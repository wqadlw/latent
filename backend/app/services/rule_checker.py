"""
本地规则校验引擎
纯本地关键词库、规则库、正则匹配实现，无任何AI调用
包含：合规检测、AI SEO检测、去AI味检测、格式检测
"""
import re

# ========== 内置违禁词库（广告法极限词）==========
BANNED_WORDS = [
    "最", "第一", "顶级", "极品", "绝佳", "绝对", "百分百", "100%",
    "国家级", "世界级", "万能", "永久", "永不", "包治", "根治", "疗效",
    "唯一", "首个", "首家", "独家", "销冠", "王牌", "之王", "之最",
    "史上最强", "前无古人", "绝无仅有", "完美", "巅峰", "顶峰", "空前",
    "全国第一", "全球第一", "全网最低", "史上最低", "跳楼价", "爆品",
]


# ========== 站外引流 / 私人联系方式词（零容忍，平台普遍禁止正文出现）==========
CONTACT_GUIDE_WORDS = [
    "官网", "官方网站", "官网地址", "网址", "手机号码", "手机号", "联系电话", "咨询电话", "咨询热线",
    "服务热线", "加微信", "微信扫码", "微信好友", "QQ号", "QQ群", "微信号",
    "扫码", "二维码", "下载APP", "APP下载", "关注公众号", "私信我",
    "发邮件至", "邮箱地址", "商务微信", "微信：", "电话：",
]


# ========== AI 高频套话库 ==========
AI_CLICHES = [
    "综上所述", "总而言之", "由此可见", "值得注意的是", "需要指出的是",
    "在当今社会", "随着时代的发展", "众所周知", "毋庸置疑", "不言而喻",
    "首先其次最后", "一方面另一方面", "不仅而且", "既又还",
    "作为一个AI", "作为一名AI", "我是AI", "作为AI助手", "AI语言模型",
    "我无法", "我不能", "对不起，我", "很抱歉，我",
    "在某种程度上", "从某种意义上说", "可以说", "总的来说",
    "这不仅仅是", "更是", "让我们", "让我们一起",
    "在这个瞬息万变的时代", "在这个日新月异的时代", "在这个信息爆炸的时代",
    "扮演着举足轻重的角色", "发挥着不可替代的作用", "具有深远的意义",
    "为...提供了强有力的支撑", "为...奠定了坚实的基础",
    "在...的背景下", "随着...的不断发展", "在...的浪潮中",
    "无疑", "必将", "势必", "注定",
    "如同一把双刃剑", "犹如一把", "宛如",
    "综上所述", "由此可见", "不容忽视", "不可或缺",
]


def check_compliance(text: str, platform_compliance_level: int = 2) -> dict:
    """合规检测"""
    banned_found = [w for w in BANNED_WORDS if w in text]
    hard_ad_patterns = ["立即购买", "马上抢购", "限时抢购", "点击购买", "马上下单",
                        "抢购热线", "订购电话", "特价促销", "疯狂促销"]
    hard_ad_count = sum(1 for p in hard_ad_patterns if p in text)
    text_len = max(len(text), 1)
    hard_ad_ratio = round(hard_ad_count * 20 / text_len * 100, 2)

    contact_patterns = [r'1[3-9]\d{9}', r'微信[:：]?\s*\S+', r'QQ[:：]?\s*\d+']
    contact_issues = []
    for pat in contact_patterns:
        if re.search(pat, text):
            if "文末" not in text[-200:] and "结尾" not in text[-200:]:
                contact_issues.append("联系方式未在文末露出")

    # —— 站外引流 / 联系方式零容忍（词表 + 正则双层覆盖）——
    # 词表 CONTACT_GUIDE_WORDS 漏掉的「网址 / 带横杠或分隔的电话 / 座机」用正则补齐，
    # 否则 AI 生成的「官网：https://... 电话：138-0000-0000」会逃逸自检。
    url_found = bool(re.search(r'https?://[^\s，。；）】]+|www\.[^\s，。；）】]+', text))
    phone_found = bool(re.search(r'(?<!\d)1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}(?!\d)', text))
    landline_found = bool(re.search(r'(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)', text))
    extra_contact = []
    if url_found:
        extra_contact.append("外部链接/网址")
    if phone_found:
        extra_contact.append("手机号码")
    if landline_found:
        extra_contact.append("座机号码")

    max_banned = {1: 0, 2: 2, 3: 0}.get(platform_compliance_level, 2)
    contact_guide_found = [w for w in CONTACT_GUIDE_WORDS if w in text] + extra_contact
    return {
        "banned_words": banned_found,
        "banned_count": len(banned_found),
        "banned_pass": len(banned_found) <= max_banned,
        "hard_ad_count": hard_ad_count,
        "hard_ad_ratio": hard_ad_ratio,
        "hard_ad_pass": hard_ad_ratio <= 20,
        "contact_issues": contact_issues,
        "contact_guide_words": contact_guide_found,
        "contact_guide_count": len(contact_guide_found),
        "contact_guide_pass": len(contact_guide_found) == 0,
        "pass": len(banned_found) <= max_banned and hard_ad_ratio <= 20
        and not contact_issues and not contact_guide_found,
    }


