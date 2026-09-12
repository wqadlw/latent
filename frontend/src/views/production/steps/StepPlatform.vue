<template>
  <div class="step-pane">
    <StepHeader :no="2" title="选择发布平台" desc="不同平台有不同的内容规范、受众与审核标准，选平台即决定后续账号人设与发布规则" />
    <div class="platform-select-list" v-loading="loading">
      <div
        v-for="p in platforms"
        :key="p.id"
        class="platform-card"
        :class="{ selected: selectedId === p.id }"
        @click="$emit('select', p)"
      >
        <div class="platform-card__head">
          <el-icon :size="22" color="#0ea5e9"><Connection /></el-icon>
          <div class="platform-card__title">
            <div class="platform-name">{{ p.name }}</div>
            <div class="platform-tags">
              <el-tag size="small" effect="plain">{{ p.word_count_min }}-{{ p.word_count_max }} 字</el-tag>
              <el-tag size="small" :type="complianceTagType(p.compliance_level)" effect="light">合规等级{{ ['宽松', '标准', '严格'][p.compliance_level] || '标准' }}</el-tag>
              <el-tag v-if="platformMeta(p).ai_weight" size="small" type="info" effect="plain">AI 收录·{{ platformMeta(p).ai_weight }}</el-tag>
            </div>
          </div>
          <el-icon v-if="selectedId === p.id" class="check-mark"><CircleCheckFilled /></el-icon>
        </div>
        <div class="platform-card__body">
          <div class="platform-field" v-if="p.characteristics">
            <span class="field-label">平台特性</span>
            <span class="field-val">{{ p.characteristics }}</span>
          </div>
          <div class="platform-field" v-if="p.rules">
            <span class="field-label">平台规则</span>
            <span class="field-val">{{ p.rules }}</span>
          </div>
          <div class="platform-field">
            <span class="field-label">账号人设</span>
            <div class="account-chips" v-if="(p.bound_accounts || []).length">
              <span class="account-chip" v-for="(a, i) in p.bound_accounts" :key="i">
                <b>{{ a.account_name }}</b><template v-if="a.persona_name"> · {{ a.persona_name }}</template>
              </span>
            </div>
            <span class="account-empty" v-else>该平台下暂无账号（去「平台管理」配置账号与人设）</span>
          </div>
        </div>
      </div>
      <EmptyState v-if="!loading && platforms.length === 0" title="暂无平台" description="请先到「平台管理」一键灌入 7 大平台或新建平台" size="small" icon="Connection" />
    </div>
  </div>
</template>

<script setup>
import StepHeader from '../../../components/production/StepHeader.vue'
import EmptyState from '../../../components/EmptyState.vue'

defineProps({
  platforms: { type: Array, default: () => [] },
  selectedId: { type: [Number, String], default: null },
  loading: { type: Boolean, default: false },
  // 纯函数：合规等级 → Tag 类型
  complianceTagType: { type: Function, required: true },
  // 纯函数：解析平台 config（features / ai_weight / marketing）
  platformMeta: { type: Function, required: true },
})
defineEmits(['select'])
</script>
