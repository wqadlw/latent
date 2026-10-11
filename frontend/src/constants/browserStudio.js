/**
 * 浏览器工作室（AI 创作运行）的展示常量与标签映射。
 *
 * 为什么单独成文件：这些映射原本长在 BrowserStudio.vue 的 script 里，
 * 但它们是**纯数据**——不依赖组件状态、不参与渲染逻辑，只是「枚举 → 中文」的翻译表。
 * 把它们和视图逻辑混在一起，会让 1500 行的视图更难读，也没法被其它页面（如流水线工作台）复用。
 *
 * 注意：运行状态（run.status）与步骤状态（step.status）是**两套**枚举，不要混用。
 * 后端取值见 app/models.py 与 app/services/doubao_studio.py。
 */

import { MODE_LABEL } from './modes'
import {
  TASK_STATUS_LABEL,
  TASK_STATUS_TYPE,
  STEP_STATUS_LABEL as _STEP_STATUS_LABEL,
  STEP_STATUS_TYPE as _STEP_STATUS_TYPE,
  taskStatusLabel,
  taskStatusType,
  stepStatusLabel,
  stepStatusType,
} from './status'

/**
 * 运行状态 —— 已上收到 constants/status.js。
 *
 * 为什么不再在这里定义：`run.status` 就是 `production_task.status`，同一个 DB 列。
 * 这里一份、Pipeline.vue 一份、仪表盘一份，三份文案已经互相漂移
 * （await_confirm 是「待你确认」还是「等待确认」？confirmed 是「已确认」还是「已入库」？）。
 * 保留这两个别名只为兼容既有 import，新代码请直接用 constants/status.js。
 */
export const RUN_STATUS_LABEL = TASK_STATUS_LABEL
export const RUN_STATUS_TYPE = TASK_STATUS_TYPE

/** 步骤状态 —— 同样已上收到 constants/status.js（pipeline_step.status，同一列） */
export const STEP_STATUS_LABEL = _STEP_STATUS_LABEL
export const STEP_STATUS_TYPE = _STEP_STATUS_TYPE

/** 执行角色 → 中文（带 emoji，用于步骤行与专家团队） */
export const AGENT_LABEL = {
  planner: '📋 主编',
  writer: '✍️ 写手',
  dual: '📋✍️ 双角色',
  system: '⚙️ 系统',
}

/** AI 引擎 → 中文 */
export const ENGINE_LABEL = {
  deepseek: 'DeepSeek',
  doubao: '豆包',
  mock: '模拟演示',
}

/** GEO 六维：标签与权重（权重之和 = 100） */
export const DIM_LABELS = {
  entity_signals: '实体信号',
  fact_density: '事实密度',
  intent_coverage: '意图覆盖',
  qa_form: '问答形态',
  structure: '结构可提取',
  attributable: '信号可归属',
}
export const DIM_WEIGHTS = {
  entity_signals: 25,
  fact_density: 20,
  intent_coverage: 20,
  qa_form: 15,
  structure: 10,
  attributable: 10,
}

/** 心智温度五维（满分 25 分制，人感评分） */
export const MIND_LABELS = {
  storytelling: '叙事感',
  scenario: '场景化',
  reader_perspective: '读者视角',
  language_warmth: '语言温度',
  pain_resonance: '痛点共鸣',
}

/** 客户画像角色 → 中文 */
export const ROLE_LABEL = {
  decision_maker: '决策层',
  technical: '技术层',
  procurement: '采购层',
}

/** 规则类型 → 中文 */
export const RULE_TYPE_LABEL = {
  ai_seo: 'AI SEO',
  anti_ai: '去AI味',
  compliance: '合规',
  creation: '创作',
}

/** 新建向导：AI 引擎卡片选项 */
export const ENGINE_OPTIONS = [
  {
    value: 'deepseek',
    label: 'DeepSeek（API）',
    desc: '多专家协同：主编(总协调)用 deepseek-v4-pro+thinking 推理做规划/评审/整改；写手用同模型非推理落地；合规官/GEO优化师/数据核查员由系统自检+主编评审共同把关',
    recommend: true,
  },
  {
    value: 'doubao',
    label: '豆包（浏览器自动化）',
    desc: '真实打开豆包官网，自动复制粘贴对话（需上传豆包 cookie）',
    recommend: false,
  },
  {
    value: 'mock',
    label: '模拟演示',
    desc: '无需任何配置，直接跑通全流程用于验证',
    recommend: false,
  },
]

