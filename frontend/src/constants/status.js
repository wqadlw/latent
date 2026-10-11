/**
 * 状态枚举 → 展示文案 / el-tag type 的单一真源。
 *
 * 为什么必须集中：同一套状态码在 5 个文件里各写了一遍映射表，且**已经开始漂移**——
 * 生产任务的 `archived` 在仪表盘是「已归档」，选题池里却写成「待处理」；
 * 内容资产的 `offline` 一处叫「已下架」、另一处叫「已打回」。
 * 状态文案不一致的代价不是「不好看」：用户会以为自己看到的是两批不同的数据。
 *
 * ⚠️ 这里只放**后端枚举**的翻译。前端自己的 UI 开关（如 topTab、viewMode）
 * 不属于状态枚举，不要往这里塞。
 *
 * ⚠️ 注意区分三套容易混淆的「状态」：
 *   - TASK_STATUS      生产任务（production_task.status）
 *   - TOPIC_STATUS     选题（keyword_topic.status）—— 注意 pending 是「待处理」不是「草稿」
 *   - ASSET_PUBLISH    内容资产的发布状态（content_asset.publish_status）
 *   - REVIEW_STATUS    内容审核状态（content_asset.review_status）
 * 发布任务（publish_job）的状态表目前只有 Publish.vue 一个消费方，留在原处，
 * 等出现第二个消费方时再迁进来。
 *
 * ⚠️ **不要**在这里加「状态 → 色值」的表。ContentOpsPanel 曾经有一份
 * `statusMeta[x].color`，四个十六进制值和 .st-* 的 CSS 完全重复，
 * 而且**从未被读取过**——真正渲染的是 `.task-chip.st-draft .task-chip__bar`
 * 这类 CSS 规则。颜色归 CSS 管，JS 里再存一份只会慢慢和 CSS 对不上。
 */

/* ============ 生产任务 ============ */
/*
 * ⚠️ 这个枚举是**两套模式的并集**，不是笔误。
 *
 * `production_task.status` 一列承载两种语义，取决于该行的 mode：
 *   · 手动模式（mode != 'auto'）—— 用户在「软文生产」里一步一步走：
 *       draft → processing → done / archived
 *     写入口：routers/production.py（建任务时 draft、第 8 步收尾时 done）
 *   · 自动模式（mode == 'auto'）—— 浏览器工作室 / 流水线 / 批量生产托管：
 *       created → running → await_confirm → confirmed → published
 *                          ↘ partial / failed
 *     写入口：services/doubao_studio.py、services/task_queue.py
 *
 * 此前前端只映射了手动模式那 4 个值，于是仪表盘和内容日历上，
 * 所有自动模式的任务都**直接显示英文原始码**（await_confirm / running / failed）。
 * 这是真事，不是理论风险 —— 见 docs/screenshots/D2-仪表盘-任务状态与时间.png。
 *
 * 并集里有两组语义重叠的值（done/succeeded 都是「已完成」），这是后端历史遗留，
 * 前端不做归一，只保证两者显示一致。
 *
 * 文案取舍：浏览器工作室原本写「已创建/运行中/待你确认/已确认」，
 * 流水线原本写「待启动/执行中/等待确认/已入库」。**同一批行、两个页面、两套词**——
 * 用户从流水线点进工作室会看到状态变了，这比措辞不统一更糟。现统一为下表，
 * 「已入库」这类带业务色彩的措辞退役，只保留能直读的状态名。
 */
export const TASK_STATUS_LABEL = {
  // 手动模式
  draft: '草稿',
  processing: '进行中',
  done: '已完成',
  archived: '已归档',
  // 自动模式
  created: '待启动',
  running: '执行中',
  await_confirm: '等待确认',
  confirmed: '已确认',
  succeeded: '已完成',
  partial: '部分成功',
  published: '已发布',
  failed: '失败',
  cancelled: '已取消',
}

export const TASK_STATUS_TYPE = {
  // 手动模式
  draft: 'info',
  processing: 'warning',
  done: 'success',
  archived: 'info',
  // 自动模式
  created: 'info',
  running: 'primary',
  await_confirm: 'warning',
  confirmed: 'success',
  succeeded: 'success',
  partial: 'warning',
  published: 'success',
  failed: 'danger',
  cancelled: 'info',
}

/** 日历 / 列表里的状态色带由 CSS 的 .st-* 规则负责，见 ContentOpsPanel.vue */

/* ============ 选题 ============ */

