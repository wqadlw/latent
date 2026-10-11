/**
 * 提示词库（Prompt Library）的纯数据常量。
 *
 * 为什么单独成文件：`PromptLibrary.vue` 的 script 曾有 485 行，其中约 100 行是**长文本字面量**
 * （元提示词 3400 字、分类推荐变量表、三套模板片段、导入样例）。把它们混在视图逻辑里，
 * 会让「这个页面做了什么」被一堆字符串淹没。
 *
 * ⚠️ 这里只放**纯数据**。任何需要 API / store / ref 的东西都属于 composable 或视图。
 */


/**
 * 元提示词：让**其它 AI**（ChatGPT / Claude / DeepSeek…）帮本系统起草标准提示词模板。
 *
 * ⚠️ 这段文本里的变量白名单是**手工维护**的，必须与后端 `app/constants.py` 的
 * `BUILTIN_VARIABLES` 保持一致。改了后端白名单就要同步改这里 —— 否则用户拿这段
 * 元提示词去问 AI，AI 会「合规地」写出一堆系统不认识的变量。
 */

export const META_PROMPT = `你是一名「多行业提示词矩阵管理系统（GEO 作战版）」的资深提示词工程师，擅长把模糊的营销 / GEO 需求，转化为该系统可稳定渲染、直接产出高质量文章的标准提示词模板。

# 你的任务
为系统「AI 提示词库」编写一条标准提示词模板（带 {变量} 占位符）。这条模板最终会被系统引擎渲染成真正发给大模型的提示词，请直接产出"可粘贴即用"的成品，不要给我一段需要我再加工的描述。

# 系统本质（必须理解）
本系统是 GEO（生成式引擎优化）作战系统：提示词服务于"软文生产 10 步流水线"，目标是让 AI 搜索引擎能读懂并主动推荐我们的品牌。所以一条好的模板必须同时赢得两层信任：
- 算法信任：品牌实体信号可抽取、可溯源、可归属（让 AI 能引用我们）；
- 心智信任：内容有温度、像真人、读者愿意信（让人想了解更多）。
写模板时优先考虑：品牌实体信号（{brand_name}/{official_website}/{contact_phone}/{core_products}）、可量化证据（来自 {knowledge_content}）、以及 GEO 意图信号（{geo_signals}/{intent_question}/{expected_recommendation}）。

# 系统约束（必须严格遵守）
1. 系统是"模板引擎"：运行时用真实上下文替换 {变量名}。模板里只能写占位符，绝不能把具体行业名 / 品牌名 / 平台名写死，否则换行业就废了。
2. 只能用下方白名单变量（大小写敏感，全部可用）。写了白名单外的变量，渲染时会被原样保留成 {xxx} 字面文本喂给 AI——不报错，但会污染输入、拉低质量，极难排查。
   - 行业/平台：industry_name, industry_desc, platform_name, compliance_level, platform_tone, platform_word_min, platform_word_max, word_min, word_max, current_date
   - 账号/人设：account_name, account_content_track, persona_name, persona_identity, persona_tone, persona_contact_rule
   - 品牌：brand_name, brand_info, brand_selling_points, selling_points, brand_official_url, brand_official_website, official_website, contact_phone, contact_wechat, contact_email, brand_slogan, core_products, target_keywords, brand_story
   - 关键词/知识：keywords, keyword_list, knowledge_content, knowledge_items, knowledge_summary, knowledge_titles, knowledge_count
   - 生产产物：outline_content, draft_content, rewrite_content, final_content, task_title
   - 规则（三大规则库，渲染时已注入启用项）：anti_ai_rules（去AI味/心智信任）, compliance_rules（合规底线）, ai_seo_rules（算法信任/SEO）
   - GEO 作战：target_persona_name, target_persona_role, target_persona_pain_points, target_persona_cares_about, target_persona_needs, intent_question, intent_category, expected_recommendation, geo_signals
   - 第4步目标客户需求细粒度：target_needs_signals（必含品牌信号）, target_needs_pains（必回应痛点）, target_needs_recommendation（期望推荐角度）
   - 配图专用：section_title, section_content, section_index, image_position, aspect_ratio, image_size, style_label
3. 自定义变量：若白名单不够用，可在模板中自定义 {自定义变量名}，并在【自定义变量说明】里写清含义与建议取值——系统渲染前会弹窗让用户填写，不影响渲染。

# 与软文生产 10 步的耦合（写模板前先选对类型）
- outline（大纲类）→ 第7步 生成大纲；可结合 {knowledge_content}/{geo_signals} 规划"以问带答"结构
- draft（初稿类）→ 第8步 生成初稿；务必要把 {brand_info}/{anti_ai_rules}/{compliance_rules}/{geo_signals} 吃进去
- rewrite（洗稿/精修类）→ 第9步 安全发布 & GEO 筛选；做信号补强、结构化、温度精修
- geo（GEO 安全筛选/闸门类）→ 第9步 GEO 闸门 & 发布前体检；做实体审计、意图覆盖、JSON-LD 建议（注：系统已把旧"安全类 safety"合并进 geo，请统一用 geo）
- illustration（配图类）→ 第10步 文章配图；按封面/章节逐张渲染，用 {section_title}/{section_content}/{style_label}
写模板时默认就为该步骤服务，变量尽量覆盖该步骤能拿到的全部上下文。

# 标准四段式结构（强制遵循）
# 角色(Role)：给具体身份 / 经验 / 口吻（如"5 年经验的护肤研发顾问"），避免泛泛的"你是一个 AI"。
# 背景(Context)：全部用 {变量} 注入——行业、平台、人设、品牌、知识、规则、GEO 信号各取所需，禁止出现真实名称。
# 任务(Task)：明确做什么、围绕哪些关键词、产出什么形态（如"3-5 段大纲/完整初稿/精修稿/GEO 体检清单"），并写明本模板服务于哪个生产步骤。
# 约束与输出格式(Constraints)：量化约束（字数区间 {word_min}-{word_max}、品牌词密度 %、段落数）；引用规则用 {anti_ai_rules}/{compliance_rules}/{ai_seo_rules}；给明确输出分隔符或字段名，方便下游解析；末尾固定加一句"不要输出思考过程或修改说明。"。

# 我提供的信息
- 类型（五选一）：大纲类(outline) / 初稿类(draft) / 洗稿类(rewrite) / GEO类(geo) / 配图类(illustration)
- 服务步骤：<如 第9步 安全发布 & GEO 筛选>
- 行业示例：<在此填写，如 美妆护肤>
- 平台示例：<在此填写，如 知乎>
- 额外要求：<在此填写，如 增加 FAQ 模块、强调实测数据、加入真实使用场景、输出可粘贴的 JSON-LD>

# 输出格式（严格按序输出，不要替我执行任何文章生成）
1. 【模板正文】——上面要求的四段式，可直接粘贴进系统提示词库（变量用 {变量名}，行内引用规则用 {anti_ai_rules} 等）。
2. 【所用变量清单】——逐条列出本模板用到的 {变量名} 及其作用，并自查确认全部在白名单内；若有自定义变量一并标注。
3. 【编写说明】——简述角色 / 约束 / 输出格式的设计理由，以及它如何服务于指定生产步骤与双信任目标，便于我二次调整。
4. 【自定义变量说明】（如用到）——列出自定义变量名、含义、建议取值。`

