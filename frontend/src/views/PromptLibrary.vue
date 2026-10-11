<template>
  <div class="prompt-library-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-dropdown @command="handleExport" trigger="click">
        <el-button :icon="Download">导出</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="all">导出全部</el-dropdown-item>
            <el-dropdown-item :command="activeCategory">导出当前分类</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button :icon="Upload" @click="importDialog = true">批量导入</el-button>
      <el-button :icon="MagicStick" @click="seedDefaults" :loading="seeding">一键灌入默认模板</el-button>
      <el-button :icon="Cpu" @click="aiDialog = true">AI 写提示词</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建提示词</el-button>
    </Teleport>

    <!-- 顶部：GEO 提示词价值说明 + 指标 -->
    <section class="hero">
      <div class="hero__lead">
        <span class="hero__eyebrow"><el-icon><Files /></el-icon> GEO 作战 · AI 提示词库</span>
        <h2 class="hero__title">把「写软文的能力」沉淀成可复用、可批量导入的标准模板</h2>
        <p class="hero__desc">提示词库是 GEO 生产的引擎：每个分类对应一类产出（大纲 / 初稿 / 洗稿 / 配图 / 安全·GEO）。支持 JSON 批量导入提示词、变量白名单校验与一键灌入默认模板。</p>
      </div>
      <div class="hero__metrics">
        <div class="metric">
          <div class="metric__num">{{ list.length }}</div>
          <div class="metric__label">模板总数</div>
        </div>
        <div class="metric metric--cat">
          <div class="metric__num">{{ categories.length }}</div>
          <div class="metric__label">分类</div>
        </div>
        <div class="metric metric--ok">
          <div class="metric__num">{{ defaultCount }}</div>
          <div class="metric__label">默认模板</div>
        </div>
      </div>
    </section>

    <!-- 分类卡片（按分类数量自适应排布） -->
    <div class="category-grid">
      <div
        v-for="cat in categories"
        :key="cat.key"
        class="category-card"
        :class="{ 'is-active': activeCategory === cat.key }"
        :style="{ '--cat-color': cat.color }"
        @click="activeCategory = cat.key"
      >
        <div class="cat-accent-bar" :style="{ background: cat.color }"></div>
        <div class="cat-card-body">
          <div class="cat-top-row">
            <el-icon :style="{ color: cat.color }"><component :is="iconMap[cat.icon] || Document" /></el-icon>
            <span class="cat-name">{{ cat.name }}</span>
          </div>
          <div class="cat-desc">{{ cat.desc }}</div>
          <div class="cat-count">{{ getCount(cat.key) }} 个模板</div>
        </div>
      </div>
    </div>

    <!-- 批量导入提示词板块 -->
    <div class="batch-import-banner">
      <div class="bib-icon"><el-icon><Upload /></el-icon></div>
      <div class="bib-body">
        <div class="bib-title">批量导入提示词</div>
        <div class="bib-desc">支持 JSON 数组或上传 .json 文件，一次导入多条大纲 / 初稿 / 洗稿 / 安全 / 配图 / GEO 提示词（含 AI 提示词）；不确定格式可先下载模板。</div>
      </div>
      <div class="bib-actions">
        <el-button text @click="downloadPromptTemplate">下载模板</el-button>
        <el-button type="primary" :icon="Upload" @click="importDialog = true">批量导入</el-button>
      </div>
    </div>

    <!-- 提示词列表（原生网格，自适应列数，卡片自然高度不裁切） -->
    <div class="prompt-list" v-loading="loading">
      <PromptCard
        v-for="item in filteredList"
        :key="item.id"
        :item="item"
        :color="catColor(item.category)"
        :icon="catIcon(item.category)"
        :variables="parseVars(item.variables)"
        @view="openView"
        @copy="copyContent"
        @duplicate="duplicate"
        @edit="openEdit"
        @remove="remove"
      />
    </div>
    <EmptyState v-if="!loading && filteredList.length === 0" title="暂无提示词" description="点击右上角「一键灌入默认模板」快速初始化" icon="Files" />

    <PromptEditorDialog
      v-model="dialogVisible"
      :editing="editing"
      :form="form"
      :categories="categories"
      :builtin-vars="builtinVars"
      :detected-vars="detectedVars"
      :unresolved-vars="unresolvedVars"
      :saving="saving"
      :initial-custom-vars="initialCustomVars"
      @submit="save"
      @copy-meta-prompt="copyMetaPrompt"
    />

    <PromptAiDialog
      v-model="aiDialog"
      :categories="categories"
      :form="aiForm"
      :result="aiResult"
      :loading="aiLoading"
      @generate="generateAiPrompt"
      @copy="copyAiResult"
      @save="saveAiAsPrompt"
    />

    <PromptImportDialog
      ref="importDialogRef"
      v-model="importDialog"
      :importing="importing"
      @submit="doImport"
      @download-template="downloadPromptTemplate"
    />

    <PromptViewDrawer
      v-model="viewVisible"
      :item="viewItem"
      :color="viewItem ? catColor(viewItem.category) : '#94a3b8'"
      :category-name="viewItem ? catName(viewItem.category) : ''"
      :variables="viewItem ? parseVars(viewItem.variables) : []"
      @copy="onDrawerCopy"
      @edit="onDrawerEdit"
    />
  </div>
