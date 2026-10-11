<template>
  <div class="keyword-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button :icon="Upload" @click="batchRef?.open()">批量导入</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建关键词</el-button>
    </Teleport>

    <!-- 顶部：GEO 关键词/选题价值说明 + 指标 -->
    <section class="hero">
      <div class="hero__lead">
        <span class="hero__eyebrow"><el-icon><Key /></el-icon> GEO 作战 · 关键词与选题</span>
        <h2 class="hero__title">用关键词与选题，把「客户搜索意图」接进 GEO 内容生产</h2>
        <p class="hero__desc">关键词按分组管理、可批量导入；选题落进平台与账号矩阵。三者共同决定软文该打哪些词、发往哪里——是 GEO 命中搜索意图的抓手。</p>
      </div>
      <div class="hero__metrics">
        <div class="metric">
          <div class="metric__num">{{ keywords.length }}</div>
          <div class="metric__label">关键词</div>
        </div>
        <div class="metric metric--cat">
          <div class="metric__num">{{ groups.length }}</div>
          <div class="metric__label">分组</div>
        </div>
        <div class="metric metric--ok">
          <div class="metric__num">{{ topics.length }}</div>
          <div class="metric__label">选题</div>
        </div>
      </div>
    </section>

    <!-- 分段切换 -->
    <div class="section-tabs">
      <button class="section-tab" :class="{ active: activeTab === 'keyword' }" @click="activeTab = 'keyword'">
        <el-icon><Key /></el-icon> 关键词库
      </button>
      <button class="section-tab" :class="{ active: activeTab === 'topic' }" @click="activeTab = 'topic'">
        <el-icon><Tickets /></el-icon> 选题池
      </button>
      <button class="section-tab" :class="{ active: activeTab === 'matrix' }" @click="activeTab = 'matrix'">
        <el-icon><Grid /></el-icon> 矩阵视图
      </button>
    </div>

    <!-- 批量导入提示词板块（已抽到 views/keyword/ImportPromptBanner.vue） -->
    <ImportPromptBanner v-if="activeTab === 'keyword'" @open-batch="batchRef?.open()" />

    <!-- 关键词库（分组 + 排序 + 搜索） -->
    <!-- 两栏工作台容器见 components/layout/WorkbenchLayout.vue。
         本页左栏 232px、需要最小高度撑住短列表。 -->
    <WorkbenchLayout
      v-show="activeTab === 'keyword'"
      class="kw-layout"
      aside-width="232px"
      min-height="500px"
    >
      <template #aside>
        <GroupPanel
          v-model:active-group="activeGroup"
          :groups="groups"
          :total-count="keywords.length"
          :uncategorized-count="uncategorizedCount"
          @create="groupRef?.openCreate()"
          @edit="groupRef?.openEdit($event)"
          @remove="removeGroup"
          @reordered="groups = $event"
        />
      </template>
      <template #main>
        <KeywordItemPanel
          :keywords="keywords"
          :groups="groups"
          :active-group="activeGroup"
          :loading="loading"
          :focus-id="focusId"
          @edit="kwDialogRef?.openEdit($event)"
          @changed="loadAll"
        />
      </template>
    </WorkbenchLayout>

    <!-- 选题池（已抽到 views/keyword/TopicPool.vue） -->
    <TopicPool
      v-show="activeTab === 'topic'"
      :topics="topics"
      :keywords="keywords"
      :platforms="platforms"
      :accounts="accounts"
      :loading="loading"
      @create="topicDialogRef?.openCreate()"
      @edit="topicDialogRef?.openEdit($event)"
      @changed="loadAll"
    />

    <!-- 矩阵视图（已抽到 views/keyword/MatrixView.vue） -->
    <MatrixView v-show="activeTab === 'matrix'" :matrix="matrix" :loading="loading" />

    <!-- 弹窗（均已抽到 views/keyword/） -->
    <KeywordDialog ref="kwDialogRef" :groups="groups" :industry-id="industryId" @saved="loadAll" />
    <GroupDialog ref="groupRef" :industry-id="industryId" @saved="loadAll" />
    <TopicDialog
      ref="topicDialogRef"
      :keywords="keywords"
      :platforms="platforms"
      :accounts="accounts"
      :industry-id="industryId"
      @saved="loadAll"
    />
    <BatchImportDialog ref="batchRef" :groups="groups" :industry-id="industryId" @imported="loadAll" />
  </div>
</template>