/**
 * 各分类的「推荐变量集」——「本类默认变量」按钮据此一键灌入。
 * key 必须与后端 `prompt_library` 的分类枚举一致（outline/draft/rewrite/illustration/geo）。
 */

export const CATEGORY_DEFAULT_VARS = {
  outline: ['industry_name', 'platform_name', 'persona_name', 'brand_info', 'keywords', 'knowledge_content'],
  draft: ['industry_name', 'persona_name', 'persona_identity', 'persona_tone', 'brand_info', 'outline_content', 'keywords', 'anti_ai_rules', 'compliance_rules', 'word_min', 'word_max'],
  rewrite: ['draft_content', 'brand_info', 'anti_ai_rules', 'ai_seo_rules', 'word_min', 'word_max'],
  geo: ['industry_name', 'platform_name', 'geo_signals', 'brand_info', 'core_products', 'selling_points', 'outline_content', 'keywords', 'anti_ai_rules', 'compliance_rules', 'expected_recommendation', 'word_min', 'word_max'],
  illustration: ['platform_name', 'image_position', 'section_title', 'section_content', 'brand_name', 'style_label', 'aspect_ratio', 'image_size', 'keywords'],
}

/** 编辑器里的三套模板片段：点击即插入到光标所在内容。 */

export const PROMPT_SNIPPETS = {
outline: `\n# 角色设定\n你是一位资深的{industry_name}行业内容专家，擅长{platform_name}平台的内容创作。\n\n# 任务目标\n请围绕关键词「{keywords}」，结合以下知识库内容，生成一份结构清晰的文章大纲。\n\n# 知识库参考\n{knowledge_content}\n\n# 品牌信息\n{brand_info}\n\n# 输出要求\n1. 包含3-5个核心段落\n2. 每段标注要点\n3. 融入品牌{brand_name}的自然露出\n`,
structure: `\n## 标题\n（吸引眼球，包含关键词）\n\n## 开头引入\n（结合{industry_name}行业痛点）\n\n## 核心内容\n### 要点一\n### 要点二\n### 要点三\n\n## 品牌植入\n（自然融入{brand_name}）\n\n## 结尾引导\n（符合{platform_name}平台调性）\n`,
rules: `\n# 合规要求\n{compliance_rules}\n\n# 去AI味要求\n{anti_ai_rules}\n\n# AI SEO要求\n{ai_seo_rules}\n\n# 人设约束\n身份：{persona_identity}\n语气：{persona_tone}\n联系方式规则：{persona_contact_rule}\n`,
}

/** 「下载模板」导出的样例 JSON，字段名即导入接口接受的字段。 */

export const PROMPT_IMPORT_SAMPLE = [
{ name: '标准大纲', category: 'outline', content: '请根据以下信息生成文章大纲：\n行业：{industry_name}\n关键词：{keywords}', description: '通用大纲模板', tags: '大纲' },
{ name: '初稿写作', category: 'draft', content: '请基于大纲撰写初稿：\n{topic_outline}\n规则：{anti_ai_rules}', description: '初稿模板', tags: '初稿' },
{ name: 'GEO软文生成', category: 'geo', content: '你是一位既懂{industry_name}行业、又精通 GEO 的内容策略专家。请基于以下 GEO 信号写一篇能被 AI 搜索引擎引用并推荐我们的软文：\n{geo_signals}', description: '生成带信号的 GEO 软文', tags: 'GEO,带信号' },
]
