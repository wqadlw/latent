import axios from 'axios'
import { ElMessage } from 'element-plus'
import { clearToken, getToken } from './authToken'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  // 注入登录令牌
  const token = getToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  if (config.params) {
    const cleaned = {}
    for (const [k, v] of Object.entries(config.params)) {
      if (v !== '' && v !== null && v !== undefined) {
        cleaned[k] = v
      }
    }
    config.params = cleaned
  }
  return config
})

// 401 只处理一次跳转，避免并发请求同时触发多次路由跳转
let redirectingToLogin = false

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status

    if (status === 401) {
      clearToken()
      if (!redirectingToLogin) {
        redirectingToLogin = true
        ElMessage.warning('登录已过期，请重新登录')
        // 懒加载 router，避免 api → router → views → api 的循环依赖
        import('../router').then(({ default: router }) => {
          const current = router.currentRoute.value
          if (current.name !== 'Login') {
            router.replace({ name: 'Login', query: { redirect: current.fullPath } })
          }
        }).finally(() => {
          setTimeout(() => { redirectingToLogin = false }, 800)
        })
      }
      return Promise.reject(error)
    }

    const detail = error.response?.data?.detail
    let msg
    if (detail == null) {
      msg = error.message || '请求失败'
    } else if (typeof detail === 'string') {
      msg = detail
    } else {
      // FastAPI 校验错误 detail 为对象/数组，避免显示 [object Object]
      try {
        msg = JSON.stringify(detail)
      } catch {
        msg = '请求失败'
      }
    }
    ElMessage.error(msg)
    return Promise.reject(error)
  }
)

// ========== 认证与用户 ==========
export const authApi = {
  login: (data) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
  changePassword: (data) => api.post('/auth/change-password', data),
  listUsers: () => api.get('/auth/users'),
  createUser: (data) => api.post('/auth/users', data),
  updateUser: (id, data) => api.put(`/auth/users/${id}`, data),
  deleteUser: (id) => api.delete(`/auth/users/${id}`),
  operationLogs: (params) => api.get('/auth/operation-logs', { params }),
}

// ========== 元信息 ==========
export const metaApi = {
  get: () => api.get('/meta'),
}

// ========== 行业 ==========
export const industryApi = {
  list: () => api.get('/industry'),
  create: (data) => api.post('/industry', data),
  update: (id, data) => api.put(`/industry/${id}`, data),
  delete: (id) => api.delete(`/industry/${id}`),
  clone: (id, data) => api.post(`/industry/${id}/clone`, data),
  sort: (items) => api.post('/industry/sort', items),
}

// ========== 平台 ==========
export const platformApi = {
  list: (industry_id) => api.get('/platform', { params: { industry_id } }),
  create: (data) => api.post('/platform', data),
  update: (id, data) => api.put(`/platform/${id}`, data),
  delete: (id) => api.delete(`/platform/${id}`),
  sort: (items) => api.post('/platform/sort', items),
}

// ========== 人设 ==========
export const personaApi = {
  list: (industry_id) => api.get('/persona', { params: { industry_id } }),
  create: (data) => api.post('/persona', data),
  update: (id, data) => api.put(`/persona/${id}`, data),
  delete: (id) => api.delete(`/persona/${id}`),
  sort: (items) => api.post('/persona/sort', items),
}

// ========== 账号 ==========
export const accountApi = {
  list: (industry_id) => api.get('/account', { params: { industry_id } }),
  create: (data) => api.post('/account', data),
  update: (id, data) => api.put(`/account/${id}`, data),
  delete: (id) => api.delete(`/account/${id}`),
  toggleStatus: (id, status) => api.patch(`/account/${id}/status`, null, { params: { status } }),
  sort: (items) => api.post('/account/sort', items),
}

