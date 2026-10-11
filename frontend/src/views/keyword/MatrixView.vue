<template>
  <div v-loading="loading">
    <div v-for="m in matrix" :key="m.platform.id" class="matrix-card">
      <div class="matrix-card__head">
        <el-tag size="small" effect="dark">{{ m.platform.name }}</el-tag>
        <span class="matrix-card__info">字数 {{ m.platform.word_count_min }}-{{ m.platform.word_count_max }}</span>
      </div>
      <div v-if="m.accounts.length === 0" class="matrix-empty">暂无账号</div>
      <div v-for="acc in m.accounts" :key="acc.account.id" class="matrix-acc">
        <div class="matrix-acc__name">{{ acc.account.account_name }}</div>
        <div v-if="acc.topics.length === 0" class="matrix-empty matrix-empty--sm">暂无选题</div>
        <div v-for="t in acc.topics" :key="t.id" class="matrix-topic">
          <el-tag size="small" :type="t.status === 'done' ? 'success' : 'info'" effect="plain">{{ TOPIC_STATUS_SHORT[t.status] }}</el-tag>
          <span class="matrix-topic__title">{{ t.title }}</span>
          <span class="matrix-topic__date">{{ t.plan_date || '' }}</span>
        </div>
      </div>
    </div>
    <EmptyState v-if="!loading && matrix.length === 0" title="暂无矩阵数据" size="small" icon="Grid" />
  </div>
</template>

<script setup>
/**
 * 矩阵视图：平台 → 账号 → 选题 的三层展开（只读）。
 *
 * 数据由壳在切到这个分段时按需拉取（`topicApi.matrix`），本组件不取数。
 */
import { TOPIC_STATUS_SHORT } from '../../constants/status'
import EmptyState from '../../components/EmptyState.vue'

defineProps({
  matrix: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
</script>

<style scoped>
.matrix-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  margin-bottom: 12px;
  box-shadow: var(--shadow-sm);
}
.matrix-card__head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.matrix-card__info { font-size: 12px; color: var(--text-tertiary); }
.matrix-acc { padding: 8px 0; border-top: 1px dashed var(--border-light); }
.matrix-acc__name { font-weight: 600; font-size: 13px; margin-bottom: 4px; color: var(--text-primary); }
.matrix-topic {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}
.matrix-topic__title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-secondary); }
.matrix-topic__date { color: var(--text-tertiary); }
/* 原先这两处是内联 style，挪到类里 */
.matrix-empty { padding: 20px; text-align: center; color: var(--text-tertiary); font-size: 13px; }
.matrix-empty--sm { padding: 4px 0; font-size: 12px; text-align: left; }
</style>
