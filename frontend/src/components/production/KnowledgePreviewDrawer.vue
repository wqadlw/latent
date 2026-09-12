<template>
  <el-drawer v-model="visible" title="知识点详情" size="480px" direction="rtl">
    <div v-if="item" class="preview-detail">
      <h3 class="pd-title">{{ item.title }}</h3>
      <div v-if="item.summary" class="pd-summary">{{ item.summary }}</div>
      <div class="pd-meta">
        <el-tag v-if="item.importance === 'high'" size="small" type="danger">高重要性</el-tag>
        <el-tag v-else size="small" type="info">普通</el-tag>
        <span v-if="item.source" class="pd-source">来源：{{ item.source }}</span>
      </div>
      <div v-if="item.tags" class="pd-tags">
        <el-tag v-for="t in item.tags.split(',').filter(Boolean)" :key="t" size="small" effect="plain">{{ t.trim() }}</el-tag>
      </div>
      <div class="pd-content">{{ item.content }}</div>
      <div class="pd-actions">
        <el-button type="primary" @click="$emit('toggle', item.id)">
          {{ isSelected ? '取消选择' : '加入选择' }}
        </el-button>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  item: { type: Object, default: null },
  isSelected: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'toggle'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
</script>