// ========== 知识库 ==========
export const knowledgeApi = {
  listCategories: (industry_id) => api.get('/knowledge/category', { params: { industry_id } }),
  createCategory: (data) => api.post('/knowledge/category', data),
  updateCategory: (id, data) => api.put(`/knowledge/category/${id}`, data),
  deleteCategory: (id) => api.delete(`/knowledge/category/${id}`),
  sortCategories: (items) => api.post('/knowledge/category/sort', items),
  listItems: (industry_id, category_id, keyword) => api.get('/knowledge/item', { params: { industry_id, category_id, keyword } }),
  createItem: (data) => api.post('/knowledge/item', data),
  updateItem: (id, data) => api.put(`/knowledge/item/${id}`, data),
  deleteItem: (id) => api.delete(`/knowledge/item/${id}`),
  batchMoveItems: (data) => api.post('/knowledge/item/batch_move', data),
  batchDeleteItems: (data) => api.post('/knowledge/item/batch_delete', data),
  batchStatusItems: (data) => api.post('/knowledge/item/batch_status', data),
  sortItems: (items) => api.post('/knowledge/item/sort', items),
  // v3
  batchImport: (data) => api.post('/knowledge/item/batch', data),
  search: (industry_id, keyword) => api.get('/knowledge/item/search', { params: { industry_id, keyword } }),
  quickCreateCategory: (data) => api.post('/knowledge/category/quick', data),
  // v4 新增
  getItem: (id) => api.get(`/knowledge/item/${id}`),
  listItemsGrouped: (industry_id, keyword) => api.get('/knowledge/item/grouped', { params: { industry_id, keyword } }),
  stats: (industry_id) => api.get('/knowledge/stats', { params: { industry_id } }),
  exportItems: (industry_id, fmt, category_id) => api.get('/knowledge/export', { params: { industry_id, fmt, category_id }, responseType: 'blob' }),
  seedDefaults: (industry_id) => api.post(`/knowledge/seed/${industry_id}`),
}

// ========== 背景库 ==========
export const backgroundApi = {
  get: (industry_id) => api.get('/background-library', { params: { industry_id } }),
  save: (data) => api.put('/background-library', data),
  generate: (industry_id) => api.post('/background-library/generate', { industry_id }),
}

// ========== 规则库 ==========
export const ruleApi = {
  list: (industry_id, rule_type, platform_id) => api.get('/rule', { params: { industry_id, rule_type, platform_id } }),
  create: (data) => api.post('/rule', data),
  update: (id, data) => api.put(`/rule/${id}`, data),
  delete: (id) => api.delete(`/rule/${id}`),
  toggleStatus: (id, status) => api.patch(`/rule/${id}/status`, null, { params: { status } }),
  sort: (items) => api.post('/rule/sort', items),
  batchImport: (data) => api.post('/rule/batch_import', data),
  seedDefaults: (industry_id) => api.post(`/rule/seed/${industry_id}`),
  assistantPrompt: (industry_id) => api.post('/rule/assistant-prompt', { industry_id }),
}

// ========== 关键词 ==========
export const keywordApi = {
  list: (industry_id, type, keyword) => api.get('/keyword', { params: { industry_id, type, keyword } }),
  create: (data) => api.post('/keyword', data),
  update: (id, data) => api.put(`/keyword/${id}`, data),
  delete: (id) => api.delete(`/keyword/${id}`),
  sort: (items) => api.post('/keyword/sort', items),
  batchImport: (data) => api.post('/keyword/batch', data),
  batchGroup: (data) => api.post('/keyword/batch_group', data),
  batchDelete: (data) => api.post('/keyword/batch_delete', data),
}
export const keywordGroupApi = {
  list: (industry_id) => api.get('/keyword-group', { params: { industry_id } }),
  create: (data) => api.post('/keyword-group', data),
  update: (id, data) => api.put(`/keyword-group/${id}`, data),
  delete: (id) => api.delete(`/keyword-group/${id}`),
  sort: (items) => api.post('/keyword-group/sort', items),
}

