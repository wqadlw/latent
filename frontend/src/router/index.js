import { createRouter, createWebHistory } from 'vue-router'
import Layout from '../components/Layout.vue'

const routes = [
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '工作台', subtitle: '系统概览与核心指标', group: '工作台', icon: 'Odometer' }
      },
      {
        path: 'production',
        name: 'Production',
        component: () => import('../views/Production.vue'),
        meta: { title: '软文生产', subtitle: '7步标准化生产流程', group: '内容生产', icon: 'MagicStick' }
      },
      {
        path: 'content',
        name: 'Content',
        component: () => import('../views/Content.vue'),
        meta: { title: '内容中心', subtitle: '内容审核 · 资产归档 · 运营投放', group: '内容生产', icon: 'Box' }
      },
      {
        path: 'brand-asset',
        name: 'BrandAsset',
        component: () => import('../views/BrandAsset.vue'),
        meta: { title: '品牌资产库', subtitle: '品牌信息自动注入提示词', group: '品牌资产', icon: 'GoldMedal' }
      },
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
      {
        path: 'prompt-library',
        name: 'PromptLibrary',
        component: () => import('../views/PromptLibrary.vue'),
        meta: { title: 'AI提示词库', subtitle: '4分类提示词模板管理', group: 'AI配置', icon: 'Files' }
      },
      {
        path: 'prompt-center',
        name: 'PromptCenter',
        component: () => import('../views/PromptCenter.vue'),
        meta: { title: '提示词总览', subtitle: '三体系统一视图 · 自动化 / 提示词库 / 阶段常量', group: 'AI配置', icon: 'Memo' }
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
        meta: { title: 'LLM 配置', subtitle: 'DeepSeek 等大模型一键生成 · 与手动模式并存', group: 'AI配置', icon: 'Cpu' }
      },
      {
        path: 'publish',
        name: 'Publish',
        component: () => import('../views/Publish.vue'),
        meta: { title: '发布自动化', subtitle: '浏览器自动化发布 · 人工审核闸门 · 凭证管理', group: '发布自动化', icon: 'Promotion' }
      },
      {
        path: 'browser-studio',
        name: 'BrowserStudio',
        component: () => import('../views/BrowserStudio.vue'),
        meta: { title: '浏览器工作室', subtitle: '豆包创作 + 搜狐号发布 全链路自动化 · 状态跟踪/失败重试/结果回溯', group: '发布自动化', icon: 'Monitor' }
      },
      {
        path: 'automation-studio',
        name: 'AutomationStudio',
        component: () => import('../views/AutomationStudio.vue'),
        meta: { title: '自动化指挥中心', subtitle: '自动化全流程可视化 · 每步提示词可编辑可复制 · 多专家协同', group: '发布自动化', icon: 'SetUp' }
      },
      {
        path: 'manual',
        name: 'Manual',
        component: () => import('../views/Manual.vue'),
        meta: { title: '操作手册', subtitle: '全流程复现指南 · 每步可复制给网页 AI 手动复现', group: '发布自动化', icon: 'Reading' }
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
        path: 'geo-canvas',
        name: 'GeoCanvas',
        component: () => import('../views/GeoCanvas.vue'),
        meta: { title: 'GEO 定位画布', subtitle: '三环定位法：人群 × 问题 × 优势', group: 'GEO 作战', icon: 'Aim' }
      },
      {
        path: 'geo-monitor',
        name: 'GeoMonitor',
        component: () => import('../views/GeoMonitor.vue'),
        meta: { title: 'AI推荐监测', subtitle: 'GEO 闭环：验证 AI 是否推荐我们', group: 'GEO 作战', icon: 'Monitor' }
      },
      {
        // 兜底路由：未知路径不再白屏，而是展示友好的 404 页面
        path: ':pathMatch(.*)*',
        name: 'NotFound',
        component: () => import('../views/NotFound.vue'),
        meta: { title: '页面不存在', subtitle: '', group: '' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
