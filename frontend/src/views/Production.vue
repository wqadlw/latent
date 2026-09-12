<template>
  <div class="production-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button type="primary" :icon="Plus" @click="createTask">新建生产任务</el-button>
      <el-button :icon="Refresh" @click="loadTasks">刷新</el-button>
    </Teleport>

    <div class="prod-layout">
      <!-- 左侧任务列表 -->
      <div class="task-panel">
        <div class="panel-head">
          <span class="panel-title">生产任务</span>
          <el-tag size="small" round>{{ tasks.length }}</el-tag>
        </div>
        <VirtualList
          class="task-list"
          v-loading="loadingTasks"
          :items="tasks"
          :row-height="92"
          :gap="10"
          :get-key="(it) => it.id"
          #default="{ item }"
        >
          <div
            class="task-card"
            :class="['task-card--' + (item.status || 'draft'), { active: currentTask?.id === item.id }]"
            @click="selectTask(item)"
          >
            <div class="task-card__header">
              <span class="task-card__title">{{ item.title || `任务 #${item.id}` }}</span>
              <div class="task-card__actions">
                <el-button
                  class="task-card__del"
                  size="small"
                  type="danger"
                  text
                  :icon="Delete"
                  title="删除任务"
                  @click.stop="handleDelete(item)"
                />
                  <el-tag :type="statusType(item.status)" size="small" effect="light">{{ statusText(item.status) }}</el-tag>
                  <el-tag v-if="item.geo_score != null" size="small" effect="plain" type="success" class="geo-score-badge">GEO {{ item.geo_score }}</el-tag>
                </div>
            </div>
            <div class="task-card__meta">
              <span><el-icon><OfficeBuilding /></el-icon> {{ item.industry_snapshot || '未选行业' }}</span>
              <span v-if="item.platform_snapshot"><el-icon><Connection /></el-icon> {{ item.platform_snapshot }}</span>
            </div>
              <div class="task-card__progress">
              <div class="progress-bar"><div class="progress-fill" :style="{ width: (item.current_step / 10 * 100) + '%' }"></div></div>
              <span class="progress-text">{{ item.current_step }}/10</span>
            </div>
          </div>
        </VirtualList>
        <div v-if="!loadingTasks && tasks.length === 0" class="empty-tip">
          <el-icon class="empty-icon"><DocumentAdd /></el-icon>
          <div>暂无生产任务<br/>点击右上角「新建生产任务」开始</div>
        </div>
      </div>

      <!-- 右侧工作面板 -->
      <div class="workspace-panel">
        <template v-if="currentTask">
          <!-- 步骤导航 -->
          <div class="steps-nav">
            <div
              v-for="step in steps"
              :key="step.no"
              class="step-node"
              :class="{ active: currentTask.current_step === step.no, done: currentTask.current_step > step.no }"
              @click="goStep(step.no)"
            >
              <div class="step-circle">
                <el-icon v-if="currentTask.current_step > step.no"><Check /></el-icon>
                <span v-else>{{ step.no }}</span>
              </div>
              <div class="step-text">
                <div class="step-name">{{ step.name }}</div>
                <div class="step-hint">{{ step.hint }}</div>
              </div>
            </div>
          </div>

          <!-- 步骤内容 -->
          <div class="step-content">
            <!-- 步骤 1：行业 -->
            <StepIndustry
              v-if="currentTask.current_step === 1"
              :industries="store.industries"
              :selected-id="currentTask.industry_id"
              @select="saveStep1"
            />

            <!-- 步骤 2：平台 -->
            <StepPlatform
              v-else-if="currentTask.current_step === 2"
              :platforms="options.platforms"
              :selected-id="currentTask.platform_id"
              :loading="loadingOptions"
              :compliance-tag-type="complianceTagType"
              :platform-meta="platformMeta"
              @select="saveStep2"
            />

            <!-- 步骤 3：人设账号（已抽取为 StepPersona） -->
            <StepPersona
              v-else-if="currentTask.current_step === 3"
              :options="options" :current-task="currentTask" :loading-options="loadingOptions"
              :save-step3-account="saveStep3Account" :save-step3-persona="saveStep3Persona"
              :get-persona-name="getPersonaName" :get-platform-name="getPlatformName"
              :has-any-rules="hasAnyRules" :all-rules-selected="allRulesSelected"
              :toggle-select-all-rules="toggleSelectAllRules" :selected-rule-total="selectedRuleTotal"
              :rule-group-list="ruleGroupList" :selected-rule-breakdown="selectedRuleBreakdown"
              :selected-rule-ids="selectedRuleIds" :toggle-rule="toggleRule"
            />

            <!-- 步骤 4：确定目标客户需求（已抽取为 StepDemand） -->
            <StepDemand
              v-else-if="currentTask.current_step === 4"
              :options="options" :current-task="currentTask" :step4-needs="step4Needs"
              :save-draft="saveDraft" :loading-options="loadingOptions"
            />

            <!-- 步骤 5：关键词 & 知识点 -->
            <Step5
              v-else-if="currentTask.current_step === 5"
              :options="options" :loading-options="loadingOptions"
              :selected-keyword-ids="selectedKeywordIds" :selected-knowledge-ids="selectedKnowledgeIds"
              :toggle-keyword="toggleKeyword" :toggle-knowledge="toggleKnowledge"
              :clear-knowledge="clearKnowledge" :toggle-category-all="toggleCategoryAll"
              :preview-knowledge="previewKnowledge"
            />

            <!-- 步骤 6：大纲（已抽取为 StepOutline） -->
            <StepOutline
              v-else-if="currentTask.current_step === 6"
              :current-task="currentTask" :loading-options="loadingOptions" :rendered-prompt="renderedPrompt"
              :gen-loading="genLoading" :selected-rule-total="selectedRuleTotal" :selected-rule-breakdown="selectedRuleBreakdown"
              :selected-knowledge-items="selectedKnowledgeItems" :selected-knowledge-summary="selectedKnowledgeSummary"
              :writing-prompts="writingPrompts" :render-prompt="renderPrompt" :generate-by-a-i="generateByAI"
              :copy-rendered-prompt="copyRenderedPrompt" :open-versions="openVersions"
              :toggle-knowledge="toggleKnowledge" :export-knowledge-material="exportKnowledgeMaterial"
            />

            <!-- 步骤 7：生成初稿（已抽取为 StepSingleFlow） -->
            <StepSingleFlow
              v-else-if="currentTask.current_step === 7"
              :no="7" title="生成文章初稿" desc="选择初稿写作提示词 + 上一步的大纲，生成第一版 AI 初稿"
              category="draft" prompt-field="draft_prompt_id" content-field="draft_content"
              prompt-label="初稿写作提示词" content-label="AI 生成的初稿（粘贴回填）"
              version-key="draft" content-placeholder="将 AI 工具生成的初稿粘贴到这里"
              :current-task="currentTask" :loading-options="loadingOptions" :rendered-prompt="renderedPrompt"
              :gen-loading="genLoading" :selected-rule-total="selectedRuleTotal" :selected-rule-breakdown="selectedRuleBreakdown"
              :writing-prompts="writingPrompts" :render-prompt="renderPrompt" :generate-by-a-i="generateByAI"
              :copy-rendered-prompt="copyRenderedPrompt" :open-versions="openVersions"
            />

            <!-- 步骤 8：AI 洗稿精修（已抽取为 StepSingleFlow） -->
            <StepSingleFlow
              v-else-if="currentTask.current_step === 8"
              :no="8" title="AI 洗稿精修" desc="选择洗稿提示词 + 初稿，生成去 AI 味精修稿"
              category="rewrite" prompt-field="rewrite_prompt_id" content-field="rewrite_content"
              prompt-label="洗稿提示词" content-label="AI 生成的精修稿（粘贴回填）"
              version-key="rewrite" content-placeholder="将 AI 工具生成的精修稿粘贴到这里"
              :current-task="currentTask" :loading-options="loadingOptions" :rendered-prompt="renderedPrompt"
              :gen-loading="genLoading" :selected-rule-total="selectedRuleTotal" :selected-rule-breakdown="selectedRuleBreakdown"
              :writing-prompts="writingPrompts" :render-prompt="renderPrompt" :generate-by-a-i="generateByAI"
              :copy-rendered-prompt="copyRenderedPrompt" :open-versions="openVersions"
            />

            <!-- 步骤 9：安全发布 & GEO 筛选（已抽取为 StepFinal，内含 StepGeoGate） -->
            <StepFinal
              v-else-if="currentTask.current_step === 9"
              :current-task="currentTask" :loading-options="loadingOptions" :rendered-prompt="renderedPrompt"
              :gen-loading="genLoading" :selected-rule-total="selectedRuleTotal" :selected-rule-breakdown="selectedRuleBreakdown"
              :writing-prompts="writingPrompts" :render-prompt="renderPrompt" :generate-by-a-i="generateByAI"
              :copy-rendered-prompt="copyRenderedPrompt" :open-versions="openVersions"
              :geo-scoring="geoScoring" :finalizing="finalizing" :geo-result="geoResult"
              :has-final-content="hasFinalContent" :finalize-import-text="finalizeImportText"
              :set-finalize-import-text="setFinalizeImportText" :finalize-result="finalizeResult"
              :geo-suggestion-prompts="geoSuggestionPrompts" :geo-dim-label="geoDimLabel"
              :mind-dim-label="mindDimLabel" :copy-suggestion="copySuggestion"
              :run-local-geo-score="runLocalGeoScore" :run-geo-finalize="runGeoFinalize"
              :copy-text="copyText" :open-publish-dialog="openPublishDialog"
            />

            <!-- 步骤 10：文章配图（已抽取为 StepIllustration） -->
            <StepIllustration
              v-else-if="currentTask.current_step === 10"
              :options="options" :current-task="currentTask" :save-draft="saveDraft"
              :illu-state="illuState" :current-recommendation="currentRecommendation" :recommendation-method="recommendationMethod"
            />

            <!-- 步骤 11（GEO 评分闸门）已合并进第 9 步「安全发布 & GEO 筛选」 -->
          </div>

          <VersionHistoryDialog v-model="versionDialog" :list="versionList" :step="versionStep" @restore="restoreVersion" />

          <!-- 底部操作栏 -->
          <div class="action-bar">
            <el-button :icon="ArrowLeft" @click="prevStep" :disabled="currentTask.current_step <= 1">上一步</el-button>
            <div class="action-center">
              <span class="step-indicator">第 {{ currentTask.current_step }} 步 / 共 10 步</span>
            </div>
            <div class="action-right">
              <el-button :icon="Document" @click="saveDraft">保存草稿</el-button>
              <el-button v-if="currentTask.current_step < 9" type="primary" @click="nextStep">
                下一步 <el-icon><ArrowRight /></el-icon>
              </el-button>
              <el-button v-else-if="currentTask.current_step === 9" type="success" :icon="Promotion" @click="publishTask">发布文章</el-button>
            </div>
          </div>
        </template>

        <div v-else class="empty-workspace">
          <el-icon class="empty-icon"><DocumentAdd /></el-icon>
          <div class="empty-title">请从左侧选择或创建生产任务</div>
          <div class="empty-desc">10 步标准化流程：行业 → 平台 → 定人设 → 确定目标客户需求(GEO) → 关键词/知识点 → 大纲 → 初稿 → 洗稿 → 安全发布 & GEO 筛选 → 配图</div>
        </div>

      </div>
    </div>
  </div>

  <KnowledgePreviewDrawer
    v-model="previewDrawer"
    :item="previewKnowledgeItem"
    :is-selected="selectedKnowledgeIds.includes(previewKnowledgeItem?.id)"
    @toggle="onPreviewToggle"
  />

  <CustomVarDialog v-model="cvarDialog" :list="cvarList" @confirm="confirmCvar" />

  <OneClickGenerateResult
    v-model="genDialogVisible"
    :data="genData"
    :step="genStep"
    :label-map="CAT_LABEL"
    :accepting="genAccepting"
    @copy="copyGenText"
    @accept="acceptGen"
  />

  <CreatePublishTaskDialog
    v-model="publishDialog"
    :form="publishForm"
    :platforms="publishPlatforms"
    :saving="publishSaving"
    @platform-change="onPublishPlatformChange"
    @create="createPublishTask"
  />
