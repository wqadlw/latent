<template>
  <div class="step-pane">
    <StepHeader :no="no" :title="title" :desc="desc" />
    <div class="single-flow" v-loading="loadingOptions">
      <div class="flow-row">
        <div class="flow-label">{{ promptLabel }}</div>
        <el-select v-model="currentTask[promptField]" :placeholder="'选择' + promptLabel" style="flex: 1">
          <el-option
            v-for="p in writingPrompts(category)"
            :key="p.id"
            :label="p.name + (showGeoTag && p.category === 'geo' ? ' 〔GEO〕' : '')"
            :value="p.id"
          />
        </el-select>
        <el-button type="primary" :icon="MagicStick" @click="renderPrompt(category)" :disabled="!currentTask[promptField]">生成提示词</el-button>
        <el-button type="success" :icon="Promotion" @click="generateByAI" :loading="genLoading" :disabled="!currentTask[promptField]">一键生成</el-button>
      </div>
      <el-input :model-value="renderedPrompt" type="textarea" :rows="8" placeholder="点击上方按钮生成提示词，复制到外部 AI 工具" readonly />
      <div class="prompt-actions">
        <el-button :icon="CopyDocument" :disabled="!renderedPrompt" @click="copyRenderedPrompt">复制提示词</el-button>
        <span class="prompt-actions-hint" v-if="renderedPrompt">已生成，复制后粘贴到 AI 工具即可使用</span>
      </div>
      <div v-if="renderedPrompt && selectedRuleTotal > 0" class="rule-applied-tip">
        <el-icon><CircleCheck /></el-icon>
        已注入规则引导 AI 写作：去AI味 {{ selectedRuleBreakdown.anti_ai }} 条 · 平台合规 {{ selectedRuleBreakdown.compliance }} 条 · AI SEO {{ selectedRuleBreakdown.ai_seo }} 条
      </div>
      <slot name="before-content" />
      <div class="flow-label flow-label--row" style="margin-top: 16px">
        <span>{{ contentLabel }}</span>
        <el-button size="small" :icon="Clock" @click="openVersions(versionKey)">历史版本</el-button>
      </div>
      <el-input v-model="currentTask[contentField]" type="textarea" :rows="14" :placeholder="contentPlaceholder" />
      <slot name="after-content" />
    </div>
  </div>
</template>

<script setup>
import StepHeader from './StepHeader.vue'
import { MagicStick, Promotion, CopyDocument, CircleCheck, Clock } from '@element-plus/icons-vue'

// 单流步骤通用面板（步骤 6/7/8/9 共用）：提示词选择 → 生成提示词/一键生成 → 回填内容。
// 父组件保留全部状态与逻辑，本组件纯展示 + 函数 prop 下传；before-content / after-content 插槽供各步骤注入专属块。
defineProps({
  no: { type: Number, required: true },
  title: { type: String, default: '' },
  desc: { type: String, default: '' },
  category: { type: String, default: '' },
  promptField: { type: String, required: true },
  contentField: { type: String, required: true },
  promptLabel: { type: String, default: '提示词' },
  contentLabel: { type: String, default: '内容（粘贴回填）' },
  versionKey: { type: String, default: '' },
  contentPlaceholder: { type: String, default: '' },
  showGeoTag: { type: Boolean, default: false },
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
})
</script>
