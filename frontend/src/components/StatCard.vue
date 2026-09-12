<template>
  <div class="stat-card" :class="[`stat-card--${variant}`]">
    <div class="stat-card__body">
      <div class="stat-card__top">
        <div class="stat-card__icon">
          <el-icon><component :is="icon" v-if="icon" /></el-icon>
        </div>
        <div v-if="trend !== null" class="stat-card__trend" :class="trend >= 0 ? 'is-up' : 'is-down'">
          <el-icon><CaretTop v-if="trend >= 0" /><CaretBottom v-else /></el-icon>
          <span>{{ Math.abs(trend) }}%</span>
        </div>
      </div>
      <div class="stat-card__value">{{ displayValue }}</div>
      <div class="stat-card__label">{{ label }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: [Number, String], default: 0 },
  label: { type: String, default: '' },
  icon: { type: String, default: 'DataLine' },
  variant: { type: String, default: 'indigo' },
  trend: { type: Number, default: null },
  prefix: { type: String, default: '' },
  suffix: { type: String, default: '' }
})

const displayValue = computed(() => {
  const v = props.value
  if (typeof v === 'number') {
    return props.prefix + v.toLocaleString() + props.suffix
  }
  return props.prefix + v + props.suffix
})
</script>

<style scoped>
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 20px;
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;
}
.stat-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
}
.stat-card--indigo::before { background: linear-gradient(90deg, var(--brand-400), var(--brand-600)); }
.stat-card--emerald::before { background: linear-gradient(90deg, #34d399, var(--accent-emerald)); }
.stat-card--amber::before { background: linear-gradient(90deg, #fbbf24, var(--accent-amber)); }
.stat-card--rose::before { background: linear-gradient(90deg, #fb7185, var(--accent-rose)); }
.stat-card--cyan::before { background: linear-gradient(90deg, #22d3ee, var(--accent-cyan)); }
.stat-card--violet::before { background: linear-gradient(90deg, #a78bfa, var(--accent-violet)); }
.stat-card:hover { box-shadow: var(--shadow-md); transform: translateY(-2px); }

.stat-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.stat-card__icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}
.stat-card--indigo .stat-card__icon { background: var(--brand-50); color: var(--brand-600); }
.stat-card--emerald .stat-card__icon { background: #ecfdf5; color: var(--accent-emerald); }
.stat-card--amber .stat-card__icon { background: #fffbeb; color: var(--accent-amber); }
.stat-card--rose .stat-card__icon { background: #fff1f2; color: var(--accent-rose); }
.stat-card--cyan .stat-card__icon { background: #ecfeff; color: var(--accent-cyan); }
.stat-card--violet .stat-card__icon { background: #f5f3ff; color: var(--accent-violet); }

.stat-card__trend {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}
.stat-card__trend.is-up { color: var(--accent-emerald); background: #ecfdf5; }
.stat-card__trend.is-down { color: var(--accent-rose); background: #fff1f2; }
.stat-card__trend .el-icon { font-size: 11px; }

.stat-card__value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
  letter-spacing: -0.5px;
  font-variant-numeric: tabular-nums;
}
.stat-card__label {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 4px;
  font-weight: 500;
}
</style>
