<template>
  <div class="iq-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button :icon="MagicStick" @click="openAssistantPrompt" :loading="promptLoading">辅助提示词</el-button>
      <el-button :icon="Upload" @click="importDialog = true">批量导入</el-button>
      <el-button :icon="MagicStick" @click="seedDefaults" :loading="seeding">预置默认</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建意图问题</el-button>
    </Teleport>

    <!-- 顶部：GEO 价值说明 + 覆盖率指标 -->
    <section class="hero">
      <div class="hero__lead">
        <div class="hero__tags">
          <span class="hero__eyebrow"><el-icon><Aim /></el-icon> GEO 作战 · 模块① 地基</span>
          <el-tag size="small" effect="plain" class="hero__industry"><el-icon><OfficeBuilding /></el-icon> 当前行业：{{ store.currentIndustryName }}</el-tag>
        </div>
        <h2 class="hero__title">沉淀意图问题库：把「客户会问 AI 什么」变成可被推荐、可量化覆盖的清单</h2>
        <p class="hero__desc">按目标画像归类每个真实问题，标注期望 AI 推荐我们的角度与覆盖状态。左侧按画像分组，右侧逐条管理——这是后续软文选题与 GEO 评分闸门的事实基础。</p>
      </div>
      <div class="hero__metrics">
        <div class="metric">
          <div class="metric__num">{{ questions.length }}</div>
          <div class="metric__label">意图问题</div>
        </div>
        <div class="metric metric--ok">
          <div class="metric__num">{{ coveredCount }}</div>
          <div class="metric__label">已覆盖</div>
        </div>
        <div class="metric metric--gap">
          <div class="metric__num">{{ gapCount }}</div>
          <div class="metric__label">待覆盖</div>
        </div>
        <div class="metric metric--cover">
          <div class="cover" :title="`GEO 覆盖率 ${coverRate}%`">
            <div class="cover__track"><div class="cover__fill" :style="{ width: coverRate + '%' }"></div></div>
            <div class="cover__pct">覆盖率 {{ coverRate }}%</div>
          </div>
        </div>
      </div>
    </section>

    <div class="iq-body">
      <!-- 左侧：按画像分组 -->
      <aside class="iq-side">
        <header class="iq-side__head">
          <span class="iq-side__title"><el-icon><User /></el-icon> 按画像分组</span>
        </header>
        <div class="iq-side__list">
          <button class="gitem" :class="{ active: activePersona === null }" @click="activePersona = null">
            <span class="gitem__icon" style="color:#6366f1"><el-icon><Aim /></el-icon></span>
            <span class="gitem__main"><span class="gitem__name">全部画像</span></span>
            <span class="gitem__count">{{ questions.length }}</span>
          </button>
          <transition-group name="cat-list" tag="div" class="iq-side__group">
            <div
              class="gitem"
              :class="{ active: activePersona === p.id }"
              v-for="p in personas"
              :key="p.id"
              @click="activePersona = p.id"
            >
              <span class="gitem__icon" :style="{ color: p.color || '#6366f1' }"><el-icon><component :is="personaIconOf(p)" /></el-icon></span>
              <span class="gitem__main">
                <span class="gitem__name">{{ p.name }}</span>
                <span class="gitem__sub">{{ roleLabel(p.role_type) }} · {{ p.question_count }} 问</span>
              </span>
              <span class="gitem__count">{{ p.question_count }}</span>
            </div>
          </transition-group>
          <button class="gitem" :class="{ active: activePersona === -1 }" @click="activePersona = -1">
            <span class="gitem__icon" style="color:#94a3b8"><el-icon><Document /></el-icon></span>
            <span class="gitem__main"><span class="gitem__name">未关联画像</span></span>
            <span class="gitem__count">{{ unlinkedCount }}</span>
          </button>
        </div>
      </aside>

      <!-- 右侧：问题表 -->
      <section class="iq-main" v-loading="loading">
        <header class="iq-main__head">
          <div class="iq-main__title">
            <el-icon><ChatDotRound /></el-icon> 意图问题
            <el-tag size="small" type="info" round>{{ displayQuestions.length }}</el-tag>
          </div>
          <div class="iq-main__tools">
            <el-select v-model="filterCategory" placeholder="全部意图" clearable size="small" style="width: 124px;">
              <el-option label="选型" value="selection" />
              <el-option label="成本" value="cost" />
              <el-option label="集成落地" value="integration" />
              <el-option label="风险" value="risk" />
              <el-option label="合规" value="compliance" />
              <el-option label="其他" value="other" />
            </el-select>
            <el-select v-model="filterCoverage" placeholder="全部覆盖" clearable size="small" style="width: 116px;">
              <el-option label="已覆盖" value="covered" />
              <el-option label="待覆盖" value="gap" />
            </el-select>
            <el-select v-model="sortBy" size="small" style="width: 138px;">
              <el-option label="按优先级" value="priority" />
              <el-option label="按意图" value="category" />
              <el-option label="按问题" value="question" />
              <el-option label="默认（可拖拽）" value="default" />
            </el-select>
            <el-button size="small" :icon="Operation" :type="batchMode ? 'primary' : 'default'" @click="batchMode = !batchMode">
              {{ batchMode ? '退出批量' : '批量管理' }}
            </el-button>
          </div>
        </header>

        <div class="iq-toolbar">
          <el-input v-model="qSearch" placeholder="查找问题 / 期望推荐角度..." size="small" :prefix-icon="Search" clearable style="flex: 1;" />
        </div>

        <div class="qtable" :class="{ batch: batchMode }">
          <div class="qtable__head">
            <div class="qc qc--sel" v-if="batchMode">
              <el-checkbox :model-value="qSelection.length === displayQuestions.length && displayQuestions.length > 0" @change="toggleSelectAll" />
            </div>
            <div class="qc qc--q">目标客户会问 AI 的问题</div>
            <div class="qc qc--cat">意图</div>
            <div class="qc qc--expect">期望 AI 推荐我们的角度</div>
            <div class="qc qc--pri">优先级</div>
            <div class="qc qc--cov">覆盖</div>
            <div class="qc qc--act">操作</div>
          </div>
          <VirtualList
            class="qtable__body"
            :items="displayQuestions"
            :row-height="132"
            :gap="0"
            :focus-id="focusId"
            :get-key="(it) => it.id"
            #default="{ item, index }"
          >
            <div class="qrow" :class="[index % 2 === 1 ? 'striped' : '', 'focus-row-' + item.id]" :data-focus-id="item.id">
              <div class="qc qc--sel" v-if="batchMode">
                <el-checkbox :model-value="qSelection.includes(item.id)" @change="() => toggleSelect(item)" />
              </div>
              <div class="qc qc--q">
                <div class="qrow__q">{{ item.question }}</div>
                <div class="qrow__tags">
                  <span v-if="item.persona_name" class="tag tag--persona">{{ item.persona_name }}</span>
                  <span class="tag tag--src">{{ sourceLabel(item.source) }}</span>
                </div>
              </div>
              <div class="qc qc--cat">
                <el-tag size="small" :type="catColor(item.intent_category)" effect="light">{{ catLabel(item.intent_category) }}</el-tag>
              </div>
              <div class="qc qc--expect">{{ item.expected_recommendation || '—' }}</div>
              <div class="qc qc--pri"><el-rate :model-value="item.priority" disabled size="small" /></div>
              <div class="qc qc--cov">
                <el-tag size="small" :type="item.coverage_status === 'covered' ? 'success' : 'warning'" effect="light" class="cov" @click="toggleCoverage(item)" title="点击切换覆盖状态">
                  {{ item.coverage_status === 'covered' ? '已覆盖' : '待覆盖' }}
                </el-tag>
              </div>
              <div class="qc qc--act">
                <el-button text size="small" :icon="Edit" @click="openEdit(item)">编辑</el-button>
                <el-button text size="small" type="danger" :icon="Delete" @click="remove(item)">删除</el-button>
              </div>
            </div>
          </VirtualList>
        </div>

        <div v-if="batchMode && qSelection.length" class="iq-batchbar">
          <span class="iq-batchbar__count">已选 <b>{{ qSelection.length }}</b> 个</span>
          <el-button size="small" type="danger" :icon="Delete" :loading="batchSubmitting" @click="onBatchDelete">删除</el-button>
          <el-button size="small" @click="clearSelection">取消选择</el-button>
        </div>

        <EmptyState v-if="!loading && displayQuestions.length === 0" title="暂无意图问题" size="small" icon="Aim"
          hint="点右上角「新建意图问题」，或「预置默认」一键生成三类画像的典型问题。" />
      </section>
    </div>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialog" :title="editing ? '编辑意图问题' : '新建意图问题'" width="640px">
      <el-form :model="form" label-width="96px">
        <el-form-item label="目标客户问题">
          <el-input v-model="form.question" type="textarea" :rows="3" placeholder="客户会原话问 AI 的问题，如：我们工厂想上真空产线大概要花多少钱？" />
        </el-form-item>
        <el-form-item label="关联画像">
          <el-select v-model="form.persona_id" placeholder="未关联" clearable style="width: 100%;">
            <el-option label="未关联" :value="0" />
            <el-option v-for="p in personas" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="意图分类">
          <el-select v-model="form.intent_category" style="width: 100%;">
            <el-option label="选型（怎么选供应商）" value="selection" />
            <el-option label="成本（多少钱/报价）" value="cost" />
            <el-option label="集成落地（怎么接入）" value="integration" />
            <el-option label="风险（安全/踩坑）" value="risk" />
            <el-option label="合规（资质/认证）" value="compliance" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="期望推荐角度">
          <el-input v-model="form.expected_recommendation" type="textarea" :rows="3" placeholder="当 AI 回答此问题时，希望它如何推荐我们（话术要点/卖点）" />
        </el-form-item>
        <el-form-item label="优先级"><el-rate v-model="form.priority" :max="3" /></el-form-item>
        <el-form-item label="覆盖状态">
          <el-select v-model="form.coverage_status" style="width: 100%;">
            <el-option label="待覆盖（还没有对应软文）" value="gap" />
            <el-option label="已覆盖（已有软文命中）" value="covered" />
          </el-select>
        </el-form-item>
        <el-form-item label="问题来源">
          <el-select v-model="form.source" style="width: 100%;">
            <el-option label="手动录入" value="manual" />
            <el-option label="客户访谈" value="interview" />
            <el-option label="客服记录" value="support" />
            <el-option label="搜索词" value="search" />
            <el-option label="竞品分析" value="competitor" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入弹窗 -->
    <el-dialog v-model="importDialog" title="批量导入意图问题" width="640px">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        <template #title>粘贴 JSON 数组，每行一个问题对象（按问题原文 upsert）</template>
        <template #default>字段：question（必填）、persona_name（关联画像名）、intent_category、expected_recommendation、priority、coverage_status、source</template>
      </el-alert>
      <el-input v-model="importText" type="textarea" :rows="11" placeholder='例如：[{"question":"真空泵怎么选型？","persona_name":"真空工艺工程师","intent_category":"selection","expected_recommendation":"给出选型 5 问并带出我方优势"}]' />
      <template #footer>
        <el-button text @click="downloadTemplate">下载模板</el-button>
        <el-button @click="importDialog = false">取消</el-button>
        <el-button type="primary" @click="importBatch" :loading="importing">导入</el-button>
      </template>
    </el-dialog>

    <!-- 辅助提示词弹窗 -->
    <el-dialog v-model="promptDialog" title="辅助提示词" width="720px" class="assist-dialog">
      <el-alert type="success" :closable="false" show-icon style="margin-bottom: 14px;">
        <template #title>📋 使用步骤</template>
        <template #default>
          1. 点击下方「复制提示词」→ 2. 粘贴到 ChatGPT / Kimi / 豆包等 AI → 3. 将 AI 返回的 JSON 粘贴到「批量导入」
        </template>
      </el-alert>

      <div class="assist-meta" v-if="promptMeta">
        <el-tag size="small" effect="plain" type="info"><el-icon><User /></el-icon> {{ promptMeta.persona_count }} 个目标画像</el-tag>
        <el-tag size="small" effect="plain" type="warning"><el-icon><ChatDotRound /></el-icon> {{ promptMeta.existing_question_count }} 条已有问题</el-tag>
        <el-tag size="small" effect="plain" type="success"><el-icon><OfficeBuilding /></el-icon> {{ promptMeta.brand_count }} 个品牌资产</el-tag>
      </div>

      <div class="assist-prompt-box">
        <pre class="assist-prompt" v-text="promptText"></pre>
      </div>

      <template #footer>
        <el-button @click="promptDialog = false">关闭</el-button>
        <el-button type="primary" :icon="Document" @click="copyPrompt">复制提示词</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Edit, Delete, Aim, Search, Operation, Rank, Document, MagicStick, Upload, Download, ChatDotRound, User,
  OfficeBuilding, Cpu, ShoppingCart, Avatar, UserFilled,
} from '@element-plus/icons-vue'
import { useFocusScroll } from '../composables/useFocusScroll'
import { useAppStore } from '../store/app'
import { targetPersonaApi, intentQuestionApi } from '../api'
import EmptyState from '../components/EmptyState.vue'
import VirtualList from '../components/VirtualList.vue'