</template>

<script setup>
/**
 * 提示词库 —— 视图层（壳）。
 *
 * 本文件只做三件事：
 *   1. **数据编排**：分类 / 列表 / 内置变量的加载，以及增删改查、导入导出的接口调用
 *   2. **状态持有**：`form`（编辑器表单）、`aiForm` / `aiResult`、`importDialog` 等跨组件共享的状态
 *   3. **分发**：把上面两者交给 5 个子组件（卡片 / 编辑器 / AI 弹窗 / 导入弹窗 / 查看抽屉）
 *
 * 展示逻辑一律在子组件里；变量面板与变量检测在 `PromptEditorDialog` +
 * `composables/useVariableDetection`；静态长文本（元提示词 / 模板片段 / 导入样例）
 * 在 `constants/prompts.js`。共用样式在 `prompt-library/prompt-library-shared.css`。
 *
 * ⚠️ 三个状态**刻意留在壳里**，不搬进子组件：
 *   - `form`                编辑器要就地改它（v-model），保存时又要读它调接口 —— 两侧都要，所以归壳
 *   - `aiForm` / `aiResult`  「保存为提示词」要读它们去填编辑器，同理
 *   - `initialCustomVars`   由壳在打开弹窗时写入，编辑器只读
 */
import { ref, computed, onMounted, watch, markRaw, inject } from 'vue'
import { useRoute } from 'vue-router'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFocusScroll } from '../composables/useFocusScroll'
import { useVariableDetection } from '../composables/useVariableDetection'
import {
  Plus, MagicStick, List, EditPen, Lock, Files,
  Download, Upload, Document, Cpu,
} from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { promptLibraryApi } from '../api'
import { writeClipboard } from '../utils/clipboard'
import { parseJsonArray } from '../utils/json'
import { downloadBlob, downloadJson } from '../utils/download'
import { META_PROMPT, PROMPT_IMPORT_SAMPLE } from '../constants/prompts'
import EmptyState from '../components/EmptyState.vue'
import PromptCard from './prompt-library/PromptCard.vue'
import PromptEditorDialog from './prompt-library/PromptEditorDialog.vue'
import PromptAiDialog from './prompt-library/PromptAiDialog.vue'
import PromptImportDialog from './prompt-library/PromptImportDialog.vue'
import PromptViewDrawer from './prompt-library/PromptViewDrawer.vue'

/** 分类卡片的图标：后端存的是字符串名，这里映射成组件。 */
const iconMap = {
  List: markRaw(List),
  EditPen: markRaw(EditPen),
  MagicStick: markRaw(MagicStick),
  Lock: markRaw(Lock),
}

const store = useAppStore()
const route = useRoute()
const loading = ref(false)
const saving = ref(false)
const seeding = ref(false)
const categories = ref([])
const list = ref([])
const activeCategory = ref('outline')
const dialogVisible = ref(false)
const editing = ref(false)
const form = ref({ name: '', category: 'outline', content: '', description: '', is_default: 0, tags: '', variable_schema: [] })
/** 打开编辑器时要载入的自定义变量（来自被编辑项的 variable_schema） */
const initialCustomVars = ref([])

const filteredList = computed(() => list.value.filter((i) => i.category === activeCategory.value))
const defaultCount = computed(() => list.value.filter((i) => i.is_default).length)

function getCount(key) { return list.value.filter((i) => i.category === key).length }

function catColor(key) {
  const c = categories.value.find((c) => c.key === key)
  return c ? c.color : '#94a3b8'
}

function catIcon(key) {
  const c = categories.value.find((c) => c.key === key)
  return c ? iconMap[c.icon] : null
}

