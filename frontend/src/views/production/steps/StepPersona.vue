<script setup>
import { CircleCheckFilled } from '@element-plus/icons-vue'
import StepHeader from '../../../components/production/StepHeader.vue'

const props = defineProps({
  options: { type: Object, required: true },
  currentTask: { type: Object, required: true },
  loadingOptions: { type: Boolean, default: false },
  saveStep3Account: { type: Function, required: true },
  saveStep3Persona: { type: Function, required: true },
  getPersonaName: { type: Function, required: true },
  getPlatformName: { type: Function, required: true },
  hasAnyRules: { type: Boolean, default: false },
  allRulesSelected: { type: Boolean, default: false },
  toggleSelectAllRules: { type: Function, required: true },
  selectedRuleTotal: { type: Number, default: 0 },
  ruleGroupList: { type: Array, default: () => [] },
  selectedRuleBreakdown: { type: Object, default: () => ({}) },
  selectedRuleIds: { type: Array, default: () => [] },
  toggleRule: { type: Function, required: true },
})
</script>

<template>
  <div class="step-pane">
    <StepHeader :no="3" title="确定人设账号" desc="选择该平台下的人设账号" />
    <div class="persona-layout" v-loading="loadingOptions">
      <div class="persona-section">
        <div class="section-label">选择账号</div>
        <div class="persona-list">
          <div
            v-for="a in options.accounts"
            :key="a.id"
            class="persona-card"
            :class="{ selected: currentTask.account_id === a.id }"
            @click="saveStep3Account(a)"
          >
            <div class="persona-avatar">{{ (a.account_name || 'A').charAt(0) }}</div>
            <div class="persona-info">
              <div class="persona-name">{{ a.account_name }}</div>
              <div class="persona-sub">{{ getPersonaName(a.persona_id) || getPlatformName(a.platform_id) || '未绑定平台' }}</div>
            </div>
          </div>
        </div>
      </div>
      <div class="persona-section">
        <div class="section-label">选择人设</div>
        <div class="persona-list">
          <div
            v-for="p in options.personas"
            :key="p.id"
            class="persona-card"
            :class="{ selected: currentTask.persona_id === p.id }"
            @click="saveStep3Persona(p)"
          >
            <div class="persona-avatar">{{ (p.name || 'P').charAt(0) }}</div>
            <div class="persona-info">
              <div class="persona-name">{{ p.name }}</div>
              <div class="persona-sub">{{ p.identity || '未设置身份' }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 规则约束：选定规则将注入提示词，引导 AI 写作 -->
    <div class="rules-panel" v-loading="loadingOptions">
      <div class="rules-panel__head">
        <span class="col-title">规则约束</span>
        <span class="rules-panel__hint">选定的规则会注入到写作提示词中，引导 AI 遵守</span>
        <el-button
          v-if="hasAnyRules"
          size="small"
          :type="allRulesSelected ? 'info' : 'primary'"
          :plain="allRulesSelected"
          @click="toggleSelectAllRules"
          style="margin-left: auto; margin-right: 8px;"
        >
          {{ allRulesSelected ? '取消全选' : '全选' }}
        </el-button>
        <el-tag size="small" type="success">{{ selectedRuleTotal }} 条已选</el-tag>
      </div>
      <div v-if="hasAnyRules" class="rule-groups">
        <div v-for="g in ruleGroupList" :key="g.type" class="rule-group">
          <div class="rule-group__head">
            <span class="rule-group__dot" :style="{ background: g.meta.color }"></span>
            <span class="rule-group__name">{{ g.meta.label }}</span>
            <span class="rule-group__desc">{{ g.meta.desc }}</span>
            <span class="rule-group__count">{{ selectedRuleBreakdown[g.type] }}/{{ g.items.length }}</span>
          </div>
          <div class="rule-chips">
            <el-tooltip
              v-for="r in g.items"
              :key="r.id"
              :content="r.content"
              placement="top"
              :show-after="250"
              :disabled="r.content.length <= 60"
            >
              <div class="rule-chip" :class="{ selected: selectedRuleIds.includes(r.id) }" @click="toggleRule(r.id)">
                <el-icon v-if="selectedRuleIds.includes(r.id)" class="rule-chip__check"><CircleCheckFilled /></el-icon>
                <span class="rule-chip__text">{{ r.content.length > 46 ? r.content.slice(0, 46) + '…' : r.content }}</span>
              </div>
            </el-tooltip>
          </div>
        </div>
      </div>
      <div v-else class="empty-tip" style="padding: 16px 0">该行业暂无规则，请先在「规则库」中添加</div>
    </div>
  </div>
</template>