</template>

<script setup>
import './production/steps/step-shared.css'
import { ref, reactive, onMounted, h, computed, watch, inject } from 'vue'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Refresh, MagicStick, Check, ArrowLeft, ArrowRight, Clock,
  Document, Promotion, OfficeBuilding, Connection, CircleCheckFilled, DocumentAdd, CircleCheck,
  DocumentCopy, Upload,
  Search, View, Close, CopyDocument, ArrowDown, Delete, SortUp, SortDown,
  Folder, Reading, Notebook, Box, ChatDotRound, Flag, Collection, Files,
  Aim, Cpu, ShoppingCart, User, Avatar, UserFilled, WarningFilled,
} from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { productionApi, knowledgeApi, publishApi } from '../api'
import VirtualList from '../components/VirtualList.vue'
import EmptyState from '../components/EmptyState.vue'
import VersionHistoryDialog from '../components/production/VersionHistoryDialog.vue'
import KnowledgePreviewDrawer from '../components/production/KnowledgePreviewDrawer.vue'
import CustomVarDialog from '../components/production/CustomVarDialog.vue'
import OneClickGenerateResult from '../components/production/OneClickGenerateResult.vue'
import CreatePublishTaskDialog from '../components/production/CreatePublishTaskDialog.vue'
import StepHeader from '../components/production/StepHeader.vue'
import StepIndustry from './production/steps/StepIndustry.vue'
import StepPlatform from './production/steps/StepPlatform.vue'
import StepSingleFlow from '../components/production/StepSingleFlow.vue'
import StepOutline from './production/steps/StepOutline.vue'
import StepFinal from './production/steps/StepFinal.vue'
import Step5 from './production/steps/Step5.vue'
import StepIllustration from './production/steps/StepIllustration.vue'
import StepPersona from './production/steps/StepPersona.vue'
import StepDemand from './production/steps/StepDemand.vue'