<script setup>
/**
 * 关键词 —— 壳。
 *
 * 拆分后的分工（D5 沿用 D4/D5-1 的范式）：
 *   - 壳只管**跨面板的共享状态**（keywords / groups / topics / matrix / platforms / accounts、
 *     当前选中分组、分段）与**取数**，以及页面级布局（Teleport 动作 / hero / 分段 / 弹窗编排）。
 *   - 展示与「只作用于某个面板的交互」全部搬进子组件：
 *     GroupPanel（左栏）、KeywordItemPanel（右栏：搜索/排序/筛选/批量）、
 *     ImportPromptBanner（批量导入提示词板块）、TopicPool（选题池）、MatrixView（矩阵），
 *     以及 4 个弹窗（KeywordDialog / GroupDialog / TopicDialog / BatchImportDialog）。
 *   - 子组件一律**不直接改共享状态**：要么 emit 意图，要么（对自己专属的数据）自己发请求，
 *     完成后 emit `changed` 让壳重新拉一遍。
 *
 * 顺带收敛的重复：关键词类型（brand/product/long_tail/question）原先在**本文件里被抄了 4 遍**
 * （筛选下拉 / 弹窗下拉 / 批量导入下拉 / typeLabel），拆分只会把它复制进 3 个新组件，
 * 所以先收进 `constants/status.js`（KEYWORD_TYPE_*）。分组图标选项同理，收进 `constants/icons.js`。
 */
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Key, Tickets, Grid, Upload } from '@element-plus/icons-vue'
import { useFocusScroll } from '../composables/useFocusScroll'
import { useAppStore } from '../store/app'
import { keywordApi, keywordGroupApi, topicApi, platformApi, accountApi } from '../api'
import GroupPanel from './keyword/GroupPanel.vue'
import KeywordItemPanel from './keyword/KeywordItemPanel.vue'
import ImportPromptBanner from './keyword/ImportPromptBanner.vue'
import TopicPool from './keyword/TopicPool.vue'
import MatrixView from './keyword/MatrixView.vue'
import KeywordDialog from './keyword/KeywordDialog.vue'
import GroupDialog from './keyword/GroupDialog.vue'
import TopicDialog from './keyword/TopicDialog.vue'
import BatchImportDialog from './keyword/BatchImportDialog.vue'
import WorkbenchLayout from '../components/layout/WorkbenchLayout.vue'

const pageActionsTarget = inject('pageActionsTarget', null)
const route = useRoute()
const focusId = computed(() => route.query.focus)

const store = useAppStore()
const industryId = computed(() => Number(store.currentIndustryId) || 0)

const loading = ref(false)
const activeTab = ref('keyword')
const keywords = ref([])
const groups = ref([])
const topics = ref([])
const matrix = ref([])
const platforms = ref([])
const accounts = ref([])
const activeGroup = ref(null) // null=全部, -1=未分组, 否则 group_id

// 子组件句柄（壳只负责「谁来打开它」，弹窗自己管自己的表单与请求）
const kwDialogRef = ref(null)
const groupRef = ref(null)
const topicDialogRef = ref(null)
const batchRef = ref(null)

const uncategorizedCount = computed(() => keywords.value.filter((k) => k.group_id == null).length)

// ============ 取数 ============
async function loadAll() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const [k, g, t, p, a] = await Promise.all([
      keywordApi.list(store.currentIndustryId),
      keywordGroupApi.list(store.currentIndustryId),
      topicApi.list(store.currentIndustryId),
      platformApi.list(store.currentIndustryId),
      accountApi.list(store.currentIndustryId),
    ])
    keywords.value = k.data || []
    groups.value = g.data || []
    topics.value = t.data || []
    platforms.value = p.data || []
    accounts.value = a.data || []
  } finally {
    loading.value = false
  }
}

async function loadMatrix() {
  if (!store.currentIndustryId) return
  const res = await topicApi.matrix(store.currentIndustryId)
  matrix.value = res.data || []
}

// ============ 操作 ============
function openCreate() {
  // 若当前正选中某个真实分组，新建时预填它（「全部」/「未分组」不预填）
  const preset = activeGroup.value && activeGroup.value > 0 ? activeGroup.value : null
  kwDialogRef.value?.openCreate(preset)
}

async function removeGroup(g) {
  const tip = g.item_count > 0
    ? `确定删除分组「${g.name}」吗？该分组下的 ${g.item_count} 个关键词将变为「未分组」。`
    : `确定删除分组「${g.name}」吗？`
  await ElMessageBox.confirm(tip, '删除分组', { type: 'warning' })
  await keywordGroupApi.delete(g.id)
  ElMessage.success('分组已删除')
  if (activeGroup.value === g.id) activeGroup.value = null
  await loadAll()
}

watch(() => store.currentIndustryId, loadAll)
watch(activeTab, (v) => { if (v === 'matrix') loadMatrix() })
// 全局搜索跳转：定位关键词时确保停留在「关键词库」分页
watch(() => route.query.focus, (f) => { if (f) activeTab.value = 'keyword' }, { immediate: true })
useFocusScroll()
onMounted(loadAll)
</script>

<style scoped>
.keyword-view { display: flex; flex-direction: column; gap: 16px; }

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
.metric--ok .metric__num { color: var(--accent-emerald, #10b981); }

@media (max-width: 768px) {
  .hero { flex-direction: column; align-items: flex-start; }
  .hero__metrics { width: 100%; }
}

/* 关键词库：分组 + 列表布局。
   网格定义已收进 WorkbenchLayout（D7-2）—— 此前 `.kw-layout` 这个名字 Knowledge.vue
   也在用且列宽不同（220 vs 232），只能各写一份；现在宽度作为 prop 显式传给容器，
   同名类不再互相干扰（各自的 scoped 作用域 + 容器变量）。 */
.kw-layout { min-height: 500px; }

</style>
