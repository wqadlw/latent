"""AI 可见性采集 API（受保护路由）

与 ``routers/geo_monitor.py`` 的分工：
- ``geo_monitor``  管理**监测任务**（问什么、测哪个品牌）与**人工粘贴通道**
- ``visibility``   负责**自动探测**：调模型、拿回答、解析信源、落库

两条通道最终汇入同一张 ``geo_monitor_reply``，看板不需要区分来源。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import GeoMonitor, GeoVisibilityRun, GeoVisibilitySource
from ..services.circuit_breaker import get_breaker
from ..services.visibility import analytics, collector, competitor
from ..services.visibility.base import PROVIDER_LLM_CHAT, list_provider_types

router = APIRouter(prefix="/api", tags=["GEO-可见性采集"])


# ============================================================
#  输入模型
# ============================================================
class CollectIn(BaseModel):
    industry_id: int
    keyword: str = ""
    monitor_id: int = 0
    llm_config_id: int = 0
    provider_type: str = PROVIDER_LLM_CHAT
    prompt: str = ""
    temperature: float = 0.3
    max_tokens: int = 2000
    auto_sync_reply: bool = True


class MultiCollectTarget(BaseModel):
    llm_config_id: int = 0
    provider_type: str = PROVIDER_LLM_CHAT
    label: str = ""


class MultiCollectIn(BaseModel):
    industry_id: int
    keyword: str = ""
    monitor_id: int = 0
    targets: List[MultiCollectTarget] = []
    prompt: str = ""
    temperature: float = 0.3
    max_tokens: int = 2000
    max_workers: int = 4
    auto_sync_reply: bool = False


# ============================================================
#  元信息
# ============================================================
@router.get("/visibility/providers")
def list_providers():
    """可用的采集通道类型。"""
    return {"code": 0, "data": {
        "providers": list_provider_types(),
        "breaker": get_breaker("ai_visibility").state(),
    }}


@router.get("/visibility/configs")
def list_available_configs(industry_id: int, db: Session = Depends(get_db)):
    """本行业可用于探测的 LLM 配置（每个配置 = 一个「引擎」）。"""
    from ..models import LlmConfig

    rows = db.query(LlmConfig).filter(
        LlmConfig.industry_id == industry_id,
        LlmConfig.is_deleted == 0,
        LlmConfig.status == 1,
    ).order_by(LlmConfig.is_default.desc(), LlmConfig.id.asc()).all()
    return {"code": 0, "data": [
        {
            "id": r.id,
            "name": r.name,
            "provider": r.provider,
            "model": r.model,
            "is_default": r.is_default,
            "has_key": bool(r.api_key),
            "role": r.role,
        }
        for r in rows
    ]}


# ============================================================
#  采集
# ============================================================
@router.post("/visibility/collect")
def collect(payload: CollectIn, db: Session = Depends(get_db)):
    """对单个引擎做一次探测。"""
    keyword = (payload.keyword or "").strip()
    monitor = None
    if payload.monitor_id:
        monitor = db.query(GeoMonitor).filter(GeoMonitor.id == payload.monitor_id).first()
        if not monitor:
            raise HTTPException(404, "监测任务不存在")
        keyword = keyword or (monitor.target_query or "")
    if not keyword:
        raise HTTPException(400, "关键词不能为空（也可通过 monitor_id 从监测任务带出）")

    try:
        data = collector.collect_one(
            db,
            industry_id=payload.industry_id,
            keyword=keyword,
            llm_config_id=payload.llm_config_id,
            provider_type=payload.provider_type,
            prompt=payload.prompt,
            monitor_id=payload.monitor_id,
            options={"temperature": payload.temperature, "max_tokens": payload.max_tokens},
            auto_sync_reply=payload.auto_sync_reply,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    msg = "探测完成" if not data.get("error_code") else f"探测失败：{data['error_code']}"
    return {"code": 0, "data": data, "msg": msg}


@router.post("/visibility/collect-multi")
def collect_multi(payload: MultiCollectIn, db: Session = Depends(get_db)):
    """对多个引擎**并发**探测同一个问题（一问 × N 引擎）。"""
    keyword = (payload.keyword or "").strip()
    if payload.monitor_id:
        monitor = db.query(GeoMonitor).filter(GeoMonitor.id == payload.monitor_id).first()
        if not monitor:
            raise HTTPException(404, "监测任务不存在")
        keyword = keyword or (monitor.target_query or "")
    if not keyword:
        raise HTTPException(400, "关键词不能为空")

    targets = [
        {"llm_config_id": t.llm_config_id, "provider_type": t.provider_type, "label": t.label}
        for t in payload.targets
    ]
    try:
        runs = collector.collect_multi(
            db,
            industry_id=payload.industry_id,
            keyword=keyword,
            targets=targets or None,
            prompt=payload.prompt,
            monitor_id=payload.monitor_id,
            options={"temperature": payload.temperature, "max_tokens": payload.max_tokens},
            auto_sync_reply=payload.auto_sync_reply,
            max_workers=payload.max_workers,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    ok = sum(1 for r in runs if not r.get("error_code"))
    return {"code": 0, "data": {"total": len(runs), "succeeded": ok, "runs": runs},
            "msg": f"已完成 {len(runs)} 个引擎探测，成功 {ok} 个"}


@router.post("/visibility/monitor/{monitor_id}/collect")
def collect_for_monitor(monitor_id: int, max_workers: int = 4,
                        auto_sync_reply: bool = True, db: Session = Depends(get_db)):
    """对某个监测任务一键并发探测（用该行业全部启用的模型配置）。"""
    monitor = db.query(GeoMonitor).filter(GeoMonitor.id == monitor_id).first()
    if not monitor:
        raise HTTPException(404, "监测任务不存在")
    if not (monitor.target_query or "").strip():
        raise HTTPException(400, "该监测任务未设置目标问题")

    runs = collector.collect_multi(
        db,
        industry_id=monitor.industry_id,
        keyword=monitor.target_query,
        targets=None,
        monitor_id=monitor_id,
        max_workers=max_workers,
        auto_sync_reply=auto_sync_reply,
    )
    ok = sum(1 for r in runs if not r.get("error_code"))
    return {"code": 0, "data": {"total": len(runs), "succeeded": ok, "runs": runs},
            "msg": f"已完成 {len(runs)} 个引擎探测，成功 {ok} 个"}


# ============================================================
#  查询
# ============================================================
@router.get("/visibility/run")
def list_runs(industry_id: int, keyword: str = "", monitor_id: int = 0,
              status: str = "", days: int = 30, limit: int = 50, offset: int = 0,
              db: Session = Depends(get_db)):
    """探测记录列表（不含回答正文，列表页用）。"""
    days = max(1, min(3650, days))
    limit = max(1, min(500, limit))
    since = datetime.now() - timedelta(days=days)

    q = db.query(GeoVisibilityRun).filter(
        GeoVisibilityRun.industry_id == industry_id,
        GeoVisibilityRun.create_time >= since,
        GeoVisibilityRun.parent_run_id == 0,
    )
    if keyword.strip():
        q = q.filter(GeoVisibilityRun.keyword.contains(keyword.strip()))
    if monitor_id:
        q = q.filter(GeoVisibilityRun.monitor_id == monitor_id)
    if status:
        q = q.filter(GeoVisibilityRun.status == status)

    total = q.count()
    rows = q.order_by(GeoVisibilityRun.id.desc()).offset(offset).limit(limit).all()

    items = []
    for r in rows:
        try:
            analysis = json.loads(r.analysis_json) if r.analysis_json else {}
        except (TypeError, ValueError):
            analysis = {}
        source_count = db.query(GeoVisibilitySource).filter(
            GeoVisibilitySource.run_id == r.id
        ).count()
        items.append({
            "id": r.id,
            "keyword": r.keyword,
            "monitor_id": r.monitor_id,
            "provider_type": r.provider_type,
            "provider_key": r.provider_key,
            "model_id": r.model_id,
            "status": r.status,
            "error_code": r.error_code,
            "latency_ms": r.latency_ms,
            "source_count": source_count,
            "brand_visible": analysis.get("brand_visible"),
            "top3": analysis.get("top3"),
            "best_brand_rank": analysis.get("best_brand_rank"),
            "sentiment": analysis.get("sentiment"),
            "create_time": r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else "",
        })
    return {"code": 0, "data": {"total": total, "items": items}}


@router.get("/visibility/run/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    """探测明细（含 AI 原始回答与被引用的全部信源）。"""
    run = db.query(GeoVisibilityRun).filter(GeoVisibilityRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "探测记录不存在")
    return {"code": 0, "data": collector.run_to_dict(run, include_sources=True)}


@router.delete("/visibility/run/{run_id}")
def delete_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(GeoVisibilityRun).filter(GeoVisibilityRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "探测记录不存在")
    # 信源由 GeoVisibilityRun.sources 的 delete-orphan 级联删除，
    # 不再手工 bulk delete —— 两条删除路径并存容易漏掉一条、也容易重复删。
    db.delete(run)
    db.commit()
    return {"code": 0, "msg": "探测记录已删除"}


@router.get("/visibility/sources")
def list_sources(run_id: int = 0, industry_id: int = 0, days: int = 30,
                 limit: int = 200, db: Session = Depends(get_db)):
    """信源明细：可以按单次探测查，也可以按行业 + 时间窗汇总。"""
    q = db.query(GeoVisibilitySource)
    if run_id:
        q = q.filter(GeoVisibilitySource.run_id == run_id)
    elif industry_id:
        since = datetime.now() - timedelta(days=max(1, min(3650, days)))
        sub = db.query(GeoVisibilityRun.id).filter(
            GeoVisibilityRun.industry_id == industry_id,
            GeoVisibilityRun.create_time >= since,
        ).subquery()
        q = q.filter(GeoVisibilitySource.run_id.in_(sub))
    else:
        raise HTTPException(400, "需要提供 run_id 或 industry_id")

    rows = q.order_by(GeoVisibilitySource.run_id.desc(), GeoVisibilitySource.rank.asc()).limit(
        max(1, min(1000, limit))
    ).all()
    return {"code": 0, "data": [
        {
            "id": r.id, "run_id": r.run_id, "rank": r.rank, "title": r.title,
            "url": r.url, "domain": r.domain, "authority_level": r.authority_level,
            "is_owned": r.is_owned, "citation_key": r.citation_key,
            "source_type": r.source_type, "rank_score": r.rank_score,
        }
        for r in rows
    ]}


# ============================================================
#  分析看板（B3）
#  采集只解决「拿到数据」，分析才回答「数据说明什么」。
# ============================================================
class CompetitorIn(BaseModel):
    industry_id: int
    name: str
    aliases: List[str] = []
    is_self: int = 0
    note: str = ""


@router.get("/visibility/overview")
def visibility_overview(industry_id: int, days: int = 30, keyword: str = "",
                        monitor_id: int = 0, db: Session = Depends(get_db)):
    """整个看板一次拉齐：6 KPI + 趋势 + 信源偏好榜 + 词云 + 选题建议。

    刻意做成单个端点：看板由 5 个面板组成，拆成 5 个请求会让前端出现
    「卡片已经显示了、折线还在转圈」的割裂状态，而且窗口参数必须处处一致。
    """
    data = analytics.overview(db, industry_id, days=days, keyword=keyword,
                              monitor_id=monitor_id)
    data["competitor_board"] = competitor.board(
        db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id
    )
    data["gap_analysis"] = competitor.gap_analysis(data["competitor_board"])
    return {"code": 0, "data": data}


@router.get("/visibility/kpis")
def visibility_kpis(industry_id: int, days: int = 30, keyword: str = "",
                    monitor_id: int = 0, db: Session = Depends(get_db)):
    """只要 6 个 KPI（供嵌入其他页面时复用）。"""
    runs = analytics.sample_runs(
        analytics.load_runs(db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id)
    )
    kpis = analytics.compute_kpis(runs)
    return {"code": 0, "data": {"kpis": kpis, "kpi_cards": analytics.kpi_cards(kpis)}}


@router.get("/visibility/trend")
def visibility_trend(industry_id: int, days: int = 30, keyword: str = "",
                     monitor_id: int = 0, db: Session = Depends(get_db)):
    """日粒度趋势（缺数据的日子补 0，不跳过）。"""
    return {"code": 0, "data": analytics.daily_trend(
        db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id
    )}


@router.get("/visibility/source-preferences")
def visibility_source_preferences(industry_id: int, days: int = 30, keyword: str = "",
                                  monitor_id: int = 0, limit: int = 20,
                                  db: Session = Depends(get_db)):
    """信源偏好榜：哪些域名被 AI 偏爱引用（附行动建议）。"""
    return {"code": 0, "data": analytics.source_preferences(
        db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id, limit=limit
    )}


@router.get("/visibility/term-cloud")
def visibility_term_cloud(industry_id: int, days: int = 30, keyword: str = "",
                          monitor_id: int = 0, limit: int = 60,
                          db: Session = Depends(get_db)):
    return {"code": 0, "data": analytics.term_cloud(
        db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id, limit=limit
    )}


@router.get("/visibility/topic-suggestions")
def visibility_topic_suggestions(industry_id: int, days: int = 30, keyword: str = "",
                                 limit: int = 10, db: Session = Depends(get_db)):
    """把信源偏好榜接回选题 —— 把「看板」变成「可执行的下一步」。"""
    return {"code": 0, "data": analytics.topic_suggestions(
        db, industry_id, days=days, keyword=keyword, limit=limit
    )}


@router.get("/visibility/compare")
def visibility_compare(industry_id: int, keywords: str = "", days: int = 30,
                       db: Session = Depends(get_db)):
    """多个关键词横向对比 KPI（``keywords`` 用逗号分隔），按可见率升序。"""
    items = [k.strip() for k in (keywords or "").split(",") if k.strip()]
    if not items:
        raise HTTPException(400, "请用 keywords 传入逗号分隔的关键词")
    return {"code": 0, "data": analytics.compare_keywords(db, industry_id, items, days=days)}


# ============================================================
#  竞品对比（B3）
# ============================================================
@router.get("/visibility/competitors")
def list_competitors(industry_id: int, db: Session = Depends(get_db)):
    rows = competitor.list_competitors(db, industry_id)
    return {"code": 0, "data": [competitor.competitor_to_dict(r) for r in rows]}


@router.post("/visibility/competitors")
def save_competitor(payload: CompetitorIn, db: Session = Depends(get_db)):
    try:
        row = competitor.upsert_competitor(
            db, payload.industry_id, payload.name,
            aliases=payload.aliases, is_self=payload.is_self, note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"code": 0, "data": competitor.competitor_to_dict(row), "msg": "已保存"}


@router.delete("/visibility/competitors/{competitor_id}")
def remove_competitor(competitor_id: int, db: Session = Depends(get_db)):
    if not competitor.delete_competitor(db, competitor_id):
        raise HTTPException(404, "竞品不存在")
    return {"code": 0, "msg": "已删除"}


@router.post("/visibility/competitors/seed")
def seed_competitors(industry_id: int, db: Session = Depends(get_db)):
    """把本品牌写入竞品库作为对比基线（幂等，可重复调用）。"""
    row = competitor.seed_self_brand(db, industry_id)
    return {"code": 0, "data": competitor.competitor_to_dict(row), "msg": "本品牌基线已就绪"}


@router.post("/visibility/competitors/detect/{run_id}")
def detect_competitors(run_id: int, db: Session = Depends(get_db)):
    """对指定探测跑一次竞品检测并落库。"""
    run = db.query(GeoVisibilityRun).filter(GeoVisibilityRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "探测记录不存在")
    detections = competitor.detect_from_run(db, run)
    return {"code": 0, "data": detections, "msg": f"检出 {len(detections)} 个竞品"}


@router.get("/visibility/competitors/board")
def competitor_board(industry_id: int, days: int = 30, keyword: str = "",
                     monitor_id: int = 0, db: Session = Depends(get_db)):
    """我们 vs 竞品的提及率对比（基线恒排第一行）。"""
    rows = competitor.board(db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id)
    return {"code": 0, "data": {"board": rows, "gap": competitor.gap_analysis(rows)}}


@router.post("/visibility/competitors/suggest")
def suggest_competitors(payload: CollectIn, db: Session = Depends(get_db)):
    """可选：让模型从最近一次探测的回答里「猜」出还没入库的竞品名。

    结果仅作候选展示，不会自动入库 —— 模型可能给出通用词或错误名称，
    直接写进竞品库会污染整个对比看板。
    """
    from ..services.visibility.competitor import extract_competitor_names

    runs = analytics.load_runs(db, payload.industry_id, days=30, keyword=payload.keyword)
    if not runs:
        raise HTTPException(404, "该条件下没有探测记录")
    run = runs[-1]
    cfg = collector.resolve_llm_config(db, payload.industry_id, payload.llm_config_id)
    names = extract_competitor_names(run.answer_text or "", cfg)
    known = {c.name for c in competitor.list_competitors(db, payload.industry_id)}
    return {"code": 0, "data": {
        "run_id": run.id,
        "candidates": [n for n in names if n not in known],
        "known": [n for n in names if n in known],
    }}