// ========== 选题 ==========
export const topicApi = {
  list: (industry_id, platform_id, account_id) => api.get('/topic', { params: { industry_id, platform_id, account_id } }),
  create: (data) => api.post('/topic', data),
  update: (id, data) => api.put(`/topic/${id}`, data),
  delete: (id) => api.delete(`/topic/${id}`),
  sort: (items) => api.post('/topic/sort', items),
  matrix: (industry_id) => api.get('/topic/matrix', { params: { industry_id } }),
}


// ========== 内容审核/资产 ==========
export const contentApi = {
  list: (industry_id, review_status, publish_status, platform_id, keyword) => api.get('/content', { params: { industry_id, review_status, publish_status, platform_id, keyword } }),
  create: (data) => api.post('/content', data),
  update: (id, data) => api.put(`/content/${id}`, data),
  delete: (id) => api.delete(`/content/${id}`),
  review: (id, data) => api.post(`/content/${id}/review`, data),
  publish: (id, data) => api.post(`/content/${id}/publish`, data),
  check: (id) => api.post(`/content/${id}/check`),
  similarity: (id) => api.get('/content/similarity', { params: { item_id: id } }),
}

// ========== 效果统计 ==========
export const effectApi = {
  list: (industry_id, keyword_id, model_type) => api.get('/effect', { params: { industry_id, keyword_id, model_type } }),
  create: (data) => api.post('/effect', data),
  delete: (id) => api.delete(`/effect/${id}`),
  dashboard: (industry_id) => api.get('/effect/dashboard', { params: { industry_id } }),
}

// ========== 提示词库 ==========
export const promptLibraryApi = {
  categories: () => api.get('/prompt-library/categories'),
  list: (industry_id, category, keyword) => api.get('/prompt-library', { params: { industry_id, category, keyword } }),
  create: (data) => api.post('/prompt-library', data),
  update: (id, data) => api.put(`/prompt-library/${id}`, data),
  delete: (id) => api.delete(`/prompt-library/${id}`),
  setDefault: (id) => api.post(`/prompt-library/${id}/default`),
  sort: (items) => api.post('/prompt-library/sort', items),
  seedDefaults: (industry_id) => api.post(`/prompt-library/seed/${industry_id}`),
  // v3
  detectVariables: (content) => api.post('/prompt-library/detect-variables', { content }),
  testRender: (data) => api.post('/prompt-library/test-render', data),
  duplicate: (id) => api.post(`/prompt-library/${id}/duplicate`),
  // v4 新增
  builtinVariables: () => api.get('/prompt-library/builtin-variables'),
  incrementUsage: (id) => api.post(`/prompt-library/${id}/use`),
  rate: (id, rating) => api.post(`/prompt-library/${id}/rate`, { rating }),
  exportPrompts: (industry_id, category) => api.get('/prompt-library/export', { params: { industry_id, category }, responseType: 'blob' }),
  importPrompts: (data) => api.post('/prompt-library/import', data),
  // AI 写提示词：让 AI 按白名单变量为系统写标准提示词模板
  generate: (data) => api.post('/prompt-library/generate', data),
}

