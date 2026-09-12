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
      <div
        v-for="item in filteredList"
        :key="item.id"
        class="prompt-item"
        :data-focus-id="item.id"
        :style="{ '--cat-color': catColor(item.category) }"
      >
        <div class="prompt-item__main">
          <div class="prompt-item__header">
            <span class="prompt-item__avatar" :style="{ background: 'color-mix(in srgb, var(--cat-color) 14%, transparent)', color: 'var(--cat-color)' }">
              <el-icon><component :is="catIcon(item.category) || Document" /></el-icon>
            </span>
            <span class="prompt-item__name">{{ item.name }}</span>
            <div class="prompt-item__badges">
              <el-tag v-if="item.is_default" size="small" type="warning" effect="dark">默认</el-tag>
              <el-rate v-if="item.rating" :model-value="item.rating" disabled size="small" />
              <el-tag v-if="item.usage_count" size="small" type="info" effect="plain">
                <el-icon><TrendCharts /></el-icon> {{ item.usage_count }}
              </el-tag>
            </div>
          </div>
          <div class="prompt-item__desc">{{ item.description || '暂无描述' }}</div>
          <div class="prompt-item__preview">
            <span class="prompt-item__preview-label"><el-icon><Memo /></el-icon> 提示词内容</span>
            <div class="prompt-item__preview-text">{{ (item.content || '').slice(0, 220) }}{{ (item.content || '').length > 220 ? '…' : '' }}</div>
          </div>
          <div class="prompt-item__vars" v-if="item.variables && parseVars(item.variables).length">
            <el-tag v-for="v in parseVars(item.variables).slice(0, 6)" :key="v" size="small" effect="plain" type="info" class="var-tag">{{ '{' + v + '}' }}</el-tag>
            <span v-if="parseVars(item.variables).length > 6" class="var-more">+{{ parseVars(item.variables).length - 6 }}</span>
          </div>
          <div class="prompt-item__meta">
            <span><el-icon><Clock /></el-icon> {{ formatTime(item.update_time) }}</span>
            <span v-if="item.tags"><el-icon><PriceTag /></el-icon> {{ item.tags }}</span>
          </div>
        </div>
        <div class="prompt-item__actions">
          <el-button text size="small" :icon="View" @click="openView(item)">查看</el-button>
          <el-button text size="small" :icon="CopyDocument" @click="copyContent(item)">复制</el-button>
          <el-button text size="small" :icon="DocumentCopy" @click="duplicate(item)">克隆</el-button>
          <el-button text size="small" :icon="Edit" @click="openEdit(item)">编辑</el-button>
          <el-button text size="small" type="danger" :icon="Delete" @click="remove(item)">删除</el-button>
        </div>
      </div>
    </div>
    <EmptyState v-if="!loading && filteredList.length === 0" title="暂无提示词" description="点击右上角「一键灌入默认模板」快速初始化" icon="Files" />

    <!-- 新建/编辑弹窗 - 分栏布局 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑提示词' : '新建提示词'" width="92%" top="3vh" class="prompt-editor-dialog">
      <!-- 元提示词助手：一键复制给其它 AI，让它帮写符合本系统规范的标准提示词 -->
      <div class="meta-prompt-box">
        <div class="meta-prompt-head" @click="metaPromptOpen = !metaPromptOpen">
          <el-icon class="mp-icon"><MagicStick /></el-icon>
          <span class="mp-title">让其它 AI 帮你写标准提示词？点此展开「元提示词」一键复制</span>
          <el-icon class="mp-chevron" :class="{ 'is-open': metaPromptOpen }"><ArrowDown /></el-icon>
        </div>
        <div v-show="metaPromptOpen" class="meta-prompt-body">
          <p class="mp-tip">把下面这段直接发给 ChatGPT / Claude / 通义 / DeepSeek 等任意 AI，它会按本系统规范起草一条标准提示词模板；复制结果填到上方编辑区即可（记得确认变量名在白名单内）。</p>
          <el-input :model-value="META_PROMPT" type="textarea" :rows="18" readonly class="mp-textarea" />
          <div class="mp-foot">
            <el-button type="primary" :icon="CopyDocument" @click="copyMetaPrompt">一键复制元提示词</el-button>
            <span class="mp-hint">复制后粘贴给任意 AI，即可得到符合规范的提示词模板</span>
          </div>
        </div>
      </div>

      <div class="editor-layout">
        <!-- 左栏：变量面板（重设计：分组高亮 + 一键灌入本类默认变量 + 变量中心联动） -->
        <div class="var-panel">
          <div class="var-panel-head">
            <span class="vp-title">变量面板</span>
            <el-button size="small" type="primary" plain :icon="MagicStick" @click="injectCategoryDefaults" title="按当前分类灌入推荐变量集">本类默认变量</el-button>
          </div>
          <div class="var-panel-sub">
            <el-input v-model="varSearch" placeholder="搜索变量..." size="small" :prefix-icon="Search" clearable />
            <span class="vp-count">点击变量插入到光标处</span>
          </div>
          <div class="var-panel-body">
            <div v-for="group in groupedVars" :key="group.name" class="var-group" :class="{ 'var-group--geo': group.isGeo }">
              <div class="var-group-title">
                <span class="var-group-name">
                  <span v-if="group.isGeo" class="geo-dot"></span>{{ group.name }}
                </span>
                <el-button text size="small" @click="insertGroup(group)">全插</el-button>
              </div>
              <div class="var-group-items">
                <div
                  v-for="v in group.items"
                  :key="v.key"
                  class="var-item"
                  :class="{ 'is-used': isVarUsed(v.key) }"
                  @click="insertVariable(v.key)"
                  :title="'点击插入 {' + v.key + '}'"
                >
                  <div class="var-item-key">{{ '{' + v.key + '}' }}</div>
                  <div class="var-item-desc">{{ v.desc }}</div>
                  <el-icon v-if="isVarUsed(v.key)" class="var-item-used"><CircleCheckFilled /></el-icon>
                </div>
              </div>
            </div>
            <!-- 自定义变量 -->
            <div class="var-group">
              <div class="var-group-title">
                自定义变量
                <el-button text size="small" :icon="Plus" @click="addCustomVar">添加</el-button>
              </div>
              <div v-for="(cv, idx) in customVars" :key="idx" class="custom-var-item">
                <el-input v-model="cv.name" size="small" placeholder="变量名" style="width: 120px;" />
                <el-input v-model="cv.desc" size="small" placeholder="描述" style="flex: 1;" />
                <el-button text size="small" type="danger" :icon="Delete" @click="customVars.splice(idx, 1)" />
              </div>
              <div v-if="customVars.length === 0" class="empty-hint">点击「添加」创建自定义变量</div>
            </div>
          </div>
        </div>

        <!-- 中栏：编辑器 -->
        <div class="editor-center">
          <el-form :model="form" label-width="90px" class="prompt-form">
            <el-form-item label="名称" required>
              <el-input v-model="form.name" placeholder="提示词名称" />
            </el-form-item>
            <el-form-item label="分类">
              <el-select v-model="form.category" style="width: 100%;">
                <el-option v-for="c in categories" :key="c.key" :label="c.name" :value="c.key" />
              </el-select>
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="form.description" placeholder="简要描述这个提示词的用途" />
            </el-form-item>
            <el-form-item label="标签">
              <el-input v-model="form.tags" placeholder="多个标签用逗号分隔" />
            </el-form-item>
            <el-form-item label="内容" required>
              <div class="editor-wrapper">
                <div class="editor-toolbar">
                  <span class="toolbar-hint">点击左侧变量插入，或直接输入 {变量名}</span>
                  <el-button text size="small" :icon="Document" @click="insertSnippet('outline')">大纲模板</el-button>
                  <el-button text size="small" :icon="Document" @click="insertSnippet('structure')">结构模板</el-button>
                  <el-button text size="small" :icon="Document" @click="insertSnippet('rules')">规则模板</el-button>
                </div>
                <el-input
                  ref="contentInputRef"
                  v-model="form.content"
                  type="textarea"
                  :rows="16"
                  placeholder="支持变量占位符：{industry_name} {platform_name} {brand_name} {keywords} {knowledge_content} 等&#10;点击左侧变量面板可快速插入"
                  class="prompt-textarea"
                />
                <div v-if="detectedVars.length > 0" class="detected-vars">
                  <span class="dv-label">检测到 {{ detectedVars.length }} 个变量：</span>
                  <el-tag v-for="v in detectedVars" :key="v.key" size="small" :type="v.is_builtin ? 'success' : 'danger'" effect="plain" class="dv-tag">
                    {{ '{' + v.key + '}' }}
                    <span class="dv-desc">{{ v.desc }}</span>
                  </el-tag>
                </div>
                <el-alert
                  v-if="unresolvedVars.length"
                  class="unresolved-alert"
                  type="error"
                  :closable="false"
                  show-icon
                  :title="`${unresolvedVars.length} 个变量无法解析，渲染时会原样保留为 {变量名}`"
                  :description="'这些变量不在系统白名单内，AI 将收到错误文本：' + unresolvedVars.map(k => '{' + k + '}').join(' ')"
                />
              </div>
            </el-form-item>
            <el-form-item label="设为默认">
              <el-switch v-model="form.is_default" :active-value="1" :inactive-value="0" />
            </el-form-item>
          </el-form>
        </div>

      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- AI 写提示词：让 AI 按白名单变量为系统写标准提示词模板 -->
    <el-dialog v-model="aiDialog" title="AI 写提示词（让 AI 为系统写标准模板）" width="720px">
      <el-alert type="info" :closable="false" show-icon class="ai-tip">
        <template #title>AI 会严格按照系统变量白名单生成</template>
        生成的提示词只会使用系统支持的内置变量（如 {brand_name} / {geo_signals}），可直接被生产链路渲染。若未配置 LLM，请先在「LLM 配置」页填写 Key，或手动编写。
      </el-alert>
      <el-form label-width="88px" style="margin-top: 12px;">
        <el-form-item label="类别">
          <el-select v-model="aiForm.category" style="width: 100%">
            <el-option v-for="c in categories" :key="c.key" :label="c.name" :value="c.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称（可选）">
          <el-input v-model="aiForm.name" placeholder="留空将自动命名" />
        </el-form-item>
        <el-form-item label="要求描述">
          <el-input v-model="aiForm.requirement" type="textarea" :rows="3" placeholder="例如：面向小红书的口语化大纲，强植入品牌信号，并呼应目标客户问 AI 的问题" />
        </el-form-item>
      </el-form>
      <div v-if="aiResult" class="ai-result">
        <el-alert v-if="aiResult.non_builtin && aiResult.non_builtin.length" type="warning" :closable="false" show-icon
          :title="'有 ' + aiResult.non_builtin.length + ' 个变量不在白名单：' + aiResult.non_builtin.map(k => '{'+k+'}').join(' ')" />
        <el-input v-model="aiResult.content" type="textarea" :rows="14" />
      </div>
      <template #footer>
        <el-button @click="aiDialog = false">关闭</el-button>
        <el-button :icon="CopyDocument" :disabled="!aiResult" @click="copyAiResult">复制</el-button>
        <el-button type="success" :disabled="!aiResult" @click="saveAiAsPrompt">保存为提示词</el-button>
        <el-button type="primary" :icon="Cpu" :loading="aiLoading" @click="generateAiPrompt">生成</el-button>
      </template>
    </el-dialog>

    <!-- 导入弹窗 -->
    <el-dialog v-model="importDialog" title="批量导入 AI 提示词" width="680px">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        <template #title>支持三种方式</template>
        ① 直接粘贴 JSON 数组；② 上传 .json 文件；③ 每条字段：<b>name / category / content / description / tags</b>（category 取值 outline / draft / rewrite / safety / illustration / geo）。
      </el-alert>
      <el-form label-width="80px">
        <el-form-item label="JSON数据">
          <el-input v-model="importData" type="textarea" :rows="10" placeholder='JSON数组格式：[{"name":"GEO软文生成","category":"geo","content":"你是一位 GEO 内容策略专家…","description":"生成带信号的 GEO 软文","tags":"GEO,带信号"}]' />
        </el-form-item>
        <el-form-item label="或上传文件">
          <el-upload
            action="#"
            :auto-upload="false"
            :show-file-list="true"
            :on-change="handleImportFile"
            :before-upload="() => false"
            accept=".json"
            style="width: 100%;"
          >
            <el-button :icon="Document">选择 .json 文件</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button text @click="downloadPromptTemplate">下载模板</el-button>
        <el-button @click="importDialog = false">取消</el-button>
        <el-button type="primary" @click="doImport" :loading="importing">导入</el-button>
      </template>
    </el-dialog>

    <!-- 只读查看抽屉 -->
    <el-drawer v-model="viewVisible" :title="viewItem?.name || '提示词详情'" size="640px" direction="rtl">
      <div class="view-content" v-if="viewItem">
        <div class="view-meta">
          <el-tag size="small" :style="{ background: catColor(viewItem.category) + '22', color: catColor(viewItem.category), border: 'none' }">
            {{ catName(viewItem.category) }}
          </el-tag>
          <el-tag v-if="viewItem.is_default" size="small" type="warning" effect="dark">默认</el-tag>
          <el-tag v-if="viewItem.tags" size="small" effect="plain">{{ viewItem.tags }}</el-tag>
          <el-tag v-if="viewItem.usage_count" size="small" type="info" effect="plain">用 {{ viewItem.usage_count }} 次</el-tag>
        </div>
        <div class="view-desc" v-if="viewItem.description">{{ viewItem.description }}</div>
        <div class="view-vars" v-if="viewItem.variables && parseVars(viewItem.variables).length">
          <span class="view-vars-label">变量：</span>
          <el-tag v-for="v in parseVars(viewItem.variables)" :key="v" size="small" effect="plain" type="info" class="var-tag">{{ '{' + v + '}' }}</el-tag>
        </div>
        <div class="view-body-label"><el-icon><Memo /></el-icon> 提示词全文</div>
        <div class="view-body-text">{{ viewItem.content || '（空）' }}</div>
        <div class="view-foot">
          <el-button type="primary" :icon="CopyDocument" @click="copyContent(viewItem); viewVisible = false">复制全文</el-button>
          <el-button :icon="Edit" @click="viewVisible = false; openEdit(viewItem)">编辑</el-button>
        </div>
      </div>
    </el-drawer>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, markRaw, inject } from 'vue'
