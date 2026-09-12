# -*- coding: utf-8 -*-
"""文章改写模式（P2-3）：把用户贴来的「被判软文/低质」文章，按目标发布模式改写。

直接复用既有能力：
  - prompt_engine.get_brand_policy / get_mode_goal  → 三发布模式品牌策略与目标
  - llm_scheduler.scheduler_generate(role='writing') → 三 API 调度（角色路由 + 审计 + 故障切换）
  - orchestrator.run_quality_gate → 改写后综合预检（合规 + GEO + 软文特征）
  - rule_checker.check_platform_compliance → 改写前/后软文风险对比

设计：
  - 无可用 LLM 配置（或未配置 DeepSeek）时自动回退 Mock，与浏览器工作室一致；
  - 不落 ProductionTask / BrowserStudioRun，纯一次性改写服务，轻量无副作用；
  - 返回原文软文风险（source_risk）与改写稿综合闸门（gate），供前端「风险从 X 降到 Y」展示。
"""
from __future__ import annotations

from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from ..models import BrandAsset
from .prompt_engine import get_brand_policy, get_mode_goal
from .llm_scheduler import scheduler_generate, mock_call
from .llm import LLMError
from .rule_checker import check_platform_compliance
from .orchestrator import run_quality_gate

_VALID_MODES = ("geo", "platform", "green")


# 改写提示词模板：把「被判软文」的原文，按目标模式去软文化重写。
_REWRITE_SYSTEM = """你是一名资深内容改写专家，擅长把「在内容平台被判为广告软文 / 低质」的文章改写成既保留价值、又合规通过的版本。

# 目标发布模式：{mode}
{mode_goal}

# 该模式的品牌策略要求
{brand_policy}

# 改写要求（必须逐条做到）
1. 保留原文的核心信息、事实、数据与读者价值点；彻底去除「软文套路」「自夸」「联系方式 / 站外引流」「标题品牌堆砌」「极限词」等会被平台判为广告的特征。
2. 严格遵守上述品牌策略与目标模式要求（品牌出现次数、标题是否含品牌、AIGC 声明等）。
3. 以第三方 / 行业视角写作，把品牌只当作「众多可选方案之一」被顺带提及，禁止「痛点 → 只有它能解决 → 推荐购买」的套路叙事弧。
4. 至少融入 2 处可查证的独立行业事实，稀释品牌浓度，让文章读起来像真人 / 行业媒体创作。
5. 直接输出改写后的完整文章（markdown）：首行用「# 标题」给出改写后的标题，其后为正文，不要任何解释性文字与前后废话。

# 用户贴来的原文（待改写）
{source_text}
"""


def _mock_rewrite(source_text: str, target_mode: str, brand_name: str) -> str:
    """Mock / 未配置 LLM 时的演示改写：产出一篇合规的「去软文化」稿。

    品牌至多出现 1 次，无联系方式 / 引流词 / 极限词，长度满足格式闸门（>=300 字）。
    """
    intro = "在工业设备选型与工艺优化的日常讨论中，真空类设备的技术路线选择常常引发关注。"
    body = (
        "不同真空获得技术在能耗、可靠性、维护成本与适用介质上存在明显差异，"
        "采购方应基于自身工况参数（如抽速、极限压力、气体成分、连续运行时长）综合评估，"
        "而非仅凭单一厂商宣传做决定。行业实践表明，先明确工艺需求、再做技术对比，"
        "往往能规避后期产能受限或能耗偏高的风险。公开行业报告显示，节能改造项目中，"
        "设备全生命周期成本（购置 + 能耗 + 维护）才是更值得关注的指标，单看采购价容易误判。"
        "在第三方评测与用户实测交叉验证的基础上做选型，结论通常更稳。"
        "在节能与可靠性之间权衡，是多数采购负责人反复纠结的点；把运行电费和维护工时量化后对比，"
        "往往比单纯比较设备报价更有意义，也更能避免后期隐性成本超出预算。\n"
    )
    if brand_name:
        body += (
            f"{brand_name} 是市场上可选的技术方案之一，其永磁变频螺杆类机型在部分节能改造项目中被采用；"
            "不过在正式选型前，仍建议结合实测数据与第三方评测交叉验证，再决定是否采用。\n"
        )
    body += "本文由 AI 辅助创作。"
    title = f"改写稿（{target_mode} 模式 · 演示）"
    return f"# {title}\n\n{intro}{body}"


