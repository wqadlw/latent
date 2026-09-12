from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Keyword, RuleLibrary, PromptLibraryItem, KnowledgeItem, IntentQuestion, GeoMonitor

router = APIRouter(prefix="/api/search", tags=["全局搜索"])


def _snip(s, n=80):
    s = (s or "").replace("\n", " ").strip()
    return s[:n] + ("..." if len(s) > n else "")


@router.get("")
def global_search(
    q: str = Query("", min_length=1),
    industry_id: int = 0,
    db: Session = Depends(get_db),
):
    """跨板块全局搜索：联合查关键词 / 规则 / 提示词 / 知识点四张表（按行业过滤、逻辑删除过滤）
    industry_id 为 0 或省略时，视为搜索全部行业（真正的全局搜索）。"""
    kw = f"%{q.strip()}%"

    # 行业过滤条件：industry_id 为真才限制行业，否则不过滤（全局）
    ind_filter_kw = [Keyword.industry_id == industry_id] if industry_id else []
    ind_filter_rule = [RuleLibrary.industry_id == industry_id] if industry_id else []
    ind_filter_prompt = [PromptLibraryItem.industry_id == industry_id] if industry_id else []
    ind_filter_know = [KnowledgeItem.industry_id == industry_id] if industry_id else []
    ind_filter_intent = [IntentQuestion.industry_id == industry_id] if industry_id else []
    ind_filter_monitor = [GeoMonitor.industry_id == industry_id] if industry_id else []

    keywords = (
        db.query(Keyword)
        .filter(*ind_filter_kw, Keyword.is_deleted == 0, Keyword.word.like(kw))
        .limit(8).all()
    )
    intents = (
        db.query(IntentQuestion)
        .filter(
            *ind_filter_intent,
            IntentQuestion.is_deleted == 0,
            or_(IntentQuestion.question.like(kw), IntentQuestion.expected_recommendation.like(kw)),
        )
        .limit(8).all()
    )
    rules = (
        db.query(RuleLibrary)
        .filter(*ind_filter_rule, RuleLibrary.is_deleted == 0, RuleLibrary.content.like(kw))
        .limit(8).all()
    )
    prompts = (
        db.query(PromptLibraryItem)
        .filter(
            *ind_filter_prompt,
            PromptLibraryItem.is_deleted == 0,
            or_(PromptLibraryItem.name.like(kw), PromptLibraryItem.content.like(kw)),
        )
        .limit(8).all()
    )
    knowledges = (
        db.query(KnowledgeItem)
        .filter(
            *ind_filter_know,
            KnowledgeItem.is_deleted == 0,
            or_(KnowledgeItem.title.like(kw), KnowledgeItem.summary.like(kw), KnowledgeItem.content.like(kw)),
        )
        .limit(8).all()
    )
    monitors = (
        db.query(GeoMonitor)
        .filter(
            *ind_filter_monitor,
            GeoMonitor.is_deleted == 0,
            or_(GeoMonitor.name.like(kw), GeoMonitor.target_query.like(kw), GeoMonitor.brand_name.like(kw)),
        )
        .limit(8).all()
    )

    return {"code": 0, "data": {
        "keyword": [{"id": k.id, "title": k.word, "snippet": _snip(k.related_product, 60)} for k in keywords],
        "rule": [{"id": r.id, "title": _snip(r.content, 40), "snippet": _snip(r.content, 80), "type": r.rule_type} for r in rules],
        "prompt": [{"id": p.id, "title": p.name, "snippet": _snip(p.content, 80), "category": p.category} for p in prompts],
        "knowledge": [{"id": k.id, "title": k.title, "snippet": _snip(k.summary or k.content, 80), "category_id": k.category_id} for k in knowledges],
        "intent": [{"id": i.id, "title": _snip(i.question, 50), "snippet": _snip(i.expected_recommendation, 80)} for i in intents],
        "monitor": [{"id": m.id, "title": _snip(m.name or m.target_query, 50), "snippet": _snip(f"品牌: {m.brand_name} | {m.target_query}", 80)} for m in monitors],
    }}
