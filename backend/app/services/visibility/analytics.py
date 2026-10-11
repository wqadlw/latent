"""
AI 可见性分析：6 个 KPI + 日粒度趋势 + 信源偏好榜 + 选题回流

为什么要有这一层
----------------
采集（B2）解决的是「拿到数据」，分析解决的是「数据说明什么」。
没有分析层，``geo_visibility_run`` 只是一堆没人看的回答文本。

6 个 KPI 的定义直接对齐 GEOFlow 的 ``AiVisibilityAnalyticsService``::

    brand_visibility = 回答正文提到品牌  OR  引用信源前 3 名里有自有站点
    top1_rate        = 品牌信源排第 1 的比例
    top3_rate        = 品牌信源排前 3 的比例
    positive_rate    = 正面情感比例
    negative_rate    = 负面情感比例
    sentiment_score  = 情感分（-1 ~ 1）

口径约定（写死在这里，避免前后端各算一套）
------------------------------------------
- **分母**统一是「有可用分析的探测数」，不是「全部探测数」。
  失败的探测（超时、熔断、限流）不该被算成「品牌不可见」——
  那会把上游故障误读成品牌表现变差。
- 比率统一返回 **0~1 的浮点数**，前端自行乘 100 展示。
  服务层不带单位，才能在质检闸门等场景复用。

采样策略
--------
``DAILY_SAMPLE_TARGET = 5``：每个「关键词 × 日」最多取 5 条探测参与 KPI。
不采样的话，某天多跑几次就会把趋势线整个拉歪，而且数据量随时间无上限增长。
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from sqlalchemy.orm import Session

from ..claim_extractor import extract_terms
from .normalizer import source_action

# 每个「关键词 × 日」最多取多少条探测参与 KPI（对齐 GEOFlow）
DAILY_SAMPLE_TARGET = 5

# 默认分析窗口
DEFAULT_DAYS = 30

# 信源偏好榜默认条数（验收要求：能列出 top 20 域名及引用次数）
DEFAULT_SOURCE_LIMIT = 20

KPI_LABELS = {
    "brand_visibility": "品牌可见率",
    "top1_rate": "品牌信源 Top1 率",
    "top3_rate": "品牌信源 Top3 率",
    "positive_rate": "正面情感率",
    "negative_rate": "负面情感率",
    "sentiment_score": "情感分",
}


# ============================================================
#  数据装载
# ============================================================
def _window(days: int) -> datetime:
    return datetime.now() - timedelta(days=max(1, min(3650, int(days or DEFAULT_DAYS))))


def load_runs(db: Session, industry_id: int, *, days: int = DEFAULT_DAYS,
              keyword: str = "", monitor_id: int = 0) -> List[Any]:
    """取出窗口内的探测记录（只取主 Run，不含竞品检测的子 Run）。"""
    from ...models import GeoVisibilityRun

    q = db.query(GeoVisibilityRun).filter(
        GeoVisibilityRun.industry_id == industry_id,
        GeoVisibilityRun.create_time >= _window(days),
        GeoVisibilityRun.parent_run_id == 0,
    )
    if (keyword or "").strip():
        q = q.filter(GeoVisibilityRun.keyword.contains(keyword.strip()))
    if monitor_id:
        q = q.filter(GeoVisibilityRun.monitor_id == monitor_id)
    return q.order_by(GeoVisibilityRun.id.asc()).all()


def sample_runs(runs: Sequence[Any], target: int = DAILY_SAMPLE_TARGET) -> List[Any]:
    """按「关键词 × 日」采样，每天每关键词最多留 ``target`` 条。

    取**最早**的若干条而不是随机取：同一关键词在同一天的多次探测，
    回答往往高度相似（模型对同一问题很稳定），留最早的一批既确定又可复现。
    """
    target = max(1, int(target or DAILY_SAMPLE_TARGET))
    buckets: Dict[Tuple[str, str], int] = {}
    out: List[Any] = []
    for run in runs:
        day = run.create_time.strftime("%Y-%m-%d") if run.create_time else ""
        key = (day, run.keyword or "")
        if buckets.get(key, 0) >= target:
            continue
        buckets[key] = buckets.get(key, 0) + 1
        out.append(run)
    return out


def _analysis_of(run) -> Dict[str, Any]:
    """读出 Run 的结构化分析（失败/损坏时返回空字典，绝不抛异常）。"""
    import json

    raw = getattr(run, "analysis_json", "") or ""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def usable_runs(runs: Sequence[Any]) -> List[Tuple[Any, Dict[str, Any]]]:
    """只保留「探测成功且有分析结果」的 Run —— 这是所有 KPI 的分母。"""
    out: List[Tuple[Any, Dict[str, Any]]] = []
    for run in runs:
        if getattr(run, "status", "") != "completed":
            continue
        analysis = _analysis_of(run)
        if not analysis:
            continue
        out.append((run, analysis))
    return out


# ============================================================
#  6 个 KPI
# ============================================================
def compute_kpis(runs: Sequence[Any]) -> Dict[str, Any]:
    """算出 6 个 KPI。``runs`` 为原始探测列表（内部会自行过滤）。"""
    pairs = usable_runs(runs)
    total = len(pairs)
    if not total:
        return {
            "brand_visibility": 0.0,
            "top1_rate": 0.0,
            "top3_rate": 0.0,
            "positive_rate": 0.0,
            "negative_rate": 0.0,
            "sentiment_score": 0.0,
            "sample_size": 0,
            "source_total": 0,
        }

    visible = top1 = top3 = positive = negative = 0
    sentiment_sum = 0.0
    source_total = 0
    for _run, a in pairs:
        if a.get("brand_visible"):
            visible += 1
        if a.get("top1"):
            top1 += 1
        if a.get("top3"):
            top3 += 1
        sentiment = str(a.get("sentiment") or "neutral")
        if sentiment == "positive":
            positive += 1
        elif sentiment == "negative":
            negative += 1
        try:
            sentiment_sum += float(a.get("sentiment_score") or 0.0)
        except (TypeError, ValueError):
            pass
        try:
            source_total += int(a.get("source_count") or 0)
        except (TypeError, ValueError):
            pass

    return {
        "brand_visibility": round(visible / total, 4),
        "top1_rate": round(top1 / total, 4),
        "top3_rate": round(top3 / total, 4),
        "positive_rate": round(positive / total, 4),
        "negative_rate": round(negative / total, 4),
        "sentiment_score": round(sentiment_sum / total, 4),
        "sample_size": total,
        "source_total": source_total,
    }


def kpi_cards(kpis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把 KPI 直接整理成看板卡片（前端不必再做单位换算）。"""
    cards = []
    for key, label in KPI_LABELS.items():
        value = float(kpis.get(key) or 0.0)
        if key == "sentiment_score":
            cards.append({
                "key": key, "label": label,
                "value": value, "display": f"{value:+.2f}",
                "unit": "分（-1 ~ 1）",
                "hint": "均值 > 0 说明 AI 对品牌的整体语气偏正面",
            })
        else:
            cards.append({
                "key": key, "label": label,
                "value": value, "display": f"{value * 100:.1f}%",
                "unit": "%",
                "hint": _KPI_HINTS[key],
            })
    return cards


