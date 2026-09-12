"""
提示词渲染引擎
把提示词模板里的 {xxx} 占位符替换成真实上下文
"""
from ..constants import SUPPORTED_RENDER_VARIABLES as BUILTIN_VARIABLES
import re
import json
from datetime import datetime
from ..utils import to_dict, parse_json, parse_ids, safe_format


# ============================================================
#  三发布模式：发布模式 → 品牌策略 / 目标定位
#  - geo      ：强品牌 / GEO 模式（自建站、AI 抓取）。品牌突出、公司为主体、品牌名多次出现。
#  - platform ：平台合规模式（搜狐/知乎等内容平台）。中立、有价值、品牌自然植入≤2次、
#               标题无品牌、不自我夸赞、不引导联系、带 AIGC 声明。
#  - green    ：绿色吸粉模式（自媒体）。纯干货/趣味文章吸引阅读涨粉、提升账号权重与信用分，
#               不带软文营销，品牌仅可自然偶提≤2次。
#  官网/自建站平台 → output_format="mdx"，按 OFFICIAL_MDX_PROMPT 模板产出可复制 MDX 代码。
# ============================================================
def get_brand_policy(mode: str = "geo") -> str:
    """按发布模式返回「品牌策略」文本，供提示词与背景资料引用。"""
    if mode == "green":
        return (
            "绿色吸粉模式：写「纯自媒体干货 / 趣味 / 行业洞察」文章，目标是吸引阅读、涨粉、"
            "提升账号权重与信用分，不夹带任何软文营销与硬广。"
            "品牌（示例品牌）仅可在文中「自然、偶然、顺带」地提一嘴，全文出现不超过 2 次，"
            "且绝不能为了营销而提；不自我夸赞、不写口号式标语、不引导联系（禁「了解/欢迎/联系/加微信/扫码」），"
            "不出现任何联系方式与站外引流词。文章以读者价值为先，品牌只是「彩蛋式」轻提及。"
            "去软文化铁律：以行业/第三方视角切入，用公开通用行业知识写作；禁止「痛点→只有它能解决→推荐」的套路叙事弧；"
            "若提及品牌，仅作为「众多可选方案之一」被顺带比较，绝不以其为全文主角；"
            "至少嵌入 2 处可查证的独立行业事实，稀释品牌浓度，让文章读起来像真人创作而非企业宣传。"
        )
    if mode == "platform":
        return (
            "平台合规模式：以中立、有干货价值的第三方视角服务读者，不突出品牌、不做软文营销。"
            "品牌名仅在必要时自然提及，全文出现不超过 2 次；标题严禁出现品牌名。"
            "不自我夸赞、不引导联系（禁止「了解更多/欢迎/联系/加微信/扫码」式话术）、"
            "不写口号式标语（如「品质可靠，始终如一」「行业领先」）。"
            "若需提及品牌，仅以中性事实陈述（如技术/案例），并文末标注 AIGC 声明"
            "「本文由 AI 辅助创作」。"
            "去软文化铁律：以行业通用知识和公开数据切入，把品牌只当作「众多可选方案之一」被顺带提及，"
            "禁止以单一企业/产品为叙事主线，禁止「先讲痛点→只有它能解决→推荐购买」的软文套路弧；"
            "优势表述须有独立来源佐证（如行业报告/实测数据），不得密集堆砌企业自述式卖点；"
            "至少融入 2 处可查证的独立行业事实，让文章读起来像行业媒体专栏而非企业宣传稿。"
        )
    return (
        "品牌宣传铁律：文章始终以「品牌所属公司」为主体——不是只提产品名，"
        "而是要宣传公司的实力、本地化全生命周期服务与核心优势；"
        "品牌名（公司全称）全文至少出现 3 次、自然融入上下文、不堆砌；"
        "严禁口号式标语（如「品质可靠，始终如一」）、严禁出现任何站外引流/私人联系方式词。"
    )


