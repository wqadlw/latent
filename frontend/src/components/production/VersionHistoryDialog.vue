<template>
  <el-dialog v-model="visible" title="历史版本" width="600px">
    <div v-if="list.length === 0" class="empty-tip" style="padding: 20px">暂无历史版本，保存内容时会自动记录</div>
    <div v-else class="version-list">
      <div v-for="v in list" :key="v.id" class="version-item">
        <div class="version-item__head">
          <span class="version-no">v{{ v.version_no }}</span>
          <span class="version-time">{{ formatFullDateTime(v.create_time, '') }}</span>
          <el-button size="small" type="primary" plain @click="$emit('restore', v)">回滚到此版本</el-button>
        </div>
        <div class="version-content">{{ v.content }}</div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
import { formatFullDateTime } from '../../utils/format'

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
</script>

<style scoped>
/* 这些规则原先留在 Production.vue 的 scoped style 里，但本组件被拆出来后它们就够不到这里了
   （scoped 样式只能作用到子组件的根元素，而本组件根元素是 el-dialog）。
   结果：历史版本弹窗一直是裸样式。阶段 D 的 D2 把它们归还给真正的宿主。 */
.empty-tip { text-align: center; color: var(--text-tertiary); font-size: 13px; }

.version-list { display: flex; flex-direction: column; gap: 10px; max-height: 60vh; overflow-y: auto; }
.version-item { border: 1px solid var(--border-light); border-radius: 10px; padding: 10px 12px; }
.version-item__head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.version-no { font-weight: 700; color: var(--brand-600); }
.version-time { font-size: 12px; color: var(--text-tertiary); flex: 1; }
.version-content {
  font-size: 13px; color: var(--text-secondary); white-space: pre-wrap;
  max-height: 160px; overflow-y: auto; line-height: 1.6;
}
</style>
