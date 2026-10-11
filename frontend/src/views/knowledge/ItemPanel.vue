<template>
  <div class="kb-panel item-panel">
    <div class="kb-panel-head">
      <div class="head-left">
        <span class="kb-panel-title">知识点列表</span>
        <el-tag v-if="activeCategory" size="small" type="info" closable @close="emit('update:activeCategory', null)">
          {{ categoryNameOf(categories, activeCategory) }}
        </el-tag>
      </div>
      <div class="head-right">
        <el-input v-model="search" placeholder="搜索标题/内容/标签..." :prefix-icon="Search" size="small" clearable style="width: 240px" />
        <el-select v-model="sortBy" size="small" class="k-sort" style="width: 132px">
          <el-option label="默认顺序" value="default" />
          <el-option label="按重要度" value="importance" />
          <el-option label="按更新时间" value="update_time" />
          <el-option label="按名称" value="title" />
          <el-option label="按来源" value="source" />
          <el-option label="自定义（拖拽）" value="custom" />
        </el-select>
        <el-tooltip :content="sortDir === 'asc' ? '当前升序，点击切换为降序' : '当前降序，点击切换为升序'">
          <el-button
            size="small"
            :icon="sortDir === 'asc' ? SortUp : SortDown"
            :disabled="sortBy === 'default' || sortBy === 'custom'"
            @click="toggleSortDir"
          >{{ sortDir === 'asc' ? '升序' : '降序' }}</el-button>
        </el-tooltip>
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="grid"><el-icon><Grid /></el-icon></el-radio-button>
          <el-radio-button value="list"><el-icon><List /></el-icon></el-radio-button>
        </el-radio-group>
        <el-button size="small" :icon="Operation" :type="batchMode ? 'primary' : 'default'" @click="batchMode = !batchMode">
          {{ batchMode ? '退出批量' : '批量管理' }}
        </el-button>
      </div>
    </div>

    <!-- 标签过滤 -->
    <div v-if="allTags.length" class="tag-filter-bar">
      <span class="tag-filter-label">标签：</span>
      <el-tag
        v-for="tag in allTags"
        :key="tag"
        :type="activeTags.includes(tag) ? 'primary' : 'info'"
        :effect="activeTags.includes(tag) ? 'dark' : 'plain'"
        size="small"
        class="tag-chip"
        @click="toggleTag(tag)"
      >{{ tag }}</el-tag>
      <el-button v-if="activeTags.length" text size="small" type="danger" @click="activeTags = []">清除</el-button>
    </div>

    <div
      v-loading="loading"
      class="item-list"
      :class="[viewMode, { 'is-batch': batchMode }]"
    >
      <template v-if="viewMode === 'grid'">
        <div
          v-for="item in filteredList"
          :key="item.id"
          class="item-card"
          :data-focus-id="item.id"
          :class="{ 'is-selected': batchMode && selectedItems.includes(item.id), 'is-dragging': dragItemId === item.id }"
          :draggable="sortBy === 'custom'"
          @click="batchMode ? toggleItemSelect(item) : emit('detail', item)"
          @dragstart="onItemDragStart(item, $event)"
          @dragover.prevent="onItemDragOver($event)"
          @drop="onItemDrop(item)"
        >
          <el-checkbox v-if="batchMode" class="item-select" :model-value="selectedItems.includes(item.id)" @click.stop @change="() => toggleItemSelect(item)" />
          <el-icon v-if="sortBy === 'custom' && !batchMode" class="item-drag" title="拖拽排序"><Rank /></el-icon>
          <div class="item-card__top">
            <div class="item-card__title-row">
              <el-icon v-if="item.importance === 'high'" class="imp-high"><StarFilled /></el-icon>
              <span class="item-card__title">{{ item.title }}</span>
            </div>
            <div class="item-card__badges">
              <el-tag size="small" :color="categoryColorOf(categories, item.category_id)" effect="light" style="border: none; color: #fff;">
                {{ categoryNameOf(categories, item.category_id) }}
              </el-tag>
              <el-tag v-if="item.status === 'draft'" size="small" type="warning">草稿</el-tag>
            </div>
          </div>
          <div class="item-card__summary">{{ item.summary || item.content || '暂无内容' }}</div>
          <div v-if="item.tags" class="item-card__tags">
            <el-tag v-for="t in parseTags(item.tags)" :key="t" size="small" effect="plain" type="info" class="kw-tag">{{ t }}</el-tag>
          </div>
          <div class="item-card__footer">
            <div class="item-card__meta">
              <span v-if="item.source" class="meta-item"><el-icon><Link /></el-icon>{{ item.source }}</span>
              <span class="meta-item"><el-icon><View /></el-icon>{{ item.view_count || 0 }}</span>
              <span class="meta-item">{{ formatShortDate(item.update_time) }}</span>
            </div>
            <div class="item-card__actions" @click.stop>
              <el-button text size="small" :icon="Edit" @click="emit('edit', item)">编辑</el-button>
              <el-button text size="small" type="danger" :icon="Delete" @click="removeItem(item)">删除</el-button>
            </div>
          </div>
        </div>
      </template>
      <template v-else>
        <div
          v-for="item in filteredList"
          :key="item.id"
          class="item-row"
          :data-focus-id="item.id"
          :class="{ 'is-selected': batchMode && selectedItems.includes(item.id), 'is-dragging': dragItemId === item.id }"
          :draggable="sortBy === 'custom'"
          @click="batchMode ? toggleItemSelect(item) : emit('detail', item)"
          @dragstart="onItemDragStart(item, $event)"
          @dragover.prevent="onItemDragOver($event)"
          @drop="onItemDrop(item)"
        >
          <el-checkbox v-if="batchMode" class="item-select" :model-value="selectedItems.includes(item.id)" @click.stop @change="() => toggleItemSelect(item)" />
          <el-icon v-if="sortBy === 'custom' && !batchMode" class="item-drag" title="拖拽排序"><Rank /></el-icon>
          <div class="item-row__main">
            <div class="item-row__title-row">
              <el-icon v-if="item.importance === 'high'" class="imp-high"><StarFilled /></el-icon>
              <span class="item-row__title">{{ item.title }}</span>
              <el-tag size="small" :color="categoryColorOf(categories, item.category_id)" effect="light" style="border: none; color: #fff;">{{ categoryNameOf(categories, item.category_id) }}</el-tag>
              <el-tag v-if="item.status === 'draft'" size="small" type="warning">草稿</el-tag>
            </div>
            <div class="item-row__summary">{{ item.summary || item.content || '暂无内容' }}</div>
            <div v-if="item.tags" class="item-row__tags">
              <el-tag v-for="t in parseTags(item.tags).slice(0, 5)" :key="t" size="small" effect="plain" type="info">{{ t }}</el-tag>
            </div>
          </div>
          <div class="item-row__meta">
            <span v-if="item.source" class="meta-item"><el-icon><Link /></el-icon>{{ item.source }}</span>
            <span class="meta-item"><el-icon><View /></el-icon>{{ item.view_count || 0 }}</span>
            <span class="meta-item">{{ formatShortDate(item.update_time) }}</span>
          </div>
          <div class="item-row__actions" @click.stop>
            <el-button text size="small" :icon="Edit" @click="emit('edit', item)">编辑</el-button>
            <el-button text size="small" type="danger" :icon="Delete" @click="removeItem(item)">删除</el-button>
          </div>
        </div>
      </template>
    </div>
    <EmptyState v-if="!loading && filteredList.length === 0" title="暂无知识点" desc="点击右上角「新建知识点」开始添加" size="small" icon="Collection" />
    <!-- 批量操作条 -->
    <div v-if="batchMode && selectedItems.length" class="batch-bar">
      <span class="batch-count">已选 <b>{{ selectedItems.length }}</b> 个</span>
      <span class="batch-label">移动分类：</span>
      <el-select v-model="batchTargetCategory" placeholder="选择分类" size="small" clearable style="width: 160px" @change="onBatchMoveCategory">
        <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <span class="batch-label">重要度：</span>
      <el-select v-model="batchTargetImportance" placeholder="设置" size="small" clearable style="width: 120px" @change="onBatchSetImportance">
        <el-option label="高" value="high" />
        <el-option label="中" value="normal" />
        <el-option label="低" value="low" />
      </el-select>
      <el-button size="small" type="danger" :icon="Delete" :loading="batchSubmitting" @click="onBatchDeleteItems">删除</el-button>
      <el-button size="small" @click="clearItemSelection">取消选择</el-button>
    </div>
  </div>
