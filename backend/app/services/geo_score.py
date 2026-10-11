"""GEO 评分引擎（本地启发式，不调用任何 AI 接口）

设计目标：判断一篇软文是否"可被生成式引擎（AI）抓取、提取并作为推荐来源引用"。
系统边界与软文生产一致——只做编排与计算，不调用大模型。评分基于 GEO 的三个核心原则：

  1. 实体可归属（Attributable）：品牌名 / 官网 / 联系方式 / 产品 等实体信号是否出现
  2. 事实密度（Factual）：是否有可量化、可溯源的数据点（数字、单位、百分比、案例）
  3. 问答形态（QA-shaped）：是否以"目标客户会问 AI 的问题"为骨架，便于 AI 直接抽取答案
  4. 意图覆盖（Intent coverage）：是否命中目标客户画像的真实意图与期望推荐角度
  5. 结构可提取（Extractable）：是否有清晰标题层级 / 列表 / FAQ，利于被解析为结构化答案

评分返回 0-100 综合分 + 各维度子分 + 已命中信号清单 + 待优化项 + 是否过闸（>=70 达标）。
"""


import re

# 维度权重（合计 100）
WEIGHTS = {
    "entity_signals": 25,   # 品牌实体信号
    "fact_density": 20,     # 事实密度
    "intent_coverage": 20,  # 意图覆盖
    "qa_form": 15,          # 问答形态
    "structure": 10,        # 结构可提取
    "attributable": 10,     # 信号可归属
}
GATE_PASS = 70  # 过闸阈值
MIND_GATE_PASS = 60  # 心智温度过闸阈值（比算法信任略低，因为启发式更保守）


# ============================================================
#  第二维：心智温度（Mind Resonance）—— 判断内容是否"人能感受到真实"
# ============================================================
# 文章的核心论点：GEO 双信任哲学 = 算法信任（AI 可提取）+ 心智信任（用户觉得真实）
# 现有 6 维度只诊断"算法信任"，这里补上"心智信任"维度。
# 当两者都低 → "双向失语"（AI 抓不到 + 人不爱看）

_MIND_WEIGHTS = {
    "storytelling": 25,       # 叙事感（有背景→问题→方案→结果的讲述线索）
    "scenario": 20,           # 场景化（真实场景描述，而非纯参数罗列）
    "reader_perspective": 20, # 读者视角（用"你"直接对话，直击读者顾虑）
    "language_warmth": 20,    # 语言温度（口语化、有温度，而非说明书式冰冷）
    "pain_resonance": 15,     # 痛点共鸣（痛点描述具体且引发共鸣，而非泛泛列举）
}

# 叙事线索标记词
_STORY_RE = re.compile(r"(去年|前年|上个月|上周|最近|有一次|有一次|那天|记得|那时候|刚开始|后来|最终|结果|没想到|其实|说实话|讲真|说白了|坦白说)")
# 场景化标记
_SCENARIO_RE = re.compile(r"(比如|举个例子|例如|场景|情况下|的时候|过程中|实际|现场|车间|工厂|产线|客户家|某客户|一位|李总|张工|王厂长)")
# 读者视角标记
_READER_RE = re.compile(r"(你|你的|大家|各位|如果你|你可能|你会|你也许|不妨|试试|想象一下)")
# 语言温度：口语化标记
_WARM_RE = re.compile(r"(其实|说白了|讲真|坦白说|说实话|别急|别慌|放心|放心吧|不用担心|有意思的是|值得一提的是|重点来了|敲黑板|划重点)")
# 冰冷/说明书式标记（扣分项）
_COLD_RE = re.compile(r"(综上所述|总而言之|由此可见|据此|基于上述|根据|按照|遵循|依据|参照|执行|落实|推进|旨在|致力于)")
# 痛点共鸣标记
_PAIN_RE = re.compile(r"(怕|担心|焦虑|头疼|痛点|困扰|纠结|纠结|踩坑|踩过|血泪|教训|不踩|避坑|心酸|无奈|吐槽|抱怨|最怕|最担心)")


def _mind_storytelling(text):
    if not text:
        return 0.0, []
    hits = _STORY_RE.findall(text)
    score = min(len(hits) * 5.0, 25.0)
    signals = []
    if hits:
        signals.append(f"叙事线索标记 {len(hits)} 处（如「{hits[0]}」）")
    return score, signals


