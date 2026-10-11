import { createRouter, createWebHistory } from 'vue-router'
import Layout from '../components/Layout.vue'
import { getToken } from '../api/authToken'

// ⚠️ 这个文件同时是**侧边栏菜单的唯一来源**（见 src/constants/menu.js）。
//
// 契约（D7 确立，改动前务必读）：
//   - 进菜单的页面必须有 `meta.group`（组名）、`meta.title`（菜单文案）、`meta.icon`（Element Plus 图标名）。
//     三者缺一，`buildMenuGroups()` 会跳过该路由或产出空标题 —— 那是静默失效，肉眼很难发现。
//   - 不进菜单的页面要么不写 `meta.group`（如登录页），要么显式写 `meta.hidden: true`（如 404）。
//   - `meta.badge` 是菜单独有元数据（小徽标），非必填。
//   - **菜单的分组顺序 = 下面 children 的声明顺序**（首次出现即建组）。
//     想调顺序，就把整块路由挪位置，**不要**再另建一张排序表。
//   - 兜底路由 `:pathMatch(.*)*` **必须声明在最后**，否则它会吞掉后面所有路由。
//
// 历史教训：D7 之前菜单在 `Layout.vue` 里手工维护了第二份，两份必然漂移 ——
// 实测组顺序不同、`/publish` 标题不同，且顶栏出现过「发布自动化 / 发布自动化」。

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { public: true, title: '登录' }
  },
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    children: [
      // ============ 工作台 ============
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '工作台', subtitle: '系统概览与核心指标', group: '工作台', icon: 'Odometer' }
      },

      // ============ 内容生产 ============
      {
        path: 'production',
        name: 'Production',
        component: () => import('../views/Production.vue'),
        meta: { title: '软文生产', subtitle: '10步标准化生产流程', group: '内容生产', icon: 'MagicStick' }
      },
      {
        path: 'content',
        name: 'Content',
        component: () => import('../views/Content.vue'),
        meta: { title: '内容中心', subtitle: '内容审核 · 资产归档 · 运营投放', group: '内容生产', icon: 'Box', badge: 'NEW' }
      },

      // ============ 品牌资产 ============
      {
        path: 'brand-asset',
        name: 'BrandAsset',
        component: () => import('../views/BrandAsset.vue'),
        meta: { title: '品牌资产库', subtitle: '品牌信息自动注入提示词', group: '品牌资产', icon: 'GoldMedal', badge: 'NEW' }
      },

      // ============ 基础配置 ============
      {
        path: 'industry',
        name: 'Industry',
        component: () => import('../views/Industry.vue'),
        meta: { title: '行业空间', subtitle: '行业配置与切换', group: '基础配置', icon: 'OfficeBuilding' }
      },
      {
        path: 'platform',
        name: 'Platform',
        component: () => import('../views/Platform.vue'),
        meta: { title: '平台账号人设', subtitle: '7大平台预置与账号管理', group: '基础配置', icon: 'Connection' }
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('../views/Knowledge.vue'),
        meta: { title: '知识库', subtitle: '行业知识文档管理', group: '基础配置', icon: 'Collection' }
      },
      {
        path: 'keyword',
        name: 'Keyword',
        component: () => import('../views/Keyword.vue'),
        meta: { title: '关键词选题', subtitle: '关键词与选题管理', group: '基础配置', icon: 'Key' }
      },

      // ============ AI配置 ============
      {
        path: 'prompt-library',
        name: 'PromptLibrary',
        component: () => import('../views/PromptLibrary.vue'),
        meta: { title: 'AI提示词库', subtitle: '4分类提示词模板管理', group: 'AI配置', icon: 'Files', badge: '4类' }
      },
      {
        path: 'prompt-center',
        name: 'PromptCenter',
        component: () => import('../views/PromptCenter.vue'),
        meta: { title: '提示词总览', subtitle: '三体系统一视图 · 自动化 / 提示词库 / 阶段常量', group: 'AI配置', icon: 'Memo', badge: '收口' }
      },
      {
        path: 'rule',
        name: 'Rule',
        component: () => import('../views/Rule.vue'),
        meta: { title: '规则库', subtitle: 'AI SEO/去AI味/合规/创作规则', group: 'AI配置', icon: 'SetUp' }
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('../views/Settings.vue'),
        meta: { title: 'LLM 配置', subtitle: 'DeepSeek 等大模型一键生成 · 与手动模式并存', group: 'AI配置', icon: 'Cpu', badge: 'NEW' }
      },

      // ============ GEO 作战 ============
      {
        path: 'geo-canvas',
        name: 'GeoCanvas',
        component: () => import('../views/GeoCanvas.vue'),
        meta: { title: 'GEO 定位画布', subtitle: '三环定位法：人群 × 问题 × 优势', group: 'GEO 作战', icon: 'Aim', badge: 'NEW' }
      },
      {
        path: 'persona',
        name: 'Persona',
        component: () => import('../views/Persona.vue'),
        meta: { title: '客户画像', subtitle: 'GEO 基础：定义目标客户会问 AI 什么', group: 'GEO 作战', icon: 'User' }
      },
      {
        path: 'intent-question',
        name: 'IntentQuestion',
        component: () => import('../views/IntentQuestion.vue'),
        meta: { title: '意图问题库', subtitle: 'GEO 基础：目标客户会问 AI 的问题', group: 'GEO 作战', icon: 'ChatDotRound' }
      },
      {
        path: 'geo-monitor',
        name: 'GeoMonitor',
        component: () => import('../views/GeoMonitor.vue'),
        meta: { title: 'AI推荐监测', subtitle: 'GEO 闭环：验证 AI 是否推荐我们', group: 'GEO 作战', icon: 'Monitor' }
      },
      {
        path: 'geo-visibility',
        name: 'GeoVisibility',
        component: () => import('../views/GeoVisibility.vue'),
        meta: { title: 'AI可见性看板', subtitle: '自动探测 · 6 KPI · 信源偏好榜 · 竞品对比', group: 'GEO 作战', icon: 'DataAnalysis', badge: 'NEW' }
      },
      {
        path: 'geo-loop',
        name: 'GeoLoop',
        component: () => import('../views/GeoLoop.vue'),
        meta: { title: '归因闭环', subtitle: '发布 → 收录 → 引用 → 排名 → 回流', group: 'GEO 作战', icon: 'Connection', badge: 'NEW' }
      },

      // ============ 发布自动化 ============
      // ⚠️ 这一组刻意排在「GEO 作战」之后 —— 声明顺序即菜单顺序。
      {
        path: 'pipeline',
        name: 'Pipeline',
        component: () => import('../views/Pipeline.vue'),
        meta: { title: '批量生产与队列', subtitle: '可编排流水线 · 断点续跑 · 有界并发执行池', group: '发布自动化', icon: 'Tickets', badge: 'NEW' }
      },
      {
        // 标题曾漂移成「发布自动化」，与 group 同名，顶栏渲染为「发布自动化 / 发布自动化」。
        // 现统一为菜单里的叫法「发布中心」，层级感恢复正常。
        path: 'publish',
        name: 'Publish',
        component: () => import('../views/Publish.vue'),
        meta: { title: '发布中心', subtitle: '浏览器自动化发布 · 人工审核闸门 · 凭证管理', group: '发布自动化', icon: 'Promotion', badge: 'NEW' }
      },
      {
        path: 'browser-studio',
        name: 'BrowserStudio',
        component: () => import('../views/BrowserStudio.vue'),
        meta: { title: '浏览器工作室', subtitle: '豆包创作 + 搜狐号发布 全链路自动化 · 状态跟踪/失败重试/结果回溯', group: '发布自动化', icon: 'Monitor', badge: 'NEW' }
      },
      {
        path: 'automation-studio',
        name: 'AutomationStudio',
        component: () => import('../views/AutomationStudio.vue'),
        meta: { title: '自动化指挥中心', subtitle: '自动化全流程可视化 · 每步提示词可编辑可复制 · 多专家协同', group: '发布自动化', icon: 'SetUp', badge: 'NEW' }
      },
      {
        path: 'manual',
        name: 'Manual',
        component: () => import('../views/Manual.vue'),
        meta: { title: '操作手册', subtitle: '全流程复现指南 · 每步可复制给网页 AI 手动复现', group: '发布自动化', icon: 'Reading' }
      },

      // ============ 兜底（必须最后） ============
      {
        // 兜底路由：未知路径不再白屏，而是展示友好的 404 页面。
        // hidden 让 buildMenuGroups() 跳过它；`group: ''` 本身也会被跳过，这里是双保险。
        path: ':pathMatch(.*)*',
        name: 'NotFound',
        component: () => import('../views/NotFound.vue'),
        meta: { title: '页面不存在', subtitle: '', group: '', hidden: true }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

/**
 * 登录守卫。
 *
 * 只做「有没有令牌」的粗判 —— 令牌是否真的有效由后端 `get_current_user` 决定，
 * 前端过期令牌会在首个接口 401 时被拦截器统一清掉并跳回登录页。
 * 这样避免在守卫里同步请求后端（会让首屏变慢），也不会出现「守卫放行但接口全 401」的体验。
 */
router.beforeEach((to) => {
  const loggedIn = !!getToken()

  if (to.meta?.public) {
    // 已登录时访问登录页，直接送回工作台
    if (loggedIn && to.name === 'Login') return { path: '/dashboard' }
    return true
  }

  if (!loggedIn) {
    return { name: 'Login', query: to.fullPath === '/' ? {} : { redirect: to.fullPath } }
  }
  return true
})

export default router