</template>

<script setup>
/**
 * 知识库 —— 右侧知识点列表面板。
 *
 * 这一块为什么整块搬进来而不是继续留在视图里：
 * 搜索 / 排序 / 标签过滤 / 视图切换 / 批量选择 / 拖拽排序 **全部只作用于这个列表**，
 * 它们共享同一份状态（`filteredList` 同时受这五个影响）。留在视图里等于让视图
 * 替列表保管状态；拆成两个组件则要把这份状态在两边来回同步。
 *
 * 边界：
 *   - 列表数据 `items` / 分类 `categories` / 当前分类 `activeCategory` 由父组件传入
 *     （分类与「当前选中分类」是跨面板共享的，不归本组件）。
 *   - 增删改 / 详情 / 拖拽落库后的刷新，一律 `emit` 给父组件去做
 *     （父组件才知道要不要顺带刷分类计数和统计）。
 *   - 批量移动/改重要度/删除是本列表自己的操作，直接在这里发请求，完成后 emit `changed`。
 */
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, Edit, Delete, Grid, List, StarFilled, View, Link,
  Operation, Rank, SortUp, SortDown,
} from '@element-plus/icons-vue'
import { knowledgeApi } from '../../api'
import { formatShortDate } from '../../utils/format'
import EmptyState from '../../components/EmptyState.vue'
import { parseTags, categoryNameOf, categoryColorOf } from './shared'
import '../knowledge/knowledge-shared.css'