_KPI_HINTS = {
    "brand_visibility": "回答提到品牌，或引用的前 3 个信源里有自有站点，都算可见",
    "top1_rate": "品牌内容成为 AI 的**首个**引用来源，是最高价值的可见形态",
    "top3_rate": "品牌内容进入 AI 引用前 3 名",
    "positive_rate": "品牌被提及且语气正面",
    "negative_rate": "品牌被提及但语气负面，需要优先处理",
}


# ============================================================
#  日粒度趋势
# ============================================================
def daily_trend(db: Session, industry_id: int, *, days: int = DEFAULT_DAYS,
                keyword: str = "", monitor_id: int = 0,
                sample_target: int = DAILY_SAMPLE_TARGET) -> List[Dict[str, Any]]:
    """日粒度趋势：每天一组 6 KPI，缺数据的日子补 0 而不是跳过。

    补 0 很关键 —— 直接跳过空白日会让折线图把「那天没探测」和
    「那天表现很好」画成同一条连贯曲线，读图的人会得出错误结论。
    """
    runs = sample_runs(
        load_runs(db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id),
        sample_target,
    )
    grouped: Dict[str, List[Any]] = {}
    for run in runs:
        day = run.create_time.strftime("%Y-%m-%d") if run.create_time else ""
        grouped.setdefault(day, []).append(run)

    days = max(1, min(3650, int(days or DEFAULT_DAYS)))
    today = datetime.now().date()
    out: List[Dict[str, Any]] = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        day_runs = grouped.get(day, [])
        kpis = compute_kpis(day_runs)
        out.append({
            "date": day,
            "runs": len(day_runs),
            **kpis,
        })
    return out