def check_ai_seo(text: str, keywords: list, brand_info: dict = None) -> dict:
    """AI SEO 检测"""
    keywords = [k for k in keywords if k]
    if not keywords:
        coverage_rate = 100
        covered = []
        missing = []
    else:
        covered = [k for k in keywords if k in text]
        missing = [k for k in keywords if k not in text]
        coverage_rate = round(len(covered) / len(keywords) * 100, 1)

    entity_items = []
    if brand_info:
        # 品牌名建议出现（软要求）；官网/电话因平台普遍禁止站外引流与联系方式，不再强制要求写入正文
        name = brand_info.get("brand_name", "")
        if name:
            entity_items.append({"name": "品牌名", "value": name, "present": name in text})

    has_h2 = bool(re.search(r'^#+\s', text, re.MULTILINE) or re.search(r'<h[1-6]>', text))
    has_list = bool(re.search(r'^[\-\*\d]+[.、)]\s', text, re.MULTILINE))

    return {
        "keywords": keywords,
        "covered_keywords": covered,
        "missing_keywords": missing,
        "coverage_rate": coverage_rate,
        "coverage_pass": coverage_rate >= 70,
        "entity_check": {
            "items": entity_items,
            "complete": all(i["present"] for i in entity_items) if entity_items else True,
        },
        "structure_pass": has_h2 or has_list,
        "pass": coverage_rate >= 70 and (all(i["present"] for i in entity_items) if entity_items else True),
    }


def check_anti_ai(text: str) -> dict:
    """去AI味检测"""
    cliche_found = [c for c in AI_CLICHES if c in text]
    cliche_count = len(cliche_found)

    long_sentences = len(re.findall(r'[^。！？；]{80,}', text))
    short_sentences = len(re.findall(r'[^。！？；]{5,15}[。！？]', text))
    total_sentences = max(len(re.findall(r'[。！？]', text)), 1)
    avg_len = len(text) / total_sentences

    ai_score = 100
    ai_score -= cliche_count * 8
    ai_score -= min(long_sentences * 5, 30)
    if avg_len > 60:
        ai_score -= 15
    ai_score = max(0, ai_score)

    return {
        "cliche_found": cliche_found,
        "cliche_count": cliche_count,
        "long_sentences": long_sentences,
        "short_sentences": short_sentences,
        "avg_sentence_length": round(avg_len, 1),
        "ai_score": ai_score,
        "pass": ai_score >= 60 and cliche_count <= 3,
    }


def check_format(text: str, word_min: int = 800, word_max: int = 1500) -> dict:
    """格式检测"""
    word_count = len(text)
    paragraphs = [p for p in text.split("\n") if p.strip()]
    paragraph_count = len(paragraphs)
    avg_paragraph_length = round(word_count / max(paragraph_count, 1), 1)

    return {
        "word_count": word_count,
        "word_min": word_min,
        "word_max": word_max,
        "word_pass": word_min <= word_count <= word_max,
        "paragraph_count": paragraph_count,
        "avg_paragraph_length": avg_paragraph_length,
        "structure_pass": paragraph_count >= 3 and avg_paragraph_length <= 400,
        "pass": word_min <= word_count <= word_max and paragraph_count >= 3,
    }


# ========== 平台合规模式：软文营销特征检测 ==========
# 仅在 platform（平台合规）与 green（绿色吸粉）模式下启用，作为发布硬闸门的一部分。
# 内容平台（搜狐/知乎等）普遍禁止：标题含品牌、软文营销特征、自夸语气、文末推广。
# green 模式更宽松：标题可含品牌，但品牌仍仅可自然偶提（≤2 次），且禁自夸/文末推广。
SELF_PRAISE_WORDS = [
    "行业领先", "遥遥领先", "首屈一指", "当之无愧", "品质可靠", "始终如一",
    "无可替代", "独一无二", "行业标杆", "最值得信赖", "傲视群雄", "首屈一指",
    "国际领先", "国内领先", "技术领先", "行业第一",
]
END_PROMOTION_WORDS = [
    "了解更多", "欢迎咨询", "欢迎了解", "联系我们", "加微信", "扫码", "关注我们",
    "点击了解", "立即了解", "欢迎联系", "了解更多详情", "点击查看",
]