export const TOPIC_STATUS_LABEL = {
  pending: '待处理',
  processing: '进行中',
  done: '已完成',
}

export const TOPIC_STATUS_TYPE = {
  pending: 'info',
  processing: 'warning',
  done: 'success',
}

/** 矩阵视图里塞进小徽标的**单字**版本（位置太窄放不下「待处理」）。 */
export const TOPIC_STATUS_SHORT = {
  pending: '待',
  processing: '中',
  done: '完',
}

/* ============ 关键词类型 ============ */

/**
 * 关键词类型的**唯一真源**。
 *
 * D5 拆分前，这套「值 → 中文名」在 Keyword.vue 里被抄了 **4 遍**：
 * 类型筛选下拉、新建/编辑弹窗下拉、批量导入弹窗下拉，外加 `typeLabel()`。
 * 拆分会把这份重复**复制进 3 个新组件**，所以先收敛到这里。
 * 新增类型时改这一处即可（下拉选项由 OPTIONS 派生，不会再漏改）。
 */
export const KEYWORD_TYPE_LABEL = {
  brand: '品牌词',
  product: '产品词',
  long_tail: '长尾词',
  question: '问题词',
}

/** el-tag 的 type（配色语义，不是颜色值本身） */
export const KEYWORD_TYPE_TAG = {
  brand: 'danger',
  product: 'warning',
  long_tail: 'info',
  question: 'success',
}

/** 下拉选项，供 el-select 直接 v-for */
export const KEYWORD_TYPE_OPTIONS = Object.entries(KEYWORD_TYPE_LABEL).map(
  ([value, label]) => ({ value, label }),
)

export const keywordTypeLabel = (t) => KEYWORD_TYPE_LABEL[t] || t || '—'
export const keywordTypeTag = (t) => KEYWORD_TYPE_TAG[t] || 'info'

/* ============ 内容资产：发布状态 ============ */

export const ASSET_PUBLISH_LABEL = {
  pending: '待发布',
  published: '已发布',
  offline: '已下架',
}

export const ASSET_PUBLISH_TYPE = {
  pending: 'info',
  published: 'success',
  offline: 'danger',
}

/* ============ 内容资产：审核状态 ============ */

export const REVIEW_STATUS_LABEL = {
  pending: '待审核',
  pass: '已通过',
  reject: '已驳回',
}

export const REVIEW_STATUS_TYPE = {
  pending: 'warning',
  pass: 'success',
  reject: 'danger',
}

/* ============ 流水线步骤 ============ */

/*
 * `pipeline_step.status`。与上面的 TASK_STATUS 是**不同**的列，不要混用：
 * 任务状态说「这一次生产走到哪」，步骤状态说「十步流水线里的某一步走到哪」。
 *
 * `reuse` 是断点续跑专用：作业重试时若该步的产物仍然有效，直接复用、不重烧 token。
 */
export const STEP_STATUS_LABEL = {
  pending: '待执行',
  running: '执行中',
  done: '已完成',
  failed: '失败',
  skipped: '已跳过',
  reuse: '复用产物',
}

export const STEP_STATUS_TYPE = {
  pending: 'info',
  running: 'primary',
  done: 'success',
  failed: 'danger',
  skipped: 'info',
  reuse: 'success',
}

/* ============ 取值函数 ============ */
/* 约定：文案取不到时**回退到原始码**（便于发现新枚举未登记），
   类型/颜色取不到时回退到中性值（避免 el-tag 拿到 undefined 后样式塌掉）。 */

export const taskStatusLabel = (s) => TASK_STATUS_LABEL[s] || s || '—'
export const taskStatusType = (s) => TASK_STATUS_TYPE[s] || 'info'

export const topicStatusLabel = (s) => TOPIC_STATUS_LABEL[s] || s || '—'
export const topicStatusType = (s) => TOPIC_STATUS_TYPE[s] || 'info'

export const assetPublishLabel = (s) => ASSET_PUBLISH_LABEL[s] || s || '—'
export const assetPublishType = (s) => ASSET_PUBLISH_TYPE[s] || 'info'

export const reviewStatusLabel = (s) => REVIEW_STATUS_LABEL[s] || s || '—'
export const reviewStatusType = (s) => REVIEW_STATUS_TYPE[s] || 'info'

export const stepStatusLabel = (s) => STEP_STATUS_LABEL[s] || s || '待执行'
export const stepStatusType = (s) => STEP_STATUS_TYPE[s] || 'info'
