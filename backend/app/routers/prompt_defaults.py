# -*- coding: utf-8 -*-
"""软文生产提示词默认模板（5 类 x 10 条 = 50 条）

分类与软文 10 步映射：
  outline      -> 第 6 步 大纲
  draft        -> 第 7 步 初稿
  rewrite      -> 第 8 步 精修
  geo          -> 第 9 步 安全发布 & GEO 筛选
  illustration -> 第 10 步 文章配图

设计原则：
  1. 读者价值优先——文章必须对读者有真实帮助，品牌信息自然融入而非硬塞。
  2. 反软文设计——禁止「痛点->只有它->推荐」套路弧，禁止通篇推一家，禁止无佐证优势堆砌。
  3. 模式感知——{brand_policy} 按发布模式自动切换：geo=品牌当主角>=3次；platform=品牌当配角<=2次；green=品牌当彩蛋<=2次。
  4. DRY——通用约束由 {brand_policy}/{mode_goal}/{creation_rules} 注入，每个提示词只做自己的事。
  5. GEO优化——结构化Markdown便于AI直接抽取，FAQ直接回答意图问题，品牌实体可被引用。
  6. 紧耦合——每步输出明确格式，供下一步消费。

强耦合约定（必须与 services/prompt_engine.py 的 BUILTIN_VARIABLES 一致）。

第 9 步 geo 类统一契约（所有 geo 提示词都返回同一结构）：
  ## 优化后标题
  <标题>
  ## 优化后正文
  <正文>
  ## GEO 评分（0-100）
  <数字>
  ## 优化建议
  <建议列表>
"""