# ============================================================
#  信源偏好榜（本次借鉴里最有商业价值的面板）
# ============================================================
def source_preferences(db: Session, industry_id: int, *, days: int = DEFAULT_DAYS,
                       keyword: str = "", monitor_id: int = 0,
                       limit: int = DEFAULT_SOURCE_LIMIT) -> List[Dict[str, Any]]:
    """哪些域名被 AI 偏爱引用 —— 直接回答「内容该铺到哪里」。

    ``cited_runs`` 统计的是**引用过该域名的探测条数**，而不是信源行数：
    一篇啰嗦的回答把一个域名写了 5 次，不代表它比另一个域名重要 5 倍。
    """
    from ...models import GeoVisibilitySource

    runs = load_runs(db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id)
    run_ids = [r.id for r in runs]
    if not run_ids:
        return []

    rows = db.query(GeoVisibilitySource).filter(
        GeoVisibilitySource.run_id.in_(run_ids)
    ).all()

    agg: Dict[str, Dict[str, Any]] = {}
    seen_run_domain: set = set()
    for row in rows:
        host = (row.domain or "").strip()
        if not host:
            continue
        slot = agg.setdefault(host, {
            "domain": host,
            "cited_runs": 0,
            "citation_rows": 0,
            "best_rank": 0,
            "rank_sum": 0,
            "authority_level": row.authority_level or "low",
            "is_owned": int(row.is_owned or 0),
            "titles": [],
        })
        slot["citation_rows"] += 1
        dedupe_key = (row.run_id, host)
        if dedupe_key not in seen_run_domain:
            seen_run_domain.add(dedupe_key)
            slot["cited_runs"] += 1
        rank = int(row.rank or 0)
        if rank > 0:
            slot["rank_sum"] += rank
            slot["best_rank"] = rank if slot["best_rank"] in (0, None) else min(slot["best_rank"], rank)
        # 标题去重：同一篇文章被多次引用时，标题会重复出现，
        # 榜单上连排三个一样的标题只会挤占空间、不增加信息。
        title = (row.title or "").strip()
        if title and title not in slot["titles"] and len(slot["titles"]) < 3:
            slot["titles"].append(title)

    out = list(agg.values())
    for slot in out:
        slot["avg_rank"] = round(slot["rank_sum"] / slot["cited_runs"], 2) if slot["cited_runs"] else 0
        slot.pop("rank_sum", None)
        slot["share"] = 0.0
        slot["action"] = source_action(slot)

    # 排序：先看被引用的探测条数；条数相同时看**最好名次**（越靠前越重要），
    # 再看平均名次。用 best_rank 而不是 avg_rank 做首要并列依据 ——
    # 「被引用了 1 次且排第 1」的站点，比「被引用 1 次但只排到第 4」的更值得投放。
    out.sort(key=lambda x: (-x["cited_runs"], x["best_rank"] or 9999, x["avg_rank"]))
    out = out[: max(1, int(limit or DEFAULT_SOURCE_LIMIT))]
    top = out[0]["cited_runs"] if out else 0
    for slot in out:
        slot["share"] = round(slot["cited_runs"] / top, 4) if top else 0.0
    return out


