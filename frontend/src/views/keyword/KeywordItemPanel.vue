<template>
  <!-- 保留 item-panel 这个类名：shot-knowledge.mjs 的断言按 `.item-panel .vtable .kw-row` 取数 -->
  <div class="item-panel kw-panel" v-loading="loading">
    <div class="kw-panel-head">
      <div class="head-left">
        <span class="kw-panel-title">关键词列表</span>
        <el-tag size="small" type="info" round>{{ displayKeywords.length }}</el-tag>
      </div>
      <div class="head-right">
        <el-select v-model="sortBy" size="small" class="kw-sort" style="width: 128px">
          <el-option label="默认顺序" value="default" />
          <el-option label="按关键词" value="word" />
          <el-option label="按优先级" value="priority" />
          <el-option label="按类型" value="type" />
          <el-option label="按关联产品" value="related_product" />
        </el-select>
        <el-button size="small" :icon="sortDir === 'asc' ? SortUp : SortDown"
                   :disabled="sortBy === 'default'"
                   :title="sortDir === 'asc' ? '升序' : '降序'"
                   @click="sortDir = sortDir === 'asc' ? 'desc' : 'asc'">
          {{ sortDir === 'asc' ? '升序' : '降序' }}
        </el-button>
        <el-select v-model="filterType" placeholder="全部类型" clearable size="small" style="width: 124px;">
          <el-option v-for="o in KEYWORD_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </div>
    </div>
    <div class="kw-toolbar">
      <el-input v-model="search" placeholder="查找关键词 / 关联产品 / 标签..." size="small" :prefix-icon="Search" clearable style="flex: 1;" />
      <el-button size="small" :icon="Operation" :type="batchMode ? 'primary' : 'default'" @click="batchMode = !batchMode">
        {{ batchMode ? '退出批量' : '批量管理' }}
      </el-button>
    </div>
    <!-- 关键词列表（窗口化虚拟滚动） -->
    <div class="vtable" :class="{ batch: batchMode }">
      <div class="kw-grid vtable__head">
        <div class="kw-cell sel">
          <el-checkbox v-if="batchMode" :model-value="selection.length === displayKeywords.length && displayKeywords.length > 0" @change="toggleSelectAll" />
        </div>
        <div class="kw-cell">关键词</div>
        <div class="kw-cell">分组</div>
        <div class="kw-cell">类型</div>
        <div class="kw-cell">优先级</div>
        <div class="kw-cell">关联产品</div>
        <div class="kw-cell">标签</div>
        <div class="kw-cell">操作</div>
      </div>
      <VirtualList
        class="vtable__body"
        :items="displayKeywords"
        :row-height="52"
        :gap="0"
        :focus-id="focusId"
        :get-key="(it) => it.id"
        #default="{ item, index }"
      >
        <div class="kw-grid kw-row" :class="[index % 2 === 1 ? 'striped' : '', 'focus-row-' + item.id]" :data-focus-id="item.id">
          <div class="kw-cell sel">
            <el-checkbox v-if="batchMode" :model-value="selection.includes(item.id)" @change="() => toggleSelect(item)" />
          </div>
          <div class="kw-cell"><span class="kw-word">{{ item.word }}</span></div>
          <div class="kw-cell">
            <span v-if="groupNameOf(item.group_id)" class="kw-group-tag">
              <span class="kw-group-dot" :style="{ background: groupColorOf(item.group_id) }"></span>{{ groupNameOf(item.group_id) }}
            </span>
            <span v-else class="kw-group-none">未分组</span>
          </div>
          <div class="kw-cell">
            <el-tag size="small" :type="keywordTypeTag(item.type)" effect="light">{{ keywordTypeLabel(item.type) }}</el-tag>
          </div>
          <div class="kw-cell">
            <el-rate :model-value="item.priority" disabled size="small" />
          </div>
          <div class="kw-cell kw-ellipsis">{{ item.related_product || '—' }}</div>
          <div class="kw-cell kw-ellipsis">{{ item.tags || '—' }}</div>
          <div class="kw-cell kw-actions">
            <el-button text size="small" :icon="Edit" @click="emit('edit', item)">编辑</el-button>
            <el-button text size="small" type="danger" :icon="Delete" @click="remove(item)">删除</el-button>
          </div>
        </div>
      </VirtualList>
    </div>
    <!-- 批量操作条 -->
    <div v-if="batchMode && selection.length" class="batch-bar">
      <span class="batch-count">已选 <b>{{ selection.length }}</b> 个</span>
      <span class="batch-label">改分组：</span>
      <el-select v-model="batchTargetGroup" placeholder="选择分组" size="small" clearable style="width: 160px" @change="onBatchMoveGroup">
        <el-option label="未分组" :value="null" />
        <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
      </el-select>
      <el-button size="small" type="danger" :icon="Delete" :loading="batchSubmitting" @click="onBatchDelete">删除</el-button>
      <el-button size="small" @click="clearSelection">取消选择</el-button>
    </div>
    <EmptyState v-if="!loading && displayKeywords.length === 0" title="暂无关键词" size="small" icon="Key" />
  </div>
