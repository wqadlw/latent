"""
AI 答复指标解析（手工通道与自动通道**共用**的单一真源）

历史背景
--------
这些函数原本私有在 ``routers/geo_monitor.py`` 里，只服务于「用户复制 AI 回答
粘贴回系统」这一条通道。v3.1 新增自动采集通道后，如果两边各写一套解析，
必然出现「同一个回答，手工导入判为正面、自动采集判为中性」这种自相矛盾。

因此把它们上提到服务层，两条通道共用：
- 手工通道：``routers/geo_monitor.py`` 的 ``import_reply``
- 自动通道：``services/visibility/collector.py`` 落库后同步到 ``geo_monitor_reply``

解析口径（保持不变）
--------------------
情感 / 推荐 / 证据判定都**锚定在品牌提及的上下文窗口内**（前后各 70 字），
避免被同一段回答里对竞品的评价带偏；并处理否定前缀（「不推荐」→ 负向）。
"""
from __future__ import annotations

import re
from typing import Dict, List

# 情感词（围绕品牌提及的上下文窗口判定，避免被竞品言论带偏）
_POSITIVE_WORDS = [
    "推荐", "首选", "值得", "优秀", "领先", "知名", "专业", "可靠", "信赖",
    "优势", "突出", "创新", "高效", "节能", "稳定", "成熟", "好评", "口碑",
    "标杆", "头部", "第一梯队", "优选", "出色", "强", "放心", "靠谱",
    "案例", "验证", "认证", "资质", "实测", "背书",
]
_NEGATIVE_WORDS = [
    "不推荐", "不值得", "不建议", "差", "问题", "缺陷", "投诉", "纠纷", "负面",
    "落后", "过时", "不稳定", "故障", "风险", "谨慎", "陷阱", "踩坑", "弱",
    "差评", "别买", "回避", "拉黑", "避坑",
]
# 否定前缀：与正面词搭配时翻转为负向
_NEGATORS = ["不", "没", "无", "非", "别", "未", "难以", "慎", "勿"]
# 推荐信号词
_RECOMMEND_WORDS = ["推荐", "首选", "建议选", "值得考虑", "可以选", "优先考虑", "首推", "值得入手", "可以放心"]
# 数据/案例证据
_DATA_PATTERNS = [
    r"\d+\.?\d*\s*%",
    r"\d+\s*万",
    r"\d+\s*台",
    r"\d+\s*个",
    r"\d+\s*年",
    r"\d+\s*小时",
    r"\d+\s*倍",
    r"案例", r"客户", r"实测", r"验证", r"认证", r"数据", r"报告",
]

# 上下文窗口半径（字符）
CONTEXT_RADIUS = 70


def build_brand_variants(brand: str) -> List[str]:
    """生成品牌名的多形态匹配变体（全称/简称/去空格/英文分词）。"""
    variants: List[str] = []
    if not brand:
        return variants
    b = brand.strip()
    variants.append(b)
    # 去空格/括号
    clean = re.sub(r"[\s（）()]+", "", b)
    if clean != b and clean:
        variants.append(clean)
    # 中文品牌：取前 2-3 字作简称（避免单字误命中）
    if len(b) >= 4:
        variants.append(b[:3])
        variants.append(b[:2])
    elif len(b) == 3:
        variants.append(b[:2])
    # 英文/含空格品牌：拆分单词作变体
    if re.search(r"[A-Za-z]", b):
        for part in re.split(r"[\s\-_/]+", b):
            if len(part) >= 3:
                variants.append(part)
    # 去重保序
    seen = set()
    out = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def merge_spans(spans):
    """合并重叠的提及区间，返回去重后的 (start, end) 列表。"""
    if not spans:
        return []
    spans = sorted(spans)
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [tuple(x) for x in merged]


def has_negation_before(text: str, pos: int, window: int = 6) -> bool:
    """判定 pos 处的词前 window 字内是否含否定前缀。"""
    start = max(0, pos - window)
    prefix = text[start:pos]
    return any(neg in prefix for neg in _NEGATORS)


