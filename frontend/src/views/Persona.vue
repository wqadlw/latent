<template>
  <div class="persona-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button :icon="MagicStick" @click="openAssistantPrompt" :loading="promptLoading">辅助提示词</el-button>
      <el-button :icon="Upload" @click="importDialog = true">批量导入</el-button>
      <el-button :icon="MagicStick" @click="seedDefaults" :loading="seeding">预置默认</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建客户画像</el-button>
    </Teleport>

    <!-- 顶部：GEO 价值说明 + 指标 -->
    <section class="hero">
      <div class="hero__lead">
        <div class="hero__tags">
          <span class="hero__eyebrow"><el-icon><Aim /></el-icon> GEO 作战 · 模块① 地基</span>
          <el-tag size="small" effect="plain" class="hero__industry"><el-icon><OfficeBuilding /></el-icon> 当前行业：{{ store.currentIndustryName }}</el-tag>
        </div>
        <h2 class="hero__title">定义目标客户画像：让 AI 在回答时知道该推荐「谁」</h2>
        <p class="hero__desc">把"谁会向 AI 提问、关心什么、痛点是什么"结构化沉淀下来。画像越清晰，后续意图问题、软文选题与 GEO 评分才能精准命中，AI 在回答时才能把正确的客户指向我们。</p>
      </div>
      <div class="hero__metrics">
        <div class="metric">
          <div class="metric__num">{{ personas.length }}</div>
          <div class="metric__label">客户画像</div>
        </div>
        <div class="metric metric--link">
          <div class="metric__num">{{ totalQuestions }}</div>
          <div class="metric__label">关联意图问题</div>
        </div>
        <div class="metric metric--group">
          <div class="metric__num">{{ roleGroups.length }}</div>
          <div class="metric__label">角色分组</div>
        </div>
      </div>
    </section>

    <!-- 工具栏：分组(角色) / 排序 / 搜索 -->
    <div class="toolbar">
      <div class="toolbar__group">
        <span class="toolbar__label">角色分组</span>
        <el-radio-group v-model="filterRole" size="small">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button v-for="r in ROLE_ORDER" :key="r" :value="r">{{ roleLabel(r) }}</el-radio-button>
        </el-radio-group>
      </div>
      <el-input v-model="kw" placeholder="搜索画像名称 / 描述 / 痛点..." size="small" :prefix-icon="Search" clearable class="toolbar__search" />
      <el-select v-model="sortBy" size="small" class="toolbar__sort" style="width: 150px;">
        <el-option label="默认顺序（可拖拽）" value="default" />
        <el-option label="按名称" value="name" />
        <el-option label="按关联问题数" value="questions" />
        <el-option label="按决策影响力" value="weight" />
      </el-select>
      <el-tooltip :content="sortBy === 'default' ? '拖拽卡片左侧手柄排序' : '当前按字段排序'">
        <el-button size="small" :icon="sortBy === 'default' ? Sort : (sortDir === 'asc' ? SortUp : SortDown)" :disabled="sortBy === 'default'" @click="toggleDir">
          {{ sortBy === 'default' ? '拖拽排序' : (sortDir === 'asc' ? '升序' : '降序') }}
        </el-button>
      </el-tooltip>
    </div>

    <!-- 画像卡片网格 -->
    <div class="cards" v-loading="loading">
      <transition-group name="cat-list" tag="div" class="cards__grid">
        <div
          v-for="p in displayPersonas"
          :key="p.id"
          class="pcard"
          :style="{ '--pc': p.color || '#6366f1' }"
          draggable="true"
          @dragstart="onDragStart(p, $event)"
          @dragover.prevent="onDragOver($event)"
          @drop="onDrop(p)"
        >
          <span class="pcard__drag" title="拖拽排序"><el-icon><Rank /></el-icon></span>
          <div class="pcard__head">
            <span class="pcard__avatar" :style="{ background: 'color-mix(in srgb, var(--pc) 16%, transparent)', color: 'var(--pc)' }">
              <el-icon><component :is="personaIconOf(p)" /></el-icon>
            </span>
            <div class="pcard__title">
              <div class="pcard__name-row">
                <span class="pcard__name">{{ p.name }}</span>
                <el-tag size="small" :type="roleColor(p.role_type)" effect="plain">{{ roleLabel(p.role_type) }}</el-tag>
              </div>
              <div class="pcard__sub">
                <el-rate :model-value="p.decision_weight" disabled size="small" />
                <span class="pcard__qcount">{{ p.question_count }} 个问题</span>
              </div>
            </div>
            <div class="pcard__actions" @click.stop>
              <el-button text size="small" :icon="Edit" title="编辑" @click="openEdit(p)" />
              <el-button text size="small" type="danger" :icon="Delete" title="删除" @click="remove(p)" />
            </div>
          </div>

          <div class="pcard__desc" v-if="p.description">{{ p.description }}</div>

          <div class="pcard__cols" v-if="painPoints(p).length || cares(p).length">
            <div class="pcard__col" v-if="painPoints(p).length">
              <div class="pcard__col-t"><el-icon><WarningFilled /></el-icon> 痛点</div>
              <ul class="pcard__col-b"><li v-for="(x, i) in painPoints(p)" :key="'p' + i">{{ x }}</li></ul>
            </div>
            <div class="pcard__col" v-if="cares(p).length">
              <div class="pcard__col-t"><el-icon><Star /></el-icon> 关注点</div>
              <ul class="pcard__col-b"><li v-for="(x, i) in cares(p)" :key="'c' + i">{{ x }}</li></ul>
            </div>
          </div>

          <div class="pcard__foot">
            <el-button size="small" text :icon="ChatDotRound" @click="gotoQuestions(p)">查看其意图问题</el-button>
          </div>
        </div>
      </transition-group>
      <EmptyState v-if="!loading && displayPersonas.length === 0" title="暂无客户画像" size="small" icon="Aim"
        hint="点右上角「新建客户画像」或「预置默认」一键生成三类典型目标客户。" />
    </div>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialog" :title="editing ? '编辑客户画像' : '新建客户画像'" width="540px">
      <el-form :model="form" label-width="88px">
        <el-form-item label="画像名称"><el-input v-model="form.name" placeholder="如：工厂老板 / 技术负责人 / 采购主管" /></el-form-item>
        <el-form-item label="角色类型">
          <el-select v-model="form.role_type" style="width: 100%;">
            <el-option label="决策层（老板/总经理）" value="decision_maker" />
            <el-option label="技术层（工程师/技术负责人）" value="technical" />
            <el-option label="采购层（采购/商务）" value="procurement" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="决策影响力">
          <el-rate v-model="form.decision_weight" :max="3" />
          <span class="form-hint">在采购决策中的话语权权重（1-3）</span>
        </el-form-item>
        <el-form-item label="图标">
          <el-select v-model="form.icon" placeholder="选择图标" style="width: 100%;">
            <el-option v-for="ic in iconOptions" :key="ic" :label="ic" :value="ic">
              <el-icon style="vertical-align: middle;"><component :is="iconMap[ic]" v-if="iconMap[ic]" /></el-icon>
              <span style="margin-left: 8px;">{{ ic }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="主题色">
          <el-color-picker v-model="form.color" />
          <el-input v-model="form.color" style="width: 110px; margin-left: 10px;" />
        </el-form-item>
        <el-form-item label="画像描述"><el-input v-model="form.description" type="textarea" :rows="2" placeholder="一句话概括这类人是谁" /></el-form-item>
        <el-form-item label="痛点"><el-input v-model="form.pain_points" type="textarea" :rows="2" placeholder="每行一个，如：看不懂技术 / 怕踩坑" /></el-form-item>
        <el-form-item label="关注点"><el-input v-model="form.cares_about" type="textarea" :rows="2" placeholder="每行一个，如：ROI / 交付周期 / 售后" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入弹窗 -->
    <el-dialog v-model="importDialog" title="批量导入客户画像" width="640px">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        <template #title>粘贴 JSON 数组，每行一个画像对象（按名称 upsert，已存在则更新）</template>
        <template #default>字段：name（必填）、role_type、description、pain_points、cares_about、decision_weight、icon、color</template>
      </el-alert>
      <el-input v-model="importText" type="textarea" :rows="11" placeholder='例如：[{"name":"真空产线厂长","role_type":"decision_maker","decision_weight":3,"pain_points":"真空度不稳\n能耗高"}]' />
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
        <el-tag size="small" effect="plain" type="info"><el-icon><User /></el-icon> {{ promptMeta.persona_count }} 个已有画像</el-tag>
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
import { useRouter } from 'vue-router'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Edit, Delete, Aim, Search, Sort, SortUp, SortDown, Rank, Download, Upload, MagicStick, ChatDotRound, WarningFilled, Star,
  User, OfficeBuilding, Cpu, ShoppingCart, Avatar, UserFilled,
} from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { targetPersonaApi } from '../api'
import EmptyState from '../components/EmptyState.vue'