</template>

<script setup>
/**
 * 关键词库右栏：工具条（搜索 / 排序 / 类型筛选）+ 虚拟滚动表格 + 批量操作条。
 *
 * 分工（照 knowledge/ItemPanel 的范式）：
 *   - **条目级动作自己干**（删除、批量改分组、批量删除、排序/筛选状态），完成后 emit `changed`
 *     让壳重新拉数；
 *   - **弹窗类动作只 emit 意图**（`edit`），由壳决定用哪个组件打开。
 */
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Delete, Search, Operation, SortUp, SortDown } from '@element-plus/icons-vue'
import { keywordApi } from '../../api'
import { KEYWORD_TYPE_OPTIONS, keywordTypeLabel, keywordTypeTag } from '../../constants/status'
import EmptyState from '../../components/EmptyState.vue'
import VirtualList from '../../components/VirtualList.vue'
import './keyword-shared.css'

const props = defineProps({
  keywords: { type: Array, default: () => [] },
  groups: { type: Array, default: () => [] },
  /** null=全部, -1=未分组, 否则 group_id */
  activeGroup: { type: [Number, String], default: null },
  loading: { type: Boolean, default: false },
  focusId: { type: [String, Number], default: null },
})
const emit = defineEmits(['edit', 'changed'])

// ========== 排序 / 筛选 / 搜索 ==========
const search = ref('')
const sortBy = ref('default') // default/word/priority/type/related_product
const sortDir = ref('asc') // asc/desc
const filterType = ref('')

// 分组查找（只服务于本表格的「分组」列）
function groupById(id) { return props.groups.find((g) => g.id === id) }
function groupNameOf(id) { return groupById(id)?.name || '' }
function groupColorOf(id) { return groupById(id)?.color || '#6366f1' }

const displayKeywords = computed(() => {
  let arr = props.keywords
  if (props.activeGroup === -1) {
    arr = arr.filter((k) => k.group_id == null)
  } else if (props.activeGroup != null) {
    arr = arr.filter((k) => k.group_id === props.activeGroup)
  }
  if (filterType.value) arr = arr.filter((k) => k.type === filterType.value)
  const q = (search.value || '').trim().toLowerCase()
  if (q) {
    arr = arr.filter((k) =>
      (k.word || '').toLowerCase().includes(q) ||
      (k.related_product || '').toLowerCase().includes(q) ||
      (k.tags || '').toLowerCase().includes(q)
    )
  }
  const by = sortBy.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  if (by !== 'default') {
    arr = [...arr].sort((a, b) => {
      if (by === 'priority') return (a.priority - b.priority) * dir
      const va = (a[by] || '').toString()
      const vb = (b[by] || '').toString()
      return va.localeCompare(vb, 'zh-CN') * dir
    })
  }
  return arr
})

// ========== 批量操作 ==========
const batchMode = ref(false)
const selection = ref([])
const batchTargetGroup = ref(null)
const batchSubmitting = ref(false)