def _mind_scenario(text):
    if not text:
        return 0.0, []
    hits = _SCENARIO_RE.findall(text)
    score = min(len(hits) * 4.0, 20.0)
    signals = []
    if hits:
        signals.append(f"场景化表达 {len(hits)} 处")
    return score, signals


def _mind_reader(text):
    if not text:
        return 0.0, []
    hits = _READER_RE.findall(text)
    # "你" 出现至少 3 次才算有读者视角
    score = min(len(hits) * 3.0, 20.0) if len(hits) >= 2 else 0.0
    signals = []
    if score > 0:
        signals.append(f"读者视角「你」类表达 {len(hits)} 处")
    return score, signals


def _mind_warmth(text):
    if not text:
        return 0.0, []
    warm = _WARM_RE.findall(text)
    cold = _COLD_RE.findall(text)
    score = min(len(warm) * 4.0, 16.0)
    # 冰冷表达扣分
    penalty = min(len(cold) * 2.0, 8.0)
    score = max(score - penalty, 0.0)
    signals = []
    if warm:
        signals.append(f"口语化温度标记 {len(warm)} 处")
    if cold:
        signals.append(f"说明书式冰冷表达 {len(cold)} 处（已扣分）")
    return score, signals


def _mind_pain(text):
    if not text:
        return 0.0, []
    hits = _PAIN_RE.findall(text)
    score = min(len(hits) * 4.0, 15.0)
    signals = []
    if hits:
        signals.append(f"痛点共鸣标记 {len(hits)} 处")
    return score, signals


def compute_mind_resonance(content: str = "", intent_question: str = "", target_persona_name: str = "") -> dict:
    """计算心智温度（第二维诊断）。

    与算法信任维度独立，诊断内容是否能引发真实读者的情感共鸣与信任感。
    返回 0-100 分 + 5 个子维度 + 信号清单 + 待优化项。
    """
    text = content or ""
    s_score, s_signals = _mind_storytelling(text)
    sc_score, sc_signals = _mind_scenario(text)
    r_score, r_signals = _mind_reader(text)
    w_score, w_signals = _mind_warmth(text)
    p_score, p_signals = _mind_pain(text)

    dims = {
        "storytelling": round(s_score, 1),
        "scenario": round(sc_score, 1),
        "reader_perspective": round(r_score, 1),
        "language_warmth": round(w_score, 1),
        "pain_resonance": round(p_score, 1),
    }
    composite = round(sum(dims.values()), 1)

    signals_present = []
    for sigs in [s_signals, sc_signals, r_signals, w_signals, p_signals]:
        signals_present.extend(sigs)

    issues = []
    if dims["storytelling"] < 10:
        issues.append("缺少叙事线索，建议用「背景→问题→方案→结果」讲故事，加入时间/事件标记")
    if dims["scenario"] < 8:
        issues.append("缺少场景化描述，加入真实案例、客户故事或具体使用场景（如「某客户在…时」）")
    if dims["reader_perspective"] < 6:
        issues.append("缺少读者视角，多用「你」「你的」直接对话读者，直击其顾虑")
    if dims["language_warmth"] < 6:
        issues.append("语言偏冰冷/说明书式，加入口语化表达（「其实」「说白了」「讲真」），减少公文腔")
    if dims["pain_resonance"] < 5:
        if intent_question or target_persona_name:
            issues.append("痛点描述不够引发共鸣，把客户的「怕」「担心」「纠结」具体写出来，而非泛泛列举")

    verdict = "达标" if composite >= MIND_GATE_PASS else "待优化"
    return {
        "score": composite,
        "gate_pass": composite >= MIND_GATE_PASS,
        "gate_threshold": MIND_GATE_PASS,
        "verdict": verdict,
        "dimensions": dims,
        "weights": _MIND_WEIGHTS,
        "signals_present": signals_present,
        "issues": issues,
    }