// ========== 软文生产 ==========
export const productionApi = {
  list: (params) => api.get('/production', { params }),
  get: (id) => api.get(`/production/${id}`),
  create: (data) => api.post('/production', data),
  update: (id, data) => api.put(`/production/${id}`, data),
  delete: (id) => api.delete(`/production/${id}`),
  render: (data) => api.post('/production/render', data),
  publish: (id, data) => api.post(`/production/${id}/publish`, data),
  options: (id) => api.get(`/production/${id}/options`),
  // v4 新增
  searchKnowledge: (taskId, keyword, categoryId) => api.get(`/production/${taskId}/knowledge-search`, { params: { keyword, category_id: categoryId } }),
  // v4 第8步：生成文章配图方案（文生图提示词）
  illustrationPlan: (data) => api.post('/production/illustration-plan', data),
  // 版本 / 历史管理
  versions: (taskId, step) => api.get(`/production/${taskId}/versions`, { params: { step } }),
  restoreVersion: (taskId, vid) => api.post(`/production/${taskId}/versions/${vid}/restore`),
  // GEO 评分闸门
  geoScore: (id) => api.post(`/production/${id}/geo-score`),
  geoScoreStandalone: (data) => api.post('/production/geo-score', data),
  // GEO 审计：交给外部 AI（提示词编排 + 结果导入）
  geoAuditPrompt: (id) => api.post(`/production/${id}/geo-audit-prompt`),
  geoAuditImport: (id, ai_result) => api.post(`/production/${id}/geo-audit-import`, { ai_result }),
  // GEO 终检合并端点：解析 AI 返回的结构化终稿（标题/正文/评分/建议）并写回任务
  geoFinalize: (id, ai_result) => api.post(`/production/${id}/geo-finalize`, { ai_result }),
  // 一键生成：调用已配置 LLM（未配置时自动引导手动模式）
  generate: (id, data) => api.post(`/production/${id}/generate`, data),
}

// ========== 品牌资产库 ==========
export const brandAssetApi = {
  list: (industry_id) => api.get('/brand-asset', { params: { industry_id } }),
  get: (id) => api.get(`/brand-asset/${id}`),
  create: (data) => api.post('/brand-asset', data),
  update: (id, data) => api.put(`/brand-asset/${id}`, data),
  delete: (id) => api.delete(`/brand-asset/${id}`),
  setDefault: (id) => api.post(`/brand-asset/${id}/default`),
  getDefault: (industry_id) => api.get(`/brand-asset/default/${industry_id}`),
}

// ========== 7 大平台预设 ==========
export const platformPresetApi = {
  list: () => api.get('/platform-presets'),
  seed: (industry_id) => api.post(`/platform-presets/seed/${industry_id}`),
}

// ========== 全局搜索 ==========
export const searchApi = {
  search: (q, industry_id) => api.get('/search', { params: { q, industry_id } }),
}

// ========== GEO 作战：目标画像 ==========
export const targetPersonaApi = {
  list: (industry_id) => api.get('/target-persona', { params: { industry_id } }),
  create: (data) => api.post('/target-persona', data),
  update: (id, data) => api.put(`/target-persona/${id}`, data),
  delete: (id) => api.delete(`/target-persona/${id}`),
  sort: (items) => api.post('/target-persona/sort', items),
  seedDefaults: (industry_id) => api.post(`/target-persona/seed/${industry_id}`),
  importBatch: (industry_id, data) => api.post('/target-persona/import', { industry_id, data }),
  assistantPrompt: (industry_id) => api.post('/target-persona/assistant-prompt', { industry_id }),
}

// ========== GEO 作战：意图问题 ==========
export const intentQuestionApi = {
  list: (industry_id, persona_id, category, coverage, keyword) =>
    api.get('/intent-question', { params: { industry_id, persona_id, category, coverage, keyword } }),
  create: (data) => api.post('/intent-question', data),
  update: (id, data) => api.put(`/intent-question/${id}`, data),
  delete: (id) => api.delete(`/intent-question/${id}`),
  sort: (items) => api.post('/intent-question/sort', items),
  batchDelete: (data) => api.post('/intent-question/batch_delete', data),
  seedDefaults: (industry_id) => api.post(`/intent-question/seed/${industry_id}`),
  importBatch: (industry_id, data) => api.post('/intent-question/import', { industry_id, data }),
  assistantPrompt: (industry_id) => api.post('/intent-question/assistant-prompt', { industry_id }),
}

