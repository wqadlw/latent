<template>
  <div class="app-shell" :class="{ 'is-collapsed': store.sidebarCollapsed }">
    <!-- ============ 侧边栏 ============ -->
    <aside class="sidebar">
      <!-- Logo 区 -->
      <div class="sidebar__logo" @click="$router.push('/dashboard')">
        <div class="logo-mark">
          <svg viewBox="0 0 32 32" fill="none" width="28" height="28">
            <rect x="2" y="2" width="28" height="28" rx="8" fill="url(#lg)"/>
            <path d="M10 11h12M10 16h12M10 21h7" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>
            <defs>
              <linearGradient id="lg" x1="0" y1="0" x2="32" y2="32">
                <stop stop-color="#818cf8"/><stop offset="1" stop-color="#4f46e5"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
        <transition name="fade">
          <div v-show="!store.sidebarCollapsed" class="logo-text">
            <span class="logo-title">Prompt Matrix</span>
            <span class="logo-sub">软文宣传矩阵系统</span>
          </div>
        </transition>
      </div>

      <!-- 行业切换器 -->
      <div v-show="!store.sidebarCollapsed" class="sidebar__industry">
        <div class="industry-label">当前行业</div>
        <el-select
          v-model="store.currentIndustryId"
          placeholder="选择行业"
          size="small"
          class="industry-select"
          @change="onIndustryChange"
        >
          <el-option
            v-for="ind in store.industries"
            :key="ind.id"
            :label="ind.name"
            :value="ind.id"
          />
        </el-select>
      </div>

      <!-- 导航菜单 -->
      <nav class="sidebar__nav">
        <template v-for="group in menuGroups" :key="group.title">
          <div v-show="!store.sidebarCollapsed" class="nav-group-label">{{ group.title }}</div>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ 'is-active': isActive(item.path) }"
            :title="store.sidebarCollapsed ? item.title : ''"
          >
            <el-icon class="nav-item__icon"><component :is="item.icon" v-if="item.icon" /></el-icon>
            <span v-show="!store.sidebarCollapsed" class="nav-item__text">{{ item.title }}</span>
            <span v-if="item.badge && !store.sidebarCollapsed" class="nav-item__badge">{{ item.badge }}</span>
          </router-link>
        </template>
      </nav>

      <!-- 底部折叠按钮 -->
      <div class="sidebar__footer">
        <div class="collapse-btn" @click="store.toggleSidebar()">
          <el-icon><Fold v-if="!store.sidebarCollapsed" /><Expand v-else /></el-icon>
          <transition name="fade">
            <span v-show="!store.sidebarCollapsed" class="collapse-text">收起菜单</span>
          </transition>
        </div>
      </div>
    </aside>

    <!-- ============ 主区域 ============ -->
    <div class="main-area">
      <!-- 统一顶栏（唯一的导航栏，解决双层导航问题） -->
      <header class="topbar">
        <div class="topbar__left">
          <div class="topbar__title-group">
            <span class="topbar__group">{{ currentGroup }}</span>
            <span class="topbar__sep" v-if="currentGroup">/</span>
            <h1 class="topbar__title">{{ currentTitle }}</h1>
          </div>
          <p v-if="currentSubtitle" class="topbar__subtitle">{{ currentSubtitle }}</p>
        </div>
        <div class="topbar__right">
          <!-- 全局搜索 -->
          <GlobalSearch />
          <!-- 页面操作按钮（通过 Teleport 注入，目标元素由 provide 给出，避免选择器时序崩溃） -->
          <div ref="pageActionsEl" id="page-actions" class="topbar__page-actions"></div>

          <div class="topbar__divider"></div>

          <!-- 全局操作 -->
          <el-tooltip content="刷新当前页" placement="bottom">
            <button class="icon-btn" @click="refresh">
              <el-icon><Refresh /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip content="接口文档" placement="bottom">
            <a class="icon-btn" href="/docs" target="_blank">
              <el-icon><Document /></el-icon>
            </a>
          </el-tooltip>
          <el-tag size="small" type="success" effect="plain" class="env-chip">
            <span class="env-dot"></span>已连接
          </el-tag>
          <el-dropdown trigger="click">
            <div class="user-chip">
              <el-avatar :size="30" class="user-avatar">A</el-avatar>
              <span class="user-name">管理员</span>
              <el-icon class="user-arrow"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item :icon="User">管理员</el-dropdown-item>
                <el-dropdown-item :icon="Setting" divided>系统设置</el-dropdown-item>
                <el-dropdown-item :icon="SwitchButton">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <!-- 内容区 -->
      <main class="content">
        <router-view v-slot="{ Component }">
          <component :is="Component" v-if="Component" :key="$route.path" />
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Setting, SwitchButton } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import GlobalSearch from './GlobalSearch.vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()

