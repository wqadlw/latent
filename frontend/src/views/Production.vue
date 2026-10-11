<template>
  <div class="production-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button type="primary" :icon="Plus" @click="createTask">新建生产任务</el-button>
      <el-button :icon="Refresh" @click="loadTasks">刷新</el-button>
    </Teleport>

    <WorkbenchLayout class="prod-layout" aside-width="320px" fill>
      <template #aside>
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
                    <el-tag :type="taskStatusType(item.status)" size="small" effect="light">{{ taskStatusLabel(item.status) }}</el-tag>
                    <el-tag v-if="item.geo_score != null" size="small" effect="plain" type="success" class="geo-score-badge">GEO {{ item.geo_score }}</el-tag>
                  </div>
              </div>
              <div class="task-card__meta">
                <span><el-icon><OfficeBuilding /></el-icon> {{ item.industry_snapshot || '未选行业' }}</span>
                <span v-if="item.platform_snapshot"><el-icon><Connection /></el-icon> {{ item.platform_snapshot }}</span>
              </div>
                <div class="task-card__progress">
                <div class="progress-bar"><div class="progress-fill" :style="{ width: (item.current_step / PRODUCTION_TOTAL_STEPS * 100) + '%' }"></div></div>
                <span class="progress-text">{{ item.current_step }}/{{ PRODUCTION_TOTAL_STEPS }}</span>
              </div>
            </div>
          </VirtualList>
          <div v-if="!loadingTasks && tasks.length === 0" class="empty-tip">
            <el-icon class="empty-icon"><DocumentAdd /></el-icon>
            <div>暂无生产任务<br/>点击右上角「新建生产任务」开始</div>
          </div>
        </div>
      </template>

      <template #main>
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
                <span class="step-indicator">第 {{ currentTask.current_step }} 步 / 共 {{ PRODUCTION_TOTAL_STEPS }} 步</span>
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
      </template>
    </WorkbenchLayout>
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
import WorkbenchLayout from '../components/layout/WorkbenchLayout.vue'
import { ref, reactive, computed, onMounted, watch, inject } from 'vue'

const pageActionsTarget = inject('pageActionsTarget', null)

import { ElMessage } from 'element-plus'
import {
  Plus, Refresh, Check, ArrowLeft, ArrowRight, Document, Promotion,
  OfficeBuilding, Connection, DocumentAdd, Delete,
} from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { productionApi } from '../api'
import { copyText } from '../utils/clipboard'
import { nameById } from '../utils/lookup'
import { safeJsonParse } from '../utils/json'
import { PRODUCTION_STEPS, PRODUCTION_TOTAL_STEPS, CAT_LABEL, geoDimLabel, mindDimLabel } from '../constants/production'
import { taskStatusLabel, taskStatusType } from '../constants/status'

// 逻辑按职责拆到 7 个 composable（每个文件头部注释写了「为什么这么切」）：
//   useProductionTasks      任务生命周期：列表 / 选中 / 分步保存 / 版本回滚 / 删除
//   useProductionSelections 勾选态：已选关键词 / 知识点 / 规则 + 派生视图 + 知识点预览
//   useCustomVarDialog      自定义变量填写弹窗（渲染与一键生成共用）
//   usePromptRender         提示词渲染（只拼提示词，不调 LLM）
//   useOneClickGenerate     一键生成（调后端已配置的 LLM）
//   useGeoGate              第 9 步 GEO 体检 / 终检导入 / 优化建议提示词
//   usePublishTask          第 9 步发布（建发布任务 / 直接发布）
import { useProductionTasks } from '../composables/production/useProductionTasks'
import { useProductionSelections } from '../composables/production/useProductionSelections'
import { useCustomVarDialog } from '../composables/production/useCustomVarDialog'
import { usePromptRender } from '../composables/production/usePromptRender'
import { useOneClickGenerate } from '../composables/production/useOneClickGenerate'
import { useGeoGate } from '../composables/production/useGeoGate'
import { usePublishTask } from '../composables/production/usePublishTask'

