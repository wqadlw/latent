/**
 * 软文生产（Production）的纯数据常量。
 *
 * 为什么单独成文件：`Production.vue` 的 script 曾有 810 行，其中约 90 行是**纯配置**
 * （步骤表、规则分组元信息、GEO 维度提示语、分类→字段映射）。这些既不是状态也不是逻辑，
 * 混在视图里只会把「这一步到底做了什么」淹没掉。
 *
 * ⚠️ 这里只放**纯数据**。任何需要 `currentTask` / `options` / API 的东西都属于
 * `src/composables/production/`，不要往这里塞。
 */

/* ============ 十步流程 ============ */

/**
 * 步骤表。`no` 必须与后端 `production_task.current_step` 的取值域一致（1–10）。
 * `hint` 是步骤节点下的小字英文副标题，纯展示。
 *
 * ⚠️ 步骤 11（GEO 评分闸门）已被合并进第 9 步，不要再加回第 11 项 ——
 * 后端 `current_step` 只到 10，多加一项会让 `step.no` 与进度条分母对不上。
 */
export const PRODUCTION_STEPS = [
  { no: 1, name: '选行业', hint: 'Industry' },
  { no: 2, name: '选平台', hint: 'Platform' },
  { no: 3, name: '定人设', hint: 'Persona' },
  { no: 4, name: '目标客户需求', hint: 'GEO 作战' },
  { no: 5, name: '关键词&知识点', hint: 'Keywords & Knowledge' },
  { no: 6, name: '生成大纲', hint: 'Outline' },
  { no: 7, name: '生成初稿', hint: 'Draft' },
  { no: 8, name: 'AI洗稿', hint: 'Rewrite' },
  { no: 9, name: '安全发布 & GEO 筛选', hint: 'Safety & GEO' },
  { no: 10, name: '配图', hint: 'Illustration' },
]

/** 进度条分母。与 PRODUCTION_STEPS.length 绑定，避免两处各写一个 10。 */
export const PRODUCTION_TOTAL_STEPS = PRODUCTION_STEPS.length

/* ============ 第 3 步：规则约束分组 ============ */

/**
 * 规则类型 → 展示元信息。`color` 只用于分组标题的小圆点，
 * 归 JS 是因为它随分组类型走、不进 CSS 类名体系。
 */
export const RULE_TYPE_META = {
  ai_seo: { label: 'AI SEO 规则', color: '#6366f1', desc: '优化关键词布局与搜索收录' },
  anti_ai: { label: '去 AI 味', color: '#a855f7', desc: '消除机器套话，更像真人写作' },
  compliance: { label: '平台合规', color: '#f59e0b', desc: '规避极限词与违规风险' },
}

/** 分组展示顺序（只展示该行业下确实有规则的类型）。 */
export const RULE_TYPE_ORDER = ['ai_seo', 'anti_ai', 'compliance']

/* ============ 第 9 步：GEO 双信任维度 ============ */

/**
 * 算法信任维度（AI 可提取性）→ 中文名 + 优化手法。
 * key 必须与后端 `geo_score` 返回的 `dimensions` / `weights` 对齐。
 */
export const GEO_DIM_META = {
  entity_signals: { label: '品牌实体信号', tip: '在文中自然、可归属地补充品牌实体：品牌名、官网链接、联系方式、核心产品至少各出现 1 次，最好出现在"据 XX 官方案例"这类语境中。' },
  fact_density: { label: '事实密度', tip: '为每个核心论点补充可量化数据（具体数字+单位、百分比、案例数量），替换空泛形容词。' },
  intent_coverage: { label: '意图覆盖', tip: '围绕目标客户的真实意图问题展开，并自然植入"期望 AI 推荐我们的角度"。' },
  qa_form: { label: '问答形态', tip: '采用问答/FAQ 形态或疑问式小标题，便于 AI 直接抽取答案。' },
  structure: { label: '结构可提取', tip: '补充清晰标题层级与小标题/列表，提升可被解析为结构化答案的概率。' },
  attributable: { label: '信号可归属', tip: '增加可溯源证据（据…显示、客户案例、实测数据），让 AI 能引用。' },
}

/**
 * 心智温度维度（人感与共鸣）→ 中文名 + 优化手法。
 * key 必须与后端 `geo_score` 返回的 `mind_resonance.dimensions` 对齐。
 */
export const MIND_DIM_META = {
  storytelling: { label: '叙事感', tip: '用「背景→问题→方案→结果」讲故事，加入时间/事件标记（如「去年」「有一次」「后来」），让内容有叙事线索而非说明书。' },
  scenario: { label: '场景化', tip: '加入真实场景描述与客户故事（如「某客户在…时」「李总说」），让读者身临其境。' },
  reader_perspective: { label: '读者视角', tip: '多用「你」「你的」「如果你」直接对话读者，直击其顾虑与纠结。' },
  language_warmth: { label: '语言温度', tip: '加入口语化表达（「其实」「说白了」「讲真」），减少公文腔与说明书式冰冷表达。' },
  pain_resonance: { label: '痛点共鸣', tip: '把客户的「怕」「担心」「纠结」具体写出来，引发情感共鸣而非泛泛列举痛点。' },
}

/** 维度 key → 中文名；未知 key 原样返回（后端加维度时不至于显示成 undefined）。 */
export const geoDimLabel = (k) => (GEO_DIM_META[k] || {}).label || k
export const mindDimLabel = (k) => (MIND_DIM_META[k] || {}).label || k

/* ============ 写作步骤 ↔ 提示词分类 ↔ 任务字段 ============ */

/**
 * 步骤号 → 提示词分类。只有 6–9 步需要提示词。
 */
export const STEP_TO_CAT = { 6: 'outline', 7: 'draft', 8: 'rewrite', 9: 'geo' }

/** 分类 → 提示词 id 字段。⚠️ `geo` 与 `safety` 都指向 `safety_prompt_id`，不是笔误。 */
export const CAT_PROMPT_FIELD = {
  outline: 'outline_prompt_id',
  draft: 'draft_prompt_id',
  rewrite: 'rewrite_prompt_id',
  geo: 'safety_prompt_id',
}

/** 分类 → 内容字段。 */
export const CAT_CONTENT_FIELD = {
  outline: 'outline_content',
  draft: 'draft_content',
  rewrite: 'rewrite_content',
  geo: 'final_content',
}

/** 分类 → 中文名（用于「已写入初稿」这类提示）。 */
export const CAT_LABEL = { outline: '大纲', draft: '初稿', rewrite: '精修稿', geo: '最终文章' }

/**
 * 渲染提示词时的分类 → 提示词 id 字段。
 *
 * ⚠️ 曾与 CAT_PROMPT_FIELD 是**两份重复字面量**，且多了一个 `safety` 键
 * （渲染走 `safety`，生成走 `geo`，实际指同一字段）。合并为一份，
 * 并保留 `safety` 别名 —— 旧调用点传的是 `safety`。
 */
export const PROMPT_FIELD_BY_CATEGORY = { ...CAT_PROMPT_FIELD, safety: 'safety_prompt_id' }

/* ============ 第 4 步：目标客户需求 ============ */

/** `target_needs` 缺字段/格式损坏时的兜底结构。 */
export const TARGET_NEEDS_DEFAULT = {
  expected_recommendation: '',
  required_signals: [],
  must_address_pains: [],
}
