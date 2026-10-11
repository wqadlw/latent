<template>
  <div class="prompt-item" :data-focus-id="item.id" :style="{ '--cat-color': color }">
    <div class="prompt-item__main">
      <div class="prompt-item__header">
        <span class="prompt-item__avatar" :style="{ background: 'color-mix(in srgb, var(--cat-color) 14%, transparent)', color: 'var(--cat-color)' }">
          <el-icon><component :is="icon || Document" /></el-icon>
        </span>
        <span class="prompt-item__name">{{ item.name }}</span>
        <div class="prompt-item__badges">
          <el-tag v-if="item.is_default" size="small" type="warning" effect="dark">默认</el-tag>
          <el-rate v-if="item.rating" :model-value="item.rating" disabled size="small" />
          <el-tag v-if="item.usage_count" size="small" type="info" effect="plain">
            <el-icon><TrendCharts /></el-icon> {{ item.usage_count }}
          </el-tag>
        </div>
      </div>
      <div class="prompt-item__desc">{{ item.description || '暂无描述' }}</div>
      <div class="prompt-item__preview">
        <span class="prompt-item__preview-label"><el-icon><Memo /></el-icon> 提示词内容</span>
        <div class="prompt-item__preview-text">{{ (item.content || '').slice(0, 220) }}{{ (item.content || '').length > 220 ? '…' : '' }}</div>
      </div>
      <div class="prompt-item__vars" v-if="variables.length">
        <el-tag v-for="v in variables.slice(0, 6)" :key="v" size="small" effect="plain" type="info" class="var-tag">{{ '{' + v + '}' }}</el-tag>
        <span v-if="variables.length > 6" class="var-more">+{{ variables.length - 6 }}</span>
      </div>
      <div class="prompt-item__meta">
        <span><el-icon><Clock /></el-icon> {{ formatShortDate(item.update_time) }}</span>
        <span v-if="item.tags"><el-icon><PriceTag /></el-icon> {{ item.tags }}</span>
      </div>
    </div>
    <div class="prompt-item__actions">
      <el-button text size="small" :icon="View" @click="$emit('view', item)">查看</el-button>
      <el-button text size="small" :icon="CopyDocument" @click="$emit('copy', item)">复制</el-button>
      <el-button text size="small" :icon="DocumentCopy" @click="$emit('duplicate', item)">克隆</el-button>
      <el-button text size="small" :icon="Edit" @click="$emit('edit', item)">编辑</el-button>
      <el-button text size="small" type="danger" :icon="Delete" @click="$emit('remove', item)">删除</el-button>
    </div>
  </div>
</template>

<script setup>
import { Clock, CopyDocument, Delete, Document, DocumentCopy, Edit, Memo, PriceTag, TrendCharts, View } from '@element-plus/icons-vue'
import { formatShortDate } from '../../utils/format'
import './prompt-library-shared.css'

/**
 * 提示词库的一张卡片。
 *
 * 设计约定：**卡片只负责显示与转发事件**，不发请求、不弹确认框。
 * 「复制要加使用次数」「删除要二次确认」这类业务动作留在视图里 ——
 * 卡片一旦自己发请求，就没法在列表外复用它，也没法统一处理错误。
 *
 * 分类色 / 分类图标由父组件查好传进来（`color` / `icon`），
 * 卡片不去查 categories —— 那会让每张卡片都持有分类表的引用。
 */
defineProps({
  item: { type: Object, required: true },
  /** 分类色，用于左侧色带与图标底色 */
  color: { type: String, default: '#94a3b8' },
  /** 分类图标组件 */
  icon: { type: [Object, Function], default: null },
  /** 已解析的变量名数组（父组件统一解析，避免卡片里重复 JSON.parse） */
  variables: { type: Array, default: () => [] },
})
defineEmits(['view', 'copy', 'duplicate', 'edit', 'remove'])
</script>
