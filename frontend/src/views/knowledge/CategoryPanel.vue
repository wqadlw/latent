<template>
  <div class="kb-panel category-panel">
    <div class="kb-panel-head">
      <span class="kb-panel-title">分类</span>
      <el-button size="small" type="primary" link @click="emit('create')">新增</el-button>
    </div>
    <transition-group name="cat-list" tag="div" class="category-list">
      <div class="category-item" key="__all__" :class="{ 'is-active': activeCategory === null }" @click="emit('update:activeCategory', null)">
        <el-icon><Files /></el-icon>
        <span>全部</span>
        <el-tag size="small" round>{{ totalCount }}</el-tag>
      </div>
      <div
        v-for="c in categories"
        :key="c.id"
        class="category-item"
        :class="{ 'is-active': activeCategory === c.id }"
        @click="emit('update:activeCategory', c.id)"
      >
        <el-icon :style="{ color: c.color || '#6366f1' }"><component :is="ICON_MAP[c.icon] || Folder" /></el-icon>
        <span class="category-name">{{ c.name }}</span>
        <el-tag size="small" round>{{ c.item_count }}</el-tag>
        <div class="category-actions" @click.stop>
          <el-button text size="small" :icon="Edit" title="编辑分类" @click="emit('edit', c)" />
          <el-button text size="small" type="danger" :icon="Delete" title="删除分类" @click="emit('remove', c)" />
        </div>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
/**
 * 知识库 —— 左侧分类面板。
 *
 * 纯展示 + 意图上抛：它不改任何数据，也不发请求。选中态用 `update:activeCategory`
 * 回传，父组件用 `v-model:active-category` 接住 —— 因为「当前选中分类」还要给
 * 知识点列表和批量导入用，不能锁在这个面板里。
 */
import { Files, Folder, Edit, Delete } from '@element-plus/icons-vue'
import { ICON_MAP } from '../../constants/icons'
import '../knowledge/knowledge-shared.css'

defineProps({
  /** 分类列表 */
  categories: { type: Array, default: () => [] },
  /** 当前选中分类 id；null = 全部 */
  activeCategory: { type: [Number, String], default: null },
  /** 「全部」后面的总数 */
  totalCount: { type: Number, default: 0 },
})

const emit = defineEmits(['update:activeCategory', 'create', 'edit', 'remove'])
</script>

<style scoped>
.category-panel { position: sticky; top: 16px; align-self: start; max-height: calc(100vh - 32px); }
.category-list { flex: 1; overflow-y: auto; padding: 8px; position: relative; }
.category-item {
  position: relative;
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  transition: background 0.22s ease, color 0.22s ease, transform 0.18s cubic-bezier(.34, 1.4, .64, 1);
}
/* 激活态左侧指示条（弹性出现动画） */
.category-item::before {
  content: '';
  position: absolute; left: 0; top: 50%;
  width: 3px; height: 56%;
  border-radius: 0 3px 3px 0;
  background: var(--brand-500);
  transform: translateY(-50%) scaleY(0);
  transform-origin: center;
  opacity: 0;
  transition: transform 0.26s cubic-bezier(.34, 1.56, .64, 1), opacity 0.2s ease;
}
.category-item:hover { background: var(--slate-50); transform: translateX(2px); }
.category-item.is-active {
  background: var(--brand-50); color: var(--brand-600); font-weight: 600;
  transform: translateX(2px);
}
.category-item.is-active::before { transform: translateY(-50%) scaleY(1); opacity: 1; }
.category-item span { flex: 1; }
.category-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.category-actions {
  display: none;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
}
.category-item:hover .category-actions { display: flex; }
.category-actions .el-button { padding: 2px 4px; margin-left: 2px; }

/* 分类增删 / 重排动画 */
.cat-list-enter-active, .cat-list-leave-active { transition: all 0.3s cubic-bezier(.34, 1.4, .64, 1); }
.cat-list-enter-from { opacity: 0; transform: translateX(-14px) scale(0.96); }
.cat-list-leave-to { opacity: 0; transform: translateX(14px) scale(0.96); }
.cat-list-leave-active { position: absolute; width: calc(100% - 16px); }
.cat-list-move { transition: transform 0.3s cubic-bezier(.34, 1.4, .64, 1); }
</style>
