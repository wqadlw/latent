<template>
  <div class="knowledge-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget && kbTab === 'items'">
      <el-dropdown @command="handleExport" trigger="click">
        <el-button :icon="Download">导出</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="json">导出为 JSON</el-dropdown-item>
            <el-dropdown-item command="csv">导出为 CSV</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button :icon="DataAnalysis" @click="showStats = !showStats">统计</el-button>
      <el-button type="warning" :icon="MagicStick" @click="seedDefaults" :loading="seeding">一键灌入默认论据</el-button>
      <el-button type="success" :icon="Upload" @click="batchRef?.open(activeCategory)">批量导入</el-button>
      <el-button type="primary" :icon="Plus" @click="itemRef?.openCreate(activeCategory)">新建知识点</el-button>
    </Teleport>

    <el-tabs v-model="kbTab" class="kb-tabs">
      <el-tab-pane label="知识点管理" name="items">
    <!-- 顶部：GEO 论据库价值说明 + 指标 -->
    <section class="hero">
      <div class="hero__lead">
        <span class="hero__eyebrow"><el-icon><Collection /></el-icon> GEO 作战 · 可引用论据库</span>
        <h2 class="hero__title">把行业知识沉淀为「可引用、可溯源」的论据</h2>
        <p class="hero__desc">知识库是 GEO 软文的论据底座：每条知识点都应带事实、来源与重要性，让 AI 在回答时优先引用我们、而非泛泛而谈。按分类管理，支持批量导入与拖拽排序。</p>
      </div>
      <div class="hero__metrics">
        <div class="metric">
          <div class="metric__num">{{ items.length }}</div>
          <div class="metric__label">知识点</div>
        </div>
        <div class="metric metric--cat">
          <div class="metric__num">{{ categories.length }}</div>
          <div class="metric__label">分类</div>
        </div>
        <div class="metric metric--ok">
          <div class="metric__num">{{ highCount }}</div>
          <div class="metric__label">高重要性</div>
        </div>
        <div class="metric metric--pub">
          <div class="metric__num">{{ publishedCount }}</div>
          <div class="metric__label">已发布</div>
        </div>
      </div>
    </section>

    <!-- 统计面板 -->
    <transition name="slide-down">
      <div v-if="showStats && stats" class="stats-bar">
        <div class="stat-item">
          <div class="stat-num">{{ stats.total }}</div>
          <div class="stat-label">知识点总数</div>
        </div>
        <div class="stat-item">
          <div class="stat-num">{{ stats.categories }}</div>
          <div class="stat-label">分类数</div>
        </div>
        <div class="stat-item">
          <div class="stat-num text-amber">{{ stats.by_importance?.high || 0 }}</div>
          <div class="stat-label">高重要性</div>
        </div>
        <div class="stat-item">
          <div class="stat-num text-green">{{ stats.by_status?.published || 0 }}</div>
          <div class="stat-label">已发布</div>
        </div>
        <div class="stat-item">
          <div class="stat-num text-gray">{{ stats.by_status?.draft || 0 }}</div>
          <div class="stat-label">草稿</div>
        </div>
        <div class="stat-item">
          <div class="stat-num">{{ stats.total_views || 0 }}</div>
          <div class="stat-label">总查看次数</div>
        </div>
      </div>
    </transition>

    <!-- 两栏工作台容器见 components/layout/WorkbenchLayout.vue。
         宽度/间距/对齐/窄屏单列都由它管，这里只声明「本页左栏 220px、不拉伸」。 -->
    <WorkbenchLayout class="kw-layout" aside-width="220px" align="start">
      <!-- 左：分类（已抽到 views/knowledge/CategoryPanel.vue） -->
      <template #aside>
        <CategoryPanel
          v-model:active-category="activeCategory"
          :categories="categories"
          :total-count="items.length"
          @create="categoryRef?.openCreate()"
          @edit="categoryRef?.openEdit($event)"
          @remove="removeCategory"
        />
      </template>

      <!-- 右：知识点列表（已抽到 views/knowledge/ItemPanel.vue） -->
      <template #main>
        <ItemPanel
          v-model:active-category="activeCategory"
          :items="items"
          :categories="categories"
          :loading="loading"
          @edit="itemRef?.openEdit($event)"
          @detail="detailRef?.open($event)"
          @items-reordered="items = $event"
          @changed="loadData"
        />
      </template>
    </WorkbenchLayout>
      </el-tab-pane>
      <el-tab-pane label="背景库" name="background">
        <BackgroundLibrary />
      </el-tab-pane>
    </el-tabs>

    <!-- 弹窗 / 抽屉（均已抽到 views/knowledge/） -->
    <CategoryDialog ref="categoryRef" :industry-id="industryId" @saved="loadCategories" />
    <KnowledgeItemDialog
      ref="itemRef"
      :categories="categories"
      :industry-id="industryId"
      @saved="loadData"
      @category-created="loadCategories"
    />
    <KnowledgeDetailDrawer
      ref="detailRef"
      :categories="categories"
      @edit="itemRef?.openEdit($event)"
      @loaded="onDetailLoaded"
    />
    <BatchImportDialog ref="batchRef" :categories="categories" :industry-id="industryId" @imported="loadData" />
  </div>