const props = defineProps({
  /** 知识点列表（父组件持有，拖拽排序后也会回传给父组件） */
  items: { type: Array, default: () => [] },
  /** 分类列表，用于显示分类名与色带 */
  categories: { type: Array, default: () => [] },
  /** 当前选中分类；null = 全部 */
  activeCategory: { type: [Number, String], default: null },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['update:activeCategory', 'edit', 'detail', 'changed', 'items-reordered'])

const search = ref('')
const viewMode = ref('grid')
const activeTags = ref([])

// ===== 排序 =====
const sortBy = ref('default') // default/importance/update_time/title/source/custom
const sortDir = ref('desc') // asc / desc（默认排序时不生效）
function toggleSortDir() {
  sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
}
function sortItems(list) {
  const arr = [...list]
  if (sortBy.value === 'custom') return arr // 自定义：保持拖拽后的顺序
  const dir = sortDir.value === 'asc' ? 1 : -1
  if (sortBy.value === 'importance') {
    const w = { high: 3, normal: 2, low: 1 }
    arr.sort((a, b) => ((w[b.importance] || 1) - (w[a.importance] || 1)) * dir)
  } else if (sortBy.value === 'update_time') {
    arr.sort((a, b) => (new Date(b.update_time || 0) - new Date(a.update_time || 0)) * dir)
  } else if (sortBy.value === 'title') {
    arr.sort((a, b) => (a.title || '').localeCompare(b.title || '', 'zh-CN') * dir)
  } else if (sortBy.value === 'source') {
    arr.sort((a, b) => {
      const sa = (a.source || '').trim()
      const sb = (b.source || '').trim()
      if (!sa && !sb) return 0
      if (!sa) return 1 // 无来源排最后（不受升降序影响）
      if (!sb) return -1
      return sa.localeCompare(sb, 'zh-CN') * dir
    })
  }
  return arr
}

const allTags = computed(() => {
  const set = new Set()
  props.items.forEach((it) => {
    parseTags(it.tags).forEach((t) => set.add(t))
  })
  return Array.from(set).slice(0, 20)
})

const filteredList = computed(() => {
  const base = props.items.filter((item) => {
    const matchCat = !props.activeCategory || item.category_id === props.activeCategory
    const kw = search.value.toLowerCase()
    const matchSearch = !kw ||
      (item.title || '').toLowerCase().includes(kw) ||
      (item.content || '').toLowerCase().includes(kw) ||
      (item.summary || '').toLowerCase().includes(kw) ||
      (item.tags || '').toLowerCase().includes(kw)
    const matchTag = activeTags.value.length === 0 || parseTags(item.tags).some((t) => activeTags.value.includes(t))
    return matchCat && matchSearch && matchTag
  })
  return sortItems(base)
})

function toggleTag(tag) {
  const idx = activeTags.value.indexOf(tag)
  if (idx >= 0) activeTags.value.splice(idx, 1)
  else activeTags.value.push(tag)
}

// ===== 自定义拖拽排序 =====
const dragItemId = ref(null)
function onItemDragStart(item, e) {
  dragItemId.value = item.id
  if (e.dataTransfer) { e.dataTransfer.effectAllowed = 'move' }
}
function onItemDragOver(e) { e.dataTransfer.dropEffect = 'move' }
async function onItemDrop(target) {
  const from = dragItemId.value
  dragItemId.value = null
  if (from == null || from === target.id) return
  const arr = [...props.items]
  const fromIdx = arr.findIndex((it) => it.id === from)
  const toIdx = arr.findIndex((it) => it.id === target.id)
  if (fromIdx < 0 || toIdx < 0) return
  const [moved] = arr.splice(fromIdx, 1)
  arr.splice(toIdx, 0, moved)
  // 乐观更新：先把新顺序交给父组件渲染，再落库；失败则让父组件重载回滚。
  emit('items-reordered', arr)
  try {
    await knowledgeApi.sortItems(arr.map((it, i) => ({ id: it.id, sort: i })))
    ElMessage.success('顺序已更新')
  } catch {
    ElMessage.error('排序失败')
    emit('changed')
  }
}

// ===== 批量操作 =====
const batchMode = ref(false)
const selectedItems = ref([])
const batchTargetCategory = ref(null)
const batchTargetImportance = ref(null)
const batchSubmitting = ref(false)

function toggleItemSelect(item) {
  const i = selectedItems.value.indexOf(item.id)
  if (i >= 0) selectedItems.value.splice(i, 1)
  else selectedItems.value.push(item.id)
}
function clearItemSelection() {
  selectedItems.value = []
  batchTargetCategory.value = null
  batchTargetImportance.value = null
}
async function onBatchMoveCategory(val) {
  if (val == null) return
  const ids = selectedItems.value
  if (!ids.length) return
  batchSubmitting.value = true
  try {
    await knowledgeApi.batchMoveItems({ ids, category_id: val })
    ElMessage.success(`已移动 ${ids.length} 个知识点`)
    batchTargetCategory.value = null
    emit('changed')
    clearItemSelection()
  } finally { batchSubmitting.value = false }
}
async function onBatchSetImportance(val) {
  if (val == null) return
  const ids = selectedItems.value
  if (!ids.length) return
  batchSubmitting.value = true
  try {
    await knowledgeApi.batchStatusItems({ ids, field: 'importance', value: val })
    ElMessage.success(`已设置 ${ids.length} 个知识点的重要度`)
    batchTargetImportance.value = null
    emit('changed')
    clearItemSelection()
  } finally { batchSubmitting.value = false }
}
async function onBatchDeleteItems() {
  const ids = selectedItems.value
  if (!ids.length) return
  await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 个知识点吗？`, '批量删除', { type: 'warning' })
  batchSubmitting.value = true
  try {
    await knowledgeApi.batchDeleteItems({ ids })
    ElMessage.success(`已删除 ${ids.length} 个知识点`)
    emit('changed')
    clearItemSelection()
  } finally { batchSubmitting.value = false }
}

async function removeItem(item) {
  await ElMessageBox.confirm(`确定删除知识点「${item.title}」吗？`, '提示', { type: 'warning' })
  await knowledgeApi.deleteItem(item.id)
  ElMessage.success('删除成功')
  emit('changed')
}
</script>

<style scoped>
.item-panel { min-width: 0; }
.head-left { display: flex; align-items: center; gap: 8px; }
.head-right { display: flex; align-items: center; gap: 8px; }
.k-sort { flex-shrink: 0; }

.tag-filter-bar {
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-light);
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.tag-filter-label { font-size: 12px; color: var(--text-tertiary); }
.tag-chip { cursor: pointer; }

.item-list { width: 100%; }
.item-list.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 12px;
  align-content: start;
}
.item-list.list { display: flex; flex-direction: column; gap: 10px; }

.item-card {
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--brand-400);
  border-radius: var(--radius-md);
  padding: 16px;
  transition: all 0.18s;
  cursor: pointer;
  display: flex; flex-direction: column;
  gap: 10px;
  background: var(--bg-card);
  position: relative;
}
.item-row {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--brand-400);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  cursor: pointer; transition: all 0.18s;
  position: relative;
}
.item-row:hover { border-color: var(--brand-300); box-shadow: 0 4px 12px rgba(99,102,241,.1); transform: translateY(-1px); }
.item-row.is-selected { border-color: var(--brand-400); box-shadow: 0 0 0 2px rgba(99,102,241,.18); }
.item-row.is-dragging { opacity: .4; }
.item-row__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.item-row__title-row { display: flex; align-items: center; gap: 6px; min-width: 0; }
.item-row__title { font-size: 14px; font-weight: 600; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-row__summary { font-size: 13px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-row__tags { display: flex; gap: 4px; flex-wrap: wrap; }
.item-row__meta { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-tertiary); flex-shrink: 0; }
.item-row__actions { display: flex; gap: 2px; flex-shrink: 0; }
.item-card.is-selected { border-color: var(--brand-400); box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.18); }
.item-card.is-dragging { opacity: 0.4; }
.item-card[draggable="true"] { cursor: grab; }
.item-drag {
  position: absolute; top: 10px; right: 10px;
  font-size: 15px; color: var(--text-tertiary); cursor: grab;
  opacity: 0; transition: opacity 0.15s;
}
.item-card:hover .item-drag { opacity: 1; }
.item-select { position: absolute; top: 10px; right: 10px; }
.batch-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 16px; margin-top: 12px;
  background: var(--brand-50); border: 1px solid var(--brand-200, #c7d2fe);
  border-radius: var(--radius-md);
}
.batch-count { font-size: 13px; color: var(--text-secondary); }
.batch-count b { color: var(--brand-600); }
.batch-label { font-size: 13px; color: var(--text-secondary); }
.item-card:hover {
  border-color: var(--brand-300);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.1);
  transform: translateY(-1px);
}
.item-card__top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.item-card__title-row { display: flex; align-items: center; gap: 4px; flex: 1; min-width: 0; }
.imp-high { color: #f59e0b; flex-shrink: 0; }
.item-card__title {
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.item-card__badges { display: flex; gap: 4px; flex-shrink: 0; }
.item-card__summary {
  font-size: 13px; color: var(--text-secondary); line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  margin: 0; min-height: 0;
}
.item-card__tags { display: flex; gap: 4px; flex-wrap: wrap; margin: 0; }
.kw-tag { max-width: 140px; overflow: hidden; text-overflow: ellipsis; }
.item-card__footer {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding-top: 0; border-top: 1px dashed var(--border-light);
}
.item-card__meta { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-tertiary); overflow: hidden; }
.meta-item { display: flex; align-items: center; gap: 2px; white-space: nowrap; }
.item-card__actions { display: flex; gap: 2px; flex-shrink: 0; }

@media (max-width: 1024px) {
  .item-list.grid { grid-template-columns: 1fr; }
}
</style>