const store = useAppStore()
const route = useRoute()
const focusId = computed(() => route.query.focus)

const loading = ref(false)
const saving = ref(false)
const seeding = ref(false)
const personas = ref([])
const questions = ref([])
const activePersona = ref(null)

const qSearch = ref('')
const filterCategory = ref('')
const filterCoverage = ref('')
const sortBy = ref('priority')
const batchMode = ref(false)
const qSelection = ref([])
const batchSubmitting = ref(false)

const iconMap = { User, OfficeBuilding, Cpu, ShoppingCart, Avatar, UserFilled, Aim }
const iconOptions = ['User', 'OfficeBuilding', 'Cpu', 'ShoppingCart', 'Avatar', 'UserFilled', 'Aim']
function personaIconOf(p) { return iconMap[p?.icon] || User }

function roleLabel(r) { return { decision_maker: '决策层', technical: '技术层', procurement: '采购层', other: '其他' }[r] || '其他' }
function catLabel(c) { return { selection: '选型', cost: '成本', integration: '集成落地', risk: '风险', compliance: '合规', other: '其他' }[c] || '其他' }
function catColor(c) { return { selection: 'success', cost: 'warning', integration: 'primary', risk: 'danger', compliance: 'info', other: 'info' }[c] || 'info' }
function sourceLabel(s) { return { manual: '手动', interview: '访谈', support: '客服', search: '搜索词', competitor: '竞品' }[s] || '手动' }