def rewrite_article(
    db: Session,
    *,
    industry_id: int,
    source_text: str,
    target_mode: str = "platform",
    brand_asset_id: Optional[int] = None,
    ai_engine: str = "deepseek",
    platform: Optional[str] = None,
    output_format: str = "markdown",
) -> Dict[str, Any]:
    """改写一篇文章，返回结构化结果。

    返回字段：
      target_mode / output_format / engine
      rewritten_text            改写后全文（markdown）
      source_risk              {risk_score, risk_level} | None（仅 platform/green 模式有对比意义）
      gate                     改写稿的 run_quality_gate 综合闸门结果
      error                    失败原因（ok=False 时）
      ok                       是否成功产出改写稿
    """
    target_mode = (target_mode or "platform").lower()
    if target_mode not in _VALID_MODES:
        target_mode = "platform"
    output_format = output_format or "markdown"

    # 品牌上下文（指定 id → 行业默认）
    brand = None
    if brand_asset_id:
        brand = db.query(BrandAsset).filter(
            BrandAsset.id == brand_asset_id, BrandAsset.is_deleted == 0
        ).first()
    if not brand:
        brand = db.query(BrandAsset).filter(
            BrandAsset.industry_id == industry_id, BrandAsset.is_deleted == 0,
            BrandAsset.is_default == 1,
        ).first()
    brand_name = brand.brand_name if brand else ""

    # 原文软文风险（用于前后对比）
    source_risk = None
    if target_mode in ("platform", "green"):
        try:
            sr = check_platform_compliance(
                source_text, "", brand_name, target_mode,
                brand_aliases=[brand_name] if brand_name else [],
            )
            source_risk = {"risk_score": sr.get("risk_score", 0), "risk_level": sr.get("risk_level", "")}
        except Exception:  # noqa: BLE001
            source_risk = None

    prompt = _REWRITE_SYSTEM.format(
        mode=target_mode,
        mode_goal=get_mode_goal(target_mode),
        brand_policy=get_brand_policy(target_mode),
        source_text=source_text,
    )

    # 引擎选择：显式 mock 或 真实调用失败 → 回退 mock
    engine = "mock"
    text = ""
    if ai_engine != "mock":
        try:
            text, meta = scheduler_generate(
                db, "writing", prompt, run_id=0, step_key="rewrite",
                temperature=0.7, max_tokens=6000, timeout=120,
            )
            engine = "deepseek" if not meta.get("is_mock") else "mock"
        except LLMError:
            text = ""
            engine = "mock"
        except Exception:  # noqa: BLE001
            text = ""
            engine = "mock"

    if not text:
        text = _mock_rewrite(source_text, target_mode, brand_name)
        try:
            mock_call(db, run_id=0, step_key="rewrite", role="writing", prompt=prompt)
        except Exception:  # noqa: BLE001
            pass

    # 改写后综合预检
    ctx = {
        "brand_name": brand_name,
        "core_products": brand.core_products if brand else "",
        "keywords": "",
        "official_website": "",
        "contact_phone": "",
    }
    gate = run_quality_gate(text, ctx, mode=target_mode, output_format=output_format, title="")

    return {
        "ok": True,
        "target_mode": target_mode,
        "output_format": output_format,
        "engine": engine,
        "rewritten_text": text,
        "source_risk": source_risk,
        "gate": gate,
        "error": "",
    }