// ========== GEO 作战：AI 推荐监测 ==========
export const geoMonitorApi = {
  platforms: () => api.get('/geo-monitor/platforms'),
  list: (industry_id) => api.get('/geo-monitor', { params: { industry_id } }),
  create: (data) => api.post('/geo-monitor', data),
  update: (id, data) => api.put(`/geo-monitor/${id}`, data),
  delete: (id) => api.delete(`/geo-monitor/${id}`),
  sort: (items) => api.post('/geo-monitor/sort', items),
  getPrompt: (monitor_id, platform) => api.get(`/geo-monitor/${monitor_id}/prompt`, { params: { platform } }),
  importReply: (monitor_id, data) => api.post(`/geo-monitor/${monitor_id}/reply`, data),
  listReplies: (monitor_id) => api.get(`/geo-monitor/${monitor_id}/replies`),
  deleteReply: (reply_id) => api.delete(`/geo-monitor/reply/${reply_id}`),
  stats: (industry_id) => api.get('/geo-monitor/stats', { params: { industry_id } }),
  seedDefaults: (industry_id) => api.post(`/geo-monitor/seed/${industry_id}`),
}

// ========== GEO 作战：定位画布（三环定位法） ==========
export const geoCanvasApi = {
  get: (industry_id) => api.get('/geo-canvas', { params: { industry_id } }),
}

// ========== GEO 作战：AI 可见性（自动探测 + 分析看板） ==========
// 与 geoMonitorApi 的分工：geoMonitor 管「监测任务 + 人工粘贴」，
// visibility 管「自动探测 + 6 KPI 分析 + 竞品对比」。
export const visibilityApi = {
  // 元信息
  providers: () => api.get('/visibility/providers'),
  configs: (industry_id) => api.get('/visibility/configs', { params: { industry_id } }),

  // 采集
  collect: (data) => api.post('/visibility/collect', data),
  collectMulti: (data) => api.post('/visibility/collect-multi', data),
  collectForMonitor: (monitor_id, params) =>
    api.post(`/visibility/monitor/${monitor_id}/collect`, null, { params }),

  // 探测记录
  runs: (params) => api.get('/visibility/run', { params }),
  run: (run_id) => api.get(`/visibility/run/${run_id}`),
  deleteRun: (run_id) => api.delete(`/visibility/run/${run_id}`),
  sources: (params) => api.get('/visibility/sources', { params }),

  // 分析看板
  overview: (params) => api.get('/visibility/overview', { params }),
  kpis: (params) => api.get('/visibility/kpis', { params }),
  trend: (params) => api.get('/visibility/trend', { params }),
  sourcePreferences: (params) => api.get('/visibility/source-preferences', { params }),
  termCloud: (params) => api.get('/visibility/term-cloud', { params }),
  topicSuggestions: (params) => api.get('/visibility/topic-suggestions', { params }),
  compare: (params) => api.get('/visibility/compare', { params }),

  // 竞品对比
  competitors: (industry_id) => api.get('/visibility/competitors', { params: { industry_id } }),
  saveCompetitor: (data) => api.post('/visibility/competitors', data),
  deleteCompetitor: (id) => api.delete(`/visibility/competitors/${id}`),
  seedCompetitors: (industry_id) =>
    api.post('/visibility/competitors/seed', null, { params: { industry_id } }),
  detectCompetitors: (run_id) => api.post(`/visibility/competitors/detect/${run_id}`),
  competitorBoard: (params) => api.get('/visibility/competitors/board', { params }),
}