def get_mode_goal(mode: str = "geo") -> str:
    """按发布模式返回「文章目标」文本，供背景资料与系统提示词引用。"""
    if mode == "green":
        return (
            "写一篇「读者爱看、能涨粉、提升账号权重与信用分」的自媒体文章：选题轻巧、"
            "有真料或真洞察、有互动感，让用户在信息流里愿意点开、读完、点赞转发。"
            "不带软文营销，不卖货不引流；品牌（示例品牌）只在合适处「顺手一提」，"
            "绝不喧宾夺主。目标是内容资产沉淀与账号成长，而非即时转化。"
            "写法：以读者兴趣为锚，用行业洞察/实用干货撑起全文，品牌仅作彩蛋式轻提及，绝不当主角。"
        )
    if mode == "platform":
        return (
            "写一篇「中立、专业、对读者有真实帮助」的行业干货文章，用于发布到内容平台（如搜狐号）。"
            "须严格符合平台发文规范：不夹带广告推广、不做软文营销、不出现联系方式、标题不含品牌名、"
            "文末标注 AIGC 声明。目标是被读者读完并收藏，而非为品牌曝光。"
            "写法上：用第三方/行业视角，从公开通用知识讲起，把品牌只作为可选方案之一顺带提及；"
            "避免「通篇围绕一家企业、结尾导向推荐」的软文结构，确保内容对不关心该品牌的读者也有价值。"
        )
    return (
        "写一篇「既有干货价值、又能被豆包/文心/DeepSeek 等 AI 在用户提问时检索并推荐引用」的专业软文——"
        "让目标客户在问 AI 时，AI 会自然推荐并引用我们品牌（公司为主体、品牌信号密集、事实可溯源）。"
    )


# ============================================================
#  官网 / 自建站（Astro）MDX 自动化发布
#  官网 https://www.example.com，栏目：案例·新闻 > 客户案例 / 产品应用 / 行业资讯
#  选官网发布时，按本模板产出可直接复制的 MDX 代码块 + 图片文件名提示。
# ============================================================
OFFICIAL_SITE_URL = "https://www.example.com"

OFFICIAL_MDX_PROMPT = """你是「示例品牌科技有限公司」官网内容编辑，负责为官网（{official_site_url}）「案例·新闻」板块撰写并产出可直接粘贴的 MDX 文章代码。官网基于 Astro 构建，文章配图统一存放于 src/assets/news/industry/xingwen/ 目录。

# 任务
围绕主题「{subject}」，结合品牌 {brand_name}（核心产品：{core_products}；核心优势：{selling_points}）与以下背景资料，产出一篇「行业资讯（IndustryNews）」类技术文章：
{knowledge_content}

# 生成规则
1. 直接输出 MDX 内容本身：不要任何代码围栏（严禁 ```mdx 包裹）、不要任何解释性文字、不要前后废话，直接以 --- frontmatter 开头。
2. 严禁使用 <Image /> 等任何 Astro / MDX 组件；图片仅通过 cover frontmatter 字段声明路径，正文不内嵌组件。
3. 严禁使用任何 emoji / 表情符号；全文严肃、专业、工业风。
4. 文章结构严格如下 6 段（用二级标题 ## 分隔）：
   - ## 现状与痛点
   - ## 核心挑战
   - ## 解决方案（突出 {brand_name} 的 {core_products} 如何解决问题）
   - ## 数据对比（4 列表格：| 指标维度 | 传统方案 | 示例品牌方案 | 优化成果 |）
   - ## 专家观点（用 > 引用块写一句金句 / 行业判断）
   - ## 结语
5. 数据对比表至少 3 行真实可比数据；「优化成果」列须给出量化提升（如节能 X%、噪音 < X dB、效率提升 X%）。
6. 全文 800–1500 字，事实可溯源，不写口号式标语，不出现联系方式与任何站外引流词。
7. 文件名约定：cover 的英文 base 即为本 MDX 文件名与图片名（如 cover 用 dry-screw-pump-food-factory.jpg，则文件名为 dry-screw-pump-food-factory.mdx，封面图 xingwen/dry-screw-pump-food-factory.jpg，正文配图 xingwen/dry-screw-pump-food-factory-detail.jpg）。务必取一个清晰、可读的英文小写 + 连字符 base。

# Frontmatter 规则（必须置于 MDX 顶部，且为第一个内容）
---
title: "文章标题"
category: "IndustryNews"
publishDate: "YYYY-MM-DD"   # 在 2024-01-01 ~ 2026-12-31 之间取一个合理的近期日期
tags: ["标签1", "标签2", "标签3"]   # 3–5 个中文标签
cover: "@/assets/news/industry/xingwen/英文名.jpg"   # 英文小写 + 连字符 base，决定 .mdx 文件名与图片名
---

# 标准样例（仅作风格参考，不要照抄）
标题示例：「降本增效新标杆：为何示例品牌干式螺杆泵成为食品工厂升级首选？」
样例数据：示例产品系列干式螺杆真空泵，较传统水环泵节能 32%，运行噪音 < 70 dB，无废水排放、免维护周期更长。
"""

