<template>
  <div class="ops-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <template v-if="topTab === 'calendar'">
        <el-button :icon="Download" @click="exportCsv" :loading="exporting">导出 CSV</el-button>
        <el-button :icon="Refresh" @click="loadTasks">刷新</el-button>
      </template>
      <template v-else>
        <el-button :icon="Refresh" @click="loadEffectData">刷新</el-button>
      </template>
    </Teleport>

    <!-- 一级 Tab：运营日历 / 效果分析 -->
    <div class="ops-tabs">
      <button class="ops-tab" :class="{ active: topTab === 'calendar' }" @click="topTab = 'calendar'">
        <el-icon><Calendar /></el-icon> 运营日历
      </button>
      <button class="ops-tab" :class="{ active: topTab === 'effect' }" @click="onTabEffect">
        <el-icon><TrendCharts /></el-icon> 效果分析
      </button>
    </div>

    <!-- ============ 运营日历 ============ -->
    <div v-show="topTab === 'calendar'" class="ops-pane">
      <!-- 状态汇总 -->
      <div class="stat-grid">
        <StatCard label="生产任务总数" :value="stats.total" icon="MagicStick" variant="indigo" />
        <StatCard label="草稿" :value="stats.draft" icon="EditPen" variant="cyan" />
        <StatCard label="进行中" :value="stats.processing" icon="Loading" variant="amber" />
        <StatCard label="已完成 / 已发布" :value="stats.done" icon="CircleCheck" variant="emerald" />
      </div>

      <!-- 工具栏 -->
      <div class="toolbar">
        <el-radio-group v-model="viewMode" size="default">
          <el-radio-button label="timeline" value="timeline">生产时间线</el-radio-button>
          <el-radio-button label="schedule" value="schedule">排期视图</el-radio-button>
        </el-radio-group>

        <div class="month-nav">
          <el-button :icon="ArrowLeft" circle size="small" @click="prevMonth" />
          <span class="month-label">{{ viewYear }} 年 {{ viewMonth + 1 }} 月</span>
          <el-button :icon="ArrowRight" circle size="small" @click="nextMonth" />
          <el-button size="small" @click="goToday">今天</el-button>
        </div>

        <div class="toolbar__right">
          <el-select v-model="statusFilter" size="small" style="width: 120px" @change="applyFilter">
            <el-option label="全部状态" value="all" />
            <el-option label="草稿" value="draft" />
            <el-option label="进行中" value="processing" />
            <el-option label="已完成" value="done" />
            <el-option label="已归档" value="archived" />
          </el-select>
        </div>
      </div>

      <!-- 主体：日历 + 待排期 -->
      <div class="body">
        <div class="cal-card">
          <div class="cal-weekdays">
            <span v-for="w in weekdays" :key="w" class="cal-weekday" :class="{ weekend: w === '六' || w === '日' }">{{ w }}</span>
          </div>
          <div class="cal-grid">
            <div
              v-for="cell in cells"
              :key="cell.key"
              class="cal-cell"
              :class="{ 'is-other': !cell.inMonth, 'is-today': cell.key === todayKey, 'drop-active': dropKey === cell.key }"
              @dragover.prevent="onDayDragOver(cell.key)"
              @dragleave="onDayDragLeave(cell.key)"
              @drop="onDropToDate(cell.key)"
            >
              <div class="cal-cell__date">
                <span class="cal-day">{{ cell.day }}</span>
                <span v-if="cell.key === todayKey" class="cal-today-dot">今天</span>
              </div>
              <div class="cal-cell__tasks">
                <div
                  v-for="t in tasksByDate[cell.key] || []"
                  :key="t.id"
                  class="task-chip"
                  :class="['st-' + t.status, { draggable: viewMode === 'schedule' }]"
                  :draggable="viewMode === 'schedule'"
                  @dragstart="onTaskDragStart(t, $event)"
                  @click="openTask(t)"
                  :title="(t.title || ('任务 #' + t.id)) + ' · ' + taskStatusLabel(t.status)"
                >
                  <span class="task-chip__bar"></span>
                  <span class="task-chip__title">{{ t.title || ('任务 #' + t.id) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 待排期面板（仅排期视图） -->
        <div v-if="viewMode === 'schedule'" class="unscheduled">
          <div class="unscheduled__head">
            <span>待排期</span>
            <el-tag size="small" type="info" effect="plain">{{ unscheduledTasks.length }}</el-tag>
          </div>
          <div class="unscheduled__hint" v-if="unscheduledTasks.length">把任务拖到左侧日历的日期上即可排定发布计划</div>
          <div class="unscheduled__hint" v-else>全部任务已排期 🎉</div>
          <div class="unscheduled__list">
            <div
              v-for="t in unscheduledTasks"
              :key="t.id"
              class="unscheduled__item"
              :class="['st-' + t.status]"
              draggable="true"
              @dragstart="onTaskDragStart(t, $event)"
              @click="openTask(t)"
            >
              <span class="task-chip__bar"></span>
              <span class="unscheduled__title">{{ t.title || ('任务 #' + t.id) }}</span>
              <span class="unscheduled__status">{{ taskStatusLabel(t.status) }}</span>
            </div>
            <EmptyState v-if="!unscheduledTasks.length" title="无待排期任务" description="排期视图下没有未排期的任务" size="small" icon="CircleCheck" />
          </div>
        </div>
      </div>

      <!-- 任务详情抽屉 -->
      <el-drawer v-model="drawerVisible" :title="activeTask ? (activeTask.title || ('任务 #' + activeTask.id)) : ''" size="380px">
        <div v-if="activeTask" class="drawer-body">
          <div class="drawer-row">
            <span class="drawer-label">状态</span>
            <el-tag :type="taskStatusType(activeTask.status)" size="small" effect="light">{{ taskStatusLabel(activeTask.status) }}</el-tag>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">平台</span>
            <span class="drawer-value">{{ platformName(activeTask) }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">进度</span>
            <span class="drawer-value">第 {{ activeTask.current_step || 1 }} / 8 步</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">创建时间</span>
            <span class="drawer-value">{{ formatDateTime(activeTask.create_time) }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">发布链接</span>
            <span class="drawer-value">{{ activeTask.publish_url || '—' }}</span>
          </div>

          <el-divider />

          <div class="drawer-field">
            <div class="drawer-label" style="margin-bottom: 8px;">计划发布日期</div>
            <el-date-picker
              v-model="planDateModel"
              type="date"
              value-format="YYYY-MM-DD"
              format="YYYY-MM-DD"
              placeholder="选择计划发布日"
              style="width: 100%"
            />
            <div class="drawer-actions">
              <el-button size="small" @click="setPlanDate(todayKey)">设为今天</el-button>
              <el-button size="small" @click="setPlanDate('')">清除排期</el-button>
              <el-button size="small" type="primary" :loading="savingPlan" @click="savePlanDate">保存</el-button>
            </div>
          </div>

          <el-button class="drawer-open" type="primary" plain style="width: 100%" @click="openProduction(activeTask)">在软文生产中打开</el-button>
        </div>
      </el-drawer>
    </div>

    <!-- ============ 效果分析 ============ -->
    <div v-show="topTab === 'effect'" class="ops-pane">
      <!-- 核心指标 -->
      <div class="stat-grid">
        <StatCard label="内容总数" :value="dashboard.total_content || 0" icon="Document" variant="indigo" />
        <StatCard label="审核通过率" :value="dashboard.pass_rate || 0" icon="CircleCheck" variant="emerald" suffix="%" />
        <StatCard label="品牌露出率" :value="dashboard.brand_rate || 0" icon="GoldMedal" variant="amber" suffix="%" />
        <StatCard label="官网露出率" :value="dashboard.website_rate || 0" icon="Link" variant="violet" suffix="%" />
      </div>

      <!-- 分段切换 -->
      <div class="section-tabs">
        <button class="section-tab" :class="{ active: effTab === 'dashboard' }" @click="effTab = 'dashboard'">
          <el-icon><TrendCharts /></el-icon> 数据看板
        </button>
        <button class="section-tab" :class="{ active: effTab === 'record' }" @click="onEffTabRecord">
          <el-icon><EditPen /></el-icon> 效果录入
        </button>
      </div>

      <!-- 数据看板 -->
      <div v-show="effTab === 'dashboard'" class="dashboard-block">
        <el-row :gutter="16">
          <el-col :span="12">
            <div class="chart-card">
              <div class="chart-head"><span class="chart-title">各平台内容产出</span></div>
              <div class="chart-body">
                <div v-for="p in dashboard.platform_stats || []" :key="p.name" class="bar-row">
                  <span class="bar-label">{{ p.name }}</span>
                  <div class="bar-track"><div class="bar-fill" :style="{ width: barWidth(p.count) }"></div></div>
                  <span class="bar-value">{{ p.count }}</span>
                </div>
                <div v-if="!(dashboard.platform_stats || []).length" class="empty-tip">暂无数据</div>
              </div>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="chart-card">
              <div class="chart-head"><span class="chart-title">账号产出排行 TOP10</span></div>
              <div class="chart-body">
                <div v-for="(a, idx) in dashboard.account_stats || []" :key="a.id" class="rank-row">
                  <span class="rank-no" :class="{ top: idx < 3 }">{{ idx + 1 }}</span>
                  <span class="rank-name">{{ a.name }}</span>
                  <span class="rank-platform">{{ a.platform }}</span>
                  <span class="rank-count">{{ a.count }} 篇</span>
                </div>
                <div v-if="!(dashboard.account_stats || []).length" class="empty-tip">暂无数据</div>
              </div>
            </div>
          </el-col>
        </el-row>
      </div>

      <!-- 效果录入 -->
      <div v-show="effTab === 'record'" class="table-card" v-loading="effLoading">
        <div class="table-head">
          <span class="table-title">效果记录</span>
          <el-button type="primary" size="small" :icon="Plus" @click="openCreate">录入数据</el-button>
        </div>
        <el-table :data="effList" stripe style="width: 100%">
          <el-table-column label="关键词" min-width="160">
            <template #default="{ row }"><span style="font-weight: 600;">{{ row.keyword_word || '—' }}</span></template>
          </el-table-column>
          <el-table-column label="AI模型" width="120">
            <template #default="{ row }">{{ row.model_type || '—' }}</template>
          </el-table-column>
          <el-table-column label="品牌露出" width="100">
            <template #default="{ row }"><el-tag :type="row.has_brand ? 'success' : 'danger'" size="small">{{ row.has_brand ? '是' : '否' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="官网露出" width="100">
            <template #default="{ row }"><el-tag :type="row.has_website ? 'success' : 'danger'" size="small">{{ row.has_website ? '是' : '否' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="联系方式" width="100">
            <template #default="{ row }"><el-tag :type="row.has_contact ? 'success' : 'danger'" size="small">{{ row.has_contact ? '是' : '否' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="排名" width="80">
            <template #default="{ row }">{{ row.rank || '—' }}</template>
          </el-table-column>
          <el-table-column label="记录日期" width="120">
            <template #default="{ row }">{{ row.record_date || '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" type="danger" :icon="Delete" @click="remove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <EmptyState v-if="!effLoading && effList.length === 0" title="暂无效果记录" description="手动录入目标关键词在主流大模型中的检索结果" icon="TrendCharts" />
      </div>

      <!-- 录入弹窗 -->
      <el-dialog v-model="createDialog" title="录入效果数据" width="520px">
        <el-form :model="form" label-width="100px">
          <el-form-item label="关键词">
            <el-select v-model="form.keyword_id" placeholder="选择关键词" style="width: 100%;">
              <el-option v-for="k in keywords" :key="k.id" :label="k.word" :value="k.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="AI模型">
            <el-select v-model="form.model_type" style="width: 100%;">
              <el-option label="ChatGPT" value="ChatGPT" />
              <el-option label="Claude" value="Claude" />
              <el-option label="文心一言" value="文心一言" />
              <el-option label="通义千问" value="通义千问" />
              <el-option label="智谱清言" value="智谱清言" />
              <el-option label="Kimi" value="Kimi" />
            </el-select>
          </el-form-item>
          <el-form-item label="品牌露出"><el-switch v-model="form.has_brand" :active-value="1" :inactive-value="0" /></el-form-item>
          <el-form-item label="官网露出"><el-switch v-model="form.has_website" :active-value="1" :inactive-value="0" /></el-form-item>
          <el-form-item label="联系方式"><el-switch v-model="form.has_contact" :active-value="1" :inactive-value="0" /></el-form-item>
          <el-form-item label="排名"><el-input-number v-model="form.rank" :min="0" :max="100" style="width: 100%;" /></el-form-item>
          <el-form-item label="记录日期"><el-input v-model="form.record_date" placeholder="YYYY-MM-DD" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="createDialog = false">取消</el-button>
          <el-button type="primary" @click="saveEffect">保存</el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Refresh, ArrowLeft, ArrowRight, Plus, Delete, TrendCharts, EditPen, Calendar } from '@element-plus/icons-vue'
import { useAppStore } from '../../store/app'
import { productionApi, effectApi, keywordApi } from '../../api'
import { toDateKey, addDays, formatDateTime } from '../../utils/format'
import { taskStatusLabel, taskStatusType } from '../../constants/status'
import { downloadCsv } from '../../utils/download'
import StatCard from '../StatCard.vue'
import EmptyState from '../EmptyState.vue'

const router = useRouter()
const store = useAppStore()
const pageActionsTarget = inject('pageActionsTarget', null)

const topTab = ref('calendar') // 'calendar' | 'effect'

/* ===================== 运营日历 ===================== */
const loading = ref(false)
const exporting = ref(false)
const savingPlan = ref(false)
const tasks = ref([])
const viewMode = ref('timeline')
const statusFilter = ref('all')

const weekdays = ['一', '二', '三', '四', '五', '六', '日']

const today = new Date()
const viewYear = ref(today.getFullYear())
const viewMonth = ref(today.getMonth())
const todayKey = toDateKey(today)

const dropKey = ref(null)
const dragTaskId = ref(null)

const drawerVisible = ref(false)
const activeTask = ref(null)
const planDateModel = ref('')


function dateKeyOf(t) {
  if (viewMode.value === 'schedule') return t.plan_date || ''
  return (t.create_time || '').slice(0, 10)
}

const filteredTasks = computed(() => {
  if (statusFilter.value === 'all') return tasks.value
  return tasks.value.filter(t => t.status === statusFilter.value)
})

const stats = computed(() => {
  const all = tasks.value
  return {
    total: all.length,
    draft: all.filter(t => t.status === 'draft').length,
    processing: all.filter(t => t.status === 'processing').length,
    done: all.filter(t => t.status === 'done' || t.status === 'archived').length,
  }
})

const tasksByDate = computed(() => {
  const map = {}
  for (const t of filteredTasks.value) {
    const k = dateKeyOf(t)
    if (!k) continue
    ;(map[k] = map[k] || []).push(t)
  }
  return map
})

const unscheduledTasks = computed(() => {
  if (viewMode.value !== 'schedule') return []
  return filteredTasks.value.filter(t => !t.plan_date)
})

const cells = computed(() => {
  const first = new Date(viewYear.value, viewMonth.value, 1)
  const startWeekday = (first.getDay() + 6) % 7 // 周一=0
  const start = addDays(first, -startWeekday)
  const out = []
  for (let i = 0; i < 42; i++) {
    const d = addDays(start, i)
    const key = toDateKey(d)
    out.push({
      key,
      day: d.getDate(),
      inMonth: d.getMonth() === viewMonth.value,
    })
  }
  return out
})

function platformName(t) {
  if (!t.platform_snapshot) return t.platform_id ? `平台#${t.platform_id}` : '未设平台'
  try {
    const p = JSON.parse(t.platform_snapshot)
    return p?.name || p?.platform || (t.platform_id ? `平台#${t.platform_id}` : '未设平台')
  } catch {
    return t.platform_id ? `平台#${t.platform_id}` : '未设平台'
  }
}

async function loadTasks() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const res = await productionApi.list({ industry_id: store.currentIndustryId })
    tasks.value = res.data || []
  } catch (e) {
    console.error('加载生产任务失败', e)
    ElMessage.error('加载生产任务失败')
  } finally {
    loading.value = false
  }
}

function applyFilter() { /* computed 已响应，无需额外操作 */ }

function prevMonth() {
  if (viewMonth.value === 0) { viewMonth.value = 11; viewYear.value-- } else viewMonth.value--
}
function nextMonth() {
  if (viewMonth.value === 11) { viewMonth.value = 0; viewYear.value++ } else viewMonth.value++
}
function goToday() {
  const n = new Date()
  viewYear.value = n.getFullYear()
  viewMonth.value = n.getMonth()
}

// ===== 拖拽排期 =====
function onTaskDragStart(t, e) {
  dragTaskId.value = t.id
  if (e?.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(t.id))
  }
}
function onDayDragOver(key) {
  if (viewMode.value !== 'schedule') return
  dropKey.value = key
}
function onDayDragLeave(key) {
  if (dropKey.value === key) dropKey.value = null
}
async function onDropToDate(key) {
  dropKey.value = null
  const id = dragTaskId.value
  dragTaskId.value = null
  if (!id) return
  await applyPlanDate(id, key)
}