// ========== GEO 作战：收录观测 + 归因闭环 ==========
// 抓取侧（bots/hit/stats/uncovered/trend）是全局观测；
// 闭环侧（funnel/attribution/journey/recycle/loop-*）按行业隔离，
// 把 crawler_hit 与 geo_visibility_source 接起来。
export const crawlerApi = {
  bots: () => api.get('/crawler/bots'),
  hits: (params) => api.get('/crawler/hit', { params }),
  stats: (days) => api.get('/crawler/stats', { params: { days } }),
  uncovered: (days) => api.get('/crawler/uncovered', { params: { days } }),
  trend: (days) => api.get('/crawler/trend', { params: { days } }),
  importLog: (data) => api.post('/crawler/import-log', data),
  clearHits: (before_days) => api.delete('/crawler/hit', { params: { before_days } }),
  siteIndex: (site) => api.get('/site/index', { params: { site } }),

  // 归因闭环（B4）
  loopOverview: (params) => api.get('/crawler/loop-overview', { params }),
  funnel: (params) => api.get('/crawler/funnel', { params }),
  attribution: (params) => api.get('/crawler/attribution', { params }),
  journey: (params) => api.get('/crawler/journey', { params }),
  recycle: (params) => api.get('/crawler/recycle', { params }),
  loopHealth: (params) => api.get('/crawler/loop-health', { params }),
}

// ========== LLM 配置（DeepSeek 可插拔，与手动模式并存） ==========
export const llmApi = {
  providers: () => api.get('/llm/providers'),
  listConfigs: (industry_id) => api.get('/llm/configs', { params: { industry_id } }),
  createConfig: (data) => api.post('/llm/configs', data),
  updateConfig: (id, data) => api.put(`/llm/configs/${id}`, data),
  deleteConfig: (id) => api.delete(`/llm/configs/${id}`),
  setDefault: (id) => api.post(`/llm/configs/${id}/set-default`),
  test: (id) => api.post(`/llm/configs/${id}/test`),
  generate: (data) => api.post('/llm/generate', data),
}

// ========== 软文生产：一键生成（调用已配置 LLM） ==========
// （generate 方法已并入上方 productionApi 定义）

// ========== 发布自动化（Playwright 兜底 + 审核闸门） ==========
export const platformCredentialApi = {
  list: (industry_id) => api.get('/platform-credential', { params: { industry_id } }),
  create: (data) => api.post('/platform-credential', data),
  update: (id, data) => api.put(`/platform-credential/${id}`, data),
  delete: (id) => api.delete(`/platform-credential/${id}`),
  captureStart: (data) => api.post('/platform-credential/capture-start', data),
  captureStatus: (session_id) => api.get('/platform-credential/capture-status', { params: { session_id } }),
  captureFinish: (session_id) => api.post('/platform-credential/capture-finish', null, { params: { session_id } }),
  captureCancel: (session_id) => api.post('/platform-credential/capture-cancel', null, { params: { session_id } }),
  capturePaste: (data) => api.post('/platform-credential/capture-paste', data),
}
export const publishApi = {
  platforms: (industry_id) => api.get('/platforms', { params: { industry_id } }),
  listJobs: (industry_id, task_id) => api.get('/publish-job', { params: { industry_id, task_id } }),
  createJob: (data) => api.post('/publish-job', data),
  approveJob: (id) => api.post(`/publish-job/${id}/approve`),
  rejectJob: (id, reason) => api.post(`/publish-job/${id}/reject`, { reason }),
  runJob: (id) => api.post(`/publish-job/${id}/run`),
  oneClick: (data) => api.post('/publish/one-click', data),
}

// ========== 浏览器工作室（豆包创作 + 搜狐号发布 自动化流水线） ==========
export const browserStudioApi = {
  list: (industry_id) => api.get('/browser-studio', { params: { industry_id } }),
  get: (id) => api.get(`/browser-studio/${id}`),
  create: (data) => api.post('/browser-studio', data),
  start: (id) => api.post(`/browser-studio/${id}/start`),
  retry: (id) => api.post(`/browser-studio/${id}/retry`),
  retryPublish: (id) => api.post(`/browser-studio/${id}/retry-publish`),
  confirm: (id) => api.post(`/browser-studio/${id}/confirm`),
  publish: (id) => api.post(`/browser-studio/${id}/publish`),
  // 发布前软文预检（P2-1 / C 项补全）：对终稿跑综合闸门，返回结构化预检（非硬阻断）
  precheck: (id) => api.get(`/browser-studio/${id}/precheck`),
  remove: (id) => api.delete(`/browser-studio/${id}`),
  doubaoCredentials: (industry_id) => api.get('/browser-studio/doubao-credential', { params: { industry_id } }),
  pasteDoubaoCredential: (data) => api.post('/browser-studio/doubao-credential', data),
  // 步骤透明日志（API 全流程可复现：发送内容 / 耗时 / 提取结果 / 下一步）
  stepLogs: (id) => api.get(`/browser-studio/${id}/step-logs`),
  // 创作过程可视化（P2-2）：主编指令↔写手改写多轮对话，便于调优提示词
  conversation: (id) => api.get(`/browser-studio/${id}/conversation`),
  // 文章改写模式（P2-3）：贴被判软文 → 按目标模式改写，返回改写稿 + 软文风险对比
  rewrite: (data) => api.post('/browser-studio/rewrite', data),
}

