"""
GEO 归因闭环：发布 → 收录 → 引用 → 排名 → 回流

为什么需要单独一层
------------------
B5 建好了「收录观测」（``crawler_hit``），B2/B3 建好了「可见性采集与引用分析」
（``geo_visibility_run`` / ``geo_visibility_source``）。但两条链路各自躺在自己的表里，
谁也回答不了运营真正关心的那个问题：

    我发了 50 篇文章，AI 到底看了几篇、引用了几篇、有几篇进了前 3？

本模块把两条链路**接起来**，形成一条可度量、可定位、可回流的闭环::

    发布  →  收录（AI 爬虫抓取）  →  引用（成为 AI 回答的信源）  →  排名（进入前 3）
                                        ↓
                          回流：缺口清单 + 对标选题 + 可复制模式

四阶段口径（写死在这里，避免各处各算一套）
----------------------------------------
- **发布**：``production_task.publish_url`` 非空且 ``is_deleted = 0``
- **收录**：该 URL 被 ``ai_bot`` 类抓取器抓过至少一次
- **引用**：该 URL 出现在 ``geo_visibility_source.url`` 里
- **排名**：该信源的 ``rank <= 3``

为什么 ``search_bot`` 不算收录
------------------------------
百度/Google 收录是传统 SEO 指标，而 AI 回答的语料来自各自的抓取器
（GPTBot / Bytespider / PerplexityBot …）。把两者合并会虚高收录率，
掩盖「AI 根本没来抓」这个真问题 —— 而后者才是 GEO 要修的洞。
因此本模块**只认 ai_bot**，search_bot 单独作为参考指标给出。

为什么按「路径」而不是「完整 URL」关联
------------------------------------
同一篇文章在 A 平台和 B 平台的 URL 完全不同，但 ``crawler_hit.path`` 与
``geo_visibility_source.url`` 都指向同一批内容时，路径是最稳定的连接键。
归一化规则复用 ``services/attribution.normalize_path``，两边必须用同一套，
否则会出现「爬虫记了、引用没记」的假缺口。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from .attribution import normalize_path
from .crawler_classifier import AI_BOT, SEARCH_BOT

# 漏斗阶段定义（顺序即漏斗顺序，前端直接按这个渲染）
STAGES: List[Tuple[str, str, str]] = [
    ("published", "已发布", "已填写发布 URL 的内容"),
    ("crawled", "AI 已收录", "被 GPTBot / Bytespider / PerplexityBot 等 AI 抓取器抓过"),
    ("cited", "被 AI 引用", "作为信源出现在 AI 回答里"),
    ("top3", "进入前 3", "被引用且排名前 3 —— 最高价值的可见形态"),
]

# 默认观察窗口：收录与引用都有滞后，窗口太短会得出「全都没收录」的错误结论
DEFAULT_DAYS = 90


# ============================================================
#  数据装载
# ============================================================
def _since(days: int) -> datetime:
    return datetime.now() - timedelta(days=max(1, min(3650, int(days or DEFAULT_DAYS))))


def _slug(path: str) -> str:
    """取路径末段（文章的 URL 别名）。"""
    return (path or "").rstrip("/").rsplit("/", 1)[-1]


def _all_published_paths(db: Session) -> set:
    """**所有行业**的已发布路径集合。

    用来把「抓取记录对不上任何内容」（可能是路径配错）与
    「对上了，只是属于别的行业空间」区分开 —— ``crawler_hit`` 是全站级的
    （一个站点服务多个行业空间），不做这层区分就会把别的行业的正常流量
    误报成「路径不一致」。
    """
    from ..models import ProductionTask

    paths = set()
    rows = db.query(ProductionTask.publish_url).filter(
        ProductionTask.is_deleted == 0, ProductionTask.publish_url != "",
    ).all()
    for (url,) in rows:
        p = normalize_path(url)
        if p != "/":
            paths.add(p)
    return paths


def published_contents(db: Session, industry_id: int) -> List[Dict[str, Any]]:
    """已发布内容清单（以 ``production_task.publish_url`` 为准）。

    只取有 URL 的：没有 URL 就无从观测收录与引用，列进来只会让分母虚高、
    把「还没发布」误算成「发布了但没被收录」。
    """
    from ..models import ProductionTask

    rows = db.query(ProductionTask).filter(
        ProductionTask.industry_id == industry_id,
        ProductionTask.is_deleted == 0,
        ProductionTask.publish_url != "",
    ).order_by(ProductionTask.update_time.desc()).all()

    out: List[Dict[str, Any]] = []
    for t in rows:
        path = normalize_path(t.publish_url)
        if path == "/":
            continue
        out.append({
            "task_id": t.id,
            "title": (t.final_title or t.title or "").strip() or f"任务 #{t.id}",
            "url": t.publish_url,
            "path": path,
            "published_at": t.update_time.strftime("%Y-%m-%d %H:%M:%S") if t.update_time else "",
            "platform": (t.platform_snapshot or "")[:32],
        })
    return out


def _crawl_map(db: Session, since: datetime) -> Dict[str, Dict[str, Any]]:
    """按路径汇总抓取情况，AI 抓取与搜索引擎抓取分开统计。

    分开是为了让「AI 收录率」这个指标真的反映 AI 行为；
    合并统计出来的数字看着漂亮，但对 GEO 没有任何指导意义。
    """
    from ..models import CrawlerHit

    out: Dict[str, Dict[str, Any]] = {}
    rows = db.query(CrawlerHit).filter(CrawlerHit.hit_time >= since).all()
    for r in rows:
        path = normalize_path(r.matched_url or r.path)
        if path == "/":
            continue
        slot = out.setdefault(path, {
            "ai_hits": 0, "search_hits": 0, "other_hits": 0,
            "ai_bots": set(), "first_hit": None, "last_hit": None,
        })
        if r.bot_class == AI_BOT:
            slot["ai_hits"] += 1
            if r.bot_name:
                slot["ai_bots"].add(r.bot_name)
        elif r.bot_class == SEARCH_BOT:
            slot["search_hits"] += 1
        else:
            slot["other_hits"] += 1

        t = r.hit_time
        if t:
            if slot["first_hit"] is None or t < slot["first_hit"]:
                slot["first_hit"] = t
            if slot["last_hit"] is None or t > slot["last_hit"]:
                slot["last_hit"] = t
    return out


def _citation_map(db: Session, industry_id: int, since: datetime) -> Dict[str, Dict[str, Any]]:
    """按路径汇总「被 AI 引用」的情况（来自 ``geo_visibility_source``）。

    需要经 ``geo_visibility_run`` 过滤行业 —— ``geo_visibility_source`` 本身
    不带 industry_id，直接全表扫会把别的行业的数据混进来。
    """
    from ..models import GeoVisibilityRun, GeoVisibilitySource

    run_ids = [
        r.id for r in db.query(GeoVisibilityRun.id).filter(
            GeoVisibilityRun.industry_id == industry_id,
            GeoVisibilityRun.create_time >= since,
        ).all()
    ]
    if not run_ids:
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    rows = db.query(GeoVisibilitySource).filter(
        GeoVisibilitySource.run_id.in_(run_ids)
    ).all()
    for s in rows:
        url = (s.url or "").strip()
        if not url:
            continue
        path = normalize_path(url)
        if path == "/":
            continue
        slot = out.setdefault(path, {
            "cited_times": 0, "best_rank": 0, "keywords": set(),
            "run_ids": set(), "domains": set(),
        })
        slot["cited_times"] += 1
        rank = int(s.rank or 0)
        if rank > 0:
            slot["best_rank"] = rank if slot["best_rank"] in (0, None) else min(slot["best_rank"], rank)
        slot["run_ids"].add(s.run_id)
        if s.domain:
            slot["domains"].add(s.domain)
    return out


def _run_keywords(db: Session, run_ids: Sequence[int]) -> Dict[int, str]:
    """一次查出 Run 的问题关键词，避免在循环里逐条查库（N+1）。"""
    from ..models import GeoVisibilityRun

    if not run_ids:
        return {}
    rows = db.query(GeoVisibilityRun.id, GeoVisibilityRun.keyword).filter(
        GeoVisibilityRun.id.in_(list(run_ids))
    ).all()
    return {r[0]: r[1] or "" for r in rows}


# ============================================================
#  四阶段漏斗
# ============================================================
def publish_funnel(db: Session, industry_id: int, days: int = DEFAULT_DAYS) -> Dict[str, Any]:
    """发布 → 收录 → 引用 → 排名 的四阶段漏斗，含阶段间转化率。

    转化率同时给「相对上一阶段」和「相对发布总数」两个口径：
    前者用于定位**具体哪一步漏得最狠**，后者用于对外汇报整体效果。
    """
    days = max(1, min(3650, int(days or DEFAULT_DAYS)))
    since = _since(days)

    published = published_contents(db, industry_id)
    pub_paths = {p["path"] for p in published}
    crawl = _crawl_map(db, since)
    cite = _citation_map(db, industry_id, since)

    crawled = {p for p in pub_paths if crawl.get(p, {}).get("ai_hits", 0) > 0}
    cited = {p for p in pub_paths if cite.get(p, {}).get("cited_times", 0) > 0}
    top3 = {p for p in cited if 0 < int(cite.get(p, {}).get("best_rank") or 0) <= 3}
    # 参考口径：被搜索引擎抓过（不计入 AI 收录）
    search_only = {p for p in pub_paths if crawl.get(p, {}).get("search_hits", 0) > 0}

    counts = {
        "published": len(pub_paths),
        "crawled": len(crawled),
        "cited": len(cited),
        "top3": len(top3),
    }

    ai_crawl_total = sum(v.get("ai_hits", 0) for v in crawl.values())
    matched_ai_hits = sum(crawl.get(p, {}).get("ai_hits", 0) for p in pub_paths)

    # 三分类：命中本行业 / 命中别的行业空间 / 谁也对不上。
    # 最后这一类才是「路径可能配错了」的信号；中间那一类是完全正常的流量。
    all_paths = _all_published_paths(db)
    unmatched_ai_hits = sum(
        v.get("ai_hits", 0) for p, v in crawl.items() if p not in all_paths
    )
    other_industry_ai_hits = max(0, ai_crawl_total - matched_ai_hits - unmatched_ai_hits)

    # 「路径配错」的**精确**信号：抓取路径的末段与某篇已发布内容一致，但整条路径对不上。
    # 例：发布了 /case/vacuum-pump，日志里却是 /articles/vacuum-pump。
    #
    # 为什么不用「存在对不上的抓取流量」来判断：站点上本来就有产品页、分类页等
    # 我们从未打算归因的 URL，那样会天天误报，运营很快就不再相信这个提示。
    pub_slugs = {_slug(p): p for p in pub_paths if _slug(p)}
    near_miss: List[Dict[str, Any]] = []
    for path, info in crawl.items():
        if path in all_paths or not info.get("ai_hits"):
            continue
        published = pub_slugs.get(_slug(path))
        if published and published != path:
            near_miss.append({
                "hit_path": path,
                "published_path": published,
                "ai_hits": int(info["ai_hits"]),
            })
    near_miss.sort(key=lambda x: x["ai_hits"], reverse=True)

    def _rate(num: int, den: int) -> float:
        return round(num / den, 4) if den else 0.0

    stages: List[Dict[str, Any]] = []
    prev: Optional[int] = None
    for key, label, desc in STAGES:
        value = counts[key]
        stages.append({
            "key": key,
            "label": label,
            "desc": desc,
            "value": value,
            "rate_of_published": _rate(value, counts["published"]),
            "rate_of_prev": 1.0 if prev is None else _rate(value, prev),
        })
        prev = value

    return {
        "days": days,
        "stages": stages,
        "counts": counts,
        "search_only_count": len(search_only - crawled),
        "ai_crawl_total": ai_crawl_total,
        # 三分类暴露出来是为了让「AI 抓取总量」这个数字能被解释：
        # 其中多少真正落在本行业的内容上，多少属于别的行业空间，多少谁也对不上。
        "matched_ai_hits": matched_ai_hits,
        "other_industry_ai_hits": other_industry_ai_hits,
        "unmatched_ai_hits": unmatched_ai_hits,
        # 「路径配错」的精确证据：slug 相同但整条路径不同。
        # 只有它非空时才能断定是路径配错 —— 见上方注释。
        "near_miss": near_miss,
    }


# ============================================================
#  逐篇归因表
# ============================================================
def _status_of(ai_hits: int, cited_times: int, best_rank: int) -> Tuple[str, str]:
    """给每篇内容一个可执行的状态标签（而不是让运营自己看数字猜）。"""
    if ai_hits == 0:
        return "not_crawled", "未被 AI 抓取"
    if cited_times == 0:
        return "crawled_only", "已抓取未被引用"
    if 0 < best_rank <= 3:
        return "top3", "已引用且进前 3"
    return "cited", "已被引用"


_ACTION_HINTS = {
    "not_crawled": "先核对发布 URL 与站点实际路径是否一致（多/少一段路径、域名不同都会让归因静默失败）；确认无误后，再检查该 URL 是否已在 sitemap.xml / llms.txt 中、robots.txt 是否放行 AI 抓取、页面是否有内链可达",
    "crawled_only": "AI 抓到了但没引用：补充可被引用的硬信息（实测数据、规格表、对比结论），并加上明确标题层级",
    "cited": "已被引用但排名靠后：扩写该主题、增加数据密度与结构化小标题，争取进入前 3",
    "top3": "已进入前 3：这是被验证有效的内容模式，建议复制选题角度扩写同主题系列",
}


def attribution_table(db: Session, industry_id: int, days: int = DEFAULT_DAYS,
                      limit: int = 200) -> List[Dict[str, Any]]:
    """逐篇内容的完整归因行：抓了几次、谁抓的、被引用几次、最好排名、下一步做什么。"""
    days = max(1, min(3650, int(days or DEFAULT_DAYS)))
    since = _since(days)

    crawl = _crawl_map(db, since)
    cite = _citation_map(db, industry_id, since)

    out: List[Dict[str, Any]] = []
    for item in published_contents(db, industry_id):
        path = item["path"]
        c = crawl.get(path, {})
        ci = cite.get(path, {})
        ai_hits = int(c.get("ai_hits", 0))
        cited_times = int(ci.get("cited_times", 0))
        best_rank = int(ci.get("best_rank", 0) or 0)
        status, status_label = _status_of(ai_hits, cited_times, best_rank)

        first_hit = c.get("first_hit")
        out.append({
            **item,
            "ai_hits": ai_hits,
            "search_hits": int(c.get("search_hits", 0)),
            "ai_bots": sorted(c.get("ai_bots") or []),
            "first_crawl": first_hit.strftime("%Y-%m-%d %H:%M") if first_hit else "",
            "cited_times": cited_times,
            "best_rank": best_rank,
            "status": status,
            "status_label": status_label,
            "action": _ACTION_HINTS[status],
        })

    # 排序：先按「越靠后越需要处理」排，再按引用次数 ——
    # 运营打开这张表是为了找问题，不是为了看已经成功的那些。
    order = {"not_crawled": 0, "crawled_only": 1, "cited": 2, "top3": 3}
    out.sort(key=lambda x: (order.get(x["status"], 9), -x["cited_times"], -x["ai_hits"]))
    return out[: max(1, int(limit or 200))]


# ============================================================
#  单篇内容旅程（钻取）
# ============================================================
def content_journey(db: Session, raw_url: str, industry_id: int = 0,
                    days: int = 365) -> Dict[str, Any]:
    """单篇内容的完整旅程：什么时候被谁抓过、在哪些问题下被引用、排名多少。

    这是把「聚合数字」还原成「可排查的事实」的那一步：
    看板上说「这篇没被收录」，运营的第一反应必然是「真的吗」，
    所以必须能点进去看到原始的抓取记录。
    """
    from ..models import CrawlerHit, GeoVisibilityRun, GeoVisibilitySource

    path = normalize_path(raw_url)
    since = _since(days)

    hits = db.query(CrawlerHit).filter(
        CrawlerHit.hit_time >= since,
    ).order_by(CrawlerHit.hit_time.desc()).all()
    matched = [h for h in hits if normalize_path(h.matched_url or h.path) == path]

    crawl_records = [{
        "id": h.id,
        "time": h.hit_time.strftime("%Y-%m-%d %H:%M:%S") if h.hit_time else "",
        "bot_class": h.bot_class,
        "bot_name": h.bot_name or "(未识别)",
        "method": h.method,
        "status_code": h.status_code,
        "referer": (h.referer or "")[:200],
    } for h in matched[:200]]

    # 引用记录：先按路径筛信源，再回查所属 Run 的关键词
    src_q = db.query(GeoVisibilitySource).filter(
        GeoVisibilitySource.url != "",
    )
    srcs = [s for s in src_q.all() if normalize_path(s.url) == path]

    keywords = _run_keywords(db, [s.run_id for s in srcs])
    runs = {
        r.id: r for r in db.query(GeoVisibilityRun).filter(
            GeoVisibilityRun.id.in_([s.run_id for s in srcs] or [0])
        ).all()
    }

    citations = []
    for s in srcs:
        run = runs.get(s.run_id)
        if industry_id and run and run.industry_id != industry_id:
            continue
        citations.append({
            "source_id": s.id,
            "run_id": s.run_id,
            "keyword": keywords.get(s.run_id, ""),
            "rank": s.rank,
            "title": s.title,
            "domain": s.domain,
            "authority_level": s.authority_level,
            "is_owned": s.is_owned,
            "create_time": run.create_time.strftime("%Y-%m-%d %H:%M:%S") if run and run.create_time else "",
        })
    citations.sort(key=lambda x: (x["rank"] or 9999, x["create_time"]))

    ai_hits = sum(1 for h in matched if h.bot_class == AI_BOT)
    best_rank = min((c["rank"] for c in citations if c["rank"]), default=0)
    status, status_label = _status_of(ai_hits, len(citations), best_rank)

    return {
        "path": path,
        "ai_hits": ai_hits,
        "search_hits": sum(1 for h in matched if h.bot_class == SEARCH_BOT),
        "total_hits": len(matched),
        "first_crawl": crawl_records[-1]["time"] if crawl_records else "",
        "last_crawl": crawl_records[0]["time"] if crawl_records else "",
        "crawl_records": crawl_records,
        "cited_times": len(citations),
        "best_rank": best_rank,
        "citations": citations[:200],
        "status": status,
        "status_label": status_label,
        "action": _ACTION_HINTS[status],
    }


# ============================================================
#  回流选题
# ============================================================
def recycle_suggestions(db: Session, industry_id: int, days: int = DEFAULT_DAYS,
                        limit: int = 20) -> List[Dict[str, Any]]:
    """闭环的最后一环：把观测结果转成**下一步该做什么**。

    三类回流，优先级从高到低：

    1. ``replicate`` —— 已进前 3 的自有内容：验证有效的模式，复制它
    2. ``push_index`` —— 发布了但 AI 从没来抓：先解决「被发现」的问题
    3. ``improve`` —— 抓了但没被引用：内容本身不够「可被引用」

    刻意不把「对标第三方信源」放进来 —— 那件事在
    ``services/visibility/analytics.topic_suggestions`` 里已经做了，
    两处都产出「对标建议」只会让运营收到两份互相矛盾的清单。
    """
    days = max(1, min(3650, int(days or DEFAULT_DAYS)))
    rows = attribution_table(db, industry_id, days=days, limit=1000)

    out: List[Dict[str, Any]] = []
    for row in rows:
        if row["status"] == "top3":
            out.append({
                "kind": "replicate",
                "priority": "高",
                "title": f"复制已验证模式：《{row['title']}》进入前 3",
                "basis": f"被引用 {row['cited_times']} 次，最好排名第 {row['best_rank']}",
                "reason": "该内容已被 AI 采信并排到前 3，说明选题角度与信息密度被验证有效",
                "action": f"围绕同一主题扩写系列文章，沿用《{row['title']}》的结构与数据密度",
                "url": row["url"],
            })
        elif row["status"] == "not_crawled":
            out.append({
                "kind": "push_index",
                "priority": "高",
                "title": f"推动收录：《{row['title']}》尚未被 AI 抓取",
                "basis": f"已发布 {row['published_at'] or '（时间未知）'}，AI 抓取 0 次",
                "reason": "AI 从未来抓取，说明内容还没进入 AI 的视野，谈引用为时过早",
                "action": row["action"],
                "url": row["url"],
            })
        elif row["status"] == "crawled_only":
            out.append({
                "kind": "improve",
                "priority": "中",
                "title": f"提升可引用性：《{row['title']}》被抓取但未被引用",
                "basis": f"AI 抓取 {row['ai_hits']} 次，被引用 0 次",
                "reason": "AI 读过了但没把它当作依据，通常是缺硬数据或结构不清晰",
                "action": row["action"],
                "url": row["url"],
            })
        if len(out) >= max(1, int(limit or 20)):
            break

    # 前端标了「按越先做越靠前排序」，就必须真的按优先级排 ——
    # 否则会出现「中」排在「高」前面，运营看到第一反应是这张表坏了。
    # 优先级相同时保持漏斗顺序（越靠前的阶段越该先处理）。
    rank = {"高": 0, "中": 1, "低": 2}
    out.sort(key=lambda x: rank.get(x["priority"], 9))
    return out


# ============================================================
#  闭环健康度诊断
# ============================================================
def loop_health(db: Session, industry_id: int, days: int = DEFAULT_DAYS) -> Dict[str, Any]:
    """诊断闭环卡在哪一步 —— 给出结论，而不是丢一堆数字让人自己判断。

    判定规则刻意简单可解释：找**相邻两阶段之间转化率最低**的那一步。
    一个说不清依据的「健康分」对运营没有价值。
    """
    funnel = publish_funnel(db, industry_id, days)
    counts = funnel["counts"]

    if counts["published"] == 0:
        return {
            "stage": "empty",
            "label": "尚未发布内容",
            "detail": "闭环还没有起点：先在「软文生产」里产出内容并填写发布 URL",
            "bottleneck": "",
            "funnel": funnel,
        }

    # 「AI 抓到了、但记的路径和我们发布的路径不是同一条」—— 这几乎总是
    # **路径配置不一致**（发布 URL 多/少一段、域名不同、大小写差异），
    # 而不是「AI 没来抓」。两者给的处置动作完全相反：前者要改 URL 映射，
    # 后者要去做 sitemap / llms.txt。判断错了运营就会白忙一场。
    #
    # 判定依据是 ``near_miss`` 而非「存在对不上的抓取流量」：
    # 站点上本来就有产品页、分类页这些我们从未打算归因的 URL，
    # 按后者判会天天误报，运营很快就不再相信这个提示。
    near_miss = funnel.get("near_miss") or []
    if counts["crawled"] == 0 and near_miss:
        sample = near_miss[0]
        return {
            "stage": "path_mismatch",
            "label": "AI 抓取器有到访，但路径与发布 URL 对不上",
            "detail": (
                f"有 {len(near_miss)} 条抓取记录的末段路径与已发布内容一致，"
                f"但整条路径不同。例如站点日志里是 {sample['hit_path']}，"
                f"而我们登记的是 {sample['published_path']}。"
                "这通常是**发布 URL 与站点实际路径不一致**（多/少一段路径、"
                "域名不同、大小写差异），而不是 AI 没有来抓。"
            ),
            "bottleneck": "path_mismatch",
            "next_step": "去「内容归因」逐篇核对发布 URL 与站点访问日志里的路径是否完全一致",
            "transition_rate": 0.0,
            "funnel": funnel,
        }

    transitions = [
        ("crawled", "收录", counts["crawled"], counts["published"], "push_index"),
        ("cited", "引用", counts["cited"], counts["crawled"], "improve"),
        ("top3", "前 3", counts["top3"], counts["cited"], "expand"),
    ]
    worst = min(
        transitions,
        key=lambda x: (x[2] / x[3]) if x[3] else 1.0,
    )
    key, label, num, den, hint_kind = worst
    rate = round(num / den, 4) if den else 0.0

    detail_map = {
        # 措辞必须与实际情况相符：这里只说明「收录这一步转化最低」，
        # 不写死「AI 还没来抓」—— 部分抓取时那样说会自相矛盾
        # （漏斗上明明有已收录的内容），运营一眼就会不信这个结论。
        "push_index": "仍有内容未被 AI 抓取：优先检查这些 URL 是否已在 sitemap.xml / llms.txt 中、robots.txt 是否放行 AI 爬虫、页面是否有内链可达",
        "improve": "AI 抓到了内容但没引用：补充实测数据、规格表与明确结论，让内容「值得被引用」",
        "expand": "已被引用但排名靠后：扩写该主题、提高数据密度，争取进入前 3",
    }
    hint_map = {
        "push_index": "去「内容归因」筛选「未被 AI 抓取」，逐篇推动收录",
        "improve": "去「回流选题」处理「被抓取但未被引用」的清单",
        "expand": "去「回流选题」复制已进前 3 的内容模式",
    }

    return {
        "stage": key,
        "label": f"{label}环节转化最弱（{rate * 100:.1f}%）",
        "detail": detail_map[hint_kind],
        "bottleneck": hint_kind,
        "next_step": hint_map[hint_kind],
        "transition_rate": rate,
        "funnel": funnel,
    }