const store = useAppStore()
const loadingTasks = ref(false)
const loadingOptions = ref(false)
const tasks = ref([])
const currentTask = ref(null)
const options = reactive({ platforms: [], accounts: [], personas: [], keywords: [], prompts: {}, knowledge_grouped: [], rules: {} })
// 平台 id → 名称：账号接口只返回 platform_id，需结合 options.platforms 本地映射
function getPlatformName(id) {
  if (!id) return ''
  return options.platforms.find(p => p.id === id)?.name || ''
}
// 合规等级 → Tag 类型
function complianceTagType(level) {
  return level >= 3 ? 'danger' : level >= 2 ? 'warning' : 'success'
}
// 解析平台 config（features / ai_weight / marketing）
function platformMeta(p) {
  try { return JSON.parse((p && p.config) || '{}') } catch { return {} }
}
// 人设 id → 名称（账号绑定人设展示用）
function getPersonaName(id) {
  if (!id) return ''
  return (options.personas || []).find(p => p.id === id)?.name || ''
}
const selectedKeywordIds = ref([])
const selectedKnowledgeIds = ref([])
const renderedPrompt = ref('')
// v4 第8步：文章配图——配图状态（属于任务持久化数据，由父持有，StepIllustration 就地修改）
const illuState = reactive({ plan: null, promptId: 0, style: '', method: 'ai' })
// 当前配图建议（已生成的优先，否则用 options 里的预计算建议）
const currentRecommendation = computed(() => {
  return illuState.plan?.recommendation
    || options.recommendation
    || { method: 'ai', reason: '根据平台与文章内容，建议优先 AI 生图以统一风格、规避版权风险。' }
})
const recommendationMethod = computed(() => currentRecommendation.value?.method || 'ai')

// v4 新增：第4步搜索与筛选
const previewKnowledgeItem = ref(null)
const previewDrawer = ref(false)
// v5 新增：第3步规则约束——选定规则注入提示词引导 AI 写作
const selectedRuleIds = ref([])
const ruleTypeMeta = {
  ai_seo: { label: 'AI SEO 规则', color: '#6366f1', desc: '优化关键词布局与搜索收录' },
  anti_ai: { label: '去 AI 味', color: '#a855f7', desc: '消除机器套话，更像真人写作' },
  compliance: { label: '平台合规', color: '#f59e0b', desc: '规避极限词与违规风险' },
}
const ruleTypeOrder = ['ai_seo', 'anti_ai', 'compliance']
// 仅展示该行业下存在规则的类型分组
const ruleGroupList = computed(() => {
  const rb = options.rules || {}
  return ruleTypeOrder
    .filter(rt => rb[rt] && rb[rt].length)
    .map(rt => ({ type: rt, meta: ruleTypeMeta[rt], items: rb[rt] }))
})
const hasAnyRules = computed(() => ruleGroupList.value.length > 0)
// 已选规则按类型计数（用于在写作步骤反馈「已应用规则」）
const selectedRuleBreakdown = computed(() => {
  const rb = options.rules || {}
  const ids = new Set(selectedRuleIds.value)
  const b = { ai_seo: 0, anti_ai: 0, compliance: 0 }
  for (const rt of ruleTypeOrder) {
    for (const r of (rb[rt] || [])) if (ids.has(r.id)) b[rt]++
  }
  return b
})
const selectedRuleTotal = computed(() => selectedRuleBreakdown.value.ai_seo + selectedRuleBreakdown.value.anti_ai + selectedRuleBreakdown.value.compliance)

// 某分类是否已被全选
function isCategoryAllSelected(sec) {
  if (!sec.items.length) return false
  return sec.items.every(ki => selectedKnowledgeIds.value.includes(ki.id))
}

// 全选 / 取消全选 某分类
function toggleCategoryAll(sec) {
  const ids = sec.items.map(ki => ki.id)
  const set = new Set(selectedKnowledgeIds.value)
  if (isCategoryAllSelected(sec)) {
    ids.forEach(id => set.delete(id))
  } else {
    ids.forEach(id => set.add(id))
  }
  selectedKnowledgeIds.value = Array.from(set)
}
// v4 新增：已选知识点详情列表（附带所属分类，用于右侧面板反馈）
const selectedKnowledgeItems = computed(() => {
  const result = []
  const seen = new Set()
  for (const g of (options.knowledge_grouped || [])) {
    for (const ki of (g.items || [])) {
      if (selectedKnowledgeIds.value.includes(ki.id) && !seen.has(ki.id)) {
        seen.add(ki.id)
        result.push({ ...ki, categoryId: g.category.id, categoryName: g.category.name })
      }
    }
  }
  return result
})
// 已选知识点概览（数量 + 覆盖分类数）
const selectedKnowledgeSummary = computed(() => {
  const cats = new Set()
  selectedKnowledgeItems.value.forEach(ki => { if (ki.categoryId) cats.add(ki.categoryId) })
  return { count: selectedKnowledgeItems.value.length, categoryCount: cats.size }
})
// 导出已选知识点为大纲素材（拼成文本，供 AI 直接利用）
function exportKnowledgeMaterial() {
  const items = selectedKnowledgeItems.value
  if (!items.length) { ElMessage.warning('请先选择知识点'); return }
  const lines = items.map((ki, i) => {
    const body = ki.summary || (ki.content || '').slice(0, 120)
    return body ? `${i + 1}. ${ki.title}\n   ${body}` : `${i + 1}. ${ki.title}`
  })
  const text = `【大纲素材】以下是本文需覆盖的知识点：\n\n${lines.join('\n\n')}`
  navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制大纲素材，可粘贴给 AI'))
}

const clearKnowledge = () => { selectedKnowledgeIds.value = [] }


const previewKnowledge = (ki) => {
  previewKnowledgeItem.value = ki
  previewDrawer.value = true
}
function onPreviewToggle(id) {
  toggleKnowledge(id)
  previewDrawer.value = false
}

const steps = [
  { no: 1, name: '选行业', hint: 'Industry' },
  { no: 2, name: '选平台', hint: 'Platform' },
  { no: 3, name: '定人设', hint: 'Persona' },
  { no: 4, name: '目标客户需求', hint: 'GEO 作战' },
  { no: 5, name: '关键词&知识点', hint: 'Keywords & Knowledge' },
  { no: 6, name: '生成大纲', hint: 'Outline' },
  { no: 7, name: '生成初稿', hint: 'Draft' },
  { no: 8, name: 'AI洗稿', hint: 'Rewrite' },
  { no: 9, name: '安全发布 & GEO 筛选', hint: 'Safety & GEO' },
  { no: 10, name: '配图', hint: 'Illustration' },
]

