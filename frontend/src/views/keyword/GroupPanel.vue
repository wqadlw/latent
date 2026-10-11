<template>
  <!-- 保留 group-panel 这个类名：shot-knowledge.mjs 的断言按 `.group-panel .group-item` 取数 -->
  <div class="group-panel kw-panel">
    <div class="kw-panel-head">
      <span class="kw-panel-title">分组</span>
      <el-button size="small" type="primary" link :icon="Plus" @click="emit('create')">新建分组</el-button>
    </div>
    <transition-group name="cat-list" tag="div" class="group-list">
      <div
        class="group-item"
        key="__all__"
        :class="{ 'is-active': activeGroup === null }"
        @click="emit('update:activeGroup', null)"
      >
        <el-icon><Collection /></el-icon>
        <span>全部</span>
        <el-tag size="small" round>{{ totalCount }}</el-tag>
      </div>
      <div
        v-for="g in groups"
        :key="g.id"
        class="group-item"
        :class="{ 'is-active': activeGroup === g.id }"
        draggable="true"
        @click="emit('update:activeGroup', g.id)"
        @dragstart="onDragStart(g, $event)"
        @dragover.prevent="onDragOver($event)"
        @drop="onDrop(g)"
      >
        <el-icon class="group-drag" title="拖拽排序"><Rank /></el-icon>
        <el-icon class="group-icon" :style="{ color: g.color || '#6366f1' }"><component :is="groupIconOf(g)" /></el-icon>
        <span class="group-name">{{ g.name }}</span>
        <el-tag size="small" round>{{ g.item_count }}</el-tag>
        <div class="group-actions" @click.stop>
          <el-button text size="small" :icon="Edit" title="编辑分组" @click="emit('edit', g)" />
          <el-button text size="small" type="danger" :icon="Delete" title="删除分组" @click="emit('remove', g)" />
        </div>
      </div>
      <div
        v-if="uncategorizedCount > 0"
        class="group-item"
        key="__uncat__"
        :class="{ 'is-active': activeGroup === -1 }"
        @click="emit('update:activeGroup', -1)"
      >
        <el-icon class="group-icon" style="color:#94a3b8"><Document /></el-icon>
        <span class="group-name">未分组</span>
        <el-tag size="small" round>{{ uncategorizedCount }}</el-tag>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
/**
 * 关键词库左栏：分组列表（含「全部」「未分组」两个虚拟项 + 拖拽排序）。
 *
 * 不直接改共享状态：选中走 `update:activeGroup`，增删改走 `edit`/`remove`/`create`。
 * 拖拽排序是它自己的交互，但它改的是壳里的 `groups`，所以先 emit 新数组（界面立刻响应），
 * 再自己发排序请求 —— 与 knowledge/ItemPanel 的 `items-reordered` 同一套路。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Edit, Delete, Collection, Document, Rank, Folder } from '@element-plus/icons-vue'
import { keywordGroupApi } from '../../api'
import { ICON_MAP } from '../../constants/icons'
import './keyword-shared.css'

const props = defineProps({
  groups: { type: Array, default: () => [] },
  activeGroup: { type: [Number, String], default: null },
  totalCount: { type: Number, default: 0 },
  uncategorizedCount: { type: Number, default: 0 },
})
const emit = defineEmits(['update:activeGroup', 'create', 'edit', 'remove', 'reordered'])

// 分组图标真源在 constants/icons.js（原先与 Knowledge.vue 各存一份，且已经漂移）
function groupIconOf(g) { return ICON_MAP[g?.icon] || Folder }

// ========== 拖拽排序 ==========
const dragGroupId = ref(null)

function onDragStart(g, e) {
  dragGroupId.value = g.id
  if (e.dataTransfer) { e.dataTransfer.effectAllowed = 'move' }
}
function onDragOver(e) { e.dataTransfer.dropEffect = 'move' }

async function onDrop(target) {
  const from = dragGroupId.value
  dragGroupId.value = null
  if (from == null || from === target.id) return
  const fromIdx = props.groups.findIndex((g) => g.id === from)
  const toIdx = props.groups.findIndex((g) => g.id === target.id)
  if (fromIdx < 0 || toIdx < 0) return
  const arr = [...props.groups]
  const [moved] = arr.splice(fromIdx, 1)
  arr.splice(toIdx, 0, moved)
  emit('reordered', arr)
  try {
    await keywordGroupApi.sort(arr.map((g, i) => ({ id: g.id, sort: i })))
    ElMessage.success('分组顺序已更新')
  } catch {
    ElMessage.error('分组排序失败')
  }
}
</script>

<style scoped>
.group-list { flex: 1; overflow-y: auto; padding: 8px; position: relative; }
.group-item {
  position: relative;
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.16s, transform 0.16s;
  font-size: 13px;
  color: var(--text-secondary);
}
.group-item::before {
  content: '';
  position: absolute; left: 0; top: 50%;
  width: 3px; height: 0;
  background: var(--brand-500, #6366f1);
  border-radius: 0 3px 3px 0;
  transform: translateY(-50%);
  transition: height 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.group-item:hover { background: var(--slate-50); transform: translateX(2px); }
.group-item.is-active { background: var(--brand-50); color: var(--brand-600); font-weight: 600; }
.group-item.is-active::before { height: 60%; }
.group-item span { flex: 1; }
.group-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.group-icon { font-size: 16px; flex-shrink: 0; }
.group-actions { display: none; align-items: center; gap: 0; flex-shrink: 0; }
.group-item:hover .group-actions { display: flex; }
.group-actions .el-button { padding: 2px 4px; margin-left: 2px; }
.group-drag { font-size: 14px; color: var(--text-tertiary); cursor: grab; opacity: 0; transition: opacity 0.15s; flex-shrink: 0; }
.group-item:hover .group-drag { opacity: 1; }
.group-item[draggable="true"] { cursor: grab; }
.group-item.dragging { opacity: 0.4; }

/* 分组列表增删/重排动画 */
.cat-list-enter-active, .cat-list-leave-active { transition: all 0.25s ease; }
.cat-list-enter-from { opacity: 0; transform: translateX(-12px); }
.cat-list-leave-to { opacity: 0; transform: translateX(12px); }
.cat-list-move { transition: transform 0.25s ease; }
.cat-list-leave-active { position: absolute; width: calc(100% - 16px); }
</style>
