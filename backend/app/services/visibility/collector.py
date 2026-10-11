"""
可见性采集编排

一次完整探测的链路::

    resolve 配置 → 建 Run(running) → 调用 provider → 归一化信源 → 算指标
                 → 落库 Run + Sources → 同步到 geo_monitor_reply（可选）

并发设计（重要）
----------------
多引擎探测是**网络密集**的，天然适合并发。但 SQLite 的并发写会互相锁表。
因此采取「**并发调用、串行落库**」：

- 线程池只负责调 provider（纯网络 IO，不碰数据库）
- 主线程统一按顺序写库

这样既拿到并发收益，又完全避开 SQLite 的写锁竞争 ——
比给每个线程配一个 session 再祈祷不冲突要可靠得多。
"""
from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from ..circuit_breaker import get_breaker
from .base import (
    ERR_REQUEST,
    PROVIDER_LLM_CHAT,
    PROVIDER_MOCK,
    BaseVisibilityProvider,
    VisibilityResult,
    build_default_prompt,
    get_provider_cls,
)
from .metrics import parse_ai_reply
from .normalizer import analyze_answer, extract_sources, source_action, top_domains

# 熔断时的错误码
ERR_CIRCUIT_OPEN = "ai_circuit_open"

# 并发上限：太高会打爆上游限流，太低拿不到并发收益
DEFAULT_MAX_WORKERS = 4


# ============================================================
#  配置解析
# ============================================================
def resolve_llm_config(db: Session, industry_id: int, llm_config_id: int = 0) -> Dict[str, Any]:
    """取一套可用的 LLM 配置（指定 id > 行业默认 > 该行业任意启用项）。"""
    from ...models import LlmConfig

    q = db.query(LlmConfig).filter(LlmConfig.is_deleted == 0, LlmConfig.status == 1)
    if llm_config_id:
        row = q.filter(LlmConfig.id == llm_config_id).first()
    else:
        row = (
            q.filter(LlmConfig.industry_id == industry_id)
            .order_by(LlmConfig.is_default.desc(), LlmConfig.id.asc())
            .first()
        )
    if not row:
        return {}
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "api_key": row.api_key,
        "base_url": row.base_url,
        "model": row.model,
        "temperature": row.temperature,
        "max_tokens": row.max_tokens,
        "timeout": row.timeout,
    }


def owned_hosts_for(db: Session, industry_id: int) -> List[str]:
    """汇总自有站点域名（品牌官网 / 自建站），用于判定「信源是不是我们自己的」。"""
    from ...brand_config import OFFICIAL_SITE_URL
    from ...models import BrandAsset

    hosts = [OFFICIAL_SITE_URL]
    rows = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id, BrandAsset.is_deleted == 0,
    ).all()
    for r in rows:
        for attr in ("official_website", "official_url", "site_url"):
            val = getattr(r, attr, "") or ""
            if val:
                hosts.append(val)
    return [h for h in hosts if h]


def brand_aliases_for(db: Session, industry_id: int) -> List[str]:
    """汇总品牌别名（品牌名 + 产品线 + 配置别名）。"""
    from ...brand_config import BRAND_ALIASES, BRAND_NAME, BRAND_PRODUCT
    from ...models import BrandAsset

    aliases = [BRAND_NAME, BRAND_PRODUCT, *BRAND_ALIASES]
    rows = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id, BrandAsset.is_deleted == 0,
    ).all()
    for r in rows:
        name = getattr(r, "brand_name", "") or ""
        if name:
            aliases.append(name)
        products = getattr(r, "core_products", "") or ""
        for p in str(products).replace("，", ",").split(","):
            if p.strip():
                aliases.append(p.strip())

    seen = set()
    out = []
    for a in aliases:
        a = (a or "").strip()
        if a and len(a) >= 2 and a not in seen:
            seen.add(a)
            out.append(a)
    return out


# ============================================================
#  单次探测
# ============================================================
def _build_provider(provider_type: str, llm_config: Dict[str, Any],
                    options: Optional[Dict[str, Any]] = None) -> BaseVisibilityProvider:
    cls = get_provider_cls(provider_type)
    return cls(llm_config, options)


