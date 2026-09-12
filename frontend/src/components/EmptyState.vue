<template>
  <div class="empty-state" :class="{ 'is-small': size === 'small' }">
    <div class="empty-icon">
      <el-icon><component :is="icon" v-if="icon" /></el-icon>
    </div>
    <div class="empty-title">{{ title }}</div>
    <div v-if="description" class="empty-desc">{{ description }}</div>
    <div v-if="$slots.default" class="empty-action">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '' },
  icon: { type: String, default: 'Inbox' },
  size: { type: String, default: 'default' }
})
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 56px 24px;
  text-align: center;
}
.empty-state.is-small { padding: 32px 16px; }
.empty-icon {
  width: 64px;
  height: 64px;
  border-radius: var(--radius-xl);
  background: var(--slate-100);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--slate-400);
  font-size: 28px;
  margin-bottom: 16px;
}
.is-small .empty-icon { width: 48px; height: 48px; font-size: 22px; margin-bottom: 12px; }
.empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.empty-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  max-width: 360px;
  line-height: 1.6;
}
.empty-action { margin-top: 18px; }
</style>
