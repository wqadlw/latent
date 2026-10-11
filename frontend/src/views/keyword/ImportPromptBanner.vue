<template>
  <div class="kw-import-prompt-banner">
    <div class="kip-head" @click="open = !open">
      <el-icon class="kip-icon"><MagicStick /></el-icon>
      <div class="kip-head-text">
        <span class="kip-title">批量导入提示词</span>
        <span class="kip-hint">把下面这段发给任意 AI（ChatGPT / Claude / 通义 / DeepSeek），它能把你手里各种格式的关键词转成本系统可直接批量导入的格式</span>
      </div>
      <el-icon class="kip-chevron" :class="{ 'is-open': open }"><ArrowDown /></el-icon>
    </div>
    <div v-show="open" class="kip-body">
      <el-input :model-value="KW_IMPORT_PROMPT" type="textarea" :rows="14" readonly class="kip-textarea" />
      <div class="kip-foot">
        <el-button type="primary" :icon="CopyDocument" @click="copyPrompt">一键复制提示词</el-button>
        <el-button :icon="Upload" @click="emit('open-batch')">打开批量导入</el-button>
        <span class="kip-tip">复制后粘贴给 AI，把转换结果粘到批量导入框即可</span>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 「批量导入提示词」折叠板块：给用户一段可直接丢给外部 AI 的转换提示词。
 *
 * 自成一体（折叠状态 + 常量 + 复制），只把「打开批量导入」这个跨组件动作 emit 出去。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ArrowDown, CopyDocument, Upload } from '@element-plus/icons-vue'
import { writeClipboard } from '../../utils/clipboard'

const emit = defineEmits(['open-batch'])

const open = ref(false)

const KW_IMPORT_PROMPT = `你是一个关键词格式转换助手。我会给你一批关键词（可能是各种格式：逐行、逗号分隔、表格、带分类/优先级/产品/标签的混合文本等），请把它们转换成下面三种格式之一，方便我批量导入到关键词管理系统。

系统支持的批量导入格式（三选一，默认输出格式2）：
1. 简单格式：每行一个关键词
2. 字段格式：每行一条，用逗号分隔，字段顺序为：关键词, 类型, 优先级, 关联产品, 标签, 分组名
   - 类型取值：brand(核心品牌词) / product(产品词) / long_tail(长尾词) / question(问题词)
   - 优先级取值：1 / 2 / 3（3最高，默认2）
   - 关联产品、标签、分组名可选，没有则留空；分组名不存在会自动新建并归入
3. JSON 数组格式：[{"word":"关键词","type":"long_tail","priority":2,"related_product":"","tags":"","group_name":"品牌词"}]

要求：
- 识别每条关键词的合理类型（品牌名→brand，具体产品→product，长尾/泛词→long_tail，疑问句→question）
- 如有优先级信息则保留，否则默认 2
- 去除重复词、空行、无意义符号
- 默认输出"字段格式（格式2）"，除非我指定其他格式
- 只输出转换结果，不要额外解释

请等待我发送关键词后再转换。`

async function copyPrompt() {
  if (await writeClipboard(KW_IMPORT_PROMPT)) ElMessage.success('已复制提示词，粘贴给任意 AI 即可')
  else ElMessage.error('复制失败，请手动选择文本复制')
}
</script>

<style scoped>
.kw-import-prompt-banner {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-left: 3px solid #8b5cf6;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.kip-head { display: flex; align-items: center; gap: 12px; padding: 12px 16px; cursor: pointer; }
.kip-icon { color: #8b5cf6; font-size: 18px; flex-shrink: 0; }
.kip-head-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.kip-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.kip-hint { font-size: 12px; color: var(--text-tertiary); line-height: 1.5; }
.kip-chevron { color: var(--text-tertiary); transition: transform .2s; flex-shrink: 0; }
.kip-chevron.is-open { transform: rotate(180deg); }
.kip-body { padding: 0 16px 14px; }
.kip-textarea :deep(.el-textarea__inner) { font-family: 'SF Mono', 'Monaco', monospace; font-size: 12px; }
.kip-foot { display: flex; align-items: center; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
.kip-tip { font-size: 12px; color: var(--text-tertiary); }
</style>
