<template>
  <el-dialog :model-value="modelValue" :title="editing ? '编辑提示词' : '新建提示词'" width="92%" top="3vh" class="prompt-editor-dialog"
    @update:model-value="$emit('update:modelValue', $event)">
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
          <el-button type="primary" :icon="CopyDocument" @click="$emit('copy-meta-prompt')">一键复制元提示词</el-button>
          <span class="mp-hint">复制后粘贴给任意 AI，即可得到符合规范的提示词模板</span>
        </div>
      </div>
    </div>

    <div class="editor-layout">
      <!-- 左栏：变量面板（分组高亮 + 一键灌入本类默认变量） -->
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
              <el-button text size="small" :icon="Plus" @click="customVars.push({ name: '', desc: '' })">添加</el-button>
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
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="submit" :loading="saving">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, CircleCheckFilled, CopyDocument, Delete, Document, MagicStick, Plus, Search } from '@element-plus/icons-vue'
import { META_PROMPT, CATEGORY_DEFAULT_VARS, PROMPT_SNIPPETS } from '../../constants/prompts'
import './prompt-library-shared.css'

/**
 * 提示词编辑器（新建 / 编辑共用）。
 *
 * 三块内容，自左向右：
 *   1. 元提示词折叠区 —— 复制给外部 AI 让它帮写模板（纯静态文本，来自 constants）
 *   2. 变量面板 —— 内置变量（后端白名单）按组列出 + 自定义变量增删，点击插入内容框
 *   3. 编辑器中栏 —— 表单字段 + 内容框 + 变量检测反馈 + 未解析变量告警
 *
 * ⚠️ `form` 与 `categories` 由**视图**传入并就地修改（不是本组件的内部状态）：
 * 视图的 `save()` 要读这份 form 去调接口，`openCreate/openEdit` 也要写它。
 * 反过来，`customVars` 是**本组件内部**状态 —— 视图不需要它，只有保存时通过
 * `submit` 事件带出去（转成 variable_schema）。
 */
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  editing: { type: Boolean, default: false },
  /** 视图持有的 reactive 表单（本组件就地修改） */
  form: { type: Object, required: true },
  categories: { type: Array, default: () => [] },
  /** 后端白名单变量（{ key, desc, group }） */
  builtinVars: { type: Array, default: () => [] },
  /** useVariableDetection 的结果 */
  detectedVars: { type: Array, default: () => [] },
  unresolvedVars: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
  /** 打开弹窗时要载入的自定义变量（来自被编辑项的 variable_schema） */
  initialCustomVars: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'submit', 'copy-meta-prompt'])

const metaPromptOpen = ref(false)
const varSearch = ref('')
const customVars = ref([])
const contentInputRef = ref(null)

// 每次打开：收起元提示词、清空搜索、按传入的 schema 重置自定义变量。
// 不做这一步的话，上一次编辑残留的自定义变量会串到下一次。
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    metaPromptOpen.value = false
    varSearch.value = ''
    customVars.value = (props.initialCustomVars || []).map((v) => ({ ...v }))
  },
)

/** 内置变量 + 自定义变量，按 group 归并；GEO 组额外打标以便高亮。 */
const groupedVars = computed(() => {
  const groups = {}
  const kw = varSearch.value.toLowerCase()
  props.builtinVars.forEach((v) => {
    if (kw && !v.key.toLowerCase().includes(kw) && !(v.desc || '').toLowerCase().includes(kw)) return
    const g = v.group || '其他'
    if (!groups[g]) groups[g] = { name: g, items: [] }
    groups[g].items.push(v)
  })
  if (customVars.value.length) {
    const items = customVars.value
      .filter((v) => {
        if (!v.name) return false
        if (kw && !v.name.toLowerCase().includes(kw) && !(v.desc || '').toLowerCase().includes(kw)) return false
        return true
      })
      .map((v) => ({ key: v.name, desc: v.desc || '自定义变量', is_custom: true }))
    if (items.length) groups['自定义'] = { name: '自定义', items }
  }
  return Object.values(groups).map((g) => ({ ...g, isGeo: (g.name || '').includes('GEO') }))
})

function isVarUsed(key) {
  return (props.form.content || '').includes(`{${key}}`)
}

/** 把一段文本追加到内容框末尾（自动补换行，避免和上一段黏在一起）。 */
function appendToContent(text) {
  const before = props.form.content || ''
  const sep = before && !before.endsWith('\n') ? '\n' : ''
  props.form.content = before + sep + '\n' + text + '\n'
}

/** 一键灌入「本类默认变量」：只补还没写进去的那些。 */
function injectCategoryDefaults() {
  const set = CATEGORY_DEFAULT_VARS[props.form.category] || []
  if (!set.length) {
    ElMessage.info('该分类暂无可灌入的默认变量')
    return
  }
  const before = props.form.content || ''
  const missing = set.filter((k) => !before.includes(`{${k}}`))
  if (!missing.length) {
    ElMessage.info('本类默认变量已包含在内')
    return
  }
  appendToContent(missing.map((k) => `{${k}}`).join(' '))
  ElMessage.success(`已灌入 ${missing.length} 个本类默认变量`)
}

/** 一键插入某个分组下尚未出现的全部变量。 */
function insertGroup(group) {
  const missing = group.items.filter((v) => !(props.form.content || '').includes(`{${v.key}}`))
  if (!missing.length) {
    ElMessage.info('该分组变量已全部存在')
    return
  }
  appendToContent(missing.map((v) => `{${v.key}}`).join(' '))
  ElMessage.success(`已插入 ${missing.length} 个 ${group.name} 变量`)
}

/** 插入单个变量到**光标处**（拿不到 textarea 时退化成追加到末尾）。 */
function insertVariable(key) {
  const varText = `{${key}}`
  const textarea = contentInputRef.value?.$el?.querySelector('textarea')
  if (textarea) {
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const content = props.form.content || ''
    props.form.content = content.slice(0, start) + varText + content.slice(end)
    setTimeout(() => {
      textarea.focus()
      textarea.setSelectionRange(start + varText.length, start + varText.length)
    }, 0)
  } else {
    props.form.content = (props.form.content || '') + varText
  }
}

function insertSnippet(type) {
  const snippet = PROMPT_SNIPPETS[type]
  if (snippet) props.form.content = (props.form.content || '') + snippet
}

/** 保存：把内部的自定义变量转成 variable_schema 一起交给视图。 */
function submit() {
  emit('submit', {
    ...props.form,
    variable_schema: customVars.value.filter((v) => v.name).map(({ name, desc }) => ({ name, desc })),
  })
}
</script>