function toggleSelect(item) {
  const i = selection.value.indexOf(item.id)
  if (i >= 0) selection.value.splice(i, 1)
  else selection.value.push(item.id)
}
function toggleSelectAll(val) {
  selection.value = val ? displayKeywords.value.map((k) => k.id) : []
}
function clearSelection() { selection.value = [] }

async function onBatchMoveGroup(val) {
  const ids = selection.value
  if (!ids.length) return
  batchSubmitting.value = true
  try {
    await keywordApi.batchGroup({ ids, group_id: val })
    ElMessage.success(`已将 ${ids.length} 个关键词移到「${val == null ? '未分组' : (groupNameOf(val) || '未分组')}」`)
    batchTargetGroup.value = null
    clearSelection()
    emit('changed')
  } finally { batchSubmitting.value = false }
}

async function onBatchDelete() {
  const ids = selection.value
  if (!ids.length) return
  await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 个关键词吗？`, '批量删除', { type: 'warning' })
  batchSubmitting.value = true
  try {
    await keywordApi.batchDelete({ ids })
    ElMessage.success(`已删除 ${ids.length} 个关键词`)
    clearSelection()
    emit('changed')
  } finally { batchSubmitting.value = false }
}

async function remove(item) {
  await ElMessageBox.confirm(`确定删除关键词「${item.word}」吗？`, '提示', { type: 'warning' })
  await keywordApi.delete(item.id)
  ElMessage.success('删除成功')
  emit('changed')
}
</script>

<style scoped>
.head-left { display: flex; align-items: center; gap: 8px; }
.head-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.kw-sort { flex-shrink: 0; }
.kw-toolbar {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; border-bottom: 1px solid var(--border-light);
  flex-wrap: wrap;
}

/* 关键词窗口化虚拟滚动表格 */
.vtable { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.vtable__body { flex: 1; min-height: 0; }
.vtable__head {
  height: 44px; flex-shrink: 0;
  background: var(--bg-secondary, #f8fafc);
  border-bottom: 1px solid var(--border-light);
  font-size: 13px; font-weight: 600; color: var(--text-secondary);
}
.kw-grid {
  display: grid;
  grid-template-columns: 0 160px 130px 110px 100px minmax(140px, 1.2fr) minmax(140px, 1.2fr) 156px;
  align-items: center;
}
.kw-grid.batch {
  grid-template-columns: 48px 160px 130px 110px 100px minmax(140px, 1.2fr) minmax(140px, 1.2fr) 156px;
}
.kw-row { height: 100%; border-bottom: 1px solid var(--border-light); }
.kw-row.striped { background: rgba(148, 163, 184, 0.08); }
.kw-row:hover { background: rgba(99, 102, 241, 0.06); }
.kw-cell { padding: 0 14px; font-size: 13px; color: var(--text-secondary); overflow: hidden; min-width: 0; }
.kw-cell.sel { display: flex; align-items: center; justify-content: center; overflow: hidden; }
.kw-cell.kw-actions { display: flex; gap: 2px; justify-content: flex-start; padding: 0 8px; }
.kw-actions .el-button { flex-shrink: 0; white-space: nowrap; }
.kw-actions .el-button:not(.el-button--danger):hover { color: var(--brand-600); background: var(--brand-50); }
.kw-actions .el-button--danger { color: #f56c6c; font-weight: 600; }
.kw-actions .el-button--danger:hover { color: #f56c6c; background: #fef2f2; }
.kw-word { font-weight: 600; color: var(--text-primary); display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kw-ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kw-group-tag { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-secondary); }
.kw-group-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.kw-group-none { font-size: 13px; color: var(--text-tertiary); }

.batch-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 16px; margin-top: 10px;
  background: var(--brand-50); border: 1px solid var(--brand-200, #c7d2fe);
  border-radius: var(--radius-md);
}
.batch-count { font-size: 13px; color: var(--text-secondary); }
.batch-count b { color: var(--brand-600); }
.batch-label { font-size: 13px; color: var(--text-secondary); }
</style>
