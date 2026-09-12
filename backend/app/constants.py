# ============================================================
#  全局常量单一事实来源（Single Source of Truth）
#  收敛此前散落/重复定义的常量，杜绝多份不一致：
#   - BUILTIN_VARIABLES：前端变量面板参考列表（list[dict]，含 key/desc/group/example）
#   - SUPPORTED_RENDER_VARIABLES：渲染引擎 is_builtin 白名单（set，build_render_context 支持的全部变量键）
#  说明：render 白名单是面板列表的**超集**（面板只展示一部分面向用户的变量），
#       二者键集合必须满足「面板键 ⊆ 渲染白名单」，否则面板变量在渲染时原样残留（历史 A2 缺陷）。
#       该不变量由 tests/test_constants.py 守护。
#  PLATFORM_PRESETS 仅定义于 models.py（本就是单一来源），此处不重复。
# ============================================================

# 内置变量参考列表（供前端变量面板展示）。
# 注意：键集合必须是 SUPPORTED_RENDER_VARIABLES 的子集，新增变量请同步两套定义。
BUILTIN_VARIABLES = [
    # 行业与平台
    {"key": "industry_name", "desc": "行业名称", "group": "行业与平台", "example": "美妆护肤"},
    {"key": "industry_desc", "desc": "行业描述", "group": "行业与平台", "example": "专注敏感肌修护的细分赛道"},
    {"key": "platform_name", "desc": "平台名称", "group": "行业与平台", "example": "小红书"},
    {"key": "compliance_level", "desc": "平台合规等级 1-3", "group": "行业与平台", "example": "2"},
    {"key": "platform_tone", "desc": "平台内容调性", "group": "行业与平台", "example": "种草风、真实分享"},
    {"key": "current_date", "desc": "当前日期（YYYY-MM-DD）", "group": "行业与平台", "example": "2026-07-09"},
    # 账号与人设
    {"key": "account_name", "desc": "账号名称", "group": "账号与人设", "example": "小美护肤日记"},
    {"key": "account_content_track", "desc": "账号内容赛道/定位", "group": "账号与人设", "example": "成分党科普"},
    {"key": "persona_name", "desc": "人设名称", "group": "账号与人设", "example": "护肤达人小美"},
    {"key": "persona_identity", "desc": "人设身份", "group": "账号与人设", "example": "5年护肤经验的美妆博主"},
    {"key": "persona_tone", "desc": "语气风格", "group": "账号与人设", "example": "亲切、专业、有亲和力"},
    {"key": "persona_contact_rule", "desc": "人设联系方式规则", "group": "账号与人设", "example": "文末引导私信，不直接留微信"},
    # 品牌信息
    {"key": "brand_name", "desc": "品牌名称", "group": "品牌信息", "example": "XX护肤"},
    {"key": "brand_info", "desc": "品牌完整信息（汇总）", "group": "品牌信息", "example": "品牌名+官网+联系方式+卖点"},
    {"key": "brand_selling_points", "desc": "品牌核心卖点", "group": "品牌信息", "example": "天然成分、温和不刺激"},
    {"key": "brand_official_url", "desc": "品牌官网", "group": "品牌信息", "example": "https://example.com"},
    {"key": "brand_official_website", "desc": "品牌官网（同 brand_official_url）", "group": "品牌信息", "example": "https://example.com"},
    {"key": "contact_phone", "desc": "品牌联系电话", "group": "品牌信息", "example": "400-xxx-xxxx"},
    {"key": "contact_wechat", "desc": "品牌联系微信", "group": "品牌信息", "example": "xxbrand_vip"},
    {"key": "contact_email", "desc": "品牌联系邮箱", "group": "品牌信息", "example": "service@example.com"},
    {"key": "brand_slogan", "desc": "品牌口号", "group": "品牌信息", "example": "让敏感肌安心"},
    {"key": "core_products", "desc": "核心产品", "group": "品牌信息", "example": "修护精华、舒缓面霜"},
    {"key": "target_keywords", "desc": "品牌目标关键词", "group": "品牌信息", "example": "敏感肌精华、屏障修护"},
    {"key": "brand_story", "desc": "品牌故事", "group": "品牌信息", "example": "源于一次过敏后的研发初心"},
    {"key": "selling_points", "desc": "独特卖点（品牌核心差异化）", "group": "品牌信息", "example": "天然成分、温和不刺激"},
    # 关键词与知识
    {"key": "keywords", "desc": "关键词（顿号分隔）", "group": "关键词与知识", "example": "敏感肌护肤|修复屏障"},
    {"key": "keyword_list", "desc": "关键词列表（每行一个）", "group": "关键词与知识", "example": "1. 敏感肌护肤 2. 修复屏障"},
    {"key": "knowledge_content", "desc": "知识库内容（完整正文）", "group": "关键词与知识", "example": "【标题】\n知识点正文..."},
    {"key": "knowledge_items", "desc": "知识库条目摘要列表", "group": "关键词与知识", "example": "- 标题：摘要..."},
    {"key": "knowledge_summary", "desc": "知识点摘要列表（同 knowledge_items）", "group": "关键词与知识", "example": "- 标题：摘要..."},
    {"key": "knowledge_titles", "desc": "知识库条目标题（顿号分隔）", "group": "关键词与知识", "example": "标题1、标题2"},
    {"key": "knowledge_count", "desc": "知识库条目数量", "group": "关键词与知识", "example": "12"},
    # 生产内容
    {"key": "outline_content", "desc": "大纲内容", "group": "生产内容", "example": "一、引言...二、正文..."},
    {"key": "draft_content", "desc": "初稿内容", "group": "生产内容", "example": "完整文章初稿"},
    {"key": "rewrite_content", "desc": "精修稿内容", "group": "生产内容", "example": "去AI味后的精修稿"},
    {"key": "final_content", "desc": "最终文章内容（用于配图章节拆分）", "group": "生产内容", "example": "已发布的完整文章"},
    {"key": "task_title", "desc": "生产任务标题（文章主题，可用于标题/封面语境）", "group": "生产内容", "example": "真空泵选型避坑指南"},
    {"key": "section_title", "desc": "当前配图对应章节标题（封面图为文章标题）", "group": "配图专用", "example": "三步搞定敏感肌"},
    {"key": "section_content", "desc": "当前章节正文内容", "group": "配图专用", "example": "正文段落..."},
    {"key": "section_index", "desc": "配图序号（封面=1）", "group": "配图专用", "example": "1"},
    {"key": "image_position", "desc": "图片位置：cover/section", "group": "配图专用", "example": "cover"},
    {"key": "aspect_ratio", "desc": "推荐画面比例", "group": "配图专用", "example": "3:4"},
    {"key": "image_size", "desc": "推荐像素尺寸", "group": "配图专用", "example": "1080x1440"},
    {"key": "style_label", "desc": "配图风格描述", "group": "配图专用", "example": "清新生活插画"},
    # 规则约束
    {"key": "anti_ai_rules", "desc": "去AI味规则", "group": "规则约束", "example": "避免机械对称句式..."},
    {"key": "compliance_rules", "desc": "合规规则", "group": "规则约束", "example": "禁止使用极限词..."},
    {"key": "ai_seo_rules", "desc": "AI SEO规则", "group": "规则约束", "example": "品牌关键词密度3-5%..."},
    {"key": "creation_rules", "desc": "创作规则", "group": "规则约束", "example": "核心信息前置：首段100字内点明主题..."},
    # 字数要求
    {"key": "word_min", "desc": "最小字数", "group": "字数要求", "example": "800"},
    {"key": "word_max", "desc": "最大字数", "group": "字数要求", "example": "1200"},
    {"key": "platform_word_min", "desc": "平台最低字数（同 word_min）", "group": "字数要求", "example": "800"},
    {"key": "platform_word_max", "desc": "平台最高字数（同 word_max）", "group": "字数要求", "example": "1200"},
    # GEO 作战
    {"key": "target_persona_name", "desc": "GEO 目标客户画像名称", "group": "GEO 作战", "example": "真空产线厂长"},
    {"key": "target_persona_role", "desc": "GEO 目标客户角色", "group": "GEO 作战", "example": "决策层"},
    {"key": "target_persona_pain_points", "desc": "GEO 目标客户痛点", "group": "GEO 作战", "example": "怕选型踩坑、担心交付周期"},
    {"key": "target_persona_cares_about", "desc": "GEO 目标客户关注点", "group": "GEO 作战", "example": "ROI、质保、案例"},
    {"key": "target_persona_needs", "desc": "GEO 目标客户需求（痛点+关注点）", "group": "GEO 作战", "example": "选型靠谱、回本快"},
    {"key": "intent_question", "desc": "GEO 目标客户会问 AI 的问题", "group": "GEO 作战", "example": "真空泵怎么选型？"},
    {"key": "intent_category", "desc": "GEO 意图分类", "group": "GEO 作战", "example": "selection"},
    {"key": "expected_recommendation", "desc": "GEO 期望 AI 推荐我们的角度", "group": "GEO 作战", "example": "给出选型 5 问并带出我方优势"},
    {"key": "geo_signals", "desc": "GEO 信号汇总（意图问题+推荐角度+画像+痛点）", "group": "GEO 作战", "example": "目标客户会问…希望 AI 推荐…"},
    {"key": "target_needs_signals", "desc": "第4步必含品牌信号（品牌名/官网/产品）", "group": "GEO 作战", "example": "品牌名、官网、核心产品"},
    {"key": "target_needs_pains", "desc": "第4步必须回应的客户痛点", "group": "GEO 作战", "example": "选型踩坑、交付周期"},
    {"key": "target_needs_recommendation", "desc": "第4步期望推荐角度（覆盖意图问题自带值）", "group": "GEO 作战", "example": "给出选型5问并带出我方优势"},
]