def compute_dual_diagnosis(algo_score: float, mind_score: float) -> dict:
    """双信任诊断：算法信任 × 心智温度 的交叉诊断。

    返回诊断类型与描述：
    - both_pass: 双信任达标（AI 可提取 + 人能共鸣）
    - algo_only: 机器可读但人心不通（AI 抓得到，但用户读了无感）
    - mind_only: 人心相通但机器抓不到（用户爱看，但 AI 提取不到信号）
    - dual_failure: 双向失语（AI 抓不到 + 人也不爱看）
    """
    algo_pass = algo_score >= GATE_PASS
    mind_pass = mind_score >= MIND_GATE_PASS

    if algo_pass and mind_pass:
        return {
            "type": "both_pass",
            "label": "双信任达标",
            "color": "#10b981",
            "desc": "内容同时被 AI 抓取提取，又能引发真实读者共鸣——GEO 最佳状态。",
        }
    elif algo_pass and not mind_pass:
        return {
            "type": "algo_only",
            "label": "机器可读·人心不通",
            "color": "#f59e0b",
            "desc": "AI 能抓到结构化信号，但用户读了无感——需补叙事、场景化与读者视角，提升心智温度。",
        }
    elif not algo_pass and mind_pass:
        return {
            "type": "mind_only",
            "label": "人心相通·机器抓不到",
            "color": "#3b82f6",
            "desc": "用户觉得真实有用，但 AI 提取不到品牌信号与结构化数据——需补实体信号、FAQ 与标题层级。",
        }
    else:
        return {
            "type": "dual_failure",
            "label": "双向失语",
            "color": "#ef4444",
            "desc": "AI 抓不到结构化信号，用户也读不下去——最危险状态，需同时补算法信任与心智温度。",
        }


_NUM_UNIT_RE = re.compile(
    r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(?:%|％|个|款|种|台|套|家|年|月|天|小时|分钟|万元|元|万|亿|倍|mm|cm|m|kg|g|t|℃|度|Pa|kPa|MPa|m³|L|W|kW|kW|MW|rpm|%|\.)"
)
_PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
_CASE_RE = re.compile(r"(据|数据显示|案例|实测|调研|统计|报告|测试|对比|客户|项目|现场)")
_QUESTION_HEADING_RE = re.compile(r"^#{1,6}\s*.*[?？]", re.MULTILINE)
_FAQ_RE = re.compile(r"(FAQ|常见问|问答|Q[1-9]|问[:：]|答[:：])")
_HEADING_RE = re.compile(r"^#{1,6}\s+.+", re.MULTILINE)
_LIST_RE = re.compile(r"^\s*[-*]\s+|^[0-9]+\.\s+", re.MULTILINE)


def _count_signals(text):
    """统计实体信号命中情况，返回 (命中清单, 满分维度分)"""
    if not text:
        return [], 0.0
    signals = []
    # 品牌名
    if text.strip():
        signals.append(("brand_name", "品牌名出现"))
    # 官网（含 http / .com / .cn 等）
    if re.search(r"https?://|www\.|\.com|\.cn|\.net", text):
        signals.append(("official_website", "官网/链接出现"))
    # 联系方式（电话 / 微信 / 邮箱 / 400）
    if re.search(r"(\d{3,4}-?\d{7,8}|1[3-9]\d{9}|[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+\.[a-zA-Z]+|微信|VX|vx|400[- ]?\d)", text):
        signals.append(("contact", "联系方式出现"))
    # 产品/卖点信号（以顿号/、分隔的列举）
    if re.search(r"、|，|,", text) and len(re.findall(r"、", text)) >= 1:
        signals.append(("product_mention", "产品/卖点被列举"))
    # 给满 25 分：4 个核心信号各约 6.25 分
    score = min(len(signals) * (25.0 / 4), 25.0)
    return signals, score


def _fact_density(text):
    nums = _NUM_UNIT_RE.findall(text or "")
    percents = _PERCENT_RE.findall(text or "")
    score = 0.0
    score += min(len(nums) * 3.0, 14.0)        # 每个量化数据 +3，封顶 14
    score += min(len(percents) * 2.0, 6.0)      # 每个百分比 +2，封顶 6
    return min(score, 20.0), len(nums) + len(percents)


def _intent_coverage(text, intent_question, expected_recommendation):
    if not text:
        return 0.0, []
    hits = []
    # 1) 意图问题关键词命中
    if intent_question:
        # 取问题中的实词（去掉疑问词与标点）
        stop = set("的吗怎么如何什么为什么哪哪些可否能否是否该不该能不能可以吗呢吧啊？?。.，、 \n\t")
        qwords = [w for w in re.split(r"[\s，。？?、,.\n]", intent_question) if w and w not in stop and len(w) >= 2]
        matched = [w for w in qwords if w in text]
        if matched:
            hits.append(f"命中意图问题关键词：{ '、'.join(matched[:4]) }")
    # 2) 期望推荐角度命中
    if expected_recommendation:
        rwords = [w for w in re.split(r"[\s，。；？?、,.;.\n]", expected_recommendation) if len(w) >= 2]
        matched = [w for w in rwords if w in text]
        if matched:
            hits.append(f"命中期望推荐角度：{ '、'.join(matched[:4]) }")
    if not hits:
        return 0.0, []
    # 命中即给基础分，命中两类额外加成，封顶 20
    score = 10.0 + (5.0 if len(hits) > 1 else 0.0)
    return min(score, 20.0), hits