const statusType = (s) => ({ draft: 'info', processing: 'warning', done: 'success', archived: 'info' }[s] || 'info')
const statusText = (s) => ({ draft: '草稿', processing: '进行中', done: '已完成', archived: '已归档' }[s] || s)

// ========== 版本 / 历史管理 ==========
const versionDialog = ref(false)
const versionList = ref([])
const versionStep = ref('')
function currentVersionStep() {
  const s = currentTask.value?.current_step
  if (s === 6) return 'outline'
  if (s === 7) return 'draft'
  if (s === 8) return 'rewrite'
  if (s === 9) return 'final'
  return ''
}
async function openVersions(step) {
  if (!currentTask.value) return
  versionStep.value = step
  versionDialog.value = true
  versionList.value = []
  const res = await productionApi.versions(currentTask.value.id, step)
  versionList.value = res.data || []
}
async function restoreVersion(v) {
  try {
    await ElMessageBox.confirm(`确定回滚到 v${v.version_no} 吗？当前内容将被覆盖`, '回滚确认', { type: 'warning' })
  } catch { return }
  await productionApi.restoreVersion(currentTask.value.id, v.id)
  const field = { outline: 'outline_content', draft: 'draft_content', rewrite: 'rewrite_content', safety: 'safety_report', final: 'final_content' }[v.step]
  if (field && currentTask.value) currentTask.value[field] = v.content
  ElMessage.success('已回滚到该版本')
  versionDialog.value = false
}

async function loadTasks() {
  if (!store.currentIndustryId) return
  loadingTasks.value = true
  try {
    const res = await productionApi.list({ industry_id: store.currentIndustryId })
    tasks.value = res.data || []
  } finally {
    loadingTasks.value = false
  }
}

async function createTask() {
  if (!store.currentIndustryId) { ElMessage.warning('请先选择行业'); return }
  const res = await productionApi.create({
    industry_id: store.currentIndustryId,
    title: `软文任务 ${new Date().toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}`,
  })
  ElMessage.success('已创建新任务')
  await loadTasks()
  selectTask(res.data)
}

async function handleDelete(t) {
  try {
    await ElMessageBox.confirm(
      `确定要删除「${t.title || '任务 #' + t.id}」吗？删除后不可恢复。`,
      '删除生产任务',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
    )
  } catch {
    return
  }
  await productionApi.delete(t.id)
  ElMessage.success('已删除任务')
  // 若删除的是当前打开的任务，回退到列表第一项或清空
  if (currentTask.value && currentTask.value.id === t.id) {
    currentTask.value = null
    illuState.plan = null
  }
  await loadTasks()
}

async function selectTask(t) {
  currentTask.value = { ...t }
  selectedKeywordIds.value = t.keyword_ids ? t.keyword_ids.split(',').filter(Boolean).map(Number) : []
  selectedKnowledgeIds.value = t.knowledge_item_ids ? t.knowledge_item_ids.split(',').filter(Boolean).map(Number) : []
  selectedRuleIds.value = t.rule_ids ? t.rule_ids.split(',').filter(Boolean).map(Number) : []
  // 第4步：按任务已存 target_needs 解析核心需求（画像/意图/必含信号/痛点）
  Object.assign(step4Needs, parseTargetNeeds(t.target_needs))
  renderedPrompt.value = ''
  // 第8步：载入已保存的配图方案（后端存储为 { meta, recommendation, plan }，兼容旧版数组）
  illuState.plan = null
  illuState.promptId = 0
  illuState.style = ''
  if (t.illustration_plan) {
    try {
      const parsed = JSON.parse(t.illustration_plan)
      if (Array.isArray(parsed)) {
        illuState.plan = { plan: parsed }
      } else {
        illuState.plan = parsed
        illuState.promptId = parsed.meta?.prompt_id || 0
        illuState.style = parsed.meta?.style || ''
      }
    } catch { illuState.plan = null }
  }
  if (t.industry_id) await loadOptions()
  // 进入第10步时，默认按配图建议选择模式（AI 生图 / 网络搜图）
  if (currentTask.value.current_step === 10) {
    illuState.method = recommendationMethod.value || 'ai'
  }
}

async function loadOptions() {
  if (!currentTask.value?.id) return
  loadingOptions.value = true
  try {
    const res = await productionApi.options(currentTask.value.id)
    Object.assign(options, res.data)
  } finally {
    loadingOptions.value = false
  }
}

function goStep(no) {
  if (no <= currentTask.value.current_step + 1) {
    currentTask.value.current_step = no
    renderedPrompt.value = ''
  } else {
    ElMessage.warning('请先完成前面的步骤')
  }
}

function prevStep() {
  if (currentTask.value.current_step > 1) {
    currentTask.value.current_step--
    renderedPrompt.value = ''
  }
}

async function nextStep() {
  await saveDraft(true)
  if (currentTask.value.current_step < 9) {
    currentTask.value.current_step++
    renderedPrompt.value = ''
  }
}

async function saveDraft(silent = false) {
  if (!currentTask.value?.id) return
  // 只发送业务字段，避免把 create_time/update_time 等字符串时间写回后端 DateTime 列
  const { id, create_time, update_time, is_deleted, ...rest } = currentTask.value
  const data = { ...rest, keyword_ids: selectedKeywordIds.value.join(','), knowledge_item_ids: selectedKnowledgeIds.value.join(','), rule_ids: selectedRuleIds.value.join(',') }
  await productionApi.update(currentTask.value.id, data)
  if (!silent) ElMessage.success('草稿已保存')
}

async function saveStep1(ind) {
  currentTask.value.industry_id = ind.id
  currentTask.value.industry_snapshot = ind.name
  await saveDraft(true)
  await loadOptions()
  ElMessage.success(`已选择行业：${ind.name}`)
}

async function saveStep2(p) {
  currentTask.value.platform_id = p.id
  currentTask.value.platform_snapshot = p.name
  await saveDraft(true)
  await loadOptions()   // 重新拉取选项，使第3步账号按所选平台过滤（与账号人设绑定）
  ElMessage.success(`已选择平台：${p.name}`)
}

async function saveStep3Account(a) {
  currentTask.value.account_id = a.id
  currentTask.value.account_snapshot = a.account_name
  await saveDraft(true)
}

async function saveStep3Persona(p) {
  currentTask.value.persona_id = p.id
  currentTask.value.persona_snapshot = p.name
  await saveDraft(true)
  ElMessage.success('人设账号已确定')
}