const router = useRouter()
const store = useAppStore()

const loading = ref(false)
const saving = ref(false)
const seeding = ref(false)
const personas = ref([])
const totalQuestions = computed(() => personas.value.reduce((s, p) => s + (p.question_count || 0), 0))
const roleGroups = computed(() => [...new Set(personas.value.map(p => p.role_type))].filter(Boolean))

const filterRole = ref('')
const kw = ref('')
const sortBy = ref('default')
const sortDir = ref('desc')

const ROLE_ORDER = ['decision_maker', 'technical', 'procurement', 'other']
function roleLabel(r) { return { decision_maker: '决策层', technical: '技术层', procurement: '采购层', other: '其他' }[r] || '其他' }
function roleColor(r) { return { decision_maker: 'danger', technical: 'primary', procurement: 'warning', other: 'info' }[r] || 'info' }

const iconMap = { User, OfficeBuilding, Cpu, ShoppingCart, Avatar, UserFilled, Aim }
const iconOptions = ['User', 'OfficeBuilding', 'Cpu', 'ShoppingCart', 'Avatar', 'UserFilled', 'Aim']
function personaIconOf(p) { return iconMap[p?.icon] || User }

function splitLines(s) { return (s || '').split('\n').map(x => x.trim()).filter(Boolean) }
function painPoints(p) { return splitLines(p?.pain_points) }
function cares(p) { return splitLines(p?.cares_about) }