def classify_sentiment(ctx: str) -> str:
    """在品牌提及上下文窗口内判定情感（positive/neutral/negative）。"""
    pos_hits = neg_hits = 0
    for kw in _POSITIVE_WORDS:
        idx = ctx.find(kw)
        if idx != -1:
            # 正面词被否定前缀修饰 → 记为负面
            if has_negation_before(ctx, idx):
                neg_hits += 1
            else:
                pos_hits += 1
    for kw in _NEGATIVE_WORDS:
        if kw in ctx:
            neg_hits += 1
    if pos_hits > 0 and pos_hits >= neg_hits:
        return "positive"
    if neg_hits > pos_hits:
        return "negative"
    return "neutral"


def has_recommend(ctx: str) -> bool:
    """上下文内是否出现明确的推荐信号（排除被否定的，如「不推荐」「不建议」）。"""
    for w in _RECOMMEND_WORDS:
        idx = ctx.find(w)
        if idx != -1:
            if not has_negation_before(ctx, idx):
                return True
    return False


def has_data_evidence(ctx: str) -> bool:
    """上下文内是否含数据/案例证据。"""
    return any(re.search(p, ctx) for p in _DATA_PATTERNS)


def find_mentions(text: str, brand_name: str) -> List[tuple]:
    """定位品牌在回答中的所有提及区间（合并重叠）。"""
    spans = []
    for variant in build_brand_variants(brand_name):
        try:
            pat = re.compile(re.escape(variant))
        except re.error:
            continue
        for m in pat.finditer(text):
            spans.append((m.start(), m.end()))
    return merge_spans(spans)


def parse_ai_reply(reply_text: str, brand_name: str) -> Dict[str, object]:
    """从 AI 答复文本中解析 AI 认可度指标。

    返回 ``mentioned / mention_count / citation_length / sentiment /
    valuable_positive / recommended / snippet``。

    关键设计：
    - 情感 / 推荐 / 证据判定都**锚定在品牌提及的上下文窗口内**，避免被竞品言论带偏
    - 处理否定前缀（"不推荐" → 负向）
    - 品牌变体覆盖简称 / 英文分词 / 去空格
    - 多提及时按上下文逐条判定后聚合，挑选信息量最高的片段做展示
    """
    text = reply_text.strip()
    brand = (brand_name or "").strip()

    spans = find_mentions(text, brand)

    mentioned = 1 if spans else 0
    mention_count = len(spans)

    # 为每个提及提取上下文窗口
    contexts = []
    for (s, e) in spans:
        ctx_start = max(0, s - CONTEXT_RADIUS)
        ctx_end = min(len(text), e + CONTEXT_RADIUS)
        contexts.append(text[ctx_start:ctx_end])

    per_sentiment = []
    recommended = 0
    has_data_any = False
    best_snippet = ""
    best_score = -1
    for ctx in contexts:
        s = classify_sentiment(ctx)
        per_sentiment.append(s)
        if has_recommend(ctx):
            recommended = 1
        has_data = has_data_evidence(ctx)
        if has_data:
            has_data_any = True
        # 挑选信息量最高的片段：正>中>负，且带数据/案例优先
        score = (2 if s == "positive" else 1 if s == "neutral" else 0)
        if has_data:
            score += 1
        if score > best_score:
            best_score = score
            best_snippet = ctx

    if not mentioned:
        sentiment = "neutral"
    else:
        pos = per_sentiment.count("positive")
        neg = per_sentiment.count("negative")
        if pos >= neg and pos > 0:
            sentiment = "positive"
        elif neg > pos:
            sentiment = "negative"
        else:
            sentiment = "neutral"

    citation_length = sum(len(c) for c in contexts)
    # 有价值正面：品牌被正面提及 + 上下文含数据/案例证据
    valuable_positive = 1 if (sentiment == "positive" and has_data_any) else 0

    snippet_text = best_snippet.strip() or ("\n---\n".join(c.strip() for c in contexts[:3]))

    return {
        "mentioned": mentioned,
        "mention_count": mention_count,
        "citation_length": citation_length,
        "sentiment": sentiment,
        "valuable_positive": valuable_positive,
        "recommended": recommended,
        "snippet": snippet_text,
    }


# 向后兼容别名：旧代码按私有名调用
_parse_ai_reply = parse_ai_reply
_build_brand_variants = build_brand_variants