import { useRoute } from 'vue-router'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFocusScroll } from '../composables/useFocusScroll'
import {
  Plus, Edit, Delete, MagicStick, CopyDocument, Clock, List, EditPen, Lock, Files,
  Search, Download, Upload, Document, DocumentCopy, TrendCharts, PriceTag, ArrowDown, CircleCheckFilled, View, Cpu
} from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { promptLibraryApi } from '../api'
import EmptyState from '../components/EmptyState.vue'

const iconMap = {
  List: markRaw(List),
  EditPen: markRaw(EditPen),
  MagicStick: markRaw(MagicStick),
  Lock: markRaw(Lock),
}

const store = useAppStore()
const route = useRoute()
const focusId = computed(() => route.query.focus)
const loading = ref(false)
const saving = ref(false)
const seeding = ref(false)
const categories = ref([])
const list = ref([])
const activeCategory = ref('outline')
const dialogVisible = ref(false)
const editing = ref(false)
const metaPromptOpen = ref(false)
const form = ref({ name: '', category: 'outline', content: '', description: '', is_default: 0, tags: '', variable_schema: [] })

const filteredList = computed(() => list.value.filter(i => i.category === activeCategory.value))
const defaultCount = computed(() => list.value.filter(i => i.is_default).length)
function getCount(key) { return list.value.filter(i => i.category === key).length }
function catColor(key) {
  const c = categories.value.find(c => c.key === key)
  return c ? c.color : '#94a3b8'
}
function catIcon(key) {
  const c = categories.value.find(c => c.key === key)
  return c ? iconMap[c.icon] : null
}
function catName(key) {
  const c = categories.value.find(c => c.key === key)
  return c ? c.name : key
}