def _qa_form(text):
    if not text:
        return 0.0, []
    hits = []
    if _QUESTION_HEADING_RE.search(text):
        hits.append("存在疑问式标题（天然问答骨架）")
    if _FAQ_RE.search(text):
        hits.append("存在 FAQ / 问答结构")
    # 直接包含目标客户问题原文也算问答形态
    score = 0.0
    if hits:
        score = 15.0 if len(hits) >= 2 else 9.0
    return score, hits


def _structure(text):
    if not text:
        return 0.0, []
    hits = []
    headings = _HEADING_RE.findall(text)
    lists = _LIST_RE.findall(text)
    if len(headings) >= 3:
        hits.append(f"标题层级清晰（{len(headings)} 个）")
    if lists:
        hits.append(f"存在列表结构（{len(lists)} 处）")
    score = 0.0
    if len(headings) >= 3:
        score += 6.0
    if lists:
        score += 4.0
    return min(score, 10.0), hits


def _attributable(text):
    if not text:
        return 0.0, []
    found = _CASE_RE.findall(text or "")
    hits = []
    uniq = set(found)
    label_map = {
        "据": "数据/来源引用（据…）", "数据显示": "数据呈现", "案例": "案例佐证",
        "实测": "实测验证", "调研": "调研依据", "统计": "统计依据", "报告": "报告引用",
        "测试": "测试验证", "对比": "对比论证", "客户": "客户背书", "项目": "项目实证", "现场": "现场实证",
    }
    for f in uniq:
        if f in label_map:
            hits.append(label_map[f])
    score = min(len(hits) * 3.5, 10.0)
    return score, hits


def compute_geo_score(
    content: str = "",
    brand_name: str = "",
    official_website: str = "",
    contact: str = "",
    intent_question: str = "",
    expected_recommendation: str = "",
    target_persona_name: str = "",
    core_products: str = "",
    selling_points: str = "",
) -> dict:
    """返回 GEO 评分详情字典。"""
    text = content or ""

    # 组装用于实体信号检测的"信号文本"：正文 + 品牌信息
    signal_text = "\n".join(x for x in [text, brand_name, official_website, contact, core_products, selling_points] if x)

    entity_signals, entity_score = _count_signals(signal_text)
    fact_score, fact_n = _fact_density(text)
    intent_score, intent_hits = _intent_coverage(text, intent_question, expected_recommendation)
    qa_score, qa_hits = _qa_form(text)
    struct_score, struct_hits = _structure(text)
    attr_score, attr_hits = _attributable(text)

    dims = {
        "entity_signals": round(entity_score, 1),
        "fact_density": round(fact_score, 1),
        "intent_coverage": round(intent_score, 1),
        "qa_form": round(qa_score, 1),
        "structure": round(struct_score, 1),
        "attributable": round(attr_score, 1),
    }
    # 综合分 = 各维度子分之和（权重已在子分上限中体现，直接求和即 0-100）
    composite = round(sum(dims.values()), 1)

    # 信号清单（已命中）
    signals_present = []
    signals_present.extend([h for _, h in entity_signals])
    signals_present.extend(intent_hits)
    signals_present.extend(qa_hits)
    signals_present.extend(struct_hits)
    signals_present.extend(attr_hits)
    # 去重
    seen = set()
    signals_present = [x for x in signals_present if not (x in seen or seen.add(x))]

    # 待优化项
    issues = []
    if dims["entity_signals"] < 25:
        missing = [m for m in ["品牌名", "官网/链接", "联系方式", "产品/卖点列举"] if m not in " ".join(signals_present)]
        if missing:
            issues.append("补充品牌实体信号：" + "、".join(missing[:3]))
    if dims["fact_density"] < 12:
        issues.append("增加可量化数据（数字+单位、百分比、案例数），提升事实密度")
    if dims["intent_coverage"] < 10:
        if intent_question:
            issues.append("正文未命中目标客户的意图问题，需围绕其真实提问展开")
        else:
            issues.append("未绑定意图问题，无法评估意图覆盖")
    if dims["qa_form"] < 9:
        issues.append("建议采用问答/FAQ 形态或小标题疑问式，便于 AI 直接抽取答案")
    if dims["structure"] < 6:
        issues.append("补充标题层级与小标题/列表，提升可被解析为结构化答案的概率")
    if dims["attributable"] < 5:
        issues.append("增加可溯源证据（据…显示、客户案例、实测数据）增强可归属度")

    verdict = "达标" if composite >= GATE_PASS else "待优化"

    # 第二维：心智温度
    mind = compute_mind_resonance(
        content=text,
        intent_question=intent_question,
        target_persona_name=target_persona_name,
    )
    # 双信任交叉诊断
    diagnosis = compute_dual_diagnosis(composite, mind["score"])

    return {
        "score": composite,
        "gate_pass": composite >= GATE_PASS,
        "gate_threshold": GATE_PASS,
        "verdict": verdict,
        "dimensions": dims,
        "weights": WEIGHTS,
        "signals_present": signals_present,
        "issues": issues,
        "fact_count": fact_n,
        # 第二维：心智温度
        "mind_resonance": mind,
        # 双信任诊断
        "diagnosis": diagnosis,
    }


