"""
GEO 质检闸门（Quality Gate）—— 把「分数」升级为「决策」

为什么需要闸门
--------------
改造前，系统的质检是**两条互不相干的判定线**：

- ``rule_checker.run_full_check()`` → 一个布尔 ``overall_pass``
- ``geo_score.compute_geo_score()`` → 一个 0-100 分

问题在于：一篇文章「72 分、有 2 个没有出处的数字」，旧版只能报「通过」。
没有任何机制能说「这个数字没有依据，不能发」。分数是**描述**，不是**决策**。

闸门做的事
----------
把三路结果（本地规则 / GEO 评分 / 断言证据）汇总成**一个三态决策**：

- ``passed``       —— 达到自动通过线（默认 85），且无硬阻塞、无高优软问题
- ``needs_review`` —— 未达自动通过线但高于人工放行底线（默认 70），需人工复核
- ``blocked``      —— 存在硬阻塞项，或分数低于人工放行底线

三态的关键价值在于「**可执行**」：``passed`` 直接进发布队列，
``blocked`` 直接打回，``needs_review`` 才进人工队列。
二值判定做不到这个分流。

两类问题的严格分离
------------------
- **硬阻塞项（hard_blockers）** —— 一票否决。合规类问题（违禁词、站外引流、
  硬广话术）与「大量无依据断言」属于此类，不存在「扣点分就算了」的余地。
- **软问题（soft_issues）** —— 扣分并影响是否自动放行，但不否决。

把它们混在一个 ``issues`` 列表里，是旧版质检最根本的设计缺陷。

超时抽样兜底
------------
长文全文质检耗时不可控。超时后直接判失败会让任务卡死，直接放行会失控。
本闸门采用第三条路：**抽样打分 + 明确标记** ``inspection_scope=fallback_sampled``，
下游据此知道「这个结论的可信度边界在哪」。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

from . import claim_extractor, quality_evidence
from .circuit_breaker import get_breaker
from .geo_score import compute_geo_score
from .rule_checker import check_platform_compliance, run_full_check

# ---- 决策枚举 ----
PASSED = "passed"
NEEDS_REVIEW = "needs_review"
BLOCKED = "blocked"

DECISION_LABELS = {
    PASSED: "通过",
    NEEDS_REVIEW: "待人工复核",
    BLOCKED: "已拦截",
}

# ---- 质检范围 ----
SCOPE_FULL = "full"
SCOPE_SAMPLED = "fallback_sampled"

ALGORITHM_VERSION = "v1"

# 严重度
SEV_HIGH = "high"
SEV_MEDIUM = "medium"
SEV_LOW = "low"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# 默认阈值（可通过 env 或调用参数覆盖）
DEFAULT_THRESHOLDS: Dict[str, Any] = {
    "auto_pass": 85.0,               # 自动通过线
    "manual_floor": 70.0,            # 人工放行底线（低于此值直接拦截）
    "unverified_block": 3,           # 无依据断言达到此数量 → 硬阻塞
    "evidence_min_coverage": 0.5,    # 证据覆盖率低于此值 → 软问题
    "geo_gate": 70.0,                # GEO 分达标线
    "mind_gate": 60.0,               # 心智温度达标线
    "full_max_characters": 20000,    # 超过此长度改走抽样
    "sampled_max_characters": 6000,
    "sampled_max_ranges": 12,
}


def resolve_thresholds(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """合并默认值 / 环境变量 / 调用参数，得到本次生效的阈值快照。"""
    th = dict(DEFAULT_THRESHOLDS)
    th["auto_pass"] = _env_float("APP_QUALITY_AUTO_PASS", th["auto_pass"])
    th["manual_floor"] = _env_float("APP_QUALITY_MANUAL_FLOOR", th["manual_floor"])
    th["unverified_block"] = _env_int("APP_QUALITY_UNVERIFIED_BLOCK", th["unverified_block"])
    th["evidence_min_coverage"] = _env_float("APP_QUALITY_EVIDENCE_MIN", th["evidence_min_coverage"])
    th["full_max_characters"] = _env_int("APP_QUALITY_FULL_MAX_CHARS", th["full_max_characters"])
    th["sampled_max_characters"] = _env_int("APP_QUALITY_SAMPLED_MAX_CHARS", th["sampled_max_characters"])
    th["sampled_max_ranges"] = _env_int("APP_QUALITY_SAMPLED_MAX_RANGES", th["sampled_max_ranges"])
    if overrides:
        for k, v in overrides.items():
            if v is not None:
                th[k] = v
    # 抽样自动放行开关（对齐 GEOFlow 的 SAMPLED_AUTO_RELEASE_ENABLED）
    th["sampled_auto_release"] = _env_bool("APP_QUALITY_SAMPLED_AUTO_RELEASE", True)
    return th


def _issue(code: str, message: str, severity: str, **extra) -> Dict[str, Any]:
    return {"code": code, "message": message, "severity": severity, **extra}


# ============================================================
#  子分计算
# ============================================================
def _compliance_score(compliance: Dict[str, Any]) -> float:
    """合规子分：违规项按严重程度扣分，而不是一刀切成 0。

    一刀切会让「1 个违禁词」和「10 个违禁词 + 站外引流」得到同样的分数，
    丢掉区分度；而这两者的处理优先级完全不同。
    """
    score = 100.0
    if not compliance.get("banned_pass", True):
        score -= 50
    if not compliance.get("contact_guide_pass", True):
        score -= 40
    if not compliance.get("hard_ad_pass", True):
        score -= 30
    if compliance.get("contact_issues"):
        score -= 20
    return max(0.0, score)


def _seo_score(ai_seo: Dict[str, Any]) -> float:
    score = float(ai_seo.get("coverage_rate") or 0)
    if not ai_seo.get("entity_check", {}).get("complete", True):
        score -= 10
    if not ai_seo.get("structure_pass", True):
        score -= 10
    return max(0.0, min(100.0, score))


def _format_score(fmt: Dict[str, Any]) -> float:
    if fmt.get("word_pass"):
        score = 100.0
    else:
        word_count = float(fmt.get("word_count") or 0)
        lo = float(fmt.get("word_min") or 1)
        hi = float(fmt.get("word_max") or 1)
        target = lo if word_count < lo else hi
        deviation = abs(word_count - target) / max(target, 1)
        score = max(0.0, 100.0 - deviation * 100)
    if not fmt.get("structure_pass", True):
        score -= 15
    return max(0.0, score)


def _rule_score(rule: Dict[str, Any]) -> float:
    """本地规则综合分（0-100）。"""
    compliance = _compliance_score(rule.get("compliance") or {})
    seo = _seo_score(rule.get("ai_seo") or {})
    anti_ai = float((rule.get("anti_ai") or {}).get("ai_score") or 0)
    fmt = _format_score(rule.get("format") or {})
    return round(0.35 * compliance + 0.25 * seo + 0.25 * anti_ai + 0.15 * fmt, 1)


def _compose_score(rule_score: float, geo_score: float, evidence_coverage: float) -> float:
    """综合分 = 40% GEO 可提取性 + 30% 本地规则 + 30% 证据可信度。

    证据占 30% 是本次改造的核心：它让「数字有没有出处」这件事
    真正进入总分，而不是只作为一句提示。
    """
    return round(0.40 * geo_score + 0.30 * rule_score + 0.30 * evidence_coverage * 100, 1)


def verdict_from_results(
    *,
    rule: Dict[str, Any],
    geo: Dict[str, Any],
    platform_check: Optional[Dict[str, Any]] = None,
    verified: Optional[List[Dict[str, Any]]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
    scope: str = SCOPE_FULL,
) -> Dict[str, Any]:
    """由**已算好的**三路结果合成三态裁决。

    单独抽出这一层，是为了让已有编排链路（``orchestrator.run_quality_gate``）
    能复用同一套裁决逻辑，而不必把规则检测和 GEO 评分再算一遍。
    单一真源的价值在这里：手动流与自动流的「什么算硬阻塞」永远一致。
    """
    th = resolve_thresholds(thresholds)
    verified = verified or []
    platform_check = platform_check or {"mode": "geo", "issues": [], "soft_issues": []}
    ev = quality_evidence.coverage(verified)

    hard_blockers: List[Dict[str, Any]] = []
    soft_issues: List[Dict[str, Any]] = []
    _collect_hard_blockers(hard_blockers, rule, platform_check, verified, th)
    _collect_soft_issues(soft_issues, rule, platform_check, geo, verified, ev, th)

    rule_score = _rule_score(rule)
    geo_score_value = float(geo.get("score") or 0)
    score = _compose_score(rule_score, geo_score_value, float(ev["coverage"]))
    decision = _decide(hard_blockers, soft_issues, score, scope, th)

    unverified = [c for c in verified if c.get("status") == quality_evidence.UNVERIFIED]
    confirmed = [c for c in verified if c.get("status") == quality_evidence.VERIFIED]

    return {
        "decision": decision,
        "decision_label": DECISION_LABELS[decision],
        "score": score,
        "inspection_scope": scope,
        "scope_label": "全文质检" if scope == SCOPE_FULL else "抽样质检（超时/超长兜底）",
        "hard_blockers": hard_blockers,
        "soft_issues": soft_issues,
        "unverified_claims": claim_extractor.claims_to_dicts(unverified),
        "verified_claims": claim_extractor.claims_to_dicts(confirmed),
        "evidence_coverage": ev["coverage"],
        "evidence_stats": ev,
        "evidence_by_type": quality_evidence.by_type(verified),
        "claim_summary": claim_extractor.claim_summary(verified),
        "scores": {
            "composite": score,
            "geo": geo_score_value,
            "rule": rule_score,
            "evidence": round(float(ev["coverage"]) * 100, 1),
            "mind": float((geo.get("mind_resonance") or {}).get("score") or 0),
        },
        "thresholds": th,
    }


# ============================================================
#  主流程
# ============================================================
def run_quality_gate(
    db=None,
    *,
    content: str = "",
    title: str = "",
    industry_id: int = 0,
    task_id: int = 0,
    keywords: Optional[List[str]] = None,
    brand_info: Optional[Dict[str, Any]] = None,
    brand_name: str = "",
    brand_aliases: Optional[List[str]] = None,
    word_min: int = 800,
    word_max: int = 1500,
    platform_compliance_level: int = 2,
    mode: str = "geo",
    official_website: str = "",
    contact: str = "",
    intent_question: str = "",
    expected_recommendation: str = "",
    target_persona_name: str = "",
    core_products: str = "",
    selling_points: str = "",
    thresholds: Optional[Dict[str, Any]] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """运行一次完整质检，返回三态决策结果。

    ``persist=True`` 且给出 ``industry_id`` 时，结果会落库到 ``quality_check``。
    """
    started = time.time()
    th = resolve_thresholds(thresholds)
    text = content or ""
    content_hash = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()

    # ---- 1. 抽样决策 ----
    sample = claim_extractor.sample_ranges(
        text,
        max_characters=int(th["sampled_max_characters"]),
        max_ranges=int(th["sampled_max_ranges"]),
    )
    scope = SCOPE_SAMPLED if sample["sampled"] else SCOPE_FULL
    analysis_text = str(sample["text"])
    # 超长文本即使不抽样也建议人工过目（信息量太大，机器判断可信度下降）
    if scope == SCOPE_FULL and len(text) > int(th["full_max_characters"]):
        scope = SCOPE_SAMPLED
        sample = claim_extractor.sample_ranges(
            text,
            max_characters=int(th["sampled_max_characters"]),
            max_ranges=int(th["sampled_max_ranges"]),
        )
        analysis_text = str(sample["text"])

    # ---- 2. 三路并行分析 ----
    rule = run_full_check(
        analysis_text,
        keywords=list(keywords or []),
        brand_info=brand_info,
        word_min=word_min,
        word_max=word_max,
        platform_compliance_level=platform_compliance_level,
    )
    platform_check = check_platform_compliance(
        analysis_text,
        title=title,
        brand_name=brand_name,
        mode=mode,
        brand_aliases=brand_aliases,
    )
    geo = compute_geo_score(
        content=analysis_text,
        brand_name=brand_name,
        official_website=official_website,
        contact=contact,
        intent_question=intent_question,
        expected_recommendation=expected_recommendation,
        target_persona_name=target_persona_name,
        core_products=core_products,
        selling_points=selling_points,
    )

    claims = claim_extractor.extract_claims(analysis_text)
    verified = quality_evidence.verify_claims(db, claims, industry_id) if db is not None else []

    # ---- 3. 裁决（与 orchestrator 共用同一套合成逻辑）----
    verdict = verdict_from_results(
        rule=rule,
        geo=geo,
        platform_check=platform_check,
        verified=verified,
        thresholds=th,
        scope=scope,
    )

    result: Dict[str, Any] = {
        **verdict,
        "diagnosis": geo.get("diagnosis"),
        "rule_result": rule,
        "geo_result": geo,
        "mind_result": geo.get("mind_resonance"),
        "content_hash": content_hash,
        "algorithm_version": ALGORITHM_VERSION,
        "latency_ms": int((time.time() - started) * 1000),
    }

    if persist and db is not None and industry_id:
        result["check_id"] = _persist(db, result, industry_id=industry_id, task_id=task_id, title=title)

    return result


def _collect_hard_blockers(hard_blockers: List[Dict[str, Any]], rule: Dict[str, Any],
                           platform_check: Dict[str, Any], verified: List[Dict[str, Any]],
                           th: Dict[str, Any]) -> None:
    """收集一票否决项。"""
    compliance = rule.get("compliance") or {}
    if not compliance.get("banned_pass", True):
        words = "、".join((compliance.get("banned_words") or [])[:5])
        hard_blockers.append(_issue(
            "banned_words", f"命中广告法违禁词：{words}", SEV_HIGH,
            detail=compliance.get("banned_words"),
        ))
    if not compliance.get("contact_guide_pass", True):
        words = "、".join((compliance.get("contact_guide_words") or [])[:5])
        hard_blockers.append(_issue(
            "offsite_contact", f"出现站外引流/联系方式：{words}", SEV_HIGH,
            detail=compliance.get("contact_guide_words"),
        ))
    if not compliance.get("hard_ad_pass", True):
        hard_blockers.append(_issue(
            "hard_ad", f"硬广话术占比 {compliance.get('hard_ad_ratio')}%，超过 20% 上限", SEV_HIGH,
        ))
    if compliance.get("contact_issues"):
        hard_blockers.append(_issue(
            "contact_placement", "；".join(compliance["contact_issues"]), SEV_MEDIUM,
        ))

    # 平台合规模式下的字面硬问题
    if platform_check.get("mode") in ("platform", "green") and platform_check.get("issues"):
        for msg in platform_check["issues"]:
            # 语义软文信号（soft_issues 里的）不算硬阻塞，这里只取字面硬问题
            if msg in (platform_check.get("soft_issues") or []):
                continue
            hard_blockers.append(_issue("platform_compliance", msg, SEV_HIGH))

    # 无依据断言过多 → 虚假宣传风险，直接拦截
    unverified = [c for c in verified if c.get("status") == quality_evidence.UNVERIFIED]
    limit = int(th.get("unverified_block") or 0)
    if limit and len(unverified) >= limit:
        hard_blockers.append(_issue(
            "too_many_unverified_claims",
            f"存在 {len(unverified)} 处无依据的数据/资质/绝对化表述（阈值 {limit}），"
            f"虚假宣传风险过高，必须补齐来源或改写",
            SEV_HIGH,
            detail=[c.get("text") for c in unverified[:10]],
        ))


def _collect_soft_issues(soft_issues: List[Dict[str, Any]], rule: Dict[str, Any],
                         platform_check: Dict[str, Any], geo: Dict[str, Any],
                         verified: List[Dict[str, Any]], ev: Dict[str, Any],
                         th: Dict[str, Any]) -> None:
    """收集扣分项（影响自动放行，但不否决）。"""
    ai_seo = rule.get("ai_seo") or {}
    anti_ai = rule.get("anti_ai") or {}
    fmt = rule.get("format") or {}

    if not ai_seo.get("coverage_pass", True):
        soft_issues.append(_issue(
            "keyword_coverage", f"关键词覆盖率仅 {ai_seo.get('coverage_rate')}%，低于 70%", SEV_MEDIUM,
        ))
    if not ai_seo.get("entity_check", {}).get("complete", True):
        missing = [i["name"] for i in (ai_seo.get("entity_check") or {}).get("items", []) if not i.get("present")]
        soft_issues.append(_issue("missing_entity", f"品牌实体缺失：{'、'.join(missing)}", SEV_MEDIUM))
    if not ai_seo.get("structure_pass", True):
        soft_issues.append(_issue("no_structure", "缺少结构化小标题，不利于大模型抽取", SEV_LOW))
    if not anti_ai.get("pass", True):
        soft_issues.append(_issue(
            "ai_flavor", f"AI 味评分 {anti_ai.get('ai_score')}，存在 {anti_ai.get('cliche_count')} 处套话", SEV_MEDIUM,
        ))
    if not fmt.get("word_pass", True):
        soft_issues.append(_issue(
            "word_count",
            f"字数 {fmt.get('word_count')}，不在 {fmt.get('word_min')}-{fmt.get('word_max')} 区间", SEV_LOW,
        ))
    if not fmt.get("structure_pass", True):
        soft_issues.append(_issue(
            "paragraph_structure",
            f"段落结构不合理（{fmt.get('paragraph_count')} 段，平均 {fmt.get('avg_paragraph_length')} 字）", SEV_LOW,
        ))

    geo_value = float(geo.get("score") or 0)
    if geo_value < float(th.get("geo_gate") or 70):
        soft_issues.append(_issue(
            "geo_score", f"GEO 评分 {geo_value}，低于达标线 {th.get('geo_gate')}", SEV_HIGH,
            detail=geo.get("issues"),
        ))
    mind_value = float((geo.get("mind_resonance") or {}).get("score") or 0)
    if mind_value < float(th.get("mind_gate") or 60):
        soft_issues.append(_issue(
            "mind_score", f"心智温度 {mind_value}，低于达标线 {th.get('mind_gate')}（内容偏说明书式，缺人味）", SEV_MEDIUM,
            detail=(geo.get("mind_resonance") or {}).get("issues"),
        ))

    min_cov = float(th.get("evidence_min_coverage") or 0)
    if ev.get("total") and float(ev["coverage"]) < min_cov:
        soft_issues.append(_issue(
            "evidence_coverage",
            f"证据覆盖率 {round(float(ev['coverage']) * 100, 1)}%，低于 {round(min_cov * 100)}%"
            f"（{ev.get('unverified', 0)}/{ev.get('total', 0)} 处断言缺依据）",
            SEV_HIGH,
        ))

    # 平台语义软文信号（已计入 risk_score，这里只做提示）
    if platform_check.get("mode") in ("platform", "green"):
        for msg in (platform_check.get("soft_issues") or []):
            soft_issues.append(_issue("platform_soft", msg, SEV_MEDIUM))
        risk = int(platform_check.get("risk_score") or 0)
        if risk >= 40:
            soft_issues.append(_issue(
                "soft_ad_risk", f"平台软文风险分 {risk}（{platform_check.get('risk_level')}），建议弱化营销口吻", SEV_HIGH,
            ))


def _decide(hard_blockers: List[Dict[str, Any]], soft_issues: List[Dict[str, Any]],
            score: float, scope: str, th: Dict[str, Any]) -> str:
    """三态决策。

    与 GEOFlow 的 ``ArticleAiQualityGate`` 语义对齐：
    硬阻塞或低于人工放行底线 → blocked；
    达到自动通过线且无高优软问题 → passed；
    其余 → needs_review。
    """
    auto_pass = float(th.get("auto_pass") or 85)
    manual_floor = float(th.get("manual_floor") or 70)

    if hard_blockers or score < manual_floor:
        return BLOCKED

    high_soft = [i for i in soft_issues if i.get("severity") == SEV_HIGH]
    if score >= auto_pass and not high_soft:
        # 抽样质检默认不自动放行（可信度不足）；可用 env 打开
        if scope == SCOPE_SAMPLED and not th.get("sampled_auto_release"):
            return NEEDS_REVIEW
        return PASSED

    return NEEDS_REVIEW


def _persist(db, result: Dict[str, Any], *, industry_id: int, task_id: int, title: str) -> int:
    """把质检结果落库。"""
    from ..models import QualityCheck

    row = QualityCheck(
        industry_id=industry_id,
        task_id=task_id,
        title=title or "",
        content_hash=result["content_hash"],
        decision=result["decision"],
        score=result["score"],
        inspection_scope=result["inspection_scope"],
        hard_blockers_json=json.dumps(result["hard_blockers"], ensure_ascii=False),
        soft_issues_json=json.dumps(result["soft_issues"], ensure_ascii=False),
        unverified_claims_json=json.dumps(result["unverified_claims"], ensure_ascii=False),
        verified_claims_json=json.dumps(result["verified_claims"], ensure_ascii=False),
        evidence_coverage=result["evidence_coverage"],
        rule_result_json=json.dumps(result["rule_result"], ensure_ascii=False),
        geo_result_json=json.dumps(result["geo_result"], ensure_ascii=False),
        mind_result_json=json.dumps(result["mind_result"], ensure_ascii=False),
        thresholds_json=json.dumps(result["thresholds"], ensure_ascii=False),
        algorithm_version=result["algorithm_version"],
        latency_ms=result["latency_ms"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


def gate_for_task(db, task, **overrides) -> Dict[str, Any]:
    """便捷入口：直接对一条 ``ProductionTask`` 跑闸门。

    自动从任务上取出品牌 / 关键词 / 意图问题 / 目标画像等上下文，
    避免调用方到处重复拼装参数。
    """
    from ..models import BrandAsset, IntentQuestion, Keyword, TargetPersona

    industry_id = int(getattr(task, "industry_id", 0) or 0)
    content = (getattr(task, "final_content", "") or getattr(task, "rewrite_content", "")
               or getattr(task, "draft_content", "") or "")
    title = getattr(task, "final_title", "") or getattr(task, "title", "") or ""

    keyword_ids = [x.strip() for x in str(getattr(task, "keyword_ids", "") or "").split(",") if x.strip().isdigit()]
    keywords: List[str] = []
    if keyword_ids:
        rows = db.query(Keyword).filter(Keyword.id.in_([int(x) for x in keyword_ids])).all()
        keywords = [r.word for r in rows if getattr(r, "word", "")]

    brand = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id, BrandAsset.is_deleted == 0,
    ).order_by(BrandAsset.is_default.desc(), BrandAsset.id.asc()).first()

    brand_name = (getattr(brand, "brand_name", "") or "") if brand else ""
    brand_info = {"brand_name": brand_name} if brand_name else None

    intent_question = ""
    expected_recommendation = ""
    iq_id = int(getattr(task, "intent_question_id", 0) or 0)
    if iq_id:
        iq = db.query(IntentQuestion).filter(IntentQuestion.id == iq_id).first()
        if iq:
            intent_question = getattr(iq, "question", "") or ""
            expected_recommendation = getattr(iq, "expected_recommendation", "") or ""

    persona_name = ""
    tp_id = int(getattr(task, "target_persona_id", 0) or 0)
    if tp_id:
        tp = db.query(TargetPersona).filter(TargetPersona.id == tp_id).first()
        if tp:
            persona_name = getattr(tp, "name", "") or ""

    params: Dict[str, Any] = {
        "content": content,
        "title": title,
        "industry_id": industry_id,
        "task_id": int(getattr(task, "id", 0) or 0),
        "keywords": keywords,
        "brand_info": brand_info,
        "brand_name": brand_name,
        "mode": getattr(task, "publish_mode", "geo") or "geo",
        "intent_question": intent_question,
        "expected_recommendation": expected_recommendation,
        "target_persona_name": persona_name,
    }
    params.update(overrides)
    return run_quality_gate(db, **params)


def breaker_state() -> Dict[str, Any]:
    """质检链路熔断器状态（供运维查看）。"""
    return get_breaker("ai_quality").state()