</template>

<script setup>
/**
 * 知识库 —— 壳。
 *
 * 拆分后的分工（D5 沿用 D4 的范式）：
 *   - 壳只管**跨面板的共享状态**（分类列表、知识点列表、当前选中分类、统计）
 *     与**取数**，以及页面级布局（Teleport 动作 / hero / 统计条 / 两栏容器）。
 *   - 展示与「只作用于某个面板的交互」全部搬进子组件：
 *     CategoryPanel（左栏）、ItemPanel（右栏：搜索/排序/标签过滤/批量/拖拽）、
 *     CategoryDialog / KnowledgeItemDialog / KnowledgeDetailDrawer / BatchImportDialog。
 *   - 子组件一律**不直接改共享状态**：要么 emit 意图，要么（对自己专属的数据）自己发请求。
 *
 * ⚠️ 本次拆分顺带修掉一个真缺陷：`seedDefaults()` 里调用的 `loadData()` **从未定义过**。
 * 于是「一键灌入默认论据」在接口成功之后抛 ReferenceError，被 catch 当成失败，
 * 用户看到「灌入失败」——**但数据其实已经写进去了**，列表还不刷新。
 * 现在 `loadData()` 有了正经定义，并作为「重新拉一遍」的统一入口。
 */
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Collection, Upload, Download, DataAnalysis, MagicStick } from '@element-plus/icons-vue'
import { useFocusScroll } from '../composables/useFocusScroll'
import { useAppStore } from '../store/app'
import { knowledgeApi } from '../api'
import { downloadBlob } from '../utils/download'
import BackgroundLibrary from '../components/knowledge/BackgroundLibrary.vue'
import CategoryPanel from './knowledge/CategoryPanel.vue'
import ItemPanel from './knowledge/ItemPanel.vue'
import CategoryDialog from './knowledge/CategoryDialog.vue'
import KnowledgeItemDialog from './knowledge/KnowledgeItemDialog.vue'
import KnowledgeDetailDrawer from './knowledge/KnowledgeDetailDrawer.vue'
import BatchImportDialog from './knowledge/BatchImportDialog.vue'
import WorkbenchLayout from '../components/layout/WorkbenchLayout.vue'

const pageActionsTarget = inject('pageActionsTarget', null)
const route = useRoute()
const focusId = computed(() => route.query.focus)

const store = useAppStore()
const industryId = computed(() => Number(store.currentIndustryId) || 0)

const kbTab = ref('items')
const loading = ref(false)
const seeding = ref(false)
const categories = ref([])
const items = ref([])
const activeCategory = ref(null)
const showStats = ref(false)
const stats = ref(null)

// 子组件句柄（壳只负责「谁来打开它」，弹窗自己管自己的表单与请求）
const categoryRef = ref(null)
const itemRef = ref(null)
const detailRef = ref(null)
const batchRef = ref(null)

const highCount = computed(() => items.value.filter((i) => i.importance === 'high').length)
const publishedCount = computed(() => items.value.filter((i) => i.status === 'published').length)

// ============ 取数 ============
async function loadCategories() {
  if (!store.currentIndustryId) return
  const res = await knowledgeApi.listCategories(store.currentIndustryId)
  categories.value = res.data || []
}

async function loadItems() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const res = await knowledgeApi.listItems(store.currentIndustryId, '', '')
    items.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  if (!store.currentIndustryId) return
  try {
    const res = await knowledgeApi.stats(store.currentIndustryId)
    stats.value = res.data
  } catch {}
}

/** 「把这一页重新拉一遍」的统一入口（原先被 seedDefaults 调用却不存在）。 */
async function loadData() {
  await loadCategories()
  await loadItems()
  if (showStats.value) await loadStats()
}

