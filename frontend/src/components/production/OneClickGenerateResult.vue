<template>
  <el-dialog v-model="visible" :title="'AI 生成 · ' + (labelMap[step] || '')" width="720px">
    <el-alert
      v-if="data && data.config_name"
      type="success" :closable="false" show-icon
      :title="`由 ${data.provider || ''} / ${data.model || ''}（${data.config_name}）生成`"
      class="gen-alert"
    />
    <div v-if="step === 'geo' && data && data.parsed && data.parsed.title" class="gen-geo-preview">
      <div class="gen-geo-row"><span class="gen-geo-k">标题</span><span class="gen-geo-v">{{ data.parsed.title }}</span></div>
      <div class="gen-geo-row" v-if="data.parsed.score != null"><span class="gen-geo-k">GEO 评分</span><span class="gen-geo-v">{{ data.parsed.score }} / 100</span></div>
    </div>
    <el-input v-model="data.text" type="textarea" :rows="18" placeholder="AI 生成的内容" />
    <div class="gen-hint" v-if="step === 'geo'">
      下方为 AI 按「安全 · GEO 终稿」契约返回的完整结果（含四段）。点「接受并生成最终发布稿」将自动解析标题/正文/评分/建议并写回。
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
      <el-button :icon="CopyDocument" @click="$emit('copy')">复制</el-button>
      <el-button type="success" :icon="Promotion" @click="$emit('accept')" :loading="accepting">
        {{ step === 'geo' ? '接受并生成最终发布稿' : '接受并写入' + (labelMap[step] || '') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
import { CopyDocument, Promotion } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  data: { type: Object, default: null },
  step: { type: String, default: '' },
  labelMap: { type: Object, default: () => ({}) },
  accepting: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'copy', 'accept'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
</script>