const coveredCount = computed(() => questions.value.filter(q => q.coverage_status === 'covered').length)
const gapCount = computed(() => questions.value.filter(q => q.coverage_status === 'gap').length)
const unlinkedCount = computed(() => questions.value.filter(q => !q.persona_id).length)
const coverRate = computed(() => questions.value.length ? Math.round(coveredCount.value / questions.value.length * 100) : 0)

const displayQuestions = computed(() => {
  let arr = questions.value
  if (activePersona.value === -1) arr = arr.filter(q => !q.persona_id)
  else if (activePersona.value != null) arr = arr.filter(q => q.persona_id === activePersona.value)
  if (filterCategory.value) arr = arr.filter(q => q.intent_category === filterCategory.value)
  if (filterCoverage.value) arr = arr.filter(q => q.coverage_status === filterCoverage.value)
  const k = (qSearch.value || '').trim().toLowerCase()
  if (k) arr = arr.filter(q =>
    (q.question || '').toLowerCase().includes(k) ||
    (q.expected_recommendation || '').toLowerCase().includes(k)
  )
  const by = sortBy.value
  const dir = -1 // 列表默认降序（高优先级/靠前的在前）
  if (by === 'priority') arr = [...arr].sort((a, b) => (b.priority - a.priority) * dir)
  else if (by === 'category') arr = [...arr].sort((a, b) => (a.intent_category || '').localeCompare(b.intent_category || '', 'zh-CN') * dir)
  else if (by === 'question') arr = [...arr].sort((a, b) => (a.question || '').localeCompare(b.question || '', 'zh-CN') * dir)
  return arr
})

