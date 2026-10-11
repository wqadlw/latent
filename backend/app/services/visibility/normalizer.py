"""
可见性结果归一化：从 AI 回答里抽出信源，并算出品牌可见性指标

为什么这一步是 GEO 的关键
-------------------------
不同引擎、不同调用方式返回的「引用」格式差异巨大：
有的给 Markdown 链接、有的给裸 URL、有的只在正文里写 `[1]`、有的干脆只提域名。
如果各 provider 各自解析，同一篇回答在不同引擎下会算出完全不同的信源列表，
跨引擎对比就失去意义。

归一化层把所有形态统一成 ``SourceData``，是「跨引擎可比」的前提。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

from .metrics import classify_sentiment, find_mentions, has_data_evidence, has_recommend

# ---- 引用形态 ----
# Markdown 链接 [标题](https://...)
_MD_LINK_RE = re.compile(r"\[([^\]\n]{1,120})\]\((https?://[^\s)]+)\)")
# 裸 URL
_BARE_URL_RE = re.compile(r"(?<![(\[<])\bhttps?://[^\s\)\]，。；、\"'<>]+")
# 纯域名（无协议）
_BARE_DOMAIN_RE = re.compile(
    r"\b((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:com\.cn|net\.cn|org\.cn|gov\.cn|edu\.cn|co\.jp|co\.uk|com|cn|net|org|io|ai|co|me|tv|info|biz))\b",
    re.IGNORECASE,
)
# 数字引用标记 [1] / ［1］ / 【1】
_CITATION_MARK_RE = re.compile(r"[\[［【]\s*(\d{1,2})\s*[\]］】]")
# 来源行：`来源：xxx` / `Sources:` / `参考资料`
_SOURCE_LINE_RE = re.compile(r"(来源|参考|引用|sources?|references?)\s*[:：]?\s*(.+)", re.IGNORECASE)

# ---- 域名权威度分级（按站点类型，而非流量）----
_AUTHORITY_HIGH = (
    "gov.cn", "edu.cn", "ac.cn", "wikipedia.org", "xinhuanet.com", "people.com.cn",
    "cctv.com", "chinadaily.com.cn", "thepaper.cn", "caixin.com", "yicai.com",
    "nature.com", "sciencedirect.com", "ieee.org", "springer.com", "arxiv.org",
)
_AUTHORITY_MEDIUM = (
    "zhihu.com", "sohu.com", "163.com", "sina.com.cn", "qq.com", "baidu.com",
    "baijiahao.baidu.com", "toutiao.com", "36kr.com", "huxiu.com", "csdn.net",
    "jianshu.com", "cnblogs.com", "oschina.net", "infoq.cn", "leiphone.com",
    "iyiou.com", "qianzhan.com", "chyxx.com", "smm.cn", "d1net.com",
)
_AUTHORITY_LOW_HINT = ("blog", "bbs", "forum", "tieba", "douban", "xiaohongshu")

# 单次解析的信源上限（防止异常回答产生成千上万条垃圾信源）
_MAX_SOURCES = 60


def normalize_host(raw: str) -> str:
    """从 URL 或域名串里取小写主机名（去 www.）。"""
    value = (raw or "").strip().lower()
    if not value:
        return ""
    if "//" in value:
        host = urlparse(value).netloc
    else:
        host = value.split("/", 1)[0]
    host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def authority_level(host: str) -> str:
    """按域名判定权威度：high / medium / low。"""
    h = normalize_host(host)
    if not h:
        return "low"
    for suffix in _AUTHORITY_HIGH:
        if h == suffix or h.endswith("." + suffix):
            return "high"
    for suffix in _AUTHORITY_MEDIUM:
        if h == suffix or h.endswith("." + suffix):
            return "medium"
    return "low"


def is_owned(host: str, owned_hosts: Sequence[str]) -> bool:
    """判断信源是否属于自有站点（品牌官网 / 自建站）。"""
    h = normalize_host(host)
    if not h:
        return False
    for owned in owned_hosts or ():
        o = normalize_host(owned)
        if o and (h == o or h.endswith("." + o)):
            return True
    return False


def _title_for(url: str, host: str) -> str:
    """无标题时用 URL 路径末段兜底，比留空更有信息量。"""
    path = urlparse(url).path if "//" in url else ""
    slug = path.rstrip("/").rsplit("/", 1)[-1]
    if slug and not slug.isdigit():
        return slug.replace("-", " ").replace("_", " ")[:80]
    return host


def _context_snippet(text: str, pos: int, radius: int = 120) -> str:
    return text[max(0, pos - radius): min(len(text), pos + radius)].strip()


def extract_sources(answer_text: str, *, owned_hosts: Sequence[str] = (),
                    brand_aliases: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """从 AI 回答里抽取被引用的信源。

    按「出现顺序」定 rank（1 = 第一个被引用），这是可见性分析里最核心的排序依据。
    同一域名只保留**首次**出现的那条 —— 一个站点被引用 5 次不代表它有 5 个不同价值，
    重复计数会严重扭曲「信源偏好榜」。
    """
    text = answer_text or ""
    found: List[Dict[str, Any]] = []
    seen_keys = set()

    def _push(url: str, title: str, source_type: str, citation_key: str = "",
              pos: int = 0, host: str = "") -> None:
        """记一条信源。``host`` 用于「只有域名、没有 URL」的场景。

        去重键**优先用域名**（而不是完整 URL）：
        同一个站点在回答里被引用 3 次，只说明它重要一次，
        记成 3 条会把「信源偏好榜」的份额算歪。
        """
        # 传进来的 host 也要过一遍 normalize_host，否则 "www.example.com"
        # 和 URL 通道解析出的 "example.com" 会被当成两个不同站点各记一条。
        host = normalize_host(host or url)
        key = host or url
        if not key or key in seen_keys:
            return
        seen_keys.add(key)
        found.append({
            "source_type": source_type,
            "citation_key": citation_key,
            "title": (title or "").strip()[:200] or _title_for(url, host),
            "url": url[:500],
            "domain": host,
            "site_name": host,
            "snippet": _context_snippet(text, pos) if pos else "",
            "summary": "",
            "content_excerpt": "",
            "published_at": "",
            "rank": 0,  # 稍后按出现顺序统一编号
            "rank_score": 0.0,
            "authority_level": authority_level(host),
            "is_owned": 1 if is_owned(host, owned_hosts) else 0,
            "metadata_json": {},
        })

    # 1) Markdown 链接（信息量最高：标题 + URL 都有）
    for m in _MD_LINK_RE.finditer(text):
        _push(m.group(2), m.group(1), "markdown_link", pos=m.start())

    # 2) 裸 URL
    for m in _BARE_URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:!?）)】]")
        _push(url, "", "bare_url", pos=m.start())

    # 3) 纯域名（无协议，常见于「来源：xxx.com」这类写法）
    #    必须显式把域名作为 host 传进去 —— 这一步没有 URL，
    #    早期实现误把它当 title 传，导致裸域名被整批丢弃。
    for m in _BARE_DOMAIN_RE.finditer(text):
        _push("", "", "domain_mention", pos=m.start(), host=m.group(1))

    # 4) 来源行（`来源：xxx` / `Sources: xxx`）—— 把其中的名称也记为信源
    for line in text.splitlines():
        m = _SOURCE_LINE_RE.search(line)
        if not m:
            continue
        body = m.group(2).strip()
        for piece in re.split(r"[、,，;；|]", body):
            name = piece.strip().strip("《》\"'")
            if not (1 < len(name) <= 60) or name.lower().startswith("http"):
                continue
            # 已经被前面的域名通道收过的，不再重复记一条（否则同一站点会以
            # 「domain_mention」和「source_line」两种身份各占一行）
            if normalize_host(name) in seen_keys:
                continue
            key = "name:" + name
            if key in seen_keys:
                continue
            seen_keys.add(key)
            found.append({
                "source_type": "source_line",
                "citation_key": "",
                "title": name,
                "url": "",
                "domain": "",
                "site_name": name,
                "snippet": line.strip()[:300],
                "summary": "",
                "content_excerpt": "",
                "published_at": "",
                "rank": 0,
                "rank_score": 0.0,
                "authority_level": "low",
                "is_owned": 0,
                "metadata_json": {},
            })

    # 按出现顺序编号：rank 是「AI 引用优先级」的直接代理指标
    for i, item in enumerate(found[: _MAX_SOURCES], start=1):
        item["rank"] = i
        # rank_score：越靠前分越高，且权威度加权（用于信源偏好榜排序）
        base = 1.0 / i
        weight = {"high": 1.5, "medium": 1.1, "low": 0.8}.get(str(item["authority_level"]), 0.8)
        item["rank_score"] = round(base * weight, 4)
        if item["is_owned"]:
            item["rank_score"] = round(item["rank_score"] * 1.3, 4)

    # 引用标记 `[1]`：把标记与最近的信源关联（尽力而为，不强行）
    markers = [m.group(1) for m in _CITATION_MARK_RE.finditer(text)]
    if markers:
        for idx, item in enumerate(found[: len(markers)], start=1):
            if not item.get("citation_key"):
                item["citation_key"] = str(idx)

    return found[: _MAX_SOURCES]


def analyze_answer(answer_text: str, sources: Sequence[Dict[str, Any]], *,
                   brand_aliases: Iterable[str] = (), owned_hosts: Sequence[str] = (),
                   ) -> Dict[str, Any]:
    """算出品牌可见性指标。

    关键定义（与 GEOFlow 的 ``AiVisibilityAnalyticsService`` 对齐）::

        brand_visible = 回答正文提到品牌  OR  引用信源前 3 名里有自有站点

    这个 OR 很重要：AI 回答里没点名你，但把你的站作为来源引用了，
    这同样是可见 —— 而且往往比「被点名」更有价值（说明你的内容被当作依据）。
    """
    text = answer_text or ""
    aliases = [a for a in (brand_aliases or ()) if a and len(a) >= 2]

    # 1) 回答正文是否提到品牌
    answer_mentions = bool(aliases) and any(a in text for a in aliases)

    # 2) 引用信源里品牌/自有站点的位次
    brand_ranks: List[int] = []
    for s in sources:
        rank = int(s.get("rank") or 0)
        if rank <= 0:
            continue
        if s.get("is_owned") or (aliases and _source_mentions_brand(s, aliases)):
            brand_ranks.append(rank)

    best_rank: Optional[int] = min(brand_ranks) if brand_ranks else None
    top1 = bool(best_rank == 1)
    top3 = bool(best_rank is not None and best_rank <= 3)
    brand_visible = bool(answer_mentions or top3)

    # 3) 情感：锚定在品牌提及的上下文窗口内
    sentiment = "neutral"
    sentiment_score = 0.0
    if aliases:
        spans = []
        for a in aliases:
            spans.extend(find_mentions(text, a))
        if spans:
            contexts = [
                text[max(0, s - 120): min(len(text), e + 120)]
                for s, e in spans[:5]
            ]
            labels = [classify_sentiment(c) for c in contexts]
            pos, neg = labels.count("positive"), labels.count("negative")
            if pos and pos >= neg:
                sentiment = "positive"
            elif neg > pos:
                sentiment = "negative"
            sentiment_score = round((pos - neg) / max(len(labels), 1), 3)

    # 4) 推荐信号与数据佐证
    recommended = False
    has_data = False
    if aliases:
        for a in aliases:
            idx = text.find(a)
            if idx < 0:
                continue
            ctx = text[max(0, idx - 150): min(len(text), idx + 150)]
            if has_recommend(ctx):
                recommended = True
            if has_data_evidence(ctx):
                has_data = True

    return {
        "answer_mentions_brand": answer_mentions,
        "brand_visible": brand_visible,
        "top1": top1,
        "top3": top3,
        "best_brand_rank": best_rank,
        "brand_source_count": len(brand_ranks),
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "recommended": recommended,
        "has_data_evidence": has_data,
        "source_count": len(sources),
        "owned_source_count": sum(1 for s in sources if s.get("is_owned")),
    }


def _source_mentions_brand(source: Dict[str, Any], aliases: Sequence[str]) -> bool:
    """信源的标题/摘要/域名里是否出现品牌。"""
    blob = " ".join(str(source.get(k) or "") for k in ("title", "summary", "site_name", "domain", "snippet"))
    return any(a in blob for a in aliases)


def top_domains(sources: Sequence[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    """汇总信源域名分布（「哪些站点被 AI 偏爱引用」）。"""
    agg: Dict[str, Dict[str, Any]] = {}
    for s in sources:
        host = str(s.get("domain") or "").strip()
        if not host:
            continue
        slot = agg.setdefault(host, {
            "domain": host, "count": 0, "total_rank_score": 0.0,
            "authority_level": str(s.get("authority_level") or "low"),
            "is_owned": int(s.get("is_owned") or 0),
            "best_rank": 9999,
            "titles": [],
        })
        slot["count"] += 1
        slot["total_rank_score"] += float(s.get("rank_score") or 0)
        slot["best_rank"] = min(slot["best_rank"], int(s.get("rank") or 9999))
        if s.get("title") and len(slot["titles"]) < 3:
            slot["titles"].append(s["title"])

    out = list(agg.values())
    for slot in out:
        slot["total_rank_score"] = round(slot["total_rank_score"], 3)
        if slot["best_rank"] == 9999:
            slot["best_rank"] = 0
    out.sort(key=lambda x: (x["count"], x["total_rank_score"]), reverse=True)
    return out[:limit]


def source_action(source: Dict[str, Any]) -> str:
    """对一条信源给出行动建议（内容该铺到哪里）。"""
    if source.get("is_owned"):
        return "自有站点：保持更新，确保 llms.txt / sitemap.xml 收录"
    level = str(source.get("authority_level") or "low")
    if level == "high":
        return "高权威信源：优先争取投稿/合作/被引用，对 AI 采信度提升最大"
    if level == "medium":
        return "行业媒体：适合做选题对标与内容铺设，性价比高"
    return "长尾信源：可作为补充覆盖，优先级较低"