def _persist_run(db: Session, *, industry_id: int, keyword: str, prompt: str,
                 monitor_id: int, llm_config: Dict[str, Any],
                 result: VisibilityResult, sources: List[Dict[str, Any]],
                 analysis: Dict[str, Any]) -> Any:
    """落库：Run + Sources（在同一个事务里完成）。"""
    from ...models import GeoVisibilityRun, GeoVisibilitySource

    run = GeoVisibilityRun(
        industry_id=industry_id,
        monitor_id=monitor_id,
        uuid=uuid.uuid4().hex,
        keyword=keyword,
        prompt=prompt,
        provider_type=result.provider_type,
        provider_key=result.provider_key,
        llm_config_id=int(llm_config.get("id") or 0),
        model_id=result.model_id,
        status="completed" if result.ok else "failed",
        answer_text=result.answer_text,
        latency_ms=result.latency_ms,
        usage_json=json.dumps(result.usage or {}, ensure_ascii=False),
        analysis_json=json.dumps(analysis, ensure_ascii=False),
        raw_request_json=json.dumps(result.raw_request or {}, ensure_ascii=False)[:20000],
        raw_response_json=json.dumps(result.raw_response or {}, ensure_ascii=False)[:20000],
        error_code=result.error_code or "",
        start_time=datetime.now(),
        complete_time=datetime.now(),
    )
    db.add(run)
    db.flush()

    for s in sources:
        # ``extract_sources`` 返回的是「干净的 Python 字典」（metadata_json 是 dict），
        # 序列化成落库形态是**数据库边界**的职责，不放到解析层去做 ——
        # 否则解析层返回的东西就既不像纯数据、也不像一行记录，谁都别扭。
        row = dict(s)
        row["metadata_json"] = json.dumps(row.get("metadata_json") or {}, ensure_ascii=False)
        db.add(GeoVisibilitySource(run_id=run.id, **row))

    db.commit()
    db.refresh(run)
    return run


def collect_one(db: Session, *, industry_id: int, keyword: str,
                llm_config: Optional[Dict[str, Any]] = None,
                llm_config_id: int = 0,
                provider_type: str = PROVIDER_LLM_CHAT,
                prompt: Optional[str] = None,
                monitor_id: int = 0,
                options: Optional[Dict[str, Any]] = None,
                owned_hosts: Optional[Sequence[str]] = None,
                brand_aliases: Optional[Sequence[str]] = None,
                auto_sync_reply: bool = True,
                use_circuit_breaker: bool = True) -> Dict[str, Any]:
    """对一个引擎做一次探测并落库，返回 Run 的字典表示（含 sources 与 analysis）。"""
    kw = (keyword or "").strip()
    if not kw:
        raise ValueError("关键词不能为空")

    cfg = llm_config if llm_config is not None else resolve_llm_config(db, industry_id, llm_config_id)
    hosts = list(owned_hosts) if owned_hosts is not None else owned_hosts_for(db, industry_id)
    aliases = list(brand_aliases) if brand_aliases is not None else brand_aliases_for(db, industry_id)
    final_prompt = (prompt or "").strip() or build_default_prompt(kw)

    # 熔断保护：上游持续失败时直接短路，不让每次探测都白等一个超时周期
    breaker = get_breaker("ai_visibility")
    if use_circuit_breaker and not breaker.allow():
        result = VisibilityResult(
            provider_type=provider_type,
            provider_key=str(cfg.get("provider") or provider_type),
            model_id=str(cfg.get("model") or ""),
            error_code=ERR_CIRCUIT_OPEN,
        )
    else:
        provider = _build_provider(provider_type, cfg, options)
        try:
            result = provider.collect(kw, final_prompt)
        except Exception as exc:  # noqa: BLE001
            from .base import classify_error

            result = VisibilityResult(
                provider_type=provider_type,
                provider_key=str(cfg.get("provider") or provider_type),
                model_id=str(cfg.get("model") or ""),
                error_code=classify_error(exc),
            )
        if use_circuit_breaker:
            if result.ok:
                breaker.record_success()
            else:
                breaker.record_failure()

    sources = extract_sources(result.answer_text, owned_hosts=hosts, brand_aliases=aliases) if result.ok else []
    analysis = analyze_answer(
        result.answer_text, sources, brand_aliases=aliases, owned_hosts=hosts,
    ) if result.ok else {}

    run = _persist_run(
        db, industry_id=industry_id, keyword=kw, prompt=final_prompt,
        monitor_id=monitor_id, llm_config=cfg, result=result,
        sources=sources, analysis=analysis,
    )

    if auto_sync_reply and monitor_id and result.ok:
        sync_reply_from_run(db, monitor_id, run, brand_name="", aliases=aliases)

    return run_to_dict(run, include_sources=True)


