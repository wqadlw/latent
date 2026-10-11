"""
三 API 智能调度器（浏览器工作室自动化发布系统核心）

设计目标（对应需求 1 / 透明化 / 可观测）
----------------------------------------
1. 按任务类型分流：选题调研(research) / 正文撰写(writing) / 审核优化(review)，
   每个角色可绑定多个 LlmConfig（如 3 个 DeepSeek API Key）。
2. 负载均衡：同一角色下多个配置按「轮询（round-robin）」分摊请求。
3. 故障自动切换：某配置调用失败（鉴权/限流/超时/网络）自动切到下一个可用配置，
   全部失败才抛错；并记录每次尝试（成功/失败）。
4. 调用审计：每次调用（含 mock 模拟调用）都落 LlmCallLog，记录
   响应耗时(ms) / 命中配置 / 模型 / 角色 / 成功失败，供步骤透明面板与调度状态查看。

对外接口
--------
- scheduler_generate(db, role, prompt, run_id, step_key, **kw) -> (text, meta)
- mock_call(db, run_id, step_key, role, prompt, latency_ms) -> meta   # mock/doubao 路径记录
- get_scheduler_status(db) -> dict                                      # 三角色配置分配与最近耗时
- record_call(db, **fields) -> LlmCallLog
"""
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import LlmCallLog, LlmConfig
from .llm import LLMError, get_provider

# 角色 -> 步骤映射（用于没有显式 role 时反查，以及策略说明）
ROLE_BY_STEP = {
    "clarify": "research",
    "outline": "research",
    "draft": "writing",
    "depolish": "writing",
    "geo": "writing",
    "review": "review",
    "revise": "review",
    "apply_revision": "review",
}
STEP_ROLE_DESC = {
    "research": "选题调研 / 大纲（主编·规划，开启推理）",
    "writing": "正文撰写 / 精修 / GEO 终稿（写手，非推理）",
    "review": "审核优化 / 闭环整改（主编评审 + 写手改写）",
    "general": "兜底通用调用",
}

# 同角色内多配置轮询游标（进程内，足够本工具使用）
_RR: Dict[str, int] = {}


def _cfg_dict(cfg: LlmConfig) -> Dict[str, Any]:
    return {
        "provider": (getattr(cfg, "provider", "deepseek") or "deepseek"),
        "api_key": (getattr(cfg, "api_key", "") or ""),
        "base_url": (getattr(cfg, "base_url", "") or ""),
        "model": (getattr(cfg, "model", "") or ""),
    }


def record_call(db, *, run_id: int = 0, step_key: str = "", role: str = "general",
                config_id: int = 0, provider: str = "", model: str = "",
                endpoint: str = "", latency_ms: int = 0, prompt_chars: int = 0,
                status: int = 1, is_mock: int = 0, error: str = "") -> LlmCallLog:
    """插入一条 LLM 调用日志（成功或失败）。"""
    row = LlmCallLog(
        run_id=run_id, step_key=step_key, role=role, config_id=config_id,
        provider=provider, model=model, endpoint=endpoint, latency_ms=int(latency_ms),
        prompt_chars=int(prompt_chars), status=status, is_mock=is_mock, error=error or "",
    )
    try:
        db.add(row)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    return row


def _eligible_configs(db: Session, role: str) -> List[LlmConfig]:
    """返回该角色可用的启用配置：优先 role 精确匹配，其次 general 兜底。"""
    exact = db.query(LlmConfig).filter(
        LlmConfig.is_deleted == 0, LlmConfig.status == 1,
        LlmConfig.role == role,
    ).order_by(LlmConfig.sort, LlmConfig.id).all()
    if exact:
        return exact
    # 兜底：没有专门配置时，用任何启用且 role=general 的配置
    return db.query(LlmConfig).filter(
        LlmConfig.is_deleted == 0, LlmConfig.status == 1,
        LlmConfig.role == "general",
    ).order_by(LlmConfig.sort, LlmConfig.id).all()


