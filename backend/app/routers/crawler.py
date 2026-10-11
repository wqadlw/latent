"""爬虫收录分析（受保护路由）

与公开的 ``routers/site.py`` 配套：``site.py`` 负责**把内容暴露给 AI**，
本模块负责**观测 AI 有没有来消费**，以及把外部站点访问日志导入进来做归因。

为什么日志导入是「粘贴文本」而不是「配置集成」
--------------------------------------------
与本系统既有的「提示词编排 + 结果回传」哲学一致：不要求用户改造站点、
不申请任何第三方权限、不引入外部依赖。用户把 Nginx/Apache 访问日志复制进来即可，
系统本地解析、分类、归因。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CrawlerHit
from ..services import access_log, attribution, geo_loop, llms_txt
from ..services.crawler_classifier import (
    CLASS_LABELS,
    ai_bot_names,
    search_bot_names,
)
from ..utils import to_dict

router = APIRouter(prefix="/api", tags=["GEO-收录观测"])


class LogImportIn(BaseModel):
    text: str = ""
    skip_human: bool = True
    dedupe: bool = True


# ============================================================
#  爬虫清单（前端展示「我们关注哪些抓取器」）
# ============================================================
@router.get("/crawler/bots")
def list_bots():
    return {"code": 0, "data": {
        "classes": [{"value": k, "label": v} for k, v in CLASS_LABELS.items()],
        "ai_bots": ai_bot_names(),
        "search_bots": search_bot_names(),
    }}


# ============================================================
#  抓取明细
# ============================================================
@router.get("/crawler/hit")
def list_hits(bot_class: Optional[str] = None, bot_name: Optional[str] = None,
              days: int = 30, keyword: str = "", limit: int = 200, offset: int = 0,
              db: Session = Depends(get_db)):
    """分页查询抓取明细，支持按分类 / 爬虫名 / 时间窗 / 路径关键词过滤。"""
    days = max(1, min(365, days))
    limit = max(1, min(1000, limit))
    since = datetime.now() - timedelta(days=days)

    q = db.query(CrawlerHit).filter(CrawlerHit.hit_time >= since)
    if bot_class:
        q = q.filter(CrawlerHit.bot_class == bot_class)
    if bot_name:
        q = q.filter(CrawlerHit.bot_name == bot_name)
    if keyword.strip():
        q = q.filter(CrawlerHit.path.contains(keyword.strip()))

    total = q.count()
    rows = q.order_by(CrawlerHit.hit_time.desc(), CrawlerHit.id.desc()).offset(offset).limit(limit).all()
    return {"code": 0, "data": {
        "total": total,
        "items": [to_dict(r) for r in rows],
    }}


@router.get("/crawler/stats")
def crawler_stats(days: int = 30, db: Session = Depends(get_db)):
    """收录看板汇总：抓取量、爬虫分布、Top 路径、日趋势、AI 收录覆盖率。"""
    return {"code": 0, "data": attribution.crawl_stats(db, days)}


@router.get("/crawler/uncovered")
def crawler_uncovered(days: int = 30, db: Session = Depends(get_db)):
    """已发布但从未被 AI 爬虫抓过的内容清单（内容缺口）。"""
    rows = attribution.uncovered_published(db, days)
    return {"code": 0, "data": {"total": len(rows), "items": rows}}


@router.get("/crawler/trend")
def crawler_trend(days: int = 30, db: Session = Depends(get_db)):
    """日粒度抓取趋势。"""
    return {"code": 0, "data": attribution.daily_ai_hits(db, days)}


# ============================================================
#  导入外部站点访问日志
# ============================================================
@router.post("/crawler/import-log")
def import_access_log(payload: LogImportIn, db: Session = Depends(get_db)):
    """解析并导入外部站点的访问日志（Nginx / Apache Combined 格式）。

    本机中间件只能记录本服务的流量，而真正需要观测的是**外部站点**上的文章被谁抓了。
    这个接口把那条通道打通：复制日志 → 粘贴 → 本地解析 → 分类 → 归因到具体文章。
    """
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(400, "日志内容不能为空")

    records, skipped = access_log.parse_log_text(text)
    if not records:
        raise HTTPException(400, "未能从日志中解析出任何有效记录，请确认格式为 Nginx/Apache Combined Log Format")

    stats = attribution.record_hits(
        db, records,
        source="manual_import",
        skip_human=payload.skip_human,
        dedupe=payload.dedupe,
    )
    return {"code": 0, "data": {
        "parsed": len(records),
        "unparsable_lines": skipped,
        **stats,
    }, "msg": f"已导入 {stats['imported']} 条抓取记录，归因到内容 {stats['attributed']} 条"}


# ============================================================
#  清理
# ============================================================
@router.delete("/crawler/hit")
def clear_hits(before_days: int = 0, db: Session = Depends(get_db)):
    """清理抓取日志。``before_days=0`` 表示清空全部。"""
    q = db.query(CrawlerHit)
    if before_days > 0:
        q = q.filter(CrawlerHit.hit_time < datetime.now() - timedelta(days=before_days))
    removed = q.delete(synchronize_session=False)
    db.commit()
    return {"code": 0, "msg": f"已清理 {removed} 条抓取记录"}


# ============================================================
#  AI 抓取入口文件预览 / 导出
# ============================================================
@router.get("/site/index")
def preview_site_index(site: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """预览将要部署到站点的 llms.txt / sitemap.xml / robots.txt。

    这三个文件由公开端点 ``/llms.txt`` ``/sitemap.xml`` ``/robots.txt`` 对外提供，
    本接口是给运营同学「先看看生成结果对不对」用的。
    """
    files = llms_txt.build_all(db, site)
    entries = llms_txt.collect_entries(db, site)
    return {"code": 0, "data": {
        **files,
        "entry_count": len(entries),
        "entries": entries[:200],
    }}


# ============================================================
#  归因闭环（B4）：发布 → 收录 → 引用 → 排名 → 回流
#
#  与上面几个端点的区别：上面是「抓取侧」的原始观测（全局，不带行业），
#  这里是「把抓取侧与 AI 引用侧接起来」的闭环视图（按行业隔离）。
# ============================================================
@router.get("/crawler/funnel")
def crawler_funnel(industry_id: int, days: int = 90, db: Session = Depends(get_db)):
    """四阶段漏斗：已发布 → AI 已收录 → 被 AI 引用 → 进入前 3。

    ``search_only_count`` 是「只被搜索引擎抓过、AI 从没来」的篇数 ——
    这个数字专门用来戳破「百度收录了就等于 AI 也收录了」的误解。
    """
    return {"code": 0, "data": geo_loop.publish_funnel(db, industry_id, days)}


@router.get("/crawler/attribution")
def crawler_attribution(industry_id: int, days: int = 90, limit: int = 200,
                        status: Optional[str] = None, db: Session = Depends(get_db)):
    """逐篇内容的归因表：抓了几次、谁抓的、被引用几次、最好排名、下一步做什么。

    默认按「越需要处理越靠前」排序，运营打开就能干活。
    """
    rows = geo_loop.attribution_table(db, industry_id, days=days, limit=limit)
    if status:
        rows = [r for r in rows if r["status"] == status]
    return {"code": 0, "data": {"total": len(rows), "items": rows}}


@router.get("/crawler/journey")
def crawler_journey(url: str, industry_id: int = 0, days: int = 365,
                    db: Session = Depends(get_db)):
    """单篇内容旅程钻取：原始抓取记录 + 在哪些问题下被引用、排名多少。

    看板说「这篇没被收录」，运营的第一反应是「真的吗」——
    所以必须能点进去看到原始记录，否则整个闭环都不可信。
    """
    if not (url or "").strip():
        raise HTTPException(400, "需要提供 url")
    return {"code": 0, "data": geo_loop.content_journey(db, url, industry_id=industry_id, days=days)}


@router.get("/crawler/recycle")
def crawler_recycle(industry_id: int, days: int = 90, limit: int = 20,
                    db: Session = Depends(get_db)):
    """回流选题：把观测结果转成下一步动作（复制已验证模式 / 推动收录 / 提升可引用性）。"""
    rows = geo_loop.recycle_suggestions(db, industry_id, days=days, limit=limit)
    return {"code": 0, "data": {"total": len(rows), "items": rows}}


@router.get("/crawler/loop-health")
def crawler_loop_health(industry_id: int, days: int = 90, db: Session = Depends(get_db)):
    """闭环健康度：指出卡得最狠的那一步，并给出下一步动作。"""
    return {"code": 0, "data": geo_loop.loop_health(db, industry_id, days)}


@router.get("/crawler/loop-overview")
def crawler_loop_overview(industry_id: int, days: int = 90, limit: int = 200,
                          db: Session = Depends(get_db)):
    """闭环看板一次拉齐（漏斗 + 健康度 + 归因表 + 回流选题）。"""
    health = geo_loop.loop_health(db, industry_id, days)
    return {"code": 0, "data": {
        "days": max(1, min(3650, int(days or 90))),
        "funnel": health["funnel"],
        "health": {k: v for k, v in health.items() if k != "funnel"},
        "attribution": geo_loop.attribution_table(db, industry_id, days=days, limit=limit),
        "recycle": geo_loop.recycle_suggestions(db, industry_id, days=days, limit=20),
    }}
