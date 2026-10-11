<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  User, OfficeBuilding, Cpu, ShoppingCart, Avatar, UserFilled, Aim, Check,
} from '@element-plus/icons-vue'
import StepHeader from '../../../components/production/StepHeader.vue'

// step4Needs 由父组件持有（任务持久化数据，selectTask 重新解析），本组件就地修改其字段
const props = defineProps({
  options: { type: Object, required: true },
  currentTask: { type: Object, required: true },
  step4Needs: { type: Object, required: true },
  saveDraft: { type: Function, required: true },
  loadingOptions: { type: Boolean, default: false },
})

const geoIntentFilter = ref(0)
const _geoIconMap = { User, OfficeBuilding, Cpu, ShoppingCart, Avatar, UserFilled, Aim }
function geoIconOf(p) { return _geoIconMap[p?.icon] || User }
function roleLabelOf(r) { return { decision_maker: '决策层', technical: '技术层', procurement: '采购层', other: '其他' }[r] || '其他' }

const filteredIntentQuestions = computed(() => {
  const all = props.options.intent_questions || []
  if (!geoIntentFilter.value) return all
  return all.filter(q => q.persona_id === geoIntentFilter.value)
})
const geoSelectedPersona = computed(() =>
  (props.options.target_personas || []).find(p => p.id === props.currentTask?.target_persona_id) || null
)
const geoSelectedIntent = computed(() =>
  (props.options.intent_questions || []).find(q => q.id === props.currentTask?.intent_question_id) || null
)
// 必含品牌信号可选项（勾选后注入提示词，便于 AI 自然归因）
const signalOptions = ['品牌名', '官网', '联系方式', '核心产品', '独特卖点', '数据案例']

// 该画像预置的痛点（用于"必须回应的客户痛点"勾选）
const personaPainOptions = computed(() => {
  const tp = geoSelectedPersona.value
  if (!tp || !tp.pain_points) return []
  return (tp.pain_points || '').split('\n').map(s => s.trim()).filter(Boolean)
})
// 是否已有任何目标客户上下文（用于决定是否展示信号预览）
const hasStep4Context = computed(() =>
  !!(props.currentTask?.target_persona_id || props.currentTask?.intent_question_id ||
    (props.step4Needs.expected_recommendation || '').trim() ||
    (props.step4Needs.required_signals || []).length || (props.step4Needs.must_address_pains || []).length)
)
// 预览将被注入到写作提示词中的 GEO 信号（与后端 prompt_engine 保持一致）
const geoSignalPreview = computed(() => {
  const tp = geoSelectedPersona.value
  const iq = geoSelectedIntent.value
  const n = props.step4Needs
  const lines = []
  if (iq && iq.question) lines.push(`目标客户会问 AI 的问题：${iq.question}`)
  const rec = (n.expected_recommendation || '').trim() || (iq && iq.expected_recommendation) || ''
  if (rec) lines.push(`期望 AI 推荐我们的角度：${rec}`)
  if (tp) {
    lines.push(`目标客户画像：${tp.name}（${roleLabelOf(tp.role_type)}）`)
    if (tp.pain_points) lines.push(`他的痛点：${(tp.pain_points || '').replace(/\n/g, '；')}`)
    if (tp.cares_about) lines.push(`他关心：${(tp.cares_about || '').replace(/\n/g, '；')}`)
  }
  if (n.required_signals && n.required_signals.length) lines.push(`必含品牌信号：${n.required_signals.join('、')}`)
  if (n.must_address_pains && n.must_address_pains.length) lines.push(`必须回应的客户痛点：${n.must_address_pains.join('；')}`)
  return lines.join('\n')
})

// 把第4步核心需求写入任务并持久化（silent=true 时不弹提示，由调用方决定文案）
async function saveStep4Needs(silent = false) {
  if (!props.currentTask?.id) return
  const payload = {
    expected_recommendation: (props.step4Needs.expected_recommendation || '').trim(),
    required_signals: props.step4Needs.required_signals || [],
    must_address_pains: props.step4Needs.must_address_pains || [],
  }
  props.currentTask.target_needs = JSON.stringify(payload)
  await props.saveDraft(true)
  if (!silent) ElMessage.success('已保存第4步核心需求')
}
async function saveStep4Persona(p) {
  props.currentTask.target_persona_id = p.id
  props.currentTask.target_persona_snapshot = `${p.name}（${roleLabelOf(p.role_type)}）`
  // 联动：选画像后意图问题自动跳到该画像的问题
  geoIntentFilter.value = p.id
  // 切换画像时，"必须回应的痛点"默认勾选为该画像的预置痛点
  props.step4Needs.must_address_pains = [...personaPainOptions.value]
  await saveStep4Needs(true)
  ElMessage.success(`已绑定目标画像：${p.name}，意图问题已联动筛选`)
}
async function saveStep4Intent(q) {
  props.currentTask.intent_question_id = q.id
  props.currentTask.intent_question_snapshot = q.question
  // 若该意图问题关联了画像且当前未选画像，自动联动绑定画像并默认勾选其痛点
  if (q.persona_id && !props.currentTask.target_persona_id) {
    const tp = (props.options.target_personas || []).find(p => p.id === q.persona_id)
    if (tp) {
      props.currentTask.target_persona_id = tp.id
      props.currentTask.target_persona_snapshot = `${tp.name}（${roleLabelOf(tp.role_type)}）`
      props.step4Needs.must_address_pains = (tp.pain_points || '').split('\n').map(s => s.trim()).filter(Boolean)
    }
  }
  // 意图问题自带推荐角度：仅在用户尚未自定义时预填
  if (q.expected_recommendation && !(props.step4Needs.expected_recommendation || '').trim()) {
    props.step4Needs.expected_recommendation = q.expected_recommendation
  }
  await saveStep4Needs(true)
  ElMessage.success('已绑定意图问题，需求将注入后续写作')
}
</script>