# 渲染引擎支持的全部变量键（build_render_context 注入键 + 别名）。
# 是 BUILTIN_VARIABLES 面板列表的**超集**；render 用此集合判定 is_builtin。
SUPPORTED_RENDER_VARIABLES = {
    "industry_name", "industry_desc",
    "platform_name", "platform_word_min", "platform_word_max", "compliance_level",
    "platform_characteristics", "platform_rules",
    "platform_tone", "current_date",
    "publish_mode", "brand_policy", "mode_goal",
    "output_format", "mdx_template", "official_site_url", "publish_prompt",
    "account_name", "account_content_track",
    "persona_name", "persona_identity", "persona_tone", "persona_contact_rule",
    "keywords", "keyword_list",
    "knowledge_content", "knowledge_items", "knowledge_summary", "knowledge_titles", "knowledge_count",
    "brand_name", "official_website", "contact_phone", "contact_wechat", "contact_email",
    "brand_slogan", "core_products", "target_keywords", "selling_points", "brand_story", "brand_info",
    "brand_selling_points", "brand_official_url", "brand_official_website",
    "anti_ai_rules", "compliance_rules", "ai_seo_rules", "creation_rules",
    "outline_content", "draft_content", "rewrite_content", "final_content", "task_title",
    # 别名（与默认模板/变量面板一致）
    "word_min", "word_max",
    # 第8步 配图专用占位符
    "section_title", "section_content", "section_index",
    "image_position", "aspect_ratio", "image_size", "style_label",
    # GEO 作战：目标画像 / 意图问题 / 信号
    "target_persona_name", "target_persona_role", "target_persona_pain_points",
    "target_persona_cares_about", "target_persona_needs",
    "intent_question", "intent_category", "expected_recommendation", "geo_signals",
    # 第4步「目标客户需求」细粒度需求（Step4 显式定义）
    "target_needs_signals", "target_needs_pains", "target_needs_recommendation",
}
