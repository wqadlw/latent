# -*- coding: utf-8 -*-
"""
编排共享层（Orchestrator）

把「浏览器工作室自动流」与「生产手动流」两路径共有的编排知识收敛到单一真源，
供两个 UI / 两套后端处理器委托，避免步骤定义、提示词映射、质量闸门在多处重复与漂移。

本模块只承载「编排知识」与「纯函数闸门」，不触碰任何模型调用（LLM provider /
scheduler / generation 仍由各引擎自行负责），也不改变任何前端 URL。

对外暴露：
  - get_step_defs(engine_kind)        : 10 步流水线定义（4 元组，兼容既有 /steps 端点）
  - STEP_PROMPT_KEYS / ROLE_BY_STEP   : 步骤→自动化提示词 key / 三 API 调度角色（单一真源）
  - run_quality_gate(...)             : 综合质量闸门（平台合规 + GEO 评分 → gate_pass）
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..services.rule_checker import run_full_check, check_platform_compliance
from ..services.geo_score import compute_geo_score


# ============================================================
#  1) 步骤注册表（单一真源）
#     双智能体 10 步流水线：每步独立状态 + 独立 AI 原文可回看 + 标注角色。
#     agent: planner=主编(规划/评审/整改指令) / writer=写手(落地) / system=系统/人 / dual=双角色协同
# ============================================================
def get_step_defs(engine_kind: str):
    """返回 10 步流水线定义：(step_no, step_key, title, agent)。

    形状与历史 _step_defs 完全一致，前端 /api/automation-prompts/steps 依赖 4 元组解析。
    """
    if engine_kind == "deepseek":
        return [
            (1, "connect", "① 连接引擎并准备创作上下文（系统）", "system"),
            (2, "clarify", "①b 主编·明晰选题（创作简报）", "planner"),
            (3, "outline", "② 主编·拟定大纲", "planner"),
            (4, "draft", "③ 写手·初稿", "writer"),
            (5, "depolish", "④ 写手·去AI味精修", "writer"),
            (6, "geo", "⑤ 写手·GEO强化 + 平台过审（终稿）", "writer"),
            (7, "review", "⑥ 主编·评审 + 平台过审/GEO评分", "planner"),
            (8, "revise", "⑦ 闭环整改：主编指令 → 写手改写（可多轮）", "dual"),
            (9, "confirm", "⑧ 你满意确认 → 加入内容中心", "system"),
            (10, "publish", "⑨ 发布到目标平台", "system"),
        ]
    label = "模拟豆包" if engine_kind == "mock" else "豆包"
    return [
        (1, "connect", f"① 打开{label}并准备上下文（系统）", "system"),
        (2, "clarify", f"①b 主编·明晰选题（{label}）", "planner"),
        (3, "outline", f"② 主编·拟定大纲（{label}）", "planner"),
        (4, "draft", f"③ 写手·初稿（{label}）", "writer"),
        (5, "depolish", f"④ 写手·去AI味精修（{label}）", "writer"),
        (6, "geo", f"⑤ 写手·GEO强化 + 过审终稿（{label}）", "writer"),
        (7, "review", "⑥ 主编·评审 + 平台过审/GEO评分", "planner"),
        (8, "revise", "⑦ 闭环整改：主编指令 → 写手改写", "dual"),
        (9, "confirm", "⑧ 你满意确认 → 加入内容中心", "system"),
        (10, "publish", "⑨ 发布到目标平台", "system"),
    ]


# 步骤 → 自动化提示词表 key（automation_prompt 体系）。
# 与前端 Manual.vue 的 STEP_PROMPT_KEYS 对齐，抽为后端单一真源，前端后续可直接委托此表。
STEP_PROMPT_KEYS: Dict[str, str] = {
    "clarify": "PLANNER_CLARIFY_PROMPT",
    "outline": "PLANNER_OUTLINE_PROMPT",
    "draft": "STAGE_draft",
    "depolish": "STAGE_depolish",
    "geo": "STAGE_geo",
    "review": "PLANNER_REVIEW_PROMPT",
    "revise": "PLANNER_DIRECTIVE_PROMPT",
}

# 步骤 → 三 API 调度角色（research / writing / review / general / human / system）。
# 单一真源：以 llm_scheduler.ROLE_BY_STEP（真实调度边界，含 apply_revision）为基底派生，
# 再补「无需 AI 调用的步骤」display 角色（confirm=human / publish=system）供前端可视化。
# 这样后端只保留一份角色映射，彻底消除 orchestrator 与 llm_scheduler 两份漂移。
from ..services.llm_scheduler import ROLE_BY_STEP as _SCHEDULER_ROLE_BY_STEP

ROLE_BY_STEP: Dict[str, str] = {
    **_SCHEDULER_ROLE_BY_STEP,
    "confirm": "human",
    "publish": "system",
}


# ============================================================
#  2) 综合质量闸门（单一真源）
#     平台合规自检（rule_checker.run_full_check）+ 软文特征硬闸门（platform/green 模式）
#     + GEO 评分（geo_score.compute_geo_score）→ 综合 gate_pass。
#     原 doubao_studio._run_review / _run_compliance_check 已收敛于此。
# ============================================================
def _compliance_gate(text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """平台合规自检：复用系统本地规则引擎（违禁词/硬广/联系方式/AI味/关键词/格式）。

    字数区间放宽（300-3000）聚焦合规与 AI 味，避免因篇幅判定误伤正常短/长文。
    返回 run_full_check 字典；硬闸门只认「违禁词/硬广/联系方式 + AI味」两类，
    字数偏短、缺小标题、关键词覆盖等作为「优化建议」保留在 issues，不阻塞发布。
    """
    try:
        kws = [k.strip() for k in (ctx.get("keywords") or "").split("、") if k.strip()]
    except Exception:
        kws = []
    brand_info = {
        "brand_name": ctx.get("brand_name", "") or "",
        "official_website": ctx.get("official_website", "") or "",
        "contact_phone": ctx.get("contact_phone", "") or "",
    }
    try:
        check = run_full_check(
            text, keywords=kws, brand_info=brand_info,
            word_min=300, word_max=3000, platform_compliance_level=2,
        )
    except Exception as e:  # noqa: BLE001
        return {"overall_pass": True, "issues": [f"合规自检跳过（引擎异常：{e}）"],
                "compliance": {}, "ai_seo": {}, "anti_ai": {}, "format": {}}
    _compliance_pass = bool((check.get("compliance") or {}).get("pass"))
    _anti_ai_pass = bool((check.get("anti_ai") or {}).get("pass"))
    check["overall_pass"] = _compliance_pass and _anti_ai_pass
    return check


def run_quality_gate(
    text: str,
    ctx: Optional[Dict[str, Any]] = None,
    *,
    mode: str = "geo",
    output_format: Optional[str] = None,
    title: str = "",
) -> Dict[str, Any]:
    """综合质量闸门：平台合规 + GEO 评分 → gate_pass。

    参数：
      - text           : 待评审终稿
      - ctx            : 创作上下文（含 brand_name / keywords / core_products 等字段）
      - mode           : 已解析的发布模式 geo / platform / green / official
      - output_format  : 已解析的输出格式 markdown / mdx（mdx 视为官网模式）
      - title          : 文章标题（软文特征检测用）

    返回与历史 _run_review 完全一致的结构：
      - compliance_pass / compliance
      - platform_compliance（platform/green 模式才有）
      - geo_score / geo
      - gate_pass（综合闸门）
      - issues（合并的可执行问题清单，带 [平台合规·A级] / [GEO优化·B级] 前缀）
    """
    ctx = ctx or {}
    # 1) 平台合规自检
    compliance = _compliance_gate(text, ctx)
    compliance_pass = bool(compliance.get("overall_pass"))
    # 1.5) platform / green 模式叠加「软文特征」硬闸门（内容平台高频拒稿原因精准拦截）
    _is_official = (output_format == "mdx")
    platform_compliance = None
    if mode in ("platform", "green"):
        _core = ctx.get("core_products", "") or ""
        _aliases = [a.strip().strip("（）()").strip() for a in re.split(r"[，,;；/、]", _core) if a.strip()]
        _aliases += ["示例品牌", "示例产品"]
        _seen = set()
        _aliases = [a for a in _aliases if a and len(a) >= 2 and not (a in _seen or _seen.add(a))]
        platform_compliance = check_platform_compliance(
            text, title or "", ctx.get("brand_name", "") or "", mode,
            brand_aliases=_aliases,
        )
        compliance_pass = compliance_pass and bool(platform_compliance.get("pass"))
    # 2) GEO 评分（本地启发式，零 AI 调用）
    try:
        geo = compute_geo_score(
            content=text,
            brand_name=ctx.get("brand_name", "") or "",
            official_website=ctx.get("official_website", "") or "",
            contact=ctx.get("contact_phone", "") or "",
            intent_question=ctx.get("intent_question", "") or "",
            expected_recommendation=ctx.get("expected_recommendation", "") or "",
            target_persona_name=ctx.get("target_persona_name", "") or "",
            core_products=ctx.get("core_products", "") or "",
            selling_points=ctx.get("selling_points", "") or "",
        )
    except Exception as e:  # noqa: BLE001
        geo = {"score": 0, "gate_pass": False,
               "issues": [f"GEO评分异常：{e}"], "dimensions": {}, "signals_present": [],
               "mind_resonance": {}, "diagnosis": {}}
    geo_score = int(geo.get("score") or 0)
    geo_pass = bool(geo.get("gate_pass"))
    # 3) 综合闸门：
    #    - geo 模式：平台过审 AND GEO达标（强品牌/GEO 双闸门）；
    #    - platform / green 模式：仅认「合规闸门」（含软文自检），GEO 仅作建议不阻塞；
    #    - official(mdx) 模式：仅认基础合规闸门（违禁词/硬广/联系方式），GEO 与软文自检均不阻塞。
    if _is_official:
        gate_pass = bool(compliance_pass)
    elif mode in ("platform", "green"):
        gate_pass = bool(compliance_pass)
    else:
        gate_pass = bool(compliance_pass and geo_pass)
    # 4) 合并可执行问题清单（分级前缀，供 AI 整改回写 Prompt）
    issues = []
    for i in (compliance.get("issues") or []):
        issues.append(f"[平台合规·A级] {i}")
    if platform_compliance:
        for i in (platform_compliance.get("issues") or []):
            issues.append(f"[平台合规·A级] {i}")
    for i in (geo.get("issues") or []):
        issues.append(f"[GEO优化·B级] {i}")
    return {
        "compliance_pass": compliance_pass,
        "compliance": compliance,
        "platform_compliance": platform_compliance,
        "geo_score": geo_score,
        "geo": geo,
        "gate_pass": gate_pass,
        "issues": issues,
    }