// ========== 步骤 4：确定目标客户需求（重设计：画像 + 意图问题 + 核心需求，驱动后续生成） ==========
// 解析任务保存的 target_needs（容错：字段缺失/格式错误时回退默认值）
function parseTargetNeeds(raw) {
  const def = { expected_recommendation: '', required_signals: [], must_address_pains: [] }
  if (!raw) return def
  try {
    const p = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (p && typeof p === 'object') {
      def.expected_recommendation = p.expected_recommendation || ''
      def.required_signals = Array.isArray(p.required_signals) ? p.required_signals : []
      def.must_address_pains = Array.isArray(p.must_address_pains) ? p.must_address_pains : []
    }
  } catch (e) { /* 忽略损坏数据，使用默认 */ }
  return def
}
// 第4步核心需求（随任务加载/切换实时解析）
const step4Needs = reactive(parseTargetNeeds(currentTask.value?.target_needs))

// ========== 步骤 11：GEO 评分闸门 ==========
const geoScoring = ref(false)
const geoResult = ref(null)
const finalizing = ref(false)
const finalizeResult = ref(null)
const finalizeImportText = ref('')
function setFinalizeImportText(v) { finalizeImportText.value = v }
const hasFinalContent = computed(() =>
  !!(currentTask.value?.final_content || currentTask.value?.rewrite_content || currentTask.value?.draft_content)
)
function geoDimLabel(k) {
  return {
    entity_signals: '品牌实体信号', fact_density: '事实密度', intent_coverage: '意图覆盖',
    qa_form: '问答形态', structure: '结构可提取', attributable: '信号可归属',
  }[k] || k
}


// 第9步终检合并端点：解析 AI 返回的「安全·GEO 终稿」结构化结果，评分（优先 AI 分，缺失本地兜底）+ 出稿一步到位
async function runGeoFinalize() {
  if (!currentTask.value?.id) return
  if (!finalizeImportText.value.trim()) { ElMessage.warning('请先粘贴 AI 返回的完整结果'); return }
  finalizing.value = true
  try {
    const res = await productionApi.geoFinalize(currentTask.value.id, finalizeImportText.value)
    const d = res.data
    finalizeResult.value = d
    // 同步写回任务主记录，使上方主文本框与发布逻辑立即生效
    currentTask.value.final_title = d.final_title
    currentTask.value.final_content = d.final_content
    currentTask.value.geo_score = d.geo_score
    currentTask.value.safety_report = d.safety_report || ''
    await saveDraft(true)
    const gate = d.quality_gate
    if (gate && !gate.gate_pass) {
      const n = (gate.issues && gate.issues.length) || 0
      ElMessage.warning(`终检完成，但平台合规闸门未通过（${n} 项待整改），详见下方红色横幅；GEO 评分 ${d.geo_score}/100`)
    } else if (d.geo_score >= 70) {
      ElMessage.success(`终检完成，合规闸门通过 + GEO ${d.geo_score}/100 已达标，可直接复制发布`)
    } else {
      ElMessage.warning(`终检完成，合规闸门通过；GEO 评分 ${d.geo_score}/100 未达 70，建议优化后重跑`)
    }
  } catch (e) {
    ElMessage.error('终检导入失败：' + (e?.response?.data?.detail || e?.message || ''))
  } finally { finalizing.value = false }
}

// ===== 第9步：创建自动化发布任务（走「发布中心」审核闸门） =====
const publishDialog = ref(false)
const publishSaving = ref(false)
const publishPlatforms = ref([])
const publishForm = reactive({ platform: '', adapter_type: 'playwright', scheduled_at: '' })

function onPublishPlatformChange() {
  const p = publishPlatforms.value.find((x) => x.platform === publishForm.platform)
  if (p && p.adapter_type === 'api') publishForm.adapter_type = 'mock'
}

async function openPublishDialog() {
  if (!currentTask.value?.id) return
  if (!currentTask.value.final_content?.trim()) {
    ElMessage.warning('请先在上方完成 GEO 终稿导入，生成最终正文后再建发布任务')
    return
  }
  try {
    const res = await publishApi.platforms(store.currentIndustryId)
    publishPlatforms.value = res.data || []
  } catch (e) { publishPlatforms.value = [] }
  publishForm.platform = (publishPlatforms.value.find((p) => p.adapter_type !== 'api') || {}).platform || ''
  publishForm.adapter_type = 'playwright'
  publishForm.scheduled_at = ''
  publishDialog.value = true
}

async function createPublishTask() {
  if (!publishForm.platform) { ElMessage.warning('请选择目标平台'); return }
  const title = finalizeResult.value?.final_title || currentTask.value.final_title || currentTask.value.title
  const content = finalizeResult.value?.final_content || currentTask.value.final_content
  if (!content?.trim()) { ElMessage.warning('缺少最终正文，无法建任务'); return }
  publishSaving.value = true
  try {
    await publishApi.createJob({
      industry_id: store.currentIndustryId,
      task_id: currentTask.value.id,
      platform: publishForm.platform,
      adapter_type: publishForm.adapter_type,
      title,
      content,
      scheduled_at: publishForm.scheduled_at || '',
    })
    ElMessage.success('已创建发布任务，请在左侧「发布中心」审核并执行')
    publishDialog.value = false
  } catch (e) { /* 拦截器已提示 */ }
  finally { publishSaving.value = false }
}

// 本地启发式兜底（无 AI 时快速体检）
async function runLocalGeoScore() {
  if (!currentTask.value?.id) return
  geoScoring.value = true
  try {
    const res = await productionApi.geoScore(currentTask.value.id)
    geoResult.value = res.data
    currentTask.value.geo_score = res.data.score
    await saveDraft(true)
    if (res.data.gate_pass) ElMessage.success(`本地体检 ${res.data.score}/100，已通过闸门`)
    else ElMessage.warning(`本地体检 ${res.data.score}/100，未达 ${res.data.gate_threshold} 分闸门，详见待优化项`)
  } catch (e) {
    ElMessage.error('评分失败：' + (e?.response?.data?.detail || ''))
  } finally { geoScoring.value = false }
}

