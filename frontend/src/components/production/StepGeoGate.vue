<template>
  <div v-if="currentTask && currentTask.current_step === 9" class="geo-gate-block">
    <el-divider content-position="left">
      <span class="geo-gate-divider"><el-icon><Aim /></el-icon> GEO 筛选闸门</span>
    </el-divider>
    <div class="geo-gate" v-loading="geoScoring || finalizing">
      <div class="geo-gate__actions">
        <el-button :icon="MagicStick" @click="runLocalGeoScore" :disabled="!hasFinalContent">
          本地快速体检
        </el-button>
        <el-tag v-if="geoResult" size="large" :type="geoResult.gate_pass ? 'success' : 'warning'" effect="dark">
          综合分 {{ geoResult.score }} / 100 · {{ geoResult.verdict }}
        </el-tag>
        <span class="geo-gate__hint" v-if="!currentTask.intent_question_id">未绑定意图问题，GEO 评分将缺意图覆盖维度</span>
      </div>

      <div v-if="geoResult" class="geo-gate__body">
        <!-- 双信任诊断横幅 -->
        <div v-if="geoResult.diagnosis" class="geo-diagnosis" :style="{ '--dc': geoResult.diagnosis.color }">
          <div class="geo-diagnosis__label">{{ geoResult.diagnosis.label }}</div>
          <div class="geo-diagnosis__desc">{{ geoResult.diagnosis.desc }}</div>
          <div class="geo-diagnosis__scores">
            <span>算法信任 {{ geoResult.score }}/100</span>
            <span v-if="geoResult.mind_resonance">心智温度 {{ geoResult.mind_resonance.score }}/100</span>
          </div>
        </div>

        <div class="geo-section-label">🔧 算法信任维度（AI 可提取性）</div>
        <div class="geo-dims">
          <div class="geo-dim" v-for="(d, key) in geoResult.dimensions" :key="key">
            <div class="geo-dim__head">
              <span class="geo-dim__name">{{ geoDimLabel(key) }}</span>
              <span class="geo-dim__val">{{ d }} / {{ geoResult.weights[key] }}</span>
            </div>
            <div class="geo-dim__bar"><div class="geo-dim__fill" :style="{ width: Math.min(100, d / geoResult.weights[key] * 100) + '%' }"></div></div>
          </div>
        </div>

        <!-- 心智温度维度 -->
        <template v-if="geoResult.mind_resonance">
          <div class="geo-section-label" style="margin-top: 16px;">🧡 心智温度维度（人感与共鸣）</div>
          <div class="geo-dims geo-dims--mind">
            <div class="geo-dim" v-for="(d, key) in geoResult.mind_resonance.dimensions" :key="'mind-'+key">
              <div class="geo-dim__head">
                <span class="geo-dim__name">{{ mindDimLabel(key) }}</span>
                <span class="geo-dim__val">{{ d }} / {{ geoResult.mind_resonance.weights[key] }}</span>
              </div>
              <div class="geo-dim__bar"><div class="geo-dim__fill geo-dim__fill--mind" :style="{ width: Math.min(100, d / geoResult.mind_resonance.weights[key] * 100) + '%' }"></div></div>
            </div>
          </div>
          <div class="geo-section" v-if="geoResult.mind_resonance.signals_present && geoResult.mind_resonance.signals_present.length">
            <div class="section-label">✅ 心智温度信号</div>
            <div class="geo-signal-tags">
              <el-tag v-for="(s, i) in geoResult.mind_resonance.signals_present" :key="'ms'+i" type="warning" effect="plain" class="geo-signal-tag">{{ s }}</el-tag>
            </div>
          </div>
          <div class="geo-section" v-if="geoResult.mind_resonance.issues && geoResult.mind_resonance.issues.length">
            <div class="section-label">⚠️ 心智温度待优化</div>
            <ul class="geo-issues">
              <li v-for="(it, i) in geoResult.mind_resonance.issues" :key="'mi'+i">{{ it }}</li>
            </ul>
          </div>
        </template>
        <div class="geo-section" v-if="geoResult.signals_present && geoResult.signals_present.length">
          <div class="section-label">✅ 已命中的 GEO 信号</div>
          <div class="geo-signal-tags">
            <el-tag v-for="(s, i) in geoResult.signals_present" :key="i" type="success" effect="plain" class="geo-signal-tag">{{ s }}</el-tag>
          </div>
        </div>
        <div class="geo-section" v-if="geoResult.issues && geoResult.issues.length">
          <div class="section-label">⚠️ 待优化项</div>
          <ul class="geo-issues">
            <li v-for="(it, i) in geoResult.issues" :key="i">{{ it }}</li>
          </ul>
        </div>
        <div class="geo-section" v-if="geoResult.rationale">
          <div class="section-label">🧭 AI 总体评价</div>
          <div class="geo-rationale">{{ geoResult.rationale }}</div>
        </div>
        <div class="geo-section" v-if="geoResult.intent_question">
          <div class="section-label">🎯 评分所基于的意图问题</div>
          <div class="geo-bound-q">{{ geoResult.intent_question }}</div>
          <div class="geo-bound-rec" v-if="geoResult.expected_recommendation">期望推荐角度：{{ geoResult.expected_recommendation }}</div>
        </div>

        <div class="geo-section geo-suggest" v-if="geoSuggestionPrompts.length">
          <div class="section-label">💡 GEO 优化建议提示词（复制后粘贴给 AI 改写）</div>
          <div class="geo-suggest__list">
            <div class="geo-suggest__item" v-for="(sp, i) in geoSuggestionPrompts" :key="i">
              <div class="geo-suggest__head">
                <span class="geo-suggest__title">{{ sp.title }}</span>
                <el-button size="small" :icon="CopyDocument" @click="copySuggestion(sp.prompt)">复制</el-button>
              </div>
              <pre class="geo-suggest__text">{{ sp.prompt }}</pre>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="empty-tip" style="padding: 16px 0">
        尚未体检。点「本地快速体检」做离线双信任评分；或按上方提示词生成终稿后，把 AI 返回的结果粘贴到下方「AI 终稿导入」一键出稿并评分。
      </div>

      <!-- AI 终稿导入：合并 GEO 闸门 + 安全·GEO 筛选，评分与出稿一步到位 -->
      <el-divider content-position="left">
        <span class="geo-gate-divider"><el-icon><Upload /></el-icon> AI 终稿导入（评分 + 出稿一步到位）</span>
      </el-divider>
      <div class="geo-finalize">
        <div class="section-label">🤖 把 AI 按上方「安全·GEO 终稿」提示词返回的完整结果粘贴到此处（须含 ## 优化后标题 / ## 优化后正文 / ## GEO 评分 / ## 优化建议 四段）</div>
        <el-input
          :model-value="finalizeImportText"
          @update:model-value="setFinalizeImportText"
          type="textarea"
          :rows="10"
          placeholder="粘贴 AI 返回的结构化结果，例如：&#10;## 优化后标题&#10;敏感肌修护三大误区…&#10;## 优化后正文&#10;（完整最终正文）&#10;## GEO 评分（0-100）&#10;86&#10;## 优化建议&#10;可补充的案例…"
        />
        <div class="geo-import__actions">
          <el-button type="success" :icon="Upload" @click="runGeoFinalize" :loading="finalizing" :disabled="!finalizeImportText.trim()">导入并生成最终发布稿</el-button>
          <el-button text @click="setFinalizeImportText('')">清空</el-button>
        </div>

        <div v-if="finalizeResult" class="geo-finalize__result">
          <div class="geo-finalize__score">
            最终 GEO 评分 <b>{{ finalizeResult.geo_score }}</b> / 100
            <span class="geo-finalize__score-sub">（AI 给分 {{ finalizeResult.ai_score ?? '—' }} · 本地兜底 {{ finalizeResult.local_score }}）</span>
            <el-tag size="small" :type="finalizeResult.geo_score >= 70 ? 'success' : 'warning'" effect="plain" style="margin-left: 8px">{{ finalizeResult.geo_score >= 70 ? '达闸门' : '未达闸门' }}</el-tag>
          </div>

          <!-- 平台合规闸门横幅：手动流与自动流共用同一套闸门（orchestrator.run_quality_gate） -->
          <div v-if="finalizeResult.quality_gate" class="gate-banner" :class="finalizeResult.quality_gate.gate_pass ? 'gate-banner--pass' : 'gate-banner--fail'">
            <div class="gate-banner__head">
              <el-icon><component :is="finalizeResult.quality_gate.gate_pass ? CircleCheckFilled : WarningFilled" /></el-icon>
              <span class="gate-banner__title">
                平台合规闸门 {{ finalizeResult.quality_gate.gate_pass ? '✅ 通过' : '⚠️ 未通过' }}
              </span>
              <el-tag size="small" effect="dark" :type="finalizeResult.quality_gate.gate_pass ? 'success' : 'danger'">
                {{ { geo: '强品牌/GEO', platform: '平台合规', green: '绿色吸粉', official: '官网MDX' }[finalizeResult.quality_gate.mode] || finalizeResult.quality_gate.mode }} 模式
              </el-tag>
              <el-tag size="small" effect="plain" :type="finalizeResult.quality_gate.compliance_pass ? 'success' : 'danger'" style="margin-left:4px">
                合规自检 {{ finalizeResult.quality_gate.compliance_pass ? '过' : '未过' }}
              </el-tag>
            </div>
            <div class="gate-banner__body">
              <template v-if="finalizeResult.quality_gate.issues && finalizeResult.quality_gate.issues.length">
                <div class="gate-banner__issues-label">发布前建议整改（{{ finalizeResult.quality_gate.issues.length }} 项）：</div>
                <ul class="gate-banner__issues">
                  <li v-for="(iss, i) in finalizeResult.quality_gate.issues.slice(0, 12)" :key="i">{{ iss }}</li>
                </ul>
                <div v-if="finalizeResult.quality_gate.issues.length > 12" class="gate-banner__more">…另有 {{ finalizeResult.quality_gate.issues.length - 12 }} 项，详见下方安全筛选报告</div>
              </template>
              <div v-else class="gate-banner__ok">未检出违禁词 / 硬广 / 联系方式 / AI味 / 软文特征风险项，可放心复制发布。</div>
            </div>
          </div>

          <div class="flow-label flow-label--row">
            <span>✅ 最终标题（可直接复制发布到平台）</span>
            <el-button size="small" :icon="CopyDocument" @click="copyText(finalizeResult.final_title)">复制标题</el-button>
          </div>
          <el-input :model-value="finalizeResult.final_title" readonly class="geo-finalize__title" />

          <div class="flow-label flow-label--row">
            <span>✅ 最终正文（可直接复制发布到平台）</span>
            <el-button size="small" :icon="CopyDocument" @click="copyText(finalizeResult.final_content)">复制正文</el-button>
          </div>
          <el-input :model-value="finalizeResult.final_content" type="textarea" :rows="14" readonly class="geo-finalize__body" />

          <div class="geo-section" v-if="finalizeResult.safety_report">
            <div class="section-label">💡 优化建议（已存档到安全筛选报告）</div>
            <pre class="geo-finalize__suggestions">{{ finalizeResult.safety_report }}</pre>
          </div>

          <div class="geo-finalize__publish">
            <el-button type="primary" :icon="Promotion" @click="openPublishDialog">
              创建发布任务（自动化发布）
            </el-button>
            <span class="geo-finalize__publish-hint">将用上方最终标题/正文建任务，在「发布中心」审核并执行</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Aim, MagicStick, Upload, CircleCheckFilled, WarningFilled, CopyDocument, Promotion } from '@element-plus/icons-vue'

// 步骤 9 的 GEO 评分闸门 + AI 终稿导入（评分/出稿一步到位）。
// 父组件（Production.vue）保留全部状态与逻辑，本组件纯展示 + 函数 prop 下传。
defineProps({
  currentTask: { type: Object, default: null },
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