// 将顶栏操作区(#page-actions)的真实 DOM 元素引用提供给子视图，
// 避免 <Teleport to="#page-actions"> 在懒加载路由挂载时因 querySelector 时序失败而崩溃。
const pageActionsEl = ref(null)
provide('pageActionsTarget', pageActionsEl)

const menuGroups = computed(() => [
  {
    title: '工作台',
    items: [
      { path: '/dashboard', title: '工作台', icon: 'Odometer' },
    ],
  },
    {
      title: '内容生产',
      items: [
        { path: '/production', title: '软文生产', icon: 'MagicStick' },
        { path: '/content', title: '内容中心', icon: 'Box', badge: 'NEW' },
      ],
    },
  {
    title: '品牌资产',
    items: [
      { path: '/brand-asset', title: '品牌资产库', icon: 'GoldMedal', badge: 'NEW' },
    ],
  },
  {
    title: '基础配置',
    items: [
      { path: '/industry', title: '行业空间', icon: 'OfficeBuilding' },
      { path: '/platform', title: '平台账号人设', icon: 'Connection' },
      { path: '/knowledge', title: '知识库', icon: 'Collection' },
      { path: '/keyword', title: '关键词选题', icon: 'Key' },
    ],
  },
  {
    title: 'AI配置',
    items: [
      { path: '/prompt-library', title: 'AI提示词库', icon: 'Files', badge: '4类' },
      { path: '/prompt-center', title: '提示词总览', icon: 'Memo', badge: '收口' },
      { path: '/rule', title: '规则库', icon: 'SetUp' },
      { path: '/settings', title: 'LLM 配置', icon: 'Cpu', badge: 'NEW' },
    ],
  },
  {
    title: 'GEO 作战',
    items: [
      { path: '/geo-canvas', title: 'GEO 定位画布', icon: 'Aim', badge: 'NEW' },
      { path: '/persona', title: '客户画像', icon: 'User' },
      { path: '/intent-question', title: '意图问题库', icon: 'ChatDotRound' },
      { path: '/geo-monitor', title: 'AI推荐监测', icon: 'Monitor' },
    ],
  },
  {
    title: '发布自动化',
    items: [
      { path: '/publish', title: '发布中心', icon: 'Promotion', badge: 'NEW' },
      { path: '/browser-studio', title: '浏览器工作室', icon: 'Monitor', badge: 'NEW' },
      { path: '/automation-studio', title: '自动化指挥中心', icon: 'SetUp', badge: 'NEW' },
      { path: '/manual', title: '操作手册', icon: 'Reading' },
    ],
  },
])

const isActive = (path) => route.path === path

const currentTitle = computed(() => route.meta.title || '工作台')
const currentSubtitle = computed(() => route.meta.subtitle || '')
const currentGroup = computed(() => route.meta.group || '')

const onIndustryChange = (id) => {
  store.setIndustry(id)
  ElMessage.success('行业已切换')
}

const refresh = () => {
  window.location.reload()
}

onMounted(async () => {
  store.initFromStorage()
  await store.loadIndustries()
})
</script>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  background: var(--bg-page);
  overflow: hidden;
}

/* ============ 侧边栏 ============ */
.sidebar {
  width: 240px;
  background: var(--bg-sidebar);
  display: flex;
  flex-direction: column;
  transition: width 0.28s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
  overflow: hidden;
}
.is-collapsed .sidebar { width: 64px; }

.sidebar__logo {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  cursor: pointer;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  flex-shrink: 0;
}
.sidebar__logo:hover { background: rgba(255,255,255,0.03); }
.logo-mark { flex-shrink: 0; }
.logo-text { display: flex; flex-direction: column; line-height: 1.2; }
.logo-title { font-size: 15px; font-weight: 700; color: #fff; letter-spacing: 0.3px; }
.logo-sub { font-size: 10px; color: rgba(255,255,255,0.4); margin-top: 2px; }

.sidebar__industry {
  padding: 12px 16px 8px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  flex-shrink: 0;
}
.industry-label {
  font-size: 10px;
  color: rgba(255,255,255,0.35);
  margin-bottom: 6px;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  font-weight: 600;
}
.industry-select :deep(.el-select__wrapper) {
  background: rgba(255,255,255,0.06) !important;
  box-shadow: none !important;
  border: 1px solid rgba(255,255,255,0.08) !important;
  border-radius: var(--radius-md) !important;
}
.industry-select :deep(.el-select__wrapper:hover) {
  border-color: rgba(255,255,255,0.2) !important;
}
.industry-select :deep(.el-select__placeholder),
.industry-select :deep(.el-select__selected-item) {
  color: #e2e8f0 !important;
  font-size: 13px;
}
.industry-select :deep(.el-select__caret) { color: var(--slate-400) !important; }

.sidebar__nav {
  flex: 1;
  overflow-y: auto;
  padding: 4px 12px 12px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.1) transparent;
}
.sidebar__nav::-webkit-scrollbar { width: 4px; }
.sidebar__nav::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