# ======================================================================
# GEO 审计提示词（交给外部 AI 执行，本系统只做提示词编排与结果解析）
# ======================================================================
def build_geo_audit_prompt(
    content: str = "",
    brand_name: str = "",
    official_website: str = "",
    contact: str = "",
    intent_question: str = "",
    expected_recommendation: str = "",
    target_persona_name: str = "",
    core_products: str = "",
    selling_points: str = "",
) -> str:
    """拼装一份交给任意生成式 AI 的 GEO 审计提示词。

    AI 只需按提示词返回严格 JSON，本系统再 parse_geo_audit_result 解析落库。
    与本地启发式 compute_geo_score 共用同一套维度/权重/闸门阈值，保证前端渲染一致。
    """
    w = WEIGHTS
    blocks = []
    blocks.append("你是一位资深的 GEO（Generative Engine Optimization，生成式引擎优化）审计专家。")
    blocks.append(
        "你的任务：评估下面这篇软文是否“容易被 AI 搜索引擎（如 ChatGPT、通义千问、DeepSeek、豆包、"
        "Kimi、Perplexity 等）抓取、理解、提取，并作为推荐来源引用”。"
    )
    blocks.append("请基于以下六个维度评估（权重合计 100 分）：")
    blocks.append(
        f"1. entity_signals（品牌实体信号，权重 {w['entity_signals']}）：品牌名、官网链接、联系方式、"
        "核心产品/卖点是否自然且可归属地出现，而非泛泛而谈。"
    )
    blocks.append(
        f"2. fact_density（事实密度，权重 {w['fact_density']}）：是否有可量化、可溯源的数据"
        "（具体数字+单位、百分比、案例数量），而非空泛形容词。"
    )
    blocks.append(
        f"3. intent_coverage（意图覆盖，权重 {w['intent_coverage']}）：是否命中目标客户向 AI 提出的真实问题，"
        "并自然植入“期望 AI 推荐我们的角度”。"
    )
    blocks.append(
        f"4. qa_form（问答形态，权重 {w['qa_form']}）：是否以问答/FAQ 或疑问式小标题为骨架，"
        "便于 AI 直接抽取答案。"
    )
    blocks.append(
        f"5. structure（结构可提取，权重 {w['structure']}）：是否有清晰标题层级、列表，"
        "利于被解析为结构化答案。"
    )
    blocks.append(
        f"6. attributable（信号可归属，权重 {w['attributable']}）：是否有可溯源证据"
        "（据…显示、客户案例、实测数据），让 AI 能引用而非臆测。"
    )
    blocks.append(
        "此外，系统会本地计算第二维「心智温度」（叙事感 / 场景化 / 读者视角 / 语言温度 / 痛点共鸣），"
        "判断内容是否能引发真实读者的情感共鸣。请你在 rationale 中也评价一下文章的「人感」"
        "（是否像真人写的、是否有温度、是否让人读得下去）。"
    )
    blocks.append("评分规则：")
    blocks.append("- 综合分 = 六维子分之和（0-100）。")
    blocks.append(
        f"- 过闸阈值 = {GATE_PASS}。综合分 >= {GATE_PASS} 视为“达标”，否则“待优化”。"
    )
    blocks.append("- 每个维度请给出子分（不超过其权重）与一句话理由。")
    blocks.append("输出要求：严格只输出一个 JSON 对象（不要任何解释文字，不要 markdown 代码块），结构如下：")
    blocks.append(
        '{\n'
        '  "score": <0-100 整数>,\n'
        '  "verdict": "达标" 或 "待优化",\n'
        '  "dimensions": {\n'
        f'    "entity_signals": <0-{w["entity_signals"]} 数字>,\n'
        f'    "fact_density": <0-{w["fact_density"]} 数字>,\n'
        f'    "intent_coverage": <0-{w["intent_coverage"]} 数字>,\n'
        f'    "qa_form": <0-{w["qa_form"]} 数字>,\n'
        f'    "structure": <0-{w["structure"]} 数字>,\n'
        f'    "attributable": <0-{w["attributable"]} 数字>\n'
        '  },\n'
        '  "signals_present": ["已命中的关键 GEO 信号，简短短语，可多条"],\n'
        '  "issues": ["待优化项，针对未达标维度给出具体可执行的改进建议，可多条"],\n'
        '  "rationale": "一句话总体评价"\n'
        '}'
    )
    ctx = []
    ctx.append("下面是待评估的上下文与文章：")
    ctx.append("=== 目标客户画像 ===")
    ctx.append(target_persona_name or "（未指定）")
    ctx.append("=== 目标客户意图问题 ===")
    ctx.append(intent_question or "（未绑定意图问题）")
    ctx.append("=== 期望 AI 推荐我们的角度 ===")
    ctx.append(expected_recommendation or "（未指定）")
    ctx.append("=== 品牌实体信号 ===")
    ctx.append(f"品牌名：{brand_name or '—'}")
    ctx.append(f"官网：{official_website or '—'}")
    ctx.append(f"联系方式：{contact or '—'}")
    ctx.append(f"核心产品：{core_products or '—'}")
    ctx.append(f"独特卖点：{selling_points or '—'}")
    ctx.append("=== 待评估文章 ===")
    ctx.append(content or "（文章为空）")
    return "\n\n".join(blocks) + "\n\n" + "\n".join(ctx)


