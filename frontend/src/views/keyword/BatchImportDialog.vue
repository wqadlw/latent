<template>
  <el-dialog v-model="visible" title="批量导入关键词" width="640px" @closed="reset">
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
      <template #title>支持三种方式</template>
      ① 每行一个关键词；② 逗号 / 制表符分隔字段：<b>词, 类型, 优先级, 关联产品, 标签</b>；③ 直接粘贴 JSON 数组。也可上传 .txt / .csv / .json 文件。
    </el-alert>
    <el-form label-width="88px">
      <el-form-item label="默认类型">
        <el-select v-model="defaultType" style="width: 100%;">
          <el-option v-for="o in KEYWORD_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <div class="form-hint">未单独指定类型的行将使用该类型</div>
      </el-form-item>
      <el-form-item label="导入到分组">
        <el-select v-model="groupId" placeholder="不指定（导入到「未分组」）" clearable style="width: 100%;">
          <el-option v-for="g in groups" :key="g.id" :label="`${g.name}`" :value="g.id" />
        </el-select>
        <div class="form-hint">
          把这一批关键词导入到指定分组；也可在「数据」里用第 6 列写分组名（<b>词, 类型, 优先级, 产品, 标签, 分组名</b>），自动建组并归入。留空则进「未分组」。
        </div>
      </el-form-item>
      <el-form-item label="数据">
        <el-input
          v-model="text"
          type="textarea"
          :rows="10"
          placeholder="示例：&#10;人工智能写作&#10;AI软文, long_tail, 3, 智能写作助手, 教程&#10;SEO优化, long_tail, 2"
          @input="updatePreview"
        />
      </el-form-item>
      <el-form-item label="或上传文件">
        <el-upload
          action="#"
          :auto-upload="false"
          :show-file-list="true"
          :on-change="handleFile"
          :before-upload="() => false"
          accept=".txt,.csv,.json"
          style="width: 100%;"
        >
          <el-button :icon="Document">选择文件</el-button>
          <template #tip><div class="form-hint">支持 .txt（每行一词）/ .csv / .json 数组</div></template>
        </el-upload>
      </el-form-item>
      <el-form-item v-if="preview.count > 0">
        <div class="batch-preview">
          待导入 <b>{{ preview.count }}</b> 条
          <span v-if="preview.sample.length" class="batch-preview-sample">
            （预览：{{ preview.sample.join('、') }}{{ preview.count > preview.sample.length ? ' …' : '' }}）
          </span>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button text @click="downloadTemplate">下载模板</el-button>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="doImport" :loading="importing" :disabled="preview.count === 0">
        导入 {{ preview.count || '' }} 条
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 批量导入关键词：粘贴文本 / 上传文件 → 本地解析预览 → 一次性提交。
 *
 * 解析逻辑（`parseBatchInput`）纯本地、无副作用，放在这里与它唯一的使用者同处一地；
 * 等第二个地方也需要时再抽到 composable —— **先有重复，再抽 composable**。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Document } from '@element-plus/icons-vue'
import { keywordApi } from '../../api'
import { KEYWORD_TYPE_OPTIONS } from '../../constants/status'
import { downloadJson } from '../../utils/download'

const props = defineProps({
  groups: { type: Array, default: () => [] },
  industryId: { type: [Number, String], default: 0 },
})
const emit = defineEmits(['imported'])

const visible = ref(false)
const text = ref('')
const defaultType = ref('long_tail')
const groupId = ref(null)
const importing = ref(false)
const preview = ref({ count: 0, sample: [] })

const VALID_TYPES = KEYWORD_TYPE_OPTIONS.map((o) => o.value)

function open() { visible.value = true }

function parseBatchInput(raw) {
  if (!raw || !raw.trim()) return []
  const trimmed = raw.trim()
  if (trimmed.startsWith('[')) {
    try {
      const arr = JSON.parse(trimmed)
      if (Array.isArray(arr)) {
        return arr.map((it) => {
          if (typeof it === 'string') return { word: it.trim() }
          return {
            word: (it.word || '').trim(),
            type: it.type || '',
            priority: it.priority ?? 2,
            related_product: it.related_product || '',
            tags: it.tags || '',
          }
        }).filter((x) => x.word)
      }
    } catch { /* 非合法 JSON，继续按文本处理 */ }
  }
  const items = []
  for (const rawLine of trimmed.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line) continue
    const sep = line.includes('\t') ? '\t' : (line.includes(',') ? ',' : null)
    if (sep) {
      const parts = line.split(sep).map((s) => s.trim())
      const word = parts[0]
      if (!word) continue
      const type = parts[1] && VALID_TYPES.includes(parts[1]) ? parts[1] : ''
      const priority = ['1', '2', '3'].includes(parts[2]) ? Number(parts[2]) : 2
      const group_name = (parts[5] || '').trim() || undefined
      items.push({ word, type, priority, related_product: parts[3] || '', tags: parts[4] || '', group_name })
    } else {
      items.push({ word: line, type: '', priority: 2, related_product: '', tags: '', group_name: undefined })
    }
  }
  return items
}

function updatePreview() {
  const items = parseBatchInput(text.value)
  preview.value = { count: items.length, sample: items.slice(0, 6).map((i) => i.word) }
  return items
}

function handleFile(file) {
  const f = file.raw || file
  if (!f) return
  const reader = new FileReader()
  reader.onload = (e) => {
    text.value = e.target.result || ''
    updatePreview()
    ElMessage.info(`已读取文件：${file.name}`)
  }
  reader.readAsText(f)
}

async function doImport() {
  const items = updatePreview()
  if (items.length === 0) { ElMessage.warning('没有可导入的关键词'); return }
  importing.value = true
  try {
    const res = await keywordApi.batchImport({
      industry_id: props.industryId,
      default_type: defaultType.value,
      group_id: groupId.value || undefined,
      items,
    })
    const d = res.data || {}
    if (d.errors && d.errors.length) console.warn('批量导入部分失败：', d.errors)
    ElMessage.success(d.msg || '导入完成')
    visible.value = false
    emit('imported')
  } catch (e) {
    ElMessage.error('导入失败：' + (e?.response?.data?.detail || '请检查数据格式'))
  } finally {
    importing.value = false
  }
}

function downloadTemplate() {
  downloadJson([
    { word: '人工智能写作', type: 'long_tail', priority: 3, related_product: '智能写作助手', tags: '教程' },
    { word: 'SEO优化技巧', type: 'long_tail', priority: 2, related_product: '', tags: '干货' },
  ], 'keyword_import_template.json')
}

function reset() {
  text.value = ''
  groupId.value = null
  preview.value = { count: 0, sample: [] }
}

defineExpose({ open })
</script>

<style scoped>
.form-hint { font-size: 12px; color: var(--text-tertiary); line-height: 1.5; margin-top: 2px; }
.batch-preview { font-size: 13px; color: var(--text-secondary); background: var(--bg-hover, #f5f7fa); padding: 8px 12px; border-radius: var(--radius-md, 8px); width: 100%; }
.batch-preview b { color: var(--brand-500, #6366f1); }
.batch-preview-sample { color: var(--text-tertiary); }
</style>
