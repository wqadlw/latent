<template>
  <div class="step-pane">
    <StepHeader :no="1" title="选择行业" desc="确定本篇软文所属行业" />
    <div class="options-grid">
      <div
        v-for="ind in industries"
        :key="ind.id"
        class="option-card"
        :class="{ selected: selectedId === ind.id }"
        @click="$emit('select', ind)"
      >
        <el-icon :size="24" color="#6366f1"><OfficeBuilding /></el-icon>
        <div class="option-name">{{ ind.name }}</div>
        <div class="option-desc">{{ ind.description || '点击选择此行业' }}</div>
        <el-icon v-if="selectedId === ind.id" class="check-mark"><CircleCheckFilled /></el-icon>
      </div>
    </div>
  </div>
</template>

<script setup>
import StepHeader from '../../../components/production/StepHeader.vue'
import { OfficeBuilding, CircleCheckFilled } from '@element-plus/icons-vue'

defineProps({
  industries: { type: Array, default: () => [] },
  selectedId: { type: Number, default: null },
})
defineEmits(['select'])
</script>
