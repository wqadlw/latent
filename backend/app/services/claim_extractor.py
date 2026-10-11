"""
断言抽取器（Claim Extraction）

要解决的问题
------------
此前质检只会数「正文里有多少个数字」（``geo_score._fact_density``），
但**从不校验这些数字对不对、有没有出处**。一篇写着「效率提升 300%」
却没有任何依据的文章，在旧版质检里反而是「事实密度高」的加分项。

本模块把正文拆成一条条**可验证断言**，交给证据核对环节逐条去知识库找依据。
无依据的断言会被标记出来——这是「内容可信度」从主观感受变成可核查指标的关键一步。

断言类型
--------
- ``quantified``    量化断言：含强单位数字（% / 倍 / 万元 / 小时 / Pa …），**必须**有证据
- ``certification`` 资质断言：ISO / CE / 专利 / 高新技术企业 …，**必须**有证据
- ``comparison``    对比断言：「比传统方案节能 40%」，**必须**有证据
- ``absolute``      绝对化断言：「行业第一」「唯一」「100%」，**必须**有证据
                    （与 ``rule_checker`` 的广告法词表有重叠，但这里关注的是「有没有依据」，
                      两者互补而非重复）

设计取舍
--------
**弱单位的小数字不算断言**。「3 步搞定」「5 个要点」「2 种方案」是结构性表述，
不是事实主张；若把它们也纳入核对，会让几乎每篇文章都挂上一堆无意义告警，
最终导致告警被无视 —— 这比不告警更糟。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# 断言类型
QUANTIFIED = "quantified"
CERTIFICATION = "certification"
COMPARISON = "comparison"
ABSOLUTE = "absolute"

CLAIM_LABELS = {
    QUANTIFIED: "量化数据",
    CERTIFICATION: "资质认证",
    COMPARISON: "对比数据",
    ABSOLUTE: "绝对化表述",
}

# 需要证据的类型（其余仅提示）
EVIDENCE_REQUIRED = (QUANTIFIED, CERTIFICATION, COMPARISON, ABSOLUTE)

# ---- 句子切分：中文句读 + 换行 ----
_SENTENCE_RE = re.compile(r"[^。！？；!?;\n]+[。！？；!?;]?")

# ---- 数字 + 单位 ----
# 强单位：一旦出现就是明确的事实主张，必须可溯源
_STRONG_UNITS = (
    "%", "％", "倍", "万", "亿", "万元", "元", "小时", "分钟", "秒", "天", "年",
    "吨", "公斤", "kg", "g", "t", "㎡", "m³", "m3", "L", "mL",
    "Pa", "kPa", "MPa", "bar", "mbar", "Torr", "℃", "度",
    "W", "kW", "MW", "V", "A", "Hz", "rpm", "dB",
    "米", "毫米", "厘米", "千米", "公里",
)
# 弱单位：小数字时属于结构性表述，不算事实主张
_WEAK_UNITS = ("个", "项", "种", "款", "台", "套", "家", "名", "位", "步", "条", "页", "字")

_UNIT_ALT = "|".join(sorted((re.escape(u) for u in _STRONG_UNITS + _WEAK_UNITS), key=len, reverse=True))
_NUM_UNIT_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(" + _UNIT_ALT + r")")

# 弱单位数字达到这个量级，就不再是结构性表述（如「服务 500 家客户」）
_WEAK_UNIT_MIN = 20

# ---- 资质认证 ----
_CERT_RE = re.compile(
    r"(ISO\s?\d{4,5}|CE\s?认证|3C\s?认证|CCC\s?认证|UL\s?认证|RoHS|REACH|SGS|T[ÜU]V|"
    r"高新技术企业|专精特新|小巨人|发明专利|实用新型|外观专利|软件著作权|"
    r"检测报告|资质证书|认证证书|等级证书|安全生产许可|ISO9001|ISO14001)"
)

# ---- 对比断言：比较词 + 数字 ----
_COMPARISON_RE = re.compile(
    r"(比|相比|对比|较|优于|高于|低于|领先于|超过)[^。！？；\n]{0,24}?\d"
    r"|(提升|提高|降低|减少|增加|节省|节约|缩短|延长)[^。！？；\n]{0,16}?\d"
)

# ---- 绝对化断言 ----
_ABSOLUTE_WORDS = (
    "行业第一", "全国第一", "全球第一", "全网第一", "国内第一",
    "国内领先", "国际领先", "行业领先", "技术领先", "遥遥领先", "首屈一指",
    "唯一", "独家", "首创", "首个", "首家", "首发",
    "顶级", "极致", "完美", "巅峰", "最强", "最好", "最优",
    "100%", "百分百", "绝对", "永久", "永不", "万能", "包治", "根治", "零风险",
)
_ABSOLUTE_RE = re.compile("|".join(re.escape(w) for w in _ABSOLUTE_WORDS))

# ---- 句内自带来源标记（有则降低风险，但不等于已验证）----
_INLINE_SOURCE_RE = re.compile(
    r"(据|数据显示|统计|报告|研究表明|调研|实测|第三方|公开数据|"
    r"客户案例|项目现场|现场实测|检测机构|权威机构|来源[:：])"
)

# ---- 明显不是事实主张的句式（排除）----
# 例：「共 3 步」「以下 5 点」「分为 2 类」——都是结构表述
_STRUCTURAL_RE = re.compile(r"(共|分为|以下|如下|以上|前面|后面|这|那)\s*\d|第\s*\d+\s*[步点条类项个部分章节]")

# 分句边界：抽取断言片段时按这些字符切到「小句」级别，
# 让片段本身可读（"效率提升30%"），而不是机械地前后各截 N 个字。
_CLAUSE_SEP = "，,、；;。！？!?\n"


def _clause(sentence: str, start: int, end: int, pad: int = 10) -> str:
    """取匹配位置所在的「小句」，作为断言的可读片段。

    直接按固定字数前后截取会得到「…效率提升30%，已服务5」这种半截话，
    运营看了无法定位问题。按标点切到小句边界才是可用的。
    """
    left = start
    while left > 0 and sentence[left - 1] not in _CLAUSE_SEP:
        left -= 1
    right = end
    while right < len(sentence) and sentence[right] not in _CLAUSE_SEP:
        right += 1
    snippet = sentence[left:right].strip()
    if not snippet:
        # 兜底：小句为空时退回固定窗口
        snippet = sentence[max(0, start - pad):min(len(sentence), end + pad)].strip()
    return snippet


def split_sentences(text: str) -> List[str]:
    """把正文切成句子（保留标点），空句被丢弃。"""
    out = []
    for m in _SENTENCE_RE.finditer(text or ""):
        s = m.group(0).strip()
        if s:
            out.append(s)
    return out


def _is_structural(sentence: str, number: str) -> bool:
    """判断某个数字是否只是结构性表述而非事实主张。"""
    if _STRUCTURAL_RE.search(sentence):
        return True
    # 年份单独出现（如「2026 年」）不算量化主张
    if len(number) == 4 and number.startswith(("19", "20")):
        return True
    return False


def extract_claims(text: str, max_claims: int = 200) -> List[Dict[str, object]]:
    """从正文中抽取可验证断言。

    返回 ``[{type, text, sentence, sentence_index, offset, has_inline_source, terms}]``。
    ``terms`` 是给证据检索用的关键词（数字 + 中文 2-gram），由本模块统一生成，
    避免检索侧各自实现一套分词导致口径不一致。
    """
    content = text or ""
    sentences = split_sentences(content)
    claims: List[Dict[str, object]] = []
    seen = set()

    cursor = 0
    for idx, sentence in enumerate(sentences):
        # 计算句子在全文中的偏移（用于前端定位高亮）
        offset = content.find(sentence, cursor)
        if offset < 0:
            offset = cursor
        cursor = offset + len(sentence)

        inline_source = bool(_INLINE_SOURCE_RE.search(sentence))

        def _push(claim_type: str, snippet: str, _s=sentence, _i=idx,
                  _o=offset, _src=inline_source) -> None:
            # 显式绑定循环变量为默认参数：避免闭包按引用捕获，
            # 也让 ruff 的 B023 检查通过（该写法在循环里定义函数时是必需的）
            key = (claim_type, snippet)
            if not snippet or key in seen:
                return
            seen.add(key)
            claims.append({
                "type": claim_type,
                "text": snippet,
                "sentence": _s,
                "sentence_index": _i,
                "offset": _o,
                "has_inline_source": _src,
                "terms": extract_terms(snippet),
            })

        # 1) 量化断言
        for m in _NUM_UNIT_RE.finditer(sentence):
            number, unit = m.group(1), m.group(2)
            if unit in _WEAK_UNITS:
                try:
                    if float(number.replace(",", "")) < _WEAK_UNIT_MIN:
                        continue
                except ValueError:
                    continue
            if _is_structural(sentence, number):
                continue
            _push(QUANTIFIED, _clause(sentence, m.start(), m.end()))

        # 2) 资质断言
        for m in _CERT_RE.finditer(sentence):
            _push(CERTIFICATION, _clause(sentence, m.start(), m.end()))

        # 3) 对比断言
        cmp_match = _COMPARISON_RE.search(sentence)
        if cmp_match:
            _push(COMPARISON, _clause(sentence, cmp_match.start(), cmp_match.end()))

        # 4) 绝对化断言
        for m in _ABSOLUTE_RE.finditer(sentence):
            _push(ABSOLUTE, _clause(sentence, m.start(), m.end()))

        if len(claims) >= max_claims:
            break

    return claims


# 中文 2-gram 抽取用的停用词（高频虚词，保留它们会让证据匹配形同虚设）
_STOP_CHARS = set("的了和与及或在是有为对从到把被让使可以这那哪些什么怎么如何并且而且但是因为所以"
                  "我们你们他们它们一个一种进行通过以及对于关于根据按照由于")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}|[\u4e00-\u9fff]+|\d+(?:\.\d+)?")


def extract_terms(text: str, max_terms: int = 40) -> List[str]:
    """抽取用于证据检索的关键词。

    策略：
    - 英文/数字 token 原样保留（型号、规格、标准号等辨识度最高）
    - 中文连续串切成 **2-gram**（中文没有天然词边界，2-gram 在检索召回上最稳）
    - 过滤纯停用字构成的 gram
    """
    terms: List[str] = []
    seen = set()
    for m in _TOKEN_RE.finditer(text or ""):
        tok = m.group(0)
        if tok.isdigit():
            candidates = [tok]
        elif re.match(r"[A-Za-z]", tok):
            candidates = [tok.lower()]
        else:
            # 中文串：切 2-gram；长度不足 2 时整串保留
            if len(tok) < 2:
                continue
            candidates = [tok[i:i + 2] for i in range(len(tok) - 1)]
        for c in candidates:
            if c in seen:
                continue
            if len(c) == 2 and all(ch in _STOP_CHARS for ch in c):
                continue
            seen.add(c)
            terms.append(c)
            if len(terms) >= max_terms:
                return terms
    return terms


def claim_summary(claims: List[Dict[str, object]]) -> Dict[str, int]:
    """按类型统计断言数量（供看板展示）。"""
    out: Dict[str, int] = dict.fromkeys(CLAIM_LABELS, 0)
    for c in claims:
        t = str(c.get("type") or "")
        if t in out:
            out[t] += 1
    out["total"] = len(claims)
    return out


def sample_ranges(text: str, max_characters: int = 6000, max_ranges: int = 12) -> Dict[str, object]:
    """把长文切成若干**互不重叠**的区间用于抽样质检。

    为什么需要它：长文全文质检耗时不可控（尤其接 AI 时）。超时后如果直接判失败，
    任务会卡死；如果直接放行，质量失控。抽样是第三条路：**拿到有代表性的一手判断，
    并明确标记「这是抽样结论」**，让下游知道可信度边界。

    区间按等距切分，保证覆盖全文首中尾而非只取开头。
    返回 ``{text, ranges: [(start, end)], sampled: bool}``。
    """
    content = text or ""
    if len(content) <= max_characters:
        return {"text": content, "ranges": [(0, len(content))], "sampled": False}

    max_ranges = max(1, int(max_ranges))
    per_range = max(200, max_characters // max_ranges)
    step = len(content) / max_ranges

    parts: List[str] = []
    ranges: List[tuple] = []
    for i in range(max_ranges):
        start = int(i * step)
        end = min(len(content), start + per_range)
        if start >= len(content):
            break
        ranges.append((start, end))
        parts.append(content[start:end])

    return {
        "text": "\n\n…\n\n".join(parts),
        "ranges": ranges,
        "sampled": True,
    }


def find_claim_offsets(text: str, claims: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """为每条断言补齐全文绝对偏移（抽样模式下会重新定位）。"""
    content = text or ""
    out = []
    cursor = 0
    for c in claims:
        snippet = str(c.get("text") or "")
        pos = content.find(snippet, cursor) if snippet else -1
        if pos < 0:
            pos = content.find(snippet) if snippet else -1
        if pos >= 0:
            cursor = pos + len(snippet)
        item = dict(c)
        item["offset"] = pos if pos >= 0 else int(c.get("offset") or 0)
        out.append(item)
    return out


def claims_to_dicts(claims: Optional[List[Dict[str, object]]]) -> List[Dict[str, object]]:
    """归一化输出（保持 JSON 可序列化）。

    证据核对环节会在断言上补 ``status`` / ``evidence`` / ``note`` 三个字段，
    这里一并带出 —— 运营需要知道「这条为什么没通过」，只给类型和文本没用。
    """
    out = []
    for c in claims or []:
        item = {
            "type": c.get("type"),
            "text": c.get("text"),
            "sentence": c.get("sentence"),
            "offset": c.get("offset"),
            "has_inline_source": bool(c.get("has_inline_source")),
        }
        if c.get("status") is not None:
            item["status"] = c.get("status")
        if c.get("note"):
            item["note"] = c.get("note")
        if c.get("evidence"):
            item["evidence"] = c.get("evidence")
        out.append(item)
    return out
