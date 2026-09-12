<template>
  <div class="dashboard-view">
    <!-- 欢迎横幅 -->
    <div class="welcome-banner">
      <div class="welcome-content">
        <h2 class="welcome-title">{{ greeting }}，管理员</h2>
        <p class="welcome-desc">欢迎使用 Prompt Matrix 软文宣传矩阵系统，当前行业：<strong>{{ store.currentIndustryName }}</strong></p>
      </div>
      <div class="welcome-deco">
        <svg viewBox="0 0 200 120" fill="none" width="200" height="120">
          <circle cx="160" cy="30" r="40" fill="rgba(255,255,255,0.08)"/>
          <circle cx="120" cy="80" r="30" fill="rgba(255,255,255,0.06)"/>
          <rect x="40" y="40" width="60" height="40" rx="8" fill="rgba(255,255,255,0.05)"/>
        </svg>
      </div>
    </div>

    <!-- 核心指标 -->
    <div class="stat-grid">
      <StatCard label="软文生产任务" :value="stats.production" icon="MagicStick" variant="indigo" />
      <StatCard label="待审核内容" :value="stats.pending" icon="Document" variant="amber" />
      <StatCard label="已发布内容" :value="stats.published" icon="CircleCheck" variant="emerald" />
      <StatCard label="关键词选题" :value="stats.keywords" icon="Key" variant="violet" />
    </div>

    <!-- 快捷入口 -->
    <div class="section-block">
      <div class="section-head">
        <h3 class="section-title">快捷入口</h3>
      </div>
      <div class="quick-grid">
        <div
          v-for="quick in quickEntries"
          :key="quick.path"
          class="quick-card"
          @click="$router.push(quick.path)"
        >
          <div class="quick-card__icon" :style="{ background: quick.bg, color: quick.color }">
            <el-icon><component :is="quick.icon" v-if="quick.icon" /></el-icon>
          </div>
          <div class="quick-card__body">
            <div class="quick-card__title">{{ quick.title }}</div>
            <div class="quick-card__desc">{{ quick.desc }}</div>
          </div>
          <el-icon class="quick-card__arrow"><ArrowRight /></el-icon>
        </div>
      </div>
    </div>

    <!-- 双栏：最近任务 + 系统状态 -->
    <div class="dual-grid">
      <div class="section-block">
        <div class="section-head">
          <h3 class="section-title">最近生产任务</h3>
          <el-button text type="primary" @click="$router.push('/production')">查看全部</el-button>
        </div>
        <div class="recent-list">
          <div v-for="task in recentTasks" :key="task.id" class="recent-item" @click="$router.push('/production')">
            <div class="recent-item__main">
              <div class="recent-item__title">{{ task.title || `任务 #${task.id}` }}</div>
              <div class="recent-item__meta">
                <el-tag size="small" :type="statusType(task.status)" effect="light">{{ statusLabel(task.status) }}</el-tag>
                <span class="recent-item__time">{{ formatTime(task.update_time) }}</span>
              </div>
            </div>
            <el-icon class="recent-item__arrow"><ArrowRight /></el-icon>
          </div>
          <EmptyState v-if="recentTasks.length === 0" title="暂无生产任务" description="点击右上角开始第一个任务" size="small" icon="DocumentAdd" />
        </div>
      </div>

      <div class="section-block">
        <div class="section-head">
          <h3 class="section-title">系统状态</h3>
        </div>
        <div class="status-list">
          <div class="status-item">
            <span class="status-item__label">当前行业</span>
            <span class="status-item__value">{{ store.currentIndustryName }}</span>
          </div>
          <div class="status-item">
            <span class="status-item__label">行业总数</span>
            <span class="status-item__value">{{ store.industries.length }}</span>
          </div>
          <div class="status-item">
            <span class="status-item__label">系统版本</span>
            <span class="status-item__value">v2.0.0</span>
          </div>
          <div class="status-item">
            <span class="status-item__label">运行模式</span>
            <span class="status-item__value">本地运行</span>
          </div>
          <div class="status-item">
            <span class="status-item__label">AI 接口</span>
            <span class="status-item__value" style="color: var(--accent-emerald);">零依赖</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAppStore } from '../store/app'
import { productionApi, contentApi, keywordApi } from '../api'
import StatCard from '../components/StatCard.vue'
import EmptyState from '../components/EmptyState.vue'