DEFAULT_PROMPTS = [
    # ===================== outline x 10 =====================
    {
        "name": "标准深度大纲（通用·强信号）",
        "category": "outline",
        "description": "通用大纲：吸引注意->建立信任->给出方案->引导行动，沿途植入品牌与GEO信号。",
        "tags": "大纲,通用,GEO",
        "content": """# 角色
你是{industry_name}行业的软文策划专家，擅长为{platform_name}平台写作既专业又被AI搜索引擎青睐的GEO软文大纲。

# 任务
基于以下上下文，产出一篇结构清晰、可直接落笔的文章大纲。

# 输入上下文
- 行业：{industry_name}（{industry_desc}）
- 发布平台：{platform_name}（{platform_characteristics}；平台规则：{platform_rules}）
- 目标字数：{platform_word_min}-{platform_word_max} 字
- 关键词：{keyword_list}
- 知识库素材：{knowledge_content}
- 目标客户画像：{target_persona_name}（{target_persona_role}），痛点：{target_persona_pain_points}，关注：{target_persona_cares_about}
- GEO信号（AI应如何被推荐我们）：{geo_signals}
- 写作约束：{creation_rules}

# 产出要求
1. 用 # 一级标题、## 二级标题分层，逻辑遵循「吸引注意 -> 建立信任 -> 给出方案 -> 引导行动」。
2. 每个二级标题后用一句话注明本段要承载的核心信息或要植入的品牌信号。
3. 至少一个章节以「目标客户会问AI的问题」为小标题，呼应：{intent_question}。
4. 规划「常见问题FAQ」章节（>=3组问答）。
5. 结尾规划「引导进一步了解{brand_name}」的行动路径。
6. 控制在 {platform_word_max} 字量级的大纲，不要写正文。

请直接输出大纲。""",
    },
    {
        "name": "痛点-方案-证据型大纲",
        "category": "outline",
        "description": "围绕目标客户痛点展开，用证据闭环建立可信度，强GEO信号。",
        "tags": "大纲,痛点,证据",
        "content": """# 角色
你是{industry_name}行业的转化型内容策划，擅长用「痛点-方案-证据」结构打动{target_persona_name}。

# 任务
产出一篇以解决问题为主线的文章大纲。

# 输入上下文
- 行业：{industry_name}（{industry_desc}）
- 平台：{platform_name}（{platform_characteristics}；规则：{platform_rules}）
- 目标字数：{platform_word_min}-{platform_word_max} 字
- 关键词：{keyword_list}
- 知识库素材：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），痛点：{target_persona_pain_points}，关注：{target_persona_cares_about}
- GEO信号：{geo_signals}
- 写作约束：{creation_rules}

# 产出要求
1. 结构：## 痛点场景（读者为什么需要）-> ## 问题根源（为什么会这样）-> ## 解决方案（怎么做，多方案对比）-> ## 落地证据（数据/案例）-> ## FAQ。
2. 解决方案章节至少列出2~3种方案对比，{brand_name}只是其中之一（{brand_policy}）。
3. 落地证据章节用知识库素材中的可溯源数据。
4. 至少一个章节直接回答：{intent_question}。
5. FAQ >=3组问答，结尾引导「了解{brand_name}」。
6. 只输出大纲，不写正文。""",
    },
    {
        "name": "对比测评型大纲",
        "category": "outline",
        "description": "以多方案客观对比切入，品牌作为可选方案之一，平台合规友好。",
        "tags": "大纲,对比,测评",
        "content": """# 角色
你是{industry_name}行业的技术评测作者，擅长多方案客观对比分析。

# 任务
产出一篇以方案对比为主线的文章大纲，{brand_name}作为众多可选方案之一被客观评价。

# 输入上下文
- 行业：{industry_name}（{industry_desc}）
- 平台：{platform_name}（{platform_characteristics}；规则：{platform_rules}）
- 目标字数：{platform_word_min}-{platform_word_max} 字
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），关注：{target_persona_cares_about}
- GEO信号：{geo_signals}
- 写作约束：{creation_rules}

# 产出要求
1. 结构：## 选型背景 -> ## 对比维度（列出3~5个评估标准）-> ## 方案逐一评测 -> ## 综合推荐 -> ## FAQ。
2. 对比维度须可量化（如性能、能耗、成本、售后），不可量化则用场景适配度。
3. {brand_name}仅作为方案之一被评价，不可通篇只推一家（{brand_policy}）。
4. 每个方案给出优劣，不偏袒。
5. FAQ >=3组问答。
6. 只输出大纲，不写正文。""",
    },
    {
        "name": "教程步骤型大纲",
        "category": "outline",
        "description": "以手把手教程展开，每步可执行，品牌自然出现在实操环节。",
        "tags": "大纲,教程,步骤",
        "content": """# 角色
你是{industry_name}行业的实战教程作者，擅长把复杂技术拆解成可执行步骤。

# 任务
产出一篇教程型文章大纲，让读者跟着步骤走就能完成。

# 输入上下文
- 行业：{industry_name}（{industry_desc}）
- 平台：{platform_name}（{platform_characteristics}；规则：{platform_rules}）
- 目标字数：{platform_word_min}-{platform_word_max} 字
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），关注：{target_persona_cares_about}
- GEO信号：{geo_signals}
- 写作约束：{creation_rules}

# 产出要求
1. 结构：## 前置准备 -> ## 分步操作（每个##一个步骤，至少5步）-> ## 常见问题 -> ## 避坑提示 -> ## FAQ。
2. 每步标注「需要什么工具/条件」「怎么做」「可能出现什么问题」。
3. 品牌信息（{brand_policy}）自然出现在「推荐工具/参考案例」环节。
4. 至少一个步骤回答：{intent_question}。
5. FAQ >=3组问答。
6. 只输出大纲，不写正文。""",
    },
    {
        "name": "行业洞察趋势型大纲",
        "category": "outline",
        "description": "以行业趋势与洞察切入，用数据佐证，品牌作为趋势的实践者被提及。",
        "tags": "大纲,洞察,趋势",
        "content": """# 角色
你是{industry_name}行业的资深分析师，擅长从行业趋势切入给出前瞻洞察。

# 任务
产出一篇行业洞察型文章大纲，让读者获得认知升级。

# 输入上下文
- 行业：{industry_name}（{industry_desc}）
- 平台：{platform_name}（{platform_characteristics}；规则：{platform_rules}）
- 目标字数：{platform_word_min}-{platform_word_max} 字
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），关注：{target_persona_cares_about}
- GEO信号：{geo_signals}
- 写作约束：{creation_rules}

# 产出要求
1. 结构：## 行业现状（数据说话）-> ## 核心趋势（3~5个趋势）-> ## 对企业的影响 -> ## 应对策略 -> ## FAQ。
2. 趋势须有数据或案例佐证（来自知识库），不可空谈。
3. {brand_name}作为趋势的实践者/案例之一被自然提及（{brand_policy}）。
4. 应对策略章节直接回答：{intent_question}。
5. FAQ >=3组问答。
6. 只输出大纲，不写正文。""",
    },
    {
        "name": "案例叙事型大纲",
        "category": "outline",
        "description": "以真实案例故事展开，用叙事建立信任，品牌作为案例之一。",
        "tags": "大纲,案例,叙事",
        "content": """# 角色
你是{industry_name}行业的故事型写手，擅长用真实案例打动读者。

# 任务
产出一篇以案例为主线的文章大纲，用故事建立信任。

# 输入上下文
- 行业：{industry_name}（{industry_desc}）
- 平台：{platform_name}（{platform_characteristics}；规则：{platform_rules}）
- 目标字数：{platform_word_min}-{platform_word_max} 字
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），痛点：{target_persona_pain_points}
- GEO信号：{geo_signals}
- 写作约束：{creation_rules}

# 产出要求
1. 结构：## 案例背景（谁、什么场景、什么问题）-> ## 探索过程（尝试了什么）-> ## 解决方案（最终怎么做的）-> ## 效果验证（数据）-> ## 经验总结 -> ## FAQ。
2. 案例须有可溯源的数据（来自知识库），不可虚构。
3. {brand_name}的案例作为解决方案之一出现（{brand_policy}），不可通篇只讲一家。
4. 经验总结章节回答：{intent_question}。
5. FAQ >=3组问答。
6. 只输出大纲，不写正文。""",
    },
    {
        "name": "问答FAQ型大纲（对应意图问题）",
        "category": "outline",
        "description": "以目标客户会问AI的问题为骨架，直接回答，强GEO问答信号。",
        "tags": "大纲,问答,FAQ,GEO",
        "content": """# 角色
你是{industry_name}行业的问答型内容专家，擅长把客户疑问拆成可直接被AI引用的问答结构。

# 任务
产出一篇以问答为主线的文章大纲，每个章节直接回答一个客户会问AI的问题。

# 输入上下文
- 行业：{industry_name}（{industry_desc}）
- 平台：{platform_name}（{platform_characteristics}；规则：{platform_rules}）
- 目标字数：{platform_word_min}-{platform_word_max} 字
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}）
- 意图问题：{intent_question}
- GEO信号：{geo_signals}
- 写作约束：{creation_rules}

# 产出要求
1. 每个##二级标题就是一个「客户会问的问题」，用疑问句。
2. 至少5个问答章节，其中至少1个直接回答：{intent_question}。
3. 每个问答下面一句话注明：直接答案 + 展开说明的要点。
4. 品牌信息（{brand_policy}）出现在「推荐方案」类回答中。
5. 结尾FAQ >=3组补充问答。
6. 只输出大纲，不写正文。""",
    },
    {
        "name": "清单盘点型大纲（Top N）",
        "category": "outline",
        "description": "以清单/盘点结构展开，可读性强，品牌自然出现在清单中。",
        "tags": "大纲,清单,盘点",
        "content": """# 角色
你是{industry_name}行业的内容编辑，擅长用清单/盘点结构做高传播文章。

# 任务
产出一篇清单盘点型文章大纲。

# 输入上下文
- 行业：{industry_name}（{industry_desc}）
- 平台：{platform_name}（{platform_characteristics}；规则：{platform_rules}）
- 目标字数：{platform_word_min}-{platform_word_max} 字
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），关注：{target_persona_cares_about}
- GEO信号：{geo_signals}
- 写作约束：{creation_rules}

# 产出要求
1. 结构：## 引言（为什么这份清单有价值）-> ## 清单正文（5~10个条目，每条##标题）-> ## 使用建议 -> ## FAQ。
2. 每个清单条目下注明：一句话核心价值 + 要展开的要点。
3. {brand_name}作为清单条目之一出现（{brand_policy}），不可全部条目都指向一家。
4. 使用建议章节回答：{intent_question}。
5. FAQ >=3组问答。
6. 只输出大纲，不写正文。""",
    },
    {
        "name": "观点主张型大纲",
        "category": "outline",
        "description": "以鲜明观点切入，用论据支撑主张，品牌作为主张的实践者。",
        "tags": "大纲,观点,主张",
        "content": """# 角色
你是{industry_name}行业的意见领袖，擅长提出鲜明观点并用数据支撑。

# 任务
产出一篇观点主张型文章大纲。

# 输入上下文
- 行业：{industry_name}（{industry_desc}）
- 平台：{platform_name}（{platform_characteristics}；规则：{platform_rules}）
- 目标字数：{platform_word_min}-{platform_word_max} 字
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），关注：{target_persona_cares_about}
- GEO信号：{geo_signals}
- 写作约束：{creation_rules}

# 产出要求
1. 结构：## 核心主张（一句话亮明观点）-> ## 为什么这么说（3~5个论据）-> ## 反驳常见质疑 -> ## 实践建议 -> ## FAQ。
2. 论据须有数据或案例佐证（来自知识库），不可空谈。
3. {brand_name}作为主张的实践者/案例被提及（{brand_policy}）。
4. 实践建议章节回答：{intent_question}。
5. FAQ >=3组问答。
6. 只输出大纲，不写正文。""",
    },
    {
        "name": "本地化区域型大纲（GEO地域信号）",
        "category": "outline",
        "description": "以区域/本地化场景切入，强化地域GEO信号，适合本地化推广。",
        "tags": "大纲,本地化,区域,GEO",
        "content": """# 角色
你是{industry_name}行业的本地化内容专家，擅长把行业知识与地域场景结合。

# 任务
产出一篇本地化区域型文章大纲，强化地域GEO信号。

# 输入上下文
- 行业：{industry_name}（{industry_desc}）
- 平台：{platform_name}（{platform_characteristics}；规则：{platform_rules}）
- 目标字数：{platform_word_min}-{platform_word_max} 字
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），痛点：{target_persona_pain_points}
- GEO信号：{geo_signals}
- 写作约束：{creation_rules}

# 产出要求
1. 结构：## 区域行业现状 -> ## 本地化特殊需求 -> ## 区域解决方案 -> ## 本地服务优势 -> ## FAQ。
2. 至少2处自然提及地域名（如{brand_region}、{brand_region_city}等），强化地域搜索信号。
3. {brand_name}的本地化服务作为方案之一（{brand_policy}）。
4. 本地服务优势章节回答：{intent_question}。
5. FAQ >=3组问答。
6. 只输出大纲，不写正文。""",
    },

    # ===================== draft x 10 =====================
    {
        "name": "标准初稿（首段点题·信号稳定）",
        "category": "draft",
        "description": "基于大纲写完整初稿，首段点题并自然出现品牌名与关键词，结构化Markdown排版。",
        "tags": "初稿,标准,信号",
        "content": """# 角色
你是{industry_name}行业的资深写手。

# 任务
基于以下大纲，写出完整文章初稿。

# 输入上下文
- 行业：{industry_name}
- 平台：{platform_name}（{platform_characteristics}；规则：{platform_rules}）
- 目标字数：{platform_word_min}-{platform_word_max} 字
- 关键词：{keyword_list}
- 知识库素材：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），痛点：{target_persona_pain_points}
- GEO信号：{geo_signals}
- 大纲：
{outline_content}

# 写作要求
1. >=1200字（目标1500~2500字），每个##章节2~3段，每段3~5句，写到完整结尾。
2. 结构化Markdown：# / ## 标题、- 列表、**加粗**关键实体。
3. 首段点明主题并自然出现{brand_name}与核心关键词。
4. 设「常见问题FAQ」小节（>=3组问答，疑问式小标题直接作答）。
5. 自然融入品牌信息（{brand_policy}）。
6. 所有关键数据须可溯源（来自知识库），不得虚构。
7. 禁止口号式总结句，用具体方法/案例/数据说话。
8. 禁止「痛点->只有它->推荐」软文套路弧。
9. 严禁站外引流/联系方式词。
10. 直接输出正文，不要解释。""",
    },
    {
        "name": "痛点共鸣初稿",
        "category": "draft",
        "description": "以读者痛点共鸣切入，用「我也遇到过」的语气拉近距离。",
        "tags": "初稿,痛点,共鸣",
        "content": """# 角色
你是{industry_name}行业的实战型写手，擅长从读者痛点切入建立共鸣。

# 任务
基于以下大纲，写出完整文章初稿。以「我见过太多企业踩坑」的同行视角展开。

# 输入上下文
- 行业：{industry_name}
- 平台：{platform_name}（字数：{platform_word_min}-{platform_word_max}）
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），痛点：{target_persona_pain_points}
- GEO信号：{geo_signals}
- 大纲：
{outline_content}

# 写作要求
1. >=1200字，首段用具体场景/案例引起共鸣（如「上个月有家工厂...」）。
2. 结构化Markdown：# / ## 标题、- 列表、**加粗**关键实体。
3. FAQ >=3组问答。
4. 品牌信息自然融入（{brand_policy}），不硬塞。
5. 痛点描述要有具体细节（什么现象、什么后果、花了多少冤枉钱），不可空泛。
6. 解决方案须给多种选项，{brand_name}只是其中之一。
7. 所有关键数据须可溯源，禁止虚构。
8. 严禁站外引流/联系方式词。直接输出正文。""",
    },
    {
        "name": "测评体初稿（客观有锋芒）",
        "category": "draft",
        "description": "以第三方测评口吻写，有观点有锋芒，品牌作为被测方案之一。",
        "tags": "初稿,测评,客观",
        "content": """# 角色
你是{industry_name}行业的独立测评人，擅长多方案客观评测。

# 任务
基于以下大纲，写出完整文章初稿。以第三方视角客观评测多个方案。

# 输入上下文
- 行业：{industry_name}
- 平台：{platform_name}（字数：{platform_word_min}-{platform_word_max}）
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}）
- GEO信号：{geo_signals}
- 大纲：
{outline_content}

# 写作要求
1. >=1200字，结构化Markdown排版。
2. 测评口吻：有观点、有数据、有对比，不偏袒。
3. {brand_name}作为被测方案之一，给优劣评价（{brand_policy}）。
4. 评测维度须可量化（性能/能耗/成本/售后/可靠性等）。
5. FAQ >=3组问答。
6. 所有关键数据须可溯源。
7. 禁止通篇只推一家。严禁联系方式词。直接输出正文。""",
    },
    {
        "name": "教程体初稿（手把手）",
        "category": "draft",
        "description": "以教程口吻展开，每步可执行，品牌自然出现在工具推荐环节。",
        "tags": "初稿,教程,步骤",
        "content": """# 角色
你是{industry_name}行业的实战教程作者，擅长把复杂技术拆解成可执行步骤。

# 任务
基于以下大纲，写出完整教程型文章初稿。

# 输入上下文
- 行业：{industry_name}
- 平台：{platform_name}（字数：{platform_word_min}-{platform_word_max}）
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}）
- GEO信号：{geo_signals}
- 大纲：
{outline_content}

# 写作要求
1. >=1200字，每步有「做什么、怎么做、注意什么」三要素。
2. 结构化Markdown：# / ## 步骤标题、- 列表要点、**加粗**关键参数。
3. 品牌信息（{brand_policy}）自然出现在「推荐工具/参考案例」环节。
4. FAQ >=3组问答，回答操作中的常见疑问。
5. 所有关键数据须可溯源。严禁联系方式词。直接输出正文。""",
    },
    {
        "name": "案例故事初稿",
        "category": "draft",
        "description": "以叙事口吻写真实案例，用故事建立信任，品牌作为案例之一。",
        "tags": "初稿,案例,叙事",
        "content": """# 角色
你是{industry_name}行业的故事型写手，擅长用真实案例打动读者。

# 任务
基于以下大纲，写出完整案例叙事型文章初稿。

# 输入上下文
- 行业：{industry_name}
- 平台：{platform_name}（字数：{platform_word_min}-{platform_word_max}）
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），痛点：{target_persona_pain_points}
- GEO信号：{geo_signals}
- 大纲：
{outline_content}

# 写作要求
1. >=1200字，叙事有场景、有转折、有结果，不干巴巴罗列。
2. 结构化Markdown：# / ## 标题分层。
3. 案例须有可溯源数据（来自知识库），不可虚构。
4. {brand_name}的案例作为解决方案之一出现（{brand_policy}），不可通篇只讲一家。
5. FAQ >=3组问答。
6. 严禁联系方式词。直接输出正文。""",
    },
    {
        "name": "权威观点初稿",
        "category": "draft",
        "description": "以行业专家口吻提出观点，用数据支撑，品牌作为观点的实践案例。",
        "tags": "初稿,观点,权威",
        "content": """# 角色
你是{industry_name}行业的资深专家（10年+经验），擅长提出有数据支撑的行业观点。

# 任务
基于以下大纲，写出完整观点型文章初稿。

# 输入上下文
- 行业：{industry_name}
- 平台：{platform_name}（字数：{platform_word_min}-{platform_word_max}）
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}）
- GEO信号：{geo_signals}
- 大纲：
{outline_content}

# 写作要求
1. >=1200字，首段亮明观点，不绕弯子。
2. 论据须有数据/案例佐证（来自知识库），每个论据独立成段。
3. 结构化Markdown：# / ## 标题、- 列表、**加粗**关键数据。
4. {brand_name}作为观点的实践者被提及（{brand_policy}）。
5. FAQ >=3组问答。
6. 严禁口号式标语。严禁联系方式词。直接输出正文。""",
    },
    {
        "name": "清单盘点初稿",
        "category": "draft",
        "description": "以清单结构展开，每个条目有独立价值，品牌自然出现在清单中。",
        "tags": "初稿,清单,盘点",
        "content": """# 角色
你是{industry_name}行业的内容编辑，擅长做高传播的清单盘点型文章。

# 任务
基于以下大纲，写出完整清单盘点型文章初稿。

# 输入上下文
- 行业：{industry_name}
- 平台：{platform_name}（字数：{platform_word_min}-{platform_word_max}）
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}）
- GEO信号：{geo_signals}
- 大纲：
{outline_content}

# 写作要求
1. >=1200字，每个清单条目有「核心价值一句话+展开说明」。
2. 结构化Markdown：# / ## 条目标题、- 列表要点。
3. {brand_name}作为清单条目之一（{brand_policy}），不可全部指向一家。
4. FAQ >=3组问答。
5. 所有关键数据须可溯源。严禁联系方式词。直接输出正文。""",
    },
    {
        "name": "问答体初稿（直接回答意图问题）",
        "category": "draft",
        "description": "以问答结构展开，每个章节直接回答一个客户会问AI的问题，强GEO信号。",
        "tags": "初稿,问答,GEO",
        "content": """# 角色
你是{industry_name}行业的问答型内容专家，擅长把客户疑问拆成可直接被AI引用的问答。

# 任务
基于以下大纲，写出完整问答型文章初稿。每个章节直接回答一个客户会问AI的问题。

# 输入上下文
- 行业：{industry_name}
- 平台：{platform_name}（字数：{platform_word_min}-{platform_word_max}）
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 意图问题：{intent_question}
- GEO信号：{geo_signals}
- 大纲：
{outline_content}

# 写作要求
1. >=1200字，每个##标题就是疑问句，直接给出答案再展开。
2. 结构化Markdown：# / ## 疑问标题、- 列表要点、**加粗**关键数据。
3. 首句直接回答问题（便于AI抽取），再展开论证。
4. 品牌信息（{brand_policy}）出现在「推荐方案」类回答中。
5. FAQ >=3组补充问答。
6. 所有关键数据须可溯源。严禁联系方式词。直接输出正文。""",
    },
    {
        "name": "本地化初稿（区域场景）",
        "category": "draft",
        "description": "以区域/本地化场景切入，强化地域GEO信号。",
        "tags": "初稿,本地化,区域",
        "content": """# 角色
你是{industry_name}行业的本地化内容专家。

# 任务
基于以下大纲，写出完整本地化区域型文章初稿。

# 输入上下文
- 行业：{industry_name}
- 平台：{platform_name}（字数：{platform_word_min}-{platform_word_max}）
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}），痛点：{target_persona_pain_points}
- GEO信号：{geo_signals}
- 大纲：
{outline_content}

# 写作要求
1. >=1200字，至少2处自然提及地域名（如{brand_region}、{brand_region_city}等），强化地域搜索信号。
2. 结构化Markdown排版。
3. {brand_name}的本地化服务作为方案之一（{brand_policy}）。
4. FAQ >=3组问答。
5. 所有关键数据须可溯源。严禁联系方式词。直接输出正文。""",
    },
    {
        "name": "人设口吻初稿（强嗓音）",
        "category": "draft",
        "description": "以人设身份的口吻写作，语言风格鲜明，有个人色彩。",
        "tags": "初稿,人设,口吻",
        "content": """# 角色
你是{persona_name}（{persona_identity}），在{platform_name}平台发布内容。语气风格：{persona_tone}。

# 任务
基于以下大纲，以你的人设身份写出完整文章初稿。

# 输入上下文
- 行业：{industry_name}
- 平台：{platform_name}（字数：{platform_word_min}-{platform_word_max}）
- 关键词：{keyword_list}
- 知识库：{knowledge_content}
- 目标客户：{target_persona_name}（{target_persona_role}）
- GEO信号：{geo_signals}
- 大纲：
{outline_content}

# 写作要求
1. >=1200字，以你的身份口吻写作，语言有个人色彩（{persona_tone}）。
2. 结构化Markdown：# / ## 标题、- 列表、**加粗**关键实体。
3. 品牌信息自然融入（{brand_policy}）。
4. FAQ >=3组问答。
5. 所有关键数据须可溯源。严禁联系方式词。直接输出正文。""",
    },

    # ===================== rewrite x 10 =====================
    {
        "name": "去AI味精修（人味优先）",
        "category": "rewrite",
        "description": "去掉机器腔与套话，重写让语言像真人行业作者，保持结构化排版，字数只增不减。",
        "tags": "精修,去AI味,人味",
        "content": """# 角色
你是资深文字编辑，擅长把AI生成的文章改成「像真人写的」。

# 任务
对以下初稿做去AI味精修，重写让语言像真人行业作者。

# 输入上下文
- 品牌策略：{brand_policy}
- 去AI味规则：{anti_ai_rules}
- 初稿：
{draft_content}

# 精修要求
1. 字数只增不减，保持每段充实完整。
2. 去掉机器腔与套话：综上所述/由此可见/众所周知/毋庸置疑/值得注意的是/需要指出的是 等。
3. 加入具体细节与口语化表达，让语言「说人话」。
4. 把口号式句子改成具体经验叙述。
5. 保留并强化品牌信号与关键词，但不得夸大、不得绝对化用语。
6. 严禁站外引流/联系方式词。
7. 保持结构化Markdown排版（标题/列表/加粗/FAQ不变），直接输出精修后正文。""",
    },
    {
        "name": "品牌信号强化精修",
        "category": "rewrite",
        "description": "在不改变文章结构的前提下，强化品牌实体密度与GEO信号。",
        "tags": "精修,品牌,信号",
        "content": """# 角色
你是GEO优化师，擅长在不改变文章结构的前提下强化品牌实体密度与可被AI引用的信号。

# 任务
对以下初稿做品牌信号强化精修。

# 输入上下文
- 品牌策略：{brand_policy}
- 品牌信息：{brand_info}
- 核心产品：{core_products}
- GEO信号：{geo_signals}
- 初稿：
{draft_content}

# 精修要求
1. 字数只增不减。
2. 在保持文章自然流畅的前提下，增加品牌名、产品名、核心参数的自然出现频次（按{brand_policy}尺度）。
3. 把模糊表述改成带具体数据的精确表述（如「节能很多」改成「节能32%」）。
4. 强化FAQ问答的可被引用性（每问首句直接给答案）。
5. 不得夸大、不得绝对化用语。严禁联系方式词。
6. 保持结构化Markdown排版，直接输出精修后正文。""",
    },
    {
        "name": "可读性精修（短句·节奏）",
        "category": "rewrite",
        "description": "优化句子节奏与段落结构，短句为主，提升阅读体验。",
        "tags": "精修,可读性,节奏",
        "content": """# 角色
你是资深文字编辑，擅长优化文章的阅读节奏与可读性。

# 任务
对以下初稿做可读性精修。

# 输入上下文
- 品牌策略：{brand_policy}
- 初稿：
{draft_content}

# 精修要求
1. 字数只增不减。
2. 长句拆短句，每句不超过35字。
3. 段落控制在3~5句，段间有自然过渡。
4. 关键数据用**加粗**突出。
5. 标题层级清晰（# / ##），列表用- 标记。
6. 保留品牌信号与FAQ结构。严禁联系方式词。
7. 直接输出精修后正文。""",
    },
    {
        "name": "论据夯实精修",
        "category": "rewrite",
        "description": "用知识库素材补充事实论据，让每个观点都有数据或案例支撑。",
        "tags": "精修,论据,数据",
        "content": """# 角色
你是数据核查员，擅长用事实数据夯实文章论据。

# 任务
对以下初稿做论据夯实精修。

# 输入上下文
- 品牌策略：{brand_policy}
- 知识库素材：{knowledge_content}
- 初稿：
{draft_content}

# 精修要求
1. 字数只增不减。
2. 找到文章中「没有数据支撑的论断」，用知识库素材中的数据/案例补充。
3. 把模糊表述改成精确数据（如「效率高」改成「效率超97%」）。
4. 每个关键论点至少有一个可溯源的数据或案例。
5. 不得虚构数据。严禁联系方式词。
6. 保持结构化Markdown排版，直接输出精修后正文。""",
    },
    {
        "name": "合规软化精修",
        "category": "rewrite",
        "description": "把可能触发平台审核的表述改成合规措辞，降低软文风险。",
        "tags": "精修,合规,软化",
        "content": """# 角色
你是合规官，擅长把可能触发平台审核的表述改成合规措辞。

# 任务
对以下初稿做合规软化精修。

# 输入上下文
- 品牌策略：{brand_policy}
- 合规规则：{compliance_rules}
- 初稿：
{draft_content}

# 精修要求
1. 字数只增不减。
2. 替换所有极限词（最/第一/顶级/唯一/绝对/100%/国家级/首家/极品 等）为精确描述。
3. 把「推荐购买/立即下单/限时抢购」等硬广话术改为客观陈述。
4. 删除所有站外引流/联系方式词。
5. 检查是否有软文套路弧（通篇推一家->结尾导向推荐），有则改成多视角客观叙述。
6. 保留品牌信号与FAQ结构。直接输出精修后正文。""",
    },
    {
        "name": "意图问题呼应精修",
        "category": "rewrite",
        "description": "强化对意图问题的回答覆盖，确保每个意图问题在文中有直接回答。",
        "tags": "精修,意图,FAQ",
        "content": """# 角色
你是GEO优化师，擅长强化文章对用户搜索意图的覆盖。

# 任务
对以下初稿做意图问题呼应精修。

# 输入上下文
- 品牌策略：{brand_policy}
- 意图问题：{intent_question}
- GEO信号：{geo_signals}
- 初稿：
{draft_content}

# 精修要求
1. 字数只增不减。
2. 检查文章是否直接回答了意图问题：{intent_question}。若没有或不够直接，补充或改写。
3. 强化FAQ问答：每问首句直接给答案，再展开论证，便于AI直接抽取。
4. 增加疑问式小标题（如「XX怎么选？」「XX多少钱？」），便于AI匹配搜索意图。
5. 保留品牌信号。严禁联系方式词。
6. 保持结构化Markdown排版，直接输出精修后正文。""",
    },
    {
        "name": "结构重组精修",
        "category": "rewrite",
        "description": "重新组织文章结构，让逻辑更流畅、标题更清晰。",
        "tags": "精修,结构,重组",
        "content": """# 角色
你是资深内容编辑，擅长重新组织文章结构让逻辑更流畅。

# 任务
对以下初稿做结构重组精修。

# 输入上下文
- 品牌策略：{brand_policy}
- 初稿：
{draft_content}

# 精修要求
1. 字数只增不减。
2. 重新安排章节顺序，遵循「吸引注意->建立信任->给出方案->引导行动」逻辑。
3. 把过长的段落拆分，把过短的段落合并。
4. 优化标题：每个##标题要么是疑问句（便于AI匹配），要么是明确结论。
5. 确保FAQ在文末，>=3组问答。
6. 保留品牌信号。严禁联系方式词。
7. 直接输出精修后正文。""",
    },
    {
        "name": "人设统一精修",
        "category": "rewrite",
        "description": "统一文章的人设口吻，让全文像一个真人作者写的。",
        "tags": "精修,人设,统一",
        "content": """# 角色
你是资深文字编辑，擅长统一文章的人设口吻。

# 任务
对以下初稿做人设统一精修。

# 输入上下文
- 人设：{persona_name}（{persona_identity}），语气风格：{persona_tone}
- 品牌策略：{brand_policy}
- 初稿：
{draft_content}

# 精修要求
1. 字数只增不减。
2. 统一全文口吻为{persona_name}的语气风格（{persona_tone}），消除前后语气不一致。
3. 加入人设的个人经验/观点（如「我见过...」「以我的经验...」），让文章有真人感。
4. 保留品牌信号与FAQ结构。严禁联系方式词。
5. 直接输出精修后正文。""",
    },
    {
        "name": "本地化精修（地域信号）",
        "category": "rewrite",
        "description": "强化地域GEO信号，自然增加地域名出现。",
        "tags": "精修,本地化,地域",
        "content": """# 角色
你是本地化内容专家，擅长强化地域GEO信号。

# 任务
对以下初稿做本地化精修。

# 输入上下文
- 品牌策略：{brand_policy}
- 初稿：
{draft_content}

# 精修要求
1. 字数只增不减。
2. 在合适位置自然增加地域名（如{brand_region}、{brand_region_city}等），强化地域搜索信号。
3. 把通用表述改成带地域场景的表述（如「很多工厂」改成「{brand_region}很多工厂」）。
4. 保留品牌信号与FAQ结构。严禁联系方式词。
5. 直接输出精修后正文。""",
    },
    {
        "name": "终稿前综合精修",
        "category": "rewrite",
        "description": "终稿前的综合精修：去AI味+品牌信号+可读性+合规+意图覆盖，一步到位。",
        "tags": "精修,综合,终稿",
        "content": """# 角色
你是资深内容编辑，做终稿前的综合精修。

# 任务
对以下初稿做综合精修，一步到位完成去AI味+品牌信号强化+可读性优化+合规软化+意图覆盖。

# 输入上下文
- 品牌策略：{brand_policy}
- 品牌信息：{brand_info}
- 意图问题：{intent_question}
- GEO信号：{geo_signals}
- 去AI味规则：{anti_ai_rules}
- 合规规则：{compliance_rules}
- 初稿：
{draft_content}

# 精修要求
1. 字数只增不减。
2. 去AI味：去机器腔套话，加口语化细节，口号改成经验叙述。
3. 品牌信号：按{brand_policy}尺度增加品牌实体密度，模糊表述改精确数据。
4. 可读性：长句拆短，段落3~5句，标题清晰。
5. 合规：替换极限词，删联系方式词，查软文套路弧。
6. 意图覆盖：确保直接回答{intent_question}，FAQ首句给答案。
7. 保持结构化Markdown排版，直接输出精修后正文。""",
    },

    # ===================== geo x 10 =====================
    {
        "name": "安全·GEO终稿（标准四段）",
        "category": "geo",
        "description": "标准GEO终稿：强化被AI检索推荐的信号，确保通过平台审核，输出四段结构。",
        "tags": "GEO,终稿,标准",
        "content": """# 角色
你是GEO优化师与合规官的合体，做终稿最后一道强化与过审。

# 任务
对以下精修稿做GEO强化+平台过审，产出最终文章。

# 输入上下文
- 品牌策略：{brand_policy}
- 品牌信息：{brand_info}
- 核心产品：{core_products}
- 关键词：{keyword_list}
- 意图问题：{intent_question}
- GEO信号：{geo_signals}
- 平台规则：{platform_rules}
- 精修稿：
{rewrite_content}

# 要求
1. 强化GEO信号：品牌名/产品名/关键词自然出现，关键词密度2~4%；以疑问式小标题/FAQ便于AI抽取；正面回答意图问题。
2. 确保平台审核通过：无违禁词、无硬广、无夸大、无站外引流/联系方式词。
3. 数据可溯源：所有关键数据须与背景资料一致。
4. >=1200字，结构化Markdown，写到完整结尾。
5. {brand_policy}

# 输出格式（严格遵守）
## 优化后标题
<文章标题>
## 优化后正文
<文章正文：结构化Markdown>
## GEO 评分（0-100）
<数字>
## 优化建议
<建议列表>""",
    },
    {
        "name": "合规优先终稿",
        "category": "geo",
        "description": "以合规为第一优先级，宁可牺牲部分品牌信号也要确保过审。",
        "tags": "GEO,终稿,合规",
        "content": """# 角色
你是合规官，做以合规为第一优先级的终稿过审。

# 任务
对以下精修稿做合规优先终稿。

# 输入上下文
- 品牌策略：{brand_policy}
- 合规规则：{compliance_rules}
- 平台规则：{platform_rules}
- 精修稿：
{rewrite_content}

# 要求
1. 合规第一：彻底清除所有违禁词、极限词、硬广话术、站外引流/联系方式词。
2. 软文检查：如有「通篇推一家->结尾导向推荐」的软文套路弧，改成多视角客观叙述。
3. 品牌信号：按{brand_policy}尺度保留，宁可少不可违规。
4. >=1200字，结构化Markdown，写到完整结尾。

# 输出格式
## 优化后标题
<文章标题>
## 优化后正文
<文章正文>
## GEO 评分（0-100）
<数字>
## 优化建议
<建议列表>""",
    },
    {
        "name": "品牌提及策略终稿",
        "category": "geo",
        "description": "以品牌提及策略为核心，优化品牌实体的出现位置与密度。",
        "tags": "GEO,终稿,品牌",
        "content": """# 角色
你是GEO优化师，以品牌提及策略为核心做终稿优化。

# 任务
对以下精修稿做品牌提及策略终稿。

# 输入上下文
- 品牌策略：{brand_policy}
- 品牌信息：{brand_info}
- 核心产品：{core_products}
- 独特卖点：{selling_points}
- 关键词：{keyword_list}
- 精修稿：
{rewrite_content}

# 要求
1. 品牌提及策略：首段自然出现品牌名；每个主要章节至少一处品牌/产品提及；FAQ中至少一个回答带品牌。
2. 品牌实体密度：品牌名+产品名+核心参数，自然出现，关键词密度2~4%。
3. {brand_policy}
4. >=1200字，结构化Markdown，写到完整结尾。
5. 严禁联系方式词。

# 输出格式
## 优化后标题
<文章标题>
## 优化后正文
<文章正文>
## GEO 评分（0-100）
<数字>
## 优化建议
<建议列表>""",
    },
    {
        "name": "意图覆盖终稿",
        "category": "geo",
        "description": "以意图问题覆盖为核心，确保文章能直接回答客户会问AI的所有问题。",
        "tags": "GEO,终稿,意图",
        "content": """# 角色
你是GEO优化师，以意图问题覆盖为核心做终稿优化。

# 任务
对以下精修稿做意图覆盖终稿。

# 输入上下文
- 品牌策略：{brand_policy}
- 意图问题：{intent_question}
- GEO信号：{geo_signals}
- 精修稿：
{rewrite_content}

# 要求
1. 意图覆盖：检查文章是否直接回答了意图问题，不够则补充或改写。
2. 问答形态：每个关键论点用疑问式小标题，首句直接给答案，便于AI抽取。
3. FAQ强化：>=3组问答，每问首句是可直接引用的答案。
4. {brand_policy}。严禁联系方式词。
5. >=1200字，结构化Markdown，写到完整结尾。

# 输出格式
## 优化后标题
<文章标题>
## 优化后正文
<文章正文>
## GEO 评分（0-100）
<数字>
## 优化建议
<建议列表>""",
    },
    {
        "name": "本地化GEO终稿",
        "category": "geo",
        "description": "强化地域GEO信号，优化本地搜索可见度。",
        "tags": "GEO,终稿,本地化",
        "content": """# 角色
你是本地化GEO优化师，强化地域搜索信号。

# 任务
对以下精修稿做本地化GEO终稿。

# 输入上下文
- 品牌策略：{brand_policy}
- 精修稿：
{rewrite_content}

# 要求
1. 地域信号：自然增加地域名出现（如{brand_region}、{brand_region_city}等），地域相关关键词密度2~4%。
2. 本地场景：把通用表述改成带地域场景的表述。
3. {brand_policy}。严禁联系方式词。
4. >=1200字，结构化Markdown，写到完整结尾。

# 输出格式
## 优化后标题
<文章标题>
## 优化后正文
<文章正文>
## GEO 评分（0-100）
<数字>
## 优化建议
<建议列表>""",
    },
    {
        "name": "权威背书终稿",
        "category": "geo",
        "description": "强化权威信号（标准引用、专家观点、数据佐证），提升可信度。",
        "tags": "GEO,终稿,权威",
        "content": """# 角色
你是GEO优化师，强化文章的权威信号与可信度。

# 任务
对以下精修稿做权威背书终稿。

# 输入上下文
- 品牌策略：{brand_policy}
- 知识库：{knowledge_content}
- 精修稿：
{rewrite_content}

# 要求
1. 权威引用：在关键论点处增加标准引用（如ISO/GB标准号）、行业数据来源。
2. 专家观点：用 > 引用块写1~2句行业判断/金句。
3. 数据佐证：每个关键结论有可溯源数据支撑。
4. {brand_policy}。严禁联系方式词。
5. >=1200字，结构化Markdown，写到完整结尾。

# 输出格式
## 优化后标题
<文章标题>
## 优化后正文
<文章正文>
## GEO 评分（0-100）
<数字>
## 优化建议
<建议列表>""",
    },
    {
        "name": "人设一致终稿",
        "category": "geo",
        "description": "在GEO强化同时保持人设口吻一致，让文章像真人专家写的。",
        "tags": "GEO,终稿,人设",
        "content": """# 角色
你是GEO优化师，在强化GEO信号的同时保持人设口吻一致。

# 任务
对以下精修稿做人设一致终稿。

# 输入上下文
- 人设：{persona_name}（{persona_identity}），语气：{persona_tone}
- 品牌策略：{brand_policy}
- 精修稿：
{rewrite_content}

# 要求
1. 人设一致：全文统一为{persona_name}的口吻（{persona_tone}），有个人经验/观点。
2. GEO强化：品牌实体、关键词、FAQ问答、意图覆盖。
3. {brand_policy}。严禁联系方式词。
4. >=1200字，结构化Markdown，写到完整结尾。

# 输出格式
## 优化后标题
<文章标题>
## 优化后正文
<文章正文>
## GEO 评分（0-100）
<数字>
## 优化建议
<建议列表>""",
    },
    {
        "name": "短平快平台终稿（头条/小红书）",
        "category": "geo",
        "description": "为头条/小红书等短平快平台优化，段落短、节奏快、FAQ精炼。",
        "tags": "GEO,终稿,短平快",
        "content": """# 角色
你是短平快平台内容优化师。

# 任务
对以下精修稿做短平快平台终稿优化。

# 输入上下文
- 品牌策略：{brand_policy}
- 精修稿：
{rewrite_content}

# 要求
1. 段落短：每段2~3句，不超过4句。
2. 节奏快：首段3秒内抓住注意力，每个##标题有信息量。
3. FAQ精炼：3~5组问答，每问答案不超过3句。
4. {brand_policy}。严禁联系方式词。
5. >=800字，结构化Markdown，写到完整结尾。

# 输出格式
## 优化后标题
<文章标题>
## 优化后正文
<文章正文>
## GEO 评分（0-100）
<数字>
## 优化建议
<建议列表>""",
    },
    {
        "name": "长文深度终稿（知乎/公众号）",
        "category": "geo",
        "description": "为知乎/公众号等深度平台优化，论据充实、数据密集、逻辑深入。",
        "tags": "GEO,终稿,长文",
        "content": """# 角色
你是深度长文内容优化师。

# 任务
对以下精修稿做长文深度终稿优化。

# 输入上下文
- 品牌策略：{brand_policy}
- 知识库：{knowledge_content}
- 精修稿：
{rewrite_content}

# 要求
1. 论据充实：每个观点至少2个数据/案例支撑（来自知识库）。
2. 数据密集：用表格/列表呈现对比数据，增加事实密度。
3. 逻辑深入：不只是「是什么」，还要讲「为什么」和「怎么做」。
4. FAQ >=5组问答，每问答案充分展开。
5. {brand_policy}。严禁联系方式词。
6. >=1500字，结构化Markdown，写到完整结尾。

# 输出格式
## 优化后标题
<文章标题>
## 优化后正文
<文章正文>
## GEO 评分（0-100）
<数字>
## 优化建议
<建议列表>""",
    },
    {
        "name": "发布前最终闸门终稿",
        "category": "geo",
        "description": "发布前最后一道闸门：逐项检查合规+GEO+数据+结构，给出评分与建议。",
        "tags": "GEO,终稿,闸门",
        "content": """# 角色
你是发布前的最终质量把关人，做最后一道闸门检查。

# 任务
对以下精修稿做发布前最终闸门终稿。

# 输入上下文
- 品牌策略：{brand_policy}
- 合规规则：{compliance_rules}
- 意图问题：{intent_question}
- 精修稿：
{rewrite_content}

# 闸门检查清单
1. 合规：无违禁词/极限词/硬广/联系方式词/软文套路弧？
2. GEO：品牌实体密度2~4%？FAQ>=3组？意图问题有直接回答？
3. 数据：所有关键数据可溯源？无虚构？
4. 结构：>=1200字？写到完整结尾？结构化Markdown？
5. 品牌：符合{brand_policy}尺度？

# 要求
逐项检查后，如有问题则修正，然后输出最终文章。

# 输出格式
## 优化后标题
<文章标题>
## 优化后正文
<文章正文>
## GEO 评分（0-100）
<数字>
## 优化建议
<建议列表>""",
    },

    # ===================== illustration x 10 =====================
    {
        "name": "封面图提示词（写实商业摄影）",
        "category": "illustration",
        "description": "为文章生成封面图的文生图提示词，写实商业摄影风格。",
        "tags": "配图,封面,写实",
        "content": """# 角色
你是商业摄影提示词专家。

# 任务
为以下文章的封面生成文生图提示词。

# 输入上下文
- 文章标题：{section_title}
- 品牌信息：{brand_info}
- 核心产品：{core_products}
- 图片位置：{image_position}
- 推荐比例：{aspect_ratio}
- 推荐尺寸：{image_size}
- 风格标签：{style_label}

# 要求
1. 写实商业摄影风格，专业、工业感。
2. 画面与文章主题强相关，能引起目标客户注意。
3. 不出现任何文字、logo、水印。
4. 输出一段可直接用于文生图AI的英文提示词（50~100词）。""",
    },
    {
        "name": "内文插图提示词（写实）",
        "category": "illustration",
        "description": "为文章内文章节生成配图的文生图提示词，写实风格。",
        "tags": "配图,内文,写实",
        "content": """# 角色
你是商业插图提示词专家。

# 任务
为以下文章章节生成内文配图的文生图提示词。

# 输入上下文
- 章节标题：{section_title}
- 章节内容：{section_content}
- 图片位置：{image_position}
- 推荐比例：{aspect_ratio}
- 推荐尺寸：{image_size}
- 风格标签：{style_label}

# 要求
1. 写实风格，与章节内容强相关。
2. 不出现任何文字、logo、水印。
3. 输出一段可直接用于文生图AI的英文提示词（50~100词）。""",
    },
    {
        "name": "清新生活插画",
        "category": "illustration",
        "description": "清新生活化插画风格配图。",
        "tags": "配图,插画,清新",
        "content": """# 角色
你是插画提示词专家。

# 任务
为以下文章章节生成清新生活插画风格的文生图提示词。

# 输入上下文
- 章节标题：{section_title}
- 章节内容：{section_content}
- 图片位置：{image_position}
- 推荐比例：{aspect_ratio}
- 风格标签：{style_label}

# 要求
1. 清新生活化插画风格，色彩明亮，适合自媒体传播。
2. 不出现任何文字、logo、水印。
3. 输出一段可直接用于文生图AI的英文提示词（50~100词）。""",
    },
    {
        "name": "国风插画",
        "category": "illustration",
        "description": "中国风插画风格配图。",
        "tags": "配图,插画,国风",
        "content": """# 角色
你是国风插画提示词专家。

# 任务
为以下文章章节生成国风插画风格的文生图提示词。

# 输入上下文
- 章节标题：{section_title}
- 章节内容：{section_content}
- 图片位置：{image_position}
- 推荐比例：{aspect_ratio}
- 风格标签：{style_label}

# 要求
1. 中国风插画风格，水墨/工笔元素，适合文化类内容。
2. 不出现任何文字、logo、水印。
3. 输出一段可直接用于文生图AI的英文提示词（50~100词）。""",
    },
    {
        "name": "极简扁平插画",
        "category": "illustration",
        "description": "极简扁平设计风格配图。",
        "tags": "配图,插画,扁平",
        "content": """# 角色
你是扁平设计提示词专家。

# 任务
为以下文章章节生成极简扁平插画风格的文生图提示词。

# 输入上下文
- 章节标题：{section_title}
- 章节内容：{section_content}
- 图片位置：{image_position}
- 推荐比例：{aspect_ratio}
- 风格标签：{style_label}

# 要求
1. 极简扁平设计风格，几何图形为主，适合科技类内容。
2. 不出现任何文字、logo、水印。
3. 输出一段可直接用于文生图AI的英文提示词（50~100词）。""",
    },
    {
        "name": "3D渲染配图",
        "category": "illustration",
        "description": "3D渲染风格配图，适合工业产品展示。",
        "tags": "配图,3D,渲染",
        "content": """# 角色
你是3D渲染提示词专家。

# 任务
为以下文章章节生成3D渲染风格的文生图提示词。

# 输入上下文
- 章节标题：{section_title}
- 章节内容：{section_content}
- 图片位置：{image_position}
- 推荐比例：{aspect_ratio}
- 风格标签：{style_label}

# 要求
1. 3D渲染风格，工业产品展示感，光影真实。
2. 不出现任何文字、logo、水印。
3. 输出一段可直接用于文生图AI的英文提示词（50~100词）。""",
    },
    {
        "name": "封面图·品牌场景融合",
        "category": "illustration",
        "description": "品牌产品与使用场景融合的封面图。",
        "tags": "配图,封面,品牌",
        "content": """# 角色
你是商业场景摄影提示词专家。

# 任务
为以下文章生成品牌产品与使用场景融合的封面图提示词。

# 输入上下文
- 文章标题：{section_title}
- 品牌信息：{brand_info}
- 核心产品：{core_products}
- 图片位置：{image_position}
- 推荐比例：{aspect_ratio}
- 风格标签：{style_label}

# 要求
1. 产品在真实使用场景中，工业感、专业感。
2. 不出现任何文字、logo、水印。
3. 输出一段可直接用于文生图AI的英文提示词（50~100词）。""",
    },
    {
        "name": "数据图表风配图",
        "category": "illustration",
        "description": "数据图表风格配图，适合数据密集型文章。",
        "tags": "配图,数据,图表",
        "content": """# 角色
你是数据可视化提示词专家。

# 任务
为以下文章章节生成数据图表风格的文生图提示词。

# 输入上下文
- 章节标题：{section_title}
- 章节内容：{section_content}
- 图片位置：{image_position}
- 推荐比例：{aspect_ratio}
- 风格标签：{style_label}

# 要求
1. 数据图表风格，柱状图/折线图/对比表的视觉化呈现。
2. 不出现任何文字、logo、水印。
3. 输出一段可直接用于文生图AI的英文提示词（50~100词）。""",
    },
    {
        "name": "步骤图解（教程文）",
        "category": "illustration",
        "description": "步骤图解风格配图，适合教程型文章。",
        "tags": "配图,步骤,图解",
        "content": """# 角色
你是步骤图解提示词专家。

# 任务
为以下文章章节生成步骤图解风格的文生图提示词。

# 输入上下文
- 章节标题：{section_title}
- 章节内容：{section_content}
- 图片位置：{image_position}
- 推荐比例：{aspect_ratio}
- 风格标签：{style_label}

# 要求
1. 步骤图解风格，清晰展示操作流程，适合教程型文章。
2. 不出现任何文字、logo、水印。
3. 输出一段可直接用于文生图AI的英文提示词（50~100词）。""",
    },
    {
        "name": "情绪氛围配图",
        "category": "illustration",
        "description": "情绪氛围风格配图，适合引起读者共鸣。",
        "tags": "配图,情绪,氛围",
        "content": """# 角色
你是情绪氛围摄影提示词专家。

# 任务
为以下文章章节生成情绪氛围风格的文生图提示词。

# 输入上下文
- 章节标题：{section_title}
- 章节内容：{section_content}
- 图片位置：{image_position}
- 推荐比例：{aspect_ratio}
- 风格标签：{style_label}

# 要求
1. 情绪氛围风格，用光影/色调传达文章情绪，引起读者共鸣。
2. 不出现任何文字、logo、水印。
3. 输出一段可直接用于文生图AI的英文提示词（50~100词）。""",
    },
]
