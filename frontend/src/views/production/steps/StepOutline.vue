<template>
  <StepSingleFlow
    :no="6" title="生成大纲" desc="选择大纲提示词，注入已选关键词、知识点与规则，生成可复制到 AI 工具的大纲提示词"
    category="outline" prompt-field="outline_prompt_id" content-field="outline_content"
    prompt-label="大纲提示词" content-label="AI 生成的大纲（粘贴回填）"
    version-key="outline" content-placeholder="将 AI 工具生成的大纲粘贴到这里"
    :show-geo-tag="true"
    :current-task="currentTask" :loading-options="loadingOptions" :rendered-prompt="renderedPrompt"
    :gen-loading="genLoading" :selected-rule-total="selectedRuleTotal" :selected-rule-breakdown="selectedRuleBreakdown"
    :writing-prompts="writingPrompts" :render-prompt="renderPrompt" :generate-by-a-i="generateByAI"
    :copy-rendered-prompt="copyRenderedPrompt" :open-versions="openVersions"
  >
    <!-- 大纲步骤专属：已选知识点摘要（生成大纲时注入提示词） -->
    <template #before-content>
      <div v-if="selectedKnowledgeItems.length > 0" class="selected-summary">
        <div class="summary-head">
          <span>已选 <b>{{ selectedKnowledgeSummary.count }}</b> 个知识点</span>
          <span class="summary-cats">覆盖 {{ selectedKnowledgeSummary.categoryCount }} 个分类</span>
        </div>
        <div class="summary-tip">
          <el-icon><CircleCheck /></el-icon>
          生成大纲时这些知识点会被注入提示词
        </div>
        <div class="summary-list">
          <div v-for="ki in selectedKnowledgeItems" :key="ki.id" class="summary-item">
            <el-icon class="si-icon"><Document /></el-icon>
            <span class="si-title">{{ ki.title }}</span>
            <el-button text size="small" :icon="Close" @click="toggleKnowledge(ki.id)" class="si-remove" />
          </div>
        </div>
        <el-button size="small" :icon="DocumentAdd" plain class="summary-export" @click="exportKnowledgeMaterial">
          导出大纲素材
        </el-button>
      </div>
    </template>
  </StepSingleFlow>
</template>

<script setup>
import StepSingleFlow from '../../../components/production/StepSingleFlow.vue'
import { CircleCheck, Document, Close, DocumentAdd } from '@element-plus/icons-vue'

defineProps({
  currentTask: { type: Object, required: true },
  loadingOptions: { type: Boolean, default: false },
  renderedPrompt: { type: String, default: '' },
  genLoading: { type: Boolean, default: false },
  selectedRuleTotal: { type: Number, default: 0 },
  selectedRuleBreakdown: { type: Object, default: () => ({ anti_ai: 0, compliance: 0, ai_seo: 0 }) },
  selectedKnowledgeItems: { type: Array, default: () => [] },
  selectedKnowledgeSummary: { type: Object, default: () => ({ count: 0, categoryCount: 0 }) },
  writingPrompts: { type: Function, required: true },
  renderPrompt: { type: Function, required: true },
  generateByAI: { type: Function, required: true },
  copyRenderedPrompt: { type: Function, required: true },
  openVersions: { type: Function, required: true },
  toggleKnowledge: { type: Function, required: true },
  exportKnowledgeMaterial: { type: Function, required: true },
})
</script>