# 与品牌策略 / 目标定位并列，提供一个「可通过模式取用的 MDX 提示词」入口。
# official 模式（output_format=mdx）会注入本模板；其余模式返回空串。
def get_mdx_template(mode: str = "official") -> str:
    """返回官网 MDX 自动化提示词模板（含占位符），由调用方用上下文渲染。"""
    return OFFICIAL_MDX_PROMPT if mode == "official" else ""


def build_render_context(db, task, industry_id) -> dict:
    """构建提示词渲染上下文"""
    from ..models import (
        Industry, Platform, Account, Persona, Keyword, KnowledgeItem,
        BrandAsset, RuleLibrary, TargetPersona, IntentQuestion,
    )

    industry = db.query(Industry).filter(Industry.id == industry_id).first()
    platform = db.query(Platform).filter(Platform.id == task.platform_id).first() if task.platform_id else None
    account = db.query(Account).filter(Account.id == task.account_id).first() if task.account_id else None
    persona = db.query(Persona).filter(Persona.id == task.persona_id).first() if task.persona_id else None

    keyword_ids = parse_ids(task.keyword_ids)
    keywords = db.query(Keyword).filter(Keyword.id.in_(keyword_ids)).all() if keyword_ids else []
    keyword_words = [k.word for k in keywords]

    # ===== 新增：知识库知识点上下文 =====
    knowledge_item_ids = parse_ids(getattr(task, "knowledge_item_ids", "") or "")
    knowledge_items = []
    if knowledge_item_ids:
        knowledge_items = db.query(KnowledgeItem).filter(
            KnowledgeItem.id.in_(knowledge_item_ids),
            KnowledgeItem.is_deleted == 0,
        ).order_by(KnowledgeItem.sort.asc()).all()

    knowledge_content_parts = []
    knowledge_summary_parts = []
    for ki in knowledge_items:
        title = ki.title or ""
        content = ki.content or ""
        summary = ki.summary or ""
        if title and content:
            knowledge_content_parts.append(f"【{title}】\n{content}")
        elif content:
            knowledge_content_parts.append(content)
        # 摘要部分：优先用 summary 字段，没有则取 content 前 80 字
        if summary:
            knowledge_summary_parts.append(f"- {title}：{summary}")
        elif content:
            knowledge_summary_parts.append(f"- {title}：{content[:80]}")
    knowledge_content = "\n\n".join(knowledge_content_parts)
    knowledge_items_text = "\n".join(knowledge_summary_parts) if knowledge_summary_parts else ""
    knowledge_summary = "\n".join(knowledge_summary_parts) if knowledge_summary_parts else ""
    knowledge_titles = "、".join(ki.title for ki in knowledge_items if ki.title) if knowledge_items else ""
    knowledge_count = len(knowledge_items)

    brand = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id,
        BrandAsset.is_default == 1,
        BrandAsset.is_deleted == 0,
    ).first()
    if not brand:
        brand = db.query(BrandAsset).filter(
            BrandAsset.industry_id == industry_id,
            BrandAsset.is_deleted == 0,
        ).first()

    rules = db.query(RuleLibrary).filter(
        RuleLibrary.industry_id == industry_id,
        RuleLibrary.is_deleted == 0,
        RuleLibrary.status == 1,
    ).all()
    # v5 新增：若任务显式选定了规则（rule_ids），则仅注入选定规则；否则回退为行业全部启用规则
    selected_rule_ids = parse_ids(getattr(task, "rule_ids", "") or "")
    if selected_rule_ids:
        rules = [r for r in rules if r.id in selected_rule_ids]
    anti_ai_rules = [r.content for r in rules if r.rule_type == "anti_ai"]
    compliance_rules = [r.content for r in rules if r.rule_type == "compliance"]
    ai_seo_rules = [r.content for r in rules if r.rule_type == "ai_seo"]
    creation_rules = [r.content for r in rules if r.rule_type == "creation"]

    context = {
        "industry_name": industry.name if industry else "",
        "industry_desc": industry.description if industry else "",
        "platform_name": platform.name if platform else "",
        "platform_word_min": platform.word_count_min if platform else 800,
        "platform_word_max": platform.word_count_max if platform else 1500,
        "compliance_level": platform.compliance_level if platform else 2,
        # GEO 作战增强：平台特性与平台规则（选平台步骤已录入，须注入提示词，让生成内容贴合平台形态与合规要求）
        "platform_characteristics": (platform.characteristics or "") if platform else "",
        "platform_rules": (platform.rules or "") if platform else "",
        # 三模式发布：publish_mode 决定品牌策略；output_format 决定产出形态（markdown / mdx）
        "publish_mode": "geo",
        "brand_policy": get_brand_policy("geo"),
        "mode_goal": get_mode_goal("geo"),
        "output_format": "markdown",
        "mdx_template": "",
        "official_site_url": "",
        "publish_prompt": "",
        "account_name": account.account_name if account else "",
        "account_content_track": account.content_track if account else "",
        "persona_name": persona.name if persona else "",
        "persona_identity": persona.identity if persona else "",
        "persona_tone": persona.tone_style if persona else "",
        # 合规红线：即便人设规则允许留联系方式，平台正文也禁止，故对创作模型中和该规则
        "persona_contact_rule": _sanitize_contact_rule(persona.contact_rule if persona else ""),
        # ===== GEO 作战：目标客户画像与意图问题（生成"带信号的 GEO 软文"锚点） =====
        "target_persona_name": "",
        "target_persona_role": "",
        "target_persona_pain_points": "",
        "target_persona_cares_about": "",
        "target_persona_needs": "",  # 痛点 + 关注点 合并，便于提示词直接引用
        "intent_question": "",
        "intent_category": "",
        "expected_recommendation": "",
        "geo_signals": "",  # 汇总：目标客户会问什么 + 期望我们被推荐的角度 + 品牌实体，供 GEO 软文提示词引用
        "keywords": "、".join(keyword_words),
        "keyword_list": "\n".join(f"- {w}" for w in keyword_words),
        # ===== 新增：知识库占位符 =====
        "knowledge_content": knowledge_content,
        "knowledge_items": knowledge_items_text,
        "knowledge_summary": knowledge_summary,
        "knowledge_titles": knowledge_titles,
        "knowledge_count": knowledge_count,
        "brand_name": brand.brand_name if brand else "",
        # 合规红线：平台正文严禁出现官网/电话/微信等站外引流与私人联系方式，
        # 故「绝不」把真实联系方式注入给创作模型，从源头杜绝 AI 把联系方式写进正文。
        "official_website": "",
        "contact_phone": "",
        "contact_wechat": "",
        "contact_email": "",
        "brand_slogan": brand.slogan if brand else "",
        "core_products": brand.core_products if brand else "",
        "target_keywords": brand.target_keywords if brand else "",
        "selling_points": brand.unique_selling_points if brand else "",
        "brand_story": brand.brand_story if brand else "",
        "brand_info": _format_brand_info(brand),
        "anti_ai_rules": "\n".join(f"- {r}" for r in anti_ai_rules),
        "compliance_rules": "\n".join(f"- {r}" for r in compliance_rules),
        "ai_seo_rules": "\n".join(f"- {r}" for r in ai_seo_rules),
        "creation_rules": "\n".join(f"- {r}" for r in creation_rules),
        "outline_content": getattr(task, "outline_content", "") or "",
        "draft_content": getattr(task, "draft_content", "") or "",
        "rewrite_content": getattr(task, "rewrite_content", "") or "",
        "final_content": getattr(task, "final_content", "") or "",
        "task_title": getattr(task, "title", "") or "",
        "current_date": datetime.now().strftime("%Y-%m-%d"),
        # ===== 第8步 配图专用占位符（按封面/章节逐张注入，全局默认留空） =====
        "section_title": "",
        "section_content": "",
        "section_index": "",
        "image_position": "",
        "aspect_ratio": "",
        "image_size": "",
        "style_label": "",
    }

    # ===== 三模式发布：解析 publish_mode 并据此装配品牌策略 =====
    # 优先级：task.publish_mode（工作室运行手动/派生） > platform.publish_mode > 默认 geo
    _task_mode = getattr(task, "publish_mode", "") or ""
    _plat_mode = (platform.publish_mode or "") if platform else ""
    _mode = "geo"
    if _task_mode in ("geo", "platform", "green"):
        _mode = _task_mode
    elif _plat_mode in ("geo", "platform", "green"):
        _mode = _plat_mode
    # output_format：优先 run.output_format > platform.output_format > 默认 markdown
    _task_out = getattr(task, "output_format", "") or ""
    _plat_out = (platform.output_format or "") if platform else ""
    _output = "markdown"
    if _task_out in ("markdown", "mdx"):
        _output = _task_out
    elif _plat_out in ("markdown", "mdx"):
        _output = _plat_out
    context["publish_mode"] = _mode
    context["brand_policy"] = get_brand_policy(_mode)
    context["mode_goal"] = get_mode_goal(_mode)
    context["output_format"] = _output
    context["mdx_template"] = OFFICIAL_MDX_PROMPT if _output == "mdx" else ""
    context["official_site_url"] = OFFICIAL_SITE_URL if _output == "mdx" else ""
    # 官网/自建站（mdx）模式：即便平台行未解析到，也强制带回 MDX 模板提示词，
    # 确保「自动化发布提示词」部件始终有内容可展示（与平台的 publish_prompt 字段同源）。
    if _output == "mdx":
        context["publish_prompt"] = (platform.publish_prompt if platform and platform.publish_prompt else OFFICIAL_MDX_PROMPT)
    else:
        context["publish_prompt"] = (platform.publish_prompt or "") if platform else ""

    # ===== GEO 作战：若任务绑定了目标画像 / 意图问题，填充对应的 GEO 上下文 =====
    # 支持多选：优先读 task.target_persona_ids / intent_question_ids（逗号列表），
    # 旧单值 target_persona_id / intent_question_id 作为兼容兜底。
    def _parse_ids(raw, fallback=0):
        out = []
        if raw:
            for x in str(raw).split(","):
                x = x.strip()
                if x.isdigit():
                    out.append(int(x))
        if not out and fallback:
            out.append(fallback)
        return out

    _tp_ids = _parse_ids(getattr(task, "target_persona_ids", ""), getattr(task, "target_persona_id", 0) or 0)
    _iq_ids = _parse_ids(getattr(task, "intent_question_ids", ""), getattr(task, "intent_question_id", 0) or 0)
    _tps = db.query(TargetPersona).filter(TargetPersona.id.in_(_tp_ids), TargetPersona.is_deleted == 0).all() if _tp_ids else []
    _iqs = db.query(IntentQuestion).filter(IntentQuestion.id.in_(_iq_ids), IntentQuestion.is_deleted == 0).all() if _iq_ids else []
    if _tps:
        _roles = []
        _pains = []
        _cares = []
        for _tp in _tps:
            _role = {"decision_maker": "决策层", "technical": "技术层", "procurement": "采购层"}.get(_tp.role_type or "", _tp.role_type or "")
            _roles.append(f"{_tp.name}（{_role}）" if _role else _tp.name)
            if _tp.pain_points:
                _pains.append((_tp.pain_points or "").replace("\n", "；"))
            if _tp.cares_about:
                _cares.append((_tp.cares_about or "").replace("\n", "；"))
        context["target_persona_name"] = "；".join(_roles)
        context["target_persona_role"] = "；".join(_roles)
        context["target_persona_pain_points"] = "；".join(_pains)
        context["target_persona_cares_about"] = "；".join(_cares)
        context["target_persona_needs"] = "；".join(x for x in [_pains and "；".join(_pains), _cares and "；".join(_cares)] if x)
    if _iqs:
        context["intent_question"] = "\n".join(f"- {_iq.question}" for _iq in _iqs if _iq.question)
        context["intent_category"] = "；".join(_iq.intent_category for _iq in _iqs if _iq.intent_category)
        context["expected_recommendation"] = "\n".join(f"- {_iq.expected_recommendation}" for _iq in _iqs if _iq.expected_recommendation)
    if _tps or _iqs:
        _geo = []
        for _iq in _iqs:
            if _iq.question:
                _geo.append(f"目标客户会问 AI 的问题：{_iq.question}")
            if _iq.expected_recommendation:
                _geo.append(f"希望 AI 推荐我们时的角度：{_iq.expected_recommendation}")
        for _tp in _tps:
            _role = {"decision_maker": "决策层", "technical": "技术层", "procurement": "采购层"}.get(_tp.role_type or "", _tp.role_type or "")
            if _tp.name:
                _geo.append(f"目标客户画像：{_tp.name}（{_role}）")
                if _tp.pain_points:
                    _geo.append(f"他的痛点：{(_tp.pain_points or '').replace(chr(10), '；')}")
                if _tp.cares_about:
                    _geo.append(f"他关心：{(_tp.cares_about or '').replace(chr(10), '；')}")
        context["geo_signals"] = "\n".join(_geo)

    # ===== 第4步「目标客户需求」：把用户在 Step4 显式定义的需求并入 GEO 信号 =====
    # 这样无论大纲 / 初稿 / 精修模板，只要引用 {geo_signals} 或 {expected_recommendation}，
    # 第4步选入的"要求"就会真实驱动后续软文生成。
    _tn_raw = getattr(task, "target_needs", "") or ""
    _tn = {}
    if _tn_raw:
        try:
            _tn = json.loads(_tn_raw) if isinstance(_tn_raw, str) else _tn_raw
        except Exception:
            _tn = {}
    _tn_rec = (str(_tn.get("expected_recommendation") or "")).strip()
    _tn_signals = _tn.get("required_signals") or []
    _tn_pains = _tn.get("must_address_pains") or []
    if _tn:
        # 期望推荐角度：用户指定值覆盖意图问题自带值
        if _tn_rec:
            context["expected_recommendation"] = _tn_rec
        _tn_extra = []
        if _tn_rec:
            _tn_extra.append(f"期望 AI 推荐我们的角度（用户指定）：{_tn_rec}")
        if _tn_signals:
            _tn_extra.append("必含品牌信号：" + "、".join(_tn_signals))
        if _tn_pains:
            _tn_extra.append("必须回应的客户痛点：" + "；".join(_tn_pains))
        if _tn_extra:
            context["geo_signals"] = (context["geo_signals"] + "\n" + "\n".join(_tn_extra)).strip() \
                if context["geo_signals"] else "\n".join(_tn_extra)
    context["target_needs_signals"] = "、".join(_tn_signals) if _tn_signals else ""
    context["target_needs_pains"] = "；".join(_tn_pains) if _tn_pains else ""
    context["target_needs_recommendation"] = _tn_rec

    # ===== 别名键：兼容模板与前端变量面板中使用的简写名称 =====
    # 早期内置变量清单与默认提示词模板使用了 {word_min}/{word_max}/
    # {brand_selling_points}/{brand_official_url}/{platform_tone} 等名称，
    # 而引擎只填充了 platform_word_min 等规范名，导致这些占位符原样残留。
    # 这里补齐别名，保证两套命名都能正确渲染。
    context["word_min"] = context["platform_word_min"]
    context["word_max"] = context["platform_word_max"]
    context["brand_selling_points"] = context["selling_points"]
    context["brand_official_url"] = context["official_website"]
    context["brand_official_website"] = context["official_website"]
    # platform_tone：从平台的 config JSON 派生（marketing + features），
    # 不再恒为空，使变量面板中展示的「平台内容调性」真实可用
    platform_tone = ""
    if platform and getattr(platform, "config", None):
        try:
            pcfg = json.loads(platform.config) if isinstance(platform.config, str) else platform.config
            parts = []
            marketing = (pcfg or {}).get("marketing", "")
            features = (pcfg or {}).get("features", [])
            if marketing:
                parts.append(marketing)
            if isinstance(features, list) and features:
                parts.append("、".join(features))
            platform_tone = "；".join(parts)
        except Exception:
            platform_tone = ""
    context["platform_tone"] = platform_tone
    return context