async function applyPlanDate(id, date) {
  try {
    await productionApi.update(id, { plan_date: date })
    await loadTasks()
    ElMessage.success(date ? `已排期到 ${date}` : '已清除排期')
  } catch (e) {
    console.error('排期失败', e)
    ElMessage.error('排期失败')
  }
}

// ===== 抽屉 =====
function openTask(t) {
  activeTask.value = t
  planDateModel.value = t.plan_date || ''
  drawerVisible.value = true
}
function setPlanDate(date) {
  planDateModel.value = date
}
async function savePlanDate() {
  if (!activeTask.value) return
  savingPlan.value = true
  try {
    await applyPlanDate(activeTask.value.id, planDateModel.value)
    if (activeTask.value) activeTask.value.plan_date = planDateModel.value
  } finally {
    savingPlan.value = false
  }
}
function openProduction(t) {
  drawerVisible.value = false
  router.push('/production')
}

// ===== CSV 导出 =====
function exportCsv() {
  if (!tasks.value.length) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  exporting.value = true
  try {
    const rows = tasks.value.map(t => [
      t.title || `任务 #${t.id}`,
      taskStatusLabel(t.status),
      platformName(t),
      (t.create_time || '').slice(0, 10),
      t.plan_date || '',
    ])
    downloadCsv(
      [['标题', '状态', '平台', '创建日期', '计划发布日'], ...rows],
      `内容运营日历_${store.currentIndustryName || '行业'}_${todayKey}.csv`,
    )
    ElMessage.success('已导出 CSV')
  } finally {
    exporting.value = false
  }
}