# ============================================================
#  多引擎并发探测
# ============================================================
def collect_multi(db: Session, *, industry_id: int, keyword: str,
                  targets: Optional[List[Dict[str, Any]]] = None,
                  prompt: Optional[str] = None,
                  monitor_id: int = 0,
                  options: Optional[Dict[str, Any]] = None,
                  auto_sync_reply: bool = False,
                  max_workers: int = DEFAULT_MAX_WORKERS) -> List[Dict[str, Any]]:
    """对多个引擎并发探测同一个问题。

    ``targets`` 形如 ``[{"llm_config_id": 1, "provider_type": "llm_chat", "label": "DeepSeek"}]``；
    留空则使用该行业全部启用的 LLM 配置（每个配置 = 一个引擎）。

    ⚠️ 线程池只做网络调用，**不碰数据库**；落库在主线程串行完成。
    """
    from ...models import LlmConfig

    kw = (keyword or "").strip()
    if not kw:
        raise ValueError("关键词不能为空")

    if targets:
        resolved: List[Dict[str, Any]] = []
        for t in targets:
            cfg = resolve_llm_config(db, industry_id, int(t.get("llm_config_id") or 0))
            ptype = str(t.get("provider_type") or PROVIDER_LLM_CHAT)
            # 只有「依赖 LLM 配置的通道」才因缺配置而被跳过。
            # 早期实现无条件跳过，导致显式指定的 mock 目标被静默丢弃 ——
            # 请求 3 个引擎、返回 0 条，还一声不吭，最难排查。
            if not cfg and ptype == PROVIDER_LLM_CHAT:
                continue
            resolved.append({
                "cfg": cfg,
                "provider_type": ptype,
                "label": str(t.get("label") or cfg.get("name") or cfg.get("model") or ptype),
            })
    else:
        rows = db.query(LlmConfig).filter(
            LlmConfig.industry_id == industry_id,
            LlmConfig.is_deleted == 0,
            LlmConfig.status == 1,
        ).order_by(LlmConfig.is_default.desc(), LlmConfig.id.asc()).all()
        resolved = [
            {
                "cfg": resolve_llm_config(db, industry_id, r.id),
                "provider_type": PROVIDER_LLM_CHAT,
                "label": r.name or r.model or f"配置#{r.id}",
            }
            for r in rows
        ]
        if not resolved:
            # 没有可用配置时退化为 mock，至少让链路可跑通、看板有数据
            resolved = [{"cfg": {}, "provider_type": PROVIDER_MOCK, "label": "模拟探测"}]

    hosts = owned_hosts_for(db, industry_id)
    aliases = brand_aliases_for(db, industry_id)
    final_prompt = (prompt or "").strip() or build_default_prompt(kw)

    # ---- 并发调用（无 DB 访问）----
    def _call(target: Dict[str, Any]) -> VisibilityResult:
        provider = _build_provider(target["provider_type"], target["cfg"], options)
        try:
            return provider.collect(kw, final_prompt)
        except Exception as exc:  # noqa: BLE001
            from .base import classify_error

            return VisibilityResult(
                provider_type=target["provider_type"],
                provider_key=str(target["cfg"].get("provider") or target["provider_type"]),
                model_id=str(target["cfg"].get("model") or ""),
                error_code=classify_error(exc),
            )

    results: List[Optional[VisibilityResult]] = [None] * len(resolved)
    workers = max(1, min(int(max_workers or DEFAULT_MAX_WORKERS), len(resolved)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_call, t): i for i, t in enumerate(resolved)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except Exception as exc:  # noqa: BLE001
                results[idx] = VisibilityResult(
                    provider_type=resolved[idx]["provider_type"],
                    provider_key=resolved[idx]["label"],
                    error_code=ERR_REQUEST,
                    raw_response={"error": str(exc)[:300]},
                )

    # ---- 串行落库 ----
    out: List[Dict[str, Any]] = []
    for target, result in zip(resolved, results):
        if result is None:
            continue
        sources = extract_sources(result.answer_text, owned_hosts=hosts, brand_aliases=aliases) if result.ok else []
        analysis = analyze_answer(
            result.answer_text, sources, brand_aliases=aliases, owned_hosts=hosts,
        ) if result.ok else {}
        run = _persist_run(
            db, industry_id=industry_id, keyword=kw, prompt=final_prompt,
            monitor_id=monitor_id, llm_config=target["cfg"], result=result,
            sources=sources, analysis=analysis,
        )
        if auto_sync_reply and monitor_id and result.ok:
            sync_reply_from_run(db, monitor_id, run, brand_name="", aliases=aliases)
        item = run_to_dict(run, include_sources=True)
        item["label"] = target["label"]
        out.append(item)

    return out


# ============================================================
#  与手工通道合流
# ============================================================
def sync_reply_from_run(db: Session, monitor_id: int, run, brand_name: str = "",
                        aliases: Optional[Iterable[str]] = None) -> Any:
    """把一次自动探测的结果同步成 ``GeoMonitorReply``。

    这样手工粘贴通道与自动采集通道的指标进入**同一张表、同一套统计口径**，
    看板不需要区分数据来源就能算总提及率。
    """
    from ...models import GeoMonitor, GeoMonitorReply

    monitor = db.query(GeoMonitor).filter(GeoMonitor.id == monitor_id).first()
    if not monitor:
        return None

    brand = (brand_name or monitor.brand_name or "").strip()
    metrics = parse_ai_reply(run.answer_text or "", brand)

    platform = run.provider_key or run.model_id or run.provider_type or "未知引擎"
    existing = db.query(GeoMonitorReply).filter(
        GeoMonitorReply.monitor_id == monitor_id,
        GeoMonitorReply.run_id == run.id,
    ).first()

    if existing:
        for k, v in metrics.items():
            setattr(existing, k, v)
        existing.platform = platform
        existing.ai_reply = run.answer_text or ""
        existing.source_channel = "auto"
        db.commit()
        db.refresh(existing)
        return existing

    reply = GeoMonitorReply(
        monitor_id=monitor_id,
        platform=platform,
        ai_reply=run.answer_text or "",
        run_id=run.id,
        source_channel="auto",
        **metrics,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return reply


# ============================================================
#  序列化
# ============================================================
def run_to_dict(run, include_sources: bool = False) -> Dict[str, Any]:
    """Run 行 → 字典（JSON 字段自动反序列化）。"""
    def _loads(raw, default):
        try:
            return json.loads(raw) if raw else default
        except (TypeError, ValueError):
            return default

    data = {
        "id": run.id,
        "industry_id": run.industry_id,
        "monitor_id": run.monitor_id,
        "parent_run_id": run.parent_run_id,
        "uuid": run.uuid,
        "keyword": run.keyword,
        "prompt": run.prompt,
        "provider_type": run.provider_type,
        "provider_key": run.provider_key,
        "llm_config_id": run.llm_config_id,
        "model_id": run.model_id,
        "status": run.status,
        "answer_text": run.answer_text,
        "latency_ms": run.latency_ms,
        "analysis": _loads(run.analysis_json, {}),
        "usage": _loads(run.usage_json, {}),
        "error_code": run.error_code,
        "start_time": run.start_time.strftime("%Y-%m-%d %H:%M:%S") if run.start_time else "",
        "complete_time": run.complete_time.strftime("%Y-%m-%d %H:%M:%S") if run.complete_time else "",
        "create_time": run.create_time.strftime("%Y-%m-%d %H:%M:%S") if run.create_time else "",
    }
    if include_sources:
        data["sources"] = [
            {
                "id": s.id,
                "source_type": s.source_type,
                "citation_key": s.citation_key,
                "title": s.title,
                "url": s.url,
                "domain": s.domain,
                "site_name": s.site_name,
                "snippet": s.snippet,
                "rank": s.rank,
                "rank_score": s.rank_score,
                "authority_level": s.authority_level,
                "is_owned": s.is_owned,
                "action": source_action({"is_owned": s.is_owned, "authority_level": s.authority_level}),
            }
            for s in (run.sources or [])
        ]
        data["top_domains"] = top_domains([
            {"domain": s.domain, "rank": s.rank, "rank_score": s.rank_score,
             "authority_level": s.authority_level, "is_owned": s.is_owned, "title": s.title}
            for s in (run.sources or [])
        ])
    return data