const displayPersonas = computed(() => {
  let arr = personas.value
  if (filterRole.value) arr = arr.filter(p => p.role_type === filterRole.value)
  const k = (kw.value || '').trim().toLowerCase()
  if (k) arr = arr.filter(p =>
    (p.name || '').toLowerCase().includes(k) ||
    (p.description || '').toLowerCase().includes(k) ||
    painPoints(p).join(' ').toLowerCase().includes(k)
  )
  const by = sortBy.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  if (by !== 'default') {
    arr = [...arr].sort((a, b) => {
      if (by === 'name') return (a.name || '').localeCompare(b.name || '', 'zh-CN') * dir
      if (by === 'questions') return ((a.question_count || 0) - (b.question_count || 0)) * dir
      if (by === 'weight') return ((a.decision_weight || 0) - (b.decision_weight || 0)) * dir
      return 0
    })
  }
  return arr
})
function toggleDir() { sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc' }

// ===== 弹窗 =====
const dialog = ref(false)
const editing = ref(false)
const form = ref(blank())
function blank() {
  return { name: '', role_type: 'other', decision_weight: 2, icon: 'User', color: '#6366f1', description: '', pain_points: '', cares_about: '', industry_id: store.currentIndustryId }
}
function openCreate() { editing.value = false; form.value = blank(); dialog.value = true }
function openEdit(p) { editing.value = false; form.value = { ...p, industry_id: store.currentIndustryId }; dialog.value = true }
async function save() {
  if (!form.value.name?.trim()) { ElMessage.warning('请输入画像名称'); return }
  saving.value = true
  try {
    if (editing.value) await targetPersonaApi.update(form.value.id, form.value)
    else await targetPersonaApi.create(form.value)
    ElMessage.success('保存成功')
    dialog.value = false
    await load()
  } finally { saving.value = false }
}
async function remove(p) {
  const tip = p.question_count > 0
    ? `确定删除画像「${p.name}」吗？其下的 ${p.question_count} 个问题将变为「未关联画像」。`
    : `确定删除画像「${p.name}」吗？`
  await ElMessageBox.confirm(tip, '删除画像', { type: 'warning' })
  await targetPersonaApi.delete(p.id)
  ElMessage.success('画像已删除')
  await load()
}

// ===== 拖拽排序 =====
const dragId = ref(null)
function onDragStart(p, e) { dragId.value = p.id; if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move' }
function onDragOver(e) { e.dataTransfer.dropEffect = 'move' }
async function onDrop(target) {
  const from = dragId.value
  dragId.value = null
  if (from == null || from === target.id) return
  const fromIdx = personas.value.findIndex(p => p.id === from)
  const toIdx = personas.value.findIndex(p => p.id === target.id)
  if (fromIdx < 0 || toIdx < 0) return
  const arr = [...personas.value]
  const [moved] = arr.splice(fromIdx, 1)
  arr.splice(toIdx, 0, moved)
  personas.value = arr
  try { await targetPersonaApi.sort(arr.map((p, i) => ({ id: p.id, sort: i }))) }
  catch (e) { ElMessage.error('排序失败'); await load() }
}

// ===== 预置默认 =====
async function seedDefaults() {
  if (!store.currentIndustryId) return
  await ElMessageBox.confirm(`将为当前行业「${store.currentIndustryName}」预置该行业对应的默认目标画像（已存在则刷新为该行业默认内容，不丢自建数据）。`, '预置默认画像', { type: 'info' })
  seeding.value = true
  try {
    await targetPersonaApi.seedDefaults(store.currentIndustryId)
    ElMessage.success('已预置默认画像')
    await load()
  } catch (e) { ElMessage.error('预置失败：' + (e?.response?.data?.detail || '')) }
  finally { seeding.value = false }
}

// ===== 批量导入 =====
const importDialog = ref(false)
const importText = ref('')
const importing = ref(false)
const TEMPLATE = [
  { name: '真空产线厂长', role_type: 'decision_maker', decision_weight: 3, description: '负责真空产线运营投资的决策者', pain_points: '真空度不稳影响良率\n系统能耗高', cares_about: '投资回报与回本周期\n单位能耗' },
  { name: '真空工艺工程师', role_type: 'technical', decision_weight: 2, description: '负责真空工艺与设备选型', pain_points: '真空度达不到工艺要求\n漏率排查耗时', cares_about: '极限真空度与抽速\n漏率检测' },
]
function downloadTemplate() {
  const blob = new Blob([JSON.stringify(TEMPLATE, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = '客户画像导入模板.json'; a.click(); URL.revokeObjectURL(a.href)
}
async function importBatch() {
  if (!importText.value.trim()) { ElMessage.warning('请粘贴 JSON 数据'); return }
  let data
  try { data = JSON.parse(importText.value) } catch (e) { ElMessage.error('JSON 解析失败：' + e.message); return }
  if (!Array.isArray(data)) { ElMessage.error('格式应为 JSON 数组'); return }
  importing.value = true
  try {
    const res = await targetPersonaApi.importBatch(store.currentIndustryId, data)
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
    const res = await targetPersonaApi.assistantPrompt(store.currentIndustryId)
    promptText.value = res.data.prompt
    promptMeta.value = { persona_count: res.data.persona_count, brand_count: res.data.brand_count }
    promptDialog.value = true
  } catch (e) { ElMessage.error('生成提示词失败：' + (e?.response?.data?.detail || '')) }
  finally { promptLoading.value = false }
}
async function copyPrompt() {
  try {
    await navigator.clipboard.writeText(promptText.value)
    ElMessage.success('提示词已复制到剪贴板')
  } catch { ElMessage.error('复制失败，请手动全选复制') }
}

function gotoQuestions(p) {
  router.push({ path: '/intent-question', query: { persona: p.id } })
}

async function load() {
  if (!store.currentIndustryId) return
  loading.value = true
  try { const res = await targetPersonaApi.list(store.currentIndustryId); personas.value = res.data || [] }
  finally { loading.value = false }
}
watch(() => store.currentIndustryId, load)
onMounted(load)
</script>

<style scoped>
.persona-view { display: flex; flex-direction: column; gap: 16px; }

/* ===== hero ===== */
.hero {
  display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
  background: linear-gradient(135deg, rgba(99,102,241,0.10), rgba(20,184,166,0.07));
  border: 1px solid var(--border-light); border-left: 4px solid #6366f1;
  border-radius: var(--radius-lg); padding: 18px 22px;
}
.hero__lead { flex: 1; min-width: 320px; display: flex; flex-direction: column; gap: 6px; }
.hero__eyebrow { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; color: #6366f1; letter-spacing: 0.03em; }
.hero__eyebrow .el-icon { font-size: 15px; }
.hero__tags { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hero__industry { display: inline-flex; align-items: center; gap: 4px; color: var(--text-secondary); border-color: var(--border-light); font-weight: 500; }
.hero__industry .el-icon { font-size: 13px; }
.hero__title { margin: 0; font-size: 17px; font-weight: 700; color: var(--text-primary); line-height: 1.4; }
.hero__desc { margin: 0; font-size: 12.5px; color: var(--text-tertiary); line-height: 1.6; max-width: 720px; }
.hero__metrics { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.metric { min-width: 84px; text-align: center; padding: 8px 14px; background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-md); }
.metric__num { font-size: 20px; font-weight: 700; color: var(--text-primary); line-height: 1.1; }
.metric__label { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
.metric--link .metric__num { color: var(--brand-600, #6366f1); }
.metric--group .metric__num { color: #14b8a6; }

/* ===== toolbar ===== */
.toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.toolbar__group { display: flex; align-items: center; gap: 8px; }
.toolbar__label { font-size: 12px; color: var(--text-tertiary); font-weight: 500; }
.toolbar__search { width: 260px; }
.toolbar__sort { flex-shrink: 0; }

/* ===== cards ===== */
.cards { min-height: 300px; }
.cards__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.pcard {
  position: relative; display: flex; flex-direction: column; gap: 10px;
  background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-lg);
  padding: 16px; box-shadow: var(--shadow-sm); overflow: hidden;
  transition: border-color 0.16s, box-shadow 0.16s, transform 0.12s;
}
.pcard:hover { border-color: var(--pc); box-shadow: var(--shadow-md); transform: translateY(-2px); }
.pcard__drag { position: absolute; top: 12px; left: 10px; font-size: 14px; color: var(--text-tertiary); cursor: grab; opacity: 0; transition: opacity 0.15s; }
.pcard:hover .pcard__drag { opacity: 0.7; }
.pcard__head { display: flex; align-items: flex-start; gap: 12px; padding-left: 16px; }
.pcard__avatar { width: 40px; height: 40px; border-radius: 11px; display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; }
.pcard__title { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.pcard__name-row { display: flex; align-items: center; gap: 6px; }
.pcard__name { font-weight: 700; font-size: 15px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pcard__sub { display: flex; align-items: center; gap: 8px; }
.pcard__sub :deep(.el-rate) { height: 14px; }
.pcard__sub :deep(.el-rate__item) { font-size: 12px; }
.pcard__qcount { font-size: 11px; color: var(--text-tertiary); }
.pcard__actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; opacity: 0; transition: opacity 0.15s; }
.pcard:hover .pcard__actions { opacity: 1; }
.pcard__actions .el-button { padding: 3px 5px; }
.pcard__desc { font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; padding: 0 16px; }
.pcard__cols { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 18px; padding: 0 16px; }
.pcard__col-t { display: flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600; color: var(--text-tertiary); margin-bottom: 5px; letter-spacing: 0.03em; }
.pcard__col-t .el-icon { font-size: 13px; }
.pcard__col-b { margin: 0; padding-left: 16px; display: flex; flex-direction: column; gap: 3px; }
.pcard__col-b li { font-size: 12px; color: var(--text-secondary); line-height: 1.5; }
.pcard__foot { padding: 10px 16px 0; border-top: 1px dashed var(--border-light); margin-top: 2px; }
.pcard__foot .el-button { color: var(--brand-600, #6366f1); }

.form-hint { font-size: 12px; color: var(--text-tertiary); line-height: 1.5; margin-top: 2px; }

.cat-list-enter-active, .cat-list-leave-active { transition: all 0.25s ease; }
.cat-list-enter-from { opacity: 0; transform: translateY(10px); }
.cat-list-leave-to { opacity: 0; transform: scale(0.96); }
.cat-list-move { transition: transform 0.25s ease; }
.cat-list-leave-active { position: absolute; width: calc(33% - 14px); }

@media (max-width: 1024px) {
  .pcard__cols { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .hero { flex-direction: column; align-items: flex-start; }
  .hero__metrics { width: 100%; }
  .toolbar { flex-direction: column; align-items: stretch; }
  .toolbar__search { width: 100%; }
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