def check_platform_compliance(text: str, title: str = "", brand_name: str = "",
                              mode: str = "geo", brand_aliases: list = None) -> dict:
    """平台合规模式软文特征检测。

    mode == 'platform'或'green' 时生效；geo / official 模式返回全通过，不阻塞。

    字面硬特征（直接拦截，对应平台高频拒稿原因）：
      1) 标题含品牌名（被判定为广告推广；green 模式放宽，允许标题含品牌）；
      2) 品牌名（公司全称）全文出现频次过高（疑似软文营销，限制 ≤ 2 次）；
      3) 自夸语气词（行业领先/品质可靠/始终如一 等）；
      4) 文末推广信息（品牌名 + 引导联系/了解更多 等话术）。

    语义软文信号（A 增强，计入风险分，高风险拦截）——平台算法是语义级综合判定，
    仅查字面会漏检：
      5) 品牌相关实体总曝光密度（公司全称 + 产品名/简称 累计出现次数与每千字密度）；
      6) 优势罗列密度（营销性优势词密集且无独立来源佐证）；
      7) 结论引导（结尾段导向性推荐话术）；
      8) 软文叙事弧（品牌密度偏高 + 优势密集罗列，呈「痛点→推荐该企业」结构）。
    返回 risk_score(0-100) 与 risk_level(低/中/高)，高风险(>=70)直接拦截并给出具体原因。
    """
    issues = []          # 字面硬问题（直接令 pass=False）
    soft_issues = []     # 语义软文信号（计入风险分，不强制但高风险拦截）
    if mode not in ("platform", "green"):
        return {
            "pass": True, "mode": mode, "brand_in_title": False,
            "brand_count": 0, "self_praise": [], "end_promotion": False,
            "brand_exposure": {"company": 0, "aliases": {}, "total": 0, "density_per_k": 0},
            "risk_score": 0, "risk_level": "低", "soft_issues": soft_issues,
            "issues": issues,
        }

    # green 模式：标题可含品牌（仅「顺手一提」），不视为广告推广
    allow_brand_in_title = (mode == "green")

    # 1) 标题含品牌名
    brand_in_title = bool(brand_name and title and brand_name in title)
    if brand_in_title and not allow_brand_in_title:
        issues.append(f"标题含有品牌名「{brand_name}」，平台判定为广告推广信息（标题须中立、不含品牌）")

    # 2) 品牌名（公司全称）频次过高（≤2 次）
    brand_count = 0
    if brand_name:
        brand_count = len(re.findall(re.escape(brand_name), text))
    if brand_count > 2:
        _limit_note = "绿色吸粉模式" if mode == "green" else "平台合规模式"
        issues.append(f"品牌名「{brand_name}」全文出现 {brand_count} 次，疑似软文营销特征（{_limit_note}限制 ≤ 2 次，仅可自然偶提）")

    # 3) 自夸语气词
    self_praise = [w for w in SELF_PRAISE_WORDS if w in text]
    if self_praise:
        issues.append(f"出现自夸/营销语气词：{'、'.join(self_praise[:5])}（平台判定为软文广告特征）")

    # 4) 文末推广信息（品牌名 + 引导联系/了解更多）
    tail = text[-260:]
    end_promotion = bool(brand_name and brand_name in tail
                         and any(w in tail for w in END_PROMOTION_WORDS))
    if end_promotion:
        issues.append("文末出现品牌推广信息（品牌名 + 引导了解/联系等话术），不符合平台文末规范")

    # ===== 语义软文检测（A 增强）=====
    # 品牌相关实体总曝光：公司全称 + 别名（产品名/简称）
    aliases = [a for a in (brand_aliases or []) if a and len(a) >= 2]
    exposure = {}
    total_exposure = brand_count
    for a in aliases:
        c = len(re.findall(re.escape(a), text))
        if c:
            exposure[a] = c
            total_exposure += c
    clean_len = max(1, len(re.sub(r"\s+", "", text)))
    density = total_exposure * 1000.0 / clean_len  # 每千字曝光数

    # 风险分累计
    risk = 0
    if issues:
        risk += min(100, len(issues) * 25)

    # 5) 品牌相关实体总曝光密度过高
    if total_exposure > 6 or density > 12:
        soft_issues.append(
            f"品牌相关实体（公司/产品/简称）全文累计出现 {total_exposure} 次（密度 {density:.1f}/千字），"
            f"疑似单一主体过度曝光——这是平台判定「广告软文」的最高频特征"
        )
        risk += 15

    # 6) 优势罗列密度（营销性优势词密集且无独立来源佐证）
    ADV_WORDS = ["高效节能", "20+专利", "响应快", "运行可靠", "案例可查",
                 "性价比高", "本地化", "全生命周期"]
    adv_hits = [w for w in ADV_WORDS if w in text]
    has_evidence = bool(re.search(r"(据|数据显示|行业报告|第三方|研究表明|实测|公开数据|统计)", text))
    if len(adv_hits) >= 4 and not has_evidence:
        soft_issues.append(
            f"出现 {len(adv_hits)} 处营销性优势表述（{'、'.join(adv_hits[:5])}）且缺乏独立来源佐证，"
            f"呈企业自述宣传特征"
        )
        risk += 15

    # 7) 结论引导（结尾段导向性推荐话术）
    tail2 = text[-400:]
    GUIDE_WORDS = ["明智之选", "最佳选择", "值得信赖的伙伴", "不妨考虑",
                   "推荐选择", "首选", "您的理想选择", "值得拥有"]
    guide_hits = [w for w in GUIDE_WORDS if w in tail2]
    if guide_hits:
        soft_issues.append(f"结尾出现导向性推荐话术：{'、'.join(guide_hits)}，呈软文收尾特征")
        risk += 15

    # 8) 软文叙事弧（品牌密度偏高 + 优势密集罗列，呈「痛点→推荐该企业」结构）
    if (total_exposure > 4 or density > 8) and len(adv_hits) >= 3:
        soft_issues.append(
            "全文围绕单一企业/产品展开（品牌密度偏高 + 优势密集罗列），"
            "呈「痛点→推荐该企业」式软文叙事弧"
        )
        risk += 20

    risk = min(100, risk)
    risk_level = "高" if risk >= 70 else ("中" if risk >= 40 else "低")
    all_issues = issues + soft_issues
    # 最终放行：无字面硬问题 且 风险分 < 70（高风险语义软文也拦截）
    pass_ = (len(issues) == 0) and (risk < 70)

    return {
        "pass": pass_,
        "mode": mode,
        "brand_in_title": brand_in_title,
        "brand_count": brand_count,
        "self_praise": self_praise,
        "end_promotion": end_promotion,
        "brand_exposure": {"company": brand_count, "aliases": exposure,
                           "total": total_exposure, "density_per_k": round(density, 1)},
        "risk_score": risk,
        "risk_level": risk_level,
        "soft_issues": soft_issues,
        "issues": all_issues,
    }