/** 流水线全景（新建向导顶部展示，与后端 STEP_ORDER 的展示口径一致） */
export const PIPELINE_STEPS = [
  '连接引擎', '主编·明晰', '主编·大纲', '写手·初稿', '写手·精修',
  '写手·GEO终稿', '主编·评审', '闭环整改', '满意确认', '发布平台',
]

/** 本运行自动带入的系统内容（强调「已内置全部内容」） */
export const AUTO_CONTEXT_TAGS = [
  '目标需求', '品牌资产', '账号人设', '知识库', '关键词', '规则库', '客户画像', '意图问题库',
]

/** 多专家协同团队（新建向导中展示） */
export const EXPERT_TEAM = [
  { role: '主编', tag: 'agent-planner', desc: '总协调：定方向、定大纲、终审把关、下达整改指令' },
  { role: '写手', tag: 'agent-writer', desc: '落地：初稿 / 去AI味 / GEO终稿 / 按指令改写' },
  { role: '合规官', tag: 'agent-compliance', desc: '平台合规红线：违禁词 / 硬广 / 站外引流 / 联系方式' },
  { role: 'GEO优化师', tag: 'agent-geo', desc: '搜索可见性：品牌实体 / 关键词 / FAQ / 意图覆盖' },
  { role: '数据核查员', tag: 'agent-fact', desc: '事实与数据：不夸大、不虚构、可溯源' },
]

// ============ 取值函数 ============

export const statusLabel = taskStatusLabel
export const statusType = taskStatusType
export const stepLabel = stepStatusLabel
export const stepType = stepStatusType
export const agentLabel = a => AGENT_LABEL[a] || AGENT_LABEL.system
export const engineLabel = e => ENGINE_LABEL[e] || e || 'DeepSeek'
export const roleLabel = rt => ROLE_LABEL[rt] || rt || '其他'
export const ruleTypeLabel = t => RULE_TYPE_LABEL[t] || t || '规则'

/** 新建向导：平台卡片上的模式角标文案（文案真源见 constants/modes.js，勿在此另写一份） */
export function modeOptionText(m) {
  return MODE_LABEL[m] || MODE_LABEL.geo
}

/** 新建向导：平台卡片上的模式角标样式类 */
export function modeOptionClass(m) {
  if (m === 'platform') return 'm-platform'
  if (m === 'official') return 'm-official'
  if (m === 'green') return 'm-green'
  return 'm-geo'
}

/**
 * 列表 / 详情：根据运行实际模式 + 产出形态给出统一徽标（三模式 + 官网 MDX 分支）。
 * 注意 output_format 优先于 publish_mode：官网运行后端会强制 geo + mdx。
 */
export function runModeTag(r) {
  if ((r.output_format || '') === 'mdx') return { text: '官网 MDX', cls: 'm-official' }
  if (r.publish_mode === 'platform') return { text: '平台合规', cls: 'm-platform' }
  if (r.publish_mode === 'green') return { text: '绿色吸粉', cls: 'm-green' }
  return { text: '强品牌/GEO', cls: 'm-geo' }
}

/** 与 runModeTag 对应的 el-tag type */
export function runModeType(r) {
  if ((r.output_format || '') === 'mdx') return 'primary'
  if (r.publish_mode === 'platform') return 'info'
  if (r.publish_mode === 'green') return 'success'
  return 'danger'
}

/** 软文风险等级 → el-tag type */
export function riskTagType(level) {
  if (level === '高') return 'danger'
  if (level === '中') return 'warning'
  return 'success'
}

/** GEO 维度得分 → 百分比（按权重折算） */
export function dimPct(key, v) {
  const w = DIM_WEIGHTS[key] || 20
  return Math.min(100, Math.round((Number(v) || 0) / w * 100))
}

/** GEO 维度得分 → 进度条颜色（红/黄/绿） */
export function dimColor(key, v) {
  const w = DIM_WEIGHTS[key] || 20
  const ratio = (Number(v) || 0) / w
  if (ratio >= 0.7) return '#10b981'
  if (ratio >= 0.4) return '#f59e0b'
  return '#ef4444'
}

export const dimLabel = k => DIM_LABELS[k] || k
export const mindLabel = k => MIND_LABELS[k] || k
