<template>
  <div class="pipeline-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-switch v-model="autoRefresh" size="small" inline-prompt active-text="自动" inactive-text="手动"
                 class="auto-switch" />
      <el-button :icon="RefreshRight" @click="reapOrphans" :loading="reaping">回收中断作业</el-button>
      <el-button type="primary" :icon="Refresh" @click="loadAll" :loading="loading">刷新</el-button>
    </Teleport>

    <!-- 顶部 -->
    <section class="hero">
      <div class="hero__lead">
        <div class="hero__tags">
          <span class="hero__eyebrow"><el-icon><Tickets /></el-icon> 内容生产 · 流水线调度</span>
          <el-tag size="small" effect="plain">
            <el-icon><OfficeBuilding /></el-icon> {{ store.currentIndustryName }}
          </el-tag>
        </div>
        <h2 class="hero__title">批量生产与执行队列</h2>
        <p class="hero__desc">
          一次提交「<strong>选题 × 平台</strong>」就展开成 N 条运行，按<strong>并发上限</strong>排队执行。
          失败自动退避重试，重试<strong>从断点续跑</strong>——已烧过的步骤不会重来一遍。
        </p>
      </div>

      <div class="dispatch" :class="dispatcher.running ? 'dispatch--on' : 'dispatch--off'">
        <div class="dispatch__dot"></div>
        <div class="dispatch__body">
          <div class="dispatch__title">
            调度线程{{ dispatcher.running ? '运行中' : '未启动' }}
          </div>
          <div class="dispatch__meta">
            并发上限 {{ dispatcher.concurrency || '—' }} · 轮询 {{ dispatcher.poll_seconds || '—' }}s
            <template v-if="dispatcher.inflight && dispatcher.inflight.length">
              · 正在跑 #{{ dispatcher.inflight.join(' #') }}
            </template>
          </div>
          <div v-if="dispatcher.last_error" class="dispatch__err">{{ dispatcher.last_error }}</div>
        </div>
      </div>
    </section>

    <div class="board" v-loading="loading">
      <!-- ① 执行队列 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">执行队列</h3>
          <div class="stats">
            <button v-for="s in statChips" :key="s.key" class="chip" :class="[`chip--${s.tone}`,
                    { 'chip--active': statusFilter === s.key }]" @click="toggleStatus(s.key)">
              <span class="chip__num">{{ s.value }}</span>
              <span class="chip__label">{{ s.label }}</span>
            </button>
            <el-button v-if="failedCount" size="small" :icon="RefreshRight"
                       @click="retryAllFailed" :loading="retryingAll">
              重试全部失败（{{ failedCount }}）
            </el-button>
          </div>
        </div>

        <el-table :data="jobs" size="small" class="job-table" empty-text="队列为空">
          <el-table-column label="运行" min-width="220">
            <template #default="{ row }">
              <div class="cell-main">{{ row.run_name || ('运行 #' + row.run_id) }}</div>
              <div class="cell-sub">
                #{{ row.run_id }} · {{ platformLabel(row.run_platform) }}
                <span v-if="row.batch_id" class="cell-batch">{{ row.batch_id }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="队列态" width="96">
            <template #default="{ row }">
              <el-tag size="small" :type="jobTagType(row.status)" effect="light">
                {{ row.status_label }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="运行态" width="110">
            <template #default="{ row }">
              <span class="cell-sub">{{ taskStatusLabel(row.run_status) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="尝试" width="72" align="center">
            <template #default="{ row }">
              <span :class="{ 'warn-text': row.attempts > 1 }">{{ row.attempts }}/{{ row.max_attempts }}</span>
            </template>
          </el-table-column>

          <el-table-column label="GEO" width="66" align="center">
            <template #default="{ row }">
              <span v-if="row.run_geo_score" class="cell-strong">{{ row.run_geo_score }}</span>
              <span v-else class="dim">—</span>
            </template>
          </el-table-column>

          <el-table-column label="说明" min-width="200">
            <template #default="{ row }">
              <span v-if="row.error" class="cell-err" :title="row.error">{{ row.error }}</span>
              <span v-else-if="row.status === 'running'" class="dim">
                执行中<template v-if="row.worker"> · {{ row.worker }}</template>
              </span>
              <span v-else-if="row.available_at && row.status === 'queued'" class="dim">
                {{ row.available_at }} 后可执行
              </span>
              <span v-else class="dim">{{ row.finished_at || row.create_time || '—' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="200" align="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openSpec(row)">编排</el-button>
              <el-button v-if="row.status === 'queued' || row.status === 'running'" link
                         type="danger" size="small" @click="cancelJob(row)">取消</el-button>
              <el-button v-else link type="primary" size="small" @click="retryJob(row)">重试</el-button>
              <el-button v-if="row.run_status !== 'running'" link type="warning"
                         size="small" @click="resumeRun(row)">续跑</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <!-- ② 批量生产 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">批量生产</h3>
          <span class="panel__note">
            一行一个选题，与所选平台两两组合。同行业 + 同平台 + 同选题默认判为重复并跳过——
            重复提交的代价是真金白银（每条运行 6~10 次模型调用）。
          </span>
        </div>

        <div class="batch">
          <div class="batch__left">
            <label class="field__label">选题（每行一个）</label>
            <el-input v-model="form.subjects" type="textarea" :rows="7"
                      placeholder="敏感肌该怎么修护屏障&#10;烟酰胺和维C能一起用吗&#10;换季泛红怎么选面霜" />

            <label class="field__label">平台（可多选）</label>
            <el-checkbox-group v-model="form.platforms" class="platform-picks">
              <el-checkbox v-for="p in PLATFORM_OPTIONS" :key="p.value" :value="p.value" border>
                {{ p.label }}
              </el-checkbox>
            </el-checkbox-group>

            <div class="field-row">
              <div class="field">
                <label class="field__label">优先级（越小越先跑）</label>
                <el-select v-model="form.priority" size="small" style="width: 130px">
                  <el-option :value="1" label="1 · 最高" />
                  <el-option :value="3" label="3 · 较高" />
                  <el-option :value="5" label="5 · 默认" />
                  <el-option :value="8" label="8 · 较低" />
                </el-select>
              </div>
              <div class="field">
                <label class="field__label">失败重试次数</label>
                <el-input-number v-model="form.max_attempts" size="small" :min="1" :max="5" />
              </div>
              <div class="field">
                <label class="field__label">跳过重复选题</label>
                <el-switch v-model="form.skip_duplicates" />
              </div>
            </div>
          </div>

          <div class="batch__right">
            <div class="spec-mini">
              <div class="spec-mini__head">
                <span class="field__label">编排规格（本批次共用）</span>
                <el-tooltip placement="top" effect="dark"
                            content="关掉的步骤会「透传」上一步产物：关掉去AI味精修，GEO 强化就直接拿初稿；关掉闭环整改则不整改。">
                  <el-icon class="help"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="spec-mini__steps">
                <el-checkbox v-for="s in stepMeta" :key="s.key" v-model="form.steps[s.key]"
                             :disabled="!s.optional">
                  <span class="step-name">{{ s.no }}. {{ shortTitle(s) }}</span>
                  <el-tag v-if="!s.optional" size="small" type="info" effect="plain">必开</el-tag>
                </el-checkbox>
              </div>
              <div class="spec-mini__rounds">
                <span class="field__label">闭环整改最多轮数</span>
                <el-input-number v-model="form.max_revise_rounds" size="small" :min="0" :max="5" />
                <span class="dim">关掉整改时该值无效</span>
              </div>
            </div>

            <div v-if="preview" class="preview" :class="{ 'preview--warn': !preview.ok }">
              <div class="preview__head">
                <el-icon><component :is="preview.ok ? CircleCheckFilled : WarningFilled" /></el-icon>
                将创建 <strong>{{ preview.will_create }}</strong> 条
                <template v-if="preview.will_skip">，跳过重复 <strong>{{ preview.will_skip }}</strong> 条</template>
              </div>
              <ul v-if="preview.problems && preview.problems.length" class="preview__problems">
                <li v-for="(p, i) in preview.problems" :key="i">{{ p }}</li>
              </ul>
              <ul v-if="skippedItems.length" class="preview__skips">
                <li v-for="(it, i) in skippedItems.slice(0, 5)" :key="i">
                  <code>{{ it.subject }}</code> · {{ platformLabel(it.platform) }}
                  <span class="dim">{{ it.duplicate_reason }}</span>
                </li>
              </ul>
              <div v-if="createdPreviewItems.length" class="preview__list">
                <el-tag v-for="(it, i) in createdPreviewItems.slice(0, 24)" :key="i" size="small"
                        effect="plain" class="preview__tag">
                  {{ it.subject }} · {{ platformLabel(it.platform) }}
                </el-tag>
                <span v-if="createdPreviewItems.length > 24" class="dim">
                  等共 {{ createdPreviewItems.length }} 条
                </span>
              </div>
            </div>

            <div class="batch__actions">
              <el-button :icon="View" @click="doPreview" :loading="previewing">预览</el-button>
              <el-button type="primary" :icon="Promotion" @click="doCreate" :loading="creating"
                         :disabled="!preview || !preview.ok || !preview.will_create">
                创建并入队
              </el-button>
            </div>
          </div>
        </div>
      </section>

      <!-- ③ 批次 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">批次进度</h3>
          <span class="panel__note">
            批量生产**不**批量过审：批次跑到「等待确认」就停下，由人来看过再入库。
          </span>
        </div>
        <el-table :data="batches" size="small" empty-text="还没有批次">
          <el-table-column label="批次号" min-width="200">
            <template #default="{ row }">
              <code class="batch-id">{{ row.batch_id }}</code>
              <div class="cell-sub">{{ row.create_time || '—' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="进度" min-width="220">
            <template #default="{ row }">
              <el-progress :percentage="Math.round((row.progress || 0) * 100)"
                           :stroke-width="10" :status="row.counts.failed ? 'exception' : undefined" />
              <div class="cell-sub">
                {{ row.finished }}/{{ row.total }} 已结束 ·
                排队 {{ row.counts.queued }} · 执行 {{ row.counts.running }} ·
                完成 {{ row.counts.done }} · 失败 {{ row.counts.failed }}
                <template v-if="row.counts.cancelled"> · 取消 {{ row.counts.cancelled }}</template>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170" align="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openBatch(row)">详情</el-button>
              <el-button link type="warning" size="small" @click="requeueBatch(row)">整批重投</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>

    <!-- 编排 + 续跑 -->
    <el-dialog v-model="specDialog" :title="`编排与续跑 · 运行 #${specRunId}`" width="720px">
      <div v-loading="specLoading" class="spec-dialog">
        <div class="spec-dialog__plan">
          <div class="plan__head">
            <el-icon><InfoFilled /></el-icon>
            当前断点：<strong>{{ planLabel }}</strong>
            <span class="dim">（复用 {{ plan.done_count || 0 }}/{{ plan.total || 0 }} 步产物）</span>
          </div>
          <div class="plan__steps">
            <div v-for="s in plan.steps || []" :key="s.key" class="plan__step"
                 :class="[`plan__step--${s.satisfied ? 'reuse' : (s.status === 'failed' ? 'failed' : 'pending')}`]">
              <span class="plan__no">{{ s.no }}</span>
              <span class="plan__name">{{ s.title }}</span>
              <el-tag size="small" effect="plain" :type="s.satisfied ? 'success' : (s.status === 'failed' ? 'danger' : 'info')">
                {{ s.satisfied ? '复用产物' : stepStatusLabel(s.status) }}
              </el-tag>
              <span v-if="s.artifact_len" class="dim">{{ s.artifact_len }} 字</span>
            </div>
          </div>
        </div>

        <div class="spec-dialog__edit">
          <div class="field__label">启用步骤（必开项不可取消）</div>
          <el-checkbox v-for="s in stepMeta" :key="s.key" v-model="edit.steps[s.key]"
                       :disabled="!s.optional || editing" class="spec-edit-row">
            <span class="step-name">{{ s.no }}. {{ shortTitle(s) }}</span>
            <span class="step-hint">{{ s.hint }}</span>
          </el-checkbox>

          <div class="field-row">
            <div class="field">
              <span class="field__label">最多整改轮数</span>
              <el-input-number v-model="edit.max_revise_rounds" size="small" :min="0" :max="5"
                               :disabled="editing" />
            </div>
            <div class="field">
              <span class="field__label">强制从某步重做（可选）</span>
              <el-select v-model="edit.from_step" size="small" clearable placeholder="自动（从断点续跑）"
                         style="width: 210px" :disabled="editing">
                <el-option v-for="s in plan.steps || []" :key="s.key" :value="s.key"
                           :label="`${s.no}. ${s.title}`" />
              </el-select>
            </div>
          </div>

          <el-alert v-if="specNotes.length" type="warning" :closable="false" class="spec-notes">
            <div v-for="(n, i) in specNotes" :key="i">{{ n }}</div>
          </el-alert>
        </div>
      </div>

      <template #footer>
        <el-button @click="specDialog = false">关闭</el-button>
        <el-button :loading="editing" @click="saveSpec">保存编排规格</el-button>
        <el-button type="primary" :loading="resuming" @click="doResume">从断点续跑</el-button>
      </template>
    </el-dialog>

    <!-- 批次详情 -->
    <el-drawer v-model="batchDrawer" :title="`批次 ${batchDetail.batch_id || ''}`" size="620px">
      <div v-loading="batchLoading" class="batch-detail">
        <div class="batch-detail__stats">
          <div v-for="(v, k) in (batchDetail.counts || {})" :key="k" class="mini-stat">
            <div class="mini-stat__num">{{ v }}</div>
            <div class="mini-stat__label">{{ (batchDetail.labels || {})[k] || k }}</div>
          </div>
        </div>
        <el-table :data="batchDetail.runs || []" size="small" empty-text="没有运行">
          <el-table-column label="选题" min-width="180">
            <template #default="{ row }">
              <div class="cell-main">{{ row.subject || row.name }}</div>
              <div class="cell-sub">#{{ row.id }} · {{ platformLabel(row.platform) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" :type="taskStatusType(row.status)">
                {{ taskStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="150">
            <template #default="{ row }">
              <span v-if="row.error" class="cell-err">{{ row.error }}</span>
              <span v-else-if="row.geo_score" class="cell-sub">GEO {{ row.geo_score }}</span>
              <span v-else class="dim">{{ row.update_time || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, inject, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Refresh, RefreshRight, Tickets, OfficeBuilding, Promotion, View, QuestionFilled,
  InfoFilled, CircleCheckFilled, WarningFilled
} from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { pipelineApi } from '../api'
import { PLATFORM_OPTIONS, platformLabel } from '../constants/platforms'
import { taskStatusLabel, taskStatusType, stepStatusLabel } from '../constants/status'

const store = useAppStore()
const pageActionsTarget = inject('pageActionsTarget', null)

const loading = ref(false)
const reaping = ref(false)
const retryingAll = ref(false)
const autoRefresh = ref(true)

const jobs = ref([])
const stats = ref({ counts: {}, labels: {} })
const dispatcher = ref({})
const batches = ref([])
const statusFilter = ref('')

const stepMeta = ref([])
const form = reactive({
  subjects: '',
  platforms: ['sohu'],
  priority: 5,
  max_attempts: 2,
  skip_duplicates: true,
  steps: {},
  max_revise_rounds: 1,
})
const preview = ref(null)
const previewing = ref(false)
const creating = ref(false)

const specDialog = ref(false)
const specRunId = ref(0)
const specLoading = ref(false)
const editing = ref(false)
const resuming = ref(false)
const specNotes = ref([])
const plan = ref({})
const edit = reactive({ steps: {}, max_revise_rounds: 3, from_step: '' })

const batchDrawer = ref(false)
const batchLoading = ref(false)
const batchDetail = ref({})

let timer = null

// ============================================================
//  派生数据
// ============================================================
const CHIPS = [
  { key: 'queued', label: '排队中', tone: 'info' },
  { key: 'running', label: '执行中', tone: 'brand' },
  { key: 'done', label: '已完成', tone: 'ok' },
  { key: 'failed', label: '失败', tone: 'bad' },
  { key: 'cancelled', label: '已取消', tone: 'muted' },
]
const statChips = computed(() => CHIPS.map((c) => ({
  ...c, value: (stats.value.counts || {})[c.key] || 0,
})))
const failedCount = computed(() => (stats.value.counts || {}).failed || 0)
const skippedItems = computed(() => (preview.value?.items || []).filter((i) => i.duplicate))
const createdPreviewItems = computed(() => (preview.value?.items || []).filter((i) => !i.duplicate))
const planLabel = computed(() => {
  const steps = plan.value.steps || []
  const key = plan.value.next_key
  const hit = steps.find((s) => s.key === key)
  return hit ? `${hit.no}. ${hit.title}` : '全部步骤已完成'
})

// ============================================================
//  加载
// ============================================================
async function loadQueue() {
  try {
    const res = await pipelineApi.queue({
      industry_id: store.currentIndustryId,
      status: statusFilter.value,
      limit: 60,
    })
    jobs.value = res.data?.jobs || []
    stats.value = res.data?.stats || { counts: {}, labels: {} }
    dispatcher.value = stats.value.dispatcher || {}
  } catch (e) { /* 拦截器已提示 */ }
}

async function loadBatches() {
  try {
    const res = await pipelineApi.batches({ industry_id: store.currentIndustryId, limit: 12 })
    batches.value = res.data || []
  } catch (e) { /* 拦截器已提示 */ }
}

async function loadSteps() {
  try {
    const res = await pipelineApi.steps()
    stepMeta.value = res.data?.steps || []
    if (!Object.keys(form.steps).length) {
      form.steps = Object.fromEntries(stepMeta.value.map((s) => [s.key, true]))
    }
  } catch (e) { /* 拦截器已提示 */ }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadQueue(), loadBatches(), loadSteps()])
  } finally {
    loading.value = false
  }
}

// ============================================================
//  队列操作
// ============================================================
function toggleStatus(key) {
  statusFilter.value = statusFilter.value === key ? '' : key
  loadQueue()
}

async function cancelJob(row) {
  try {
    const res = await pipelineApi.cancelJob(row.id)
    const d = res.data || {}
    ElMessage.success(d.immediate ? '已取消（排队中，未执行）' : (d.msg || '已请求取消'))
    loadQueue()
  } catch (e) { /* 拦截器已提示 */ }
}

async function retryJob(row) {
  try {
    await pipelineApi.retryJob(row.id)
    ElMessage.success('已重新排队')
    loadQueue()
  } catch (e) { /* 拦截器已提示 */ }
}

async function retryAllFailed() {
  try {
    await ElMessageBox.confirm(
      `将把当前行业下 ${failedCount.value} 条失败/已取消的作业重新排队。已完成的不会重复执行。`,
      '批量重试', { type: 'warning' })
  } catch { return }
  retryingAll.value = true
  try {
    const res = await pipelineApi.retryFailed({ industry_id: store.currentIndustryId })
    ElMessage.success(res.msg || `已重新排队 ${res.data?.count || 0} 条`)
    loadQueue()
  } catch (e) { /* 拦截器已提示 */ } finally {
    retryingAll.value = false
  }
}

async function reapOrphans() {
  reaping.value = true
  try {
    const res = await pipelineApi.reap()
    const n = res.data?.reaped || 0
    ElMessage.success(n ? `已回收 ${n} 条中断作业（将从断点续跑）` : '没有需要回收的中断作业')
    loadQueue()
  } catch (e) { /* 拦截器已提示 */ } finally {
    reaping.value = false
  }
}

async function resumeRun(row) {
  try {
    await ElMessageBox.confirm(
      '将从第一个未完成的步骤继续，已完成的步骤产物会被复用（不重新调用模型）。',
      '断点续跑', { type: 'info' })
  } catch { return }
  try {
    const res = await pipelineApi.resume(row.run_id, { priority: 3 })
    ElMessage.success(res.msg || '已投递')
    loadQueue()
  } catch (e) { /* 拦截器已提示 */ }
}

// ============================================================
//  编排 / 续跑弹窗
// ============================================================
async function openSpec(row) {
  specRunId.value = row.run_id
  specDialog.value = true
  specNotes.value = []
  edit.from_step = ''
  await loadPlan()
}

async function loadPlan() {
  specLoading.value = true
  try {
    const res = await pipelineApi.spec(specRunId.value)
    const d = res.data || {}
    plan.value = d.plan || {}
    const spec = d.plan?.spec || {}
    edit.steps = Object.fromEntries(
      (spec.steps || []).map((k) => [k, true])
    )
    stepMeta.value.forEach((s) => {
      if (!(s.key in edit.steps)) edit.steps[s.key] = false
    })
    edit.max_revise_rounds = spec.max_revise_rounds ?? 3
  } catch (e) { /* 拦截器已提示 */ } finally {
    specLoading.value = false
  }
}

async function saveSpec() {
  editing.value = true
  specNotes.value = []
  try {
    const steps = stepMeta.value.filter((s) => edit.steps[s.key]).map((s) => s.key)
    const res = await pipelineApi.saveSpec({
      run_id: specRunId.value,
      steps,
      max_revise_rounds: edit.max_revise_rounds,
    })
    specNotes.value = res.data?.notes || []
    plan.value = res.data?.plan || plan.value
    ElMessage.success(specNotes.value.length ? '已保存（部分取值被修正）' : '已保存')
    loadQueue()
  } catch (e) { /* 拦截器已提示 */ } finally {
    editing.value = false
  }
}

async function doResume() {
  resuming.value = true
  try {
    const res = await pipelineApi.resume(specRunId.value, {
      from_step: edit.from_step || '',
      priority: 3,
    })
    ElMessage.success(res.msg || '已投递')
    specDialog.value = false
    loadQueue()
  } catch (e) { /* 拦截器已提示 */ } finally {
    resuming.value = false
  }
}

// ============================================================
//  批量生产
// ============================================================
function batchPayload() {
  const steps = stepMeta.value.filter((s) => form.steps[s.key]).map((s) => s.key)
  return {
    industry_id: store.currentIndustryId,
    subjects: form.subjects,
    platforms: form.platforms,
    skip_duplicates: form.skip_duplicates,
    priority: form.priority,
    max_attempts: form.max_attempts,
    ai_engine: 'mock',
    pipeline_spec: { steps, max_revise_rounds: form.max_revise_rounds },
  }
}

async function doPreview() {
  previewing.value = true
  try {
    const res = await pipelineApi.batchPreview(batchPayload())
    preview.value = res.data || null
    if (preview.value && !preview.value.ok) {
      ElMessage.warning(preview.value.problems?.[0] || '规格有问题，请检查')
    }
  } catch (e) { /* 拦截器已提示 */ } finally {
    previewing.value = false
  }
}

async function doCreate() {
  creating.value = true
  try {
    const res = await pipelineApi.createBatch(batchPayload())
    ElMessage.success(res.msg || '已创建并入队')
    preview.value = null
    form.subjects = ''
    await loadAll()
  } catch (e) { /* 拦截器已提示 */ } finally {
    creating.value = false
  }
}

// ============================================================
//  批次
// ============================================================
async function openBatch(row) {
  batchDrawer.value = true
  batchLoading.value = true
  try {
    const res = await pipelineApi.batchDetail(row.batch_id)
    batchDetail.value = res.data || {}
  } catch (e) { /* 拦截器已提示 */ } finally {
    batchLoading.value = false
  }
}

async function requeueBatch(row) {
  try {
    await ElMessageBox.confirm(
      '已完成的运行会被跳过，不会重复执行；失败与未完成的会重新排队。',
      `整批重投 ${row.batch_id}`, { type: 'warning' })
  } catch { return }
  try {
    const res = await pipelineApi.requeueBatch(row.batch_id, { priority: 3 })
    ElMessage.success(res.msg || '已重投')
    await loadAll()
  } catch (e) { /* 拦截器已提示 */ }
}

// ============================================================
//  展示辅助
// ============================================================
// 运行态 / 步骤状态的文案与标签色统一来自 constants/status.js ——
// 这里原先自己存了一份 RUN_STATUS_LABEL，和浏览器工作室的那份已经漂移。
// 只剩「队列态」的标签色是本页独有的（文案由后端 status_label 提供）。
function jobTagType(s) {
  if (s === 'failed') return 'danger'
  if (s === 'done') return 'success'
  if (s === 'running') return 'primary'
  if (s === 'cancelled') return 'info'
  return 'warning'
}

/** 步骤标题里带序号前缀（如「① 连接引擎…」），列表已单独展示序号，这里去掉避免重复。 */
function shortTitle(s) {
  return (s.title || s.key).replace(/^[①②③④⑤⑥⑦⑧⑨⑩]\s*[a-z]?\s*/i, '')
}

// ============================================================
//  生命周期
// ============================================================
function startTimer() {
  stopTimer()
  timer = setInterval(() => {
    if (!autoRefresh.value || document.hidden) return
    loadQueue()
  }, 4000)
}
function stopTimer() {
  if (timer) clearInterval(timer)
  timer = null
}

watch(() => store.currentIndustryId, () => { preview.value = null; loadAll() })

onMounted(() => { loadAll(); startTimer() })
onBeforeUnmount(stopTimer)
</script>

<style scoped>
.pipeline-view { padding: 20px 24px 40px; }
.auto-switch { margin-right: 10px; }

.hero {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 24px; margin-bottom: 18px;
}
.hero__lead { max-width: 760px; }
.hero__tags { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.hero__eyebrow {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; font-weight: 600; color: var(--brand-600);
}
.hero__title { margin: 0 0 6px; font-size: 20px; font-weight: 700; color: var(--text-primary); }
.hero__desc { margin: 0; font-size: 13px; line-height: 1.7; color: var(--text-secondary); }
.hero__desc strong { color: var(--brand-600); }

.dispatch {
  display: flex; align-items: flex-start; gap: 10px; flex-shrink: 0;
  padding: 12px 16px; border-radius: var(--radius-lg);
  border: 1px solid var(--border-light); background: var(--bg-card);
  box-shadow: var(--shadow-xs); min-width: 260px;
}
.dispatch__dot {
  width: 9px; height: 9px; border-radius: var(--radius-full); margin-top: 5px; flex-shrink: 0;
}
.dispatch--on .dispatch__dot { background: var(--accent-emerald); box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.16); }
.dispatch--off .dispatch__dot { background: var(--slate-400); }
.dispatch__title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.dispatch__meta { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; line-height: 1.6; }
.dispatch__err { font-size: 11px; color: var(--accent-rose); margin-top: 4px; }

.board { display: flex; flex-direction: column; gap: 16px; }
.panel {
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-lg); padding: 16px 18px 18px; box-shadow: var(--shadow-xs);
}
.panel__head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 14px; flex-wrap: wrap;
}
.panel__title { margin: 0; font-size: 15px; font-weight: 600; color: var(--text-primary); }
.panel__note { font-size: 12px; color: var(--text-tertiary); max-width: 640px; line-height: 1.6; }

/* 状态筛选块：兼作统计与筛选，省掉一行独立的统计条 */
.stats { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip {
  display: inline-flex; align-items: baseline; gap: 5px; cursor: pointer;
  border: 1px solid var(--border-light); background: var(--bg-card);
  border-radius: var(--radius-md); padding: 5px 10px; transition: var(--transition-fast);
}
.chip:hover { border-color: var(--border-base); }
.chip__num { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.chip__label { font-size: 11px; color: var(--text-tertiary); }
.chip--active { border-color: var(--brand-500); background: var(--brand-50); }
.chip--active .chip__num { color: var(--brand-600); }
.chip--bad .chip__num { color: var(--accent-rose); }
.chip--ok .chip__num { color: var(--accent-emerald); }
.chip--brand .chip__num { color: var(--brand-600); }

.job-table { width: 100%; }
.cell-main { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.cell-sub { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
.cell-batch { margin-left: 6px; font-family: ui-monospace, Menlo, monospace; }
.cell-err {
  font-size: 11px; color: var(--accent-rose);
  display: inline-block; max-width: 100%; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.cell-strong { font-weight: 700; color: var(--brand-600); }
.dim { color: var(--text-tertiary); font-size: 11px; }
.warn-text { color: var(--accent-amber); font-weight: 600; }

/* 批量生产 */
.batch { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }
.batch__left, .batch__right { display: flex; flex-direction: column; gap: 10px; }
.field__label { font-size: 12px; font-weight: 600; color: var(--text-secondary); }
.field-row { display: flex; gap: 18px; flex-wrap: wrap; }
.field { display: flex; flex-direction: column; gap: 4px; }
.platform-picks { display: flex; gap: 8px; flex-wrap: wrap; }
.platform-picks :deep(.el-checkbox) { margin-right: 0; }

.spec-mini {
  border: 1px solid var(--border-light); border-radius: var(--radius-md);
  padding: 12px 14px; background: var(--bg-overlay);
}
.spec-mini__head { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.help { color: var(--text-tertiary); cursor: help; }
.spec-mini__steps { display: flex; flex-direction: column; gap: 4px; }
.spec-mini__steps :deep(.el-checkbox) { margin-right: 0; height: auto; }
.step-name { font-size: 12px; color: var(--text-secondary); }
.spec-mini__rounds { display: flex; align-items: center; gap: 10px; margin-top: 10px; }

.preview {
  border: 1px solid var(--brand-200); background: var(--brand-50);
  border-radius: var(--radius-md); padding: 12px 14px; font-size: 12px;
}
.preview--warn { border-color: #fcd34d; background: #fffbeb; }
.preview__head { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-primary); }
.preview__problems { margin: 8px 0 0; padding-left: 18px; color: var(--accent-amber); line-height: 1.7; }
.preview__skips { margin: 8px 0 0; padding-left: 18px; color: var(--text-secondary); line-height: 1.8; }
.preview__skips code { background: rgba(15, 23, 42, 0.06); padding: 1px 5px; border-radius: var(--radius-sm); }
.preview__list { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.preview__tag { max-width: 100%; }
.batch__actions { display: flex; justify-content: flex-end; gap: 8px; }

.batch-id { font-family: ui-monospace, Menlo, monospace; font-size: 12px; color: var(--text-primary); }

/* 编排弹窗 */
.spec-dialog { display: flex; flex-direction: column; gap: 16px; }
.spec-dialog__plan {
  border: 1px solid var(--border-light); border-radius: var(--radius-md);
  padding: 12px 14px; background: var(--bg-overlay);
}
.plan__head { display: flex; align-items: center; gap: 6px; font-size: 13px; margin-bottom: 10px; }
.plan__steps { display: flex; flex-direction: column; gap: 6px; }
.plan__step {
  display: flex; align-items: center; gap: 10px; font-size: 12px;
  padding: 5px 10px; border-radius: var(--radius-sm); background: var(--bg-card);
  border: 1px solid var(--border-light);
}
.plan__step--reuse { border-color: #a7f3d0; background: #f0fdf4; }
.plan__step--failed { border-color: #fecdd3; background: #fff1f2; }
.plan__no { font-weight: 700; color: var(--text-tertiary); width: 16px; }
.plan__name { flex: 1; color: var(--text-secondary); }
.spec-dialog__edit { display: flex; flex-direction: column; gap: 8px; }
.spec-edit-row { height: auto; align-items: flex-start; margin-right: 0; }
.spec-edit-row :deep(.el-checkbox__label) { display: flex; flex-direction: column; gap: 2px; }
.step-hint { font-size: 11px; color: var(--text-tertiary); line-height: 1.6; white-space: normal; }
.spec-notes { margin-top: 6px; }

/* 批次详情 */
.batch-detail { display: flex; flex-direction: column; gap: 14px; }
.batch-detail__stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
.mini-stat {
  border: 1px solid var(--border-light); border-radius: var(--radius-md);
  padding: 10px; text-align: center; background: var(--bg-card);
}
.mini-stat__num { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.mini-stat__label { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }

@media (max-width: 1280px) {
  .batch { grid-template-columns: 1fr; }
  .batch-detail__stats { grid-template-columns: repeat(3, 1fr); }
}
</style>
