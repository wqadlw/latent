"""GEO 质检闸门 API

把三态质检决策暴露成接口：
- 单篇即时质检（预览，不落库）
- 对生产任务跑质检（落库）
- 质检历史 / 明细 / 统计
- 熔断器健康状态

与旧版 ``routers/rule.py``（规则库 CRUD）的区别：那是**配置**接口，
这里是**执行与观测**接口。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ProductionTask, QualityCheck
from ..services import quality_gate
from ..services.quality_gate import BLOCKED, NEEDS_REVIEW, PASSED
from ..utils import to_dict

router = APIRouter(prefix="/api", tags=["GEO-质检闸门"])


# ============================================================
#  输入模型
# ============================================================
class QualityCheckIn(BaseModel):
    content: str = ""
    title: str = ""
    industry_id: int = 0
    task_id: int = 0
    keywords: List[str] = []
    brand_name: str = ""
    brand_aliases: List[str] = []
    official_website: str = ""
    contact: str = ""
    intent_question: str = ""
    expected_recommendation: str = ""
    target_persona_name: str = ""
    core_products: str = ""
    selling_points: str = ""
    word_min: int = 800
    word_max: int = 1500
    platform_compliance_level: int = 2
    mode: str = "geo"
    persist: bool = False
    thresholds: Optional[Dict[str, Any]] = None


def _json_loads(raw, default):
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _hydrate(row: QualityCheck) -> Dict[str, Any]:
    """把落库记录还原成与实时质检一致的响应结构。"""
    data = to_dict(row)
    data["hard_blockers"] = _json_loads(row.hard_blockers_json, [])
    data["soft_issues"] = _json_loads(row.soft_issues_json, [])
    data["unverified_claims"] = _json_loads(row.unverified_claims_json, [])
    data["verified_claims"] = _json_loads(row.verified_claims_json, [])
    data["thresholds"] = _json_loads(row.thresholds_json, {})
    data["decision_label"] = quality_gate.DECISION_LABELS.get(row.decision, row.decision)
    return data


# ============================================================
#  即时质检（预览）
# ============================================================
@router.post("/quality/check")
def check_content(payload: QualityCheckIn, db: Session = Depends(get_db)):
    """对一段正文跑质检闸门，返回三态决策。

    默认 ``persist=False``（不落库），适合编辑器里边写边看；
    需要留痕时传 ``persist=true`` 并提供 ``industry_id``。
    """
    if not payload.content.strip():
        raise HTTPException(400, "待质检正文不能为空")
    result = quality_gate.run_quality_gate(
        db,
        content=payload.content,
        title=payload.title,
        industry_id=payload.industry_id,
        task_id=payload.task_id,
        keywords=payload.keywords,
        brand_info={"brand_name": payload.brand_name} if payload.brand_name else None,
        brand_name=payload.brand_name,
        brand_aliases=payload.brand_aliases,
        official_website=payload.official_website,
        contact=payload.contact,
        intent_question=payload.intent_question,
        expected_recommendation=payload.expected_recommendation,
        target_persona_name=payload.target_persona_name,
        core_products=payload.core_products,
        selling_points=payload.selling_points,
        word_min=payload.word_min,
        word_max=payload.word_max,
        platform_compliance_level=payload.platform_compliance_level,
        mode=payload.mode,
        thresholds=payload.thresholds,
        persist=payload.persist,
    )
    return {"code": 0, "data": result}


# ============================================================
#  对生产任务跑质检
# ============================================================
@router.post("/quality/check-task/{task_id}")
def check_task(task_id: int, persist: bool = True, db: Session = Depends(get_db)):
    """对一条生产任务跑质检（自动带出品牌 / 关键词 / 意图问题等上下文）。"""
    task = db.query(ProductionTask).filter(
        ProductionTask.id == task_id, ProductionTask.is_deleted == 0,
    ).first()
    if not task:
        raise HTTPException(404, "生产任务不存在")

    result = quality_gate.gate_for_task(db, task, persist=persist)
    return {"code": 0, "data": result}


# ============================================================
#  质检历史
# ============================================================
@router.get("/quality/checks")
def list_checks(industry_id: int, decision: Optional[str] = None, task_id: Optional[int] = None,
                days: int = 30, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    """质检记录列表（不含大字段，列表页用）。"""
    days = max(1, min(3650, days))
    limit = max(1, min(500, limit))
    since = datetime.now() - timedelta(days=days)

    q = db.query(QualityCheck).filter(
        QualityCheck.industry_id == industry_id,
        QualityCheck.create_time >= since,
    )
    if decision:
        q = q.filter(QualityCheck.decision == decision)
    if task_id:
        q = q.filter(QualityCheck.task_id == task_id)

    total = q.count()
    rows = q.order_by(QualityCheck.id.desc()).offset(offset).limit(limit).all()
    items = []
    for r in rows:
        d = to_dict(r)
        # 列表页只回摘要，避免把三路原始 JSON 全量传回前端
        d["hard_blocker_count"] = len(_json_loads(r.hard_blockers_json, []))
        d["soft_issue_count"] = len(_json_loads(r.soft_issues_json, []))
        d["unverified_claim_count"] = len(_json_loads(r.unverified_claims_json, []))
        d["decision_label"] = quality_gate.DECISION_LABELS.get(r.decision, r.decision)
        for key in ("hard_blockers_json", "soft_issues_json", "unverified_claims_json",
                    "verified_claims_json", "rule_result_json", "geo_result_json",
                    "mind_result_json", "thresholds_json"):
            d.pop(key, None)
        items.append(d)
    return {"code": 0, "data": {"total": total, "items": items}}


@router.get("/quality/check/{check_id}")
def get_check(check_id: int, db: Session = Depends(get_db)):
    """质检记录明细（含全部断言、证据、三路原始结果）。"""
    row = db.query(QualityCheck).filter(QualityCheck.id == check_id).first()
    if not row:
        raise HTTPException(404, "质检记录不存在")
    return {"code": 0, "data": _hydrate(row)}


@router.delete("/quality/check/{check_id}")
def delete_check(check_id: int, db: Session = Depends(get_db)):
    row = db.query(QualityCheck).filter(QualityCheck.id == check_id).first()
    if not row:
        raise HTTPException(404, "质检记录不存在")
    db.delete(row)
    db.commit()
    return {"code": 0, "msg": "质检记录已删除"}


# ============================================================
#  统计
# ============================================================
@router.get("/quality/stats")
def quality_stats(industry_id: int, days: int = 30, db: Session = Depends(get_db)):
    """质检看板：决策分布、平均分、拦截原因 Top、趋势。"""
    days = max(1, min(3650, days))
    since = datetime.now() - timedelta(days=days)
    rows = db.query(QualityCheck).filter(
        QualityCheck.industry_id == industry_id,
        QualityCheck.create_time >= since,
    ).all()

    total = len(rows)
    decision_counts = {PASSED: 0, NEEDS_REVIEW: 0, BLOCKED: 0}
    blocker_counter: Dict[str, int] = {}
    issue_counter: Dict[str, int] = {}
    by_day: Dict[str, Dict[str, int]] = {}
    scores: List[float] = []
    sampled = 0

    for r in rows:
        decision_counts[r.decision] = decision_counts.get(r.decision, 0) + 1
        scores.append(float(r.score or 0))
        if r.inspection_scope == quality_gate.SCOPE_SAMPLED:
            sampled += 1
        for b in _json_loads(r.hard_blockers_json, []):
            code = str(b.get("code") or "unknown")
            blocker_counter[code] = blocker_counter.get(code, 0) + 1
        for i in _json_loads(r.soft_issues_json, []):
            code = str(i.get("code") or "unknown")
            issue_counter[code] = issue_counter.get(code, 0) + 1
        if r.create_time:
            day = r.create_time.strftime("%Y-%m-%d")
            slot = by_day.setdefault(day, {PASSED: 0, NEEDS_REVIEW: 0, BLOCKED: 0})
            slot[r.decision] = slot.get(r.decision, 0) + 1

    return {"code": 0, "data": {
        "days": days,
        "total": total,
        "decisions": decision_counts,
        "pass_rate": round(decision_counts[PASSED] / total * 100, 1) if total else 0.0,
        "block_rate": round(decision_counts[BLOCKED] / total * 100, 1) if total else 0.0,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "sampled_count": sampled,
        "top_blockers": sorted(
            ({"code": k, "count": v, "label": BLOCKER_LABELS.get(k, k)} for k, v in blocker_counter.items()),
            key=lambda x: x["count"], reverse=True,
        ),
        "top_issues": sorted(
            ({"code": k, "count": v, "label": ISSUE_LABELS.get(k, k)} for k, v in issue_counter.items()),
            key=lambda x: x["count"], reverse=True,
        ),
        "trend": [{"date": d, **c} for d, c in sorted(by_day.items())],
    }}


BLOCKER_LABELS = {
    "banned_words": "广告法违禁词",
    "offsite_contact": "站外引流/联系方式",
    "hard_ad": "硬广话术超限",
    "contact_placement": "联系方式位置不当",
    "platform_compliance": "平台合规硬问题",
    "too_many_unverified_claims": "无依据断言过多",
}

ISSUE_LABELS = {
    "keyword_coverage": "关键词覆盖不足",
    "missing_entity": "品牌实体缺失",
    "no_structure": "缺结构化小标题",
    "ai_flavor": "AI 味过重",
    "word_count": "字数不达标",
    "paragraph_structure": "段落结构问题",
    "geo_score": "GEO 分未达标",
    "mind_score": "心智温度不足",
    "evidence_coverage": "证据覆盖不足",
    "platform_soft": "平台软文信号",
    "soft_ad_risk": "软文风险分偏高",
}


# ============================================================
#  阈值与健康状态
# ============================================================
@router.get("/quality/thresholds")
def get_thresholds():
    """查看当前生效的闸门阈值（含环境变量覆盖结果）。"""
    return {"code": 0, "data": quality_gate.resolve_thresholds()}


@router.get("/quality/health")
def quality_health():
    """质检链路健康状态（熔断器）。"""
    return {"code": 0, "data": {"breaker": quality_gate.breaker_state()}}


@router.post("/quality/health/reset")
def reset_quality_health():
    """人工复位熔断器（上游模型恢复后使用）。"""
    from ..services.circuit_breaker import get_breaker

    get_breaker("ai_quality").reset()
    return {"code": 0, "msg": "质检熔断器已复位"}