const store = useAppStore()
const stats = ref({ production: 0, pending: 0, published: 0, keywords: 0 })
const recentTasks = ref([])

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '凌晨好'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const quickEntries = [
  { path: '/production', title: '软文生产', desc: '7步标准化生产流程', icon: 'MagicStick', bg: 'var(--brand-50)', color: 'var(--brand-600)' },
  { path: '/prompt-library', title: 'AI提示词库', desc: '4分类提示词模板', icon: 'Files', bg: '#fffbeb', color: 'var(--accent-amber)' },
  { path: '/brand-asset', title: '品牌资产库', desc: '品牌信息管理', icon: 'GoldMedal', bg: '#ecfdf5', color: 'var(--accent-emerald)' },
  { path: '/content', title: '内容中心', desc: '审核 · 资产 · 运营一体化', icon: 'Calendar', bg: '#f5f3ff', color: 'var(--accent-violet)' },
]

const statusType = (s) => ({ draft: 'info', processing: 'warning', done: 'success', archived: 'info' }[s] || 'info')
const statusLabel = (s) => ({ draft: '草稿', processing: '进行中', done: '已完成', archived: '已归档' }[s] || s)

function formatTime(t) {
  if (!t) return '—'
  return new Date(t).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function loadStats() {
  if (!store.currentIndustryId) return
  try {
    const [prodRes, contentRes, kwRes] = await Promise.all([
      productionApi.list({ industry_id: store.currentIndustryId }),
      contentApi.list(store.currentIndustryId, '', '', ''),
      keywordApi.list(store.currentIndustryId),
    ])
    const tasks = prodRes.data || []
    const contents = contentRes.data || []
    stats.value = {
      production: tasks.length,
      pending: contents.filter(c => c.review_status === 'pending').length,
      published: contents.filter(c => c.publish_status === 'published').length,
      keywords: kwRes.data?.length || 0,
    }
    recentTasks.value = tasks.slice(0, 5)
  } catch (e) {
    console.error('加载统计失败', e)
  }
}

onMounted(async () => {
  await store.loadIndustries()
  await loadStats()
})
</script>

<style scoped>
.dashboard-view { display: flex; flex-direction: column; gap: 20px; }

.welcome-banner {
  background: linear-gradient(135deg, var(--brand-600), var(--brand-800));
  border-radius: var(--radius-xl);
  padding: 28px 32px;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  overflow: hidden;
  position: relative;
}
.welcome-content { z-index: 1; }
.welcome-title { font-size: 22px; font-weight: 700; margin: 0 0 6px; }
.welcome-desc { font-size: 13px; opacity: 0.85; margin: 0; }
.welcome-desc strong { font-weight: 600; }
.welcome-deco { position: absolute; right: 20px; top: 50%; transform: translateY(-50%); opacity: 0.6; }

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.section-block {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-sm);
}
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.section-title { font-size: 15px; font-weight: 700; color: var(--text-primary); margin: 0; }

.quick-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.quick-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s ease;
}
.quick-card:hover { border-color: var(--brand-300); box-shadow: var(--shadow-sm); transform: translateY(-1px); }
.quick-card__icon {
  width: 40px; height: 40px;
  border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}
.quick-card__body { flex: 1; min-width: 0; }
.quick-card__title { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.quick-card__desc { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }
.quick-card__arrow { color: var(--text-quaternary); font-size: 14px; }

.dual-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 16px;
}

.recent-list { display: flex; flex-direction: column; gap: 8px; }
.recent-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  transition: background 0.16s;
  cursor: pointer;
}
.recent-item:hover { background: var(--slate-50); }
.recent-item__main { flex: 1; min-width: 0; }
.recent-item__title { font-size: 13.5px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.recent-item__meta { display: flex; align-items: center; gap: 10px; }
.recent-item__time { font-size: 12px; color: var(--text-tertiary); }
.recent-item__arrow { color: var(--text-quaternary); }

.status-list { display: flex; flex-direction: column; gap: 12px; }
.status-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px;
  background: var(--slate-50);
  border-radius: var(--radius-md);
}
.status-item__label { font-size: 13px; color: var(--text-secondary); font-weight: 500; }
.status-item__value { font-size: 13px; color: var(--text-primary); font-weight: 600; }

@media (max-width: 1024px) {
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .quick-grid { grid-template-columns: repeat(2, 1fr); }
  .dual-grid { grid-template-columns: 1fr; }
}
</style>