function catName(key) {
  const c = categories.value.find((c) => c.key === key)
  return c ? c.name : key
}

function catLabel(key) {
  const c = categories.value.find((x) => x.key === key)
  return c ? c.name : key
}

/**
 * `variables` / `variable_schema` 都是 JSON 文本列，统一走安全解析。
 * 用 `parseJsonArray` 而不是裸 `JSON.parse`：脏数据解析出非数组时返回 `[]`，
 * 避免下游 `.slice()` / `.map()` 在渲染期抛 TypeError 把整页炸成白屏。
 */
const parseVars = parseJsonArray

// ===== 只读查看抽屉 =====
const viewVisible = ref(false)
const viewItem = ref(null)

function openView(item) {
  viewItem.value = item
  viewVisible.value = true
}

/** 抽屉里「复制全文」：复制成功顺手关掉抽屉，省一次点击。 */
async function onDrawerCopy(item) {
  if (await copyContent(item)) viewVisible.value = false
}

/** 抽屉里「编辑」：先关抽屉再开编辑器，避免两层浮层叠在一起。 */
function onDrawerEdit(item) {
  viewVisible.value = false
  openEdit(item)
}

async function loadCategories() {
  const res = await promptLibraryApi.categories()
  categories.value = res.data || []
}

async function loadList() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const res = await promptLibraryApi.list(store.currentIndustryId)
    list.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function seedDefaults() {
  seeding.value = true
  try {
    const res = await promptLibraryApi.seedDefaults(store.currentIndustryId)
    ElMessage.success(res.msg)
    await loadList()
  } finally {
    seeding.value = false
  }
}

function openCreate() {
  editing.value = false
  form.value = {
    name: '', category: activeCategory.value, content: '', description: '',
    is_default: 0, tags: '', variable_schema: [], industry_id: store.currentIndustryId,
  }
  // ⚠️ `initialCustomVars` 必须在 `dialogVisible = true` **之前**写：
  // 编辑器监听的是 modelValue 的 false→true，打开那一刻读到的就得是新值。
  initialCustomVars.value = []
  dialogVisible.value = true
}

function openEdit(item) {
  editing.value = true
  form.value = { ...item, variable_schema: parseVars(item.variable_schema) }
  initialCustomVars.value = parseVars(item.variable_schema).map((v) => ({ name: v.name || v, desc: v.desc || '' }))
  dialogVisible.value = true
}

/**
 * 保存。`payload` 由编辑器抛出，它已经把组件内部的自定义变量转成了 `variable_schema`。
 *
 * 保存前拦一道「白名单外变量」：这类变量在渲染时会被**原样保留**成 `{xxx}` 喂给 AI，
 * 不报错，但会污染输入、拉低产出质量，且极难排查 —— 所以要显式确认。
 */