// ===== 只读查看抽屉 =====
const viewVisible = ref(false)
const viewItem = ref(null)
function openView(item) {
  viewItem.value = item
  viewVisible.value = true
}
function formatTime(t) {
  if (!t) return '—'
  return new Date(t).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit' })
}
function parseVars(v) {
  if (!v) return []
  if (Array.isArray(v)) return v
  try { return JSON.parse(v) } catch { return [] }
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
    is_default: 0, tags: '', variable_schema: [], industry_id: store.currentIndustryId
  }
  customVars.value = []
  dialogVisible.value = true
}

function openEdit(item) {
  editing.value = true
  form.value = { ...item, variable_schema: parseVars(item.variable_schema) }
  customVars.value = parseVars(item.variable_schema).map(v => ({ name: v.name || v, desc: v.desc || '' }))
  dialogVisible.value = true
}

async function save() {
  if (!form.value.name?.trim()) { ElMessage.warning('请输入名称'); return }
  // 未解析变量拦截：提醒用户，避免把会原样保留的 {xxx} 存进生产库
  if (unresolvedVars.value.length) {
    try {
      await ElMessageBox.confirm(
        `检测到 ${unresolvedVars.value.length} 个变量不在系统白名单内（${unresolvedVars.value.map(k => '{' + k + '}').join(' ')}）。\n渲染时会原样保留为 {变量名}，AI 可能收到错误文本。确定仍要保存吗？`,
        '变量未解析警告', { type: 'warning', confirmButtonText: '仍要保存', cancelButtonText: '去修改' }
      )
    } catch {
      return
    }
  }
  // 同步自定义变量到 variable_schema（仅保留 name/desc，value 是预览用的临时值）
  form.value.variable_schema = customVars.value
    .filter(v => v.name)
    .map(({ name, desc }) => ({ name, desc }))
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

// ========== AI 写提示词（变量白名单约束） ==========
const aiDialog = ref(false)
const aiLoading = ref(false)
const aiResult = ref(null)
const aiForm = ref({ category: 'outline', name: '', requirement: '' })

function catLabel(key) {
  const c = categories.value.find(x => x.key === key)
  return c ? c.name : key
}

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
  try {
    await navigator.clipboard.writeText(aiResult.value.content)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
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
  customVars.value = []
  aiDialog.value = false
}

async function copyContent(item) {
  try {
    await navigator.clipboard.writeText(item.content || '')
    // 增加使用次数
    await promptLibraryApi.incrementUsage(item.id)
    ElMessage.success('已复制到剪贴板')
    await loadList()
  } catch {
    ElMessage.error('复制失败')
  }
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

// ===== 变量面板 =====
const contentInputRef = ref(null)
const varSearch = ref('')
const builtinVars = ref([])
const customVars = ref([])

async function loadBuiltinVars() {
  try {
    const res = await promptLibraryApi.builtinVariables()
    // 后端返回 { variables:[...], groups:{...} }，这里取 variables 数组；
    // 兼容历史接口直出数组的情况，避免 builtinVars 变成对象导致 .forEach 崩溃
    const payload = res && res.data
    builtinVars.value = (payload && payload.variables) || payload || []
  } catch {
    // fallback
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

const groupedVars = computed(() => {
  const groups = {}
  const kw = varSearch.value.toLowerCase()
  // 内置变量
  builtinVars.value.forEach(v => {
    if (kw && !v.key.toLowerCase().includes(kw) && !(v.desc || '').toLowerCase().includes(kw)) return
    const g = v.group || '其他'
    if (!groups[g]) groups[g] = { name: g, items: [] }
    groups[g].items.push(v)
  })
  // 自定义变量
  if (customVars.value.length) {
    const items = customVars.value.filter(v => {
      if (!v.name) return false
      if (kw && !v.name.toLowerCase().includes(kw) && !(v.desc || '').toLowerCase().includes(kw)) return false
      return true
    }).map(v => ({ key: v.name, desc: v.desc || '自定义变量', is_custom: true }))
    if (items.length) groups['自定义'] = { name: '自定义', items }
  }
  return Object.values(groups).map(g => ({ ...g, isGeo: (g.name || '').includes('GEO') }))
})

// 各分类的推荐变量集（一键灌入本类默认变量用）
const CATEGORY_DEFAULT_VARS = {
  outline: ['industry_name', 'platform_name', 'persona_name', 'brand_info', 'keywords', 'knowledge_content'],
  draft: ['industry_name', 'persona_name', 'persona_identity', 'persona_tone', 'brand_info', 'outline_content', 'keywords', 'anti_ai_rules', 'compliance_rules', 'word_min', 'word_max'],
  rewrite: ['draft_content', 'brand_info', 'anti_ai_rules', 'ai_seo_rules', 'word_min', 'word_max'],
  geo: ['industry_name', 'platform_name', 'geo_signals', 'brand_info', 'core_products', 'selling_points', 'outline_content', 'keywords', 'anti_ai_rules', 'compliance_rules', 'expected_recommendation', 'word_min', 'word_max'],
  illustration: ['platform_name', 'image_position', 'section_title', 'section_content', 'brand_name', 'style_label', 'aspect_ratio', 'image_size', 'keywords'],
}

// 一键灌入「本类默认变量」：把当前分类推荐变量集中尚未写入的占位符批量插入
function injectCategoryDefaults() {
  const set = CATEGORY_DEFAULT_VARS[form.value.category] || []
  if (!set.length) { ElMessage.info('该分类暂无可灌入的默认变量'); return }
  const before = form.value.content || ''
  const missing = set.filter(k => !before.includes(`{${k}}`))
  if (!missing.length) { ElMessage.info('本类默认变量已包含在内'); return }
  const insertText = missing.map(k => `{${k}}`).join(' ')
  form.value.content = before + (before && !before.endsWith('\n') ? '\n' : '') + '\n' + insertText + '\n'
  ElMessage.success(`已灌入 ${missing.length} 个本类默认变量`)
}

// 一键插入某个分组下的全部变量
function insertGroup(group) {
  const missing = group.items.filter(v => !(form.value.content || '').includes(`{${v.key}}`))
  if (!missing.length) { ElMessage.info('该分组变量已全部存在'); return }
  const text = missing.map(v => `{${v.key}}`).join(' ')
  form.value.content = (form.value.content || '') + (form.value.content && !form.value.content.endsWith('\n') ? '\n' : '') + '\n' + text + '\n'
  ElMessage.success(`已插入 ${missing.length} 个 ${group.name} 变量`)
}

function isVarUsed(key) {
  return (form.value.content || '').includes(`{${key}}`)
}

function addCustomVar() {
  customVars.value.push({ name: '', desc: '' })
}

function insertVariable(key) {
  const varText = `{${key}}`
  const textarea = contentInputRef.value?.$el?.querySelector('textarea')
  if (textarea) {
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    form.value.content = form.value.content.slice(0, start) + varText + form.value.content.slice(end)
    setTimeout(() => {
      textarea.focus()
      textarea.setSelectionRange(start + varText.length, start + varText.length)
    }, 0)
  } else {
    form.value.content += varText
  }
}

// 元提示词（让其它 AI 帮写符合本系统规范的标准提示词），可一键复制
const META_PROMPT = `你是一名「多行业提示词矩阵管理系统（GEO 作战版）」的资深提示词工程师，擅长把模糊的营销 / GEO 需求，转化为该系统可稳定渲染、直接产出高质量文章的标准提示词模板。

# 你的任务
为系统「AI 提示词库」编写一条标准提示词模板（带 {变量} 占位符）。这条模板最终会被系统引擎渲染成真正发给大模型的提示词，请直接产出"可粘贴即用"的成品，不要给我一段需要我再加工的描述。

# 系统本质（必须理解）
本系统是 GEO（生成式引擎优化）作战系统：提示词服务于"软文生产 10 步流水线"，目标是让 AI 搜索引擎能读懂并主动推荐我们的品牌。所以一条好的模板必须同时赢得两层信任：
- 算法信任：品牌实体信号可抽取、可溯源、可归属（让 AI 能引用我们）；
- 心智信任：内容有温度、像真人、读者愿意信（让人想了解更多）。
写模板时优先考虑：品牌实体信号（{brand_name}/{official_website}/{contact_phone}/{core_products}）、可量化证据（来自 {knowledge_content}）、以及 GEO 意图信号（{geo_signals}/{intent_question}/{expected_recommendation}）。

# 系统约束（必须严格遵守）
1. 系统是"模板引擎"：运行时用真实上下文替换 {变量名}。模板里只能写占位符，绝不能把具体行业名 / 品牌名 / 平台名写死，否则换行业就废了。
2. 只能用下方白名单变量（大小写敏感，全部可用）。写了白名单外的变量，渲染时会被原样保留成 {xxx} 字面文本喂给 AI——不报错，但会污染输入、拉低质量，极难排查。
   - 行业/平台：industry_name, industry_desc, platform_name, compliance_level, platform_tone, platform_word_min, platform_word_max, word_min, word_max, current_date
   - 账号/人设：account_name, account_content_track, persona_name, persona_identity, persona_tone, persona_contact_rule
   - 品牌：brand_name, brand_info, brand_selling_points, selling_points, brand_official_url, brand_official_website, official_website, contact_phone, contact_wechat, contact_email, brand_slogan, core_products, target_keywords, brand_story
   - 关键词/知识：keywords, keyword_list, knowledge_content, knowledge_items, knowledge_summary, knowledge_titles, knowledge_count
   - 生产产物：outline_content, draft_content, rewrite_content, final_content, task_title
   - 规则（三大规则库，渲染时已注入启用项）：anti_ai_rules（去AI味/心智信任）, compliance_rules（合规底线）, ai_seo_rules（算法信任/SEO）
   - GEO 作战：target_persona_name, target_persona_role, target_persona_pain_points, target_persona_cares_about, target_persona_needs, intent_question, intent_category, expected_recommendation, geo_signals
   - 第4步目标客户需求细粒度：target_needs_signals（必含品牌信号）, target_needs_pains（必回应痛点）, target_needs_recommendation（期望推荐角度）
   - 配图专用：section_title, section_content, section_index, image_position, aspect_ratio, image_size, style_label
3. 自定义变量：若白名单不够用，可在模板中自定义 {自定义变量名}，并在【自定义变量说明】里写清含义与建议取值——系统渲染前会弹窗让用户填写，不影响渲染。

# 与软文生产 10 步的耦合（写模板前先选对类型）
- outline（大纲类）→ 第7步 生成大纲；可结合 {knowledge_content}/{geo_signals} 规划"以问带答"结构
- draft（初稿类）→ 第8步 生成初稿；务必要把 {brand_info}/{anti_ai_rules}/{compliance_rules}/{geo_signals} 吃进去
- rewrite（洗稿/精修类）→ 第9步 安全发布 & GEO 筛选；做信号补强、结构化、温度精修
- geo（GEO 安全筛选/闸门类）→ 第9步 GEO 闸门 & 发布前体检；做实体审计、意图覆盖、JSON-LD 建议（注：系统已把旧"安全类 safety"合并进 geo，请统一用 geo）
- illustration（配图类）→ 第10步 文章配图；按封面/章节逐张渲染，用 {section_title}/{section_content}/{style_label}
写模板时默认就为该步骤服务，变量尽量覆盖该步骤能拿到的全部上下文。

# 标准四段式结构（强制遵循）
# 角色(Role)：给具体身份 / 经验 / 口吻（如"5 年经验的真空产线厂长顾问"），避免泛泛的"你是一个 AI"。
# 背景(Context)：全部用 {变量} 注入——行业、平台、人设、品牌、知识、规则、GEO 信号各取所需，禁止出现真实名称。
# 任务(Task)：明确做什么、围绕哪些关键词、产出什么形态（如"3-5 段大纲/完整初稿/精修稿/GEO 体检清单"），并写明本模板服务于哪个生产步骤。
# 约束与输出格式(Constraints)：量化约束（字数区间 {word_min}-{word_max}、品牌词密度 %、段落数）；引用规则用 {anti_ai_rules}/{compliance_rules}/{ai_seo_rules}；给明确输出分隔符或字段名，方便下游解析；末尾固定加一句"不要输出思考过程或修改说明。"。

# 我提供的信息
- 类型（五选一）：大纲类(outline) / 初稿类(draft) / 洗稿类(rewrite) / GEO类(geo) / 配图类(illustration)
- 服务步骤：<如 第9步 安全发布 & GEO 筛选>
- 行业示例：<在此填写，如 真空设备>
- 平台示例：<在此填写，如 知乎>
- 额外要求：<在此填写，如 增加 FAQ 模块、强调实测数据、加入真实使用场景、输出可粘贴的 JSON-LD>

# 输出格式（严格按序输出，不要替我执行任何文章生成）
1. 【模板正文】——上面要求的四段式，可直接粘贴进系统提示词库（变量用 {变量名}，行内引用规则用 {anti_ai_rules} 等）。
2. 【所用变量清单】——逐条列出本模板用到的 {变量名} 及其作用，并自查确认全部在白名单内；若有自定义变量一并标注。
3. 【编写说明】——简述角色 / 约束 / 输出格式的设计理由，以及它如何服务于指定生产步骤与双信任目标，便于我二次调整。
4. 【自定义变量说明】（如用到）——列出自定义变量名、含义、建议取值。`

async function copyMetaPrompt() {
  try {
    await navigator.clipboard.writeText(META_PROMPT)
    ElMessage.success('元提示词已复制，可直接发给其它 AI')
  } catch {
    ElMessage.error('复制失败')
  }
}

// 模板片段
function insertSnippet(type) {
  const snippets = {
    outline: `\n# 角色设定\n你是一位资深的{industry_name}行业内容专家，擅长{platform_name}平台的内容创作。\n\n# 任务目标\n请围绕关键词「{keywords}」，结合以下知识库内容，生成一份结构清晰的文章大纲。\n\n# 知识库参考\n{knowledge_content}\n\n# 品牌信息\n{brand_info}\n\n# 输出要求\n1. 包含3-5个核心段落\n2. 每段标注要点\n3. 融入品牌{brand_name}的自然露出\n`,
    structure: `\n## 标题\n（吸引眼球，包含关键词）\n\n## 开头引入\n（结合{industry_name}行业痛点）\n\n## 核心内容\n### 要点一\n### 要点二\n### 要点三\n\n## 品牌植入\n（自然融入{brand_name}）\n\n## 结尾引导\n（符合{platform_name}平台调性）\n`,
    rules: `\n# 合规要求\n{compliance_rules}\n\n# 去AI味要求\n{anti_ai_rules}\n\n# AI SEO要求\n{ai_seo_rules}\n\n# 人设约束\n身份：{persona_identity}\n语气：{persona_tone}\n联系方式规则：{persona_contact_rule}\n`,
  }
  form.value.content = (form.value.content || '') + snippets[type]
}

// ===== 变量检测 =====
const detectedVars = ref([])
watch(() => form.value.content, async (newVal) => {
  if (!newVal) { detectedVars.value = []; return }
  try {
    const res = await promptLibraryApi.detectVariables(newVal)
    detectedVars.value = res.data || []
  } catch {}
}, { debounce: 500 })

// 未解析变量（不在系统白名单内，渲染时会原样保留为 {xxx}）
const unresolvedVars = computed(() => detectedVars.value.filter(v => !v.is_builtin).map(v => v.key))

// ===== 复制提示词 =====
async function duplicate(item) {
  try {
    await promptLibraryApi.duplicate(item.id)
    ElMessage.success('克隆成功')
    await loadList()
  } catch {
    ElMessage.error('克隆失败')
  }
}

// ===== 导入导出 =====
const importDialog = ref(false)
const importData = ref('')
const importing = ref(false)

async function handleExport(cmd) {
  try {
    const cat = cmd === 'all' ? '' : cmd
    const res = await promptLibraryApi.exportPrompts(store.currentIndustryId, cat)
    const blob = new Blob([res], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `prompts_${cat || 'all'}.json`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

async function doImport() {
  if (!importData.value.trim()) { ElMessage.warning('请输入JSON数据'); return }
  importing.value = true
  try {
    const data = JSON.parse(importData.value)
    const res = await promptLibraryApi.importPrompts({
      industry_id: store.currentIndustryId,
      data
    })
    ElMessage.success(res.data.msg)
    importDialog.value = false
    importData.value = ''
    await loadList()
  } catch (e) {
    ElMessage.error('导入失败：JSON格式错误')
  } finally {
    importing.value = false
  }
}

function handleImportFile(file) {
  const f = file.raw || file
  if (!f) return
  const reader = new FileReader()
  reader.onload = (e) => {
    importData.value = e.target.result || ''
    ElMessage.info(`已读取文件：${file.name}`)
  }
  reader.readAsText(f)
}

function downloadPromptTemplate() {
  const sample = [
    { name: '标准大纲', category: 'outline', content: '请根据以下信息生成文章大纲：\n行业：{industry_name}\n关键词：{keywords}', description: '通用大纲模板', tags: '大纲' },
    { name: '初稿写作', category: 'draft', content: '请基于大纲撰写初稿：\n{topic_outline}\n规则：{anti_ai_rules}', description: '初稿模板', tags: '初稿' },
    { name: 'GEO软文生成', category: 'geo', content: '你是一位既懂{industry_name}行业、又精通 GEO 的内容策略专家。请基于以下 GEO 信号写一篇能被 AI 搜索引擎引用并推荐我们的软文：\n{geo_signals}', description: '生成带信号的 GEO 软文', tags: 'GEO,带信号' },
  ]
  const blob = new Blob([JSON.stringify(sample, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'prompt_import_template.json'
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.prompt-library-view { display: flex; flex-direction: column; gap: 16px; }

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
.prompt-item {
  position: relative;
  display: flex; flex-direction: column; gap: 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--cat-color, #94a3b8);
  border-radius: var(--radius-lg);
  padding: 16px 18px;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
  animation: promptIn 0.34s ease;
}
.prompt-item:hover {
  transform: translateY(-3px);
  border-color: var(--brand-300);
  border-left-color: var(--cat-color, #94a3b8);
  box-shadow: var(--shadow-md);
}
.prompt-item__main { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 10px; }
.prompt-item__header { display: flex; align-items: center; gap: 10px; }
.prompt-item__avatar {
  width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 18px;
}
.prompt-item__name {
  flex: 1; min-width: 0;
  font-size: 15px; font-weight: 700; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.prompt-item__badges { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.prompt-item__desc {
  font-size: 13px; color: var(--text-secondary); line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.prompt-item__preview {
  background: var(--slate-50);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 10px 12px;
}
.prompt-item__preview-label {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; font-weight: 600; color: var(--text-tertiary);
  margin-bottom: 6px;
}
.prompt-item__preview-text {
  font-size: 12px; color: var(--text-secondary); line-height: 1.65;
  font-family: 'SF Mono', 'Monaco', monospace;
  white-space: pre-wrap; word-break: break-word;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.prompt-item__vars { display: flex; gap: 5px; flex-wrap: wrap; }
.var-tag { font-family: 'SF Mono', monospace; font-size: 11px; }
.var-more { font-size: 11px; color: var(--text-tertiary); }
.prompt-item__meta {
  display: flex; gap: 16px; font-size: 12px; color: var(--text-tertiary); flex-wrap: wrap;
  padding-top: 4px; border-top: 1px dashed var(--border-light);
}
.prompt-item__meta span { display: flex; align-items: center; gap: 4px; }
.prompt-item__actions {
  display: flex; flex-direction: row; justify-content: flex-end; gap: 2px; flex-shrink: 0;
  border-top: 1px solid var(--border-light); padding-top: 10px; margin-top: 2px;
}
.prompt-item__actions .el-button { border-radius: 7px; transition: background 0.15s ease, color 0.15s ease; }
.prompt-item__actions .el-button:not(.el-button--danger):hover { background: var(--brand-50); color: var(--brand-600); }
.prompt-item__actions .el-button.el-button--danger:hover { background: #fef2f2; color: var(--el-color-danger, #f56c6c); }
@keyframes promptIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.prompt-item:nth-child(1) { animation-delay: 0s; }
.prompt-item:nth-child(2) { animation-delay: 0.04s; }
.prompt-item:nth-child(3) { animation-delay: 0.08s; }
.prompt-item:nth-child(4) { animation-delay: 0.12s; }
.prompt-item:nth-child(5) { animation-delay: 0.16s; }
.prompt-item:nth-child(6) { animation-delay: 0.20s; }
.prompt-item:nth-child(7) { animation-delay: 0.24s; }
.prompt-item:nth-child(8) { animation-delay: 0.28s; }
.prompt-item:nth-child(9) { animation-delay: 0.32s; }
.prompt-item:nth-child(10) { animation-delay: 0.36s; }

/* 编辑器分栏布局 */
.editor-layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 16px;
  height: 70vh;
  min-height: 500px;
}

/* 元提示词助手 */
.meta-prompt-box {
  background: linear-gradient(135deg, var(--brand-50), var(--slate-50));
  border: 1px solid var(--brand-200);
  border-radius: var(--radius-md);
  margin-bottom: 14px;
  overflow: hidden;
}
.meta-prompt-head {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; cursor: pointer; user-select: none;
}
.meta-prompt-head:hover { background: var(--brand-100); }
.mp-icon { color: var(--brand-500); font-size: 16px; }
.mp-title { flex: 1; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.mp-chevron { color: var(--text-tertiary); }
.mp-chevron.is-open { transform: rotate(180deg); }
.meta-prompt-body { padding: 0 14px 14px; }
.mp-tip { font-size: 12px; color: var(--text-secondary); line-height: 1.6; margin: 0 0 10px; }
.mp-textarea :deep(textarea) {
  font-family: 'SF Mono', 'Monaco', monospace !important;
  font-size: 12px !important; line-height: 1.6 !important;
  background: var(--bg-card) !important; color: var(--text-secondary) !important;
}
.mp-foot { display: flex; align-items: center; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
.mp-hint { font-size: 11px; color: var(--text-tertiary); }
.var-panel {
  background: var(--slate-50);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.editor-center {
  overflow-y: auto;
  padding-right: 4px;
}
.var-panel-head {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  background: var(--bg-card);
}
.vp-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.var-panel-sub {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  border-bottom: 1px solid var(--border-light); background: var(--bg-card);
}
.var-panel-sub .el-input { flex: 1; }
.vp-count { font-size: 11px; color: var(--text-tertiary); white-space: nowrap; }
.var-panel-body { flex: 1; overflow-y: auto; padding: 8px; }
.var-group { margin-bottom: 16px; border: 1px solid var(--border-light); border-radius: var(--radius-sm); overflow: hidden; background: var(--bg-card); }
.var-group--geo { border-color: #14b8a6; box-shadow: 0 0 0 2px color-mix(in srgb, #14b8a6 12%, transparent); }
.var-group-title {
  font-size: 12px; font-weight: 700; color: var(--text-secondary);
  margin-bottom: 0; padding: 8px 10px;
  display: flex; align-items: center; justify-content: space-between;
  background: var(--slate-50); border-bottom: 1px solid var(--border-light);
}
.var-group--geo .var-group-title { background: #ecfeff; color: #0e7490; }
.var-group-name { display: inline-flex; align-items: center; gap: 6px; }
.geo-dot { width: 8px; height: 8px; border-radius: 50%; background: #14b8a6; flex-shrink: 0; }
.var-group-items { display: flex; flex-direction: column; gap: 4px; padding: 8px; }
.var-item {
  position: relative;
  padding: 8px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.var-item:hover { border-color: var(--brand-400); background: var(--brand-50); }
.var-item.is-used { border-color: var(--brand-500); background: var(--brand-50); }
.var-item-key { font-size: 12px; font-family: 'SF Mono', monospace; color: var(--brand-600); font-weight: 600; }
.var-item-desc { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; line-height: 1.4; }
.var-item-used { position: absolute; top: 6px; right: 6px; color: var(--brand-500); font-size: 14px; }
.custom-var-item { display: flex; gap: 4px; margin-bottom: 4px; }
.empty-hint { font-size: 11px; color: var(--text-tertiary); padding: 8px; text-align: center; }

.editor-wrapper { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.editor-toolbar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 10px; background: var(--slate-50); border-radius: var(--radius-sm);
  border: 1px solid var(--border-light);
}
.toolbar-hint { font-size: 11px; color: var(--text-tertiary); flex: 1; }
.prompt-textarea :deep(textarea) {
  font-family: 'SF Mono', 'Monaco', monospace !important;
  font-size: 13px !important;
  line-height: 1.7 !important;
}
.detected-vars {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
  padding: 8px 10px; background: #f0fdf4; border-radius: var(--radius-sm);
  border: 1px solid #bbf7d0;
}
.dv-label { font-size: 12px; color: #15803d; font-weight: 600; margin-right: 4px; white-space: nowrap; }
.dv-tag { display: flex; align-items: center; gap: 4px; }
.dv-desc { font-size: 11px; opacity: 0.7; }

@media (max-width: 1280px) {
  .editor-layout { grid-template-columns: 260px 1fr; }
}
@media (max-width: 1024px) {
  .category-grid { grid-template-columns: repeat(2, 1fr); }
  .editor-layout { grid-template-columns: 1fr; height: auto; }
  .var-panel { max-height: 300px; }
  .prompt-list { grid-template-columns: 1fr; }
}

/* 批量导入提示词板块 */
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

/* 只读查看抽屉 */
.view-content { display: flex; flex-direction: column; gap: 14px; }
.view-meta { display: flex; gap: 6px; flex-wrap: wrap; }
.view-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.6; }
.view-vars { display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }
.view-vars-label { font-size: 12px; color: var(--text-tertiary); }
.view-body-label { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: var(--text-primary); margin-top: 4px; }
.view-body-text {
  font-family: 'SF Mono', 'Monaco', monospace; font-size: 13px; line-height: 1.7;
  color: var(--text-secondary); white-space: pre-wrap; word-break: break-word;
  background: var(--slate-50); border: 1px solid var(--border-light);
  border-radius: var(--radius-md); padding: 14px 16px;
  max-height: 60vh; overflow-y: auto;
}
.view-foot { display: flex; gap: 8px; padding-top: 4px; }
</style>