// ========== 自动化提示词（自动化指挥中心 · 可编辑/可复制） ==========
export const automationPromptApi = {
  list: (category) => api.get('/automation-prompts', { params: { category } }),
  steps: () => api.get('/automation-prompts/steps'),
  // 步骤→提示词 key / 步骤→API角色 单一真源（Manual.vue 操作手册委托，消除前后端双份映射漂移）
  meta: () => api.get('/automation-prompts/meta'),
  context: (mode) => api.get('/automation-prompts/context', { params: { mode } }),
  update: (key, content) => api.put(`/automation-prompts/${key}`, { content }),
  reset: (key) => api.post(`/automation-prompts/${key}/reset`),
  // 三 API 调度状态（按角色分流 + 负载均衡 + 故障切换）
  schedulerStatus: () => api.get('/automation-prompts/scheduler-status'),
  // 各平台合规发布策略（格式 / 禁区 / 发布模式 / AI 抓取优化）
  publishStrategies: () => api.get('/automation-prompts/publish-strategies'),
  updateStrategy: (sid, data) => api.put(`/automation-prompts/publish-strategies/${sid}`, data),
}

// ========== 生产流水线（阶段 C：可编排规格 + 断点续跑 + 有界并发队列 + 批量生产） ==========
export const pipelineApi = {
  // 步骤注册表（顺序 / 是否可关 / 产物落点），供编排器渲染
  steps: (engine_kind) => api.get('/pipeline/steps', { params: { engine_kind } }),
  // 某条运行的编排规格 + 断点续跑计划
  spec: (run_id) => api.get('/pipeline/spec', { params: { run_id } }),
  saveSpec: (data) => api.put('/pipeline/spec', data),

  // 断点续跑：默认从第一个未完成步骤继续；from_step 可强制从某步重做
  resume: (run_id, data) => api.post(`/pipeline/run/${run_id}/resume`, data || {}),
  enqueue: (run_id, data) => api.post(`/pipeline/run/${run_id}/enqueue`, data || {}),
  runQueue: (run_id) => api.get(`/pipeline/run/${run_id}/queue`),

  // 队列运维
  queue: (params) => api.get('/pipeline/queue', { params }),
  queueStats: () => api.get('/pipeline/queue/stats'),
  cancelJob: (job_id) => api.post(`/pipeline/queue/${job_id}/cancel`),
  retryJob: (job_id) => api.post(`/pipeline/queue/${job_id}/retry`),
  retryFailed: (params) => api.post('/pipeline/queue/retry-failed', null, { params }),
  reap: () => api.post('/pipeline/queue/reap'),

  // 批量生产
  batchPreview: (data) => api.post('/pipeline/batch/preview', data),
  createBatch: (data) => api.post('/pipeline/batch', data),
  batches: (params) => api.get('/pipeline/batches', { params }),
  batchDetail: (batch_id) => api.get(`/pipeline/batches/${batch_id}`),
  requeueBatch: (batch_id, data) => api.post(`/pipeline/batches/${batch_id}/requeue`, data || {}),
}

export default api