# ============================================================
#  词云
# ============================================================
def term_cloud(db: Session, industry_id: int, *, days: int = DEFAULT_DAYS,
               keyword: str = "", monitor_id: int = 0,
               limit: int = 60) -> List[Dict[str, Any]]:
    """从回答正文与信源标题里抽词云，反映 AI 讨论这个话题时的关注点。"""
    from ...models import GeoVisibilitySource

    runs = load_runs(db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id)
    if not runs:
        return []
    run_ids = [r.id for r in runs]

    counter: Counter = Counter()
    for run in runs:
        for term in extract_terms(run.answer_text or "", max_terms=80):
            counter[term] += 1

    titles = db.query(GeoVisibilitySource.title).filter(
        GeoVisibilitySource.run_id.in_(run_ids)
    ).all()
    for (title,) in titles:
        for term in extract_terms(title or "", max_terms=20):
            counter[term] += 1

    return [{"term": t, "count": c} for t, c in counter.most_common(max(1, int(limit or 60)))]


# ============================================================
#  选题回流（我们比 GEOFlow 多做的一步）
# ============================================================
def topic_suggestions(db: Session, industry_id: int, *, days: int = DEFAULT_DAYS,
                      keyword: str = "", limit: int = 10) -> List[Dict[str, Any]]:
    """把信源偏好榜接回选题：AI 爱引谁，就去对标谁的内容。

    这是把「看板」变成「行动」的关键一步 ——
    只告诉你「zhihu.com 被引用了 12 次」没有意义，
    告诉你「去写一篇对标 zhihu 上那篇《真空泵选型避坑》的稿子」才有意义。
    """
    board = source_preferences(db, industry_id, days=days, keyword=keyword, limit=40)
    out: List[Dict[str, Any]] = []
    for slot in board:
        if slot["is_owned"]:
            continue  # 自有站点不需要「对标」，需要的是保持更新
        if slot["cited_runs"] < 1:
            continue
        titles = slot.get("titles") or []
        basis = titles[0] if titles else slot["domain"]
        level = slot.get("authority_level") or "low"
        if level == "high":
            priority, reason = "高", "高权威信源，被 AI 采信度高，对标收益最大"
        elif level == "medium":
            priority, reason = "中", "行业媒体，性价比高，适合批量铺设"
        else:
            priority, reason = "低", "长尾信源，作为补充覆盖即可"
        out.append({
            "source_domain": slot["domain"],
            "source_title": basis,
            "cited_runs": slot["cited_runs"],
            "best_rank": slot["best_rank"],
            "authority_level": level,
            "priority": priority,
            "reason": reason,
            "suggested_title": f"对标《{basis}》：{keyword or '核心问题'}的选型要点与实测数据",
            "action": slot["action"],
        })
        if len(out) >= max(1, int(limit or 10)):
            break
    return out


# ============================================================
#  汇总
# ============================================================
def overview(db: Session, industry_id: int, *, days: int = DEFAULT_DAYS,
             keyword: str = "", monitor_id: int = 0) -> Dict[str, Any]:
    """一次性返回整个看板需要的数据（减少前端串行请求）。"""
    runs = load_runs(db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id)
    sampled = sample_runs(runs)
    kpis = compute_kpis(sampled)
    return {
        "window_days": max(1, min(3650, int(days or DEFAULT_DAYS))),
        "keyword": keyword or "",
        "run_total": len(runs),
        "sampled": len(sampled),
        "sample_target": DAILY_SAMPLE_TARGET,
        "kpis": kpis,
        "kpi_cards": kpi_cards(kpis),
        "trend": daily_trend(db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id),
        "source_preferences": source_preferences(
            db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id
        ),
        "term_cloud": term_cloud(db, industry_id, days=days, keyword=keyword, monitor_id=monitor_id),
        "topic_suggestions": topic_suggestions(db, industry_id, days=days, keyword=keyword),
    }


def compare_keywords(db: Session, industry_id: int, keywords: Iterable[str], *,
                     days: int = DEFAULT_DAYS) -> List[Dict[str, Any]]:
    """按关键词横向对比 6 KPI —— 定位「哪个问题上我们表现最差」。"""
    out: List[Dict[str, Any]] = []
    for kw in keywords:
        kw = (kw or "").strip()
        if not kw:
            continue
        runs = sample_runs(load_runs(db, industry_id, days=days, keyword=kw))
        kpis = compute_kpis(runs)
        out.append({"keyword": kw, **kpis})
    out.sort(key=lambda x: x["brand_visibility"])
    return out