// ===== 弹窗 =====
const dialog = ref(false)
const editing = ref(false)
const form = ref(blank())
function blank() {
  return {
    question: '', persona_id: activePersona.value && activePersona.value > 0 ? activePersona.value : 0,
    intent_category: 'selection', expected_recommendation: '', priority: 2,
    coverage_status: 'gap', source: 'manual', industry_id: store.currentIndustryId,
  }
}
function openCreate() { editing.value = false; form.value = blank(); dialog.value = true }
function openEdit(q) { editing.value = false; form.value = { ...q, industry_id: store.currentIndustryId }; dialog.value = true }
async function save() {
  if (!form.value.question?.trim()) { ElMessage.warning('请输入问题'); return }
  saving.value = true
  try {
    if (editing.value) await intentQuestionApi.update(form.value.id, form.value)
    else await intentQuestionApi.create(form.value)
    ElMessage.success('保存成功')
    dialog.value = false
    await load()
  } finally { saving.value = false }
}
async function remove(q) {
  await ElMessageBox.confirm(`确定删除该意图问题吗？`, '提示', { type: 'warning' })
  await intentQuestionApi.delete(q.id)
  ElMessage.success('删除成功')
  await load()
}
async function toggleCoverage(q) {
  const next = q.coverage_status === 'covered' ? 'gap' : 'covered'
  q.coverage_status = next
  try { await intentQuestionApi.update(q.id, { ...q, coverage_status: next }) }
  catch (e) { ElMessage.error('更新失败'); await load() }
}