/* ===================== 效果分析 ===================== */
const effTab = ref('dashboard')
const effLoading = ref(false)
const dashboard = ref({})
const effList = ref([])
const keywords = ref([])
const createDialog = ref(false)
const form = ref({})
const effLoaded = ref(false)

async function loadDashboard() {
  const res = await effectApi.dashboard(store.currentIndustryId)
  dashboard.value = res.data || {}
}
async function loadEffects() {
  const res = await effectApi.list(store.currentIndustryId)
  effList.value = res.data || []
}
async function loadKeywords() {
  const res = await keywordApi.list(store.currentIndustryId)
  keywords.value = res.data || []
}
async function loadEffectData() {
  if (!store.currentIndustryId) return
  await Promise.all([loadDashboard(), loadKeywords()])
  effLoaded.value = true
}

function barWidth(count) {
  const max = Math.max(...(dashboard.value.platform_stats || []).map(p => p.count), 1)
  return (count / max * 100) + '%'
}

function onTabEffect() {
  topTab.value = 'effect'
  if (!effLoaded.value) loadEffectData()
}
function onEffTabRecord() {
  effTab.value = 'record'
  if (effLoaded.value && effList.value.length === 0) loadEffects()
}

function openCreate() {
  form.value = {
    keyword_id: keywords.value[0]?.id,
    model_type: 'ChatGPT',
    // 这里必须用本地日期。原先写的是 `new Date().toISOString().slice(0, 10)`——
    // toISOString 输出的是 **UTC** 日期，东八区下午 4 点后拿到的就是「昨天」，
    // 默认记录日期会整整差一天。toDateKey 按本地时区取。
    record_date: toDateKey(new Date()),
    has_brand: 0, has_website: 0, has_contact: 0, rank: 0, remark: '',
  }
  createDialog.value = true
}

