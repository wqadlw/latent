<template>
  <el-dialog v-model="visible" title="历史版本" width="600px">
    <div v-if="list.length === 0" class="empty-tip" style="padding: 20px">暂无历史版本，保存内容时会自动记录</div>
    <div v-else class="version-list">
      <div v-for="v in list" :key="v.id" class="version-item">
        <div class="version-item__head">
          <span class="version-no">v{{ v.version_no }}</span>
          <span class="version-time">{{ formatVersionTime(v.create_time) }}</span>
          <el-button size="small" type="primary" plain @click="$emit('restore', v)">回滚到此版本</el-button>
        </div>
        <div class="version-content">{{ v.content }}</div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  list: { type: Array, default: () => [] },
  step: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'restore'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

function formatVersionTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d) ? iso : d.toLocaleString('zh-CN', { hour12: false })
}
</script>