// ===== 批量 =====
function toggleSelect(item) { const i = qSelection.value.indexOf(item.id); if (i >= 0) qSelection.value.splice(i, 1); else qSelection.value.push(item.id) }
function toggleSelectAll(val) { qSelection.value = val ? displayQuestions.value.map(q => q.id) : [] }
function clearSelection() { qSelection.value = [] }
async function onBatchDelete() {
  const ids = qSelection.value
  if (!ids.length) return
  await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 个意图问题吗？`, '批量删除', { type: 'warning' })
  batchSubmitting.value = true
  try {
    await intentQuestionApi.batchDelete({ ids })
    ElMessage.success(`已删除 ${ids.length} 个意图问题`)
    clearSelection(); await load()
  } finally { batchSubmitting.value = false }
}

// ===== 预置默认 =====
async function seedDefaults() {
  if (!store.currentIndustryId) return
  await ElMessageBox.confirm(`将为当前行业「${store.currentIndustryName}」预置该行业对应的默认意图问题（已存在则刷新为该行业默认内容，不丢自建数据）。`, '预置默认问题', { type: 'info' })
  seeding.value = true
  try {
    await targetPersonaApi.seedDefaults(store.currentIndustryId)
    await intentQuestionApi.seedDefaults(store.currentIndustryId)
    ElMessage.success('已预置默认画像与意图问题')
    await load()
  } catch (e) { ElMessage.error('预置失败：' + (e?.response?.data?.detail || '')) }
  finally { seeding.value = false }
}

// ===== 批量导入 =====
const importDialog = ref(false)
const importText = ref('')
const importing = ref(false)
const TEMPLATE = [
  { question: '真空泵怎么选型？', persona_name: '真空工艺工程师', intent_category: 'selection', expected_recommendation: '给出选型 5 问并带出我方优势', priority: 3, coverage_status: 'gap', source: 'manual' },
  { question: '一套真空系统报价大概多少？', persona_name: '真空设备采购', intent_category: 'cost', expected_recommendation: '给出透明报价结构便于比价', priority: 3, coverage_status: 'gap', source: 'manual' },
]
function downloadTemplate() {
  const blob = new Blob([JSON.stringify(TEMPLATE, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = '意图问题导入模板.json'; a.click(); URL.revokeObjectURL(a.href)
}
async function importBatch() {
  if (!importText.value.trim()) { ElMessage.warning('请粘贴 JSON 数据'); return }
  let data
  try { data = JSON.parse(importText.value) } catch (e) { ElMessage.error('JSON 解析失败：' + e.message); return }
  if (!Array.isArray(data)) { ElMessage.error('格式应为 JSON 数组'); return }
  importing.value = true
  try {
    const res = await intentQuestionApi.importBatch(store.currentIndustryId, data)
    ElMessage.success(res.msg || '导入完成')
    importDialog.value = false; importText.value = ''
    await load()
  } catch (e) { ElMessage.error('导入失败：' + (e?.response?.data?.detail || '')) }
  finally { importing.value = false }
}

// ===== 辅助提示词 =====
const promptDialog = ref(false)
const promptText = ref('')
const promptLoading = ref(false)
const promptMeta = ref(null)
async function openAssistantPrompt() {
  if (!store.currentIndustryId) { ElMessage.warning('请先选择行业'); return }
  promptLoading.value = true
  try {
    const res = await intentQuestionApi.assistantPrompt(store.currentIndustryId)
    promptText.value = res.data.prompt
    promptMeta.value = {
      persona_count: res.data.persona_count,
      existing_question_count: res.data.existing_question_count,
      brand_count: res.data.brand_count,
    }
    promptDialog.value = true
  } catch (e) { ElMessage.error('生成提示词失败：' + (e?.response?.data?.detail || '')) }
  finally { promptLoading.value = false }
}
async function copyPrompt() {
  try {
    await navigator.clipboard.writeText(promptText.value)
    ElMessage.success('提示词已复制到剪贴板，可以粘贴到 AI 平台了')
  } catch { ElMessage.error('复制失败，请手动全选复制') }
}

async function load() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const [p, q] = await Promise.all([
      targetPersonaApi.list(store.currentIndustryId),
      intentQuestionApi.list(store.currentIndustryId),
    ])
    personas.value = p.data || []
    questions.value = q.data || []
  } finally { loading.value = false }
}

watch(() => store.currentIndustryId, load)
// 从客户画像页跳转过来时，按画像预选分组
watch(() => route.query.persona, (v) => {
  if (v != null) { const id = Number(v); activePersona.value = (id > 0 || id === -1) ? id : null }
}, { immediate: true })
watch(() => route.query.focus, (f) => {
  if (f) { activePersona.value = null; filterCategory.value = ''; filterCoverage.value = ''; qSearch.value = ''; batchMode.value = false }
}, { immediate: true })
useFocusScroll()
onMounted(load)
</script>

<style scoped>
.iq-view { display: flex; flex-direction: column; gap: 16px; }

/* ===== hero ===== */
.hero {
  display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
  background: linear-gradient(135deg, rgba(99,102,241,0.10), rgba(20,184,166,0.07));
  border: 1px solid var(--border-light); border-left: 4px solid #14b8a6;
  border-radius: var(--radius-lg); padding: 18px 22px;
}
.hero__lead { flex: 1; min-width: 320px; display: flex; flex-direction: column; gap: 6px; }
.hero__eyebrow { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; color: #14b8a6; letter-spacing: 0.03em; }
.hero__eyebrow .el-icon { font-size: 15px; }
.hero__tags { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hero__industry { display: inline-flex; align-items: center; gap: 4px; color: var(--text-secondary); border-color: var(--border-light); font-weight: 500; }
.hero__industry .el-icon { font-size: 13px; }
.hero__title { margin: 0; font-size: 17px; font-weight: 700; color: var(--text-primary); line-height: 1.4; }
.hero__desc { margin: 0; font-size: 12.5px; color: var(--text-tertiary); line-height: 1.6; max-width: 720px; }
.hero__metrics { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.metric { min-width: 76px; text-align: center; padding: 8px 12px; background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-md); }
.metric__num { font-size: 20px; font-weight: 700; color: var(--text-primary); line-height: 1.1; }
.metric__label { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
.metric--ok .metric__num { color: var(--accent-emerald, #10b981); }
.metric--gap .metric__num { color: #f59e0b; }
.metric--cover { min-width: auto; }
.cover { display: flex; flex-direction: column; gap: 5px; }
.cover__track { width: 140px; height: 8px; border-radius: 6px; background: var(--slate-100, #e2e8f0); overflow: hidden; }
.cover__fill { height: 100%; border-radius: 6px; background: linear-gradient(90deg, #10b981, #14b8a6); transition: width 0.45s ease; }
.cover__pct { font-size: 11px; font-weight: 600; color: var(--accent-emerald, #10b981); white-space: nowrap; }

/* ===== body ===== */
.iq-body { display: grid; grid-template-columns: 268px 1fr; gap: 16px; min-height: 540px; align-items: stretch; }
.iq-side, .iq-main {
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-sm);
  display: flex; flex-direction: column; overflow: hidden;
}
.iq-side__head { padding: 14px 16px; border-bottom: 1px solid var(--border-light); }
.iq-side__title { display: flex; align-items: center; gap: 7px; font-size: 14px; font-weight: 600; color: var(--text-primary); }
.iq-side__title .el-icon { color: #6366f1; font-size: 17px; }
.iq-side__list { flex: 1; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 8px; }
.gitem {
  position: relative; display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 10px 12px; border: 1px solid transparent; border-radius: var(--radius-md);
  background: var(--slate-50, #f8fafc); cursor: pointer; text-align: left;
  transition: background 0.16s, border-color 0.16s, transform 0.12s; font: inherit; color: inherit;
}
.gitem:hover { background: #eef2ff; border-color: #c7d2fe; transform: translateX(2px); }
.gitem.active { background: var(--brand-50, #eef2ff); border-color: var(--brand-500, #6366f1); }
.gitem.active::before { content: ''; position: absolute; left: 0; top: 18%; height: 64%; width: 3px; background: var(--brand-500, #6366f1); border-radius: 0 3px 3px 0; }
.gitem__icon { font-size: 17px; flex-shrink: 0; }
.gitem__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.gitem__name { font-weight: 600; font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gitem__sub { font-size: 11px; color: var(--text-tertiary); }
.gitem__count { flex-shrink: 0; font-size: 12px; font-weight: 600; color: var(--text-tertiary); background: var(--bg-card); border: 1px solid var(--border-light); border-radius: 999px; padding: 1px 9px; min-width: 28px; text-align: center; }

.iq-main__head { padding: 14px 16px; border-bottom: 1px solid var(--border-light); display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.iq-main__title { display: flex; align-items: center; gap: 7px; font-size: 14px; font-weight: 600; color: var(--text-primary); }
.iq-main__title .el-icon { color: #14b8a6; font-size: 17px; }
.iq-main__tools { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.iq-toolbar { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid var(--border-light); }

/* 问题表 */
.qtable { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.qtable__body { flex: 1; min-height: 0; }
.qtable__head {
  height: 44px; flex-shrink: 0; display: grid; align-items: center;
  background: var(--bg-secondary, #f8fafc); border-bottom: 1px solid var(--border-light);
  font-size: 12.5px; font-weight: 600; color: var(--text-secondary);
  grid-template-columns: minmax(220px, 1.7fr) 88px minmax(220px, 1.7fr) 96px 84px 150px;
}
.qtable.batch .qtable__head { grid-template-columns: 44px minmax(220px, 1.7fr) 88px minmax(220px, 1.7fr) 96px 84px 150px; }
.qc { padding: 0 14px; font-size: 13px; color: var(--text-secondary); overflow: hidden; min-width: 0; display: flex; align-items: center; }
.qc--sel { justify-content: center; padding: 0; }
.qc--act { display: flex; gap: 4px; justify-content: flex-start; overflow: visible; }
.qrow {
  height: 100%; display: grid; align-items: stretch; box-sizing: border-box;
  border-bottom: 1px solid var(--border-light);
  grid-template-columns: minmax(220px, 1.7fr) 88px minmax(220px, 1.7fr) 96px 84px 150px;
  transition: background 0.14s;
}
.qtable.batch .qrow { grid-template-columns: 44px minmax(220px, 1.7fr) 88px minmax(220px, 1.7fr) 96px 84px 150px; }
.qrow.striped { background: rgba(148, 163, 184, 0.06); }
.qrow:hover { background: rgba(20, 184, 166, 0.06); }
.qrow__q { font-weight: 600; color: var(--text-primary); line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.qrow__tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
.tag { font-size: 11px; padding: 1px 8px; border-radius: 10px; white-space: nowrap; }
.tag--persona { background: rgba(99,102,241,0.12); color: var(--brand-600, #6366f1); }
.tag--src { background: var(--slate-100, #e2e8f0); color: var(--text-tertiary); }
.qc--q { flex-direction: column; align-items: flex-start; justify-content: center; gap: 2px; padding-top: 12px; padding-bottom: 12px; }
.qc--expect { line-height: 1.5; color: var(--text-secondary); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.qc--pri :deep(.el-rate) { height: 16px; }
.qc--pri :deep(.el-rate__item) { font-size: 14px; }
.cov { cursor: pointer; }
.qc--act .el-button { padding: 4px 8px; }

.iq-batchbar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 16px; margin-top: 10px;
  background: var(--brand-50, #eef2ff); border: 1px solid var(--brand-200, #c7d2fe); border-radius: var(--radius-md);
}
.iq-batchbar__count { font-size: 13px; color: var(--text-secondary); }
.iq-batchbar__count b { color: var(--brand-600, #6366f1); }

.cat-list-enter-active, .cat-list-leave-active { transition: all 0.25s ease; }
.cat-list-enter-from { opacity: 0; transform: translateX(-12px); }
.cat-list-leave-to { opacity: 0; transform: translateX(12px); }
.cat-list-move { transition: transform 0.25s ease; }
.cat-list-leave-active { position: absolute; width: calc(100% - 20px); }

@media (max-width: 1024px) {
  .iq-body { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .hero { flex-direction: column; align-items: flex-start; }
  .hero__metrics { width: 100%; }
}

/* 辅助提示词弹窗 */
.assist-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.assist-meta .el-tag { display: inline-flex; align-items: center; gap: 4px; }
.assist-prompt-box {
  max-height: 420px; overflow-y: auto;
  background: var(--bg-secondary, #f8fafc);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 16px;
}
.assist-prompt {
  margin: 0; white-space: pre-wrap; word-break: break-word;
  font-size: 13px; line-height: 1.75; color: var(--text-primary);
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}
.assist-dialog :deep(.el-dialog__body) { padding-top: 8px; }
</style>