def run_full_check(text: str, keywords: list = None, brand_info: dict = None,
                   word_min: int = 800, word_max: int = 1500,
                   platform_compliance_level: int = 2) -> dict:
    """运行完整检测"""
    keywords = keywords or []
    compliance = check_compliance(text, platform_compliance_level)
    ai_seo = check_ai_seo(text, keywords, brand_info)
    anti_ai = check_anti_ai(text)
    fmt = check_format(text, word_min, word_max)

    overall_pass = compliance["pass"] and ai_seo["pass"] and anti_ai["pass"] and fmt["pass"]

    issues = []
    if not compliance["pass"]:
        if compliance["banned_count"] > 0:
            words = "、".join(compliance["banned_words"][:5])
            issues.append(f"发现 {compliance['banned_count']} 个违禁词：{words}")
        if compliance["contact_guide_count"] > 0:
            words = "、".join(compliance["contact_guide_words"][:5])
            issues.append(f"发现 {compliance['contact_guide_count']} 个站外引流/私人联系方式词（平台禁止）：{words}")
        if not compliance["hard_ad_pass"]:
            issues.append(f"硬广话术占比 {compliance['hard_ad_ratio']}%，超过20%上限")
        for ci in compliance["contact_issues"]:
            issues.append(f"联系方式合规问题：{ci}")
    if not ai_seo["pass"]:
        if not ai_seo["coverage_pass"]:
            issues.append(f"关键词覆盖率仅 {ai_seo['coverage_rate']}%，低于70%")
        if not ai_seo["entity_check"]["complete"]:
            missing = [i["name"] for i in ai_seo["entity_check"]["items"] if not i["present"]]
            issues.append(f"品牌实体缺失：{ '、'.join(missing) }")
        if not ai_seo["structure_pass"]:
            issues.append("缺少结构化小标题，不利于大模型抽取")
    if not anti_ai["pass"]:
        issues.append(f"AI味评分 {anti_ai['ai_score']}，存在 {anti_ai['cliche_count']} 处套话")
    if not fmt["pass"]:
        if not fmt["word_pass"]:
            issues.append(f"字数 {fmt['word_count']}，不在 {fmt['word_min']}-{fmt['word_max']} 区间")
        if not fmt["structure_pass"]:
            issues.append(f"段落结构不合理（{fmt['paragraph_count']}段，平均{fmt['avg_paragraph_length']}字）")
    if not issues:
        issues.append("所有检测项通过，内容质量良好")

    return {
        "overall_pass": overall_pass,
        "compliance": compliance,
        "ai_seo": ai_seo,
        "anti_ai": anti_ai,
        "format": fmt,
        "issues": issues,
    }