import VirtualList from '../components/VirtualList.vue'
import VersionHistoryDialog from '../components/production/VersionHistoryDialog.vue'
import KnowledgePreviewDrawer from '../components/production/KnowledgePreviewDrawer.vue'
import CustomVarDialog from '../components/production/CustomVarDialog.vue'
import OneClickGenerateResult from '../components/production/OneClickGenerateResult.vue'
import CreatePublishTaskDialog from '../components/production/CreatePublishTaskDialog.vue'
import StepIndustry from './production/steps/StepIndustry.vue'
import StepPlatform from './production/steps/StepPlatform.vue'
import StepSingleFlow from '../components/production/StepSingleFlow.vue'
import StepOutline from './production/steps/StepOutline.vue'
import StepFinal from './production/steps/StepFinal.vue'
import Step5 from './production/steps/Step5.vue'
import StepIllustration from './production/steps/StepIllustration.vue'
import StepPersona from './production/steps/StepPersona.vue'
import StepDemand from './production/steps/StepDemand.vue'

/* ==================== 本视图自己持有的状态 ====================
 * 只放「多个 composable 都要读写、或模板直接绑」的东西。判断标准很具体：
 * 搬进某个 composable 会不会造成两个 composable 之间的循环依赖。
 */

const store = useAppStore()

// 生产选项（平台/账号/人设/关键词/提示词/知识点/规则），由 loadOptions() 整体替换
const options = reactive({
  platforms: [], accounts: [], personas: [], keywords: [], prompts: {}, knowledge_grouped: [], rules: {},
})

// 已渲染的提示词。
// ⚠️ 刻意放在视图而不是 usePromptRender 里：useProductionTasks 要在「换任务 / 换步骤」时
// 清空它（否则用户会拿着上一步的提示词去问 AI），而 usePromptRender 要写它 ——
// 建在任何一侧都会让这两个 composable 互相依赖。
const renderedPrompt = ref('')

// 第 10 步配图状态：属于任务持久化数据，由视图持有，StepIllustration 就地修改
const illuState = reactive({ plan: null, promptId: 0, style: '', method: 'ai' })

// 当前配图建议（已生成的优先，否则用 options 里的预计算建议）
const currentRecommendation = computed(
  () =>
    illuState.plan?.recommendation ||
    options.recommendation || { method: 'ai', reason: '根据平台与文章内容，建议优先 AI 生图以统一风格、规避版权风险。' },
)
const recommendationMethod = computed(() => currentRecommendation.value?.method || 'ai')

const steps = PRODUCTION_STEPS

/* ==================== 模板用的小工具 ==================== */

// 平台 id → 名称：账号接口只返回 platform_id，需结合 options.platforms 本地映射。
// 回退用空串而不是「—」：这两处在子组件里是内联小字，空串更自然。
const getPlatformName = (id) => nameById(options.platforms, id, 'name', '')
// 人设 id → 名称（账号绑定人设展示用）
const getPersonaName = (id) => nameById(options.personas, id, 'name', '')

/** 合规等级 → Tag 类型 */
function complianceTagType(level) {
  return level >= 3 ? 'danger' : level >= 2 ? 'warning' : 'success'
}

/** 解析平台 config（features / ai_weight / marketing）。坏数据回退成空对象而不是抛异常。 */
function platformMeta(p) {
  return safeJsonParse(p && p.config, {})
}

/* ==================== 草稿保存 ==================== */

/**
 * 保存草稿。
 *
 * ⚠️ 这里用 `function` 声明是**刻意的**：函数声明会被提升，下面的 composable
 * 在 setup 期间就能拿到它的引用；真正的调用发生在用户交互时，
 * 那时 `currentTask` / `selections` 都已经初始化完毕。
 */
