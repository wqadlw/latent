"""
证据核对器：给每条断言去知识库找依据

核心思路
--------
断言抽取（``claim_extractor``）产出的是「需要被证实的主张」，
本模块负责回答「知识库里有没有东西能撑住它」。

检索算法：**倒排索引 + 词项命中计数**
-------------------------------------
朴素做法是「每条断言 × 每个知识条目」逐一比对，复杂度 O(断言 × 条目)；
知识库上百条、断言上百条时就是几万次全文本扫描，慢到不可用。

这里改为构建**倒排索引**（词项 → 条目集合），
单条断言的检索成本降为「词项数 × 该词项的倒排链长度」，
且索引带 TTL 缓存，连续质检多篇文章时只建一次。

判定规则
--------
- 断言含数字时，**数字必须能在证据里找到**，否则不算命中
  （数字是断言的骨头，骨头对不上，词面相似没有意义）
- 词项覆盖率达标 + 数字命中 → ``verified``
- 有命中但不够强 → ``partial``
- 完全没命中 → ``unverified``

安全边界
--------
本模块**只读知识库**，不调用任何 AI。AI 辅助裁决是可选增强，
由 ``quality_gate`` 在本地判定不足时才触发，且受熔断器保护。
"""
from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Dict, List, Optional, Tuple

from .claim_extractor import ABSOLUTE, CERTIFICATION, COMPARISON, QUANTIFIED, extract_terms

# 证据判定状态
VERIFIED = "verified"
PARTIAL = "partial"
UNVERIFIED = "unverified"

# 词项覆盖率阈值
_VERIFY_RATIO = 0.40        # >= 此比例 + 数字命中 → verified
_PARTIAL_RATIO = 0.20       # >= 此比例 → partial

# 单条知识条目参与索引的最大字符数（标题+摘要+正文前 N 字）
_ITEM_TEXT_LIMIT = 2000
# 参与索引的条目上限（防御性上限，避免超大知识库把内存打满）
_MAX_ITEMS = 2000

# 索引缓存 TTL（秒）
_INDEX_TTL = 300.0

_INDEX_LOCK = threading.Lock()
_INDEX_CACHE: Dict[int, Dict[str, object]] = {}


class KnowledgeIndex:
    """知识库倒排索引。"""

    __slots__ = ("items", "postings", "numbers")

    def __init__(self, items: List[Dict[str, object]]):
        self.items = items
        # 词项 → 条目下标集合
        self.postings: Dict[str, set] = {}
        # 数字 → 条目下标集合（数字检索比词项更关键，单独建链）
        self.numbers: Dict[str, set] = {}

        for idx, item in enumerate(items):
            text = str(item.get("text") or "")
            for term in extract_terms(text, max_terms=600):
                self.postings.setdefault(term, set()).add(idx)
            for token in _digits(text):
                self.numbers.setdefault(token, set()).add(idx)

    def search(self, claim_terms: List[str], top_k: int = 3) -> List[Tuple[int, float, int]]:
        """检索与断言最相关的知识条目。

        返回 ``[(item_index, term_ratio, term_hits)]``，按命中词项数降序。
        """
        if not claim_terms:
            return []
        counter: Counter = Counter()
        for term in claim_terms:
            for idx in self.postings.get(term, ()):
                counter[idx] += 1
        if not counter:
            return []
        total = len(claim_terms)
        return [
            (idx, hits / total, hits)
            for idx, hits in counter.most_common(top_k)
        ]

    def number_supported(self, numbers: List[str], item_index: int) -> bool:
        """断言里的数字是否在该条目中出现。"""
        if not numbers:
            return True
        for n in numbers:
            if item_index in self.numbers.get(n, ()):
                return True
        return False


def _digits(text: str) -> List[str]:
    """抽出文本中的数字 token（用于数字级核对）。"""
    out = []
    buf = []
    for ch in text or "":
        if ch.isdigit() or (ch == "." and buf):
            buf.append(ch)
        else:
            if buf:
                out.append("".join(buf).strip("."))
                buf = []
    if buf:
        out.append("".join(buf).strip("."))
    return [d for d in out if d]


def build_index(db, industry_id: int, *, use_cache: bool = True) -> KnowledgeIndex:
    """从知识库构建倒排索引（带 TTL 缓存）。"""
    from ..models import KnowledgeItem

    now = time.time()
    if use_cache:
        with _INDEX_LOCK:
            cached = _INDEX_CACHE.get(industry_id)
            if cached and now - float(cached.get("ts") or 0) < _INDEX_TTL:
                return cached["index"]  # type: ignore[return-value]

    q = db.query(KnowledgeItem).filter(KnowledgeItem.is_deleted == 0)
    if industry_id:
        q = q.filter(KnowledgeItem.industry_id == industry_id)
    rows = q.limit(_MAX_ITEMS).all()

    items: List[Dict[str, object]] = []
    for r in rows:
        text = "\n".join(x for x in [
            r.title or "",
            r.summary or "",
            (r.content or "")[:_ITEM_TEXT_LIMIT],
            r.tags or "",
        ] if x)
        items.append({
            "id": r.id,
            "title": r.title or "",
            "summary": (r.summary or "")[:200],
            "source": r.source or "",
            "text": text,
        })

    index = KnowledgeIndex(items)
    if use_cache:
        with _INDEX_LOCK:
            _INDEX_CACHE[industry_id] = {"ts": now, "index": index}
    return index