// ===== GEO 优化建议提示词（可复制）=====
// 根据评分结果与薄弱维度，动态生成可粘贴给 AI 改写的优化提示词
const GEO_DIM_META = {
  entity_signals: { label: '品牌实体信号', tip: '在文中自然、可归属地补充品牌实体：品牌名、官网链接、联系方式、核心产品至少各出现 1 次，最好出现在"据 XX 官方案例"这类语境中。' },
  fact_density: { label: '事实密度', tip: '为每个核心论点补充可量化数据（具体数字+单位、百分比、案例数量），替换空泛形容词。' },
  intent_coverage: { label: '意图覆盖', tip: '围绕目标客户的真实意图问题展开，并自然植入"期望 AI 推荐我们的角度"。' },
  qa_form: { label: '问答形态', tip: '采用问答/FAQ 形态或疑问式小标题，便于 AI 直接抽取答案。' },
  structure: { label: '结构可提取', tip: '补充清晰标题层级与小标题/列表，提升可被解析为结构化答案的概率。' },
  attributable: { label: '信号可归属', tip: '增加可溯源证据（据…显示、客户案例、实测数据），让 AI 能引用。' },
}
const MIND_DIM_META = {
  storytelling: { label: '叙事感', tip: '用「背景→问题→方案→结果」讲故事，加入时间/事件标记（如「去年」「有一次」「后来」），让内容有叙事线索而非说明书。' },
  scenario: { label: '场景化', tip: '加入真实场景描述与客户故事（如「某客户在…时」「李总说」），让读者身临其境。' },
  reader_perspective: { label: '读者视角', tip: '多用「你」「你的」「如果你」直接对话读者，直击其顾虑与纠结。' },
  language_warmth: { label: '语言温度', tip: '加入口语化表达（「其实」「说白了」「讲真」），减少公文腔与说明书式冰冷表达。' },
  pain_resonance: { label: '痛点共鸣', tip: '把客户的「怕」「担心」「纠结」具体写出来，引发情感共鸣而非泛泛列举痛点。' },
}
function mindDimLabel(k) {
  return (MIND_DIM_META[k] || {}).label || k
}
const geoSuggestionPrompts = computed(() => {
  const r = geoResult.value
  if (!r) return []
  const score = r.score ?? 0
  const threshold = r.gate_threshold ?? 70
  const dims = r.dimensions || {}
  const weights = r.weights || {}
  const issues = r.issues || []
  const intentQ = r.intent_question || ''
  const rec = r.expected_recommendation || ''
  const signals = (r.signals_present || []).join('、')
  const prompts = []
  // 整体优化提示词
  const lines = []
  lines.push(`你是一位 GEO（生成式引擎优化）改写专家。下面是一篇待优化的软文，GEO 评分 ${score}/100（达标阈值 ${threshold}），${r.gate_pass ? '已达标' : '未达标'}。`)
  if (intentQ) lines.push(`该文应服务的目标客户意图问题：${intentQ}`)
  if (rec) lines.push(`期望 AI 推荐我们的角度：${rec}`)
  lines.push('请在不改变核心信息与推荐角度的前提下，针对以下待优化项改写，使其更易被 AI 检索、提取并作为推荐来源引用：')
  if (issues.length) issues.forEach(it => lines.push('• ' + it))
  else lines.push('• 当前未列明具体待优化项，请按 GEO 六维（品牌实体信号/事实密度/意图覆盖/问答形态/结构可提取/信号可归属）整体加强。')
  lines.push('优化重点：补充品牌实体信号（品牌名/官网/联系方式/核心产品）、增加可量化数据、采用问答/FAQ 或疑问式小标题、补充标题层级与列表、增加可溯源证据。直接输出改写后的全文，不要输出说明。')
  prompts.push({ title: '整体 GEO 优化提示词', prompt: lines.join('\n') })
  // 薄弱维度专项提示词
  for (const key of Object.keys(GEO_DIM_META)) {
    const w = weights[key] || 0
    const d = dims[key] ?? 0
    if (w > 0 && d < w * 0.6) {
      const meta = GEO_DIM_META[key]
      const pl = [
        `你是一位 GEO 优化专家。请聚焦提升文章的「${meta.label}」维度（当前 ${d}/${w}，偏弱）。`,
        intentQ ? `目标客户意图问题：${intentQ}` : '',
        rec ? `期望推荐角度：${rec}` : '',
        `具体做法：${meta.tip}`,
        signals ? `已命中的 GEO 信号：${signals}` : '',
        '请在保持原文核心信息的前提下改写，直接输出优化后的相关段落。',
      ].filter(Boolean)
      prompts.push({ title: `${meta.label} · 专项优化`, prompt: pl.join('\n') })
    }
  }
  // 心智温度薄弱维度专项提示词
  const mind = r.mind_resonance
  if (mind) {
    const mDims = mind.dimensions || {}
    const mWeights = mind.weights || {}
    const mIssues = mind.issues || []
    for (const key of Object.keys(MIND_DIM_META)) {
      const w = mWeights[key] || 0
      const d = mDims[key] ?? 0
      if (w > 0 && d < w * 0.6) {
        const meta = MIND_DIM_META[key]
        const pl = [
          `你是一位内容改写专家。请聚焦提升文章的「${meta.label}」维度（当前 ${d}/${w}，偏弱）。`,
          `这是心智温度诊断（判断内容是否能让真实读者产生情感共鸣与信任感）。`,
          intentQ ? `目标客户意图问题：${intentQ}` : '',
          `具体做法：${meta.tip}`,
          '请在保持原文核心信息与推荐角度的前提下改写，直接输出优化后的相关段落。',
        ].filter(Boolean)
        prompts.push({ title: `心智温度 · ${meta.label} 专项优化`, prompt: pl.join('\n') })
      }
    }
  }
  return prompts
})
async function copySuggestion(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制 GEO 建议提示词，可粘贴给 AI 改写')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

function toggleKeyword(id) {
  const idx = selectedKeywordIds.value.indexOf(id)
  if (idx >= 0) selectedKeywordIds.value.splice(idx, 1)
  else selectedKeywordIds.value.push(id)
}

function toggleKnowledge(id) {
  const idx = selectedKnowledgeIds.value.indexOf(id)
  if (idx >= 0) selectedKnowledgeIds.value.splice(idx, 1)
  else selectedKnowledgeIds.value.push(id)
}

// v5 新增：切换规则选择，并静默持久化，确保渲染时已生效
function toggleRule(id) {
  const idx = selectedRuleIds.value.indexOf(id)
  if (idx >= 0) selectedRuleIds.value.splice(idx, 1)
  else selectedRuleIds.value.push(id)
  saveDraft(true)
}

// 全选/取消全选规则
const allRulesSelected = computed(() => {
  const all = ruleGroupList.value.flatMap(g => g.items.map(r => r.id))
  return all.length > 0 && all.every(id => selectedRuleIds.value.includes(id))
})
function toggleSelectAllRules() {
  if (allRulesSelected.value) {
    selectedRuleIds.value = []
  } else {
    selectedRuleIds.value = ruleGroupList.value.flatMap(g => g.items.map(r => r.id))
  }
  saveDraft(true)
}

function parseVars(v) {
  if (!v) return []
  if (Array.isArray(v)) return v
  try { return JSON.parse(v) } catch { return [] }
}

// 自定义变量弹窗状态
const cvarDialog = ref(false)
const cvarList = ref([])
let cvarPendingCategory = ''
let cvarPendingAction = 'render'  // 'render' | 'generate'

// 写作步骤可用的提示词 = 严格按当前步骤的分类过滤，确保与生产流程强耦合：
// outline→outline、draft→draft、rewrite→rewrite、geo（第9步）→geo，互不串类。
function writingPrompts(cat) {
  return options.prompts?.[cat] || []
}
// 跨分类查找提示词（含 geo），用于变量解析
function findPromptById(id) {
  for (const k of Object.keys(options.prompts || {})) {
    const f = (options.prompts[k] || []).find(p => p.id === id)
    if (f) return f
  }
  return null
}

async function renderPrompt(category) {
  const fieldMap = { outline: 'outline_prompt_id', draft: 'draft_prompt_id', rewrite: 'rewrite_prompt_id', safety: 'safety_prompt_id', geo: 'safety_prompt_id' }
  const promptId = currentTask.value[fieldMap[category]]
  if (!promptId) { ElMessage.warning('请先选择提示词'); return }
  // 若选中提示词含自定义变量，先弹窗填写，再渲染
  const prompt = findPromptById(promptId)
  const custom = parseVars(prompt?.variable_schema).filter(v => v && v.name)
  if (custom.length) {
    cvarList.value = custom.map(v => ({ name: v.name, desc: v.desc || '', value: '' }))
    cvarPendingCategory.value = category
    cvarPendingAction = 'render'
    cvarDialog.value = true
    return
  }
  await doRender(category, {})
}

async function confirmCvar() {
  const cv = {}
  cvarList.value.forEach(v => { if (v.name) cv[v.name] = v.value || '' })
  cvarDialog.value = false
  if (cvarPendingAction === 'generate') {
    await doGenerate(cvarPendingCategory, cv)
  } else {
    await doRender(cvarPendingCategory, cv)
  }
}

async function doRender(category, customVarsMap) {
  const fieldMap = { outline: 'outline_prompt_id', draft: 'draft_prompt_id', rewrite: 'rewrite_prompt_id', safety: 'safety_prompt_id', geo: 'safety_prompt_id' }
  const promptId = currentTask.value[fieldMap[category]]
  const res = await productionApi.render({
    task_id: currentTask.value.id,
    prompt_id: promptId,
    category,
    keyword_ids: selectedKeywordIds.value,
    knowledge_item_ids: selectedKnowledgeIds.value,
    rule_ids: selectedRuleIds.value,
    custom_vars: customVarsMap,
  })
  renderedPrompt.value = res.data.rendered
  // 后端安全网：若有未解析变量，明确提醒，避免静默污染
  if (res.data && res.data.unresolved && res.data.unresolved.length) {
    ElMessage.warning('注意：' + res.data.unresolved.map(k => '{' + k + '}').join(' ') + ' 未解析，已原样保留在提示词中')
  } else {
    ElMessage.success('提示词已生成，可复制到 AI 工具')
  }
}

// 复制已生成的提示词到剪贴板，便于粘贴到外部 AI 工具
async function copyRenderedPrompt() {
  if (!renderedPrompt.value) { ElMessage.warning('请先生成提示词'); return }
  try {
    await navigator.clipboard.writeText(renderedPrompt.value)
    ElMessage.success('提示词已复制，可粘贴到 AI 工具')
  } catch {
    ElMessage.error('复制失败，请手动选择文本复制')
  }
}

// ========== 一键生成（调用已配置 LLM，与手动模式并存） ==========
const genDialogVisible = ref(false)
const genLoading = ref(false)
const genAccepting = ref(false)
const genData = ref(null)
const genStep = ref('')

const STEP_TO_CAT = { 6: 'outline', 7: 'draft', 8: 'rewrite', 9: 'geo' }
const CAT_PROMPT_FIELD = { outline: 'outline_prompt_id', draft: 'draft_prompt_id', rewrite: 'rewrite_prompt_id', geo: 'safety_prompt_id' }
const CAT_CONTENT_FIELD = { outline: 'outline_content', draft: 'draft_content', rewrite: 'rewrite_content', geo: 'final_content' }
const CAT_LABEL = { outline: '大纲', draft: '初稿', rewrite: '精修稿', geo: '最终文章' }

async function generateByAI() {
  const step = STEP_TO_CAT[currentTask.value?.current_step]
  if (!step) return
  const promptId = currentTask.value[CAT_PROMPT_FIELD[step]]
  if (!promptId) { ElMessage.warning('请先选择提示词'); return }
  // 自定义变量：先弹窗填写，再生成
  const prompt = findPromptById(promptId)
  const custom = parseVars(prompt?.variable_schema).filter(v => v && v.name)
  if (custom.length) {
    cvarList.value = custom.map(v => ({ name: v.name, desc: v.desc || '', value: '' }))
    cvarPendingCategory.value = step
    cvarPendingAction = 'generate'
    cvarDialog.value = true
    return
  }
  await doGenerate(step, {})
}

async function doGenerate(category, customVarsMap) {
  genLoading.value = true
  try {
    const res = await productionApi.generate(currentTask.value.id, {
      step: category,
      prompt_id: currentTask.value[CAT_PROMPT_FIELD[category]],
      keyword_ids: selectedKeywordIds.value,
      knowledge_item_ids: selectedKnowledgeIds.value,
      rule_ids: selectedRuleIds.value,
      custom_vars: customVarsMap,
    })
    const d = res.data || {}
    if (d.need_config) {
      // 未配置 LLM：把渲染后的提示词留在输入框，引导手动模式
      renderedPrompt.value = d.rendered || ''
      ElMessage.warning(d.error || '未配置 LLM（如 DeepSeek），已为你生成提示词，可复制给 AI 工具')
      return
    }
    genData.value = d
    genStep.value = category
    genDialogVisible.value = true
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    genLoading.value = false
  }
}

async function acceptGen() {
  const d = genData.value
  if (!d) return
  genAccepting.value = true
  try {
    if (genStep.value === 'geo') {
      // geo 步：把 AI 四段结果喂给 geo-finalize 解析并写回（标题/正文/评分/建议）
      finalizeImportText.value = d.text
      await runGeoFinalize()
    } else {
      currentTask.value[CAT_CONTENT_FIELD[genStep.value]] = d.text
      await saveDraft(true)
      ElMessage.success('已写入' + (CAT_LABEL[genStep.value] || '内容'))
    }
    genDialogVisible.value = false
  } finally {
    genAccepting.value = false
  }
}

async function copyGenText() {
  if (!genData.value?.text) return
  try {
    await navigator.clipboard.writeText(genData.value.text)
    ElMessage.success('已复制生成内容')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function publishTask() {
  if (!currentTask.value.final_content?.trim()) { ElMessage.warning('请先回填最终文章内容'); return }
  const sc = currentTask.value.geo_score
  const geoMsg = sc == null
    ? '尚未运行 GEO 评分——建议在「安全发布 & GEO 筛选」步骤先评分，确认内容可被 AI 抓取引用后再发布。'
    : (sc >= 70
        ? `当前 GEO 评分 ${sc}/100（已达标闸门）。确认发布该文章？`
        : `当前 GEO 评分 ${sc}/100 未达 70 闸门，建议先优化 GEO 信号（品牌实体/事实密度/意图覆盖）。仍要发布？`)
  try {
    await ElMessageBox.confirm(geoMsg, '发布确认（GEO 闸门）', { type: 'warning', confirmButtonText: sc != null && sc < 70 ? '仍要发布' : '确认发布', cancelButtonText: '去优化' })
  } catch {
    if (sc != null && sc < 70) goStep(9)
    return
  }
  await saveDraft(true)
  await productionApi.publish(currentTask.value.id, { publish_url: currentTask.value.publish_url || '' })
  ElMessage.success('文章已发布，任务完成')
  await loadTasks()
  const updated = tasks.value.find(t => t.id === currentTask.value.id)
  if (updated) selectTask(updated)
}



async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制：' + text)
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}





watch(() => store.currentIndustryId, () => loadTasks())
onMounted(async () => {
  await store.loadIndustries()
  await loadTasks()
})
</script>

<style scoped>
.production-view { display: flex; flex-direction: column; height: 100%; }
.prod-layout {
  flex: 1; display: grid;
  grid-template-columns: 320px 1fr;
  gap: 20px; min-height: 0;
}

/* 左侧任务面板 */
.task-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.panel-head {
  padding: 18px 20px; border-bottom: 1px solid var(--border-light);
  display: flex; justify-content: space-between; align-items: center;
}
.panel-title { font-size: 15px; font-weight: 700; color: var(--text-primary); letter-spacing: .3px; }
.task-list { flex: 1; min-height: 0; }
.task-card {
  position: relative;
  height: 100%; box-sizing: border-box; overflow: hidden;
  padding: 14px 16px 14px 18px; border-radius: var(--radius-md);
  cursor: pointer; transition: var(--transition);
  border: 1px solid var(--border-light); border-left: 3px solid transparent;
  background: var(--bg-card);
}
.task-card:hover { border-color: var(--brand-200); box-shadow: var(--shadow-sm); transform: translateY(-1px); }
.task-card.active { background: var(--brand-50); border-color: var(--brand-200); border-left-color: var(--brand-500); }
.task-card--draft { border-left-color: #94a3b8; }
.task-card--processing { border-left-color: #f59e0b; }
.task-card--done { border-left-color: #10b981; }
.task-card--archived { border-left-color: #cbd5e1; }
.task-card__header { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; }
.task-card__title { flex: 1; font-size: 14px; font-weight: 600; color: var(--text-primary); line-height: 1.45; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.task-card__actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
.task-card__del { opacity: 0; transition: opacity 0.15s; margin-right: 2px; }
.geo-score-badge { margin-left: 2px; font-variant-numeric: tabular-nums; }
.task-card:hover .task-card__del { opacity: 1; }
.task-card__meta { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--text-tertiary); margin-bottom: 10px; }
.task-card__meta span { display: flex; align-items: center; gap: 4px; }
.task-card__progress { display: flex; align-items: center; gap: 10px; }
.progress-bar { flex: 1; height: 6px; background: var(--slate-100); border-radius: 999px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--brand-500), var(--accent-cyan)); border-radius: 999px; }
.progress-text { font-size: 11px; color: var(--text-tertiary); white-space: nowrap; font-weight: 500; }

/* 右侧工作区 */
.workspace-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: auto minmax(0, 1fr) auto;
  grid-template-areas: "nav" "content" "actions";
  overflow: hidden;
  min-height: 0;
}
.steps-nav { grid-area: nav; }
.step-content { grid-area: content; min-height: 0; }
.action-bar { grid-area: actions; }
.step-content { flex: 1; overflow-y: auto; padding: 28px 32px; }

.empty-workspace {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 40px; text-align: center;
}
.empty-workspace .empty-icon { font-size: 56px; color: var(--slate-300); margin-bottom: 16px; }
.empty-workspace .empty-title { font-size: 15px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
.empty-workspace .empty-desc { font-size: 13px; color: var(--text-tertiary); max-width: 360px; line-height: 1.6; }

/* 步骤导航 */
.steps-nav {
  display: flex; gap: 2px; padding: 18px 24px;
  border-bottom: 1px solid var(--border-light);
  overflow-x: auto;
  background: linear-gradient(180deg, var(--brand-50), transparent);
}
.step-node {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 14px; border-radius: var(--radius-md);
  cursor: pointer; transition: var(--transition);
  white-space: nowrap; flex-shrink: 0;
}
.step-node:hover { background: var(--bg-card); }
.step-node.active { background: #fff; box-shadow: var(--shadow-sm); }
.step-circle {
  width: 32px; height: 32px; border-radius: 50%;
  background: var(--slate-100); color: var(--text-tertiary);
  font-size: 13px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; border: 2px solid transparent;
  transition: var(--transition);
}
.step-node.active .step-circle {
  background: linear-gradient(135deg, var(--brand-500), var(--brand-700));
  color: #fff; box-shadow: 0 4px 12px rgba(99,102,241,.35);
}
.step-node.done .step-circle { background: var(--accent-emerald); color: #fff; }
.step-name { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.step-node.active .step-name { color: var(--brand-700); }
.step-hint { font-size: 10px; color: var(--text-tertiary); }

/* 底部操作栏 */
.action-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 24px; border-top: 1px solid var(--border-light);
  background: var(--bg-card); flex-shrink: 0;
}
.action-center { flex: 1; text-align: center; }
.step-indicator { font-size: 13px; color: var(--text-tertiary); font-weight: 500; }
.action-right { display: flex; gap: 8px; }

.empty-tip {
  display: flex; flex-direction: column; align-items: center;
  padding: 40px 20px; text-align: center;
  color: var(--text-tertiary); font-size: 13px;
}
.empty-tip .empty-icon { font-size: 40px; margin-bottom: 12px; color: var(--slate-300); }

/* 历史版本弹窗 */
.version-list { display: flex; flex-direction: column; gap: 10px; max-height: 60vh; overflow-y: auto; }
.version-item { border: 1px solid var(--border-light); border-radius: 10px; padding: 10px 12px; }
.version-item__head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.version-no { font-weight: 700; color: var(--brand-600); }
.version-time { font-size: 12px; color: var(--text-tertiary); flex: 1; }
.version-content {
  font-size: 13px; color: var(--text-secondary); white-space: pre-wrap;
  max-height: 160px; overflow-y: auto; line-height: 1.6;
}

/* 一键生成结果弹窗 */
.gen-alert { margin-bottom: 12px; }
.gen-geo-preview { margin: 8px 0 12px; border: 1px solid var(--border-light); border-radius: var(--radius-md); overflow: hidden; }
.gen-geo-row { display: flex; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--border-light); }
.gen-geo-row:last-child { border-bottom: none; }
.gen-geo-k { flex: 0 0 72px; color: var(--text-tertiary); font-size: 13px; }
.gen-geo-v { flex: 1; font-weight: 600; word-break: break-word; }
.gen-hint { margin-top: 10px; font-size: 12px; color: var(--text-tertiary); line-height: 1.6; }
</style>