.nav-group-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--slate-500);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  padding: 14px 10px 6px;
  white-space: nowrap;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius-md);
  color: rgba(255,255,255,0.65);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.16s ease;
  margin-bottom: 2px;
  text-decoration: none;
  white-space: nowrap;
}
.nav-item:hover {
  background: rgba(255,255,255,0.06);
  color: #fff;
}
.nav-item.is-active {
  background: linear-gradient(135deg, var(--brand-600), var(--brand-500));
  color: #fff;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.4);
}
.nav-item__icon { font-size: 16px; flex-shrink: 0; }
.nav-item__text { flex: 1; }
.nav-item__badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  background: rgba(99, 102, 241, 0.2);
  color: var(--brand-300);
  font-weight: 600;
}
.nav-item.is-active .nav-item__badge {
  background: rgba(255,255,255,0.2);
  color: #fff;
}

.sidebar__footer {
  padding: 8px 12px;
  border-top: 1px solid rgba(255,255,255,0.04);
  flex-shrink: 0;
}
.collapse-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  color: rgba(255,255,255,0.5);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.16s;
}
.collapse-btn:hover { background: rgba(255,255,255,0.06); color: #fff; }
.collapse-text { white-space: nowrap; }

/* ============ 主区域 ============ */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

/* 统一顶栏 */
.topbar {
  height: 60px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
.topbar__left { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.topbar__title-group { display: flex; align-items: center; gap: 8px; }
.topbar__group { font-size: 12px; color: var(--text-tertiary); font-weight: 500; }
.topbar__sep { color: var(--text-quaternary); font-size: 12px; }
.topbar__title { font-size: 17px; font-weight: 700; color: var(--text-primary); margin: 0; letter-spacing: -0.2px; }
.topbar__subtitle { font-size: 12px; color: var(--text-tertiary); margin: 0; }

.topbar__right { display: flex; align-items: center; gap: 10px; }
.topbar__page-actions { display: flex; align-items: center; gap: 8px; min-height: 34px; }
.topbar__divider { width: 1px; height: 20px; background: var(--border-light); margin: 0 4px; }

.icon-btn {
  width: 34px;
  height: 34px;
  border: 1px solid var(--border-light);
  background: var(--bg-card);
  border-radius: var(--radius-md);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  font-size: 16px;
  transition: all 0.16s;
  text-decoration: none;
}
.icon-btn:hover {
  border-color: var(--brand-300);
  color: var(--brand-600);
  background: var(--brand-50);
}

.env-chip { font-weight: 500; }
.env-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  background: var(--accent-emerald);
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: 1px;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 4px 4px;
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: background 0.16s;
}
.user-chip:hover { background: var(--slate-100); }
.user-avatar { background: linear-gradient(135deg, var(--brand-500), var(--brand-700)); color: #fff; }
.user-name { font-size: 13px; font-weight: 500; color: var(--text-secondary); }
.user-arrow { font-size: 12px; color: var(--text-tertiary); }

/* 内容区 */
.content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  scrollbar-width: thin;
  scrollbar-color: var(--slate-300) transparent;
}
.content::-webkit-scrollbar { width: 8px; }
.content::-webkit-scrollbar-thumb { background: var(--slate-300); border-radius: 4px; }
.content::-webkit-scrollbar-thumb:hover { background: var(--slate-400); }

/* 过渡 */
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.slide-up-enter-active { transition: all 0.28s cubic-bezier(0.4, 0, 0.2, 1); }
.slide-up-leave-active { transition: all 0.18s ease; }
.slide-up-enter-from { opacity: 0; transform: translateY(10px); }
.slide-up-leave-to { opacity: 0; transform: translateY(-6px); }

/* 响应式 */
@media (max-width: 768px) {
  .sidebar { position: fixed; left: 0; top: 0; bottom: 0; transform: translateX(-100%); }
  .is-collapsed .sidebar { transform: translateX(0); width: 240px; }
  .topbar { padding: 0 16px; }
  .content { padding: 16px; }
  .topbar__subtitle { display: none; }
  .user-name { display: none; }
}
</style>
