"""
竞品检测：AI 在同一批问题上还推荐了谁

为什么这块比看起来重要
----------------------
「我们被提到了吗」只是半个问题。完整的问法是
「在同一个问题上，AI 把我们和谁放在一起比，谁排在前面」。

竞品库（``GeoVisibilityCompetitor``）里 ``is_self=1`` 的那条就是**基线**，
所有对比都以它为锚点，所以看板上的「我们 vs 竞品」不需要前端特殊处理。

检测方式分两档
--------------
1. **词表匹配**（默认，零成本、可复现）：用竞品库里的名称与别名去回答正文里找。
   这是主力 —— 竞品名是运营自己维护的，比让模型「猜」可靠得多。
2. **LLM 抽取**（可选，``use_llm=True``）：把回答喂给模型，让它列出提到的厂商名。
   用于发现「还没进竞品库的新对手」，但需要已配置 LLM，且结果不稳定，
   因此只作为补充，永远不覆盖词表匹配的结果。

情感与位次都锚定在竞品名的上下文窗口内，和品牌指标用同一套判定逻辑，
避免出现「品牌用一套口径、竞品用另一套口径」导致对比失真。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from .metrics import classify_sentiment, find_mentions, merge_spans

# 竞品名在回答里的上下文窗口（与品牌指标保持一致）
CONTEXT_RADIUS = 70

# 一次检测最多认多少条竞品（防止异常回答产生大量噪声条目）
MAX_DETECTIONS = 40


# ============================================================
#  竞品库 CRUD
# ============================================================
def list_competitors(db: Session, industry_id: int, include_deleted: bool = False) -> List[Any]:
    from ...models import GeoVisibilityCompetitor

    q = db.query(GeoVisibilityCompetitor).filter(
        GeoVisibilityCompetitor.industry_id == industry_id
    )
    if not include_deleted:
        q = q.filter(GeoVisibilityCompetitor.is_deleted == 0)
    return q.order_by(
        GeoVisibilityCompetitor.is_self.desc(),
        GeoVisibilityCompetitor.id.asc(),
    ).all()


def competitor_to_dict(row) -> Dict[str, Any]:
    try:
        aliases = json.loads(row.aliases_json or "[]")
    except (TypeError, ValueError):
        aliases = []
    return {
        "id": row.id,
        "industry_id": row.industry_id,
        "name": row.name,
        "aliases": aliases if isinstance(aliases, list) else [],
        "is_self": row.is_self,
        "note": row.note or "",
        "create_time": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else "",
    }


def upsert_competitor(db: Session, industry_id: int, name: str, *,
                      aliases: Optional[Iterable[str]] = None,
                      is_self: int = 0, note: str = "") -> Any:
    """按 (industry_id, name) upsert。

    同名重复录入是运营最常见的误操作，这里直接合并而不是插一条重复的 ——
    否则看板上会出现两个同名竞品各占一行，数字被拆成两半。
    """
    from ...models import GeoVisibilityCompetitor

    name = (name or "").strip()
    if not name:
        raise ValueError("竞品名称不能为空")

    row = db.query(GeoVisibilityCompetitor).filter(
        GeoVisibilityCompetitor.industry_id == industry_id,
        GeoVisibilityCompetitor.name == name,
    ).first()

    alias_list = [a.strip() for a in (aliases or ()) if (a or "").strip()]

    if row:
        if alias_list:
            row.aliases_json = json.dumps(alias_list, ensure_ascii=False)
        row.is_self = int(is_self) if is_self else row.is_self
        if note:
            row.note = note
        row.is_deleted = 0
    else:
        row = GeoVisibilityCompetitor(
            industry_id=industry_id,
            name=name,
            aliases_json=json.dumps(alias_list, ensure_ascii=False),
            is_self=int(is_self or 0),
            note=note,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_competitor(db: Session, competitor_id: int) -> bool:
    """软删除：历史检测结果仍要能查到它，硬删会让过去的对比数据变成孤儿。

    只匹配未删除的行，因此「删一个已经删过的」返回 False，
    调用方能据此给出 404，而不是把空操作也报成成功。
    """
    from ...models import GeoVisibilityCompetitor

    row = db.query(GeoVisibilityCompetitor).filter(
        GeoVisibilityCompetitor.id == competitor_id,
        GeoVisibilityCompetitor.is_deleted == 0,
    ).first()
    if not row:
        return False
    row.is_deleted = 1
    db.commit()
    return True


def seed_self_brand(db: Session, industry_id: int) -> Any:
    """把本品牌作为基线写进竞品库（``is_self=1``）。"""
    from ...brand_config import BRAND_ALIASES, BRAND_NAME, BRAND_PRODUCT

    aliases = [BRAND_PRODUCT, *BRAND_ALIASES]
    return upsert_competitor(
        db, industry_id, BRAND_NAME or "本品牌",
        aliases=[a for a in aliases if a and a != BRAND_NAME],
        is_self=1, note="系统自动写入的本品牌基线",
    )


# ============================================================
#  检测
# ============================================================
def _aliases_of(row) -> List[str]:
    try:
        stored = json.loads(row.aliases_json or "[]")
    except (TypeError, ValueError):
        stored = []
    names = [row.name, *(stored if isinstance(stored, list) else [])]
    seen, out = set(), []
    for n in names:
        n = (n or "").strip()
        if len(n) >= 2 and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def detect_in_text(answer_text: str, competitors: Sequence[Any]) -> List[Dict[str, Any]]:
    """在回答正文里找竞品，返回按「首次出现顺序」排序的检测结果。

    排序依据是首次出现位置 —— 与信源 rank 同一思路：
    AI 先提谁，通常意味着谁在它的判断里更靠前。
    """
    text = answer_text or ""
    found: List[Dict[str, Any]] = []

    for row in competitors:
        aliases = _aliases_of(row)
        if not aliases:
            continue
        spans: List[tuple] = []
        for alias in aliases:
            spans.extend(find_mentions(text, alias))
        if not spans:
            continue
        # 必须跨别名再合并一次：别名往往包含在全称里
        # （「某某」⊂「某某真空科技」），不合并就会把一次提及数成两次。
        spans = merge_spans(spans)
        spans.sort()
        first_start, first_end = spans[0]

        ctx_start = max(0, first_start - CONTEXT_RADIUS)
        ctx_end = min(len(text), first_end + CONTEXT_RADIUS)
        context = text[ctx_start:ctx_end]

        found.append({
            "competitor_id": row.id,
            "name": row.name,
            "is_self": int(row.is_self or 0),
            "mentioned": 1,
            "mention_count": len(spans),
            "first_pos": first_start,
            "sentiment": classify_sentiment(context),
            "snippet": context.strip()[:400],
        })

    found.sort(key=lambda x: x["first_pos"])
    for idx, item in enumerate(found[:MAX_DETECTIONS], start=1):
        item["rank"] = idx
        item.pop("first_pos", None)
    return found[:MAX_DETECTIONS]


def save_detections(db: Session, run_id: int, detections: Sequence[Dict[str, Any]],
                    replace: bool = True) -> int:
    """把检测结果落到 ``geo_visibility_competitor_detection``。

    ``replace=True`` 会先清掉该 Run 的旧结果 —— 重跑检测时不该累积出重复行。
    """
    from ...models import GeoVisibilityCompetitorDetection

    if replace:
        db.query(GeoVisibilityCompetitorDetection).filter(
            GeoVisibilityCompetitorDetection.run_id == run_id
        ).delete()

    count = 0
    for item in detections:
        db.add(GeoVisibilityCompetitorDetection(
            run_id=run_id,
            competitor_id=int(item.get("competitor_id") or 0),
            name=str(item.get("name") or "")[:128],
            mentioned=int(item.get("mentioned") or 0),
            mention_count=int(item.get("mention_count") or 0),
            rank=int(item.get("rank") or 0),
            sentiment=str(item.get("sentiment") or ""),
            snippet=str(item.get("snippet") or ""),
        ))
        count += 1
    db.commit()
    return count


def detect_from_run(db: Session, run, *, competitors: Optional[Sequence[Any]] = None,
                    persist: bool = True) -> List[Dict[str, Any]]:
    """对一次探测做竞品检测（默认用该行业的竞品库）。"""
    if competitors is None:
        competitors = list_competitors(db, run.industry_id)
    detections = detect_in_text(run.answer_text or "", competitors)
    if persist and detections:
        save_detections(db, run.id, detections)
    return detections


def extract_competitor_names(answer_text: str, llm_config: Dict[str, Any]) -> List[str]:
    """可选：让模型列出回答里提到的厂商名（用于发现新竞品）。

    刻意只做「建议」：模型给出的名字可能是错的、可能是通用词，
    因此调用方应当把它作为候选展示给运营确认，而不是直接入库。
    """
    from ..llm import LLMError, get_provider

    if not (llm_config or {}).get("api_key"):
        return []
    prompt = (
        "从下面这段回答里，提取所有被提到的**真空设备/工业设备厂商或品牌名称**。\n"
        "只输出 JSON 数组，不要任何解释，例如：[\"品牌A\", \"品牌B\"]\n"
        "如果没有提到任何厂商，输出 []。\n\n"
        f"回答正文：\n{answer_text[:6000]}"
    )
    try:
        provider = get_provider(llm_config)
        raw = provider.generate(prompt, temperature=0.0, max_tokens=500)
    except (LLMError, Exception):  # noqa: BLE001 - 抽取失败不该影响主流程
        return []

    match = re.search(r"\[.*\]", raw or "", re.DOTALL)
    if not match:
        return []
    try:
        names = json.loads(match.group(0))
    except (TypeError, ValueError):
        return []
    if not isinstance(names, list):
        return []
    seen, out = set(), []
    for n in names:
        n = str(n).strip()
        if 2 <= len(n) <= 40 and n not in seen:
            seen.add(n)
            out.append(n)
    return out[:30]


# ============================================================
#  对比看板
# ============================================================
def board(db: Session, industry_id: int, *, days: int = 30, keyword: str = "",
          monitor_id: int = 0) -> List[Dict[str, Any]]:
    """我们 vs 竞品在同一批问题上的提及率对比。

    基线（``is_self=1``）恒排第一行，运营一眼就能看到差距是正是负。
    """
    from . import analytics

    runs = analytics.load_runs(db, industry_id, days=days, keyword=keyword,
                               monitor_id=monitor_id)
    usable = [r for r in runs if getattr(r, "status", "") == "completed"]
    total = len(usable)
    if not total:
        return []

    competitors = list_competitors(db, industry_id)
    if not competitors:
        return []

    rows: List[Dict[str, Any]] = []
    for row in competitors:
        mentioned_runs = 0
        mention_total = 0
        rank_sum = 0
        rank_count = 0
        positive = 0
        for run in usable:
            detections = detect_in_text(run.answer_text or "", [row])
            if not detections:
                continue
            item = detections[0]
            mentioned_runs += 1
            mention_total += int(item["mention_count"])
            rank_sum += int(item["rank"])
            rank_count += 1
            if item["sentiment"] == "positive":
                positive += 1
        rows.append({
            "competitor_id": row.id,
            "name": row.name,
            "is_self": int(row.is_self or 0),
            "mentioned_runs": mentioned_runs,
            "mention_rate": round(mentioned_runs / total, 4) if total else 0.0,
            "mention_total": mention_total,
            "avg_rank": round(rank_sum / rank_count, 2) if rank_count else 0,
            "positive_rate": round(positive / mentioned_runs, 4) if mentioned_runs else 0.0,
        })

    rows.sort(key=lambda x: (not x["is_self"], -x["mention_rate"], -x["mention_total"]))
    return rows


def gap_analysis(board_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """从对比结果里算出「我们在哪里落后」，直接给结论而不是给一堆数字。"""
    self_row = next((r for r in board_rows if r["is_self"]), None)
    if not self_row:
        return {"has_baseline": False, "behind": [], "ahead": []}

    behind = [r for r in board_rows
              if not r["is_self"] and r["mention_rate"] > self_row["mention_rate"]]
    ahead = [r for r in board_rows
             if not r["is_self"] and r["mention_rate"] < self_row["mention_rate"]]
    behind.sort(key=lambda x: x["mention_rate"], reverse=True)
    return {
        "has_baseline": True,
        "self_mention_rate": self_row["mention_rate"],
        "competitor_count": len([r for r in board_rows if not r["is_self"]]),
        "behind": [
            {"name": r["name"], "mention_rate": r["mention_rate"],
             "gap": round(r["mention_rate"] - self_row["mention_rate"], 4)}
            for r in behind[:10]
        ],
        "ahead": [
            {"name": r["name"], "mention_rate": r["mention_rate"],
             "gap": round(self_row["mention_rate"] - r["mention_rate"], 4)}
            for r in ahead[:10]
        ],
    }
