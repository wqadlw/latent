<template>
  <el-drawer v-model="visible" size="520px" :title="item?.title || '详情'">
    <div v-if="item" class="detail-content">
      <div class="detail-meta">
        <el-tag :color="categoryColorOf(categories, item.category_id)" effect="dark" style="border: none;">
          {{ categoryNameOf(categories, item.category_id) }}
        </el-tag>
        <el-tag v-if="item.importance === 'high'" type="warning" effect="dark">
          <el-icon><StarFilled /></el-icon> 高重要性
        </el-tag>
        <el-tag v-if="item.status === 'draft'" type="info">草稿</el-tag>
      </div>
      <div v-if="item.summary" class="detail-section">
        <div class="detail-label">摘要</div>
        <div class="detail-text detail-summary">{{ item.summary }}</div>
      </div>
      <div class="detail-section">
        <div class="detail-label">内容</div>
        <div class="detail-text detail-body">{{ item.content || '暂无内容' }}</div>
      </div>
      <div v-if="item.tags" class="detail-section">
        <div class="detail-label">标签</div>
        <div class="detail-tags">
          <el-tag v-for="t in parseTags(item.tags)" :key="t" size="small" effect="plain">{{ t }}</el-tag>
        </div>
      </div>
      <div class="detail-section detail-info-grid">
        <div v-if="item.source" class="info-item">
          <span class="info-label">来源</span>
          <span class="info-value">{{ item.source }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">查看次数</span>
          <span class="info-value">{{ item.view_count || 0 }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">创建时间</span>
          <span class="info-value">{{ formatFullDateTime(item.create_time) }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">更新时间</span>
          <span class="info-value">{{ formatFullDateTime(item.update_time) }}</span>
        </div>
      </div>
    </div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" :icon="Edit" @click="onEdit">编辑</el-button>
    </template>
  </el-drawer>
</template>

<script setup>
/**
 * 知识库 —— 知识点详情抽屉。
 *
 * 打开时自己去取一次详情（列表里的是摘要数据，详情接口会顺带把 view_count 加一）。
 * 取回后 emit `loaded` 把最新数据交给父组件，父组件据此同步列表里的查看次数 ——
 * 这样「谁负责取数」和「谁负责改列表」各归各位，不用父组件反向操作子组件内部状态。
 */
import { ref } from 'vue'
import { Edit, StarFilled } from '@element-plus/icons-vue'
import { knowledgeApi } from '../../api'
import { formatFullDateTime } from '../../utils/format'
import { parseTags, categoryNameOf, categoryColorOf } from './shared'

defineProps({
  /** 分类列表（父组件持有），用于把 category_id 显示成名字与颜色 */
  categories: { type: Array, default: () => [] },
})

const emit = defineEmits(['edit', 'loaded'])

const visible = ref(false)
const item = ref(null)

async function open(row) {
  item.value = row
  visible.value = true
  try {
    const res = await knowledgeApi.getItem(row.id)
    item.value = res.data
    emit('loaded', res.data)
  } catch {
    // 取详情失败就继续显示列表里那份，不打断阅读
  }
}

function onEdit() {
  visible.value = false
  emit('edit', item.value)
}

defineExpose({ open })
</script>

<style scoped>
.detail-content { padding: 0 4px; }
.detail-meta { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
.detail-section { margin-bottom: 20px; }
.detail-label { font-size: 12px; color: var(--text-tertiary); margin-bottom: 8px; font-weight: 600; }
.detail-text { font-size: 14px; color: var(--text-primary); line-height: 1.8; }
.detail-summary { color: var(--text-secondary); font-style: italic; padding: 10px 12px; background: var(--slate-50); border-radius: var(--radius-md); border-left: 3px solid var(--brand-400); }
.detail-body { white-space: pre-wrap; word-break: break-word; }
.detail-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.detail-info-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
  padding: 12px; background: var(--slate-50); border-radius: var(--radius-md);
}
.info-item { display: flex; flex-direction: column; gap: 2px; }
.info-label { font-size: 11px; color: var(--text-tertiary); }
.info-value { font-size: 13px; color: var(--text-primary); }
</style>