def scheduler_generate(db, role: str, prompt: str, run_id: int = 0, step_key: str = "",
                       temperature: float = 0.7, max_tokens: int = 4000,
                       timeout: int = 60, thinking=None, reasoning_effort: str = "") -> Tuple[str, Dict[str, Any]]:
    """按角色路由生成文本，含轮询负载均衡 + 故障自动切换 + 调用审计。

    返回 (text, meta)；meta 含 prompt / latency_ms / role / config_id / model / is_mock。
    若没有任何可用配置，抛 LLMError（调用方据此回退 mock）。
    """
    configs = _eligible_configs(db, role)
    if not configs:
        raise LLMError(f"没有可用的 LLM 配置（角色={role}）。请在「设置 → LLM 配置」添加并启用。"
                       f"（未配置时系统会自动回退模拟演示模式）")
    # 轮询游标
    idx = _RR.get(role, 0) % len(configs)
    order = list(range(len(configs)))
    order = order[idx:] + order[:idx]
    errors = []
    for i in order:
        cfg = configs[i]
        _RR[role] = (i + 1) % len(configs)
        cdict = _cfg_dict(cfg)
        if not cdict.get("api_key"):
            errors.append(f"配置#{cfg.id}({cfg.name}) 未填 api_key")
            record_call(db, run_id=run_id, step_key=step_key, role=role,
                        config_id=cfg.id, provider=cfg.provider, model=cfg.model,
                        latency_ms=0, prompt_chars=len(prompt), status=0,
                        error="未填 api_key")
            continue
        provider = get_provider(cdict)
        # 主编/规划类开启推理（thinking）
        if role in ("research", "review") and thinking is None:
            cdict2 = dict(cdict)
            cdict2["thinking"] = {"type": "enabled"}
            cdict2["reasoning_effort"] = reasoning_effort or "high"
            provider = get_provider(cdict2)
        t0 = time.time()
        try:
            text = provider.generate(prompt, temperature=temperature,
                                     max_tokens=max_tokens, timeout=timeout)
            latency = int((time.time() - t0) * 1000)
            record_call(db, run_id=run_id, step_key=step_key, role=role,
                        config_id=cfg.id, provider=cfg.provider, model=cfg.model,
                        endpoint=getattr(provider, "_endpoint", ""),
                        latency_ms=latency, prompt_chars=len(prompt), status=1, is_mock=0)
            meta = {
                "prompt": prompt, "latency_ms": latency, "role": role,
                "config_id": cfg.id, "model": cfg.model, "provider": cfg.provider,
                "is_mock": 0, "status": 1,
            }
            return text, meta
        except Exception as e:  # noqa: BLE001
            latency = int((time.time() - t0) * 1000)
            msg = str(e)
            errors.append(f"配置#{cfg.id}({cfg.name})：{msg}")
            record_call(db, run_id=run_id, step_key=step_key, role=role,
                        config_id=cfg.id, provider=cfg.provider, model=cfg.model,
                        latency_ms=latency, prompt_chars=len(prompt), status=0, error=msg)
            # 继续尝试下一个配置（故障切换）
            continue
    raise LLMError("；".join(errors) or f"角色={role} 的所有 LLM 配置均调用失败")


def mock_call(db, run_id: int, step_key: str, role: str, prompt: str,
              latency_ms: Optional[int] = None) -> Dict[str, Any]:
    """mock / doubao 路径的「调用」记录：模拟耗时并落日志（标注 is_mock=1）。

    不真正调用 LLM；引擎自行产出文本。返回 meta 供步骤透明面板展示。
    """
    if latency_ms is None:
        # 模拟真实网络+推理耗时：调研/审核偏长，撰写中等
        base = {"research": (600, 1600), "writing": (500, 1400),
                "review": (500, 1300), "general": (300, 900)}.get(role, (300, 900))
        latency_ms = random.randint(*base)
    record_call(db, run_id=run_id, step_key=step_key, role=role, config_id=0,
                provider="mock", model="mock-simulator", latency_ms=latency_ms,
                prompt_chars=len(prompt), status=1, is_mock=1)
    return {
        "prompt": prompt, "latency_ms": latency_ms, "role": role,
        "config_id": 0, "model": "mock-simulator", "provider": "mock",
        "is_mock": 1, "status": 1,
    }


def get_scheduler_status(db) -> Dict[str, Any]:
    """汇总三角色 -> 配置分配与最近耗时 / 故障切换情况，供「三 API 调度」状态卡。"""
    roles = ["research", "writing", "review"]
    out = {"roles": [], "has_real_config": False, "all_mock": True}
    for role in roles:
        configs = db.query(LlmConfig).filter(
            LlmConfig.is_deleted == 0, LlmConfig.status == 1,
            LlmConfig.role == role,
        ).order_by(LlmConfig.sort, LlmConfig.id).all()
        if not configs:
            configs = db.query(LlmConfig).filter(
                LlmConfig.is_deleted == 0, LlmConfig.status == 1,
                LlmConfig.role == "general",
            ).order_by(LlmConfig.sort, LlmConfig.id).all()
        pooled = []
        for c in configs:
            # 最近一次成功耗时
            last_ok = db.query(LlmCallLog).filter(
                LlmCallLog.config_id == c.id, LlmCallLog.status == 1,
                LlmCallLog.is_mock == 0,
            ).order_by(LlmCallLog.id.desc()).first()
            # 最近失败次数（近 50 条）
            fail = db.query(func.count(LlmCallLog.id)).filter(
                LlmCallLog.config_id == c.id, LlmCallLog.status == 0,
            ).scalar() or 0
            pooled.append({
                "config_id": c.id, "name": c.name, "provider": c.provider,
                "model": c.model, "role": c.role, "status": c.status,
                "last_latency_ms": last_ok.latency_ms if last_ok else None,
                "fail_count": int(fail),
            })
            if c.api_key:
                out["has_real_config"] = True
                out["all_mock"] = False
        out["roles"].append({
            "role": role, "desc": STEP_ROLE_DESC.get(role, ""),
            "pool_size": len(pooled), "configs": pooled,
        })
    return out