// ============ 操作 ============
async function removeCategory(c) {
  const tip = c.item_count > 0
    ? `确定删除分类「${c.name}」吗？该分类下的 ${c.item_count} 条知识点将变为「未分类」。`
    : `确定删除分类「${c.name}」吗？`
  await ElMessageBox.confirm(tip, '删除分类', { type: 'warning' })
  try {
    await knowledgeApi.deleteCategory(c.id)
    ElMessage.success('分类已删除')
    if (activeCategory.value === c.id) activeCategory.value = null
    await loadCategories()
    if (showStats.value) await loadStats()
  } catch {}
}

/** 详情抽屉取回最新数据后，把列表里的查看次数同步一下（列表是摘要数据）。 */
function onDetailLoaded(fresh) {
  const idx = items.value.findIndex((i) => i.id === fresh.id)
  if (idx >= 0) items.value[idx].view_count = fresh.view_count
}

async function handleExport(fmt) {
  try {
    const res = await knowledgeApi.exportItems(store.currentIndustryId, fmt, activeCategory.value)
    // 后端已在 CSV 开头写了 BOM（见 routers/knowledge.py），这里原样透传即可。
    downloadBlob(new Blob([res], { type: fmt === 'json' ? 'application/json' : 'text/csv' }), `knowledge_items.${fmt}`)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

async function seedDefaults() {
  try {
    await ElMessageBox.confirm(
      '将为「可引用论据库」灌入 GEO 默认论据模板（claim+evidence+source 示例，按标题去重，已有则跳过）。灌入后请把示例替换为贵司真实数据。',
      '一键灌入默认论据',
      { type: 'info' },
    )
  } catch {
    return
  }
  seeding.value = true
  try {
    const res = await knowledgeApi.seedDefaults(store.currentIndustryId)
    ElMessage.success(res.data.msg || '灌入完成')
    await loadData()
  } catch (e) {
    ElMessage.error('灌入失败：' + (e?.response?.data?.detail || '请重试'))
  } finally {
    seeding.value = false
  }
}

watch(() => store.currentIndustryId, async () => {
  activeCategory.value = null
  await loadData()
})

watch(showStats, async (v) => {
  if (v && !stats.value) await loadStats()
})

onMounted(loadData)
// 全局搜索跳转：滚动并高亮定位到具体知识点
useFocusScroll()
</script>

<style scoped>
.knowledge-view { display: flex; flex-direction: column; gap: 16px; }

/* ===== hero ===== */
.hero {
  display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
  background: linear-gradient(135deg, rgba(99,102,241,0.10), rgba(20,184,166,0.07));
  border: 1px solid var(--border-light); border-left: 4px solid #6366f1;
  border-radius: var(--radius-lg); padding: 18px 22px;
}
.hero__lead { flex: 1; min-width: 320px; display: flex; flex-direction: column; gap: 6px; }
.hero__eyebrow { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; color: #6366f1; letter-spacing: 0.03em; }
.hero__eyebrow .el-icon { font-size: 15px; }
.hero__title { margin: 0; font-size: 17px; font-weight: 700; color: var(--text-primary); line-height: 1.4; }
.hero__desc { margin: 0; font-size: 12.5px; color: var(--text-tertiary); line-height: 1.6; max-width: 720px; }
.hero__metrics { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.metric { min-width: 76px; text-align: center; padding: 8px 12px; background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-md); }
.metric__num { font-size: 20px; font-weight: 700; color: var(--text-primary); line-height: 1.1; }
.metric__label { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
.metric--cat .metric__num { color: var(--brand-600, #6366f1); }
.metric--ok .metric__num { color: #f59e0b; }
.metric--pub .metric__num { color: var(--accent-emerald, #10b981); }

@media (max-width: 768px) {
  .hero { flex-direction: column; align-items: flex-start; }
  .hero__metrics { width: 100%; }
}

.stats-bar {
  display: flex; gap: 24px; padding: 16px 24px;
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-sm);
}
.stat-item { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.stat-num { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.stat-label { font-size: 12px; color: var(--text-tertiary); }
.text-amber { color: #f59e0b; }
.text-green { color: #10b981; }
.text-gray { color: #94a3b8; }

/* .kw-layout 的网格定义已收进 WorkbenchLayout（D7-2）。
   类名**刻意保留** —— 它是验收脚本的钩子，也方便在 DevTools 里定位本页布局。 */

.slide-down-enter-active, .slide-down-leave-active { transition: all 0.3s ease; }
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; transform: translateY(-10px); }

</style>
