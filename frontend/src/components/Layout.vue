<template>
  <div class="app-shell" :class="{ 'is-collapsed': store.sidebarCollapsed }">
    <!-- ============ 侧边栏 ============ -->
    <aside class="sidebar">
      <!-- Logo 区 -->
      <div class="sidebar__logo" @click="$router.push('/dashboard')">
        <div class="logo-mark">
          <BrandMark :size="30" foreground="#FFFFFF" accent="#9CA3AF" />
        </div>
        <transition name="fade">
          <div v-show="!store.sidebarCollapsed" class="logo-text">
            <span class="logo-title">显影 Latent</span>
            <span class="logo-sub">企业级 GEO 运营系统</span>
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
          <el-dropdown trigger="click" @command="onUserCommand">
            <div class="user-chip">
              <el-avatar :size="30" class="user-avatar">{{ avatarText }}</el-avatar>
              <span class="user-name">{{ auth.displayName }}</span>
              <el-icon class="user-arrow"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  {{ auth.isAdmin ? '管理员' : '编辑' }} · {{ auth.username }}
                </el-dropdown-item>
                <el-dropdown-item command="password" :icon="Lock" divided>修改密码</el-dropdown-item>
                <el-dropdown-item command="settings" :icon="Setting">系统设置</el-dropdown-item>
                <el-dropdown-item command="logout" :icon="SwitchButton" divided>退出登录</el-dropdown-item>
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

    <!-- 修改密码 -->
    <el-dialog v-model="pwdVisible" title="修改密码" width="420px" append-to-body>
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-position="top">
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="请输入原密码" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm_password">
          <el-input v-model="pwdForm.confirm_password" type="password" show-password placeholder="再次输入新密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdSubmitting" @click="submitPassword">确认修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, provide, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, Lock, Setting, SwitchButton } from '@element-plus/icons-vue'
import { authApi } from '../api'
import { useAppStore } from '../store/app'
import { useAuthStore } from '../store/auth'
import BrandMark from './BrandMark.vue'
import GlobalSearch from './GlobalSearch.vue'
import { buildMenuGroups } from '../constants/menu'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const auth = useAuthStore()

// 将顶栏操作区(#page-actions)的真实 DOM 元素引用提供给子视图，
// 避免 <Teleport to="#page-actions"> 在懒加载路由挂载时因 querySelector 时序失败而崩溃。
const pageActionsEl = ref(null)
provide('pageActionsTarget', pageActionsEl)

// 菜单由路由派生（D7 确立的单一来源）：文案取 meta.title、分组取 meta.group、
// 徽标取 meta.badge、组顺序与项顺序取路由的声明顺序。
// 改菜单请改 src/router/index.js，本文件不再持有任何菜单文案字面量。
// 详见 src/constants/menu.js 的头部注释。
const menuGroups = computed(() => buildMenuGroups(router.getRoutes()))

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

// ============ 账号 ============
const avatarText = computed(() => (auth.username || 'U').charAt(0).toUpperCase())

const pwdVisible = ref(false)
const pwdSubmitting = ref(false)
const pwdFormRef = ref(null)
const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })

const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '新密码至少 8 位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== pwdForm.new_password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

function onUserCommand(command) {
  if (command === 'password') {
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
    pwdVisible.value = true
  } else if (command === 'settings') {
    router.push('/settings')
  } else if (command === 'logout') {
    onLogout()
  }
}

async function submitPassword() {
  const valid = await pwdFormRef.value?.validate().catch(() => false)
  if (!valid) return
  pwdSubmitting.value = true
  try {
    await authApi.changePassword({
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password,
    })
    pwdVisible.value = false
    ElMessage.success('密码已修改，请重新登录')
    // 后端未做令牌吊销，主动登出以确保新密码立即生效
    setTimeout(() => {
      auth.logout()
      router.replace({ name: 'Login' })
    }, 800)
  } catch {
    // 错误提示已由 axios 拦截器统一弹出
  } finally {
    pwdSubmitting.value = false
  }
}

async function onLogout() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '退出登录', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return // 用户取消
  }
  auth.logout()
  router.replace({ name: 'Login' })
  ElMessage.success('已退出登录')
}

onMounted(async () => {
  store.initFromStorage()
  await store.loadIndustries()
  // 用服务端数据校准本地用户态（角色可能已被管理员改动）
  if (auth.isLoggedIn) {
    try {
      await auth.fetchMe()
    } catch {
      // 401 由拦截器处理
    }
  }
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
/* ⚠️ 这里的 flex 收缩行为是踩过坑的，别随手改：
   `.topbar` 是 space-between 两栏。右栏里既有全局搜索，又会由子视图 Teleport 进任意多个
   操作按钮（Knowledge 一次塞 5 个，实测右栏需要 1215px，而顶栏只有 1200px）。
   若左栏的 min-width 是 0，浏览器就会优先把左栏压扁 —— 副标题随即**逐字换行**，
   在 60px 高的顶栏里渲染成一条竖排文字，看起来像「标题坏了」。

   所以三条约束缺一不可：
     1. 左栏给 min-width 下限（不再允许压到 0），并用 max-width 防止它反过来吃掉右栏；
     2. 左栏内部一律 nowrap + 省略号，宁可截断也绝不换行；
     3. 空间不足时由**搜索框**先收缩（见 GlobalSearch.vue 的 flex 基准）。 */
.topbar__left { display: flex; flex-direction: column; gap: 2px; min-width: 140px; max-width: 360px; flex: 0 1 auto; }
.topbar__title-group { display: flex; align-items: center; gap: 8px; min-width: 0; }
.topbar__group { font-size: 12px; color: var(--text-tertiary); font-weight: 500; white-space: nowrap; }
.topbar__sep { color: var(--text-quaternary); font-size: 12px; }
.topbar__title { font-size: 17px; font-weight: 700; color: var(--text-primary); margin: 0; letter-spacing: -0.2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.topbar__subtitle { font-size: 12px; color: var(--text-tertiary); margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.topbar__right { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 0 1 auto; }
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

/* 顶栏空间不够时，优先收起全局搜索（原因见上方 .topbar__left 的注释）：
   Knowledge 这类页面会 Teleport 5 个操作按钮进顶栏，1440 下右栏就需要 1215px，
   而顶栏只有 1200px。搜索是顶栏里最不关键的元素 —— 与其被压成一个 0 宽的细条
   （看起来像坏了），不如直接收起，把空间让给页面自己的操作。
   注：`.global-search` 是 GlobalSearch.vue 的根元素，scoped 样式能作用到它。 */
@media (max-width: 1400px) {
  .global-search { display: none; }
}

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