def _format_brand_info(brand) -> str:
    """汇总品牌信息供创作模型参考。

    重要：按平台合规要求，正文严禁出现官网/电话/微信等联系方式，故本函数
    「不输出」任何联系方式字段；仅保留品牌名/主张/产品/卖点/故事，供 AI 自然化用。
    """
    if not brand:
        return ""
    parts = []
    if brand.brand_name:
        parts.append(f"品牌名：{brand.brand_name}")
    # 联系方式（官网/电话/微信）按合规要求对创作模型屏蔽，避免被原样抄录进正文
    if brand.slogan:
        parts.append(f"品牌主张：{brand.slogan}（仅作品牌调性参考，正文中须自然化用，禁止口号式原样堆砌）")
    if brand.core_products:
        parts.append(f"核心产品：{brand.core_products}")
    if brand.unique_selling_points:
        parts.append(f"独特卖点：{brand.unique_selling_points}")
    if brand.brand_story:
        parts.append(f"品牌故事：{brand.brand_story}")
    return "\n".join(parts)


# 联系方式词（人设规则里若出现，统一中和成「品牌官方渠道」，不让模型据此往正文塞联系方式）
_CONTACT_MASK_WORDS = (
    "官网", "官方网站", "微信", "QQ", "扫码", "二维码", "电话", "手机号", "手机号码",
    "邮箱", "APP", "公众号", "下载", "网址", "链接",
)


