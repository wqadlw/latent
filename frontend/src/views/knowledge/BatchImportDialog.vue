<template>
  <el-dialog v-model="visible" title="批量导入知识点" width="680px">
    <!-- AI 转换助手：让其它 AI 把素材整理成系统支持的 JSON -->
    <div class="ai-extract-box">
      <div class="ai-extract-head" @click="extractOpen = !extractOpen">
        <el-icon class="ae-icon"><MagicStick /></el-icon>
        <span class="ae-title">有现成素材想快速导入？让 AI 帮你整理成系统 JSON</span>
        <el-icon class="ae-chevron" :class="{ 'is-open': extractOpen }"><ArrowDown /></el-icon>
      </div>
      <div v-show="extractOpen" class="ai-extract-body">
        <p class="ae-tip">把你的原始素材（散落笔记、产品文档、对话记录、网页摘录等）粘贴到下方，点「一键复制转换提示词」后发给 ChatGPT / Claude / 通义 / DeepSeek 等任意 AI，它会返回标准 JSON 数组，直接粘到本弹窗的「JSON模式」即可导入。</p>
        <el-input v-model="extractInput" type="textarea" :rows="6" placeholder="在此粘贴你的原始素材（可选）…" />
        <div class="ae-foot">
          <el-button type="primary" :icon="CopyDocument" @click="copyExtractPrompt">一键复制转换提示词</el-button>
          <span class="ae-hint">复制后发给任意 AI，把返回的 JSON 粘到下方「JSON模式」</span>
        </div>
      </div>
    </div>

    <el-form :model="form" label-width="80px">
      <el-form-item label="目标分类">
        <el-select v-model="form.category_id" clearable placeholder="选择分类（可选）" style="width: 100%;">
          <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="导入模式">
        <el-radio-group v-model="form.mode">
          <el-radio value="text">文本模式</el-radio>
          <el-radio value="json">JSON模式</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="内容">
        <el-input
          v-model="form.data"
          type="textarea"
          :rows="10"
          :placeholder="form.mode === 'text' ? '每行一个知识点，格式：标题:内容 或 标题|内容\n也可用三段式：标题|摘要|内容' : 'JSON数组格式：[{&quot;title&quot;:&quot;标题&quot;,&quot;content&quot;:&quot;内容&quot;,&quot;tags&quot;:&quot;标签&quot;,&quot;summary&quot;:&quot;摘要&quot;}]'"
        />
      </el-form-item>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        <template #title>
          <span v-if="form.mode === 'text'">文本模式：每行一条，用冒号(:)或竖线(|)分隔。支持「标题|摘要|内容」三段式</span>
          <span v-else>JSON模式：粘贴JSON数组，每条支持 title/content/summary/tags/source/importance 字段</span>
        </template>
      </el-alert>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="saveBatch" :loading="saving">导入</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 知识库 —— 批量导入弹窗（含「让其它 AI 转成 JSON」的提示词助手）。
 *
 * 自持表单、请求与 AI 提示词文本。`open(presetCategoryId)` 允许调用方
 * 带上「当前选中的分类」作为默认目标分类。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, CopyDocument, ArrowDown } from '@element-plus/icons-vue'
import { knowledgeApi } from '../../api'
import { writeClipboard } from '../../utils/clipboard'

const props = defineProps({
  /** 分类列表（父组件持有） */
  categories: { type: Array, default: () => [] },
  /** 当前行业 id */
  industryId: { type: [Number, String], default: 0 },
})

const emit = defineEmits(['imported'])

const visible = ref(false)
const saving = ref(false)
const form = ref({ category_id: null, mode: 'text', data: '' })

// AI 转换助手：让其它 AI 把素材整理成系统支持的 JSON
const extractOpen = ref(false)
const extractInput = ref('')

function buildExtractPrompt() {
  const head = `你是「多行业提示词矩阵管理系统」的知识库整理助手。请把我提供的内容提取、归纳，转换为「知识库批量导入」所需的 JSON 数组，每个独立知识点作为数组中的一项。

【字段说明】
- title（必填）：知识点标题，简洁准确，能概括核心内容
- content（必填）：知识点详细内容，保留关键事实、数据、步骤、要点
- summary（可选）：一句话概括该知识点
- tags（可选）：用逗号分隔的标签，如 "敏感肌,防晒,护理"
- source（可选）：来源，如 "官网/产品手册/会议记录"
- importance（可选）：high / normal / low，默认 normal

【输出要求】
1. 只输出一个 JSON 数组，不要输出任何解释、前言、后缀，也不要用 markdown 代码块围栏包裹。
2. 严格使用上述英文字段名（小写），不要自造字段，也不要写成中文键。
3. 把内容拆成尽量独立、不重复的知识点；同一主题过长可拆多条。
4. 若原文零散难以拆分，至少保留一条完整记录，把原文整体放入 content。`
  const raw = extractInput.value.trim()
  const tail = raw
    ? `\n\n【待整理的内容】\n${raw}\n\n请直接输出 JSON 数组：`
    : `\n\n【待整理的内容】\n（请将你的原始素材粘贴在此处，我会立即为你转换为 JSON）\n\n请直接输出 JSON 数组：`
  return head + tail
}

async function copyExtractPrompt() {
  if (await writeClipboard(buildExtractPrompt())) ElMessage.success('转换提示词已复制，发给其它 AI 即可得到 JSON')
  else ElMessage.error('复制失败')
}

function open(presetCategoryId = null) {
  form.value = { category_id: presetCategoryId, mode: 'text', data: '' }
  extractInput.value = ''
  visible.value = true
}

async function saveBatch() {
  if (!form.value.data.trim()) {
    ElMessage.warning('请输入导入内容')
    return
  }
  saving.value = true
  try {
    const payload = {
      industry_id: props.industryId,
      category_id: form.value.category_id,
      mode: form.value.mode,
      data: form.value.data,
    }
    if (form.value.mode === 'json') {
      try {
        payload.data = JSON.parse(form.value.data)
      } catch {
        ElMessage.error('JSON格式错误，请检查')
        return
      }
    }
    const res = await knowledgeApi.batchImport(payload)
    ElMessage.success(res.data.msg)
    visible.value = false
    emit('imported')
  } catch {
    ElMessage.error('导入失败')
  } finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
/* AI 转换助手（批量导入弹窗内） */
.ai-extract-box {
  background: linear-gradient(135deg, var(--brand-50), var(--slate-50));
  border: 1px solid var(--brand-200);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  overflow: hidden;
}
.ai-extract-head {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; cursor: pointer; user-select: none;
  transition: background 0.15s;
}
.ai-extract-head:hover { background: var(--brand-100); }
.ae-icon { color: var(--brand-500); font-size: 16px; }
.ae-title { flex: 1; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.ae-chevron { color: var(--text-tertiary); transition: transform 0.2s; }
.ae-chevron.is-open { transform: rotate(180deg); }
.ai-extract-body { padding: 0 14px 14px; }
.ae-tip { font-size: 12px; color: var(--text-secondary); line-height: 1.6; margin: 0 0 10px; }
.ae-foot { display: flex; align-items: center; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
.ae-hint { font-size: 11px; color: var(--text-tertiary); }
</style>