async function save(payload) {
  form.value = { ...form.value, ...(payload || {}) }
  if (!form.value.name?.trim()) { ElMessage.warning('请输入名称'); return }
  if (unresolvedVars.value.length) {
    try {
      await ElMessageBox.confirm(
        `检测到 ${unresolvedVars.value.length} 个变量不在系统白名单内（${unresolvedVars.value.map((k) => '{' + k + '}').join(' ')}）。\n渲染时会原样保留为 {变量名}，AI 可能收到错误文本。确定仍要保存吗？`,
        '变量未解析警告', { type: 'warning', confirmButtonText: '仍要保存', cancelButtonText: '去修改' },
      )
    } catch {
      return
    }
  }
  saving.value = true
  try {
    if (editing.value) {
      await promptLibraryApi.update(form.value.id, form.value)
    } else {
      await promptLibraryApi.create(form.value)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await loadList()
  } finally {
    saving.value = false
  }
}

async function remove(item) {
  await ElMessageBox.confirm(`确定删除提示词「${item.name}」吗？`, '提示', { type: 'warning' })
  await promptLibraryApi.delete(item.id)
  ElMessage.success('删除成功')
  await loadList()
}

async function duplicate(item) {
  try {
    await promptLibraryApi.duplicate(item.id)
    ElMessage.success('克隆成功')
    await loadList()
  } catch {
    ElMessage.error('克隆失败')
  }
}

/** 复制全文并累加使用次数。返回是否成功 —— 抽屉据此决定要不要关掉自己。 */
async function copyContent(item) {
  if (!(await writeClipboard(item.content || ''))) { ElMessage.error('复制失败'); return false }
  try {
    await promptLibraryApi.incrementUsage(item.id)
    ElMessage.success('已复制到剪贴板')
    await loadList()
    return true
  } catch {
    ElMessage.error('复制失败')
    return false
  }
}

async function copyMetaPrompt() {
  if (await writeClipboard(META_PROMPT)) ElMessage.success('元提示词已复制，可直接发给其它 AI')
  else ElMessage.error('复制失败')
}

// ========== AI 写提示词（变量白名单约束） ==========
const aiDialog = ref(false)
const aiLoading = ref(false)
const aiResult = ref(null)
const aiForm = ref({ category: 'outline', name: '', requirement: '' })

async function generateAiPrompt() {
  aiLoading.value = true
  aiResult.value = null
  try {
    const res = await promptLibraryApi.generate({
      industry_id: store.currentIndustryId,
      category: aiForm.value.category,
      requirement: aiForm.value.requirement,
      name: aiForm.value.name,
    })
    const d = res.data || {}
    if (d.need_config) {
      ElMessage.warning(d.error || '未配置 LLM（如 DeepSeek），请先到「LLM 配置」填写 Key')
      return
    }
    aiResult.value = d
    if (d.non_builtin && d.non_builtin.length) {
      ElMessage.warning('生成内容含白名单外变量，保存前建议修正')
    } else {
      ElMessage.success('已生成，可保存为提示词')
    }
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    aiLoading.value = false
  }
}

async function copyAiResult() {
  if (!aiResult.value?.content) return
  if (await writeClipboard(aiResult.value.content)) ElMessage.success('已复制')
  else ElMessage.error('复制失败')
}

function saveAiAsPrompt() {
  if (!aiResult.value?.content) return
  openCreate()
  form.value = {
    ...form.value,
    name: aiForm.value.name ? aiForm.value.name : 'AI生成·' + catLabel(aiForm.value.category),
    category: aiForm.value.category,
    content: aiResult.value.content,
    description: aiForm.value.requirement || '由 AI 按白名单变量生成',
    is_default: 0,
    tags: 'AI生成',
    variable_schema: [],
    industry_id: store.currentIndustryId,
  }
  aiDialog.value = false
}

// ===== 变量面板 / 变量检测 =====
const builtinVars = ref([])

async function loadBuiltinVars() {
  try {
    const res = await promptLibraryApi.builtinVariables()
    // 后端返回 { variables:[...], groups:{...} }，这里取 variables 数组；
    // 兼容历史接口直出数组的情况，避免 builtinVars 变成对象导致 .forEach 崩溃
    const payload = res && res.data
    builtinVars.value = (payload && payload.variables) || payload || []
  } catch {
    // fallback：拿不到白名单时至少给几个最常用的，别让面板空着
    builtinVars.value = [
      { key: 'industry_name', desc: '行业名称', group: '行业与平台' },
      { key: 'platform_name', desc: '平台名称', group: '行业与平台' },
      { key: 'brand_name', desc: '品牌名称', group: '品牌信息' },
      { key: 'keywords', desc: '关键词（顿号分隔）', group: '关键词' },
      { key: 'knowledge_content', desc: '知识库内容', group: '知识库' },
      { key: 'persona_name', desc: '人设名称', group: '人设' },
    ]
  }
}

// 变量检测交给 composable：内含真防抖 + 请求序号防乱序。
// （原实现的 `watch(..., { debounce: 500 })` 是无效选项，实际每敲一个字符打一次接口。）
const { detectedVars, unresolvedVars } = useVariableDetection(() => form.value.content)

// ===== 导入导出 =====
const importDialog = ref(false)
const importDialogRef = ref(null)
const importing = ref(false)

async function handleExport(cmd) {
  try {
    const cat = cmd === 'all' ? '' : cmd
    const res = await promptLibraryApi.exportPrompts(store.currentIndustryId, cat)
    downloadBlob(new Blob([res], { type: 'application/json' }), `prompts_${cat || 'all'}.json`)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

/**
 * 导入。`payload` 是导入弹窗里拿到的 JSON 文本（粘贴或读文件），
 * 解析与调接口刻意留在视图 —— 见 `PromptImportDialog` 的注释。
 */
async function doImport(payload) {
  const text = String(payload || '').trim()
  if (!text) { ElMessage.warning('请输入JSON数据'); return }
  let data
  try {
    data = JSON.parse(text)
  } catch {
    // 原来这里和后端校验失败共用一个 catch，一律报「JSON格式错误」——
    // 后端校验失败时那句话是误导，所以拆开。
    ElMessage.error('导入失败：JSON 格式错误，请检查后重试')
    return
  }
  importing.value = true
  try {
    const res = await promptLibraryApi.importPrompts({
      industry_id: store.currentIndustryId,
      data,
    })
    // ⚠️ 后端 `POST /import` 的文案在**顶层** `msg`，不是 `data.msg`（`data` 里只有 created/errors）。
    // 写错不会报错，只会弹一个没有文字的绿色 toast —— 用户看到「导入成功了个寂寞」。
    // 同一模块里 `seedDefaults` 用的就是 `res.msg`，两处必须一致。
    ElMessage.success(res.msg || `成功导入 ${res.data?.created ?? 0} 条提示词`)
    importDialog.value = false
    importDialogRef.value?.reset()
    await loadList()
  } finally {
    importing.value = false
  }
}

function downloadPromptTemplate() {
  downloadJson(PROMPT_IMPORT_SAMPLE, 'prompt_import_template.json')
}

watch(() => store.currentIndustryId, loadList)
// 全局搜索跳转：自动切到结果所在的提示词分类
watch(() => route.query.cat, (c) => { if (c) activeCategory.value = c }, { immediate: true })
useFocusScroll()
onMounted(async () => {
  await loadCategories()
  await loadList()
  await loadBuiltinVars()
})
</script>

<style scoped>
.prompt-library-view { display: flex; flex-direction: column; gap: 16px; }
.hero {
  display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
  background: linear-gradient(135deg, rgba(99,102,241,0.10), rgba(20,184,166,0.07));
  border: 1px solid var(--border-light); border-left: 4px solid #6366f1;
  border-radius: var(--radius-lg); padding: 18px 22px;
}
.hero__lead { flex: 1; min-width: 320px; display: flex; flex-direction: column; gap: 6px; }
.hero__eyebrow { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; color: #6366f1; letter-spacing: 0.03em; }
.hero__eyebrow .el-icon { font-size: 15px; }
.hero__title { margin: 0; font-size: 17px; font-weight: 700; color: var(--text-primary); line-height: 1.4; }
.hero__desc { margin: 0; font-size: 12.5px; color: var(--text-tertiary); line-height: 1.6; max-width: 720px; }
.hero__metrics { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.metric { min-width: 76px; text-align: center; padding: 8px 12px; background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-md); }
.metric__num { font-size: 20px; font-weight: 700; color: var(--text-primary); line-height: 1.1; }
.metric__label { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
.metric--cat .metric__num { color: var(--brand-600, #6366f1); }
.metric--ok .metric__num { color: var(--accent-emerald, #10b981); }
@media (max-width: 768px) {
    .hero { flex-direction: column; align-items: flex-start; }
    .hero__metrics { width: 100%; }
}
.category-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.category-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  position: relative;
}
.category-card:hover { border-color: var(--cat-color); box-shadow: var(--shadow-md); }
.category-card.is-active { border-color: var(--cat-color); box-shadow: 0 0 0 3px color-mix(in srgb, var(--cat-color) 10%, transparent); }
.cat-accent-bar { height: 3px; }
.cat-card-body { padding: 16px; }
.cat-top-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cat-top-row .el-icon { font-size: 18px; }
.cat-name { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.cat-desc { font-size: 12px; color: var(--text-tertiary); line-height: 1.5; min-height: 36px; margin-bottom: 8px; }
.cat-count { font-size: 11px; color: var(--cat-color); font-weight: 600; }
.prompt-list {
  padding: 2px 4px 4px 0;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; align-content: start;
}
@media (max-width: 1024px) {
    .category-grid { grid-template-columns: repeat(2, 1fr); }
    .prompt-list { grid-template-columns: 1fr; }
}
.batch-import-banner {
  display: flex; align-items: center; gap: 14px;
  background: var(--bg-card);
  border: 1px dashed var(--brand-300, #a5b4fc);
  border-radius: var(--radius-lg);
  padding: 14px 18px;
  box-shadow: var(--shadow-sm);
}
.bib-icon {
  width: 42px; height: 42px; border-radius: 10px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff; font-size: 20px;
}
.bib-body { flex: 1; min-width: 0; }
.bib-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.bib-desc { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; line-height: 1.5; }
.bib-actions { display: flex; gap: 8px; flex-shrink: 0; }
</style>
