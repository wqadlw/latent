<template>
  <StepSingleFlow
    :no="9" title="安全发布 & GEO 筛选" desc="用「安全 · GEO 筛选」提示词做合规过滤与品牌信号补全，生成最终文章；再跑 GEO 闸门体检可抓取/可引用度"
    category="geo" prompt-field="safety_prompt_id" content-field="final_content"
    prompt-label="安全 · GEO 筛选提示词" content-label="AI 生成的最终文章（粘贴回填）"
    version-key="final" content-placeholder="将 AI 工具生成的最终文章粘贴到这里"
    :current-task="currentTask" :loading-options="loadingOptions" :rendered-prompt="renderedPrompt"
    :gen-loading="genLoading" :selected-rule-total="selectedRuleTotal" :selected-rule-breakdown="selectedRuleBreakdown"
    :writing-prompts="writingPrompts" :render-prompt="renderPrompt" :generate-by-a-i="generateByAI"
    :copy-rendered-prompt="copyRenderedPrompt" :open-versions="openVersions"
  >
    <!-- 步骤 9 专属：GEO 评分闸门 + AI 终稿导入（合并于本步） -->
    <template #after-content>
      <StepGeoGate
        :current-task="currentTask"
        :geo-scoring="geoScoring" :finalizing="finalizing" :geo-result="geoResult"
        :has-final-content="hasFinalContent" :finalize-import-text="finalizeImportText"
        :set-finalize-import-text="setFinalizeImportText" :finalize-result="finalizeResult"
        :geo-suggestion-prompts="geoSuggestionPrompts" :geo-dim-label="geoDimLabel"
        :mind-dim-label="mindDimLabel" :copy-suggestion="copySuggestion"
        :run-local-geo-score="runLocalGeoScore" :run-geo-finalize="runGeoFinalize"
        :copy-text="copyText" :open-publish-dialog="openPublishDialog"
      />
    </template>
  </StepSingleFlow>
</template>

<script setup>
import StepSingleFlow from '../../../components/production/StepSingleFlow.vue'
import StepGeoGate from '../../../components/production/StepGeoGate.vue'

defineProps({
  currentTask: { type: Object, required: true },
  loadingOptions: { type: Boolean, default: false },
  renderedPrompt: { type: String, default: '' },
  genLoading: { type: Boolean, default: false },
  selectedRuleTotal: { type: Number, default: 0 },
  selectedRuleBreakdown: { type: Object, default: () => ({ anti_ai: 0, compliance: 0, ai_seo: 0 }) },
  writingPrompts: { type: Function, required: true },
  renderPrompt: { type: Function, required: true },
  generateByAI: { type: Function, required: true },
  copyRenderedPrompt: { type: Function, required: true },
  openVersions: { type: Function, required: true },
  geoScoring: { type: Boolean, default: false },
  finalizing: { type: Boolean, default: false },
  geoResult: { type: Object, default: null },
  hasFinalContent: { type: Boolean, default: false },
  finalizeImportText: { type: String, default: '' },
  setFinalizeImportText: { type: Function, required: true },
  finalizeResult: { type: Object, default: null },
  geoSuggestionPrompts: { type: Array, default: () => [] },
  geoDimLabel: { type: Function, required: true },
  mindDimLabel: { type: Function, required: true },
  copySuggestion: { type: Function, required: true },
  runLocalGeoScore: { type: Function, required: true },
  runGeoFinalize: { type: Function, required: true },
  copyText: { type: Function, required: true },
  openPublishDialog: { type: Function, required: true },
})
</script>
