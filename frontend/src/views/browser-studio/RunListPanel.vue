<template>
  <aside class="run-list">
    <div class="run-list__head">
      <span class="run-list__title">运行（{{ runs.length }}）</span>
      <div class="run-list__ops">
        <el-button size="small" type="primary" :icon="Plus" @click="emit('create')">新建运行</el-button>
        <el-button size="small" :icon="Refresh" @click="emit('refresh')">刷新</el-button>
      </div>
    </div>
    <div class="run-list__items">
      <div
        v-for="r in runs"
        :key="r.id"
        class="run-card"
        :class="{ 'is-active': selectedId === r.id }"
        @click="emit('select', r.id)"
      >
        <div class="run-card__top">
          <span class="run-card__name">{{ r.name }}</span>
          <el-tag :type="statusType(r.status)" size="small" effect="dark">{{ statusLabel(r.status) }}</el-tag>
        </div>
        <div class="run-card__meta">
          <span>{{ platformLabel(r.platform) }}</span>
          <span class="tag-mock">{{ engineLabel(r.ai_engine || (r.mock_doubao ? 'mock' : 'deepseek')) }}</span>
          <span class="tag-mode mode-chip" :class="runModeTag(r).cls">{{ runModeTag(r).text }}</span>
          <span class="run-card__time">{{ formatDateTime(r.create_time) }}</span>
        </div>
        <div class="run-card__geo" v-if="r.geo_score">
          GEO <b :class="r.geo_score >= 70 ? 'good' : 'warn'">{{ r.geo_score }}</b>
        </div>
        <div v-if="r.error" class="run-card__err">{{ r.error }}</div>
      </div>
    </div>
  </aside>
</template>

<script setup>
/**
 * 浏览器工作室 —— 左侧「运行列表」。
 *
 * 纯展示 + 三个动作上抛（选中 / 新建 / 刷新）。它自己不改任何运行状态，
 * 也不碰轮询 —— 那些是壳（BrowserStudio.vue）的事。壳只把 `runs` / `selectedId`
 * 递进来，再把用户意图接回去。
 *
 * 平台名走 `constants/platforms.js` 的 `platformLabel`（单一真源）。
 * 这里曾经在壳里又手写了一份同名函数，是 D2「消除重复实现」的漏网之鱼。
 */
import { Plus, Refresh } from '@element-plus/icons-vue'
import { platformLabel } from '../../constants/platforms'
import { statusLabel, statusType, engineLabel, runModeTag } from '../../constants/browserStudio'
import { formatDateTime } from '../../utils/format'
// `.mode-chip`（模式徽标配色）与 `.pc-tip` 在共享表里，非 scoped。
import './studio-shared.css'

defineProps({
  /** 运行记录列表（壳已过滤掉 is_deleted） */
  runs: { type: Array, default: () => [] },
  /** 当前选中的运行 id，用于高亮 */
  selectedId: { type: [Number, String], default: 0 },
})

const emit = defineEmits(['select', 'create', 'refresh'])
</script>

<style scoped>
/* 栏宽（300px）由 WorkbenchLayout 的 aside-width 声明 —— 布局决策归布局容器，
   面板只管自己的内部结构。D7-2 之前这里是 width:300px + flex-shrink:0。 */
.run-list { background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-lg); display: flex; flex-direction: column; overflow: hidden; }
.run-list__head { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-bottom: 1px solid var(--border-light); }
.run-list__title { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.run-list__items { flex: 1; overflow-y: auto; padding: 8px; }
.run-list__ops { display: flex; gap: 6px; }
.run-card { padding: 10px 12px; border-radius: var(--radius-md); border: 1px solid transparent; cursor: pointer; margin-bottom: 6px; transition: all .16s; }
.run-card:hover { background: var(--slate-50); }
.run-card.is-active { border-color: var(--brand-400); background: var(--brand-50); }
.run-card__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.run-card__name { font-weight: 600; font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-card__meta { display: flex; align-items: center; gap: 8px; margin-top: 4px; font-size: 12px; color: var(--text-tertiary); }
.run-card__geo { margin-top: 4px; font-size: 12px; color: var(--text-tertiary); }
.run-card__geo b { font-size: 13px; }
.run-card__geo .good { color: var(--accent-emerald); }
.run-card__geo .warn { color: var(--amber-500); }
.run-card__time { margin-left: auto; }
.run-card__err { margin-top: 4px; font-size: 11px; color: var(--red-500); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tag-mock { color: var(--brand-600); }
</style>