def _sanitize_contact_rule(rule: str) -> str:
    """中和人设联系方式规则：把其中的引流/联系词替换成中性措辞，避免模型据此写联系方式。"""
    if not rule:
        return rule
    out = rule
    for w in _CONTACT_MASK_WORDS:
        out = out.replace(w, "品牌官方渠道")
    return out


def render_prompt(template: str, context: dict) -> str:
    """渲染提示词模板"""
    return safe_format(template, context)


def unresolved_variables(template: str, context: dict) -> list:
    """返回模板中使用、但上下文未提供的变量名。

    这些变量会被 safe_format 原样保留为 {xxx}，若直接喂给 LLM 会造成
    静默污染。用于在保存/渲染时给出明确告警。
    """
    if not template:
        return []
    keys = {v["key"] for v in extract_variables(template)}
    return [k for k in keys if k not in context]


# ===== 新增：变量检测函数 =====

# 变量描述映射
VARIABLE_DESCRIPTIONS = {
    "industry_name": "行业名称",
    "industry_desc": "行业描述",
    "platform_name": "平台名称",
    "platform_word_min": "平台最低字数",
    "platform_word_max": "平台最高字数",
    "word_min": "平台最低字数（word_min 别名）",
    "word_max": "平台最高字数（word_max 别名）",
    "platform_tone": "平台内容调性",
    "current_date": "当前日期（YYYY-MM-DD）",
    "compliance_level": "合规等级",
    "platform_characteristics": "平台特性（受众画像/内容形态/分发机制/推荐逻辑等，选平台步骤录入）",
    "platform_rules": "平台规则（合规约束/营销限制/禁区/格式要求等，选平台步骤录入）",
    "publish_mode": "发布模式：geo=强品牌/GEO 模式（自建站/AI 抓取）；platform=平台合规模式（搜狐等内容平台）；green=绿色吸粉模式（自媒体涨粉）",
    "brand_policy": "品牌策略（按发布模式自动切换：geo=强品牌铁律≥3次；platform=平台合规≤2次、标题无品牌、带 AIGC 声明）",
    "mode_goal": "文章目标（按发布模式：geo=被 AI 推荐引用的专业软文；platform=中立有价值的平台合规干货；green=吸粉自媒体）",
    "output_format": "产出形态：markdown=常规内容平台/吸粉文章；mdx=官网/Astro 站，按 MDX 模板产出可复制代码",
    "mdx_template": "官网 MDX 自动化提示词模板（output_format=mdx 时注入，含 Frontmatter/六段结构/4列表格规则）",
    "official_site_url": "官网/自建站地址（output_format=mdx 时注入，如 https://www.example.com）",
    "publish_prompt": "平台自动化发布提示词（官网/自建站平台专用，有序存放的 MDX 发布指令）",
    "account_name": "账号名称",
    "account_content_track": "账号内容赛道/定位",
    "persona_name": "人设名称",
    "persona_identity": "人设身份",
    "persona_tone": "人设语气",
    "persona_contact_rule": "人设联系方式规则",
    "keywords": "关键词（顿号分隔）",
    "keyword_list": "关键词列表（换行分隔）",
    "knowledge_content": "知识库内容（完整正文）",
    "knowledge_items": "知识库条目摘要列表",
    "knowledge_summary": "知识库摘要（同 knowledge_items）",
    "knowledge_titles": "知识库条目标题（顿号分隔）",
    "knowledge_count": "知识库条目数量",
    "brand_name": "品牌名称",
    "official_website": "官网",
    "contact_phone": "联系电话",
    "contact_wechat": "微信",
    "contact_email": "联系邮箱",
    "brand_slogan": "品牌口号",
    "core_products": "核心产品",
    "target_keywords": "品牌目标关键词",
    "selling_points": "独特卖点",
    "brand_selling_points": "独特卖点（brand_selling_points 别名）",
    "brand_official_url": "官网（brand_official_url 别名）",
    "brand_official_website": "官网（brand_official_website 别名）",
    "brand_story": "品牌故事",
    "brand_info": "品牌完整信息（汇总）",
    "anti_ai_rules": "去AI味规则",
    "compliance_rules": "合规规则",
    "ai_seo_rules": "AI SEO规则",
    "creation_rules": "创作规则（结构化/数据案例/语言精准化/4类内容/自检清单，驱动软文生产）",
    "outline_content": "大纲内容",
    "draft_content": "初稿内容",
    "rewrite_content": "精修稿内容",
    "final_content": "最终文章内容（可用于配图章节拆分）",
    "task_title": "生产任务标题（文章主题，可用于标题/封面语境）",
    "section_title": "当前配图对应的章节标题（封面图为文章标题）",
    "section_content": "当前章节正文内容",
    "section_index": "配图序号（封面=1，内文插图依次递增）",
    "image_position": "图片位置：cover 封面 / section 内文插图",
    "aspect_ratio": "推荐画面比例，如 3:4、9:16、16:9、1:1",
    "image_size": "推荐像素尺寸，如 1080x1440",
    "style_label": "配图风格描述（如：写实商业摄影）",
    "target_persona_name": "GEO 目标客户画像名称（如：真空产线厂长）",
    "target_persona_role": "GEO 目标客户角色（决策层/技术层/采购层）",
    "target_persona_pain_points": "GEO 目标客户痛点（顿号分隔）",
    "target_persona_cares_about": "GEO 目标客户关注点（顿号分隔）",
    "target_persona_needs": "GEO 目标客户需求（痛点+关注点汇总）",
    "intent_question": "GEO 目标客户会问 AI 的问题",
    "intent_category": "GEO 意图分类（selection/cost/integration/risk/compliance/other）",
    "expected_recommendation": "GEO 期望 AI 推荐我们时的角度（话术要点/卖点）",
    "geo_signals": "GEO 信号汇总（意图问题+期望推荐角度+目标画像+痛点+第4步必含信号/痛点），供 GEO 软文提示词引用",
    "target_needs_signals": "第4步指定的必含品牌信号（如：品牌名、官网、核心产品），顿号分隔",
    "target_needs_pains": "第4步指定的必须回应的客户痛点，分号分隔",
    "target_needs_recommendation": "第4步指定的期望 AI 推荐我们的角度（覆盖意图问题自带值）",
}


def extract_variables(template: str) -> list:
    """从提示词模板中提取所有 {xxx} 占位符变量

    返回格式: [{"key": "xxx", "desc": "描述", "is_builtin": True/False}]
    """
    if not template:
        return []
    # 匹配 {variable_name} 格式，排除 {{ 和 }} 转义
    pattern = r'(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})'
    raw_keys = re.findall(pattern, template)
    # 去重保持顺序
    seen = set()
    result = []
    for key in raw_keys:
        if key in seen:
            continue
        seen.add(key)
        is_builtin = key in BUILTIN_VARIABLES
        desc = VARIABLE_DESCRIPTIONS.get(key, "自定义变量")
        result.append({
            "key": key,
            "desc": desc,
            "is_builtin": is_builtin,
        })
    return result