def clear_index_cache() -> None:
    """清空索引缓存（知识库变更后调用）。"""
    with _INDEX_LOCK:
        _INDEX_CACHE.clear()


def verify_claims(db, claims: List[Dict[str, object]], industry_id: int = 0,
                  *, index: Optional[KnowledgeIndex] = None,
                  use_cache: bool = True) -> List[Dict[str, object]]:
    """逐条核对断言，返回带证据判定结果的断言列表。

    每条结果在原始断言基础上增加：
    ``status``（verified/partial/unverified）、``evidence``（命中的知识条目）、
    ``note``（未通过的原因说明）。
    """
    if not claims:
        return []

    idx = index if index is not None else build_index(db, industry_id, use_cache=use_cache)
    results: List[Dict[str, object]] = []

    for claim in claims:
        terms = list(claim.get("terms") or [])          # type: ignore[arg-type]
        numbers = [t for t in terms if t.isdigit()]
        claim_type = str(claim.get("type") or "")

        candidates = idx.search(terms, top_k=3)
        best: Optional[Dict[str, object]] = None
        status = UNVERIFIED
        note = ""

        for item_index, ratio, hits in candidates:
            number_ok = idx.number_supported(numbers, item_index)
            # 数字对不上 → 这条证据不成立，继续找下一条
            if numbers and not number_ok:
                continue
            if ratio >= _VERIFY_RATIO:
                status = VERIFIED
            elif ratio >= _PARTIAL_RATIO:
                status = PARTIAL
            else:
                continue
            item = idx.items[item_index]
            best = {
                "item_id": item["id"],
                "title": item["title"],
                "source": item["source"],
                "snippet": str(item.get("summary") or "")[:200],
                "term_ratio": round(ratio, 3),
                "term_hits": hits,
                "number_matched": number_ok if numbers else None,
            }
            break

        if status == UNVERIFIED:
            if claim_type == ABSOLUTE:
                note = "绝对化表述：广告法禁止且无法用证据支撑，必须改写为可量化的客观描述"
            elif claim_type == CERTIFICATION:
                note = "资质表述未在知识库中找到对应证书或检测报告，需补充来源或删除"
            elif numbers and candidates:
                note = "知识库中有相近内容但**关键数字对不上**，需核对数据出处"
            elif not idx.items:
                note = "知识库为空，无法核对；建议先补充知识条目再启用证据闸门"
            else:
                note = "知识库中未找到支撑该表述的依据，需补充来源或改为定性描述"
        elif status == PARTIAL:
            note = "找到相近依据但匹配度不足，建议人工确认数据口径是否一致"

        results.append({
            **claim,
            "status": status,
            "evidence": best,
            "note": note,
        })

    return results


def coverage(verified_claims: List[Dict[str, object]]) -> Dict[str, object]:
    """计算证据覆盖率与分布。"""
    total = len(verified_claims)
    counts = {VERIFIED: 0, PARTIAL: 0, UNVERIFIED: 0}
    for c in verified_claims:
        st = str(c.get("status") or UNVERIFIED)
        counts[st] = counts.get(st, 0) + 1

    # 覆盖率把 partial 记为半份 —— 它确实提供了部分依据，全盘否定会低估内容质量
    weighted = counts[VERIFIED] + counts[PARTIAL] * 0.5
    rate = round(weighted / total, 4) if total else 1.0

    return {
        "total": total,
        "verified": counts[VERIFIED],
        "partial": counts[PARTIAL],
        "unverified": counts[UNVERIFIED],
        "coverage": rate,
    }


def by_type(verified_claims: List[Dict[str, object]]) -> Dict[str, Dict[str, int]]:
    """按断言类型统计通过情况（供看板展示「哪类表述最缺依据」）。"""
    out: Dict[str, Dict[str, int]] = {}
    for c in verified_claims:
        t = str(c.get("type") or "unknown")
        slot = out.setdefault(t, {VERIFIED: 0, PARTIAL: 0, UNVERIFIED: 0, "total": 0})
        st = str(c.get("status") or UNVERIFIED)
        slot[st] = slot.get(st, 0) + 1
        slot["total"] += 1
    return out


# 需要重点关注的类型（用于「哪些类型的表述最不可信」提示）
_TYPE_LABELS = {
    QUANTIFIED: "量化数据",
    CERTIFICATION: "资质认证",
    COMPARISON: "对比数据",
    ABSOLUTE: "绝对化表述",
}
