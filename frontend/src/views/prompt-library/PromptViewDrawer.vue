<template>
  <el-drawer :model-value="modelValue" :title="item?.name || '提示词详情'" size="640px" direction="rtl"
    @update:model-value="$emit('update:modelValue', $event)">
    <div class="view-content" v-if="item">
      <div class="view-meta">
        <el-tag size="small" :style="{ background: color + '22', color, border: 'none' }">{{ categoryName }}</el-tag>
        <el-tag v-if="item.is_default" size="small" type="warning" effect="dark">默认</el-tag>
        <el-tag v-if="item.tags" size="small" effect="plain">{{ item.tags }}</el-tag>
        <el-tag v-if="item.usage_count" size="small" type="info" effect="plain">用 {{ item.usage_count }} 次</el-tag>
      </div>
      <div class="view-desc" v-if="item.description">{{ item.description }}</div>
      <div class="view-vars" v-if="variables.length">
        <span class="view-vars-label">变量：</span>
        <el-tag v-for="v in variables" :key="v" size="small" effect="plain" type="info" class="var-tag">{{ '{' + v + '}' }}</el-tag>
      </div>
      <div class="view-body-label"><el-icon><Memo /></el-icon> 提示词全文</div>
      <div class="view-body-text">{{ item.content || '（空）' }}</div>
      <div class="view-foot">
        <el-button type="primary" :icon="CopyDocument" @click="$emit('copy', item)">复制全文</el-button>
        <el-button :icon="Edit" @click="$emit('edit', item)">编辑</el-button>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { CopyDocument, Edit, Memo } from '@element-plus/icons-vue'
import './prompt-library-shared.css'

/**
 * 提示词「只读查看」抽屉。
 *
 * 关闭自己（复制/编辑后）这件事交给父组件：抽屉只发事件，
 * 由父决定「复制完要不要顺手关掉抽屉」——这个决定属于页面编排，不属于抽屉。
 */
defineProps({
  modelValue: { type: Boolean, default: false },
  item: { type: Object, default: null },
  color: { type: String, default: '#94a3b8' },
  categoryName: { type: String, default: '' },
  variables: { type: Array, default: () => [] },
})
defineEmits(['update:modelValue', 'copy', 'edit'])
</script>