async function saveEffect() {
  if (!form.value.keyword_id) { ElMessage.warning('请选择关键词'); return }
  await effectApi.create({ ...form.value, industry_id: store.currentIndustryId })
  ElMessage.success('已录入')
  createDialog.value = false
  await loadEffects()
  await loadDashboard()
}

async function remove(row) {
  await ElMessageBox.confirm('确定删除该记录？', '提示', { type: 'warning' })
  await effectApi.delete(row.id)
  ElMessage.success('已删除')
  await loadEffects()
  await loadDashboard()
}

/* ===================== 生命周期 ===================== */
async function loadAll() {
  await Promise.all([loadTasks(), loadEffectData()])
}

watch(() => store.currentIndustryId, loadAll)
onMounted(loadAll)
</script>

<style scoped>
.ops-view { display: flex; flex-direction: column; gap: 16px; }

/* 一级 Tab */
.ops-tabs { display: flex; gap: 8px; }
.ops-tab {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 18px; border-radius: var(--radius-md);
  border: 1px solid var(--border-light); background: var(--bg-card);
  color: var(--text-secondary); font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all 0.16s;
}
.ops-tab:hover { border-color: var(--brand-300); color: var(--brand-600); }
.ops-tab.active {
  background: linear-gradient(135deg, var(--brand-600), var(--brand-500));
  color: #fff; border-color: transparent;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
}
.ops-tab .el-icon { font-size: 15px; }