<template>
  <div class="step-pane">
    <StepHeader :no="4" title="确定目标客户需求" desc="选定目标客户画像与他会问 AI 的意图问题，并定义核心需求——这些要求会注入大纲 / 初稿 / 精修提示词，真实驱动整篇软文。" />
    <div class="geo-demand" v-loading="loadingOptions">
      <div class="geo-demand__grid">
        <div class="geo-demand__col">
          <div class="section-label">① 选择目标客户画像</div>
          <div class="persona-list">
            <div
              v-for="p in options.target_personas || []"
              :key="p.id"
              class="persona-card"
              :class="{ selected: currentTask.target_persona_id === p.id }"
              @click="saveStep4Persona(p)"
            >
              <el-icon class="geo-p-ico" :style="{ color: p.color || '#6366f1' }"><component :is="geoIconOf(p)" /></el-icon>
              <div class="persona-info">
                <div class="persona-name">{{ p.name }}</div>
                <div class="persona-sub">{{ roleLabelOf(p.role_type) }} · {{ (p.pain_points || '').split('\n')[0] || '—' }}</div>
              </div>
            </div>
          </div>
          <div v-if="geoSelectedPersona" class="persona-detail">
            <div class="persona-detail__row"><b>痛点</b>{{ geoSelectedPersona.pain_points || '—' }}</div>
            <div class="persona-detail__row"><b>关注</b>{{ geoSelectedPersona.cares_about || '—' }}</div>
          </div>
        </div>
        <div class="geo-demand__col">
          <div class="section-label">② 选择意图问题（该客户会问 AI 的问题）</div>
          <el-select v-model="geoIntentFilter" placeholder="按画像筛选" clearable size="small" style="width: 100%; margin-bottom: 8px;">
            <el-option label="全部画像" :value="0" />
            <el-option v-for="p in options.target_personas || []" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <div class="geo-q-list">
            <div
              v-for="q in filteredIntentQuestions"
              :key="q.id"
              class="geo-q-item"
              :class="{ selected: currentTask.intent_question_id === q.id }"
              @click="saveStep4Intent(q)"
            >
              <el-icon class="geo-q-ico"><Aim /></el-icon>
              <div class="geo-q-main">
                <div class="geo-q-text">{{ q.question }}</div>
                <div class="geo-q-rec" v-if="q.expected_recommendation">期望推荐：{{ q.expected_recommendation }}</div>
              </div>
            </div>
            <div v-if="filteredIntentQuestions.length === 0" class="empty-tip" style="padding: 16px 0">
              暂无意图问题，请先在「画像与意图问题库」预置默认或新建
            </div>
          </div>
        </div>
      </div>

      <div class="geo-demand__needs" v-if="currentTask.target_persona_id || currentTask.intent_question_id">
        <div class="section-label">③ 定义核心需求（选入的要求将驱动后续软文生产）</div>
        <div class="needs-form">
          <div class="needs-row">
            <label class="needs-label">期望 AI 推荐我们的角度</label>
            <el-input
              v-model="step4Needs.expected_recommendation"
              type="textarea"
              :rows="2"
              placeholder="例如：给出修护 3 步，并自然带出我方在成分浓度 / 屏障修护上的优势（留空则用意图问题自带角度）"
              @blur="saveStep4Needs"
            />
          </div>
          <div class="needs-row">
            <label class="needs-label">必含品牌信号</label>
            <div class="needs-checks">
              <el-checkbox v-for="s in signalOptions" :key="s" v-model="step4Needs.required_signals" :label="s" border size="small">{{ s }}</el-checkbox>
            </div>
          </div>
          <div class="needs-row">
            <label class="needs-label">必须回应的客户痛点</label>
            <div class="needs-checks">
              <el-checkbox v-for="p in personaPainOptions" :key="p" v-model="step4Needs.must_address_pains" :label="p" border size="small">{{ p }}</el-checkbox>
              <span v-if="!personaPainOptions.length" class="needs-hint">该画像暂无预置痛点，可去「画像与意图问题库」补充，或换一个画像</span>
            </div>
          </div>
          <el-button type="primary" size="small" :icon="Check" @click="saveStep4Needs">保存需求</el-button>
        </div>
      </div>

      <div class="geo-demand__signals" v-if="hasStep4Context">
        <div class="section-label">🌟 将注入后续写作的 GEO 信号预览</div>
        <pre class="geo-signal-preview">{{ geoSignalPreview }}</pre>
        <div class="needs-note">以上信号会在「大纲 / 初稿 / 精修」提示词中自动出现，AI 据此回应客户需求、植入推荐角度并保持可被引用。</div>
      </div>
    </div>
  </div>
</template>