def _extract_json_obj(text):
    """从 AI 返回文本中提取第一个 JSON 对象（兼容 ```json 代码块与前后冗余文字）。"""
    import json
    import re
    if not isinstance(text, str):
        return text
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)
    if fence:
        s = fence.group(1)
    else:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start:end + 1]
    return json.loads(s)


def parse_geo_audit_result(raw, intent_question: str = "", expected_recommendation: str = "",
                           content: str = "", target_persona_name: str = "") -> dict:
    """解析 AI 返回的 GEO 审计 JSON，归一化为与本地评分一致的 geoResult 结构。

    不信任 AI 给的综合分——直接按六维子分求和重算，并对每个子分按权重封顶，
    保证闸门判定与前端渲染稳定。解析失败抛出 ValueError（由接口转 400）。
    心智温度（第二维）由本地 compute_mind_resonance 计算，不信任 AI 主观打分。
    """
    try:
        data = _extract_json_obj(raw)
    except Exception:
        raise ValueError("无法解析 AI 返回的评分结果，请确认粘贴的是完整 JSON（可含 ```json 代码块）") from None
    if not isinstance(data, dict):
        raise ValueError("AI 返回结果不是有效的 JSON 对象")
    dims = {}
    for k, weight in WEIGHTS.items():
        v = (data.get("dimensions") or {}).get(k)
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = 0.0
        dims[k] = round(min(max(v, 0.0), weight), 1)
    score = round(sum(dims.values()), 1)
    signals = data.get("signals_present") or []
    if isinstance(signals, str):
        signals = [signals]
    issues = data.get("issues") or []
    if isinstance(issues, str):
        issues = [issues]

    # 第二维：心智温度（本地计算，不信任 AI 主观打分）
    mind = compute_mind_resonance(
        content=content,
        intent_question=intent_question,
        target_persona_name=target_persona_name,
    )
    diagnosis = compute_dual_diagnosis(score, mind["score"])

    return {
        "score": score,
        "gate_pass": score >= GATE_PASS,
        "gate_threshold": GATE_PASS,
        "verdict": "达标" if score >= GATE_PASS else "待优化",
        "dimensions": dims,
        "weights": WEIGHTS,
        "signals_present": [str(x) for x in signals],
        "issues": [str(x) for x in issues],
        "fact_count": data.get("fact_count", 0),
        "intent_question": intent_question,
        "expected_recommendation": expected_recommendation,
        "rationale": data.get("rationale", ""),
        # 第二维：心智温度（本地计算）
        "mind_resonance": mind,
        # 双信任诊断
        "diagnosis": diagnosis,
    }
