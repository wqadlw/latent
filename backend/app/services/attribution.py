"""
爬虫抓取归因：把「一次抓取」关联到「一篇内容」，并汇总收录指标

要回答的三个问题
----------------
1. **收录了吗** —— 我们的内容 URL 有没有被 AI 爬虫抓过？
2. **谁在抓** —— GPTBot / Bytespider / PerplexityBot 各自来了几次？
3. **抓了什么** —— 哪些文章被反复抓、哪些从没被抓（内容缺口信号）？

与 ``services/llms_txt.py`` 的分工
----------------------------------
``llms_txt`` 负责「把内容暴露出去」（供给侧），
本模块负责「观测有没有被消费」（需求侧）。两者合起来才构成收录闭环。

URL 归因策略
------------
把三处已知的已发布 URL（``production_task.publish_url`` / ``publish_job.result_url`` /
``content_asset.publish_url``）归一化成「路径」建索引，再用抓取记录的路径去匹配。
匹配是**归一化后的精确匹配**而非模糊匹配 —— 模糊匹配会把 ``/a`` 错配到 ``/ab``，
在统计上比不匹配更糟。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List
from urllib.parse import urlparse

from .crawler_classifier import AI_BOT, SEARCH_BOT


def normalize_path(raw: str) -> str:
    """把 URL 或路径归一化成可比较的路径形式。

    - 绝对 URL → 取 path 部分
    - 去掉查询串 / 锚点
    - 去掉尾部斜杠（``/a/`` 与 ``/a`` 视为同一资源）
    - 空值 → ``/``
    """
    value = (raw or "").strip()
    if not value:
        return "/"
    if value.startswith(("http://", "https://", "//")):
        parsed = urlparse(value if "//" in value[:2] else value)
        value = parsed.path or "/"
    value = value.split("?", 1)[0].split("#", 1)[0]
    if not value.startswith("/"):
        value = "/" + value
    if len(value) > 1:
        value = value.rstrip("/") or "/"
    return value


def build_url_index(db) -> Dict[str, Dict[str, int]]:
    """建立「归一化路径 → 内容标识」索引。

    返回 ``{"/case/vacuum-pump": {"task_id": 3, "publish_job_id": 7, "content_asset_id": 0}}``。
    同名路径多处命中时**合并**（同一篇文章可能既在生产任务里、又在发布任务里）。
    """
    from ..models import ContentAsset, ProductionTask, PublishJob

    index: Dict[str, Dict[str, int]] = {}

    def _add(url: str, **ids: int) -> None:
        path = normalize_path(url)
        if path == "/":
            return
        slot = index.setdefault(path, {"task_id": 0, "publish_job_id": 0, "content_asset_id": 0})
        for key, val in ids.items():
            if val:
                slot[key] = int(val)

    for t in db.query(ProductionTask).filter(
        ProductionTask.is_deleted == 0, ProductionTask.publish_url != "",
    ).all():
        _add(t.publish_url, task_id=t.id)

    for j in db.query(PublishJob).filter(
        PublishJob.is_deleted == 0, PublishJob.result_url != "",
    ).all():
        _add(j.result_url, publish_job_id=j.id, task_id=j.task_id or 0)

    for a in db.query(ContentAsset).filter(
        ContentAsset.is_deleted == 0, ContentAsset.publish_url != "",
    ).all():
        _add(a.publish_url, content_asset_id=a.id)

    return index


def match_content(index: Dict[str, Dict[str, int]], path: str) -> Dict[str, Any]:
    """用一条抓取记录的路径去索引里找对应内容。"""
    key = normalize_path(path)
    hit = index.get(key)
    if not hit:
        return {"publish_job_id": 0, "content_asset_id": 0, "task_id": 0, "matched_url": ""}
    return {**hit, "matched_url": key}


def record_hits(db, records: List[Dict[str, Any]], *, source: str = "manual_import",
                skip_human: bool = True, dedupe: bool = True) -> Dict[str, int]:
    """批量写入抓取记录（带分类 + 归因 + 去重）。

    返回统计：``{"imported": n, "skipped_human": n, "duplicated": n, "attributed": n}``。

    ``dedupe=True`` 时按 ``(ip_hash, path, hit_time)`` 去重，
    避免用户重复粘贴同一份日志导致数据翻倍。
    """
    import hashlib

    from ..models import CrawlerHit
    from .crawler_classifier import HUMAN, identify

    index = build_url_index(db)
    stats = {"imported": 0, "skipped_human": 0, "duplicated": 0, "attributed": 0}

    # 预取已有的去重键（限定在同一时间窗内，避免全表扫描）
    existing_keys = set()
    if dedupe:
        rows = db.query(CrawlerHit.ip_hash, CrawlerHit.path, CrawlerHit.hit_time).all()
        existing_keys = {(r[0], r[1], r[2]) for r in rows}

    pending: List[CrawlerHit] = []
    for rec in records:
        verdict = identify(rec.get("user_agent"))
        if skip_human and verdict["bot_class"] == HUMAN:
            stats["skipped_human"] += 1
            continue

        ip = str(rec.get("ip") or "")
        ip_hash = hashlib.sha256(ip.encode("utf-8", "ignore")).hexdigest()[:16] if ip else ""
        path = str(rec.get("path") or "")
        hit_time = rec.get("time") or datetime.now()
        if not isinstance(hit_time, datetime):
            hit_time = datetime.now()

        key = (ip_hash, path[:512], hit_time)
        if dedupe and key in existing_keys:
            stats["duplicated"] += 1
            continue
        existing_keys.add(key)

        matched = match_content(index, path)
        if matched.get("matched_url"):
            stats["attributed"] += 1

        pending.append(CrawlerHit(
            hit_time=hit_time,
            path=path[:512],
            query=str(rec.get("query") or "")[:512],
            user_agent=str(rec.get("user_agent") or "")[:512],
            bot_class=verdict["bot_class"],
            bot_name=verdict["bot_name"],
            method=str(rec.get("method") or "GET")[:8],
            status_code=int(rec.get("status") or 0),
            referer=str(rec.get("referer") or "")[:512],
            ip_hash=ip_hash,
            publish_job_id=int(matched.get("publish_job_id") or 0),
            content_asset_id=int(matched.get("content_asset_id") or 0),
            matched_url=str(matched.get("matched_url") or "")[:512],
        ))

    if pending:
        db.add_all(pending)
        db.commit()
        stats["imported"] = len(pending)

    stats["source"] = source  # type: ignore[assignment]
    return stats


def crawl_stats(db, days: int = 30) -> Dict[str, Any]:
    """汇总最近 ``days`` 天的抓取数据。

    返回：总量、按分类/爬虫名的分布、Top 路径、日粒度趋势、AI 收录覆盖率。
    """
    from ..models import CrawlerHit, ProductionTask

    days = max(1, min(365, int(days or 30)))
    since = datetime.now() - timedelta(days=days)
    rows = db.query(CrawlerHit).filter(CrawlerHit.hit_time >= since).all()

    by_class: Dict[str, int] = {}
    by_bot: Dict[str, int] = {}
    by_path: Dict[str, int] = {}
    by_day: Dict[str, Dict[str, int]] = {}
    attributed_paths = set()

    for r in rows:
        by_class[r.bot_class] = by_class.get(r.bot_class, 0) + 1
        if r.bot_name:
            by_bot[r.bot_name] = by_bot.get(r.bot_name, 0) + 1
        by_path[r.path] = by_path.get(r.path, 0) + 1
        day = r.hit_time.strftime("%Y-%m-%d") if r.hit_time else ""
        if day:
            slot = by_day.setdefault(day, {"ai_bot": 0, "search_bot": 0, "other_bot": 0, "human": 0, "unknown": 0})
            slot[r.bot_class] = slot.get(r.bot_class, 0) + 1
        if r.bot_class == AI_BOT and r.matched_url:
            attributed_paths.add(r.matched_url)

    # AI 收录覆盖率：已发布且有 URL 的内容中，被 AI 爬虫抓过的比例
    published_urls = {
        normalize_path(t.publish_url)
        for t in db.query(ProductionTask).filter(
            ProductionTask.is_deleted == 0, ProductionTask.publish_url != "",
        ).all()
        if t.publish_url
    }
    published_urls.discard("/")
    covered = len(published_urls & attributed_paths)
    coverage = round(covered / len(published_urls) * 100, 1) if published_urls else 0.0

    top_paths = sorted(by_path.items(), key=lambda kv: kv[1], reverse=True)[:20]
    trend = [
        {"date": day, **counts}
        for day, counts in sorted(by_day.items())
    ]

    return {
        "days": days,
        "total_hits": len(rows),
        "ai_bot_hits": by_class.get(AI_BOT, 0),
        "search_bot_hits": by_class.get(SEARCH_BOT, 0),
        "by_class": by_class,
        "by_bot": sorted(
            ({"bot_name": k, "hits": v} for k, v in by_bot.items()),
            key=lambda x: x["hits"], reverse=True,
        )[:30],
        "top_paths": [{"path": p, "hits": n} for p, n in top_paths],
        "trend": trend,
        "published_count": len(published_urls),
        "ai_covered_count": covered,
        "ai_coverage_rate": coverage,
    }


def uncovered_published(db, days: int = 30) -> List[Dict[str, Any]]:
    """列出**已发布但从未被 AI 爬虫抓过**的内容 —— 内容缺口清单。

    这是归因闭环里最可执行的一环：没被抓，说明要么没被 AI 发现，
    要么被抓了但我们没记到日志，两种都值得排查。
    """
    from ..models import CrawlerHit, ProductionTask

    since = datetime.now() - timedelta(days=days)
    crawled = {
        normalize_path(r.matched_url or r.path)
        for r in db.query(CrawlerHit).filter(
            CrawlerHit.hit_time >= since, CrawlerHit.bot_class == AI_BOT,
        ).all()
    }

    out: List[Dict[str, Any]] = []
    for t in db.query(ProductionTask).filter(
        ProductionTask.is_deleted == 0, ProductionTask.publish_url != "",
    ).order_by(ProductionTask.update_time.desc()).all():
        path = normalize_path(t.publish_url)
        if path in crawled:
            continue
        out.append({
            "task_id": t.id,
            "title": t.final_title or t.title,
            "url": t.publish_url,
            "published_at": t.update_time.strftime("%Y-%m-%d %H:%M:%S") if t.update_time else "",
            "suggestion": "未被 AI 爬虫抓取：检查该 URL 是否已在 sitemap.xml 中、robots.txt 是否放行、页面是否有内链可达",
        })
    return out


def daily_ai_hits(db, days: int = 30) -> List[Dict[str, Any]]:
    """日粒度 AI 爬虫抓取趋势（供看板折线图）。"""
    from ..models import CrawlerHit

    days = max(1, min(365, int(days or 30)))
    since = datetime.now() - timedelta(days=days)
    buckets: Dict[str, Dict[str, int]] = {}
    rows = db.query(CrawlerHit).filter(CrawlerHit.hit_time >= since).all()
    for r in rows:
        if not r.hit_time:
            continue
        day = r.hit_time.strftime("%Y-%m-%d")
        slot = buckets.setdefault(day, {"ai_bot": 0, "search_bot": 0, "other_bot": 0})
        slot[r.bot_class] = slot.get(r.bot_class, 0) + 1
    return [{"date": d, **v} for d, v in sorted(buckets.items())]