.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }

/* ===== 日历 ===== */
.toolbar { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.month-nav { display: flex; align-items: center; gap: 8px; }
.month-label { font-size: 14px; font-weight: 600; color: var(--text-primary); min-width: 110px; text-align: center; }
.toolbar__right { margin-left: auto; }

.body { display: flex; gap: 16px; align-items: flex-start; }
.cal-card {
  flex: 1;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.cal-weekdays { display: grid; grid-template-columns: repeat(7, 1fr); border-bottom: 1px solid var(--border-light); }
.cal-weekday {
  padding: 10px 0; text-align: center; font-size: 12px; font-weight: 600;
  color: var(--text-tertiary); background: var(--slate-50);
}
.cal-weekday.weekend { color: var(--text-quaternary); }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); }

.cal-cell {
  min-height: 116px;
  border-right: 1px solid var(--border-light);
  border-bottom: 1px solid var(--border-light);
  padding: 6px 6px 8px;
  display: flex; flex-direction: column; gap: 4px;
  transition: background 0.15s;
}
.cal-cell:nth-child(7n) { border-right: none; }
.cal-cell.is-other { background: var(--slate-50); }
.cal-cell.is-other .cal-day { color: var(--text-quaternary); }
.cal-cell.is-today { background: var(--brand-50); }
.cal-cell.drop-active { background: #eef2ff; box-shadow: inset 0 0 0 2px var(--brand-400); }

.cal-cell__date { display: flex; align-items: center; gap: 6px; }
.cal-day { font-size: 12px; font-weight: 600; color: var(--text-secondary); }
.cal-today-dot {
  font-size: 10px; padding: 1px 6px; border-radius: var(--radius-full);
  background: var(--brand-600); color: #fff; font-weight: 600;
}
.cal-cell__tasks { display: flex; flex-direction: column; gap: 4px; overflow: hidden; }

.task-chip {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 7px; border-radius: 6px;
  background: var(--slate-100); cursor: pointer;
  font-size: 12px; color: var(--text-primary);
  border: 1px solid transparent;
  transition: all 0.15s;
}
.task-chip:hover { border-color: var(--brand-300); }
.task-chip.draggable { cursor: grab; }
.task-chip.draggable:active { cursor: grabbing; }
.task-chip__bar { width: 4px; height: 14px; border-radius: 2px; flex-shrink: 0; background: var(--slate-400); }
.task-chip__title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-chip.st-draft .task-chip__bar { background: #818cf8; }
.task-chip.st-processing .task-chip__bar { background: #f59e0b; }
.task-chip.st-done .task-chip__bar { background: #10b981; }
.task-chip.st-archived .task-chip__bar { background: #94a3b8; }
.task-chip.st-done { background: #ecfdf5; }
.task-chip.st-processing { background: #fffbeb; }

.unscheduled {
  width: 260px; flex-shrink: 0;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: var(--shadow-sm);
  align-self: stretch;
}
.unscheduled__head { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 600; color: var(--text-primary); }
.unscheduled__hint { font-size: 12px; color: var(--text-tertiary); margin: 8px 0 12px; line-height: 1.5; }
.unscheduled__list { display: flex; flex-direction: column; gap: 8px; }
.unscheduled__item {
  display: flex; align-items: center; gap: 8px;
  padding: 9px 10px; border-radius: var(--radius-md);
  background: var(--slate-50); border: 1px solid var(--border-light);
  cursor: grab; font-size: 12px;
  transition: all 0.15s;
}
.unscheduled__item:active { cursor: grabbing; }
.unscheduled__item:hover { border-color: var(--brand-300); }
.unscheduled__item .task-chip__bar { width: 4px; height: 14px; border-radius: 2px; background: var(--slate-400); }
.unscheduled__item.st-draft .task-chip__bar { background: #818cf8; }
.unscheduled__item.st-processing .task-chip__bar { background: #f59e0b; }
.unscheduled__item.st-done .task-chip__bar { background: #10b981; }
.unscheduled__item.st-archived .task-chip__bar { background: #94a3b8; }
.unscheduled__title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
.unscheduled__status { font-size: 11px; color: var(--text-tertiary); flex-shrink: 0; }

.drawer-body { display: flex; flex-direction: column; gap: 14px; }
.drawer-row { display: flex; align-items: center; gap: 12px; }
.drawer-label { font-size: 13px; color: var(--text-tertiary); width: 72px; flex-shrink: 0; }
.drawer-value { font-size: 13px; color: var(--text-primary); font-weight: 500; }
.drawer-field { display: flex; flex-direction: column; }
.drawer-actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.drawer-open { margin-top: 4px; }

/* ===== 效果分析 ===== */
.section-tabs { display: flex; gap: 8px; }
.section-tab {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 18px; border-radius: var(--radius-md);
  border: 1px solid var(--border-light); background: var(--bg-card);
  color: var(--text-secondary); font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all 0.16s;
}
.section-tab:hover { border-color: var(--brand-300); color: var(--brand-600); }
.section-tab.active { background: var(--brand-50); color: var(--brand-600); border-color: var(--brand-300); }

.chart-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.chart-head { padding: 14px 20px; border-bottom: 1px solid var(--border-light); }
.chart-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.chart-body { padding: 16px 20px; }

.bar-row { display: flex; align-items: center; margin-bottom: 14px; gap: 12px; }
.bar-label { width: 90px; font-size: 13px; color: var(--text-secondary); }
.bar-track { flex: 1; height: 20px; background: var(--slate-100); border-radius: 10px; overflow: hidden; }
.bar-fill { height: 100%; background: linear-gradient(90deg, var(--brand-500), var(--accent-cyan)); border-radius: 10px; transition: width 0.6s; }
.bar-value { width: 50px; text-align: right; font-size: 13px; font-weight: 600; color: var(--text-primary); }

.rank-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border-light); }
.rank-row:last-child { border-bottom: none; }
.rank-no {
  width: 24px; height: 24px; border-radius: var(--radius-full);
  background: var(--slate-100); color: var(--text-tertiary);
  font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.rank-no.top { background: var(--brand-600); color: #fff; }
.rank-name { flex: 1; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.rank-platform { font-size: 12px; color: var(--text-tertiary); }
.rank-count { font-size: 13px; font-weight: 600; color: var(--brand-600); }

.table-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  min-height: 300px;
}
.table-head { padding: 14px 20px; border-bottom: 1px solid var(--border-light); display: flex; align-items: center; justify-content: space-between; }
.table-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.empty-tip { text-align: center; padding: 40px; color: var(--text-tertiary); font-size: 13px; }

@media (max-width: 1100px) {
  .body { flex-direction: column; }
  .unscheduled { width: 100%; }
}
@media (max-width: 1024px) {
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