async function saveDraft(silent = false) {
  if (!currentTask.value?.id) return
  // 只发送业务字段，避免把 create_time/update_time 等字符串时间写回后端 DateTime 列
  const { id, create_time, update_time, is_deleted, ...rest } = currentTask.value
  const data = { ...rest, ...selections.toTaskFields() }
  await productionApi.update(currentTask.value.id, data)
  if (!silent) ElMessage.success('草稿已保存')
}

/* ==================== 分区逻辑 ====================
 * 下面统一「调用 composable → 解构出裸名字」，好处是**模板一个字都不用改**，
 * 拆分风险被限制在这段 setup 代码里。
 */

const selections = useProductionSelections({ options, saveDraft })
const {
  selectedKeywordIds, selectedKnowledgeIds, selectedRuleIds,
  ruleGroupList, hasAnyRules, selectedRuleBreakdown, selectedRuleTotal, allRulesSelected,
  toggleRule, toggleSelectAllRules, toggleKeyword, toggleKnowledge, clearKnowledge,
  toggleCategoryAll, selectedKnowledgeItems, selectedKnowledgeSummary,
  previewKnowledgeItem, previewDrawer, previewKnowledge, onPreviewToggle, exportKnowledgeMaterial,
} = selections

const taskState = useProductionTasks({
  store, options, selections, saveDraft, illuState, recommendationMethod,
  clearRenderedPrompt: () => { renderedPrompt.value = '' },
})
const {
  loadingTasks, loadingOptions, tasks, currentTask, step4Needs,
  loadTasks, createTask, handleDelete, selectTask, goStep, prevStep, nextStep,
  saveStep1, saveStep2, saveStep3Account, saveStep3Persona,
  versionDialog, versionList, versionStep, openVersions, restoreVersion,
} = taskState

const cvar = useCustomVarDialog({ options })
const { cvarDialog, cvarList, confirmCvar } = cvar

const render = usePromptRender({ currentTask, options, selections, cvar, renderedPrompt })
const { writingPrompts, renderPrompt, copyRenderedPrompt } = render

const geo = useGeoGate({ currentTask, saveDraft })
const {
  geoScoring, geoResult, finalizing, finalizeResult, finalizeImportText, setFinalizeImportText,
  hasFinalContent, runLocalGeoScore, runGeoFinalize, geoSuggestionPrompts, copySuggestion,
} = geo

const gen = useOneClickGenerate({ currentTask, selections, renderedPrompt, cvar, geo, saveDraft })
const {
  genDialogVisible, genLoading, genAccepting, genData, genStep, generateByAI, acceptGen, copyGenText,
} = gen

const pub = usePublishTask({
  currentTask, store, finalizeResult, saveDraft, goStep, loadTasks, selectTask, tasks,
})
const {
  publishDialog, publishSaving, publishPlatforms, publishForm,
  onPublishPlatformChange, openPublishDialog, createPublishTask, publishTask,
} = pub

/* ==================== 生命周期 ==================== */

watch(() => store.currentIndustryId, () => loadTasks())
onMounted(async () => {
  await store.loadIndustries()
  await loadTasks()
})
</script>

<style scoped>
.production-view { display: flex; flex-direction: column; height: 100%; }
/* .prod-layout 的网格定义已收进 WorkbenchLayout（D7-2）：左栏 320px + 撑满剩余高度。
   类名保留 —— shot-production.mjs 依赖它作为验收钩子。
   ⚠️ 栏间距由 20px 归一为容器的默认 16px，这是 D7「各页视觉一致」的验收点之一。 */

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

/* 历史版本弹窗 / 一键生成结果弹窗的样式已归还给各自组件
   （components/production/VersionHistoryDialog.vue、OneClickGenerateResult.vue）。
   原因：这两个组件被拆出去之后，写在父组件 scoped style 里的规则就够不到它们内部了——
   scoped 只能作用到子组件的根元素，而两者的根元素都是 el-dialog。
   留在这里的规则此前是死的，且导致这两个弹窗长期裸样式。 */
</style>
