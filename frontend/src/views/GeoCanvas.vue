<template>
  <div class="geo-canvas-view">
    <!-- 顶部：GEO 定位画布价值说明 + 洞察指标 -->
    <section class="hero">
      <div class="hero__lead">
        <div class="hero__tags">
          <span class="hero__eyebrow"><el-icon><Aim /></el-icon> GEO 作战 · 定位画布（三环定位法）</span>
          <el-tag size="small" effect="plain"><el-icon><OfficeBuilding /></el-icon> {{ store.currentIndustryName }}</el-tag>
        </div>
        <h2 class="hero__title">三环交叉定位：哪类客户、问什么问题时，AI 应该推荐我们</h2>
        <p class="hero__desc">把「客户画像 × 意图问题 × 品牌独特优势」三处数据交叉呈现在一张画布上，快速找到 GEO 定位点——当目标客户向 AI 提问时，AI 应该从什么角度推荐我们。下方定位点清单按优先级排列，标注覆盖缺口。</p>
      </div>
      <div class="hero__metrics">
        <div class="metric">
          <div class="metric__num">{{ insights.persona_count || 0 }}</div>
          <div class="metric__label">客户画像</div>
        </div>
        <div class="metric">
          <div class="metric__num">{{ insights.question_count || 0 }}</div>
          <div class="metric__label">意图问题</div>
        </div>
        <div class="metric" :class="{ 'metric--warn': !insights.has_brand }">
          <div class="metric__num">{{ insights.brand_count || 0 }}</div>
          <div class="metric__label">品牌资产</div>
        </div>
        <div class="metric" :class="{ 'metric--warn': (insights.gap_count || 0) > 0 }">
          <div class="metric__num">{{ insights.gap_count || 0 }}</div>
          <div class="metric__label">待覆盖缺口</div>
        </div>
      </div>
    </section>

    <!-- 缺口提醒 -->
    <div v-if="gapHints.length" class="gap-alerts">
      <div v-for="(h, i) in gapHints" :key="i" class="gap-alert" :class="'gap-alert--' + h.level">
        <el-icon class="gap-alert__icon"><WarningFilled v-if="h.level === 'danger'" /><InfoFilled v-else /></el-icon>
        <span class="gap-alert__text">{{ h.text }}</span>
        <el-button v-if="h.action" text size="small" type="primary" @click="h.action">{{ h.actionLabel }}</el-button>
      </div>
    </div>

    <!-- 三环画布 -->
    <div class="canvas-grid" v-loading="loading">
      <!-- 环①：客户画像 -->
      <div class="ring ring--persona">
        <div class="ring__head">
          <span class="ring__icon" style="background: #6366f122; color: #6366f1;"><el-icon><User /></el-icon></span>
          <div>
            <div class="ring__title">细分人群</div>
            <div class="ring__sub">谁会向 AI 提问</div>
          </div>
        </div>
        <div class="ring__body">
          <div v-for="p in data.personas" :key="p.id"
            class="persona-card"
            :class="{ 'is-active': selectedPersonaId === p.id }"
            :style="{ '--p-color': p.color || '#6366f1' }"
            @click="togglePersona(p.id)"
          >
            <div class="persona-card__head">
              <span class="persona-card__name">{{ p.name }}</span>
              <el-tag size="small" effect="plain" :style="{ color: p.color || '#6366f1', borderColor: (p.color || '#6366f1') + '55' }">
                {{ roleLabel(p.role_type) }}
              </el-tag>
            </div>
            <div class="persona-card__desc" v-if="p.description">{{ p.description }}</div>
            <div class="persona-card__pains" v-if="p.pain_points && p.pain_points.length">
              <span class="pc-label">痛点：</span>
              <span v-for="pp in p.pain_points.slice(0, 3)" :key="pp" class="pc-chip pc-chip--pain">{{ pp }}</span>
            </div>
            <div class="persona-card__cares" v-if="p.cares_about && p.cares_about.length">
              <span class="pc-label">关注：</span>
              <span v-for="ca in p.cares_about.slice(0, 3)" :key="ca" class="pc-chip pc-chip--care">{{ ca }}</span>
            </div>
            <div class="persona-card__count">
              <el-icon><ChatDotRound /></el-icon> {{ p.questions?.length || 0 }} 个意图问题
            </div>
          </div>
          <div v-if="!data.personas?.length" class="ring-empty">暂无客户画像<br><router-link to="/persona">去创建 →</router-link></div>
        </div>
      </div>

      <!-- 环②：意图问题 -->
      <div class="ring ring--question">
        <div class="ring__head">
          <span class="ring__icon" style="background: #14b8a622; color: #14b8a6;"><el-icon><ChatDotRound /></el-icon></span>
          <div>
            <div class="ring__title">特定问题</div>
            <div class="ring__sub">客户会问 AI 什么</div>
          </div>
        </div>
        <div class="ring__body">
          <template v-if="visibleQuestions.length">
            <div v-for="q in visibleQuestions" :key="q.id" class="question-card"
              :class="{ 'is-covered': q.coverage_status === 'covered' }">
              <div class="question-card__head">
                <span class="question-card__text">{{ q.question }}</span>
                <el-tag size="small" :type="q.coverage_status === 'covered' ? 'success' : 'warning'" effect="plain">
                  {{ q.coverage_status === 'covered' ? '已覆盖' : '待覆盖' }}
                </el-tag>
              </div>
              <div class="question-card__rec" v-if="q.expected_recommendation">
                <el-icon><Aim /></el-icon>
                <span>{{ q.expected_recommendation }}</span>
              </div>
              <div class="question-card__meta">
                <el-tag size="small" effect="plain" type="info">{{ intentLabel(q.intent_category) }}</el-tag>
                <span class="q-priority">优先级 {{ q.priority }}</span>
              </div>
            </div>
          </template>
          <div v-else class="ring-empty">
            {{ selectedPersonaId ? '该画像暂无关联问题' : '暂无意图问题' }}<br>
            <router-link to="/intent-question">去创建 →</router-link>
          </div>
        </div>
      </div>

      <!-- 环③：品牌独特优势 -->
      <div class="ring ring--brand">
        <div class="ring__head">
          <span class="ring__icon" style="background: #f59e0b22; color: #f59e0b;"><el-icon><GoldMedal /></el-icon></span>
          <div>
            <div class="ring__title">独特优势</div>
            <div class="ring__sub">AI 应推荐我们的理由</div>
          </div>
        </div>
        <div class="ring__body">
          <template v-if="data.brands?.length">
            <div v-for="b in data.brands" :key="b.id" class="brand-card">
              <div class="brand-card__name">{{ b.brand_name }}</div>
              <el-tag v-if="b.is_default" size="small" type="warning" effect="dark" style="margin-bottom: 8px;">默认品牌</el-tag>
              <div class="brand-card__section" v-if="b.usp_list && b.usp_list.length">
                <div class="bc-label">独特卖点</div>
                <div v-for="usp in b.usp_list" :key="usp" class="bc-item">
                  <el-icon><CircleCheckFilled /></el-icon> {{ usp }}
                </div>
              </div>
              <div class="brand-card__section" v-if="b.core_products_list && b.core_products_list.length">
                <div class="bc-label">核心产品</div>
                <div class="bc-tags">
                  <el-tag v-for="cp in b.core_products_list.slice(0, 5)" :key="cp" size="small" effect="plain">{{ cp }}</el-tag>
                </div>
              </div>
              <div class="brand-card__section" v-if="b.slogan">
                <div class="bc-label">品牌口号</div>
                <div class="bc-slogan">"{{ b.slogan }}"</div>
              </div>
            </div>
          </template>
          <div v-else class="ring-empty">暂无品牌资产<br><router-link to="/brand-asset">去创建 →</router-link></div>
        </div>
      </div>
    </div>

    <!-- 定位点清单：人群 × 问题 × 推荐角度 -->
    <div class="positioning-section">
      <div class="ps-head">
        <span class="ps-title"><el-icon><Aim /></el-icon> GEO 定位点清单</span>
        <span class="ps-sub">每个定位点 = 一类客户 × 一个问题 × AI 应推荐我们的角度；红色为待覆盖缺口</span>
      </div>
      <div class="ps-grid" v-if="data.positioning_points?.length">
        <div v-for="pp in sortedPositioningPoints" :key="pp.question_id + '-' + pp.persona_id"
          class="pp-card"
          :class="{ 'pp-card--gap': pp.coverage_status === 'gap', 'pp-card--covered': pp.coverage_status === 'covered' }">
          <div class="pp-card__persona">
            <el-icon><User /></el-icon>
            <span>{{ pp.persona_name }}</span>
            <el-tag size="small" effect="plain" type="info">{{ roleLabel(pp.persona_role) }}</el-tag>
          </div>
          <div class="pp-card__question">
            <el-icon><ChatDotRound /></el-icon>
            <span>{{ pp.question }}</span>
          </div>
          <div class="pp-card__rec" v-if="pp.expected_recommendation">
            <el-icon><Aim /></el-icon>
            <span>{{ pp.expected_recommendation }}</span>
          </div>
          <div class="pp-card__rec pp-card__rec--empty" v-else>
            <el-icon><EditPen /></el-icon>
            <span>未设定推荐角度（去意图问题库补充）</span>
          </div>
          <div class="pp-card__foot">
            <el-tag size="small" :type="pp.coverage_status === 'covered' ? 'success' : 'warning'" effect="dark">
              {{ pp.coverage_status === 'covered' ? '已覆盖' : '待覆盖' }}
            </el-tag>
            <span class="pp-priority">
              <el-rate :model-value="pp.priority" disabled size="small" />
            </span>
            <el-tag v-if="!pp.brand_ready" size="small" type="danger" effect="plain">品牌资产缺失</el-tag>
          </div>
        </div>
      </div>
      <EmptyState v-else title="暂无定位点" description="创建客户画像与意图问题后，定位点会自动生成" icon="Aim" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Aim, User, ChatDotRound, GoldMedal, OfficeBuilding, WarningFilled, InfoFilled, CircleCheckFilled, EditPen } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { geoCanvasApi } from '../api'
import EmptyState from '../components/EmptyState.vue'

const store = useAppStore()
const loading = ref(false)
const data = ref({})
const selectedPersonaId = ref(null)

const insights = computed(() => data.value.insights || {})

const gapHints = computed(() => {
  const hints = []
  const ins = insights.value
  if (!ins.has_brand) {
    hints.push({ level: 'danger', text: '尚未配置品牌资产——AI 无从推荐你。请先在「品牌资产库」填写品牌名与独特卖点。', actionLabel: '去配置', action: () => window.location.hash = '#/brand-asset' })
  }
  if (ins.persona_count === 0) {
    hints.push({ level: 'danger', text: '尚未创建客户画像——定位画布缺少「细分人群」这一环。', actionLabel: '去创建', action: () => window.location.hash = '#/persona' })
  }
  if (ins.question_count === 0) {
    hints.push({ level: 'danger', text: '尚未创建意图问题——定位画布缺少「特定问题」这一环。', actionLabel: '去创建', action: () => window.location.hash = '#/intent-question' })
  }
  if (ins.personas_without_question && ins.personas_without_question.length) {
    hints.push({ level: 'warning', text: `${ins.personas_without_question.length} 个画像暂无关联意图问题（${ins.personas_without_question.join('、')}），建议补充。` })
  }
  if (ins.gap_count > 0) {
    hints.push({ level: 'warning', text: `${ins.gap_count} 个意图问题标记为「待覆盖」——尚未有内容回应这些问题，是 GEO 内容生产的高优先缺口。` })
  }
  if (ins.orphan_question_count > 0) {
    hints.push({ level: 'info', text: `${ins.orphan_question_count} 个意图问题未关联画像，建议在意图问题库绑定对应客户画像。` })
  }
  return hints
})

const visibleQuestions = computed(() => {
  if (selectedPersonaId.value) {
    const p = data.value.personas?.find(p => p.id === selectedPersonaId.value)
    return p?.questions || []
  }
  // 默认显示所有问题（扁平化）
  const all = []
  for (const p of data.value.personas || []) {
    all.push(...(p.questions || []))
  }
  all.push(...(data.value.orphan_questions || []))
  return all
})

const sortedPositioningPoints = computed(() => {
  const pts = data.value.positioning_points || []
  return [...pts].sort((a, b) => {
    // 待覆盖优先，再按优先级降序
    if (a.coverage_status !== b.coverage_status) {
      return a.coverage_status === 'gap' ? -1 : 1
    }
    return (b.priority || 0) - (a.priority || 0)
  })
})

function togglePersona(id) {
  selectedPersonaId.value = selectedPersonaId.value === id ? null : id
}

function roleLabel(r) {
  return { decision_maker: '决策者', technical: '技术/工艺', procurement: '采购', other: '其他' }[r] || r || '其他'
}
function intentLabel(c) {
  return { selection: '选型', cost: '成本/回本', integration: '集成/兼容', risk: '风险/可靠性', compliance: '合规', other: '其他' }[c] || c || '其他'
}

async function loadCanvas() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const res = await geoCanvasApi.get(store.currentIndustryId)
    data.value = res.data || {}
  } finally {
    loading.value = false
  }
}

watch(() => store.currentIndustryId, loadCanvas)
onMounted(loadCanvas)
</script>

<style scoped>
.geo-canvas-view { display: flex; flex-direction: column; gap: 16px; }

/* hero */
.hero {
  display: flex; gap: 24px; align-items: stretch;
  background: linear-gradient(135deg, rgba(99,102,241,0.10), rgba(20,184,166,0.07));
  border: 1px solid var(--border-light); border-left: 4px solid #6366f1;
  border-radius: var(--radius-lg); padding: 20px 24px;
}
.hero__lead { flex: 1; min-width: 0; }
.hero__tags { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.hero__eyebrow { font-size: 12px; font-weight: 600; color: #6366f1; display: flex; align-items: center; gap: 4px; }
.hero__title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin: 0 0 6px; }
.hero__desc { font-size: 13px; color: var(--text-secondary); line-height: 1.7; margin: 0; }
.hero__metrics { display: flex; gap: 20px; flex-shrink: 0; }
.metric { text-align: center; min-width: 64px; }
.metric__num { font-size: 28px; font-weight: 800; color: var(--text-primary); line-height: 1.2; }
.metric__label { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }
.metric--warn .metric__num { color: #f59e0b; }

/* gap alerts */
.gap-alerts { display: flex; flex-direction: column; gap: 8px; }
.gap-alert {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; border-radius: var(--radius-md); font-size: 13px;
}
.gap-alert--danger { background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c; }
.gap-alert--warning { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; }
.gap-alert--info { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; }
.gap-alert__icon { font-size: 16px; flex-shrink: 0; }
.gap-alert__text { flex: 1; }

/* canvas grid */
.canvas-grid {
  display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px;
  min-height: 400px;
}
.ring {
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-lg); overflow: hidden;
  display: flex; flex-direction: column;
}
.ring--persona { border-top: 3px solid #6366f1; }
.ring--question { border-top: 3px solid #14b8a6; }
.ring--brand { border-top: 3px solid #f59e0b; }
.ring__head { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--border-light); }
.ring__icon { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px; flex-shrink: 0; }
.ring__title { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.ring__sub { font-size: 11px; color: var(--text-tertiary); }
.ring__body { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; max-height: 520px; }
.ring-empty { text-align: center; color: var(--text-tertiary); font-size: 13px; padding: 40px 0; line-height: 2; }
.ring-empty a { color: #6366f1; text-decoration: none; }

/* persona card */
.persona-card {
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-left: 3px solid var(--p-color, #6366f1);
  border-radius: var(--radius-md); padding: 12px 14px; cursor: pointer;
  transition: border-color .15s, box-shadow .15s;
}
.persona-card:hover { box-shadow: var(--shadow-sm); border-color: var(--p-color, #6366f1); }
.persona-card.is-active { box-shadow: 0 0 0 3px color-mix(in srgb, var(--p-color, #6366f1) 20%, transparent); }
.persona-card__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.persona-card__name { font-size: 13px; font-weight: 700; color: var(--text-primary); }
.persona-card__desc { font-size: 12px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 6px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.persona-card__pains, .persona-card__cares { display: flex; gap: 4px; flex-wrap: wrap; align-items: center; margin-bottom: 4px; }
.pc-label { font-size: 11px; color: var(--text-tertiary); flex-shrink: 0; }
.pc-chip { font-size: 11px; padding: 2px 7px; border-radius: 4px; }
.pc-chip--pain { background: #fef2f2; color: #b91c1c; }
.pc-chip--care { background: #eff6ff; color: #1e40af; }
.persona-card__count { font-size: 11px; color: var(--text-tertiary); display: flex; align-items: center; gap: 4px; margin-top: 4px; }

/* question card */
.question-card {
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-left: 3px solid #14b8a6; border-radius: var(--radius-md); padding: 12px 14px;
}
.question-card.is-covered { border-left-color: #10b981; }
.question-card__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.question-card__text { font-size: 13px; font-weight: 600; color: var(--text-primary); line-height: 1.5; flex: 1; }
.question-card__rec { display: flex; align-items: flex-start; gap: 6px; font-size: 12px; color: #0e7490; line-height: 1.5; margin-bottom: 6px; }
.question-card__rec .el-icon { margin-top: 1px; flex-shrink: 0; }
.question-card__meta { display: flex; align-items: center; gap: 8px; }
.q-priority { font-size: 11px; color: var(--text-tertiary); }

/* brand card */
.brand-card {
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-left: 3px solid #f59e0b; border-radius: var(--radius-md); padding: 12px 14px;
}
.brand-card__name { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.brand-card__section { margin-top: 8px; }
.bc-label { font-size: 11px; font-weight: 600; color: var(--text-tertiary); margin-bottom: 4px; }
.bc-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); line-height: 1.6; }
.bc-item .el-icon { color: #10b981; font-size: 13px; flex-shrink: 0; }
.bc-tags { display: flex; gap: 4px; flex-wrap: wrap; }
.bc-slogan { font-size: 12px; color: #92400e; font-style: italic; }

/* positioning section */
.positioning-section {
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-lg); padding: 16px 20px;
}
.ps-head { margin-bottom: 14px; }
.ps-title { font-size: 15px; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 6px; }
.ps-sub { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; display: block; }
.ps-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px;
}
.pp-card {
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-md); padding: 12px 14px;
  display: flex; flex-direction: column; gap: 6px;
}
.pp-card--gap { border-left: 3px solid #f59e0b; background: #fffbeb; }
.pp-card--covered { border-left: 3px solid #10b981; }
.pp-card__persona { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); }
.pp-card__question { display: flex; align-items: flex-start; gap: 6px; font-size: 13px; font-weight: 600; color: var(--text-primary); line-height: 1.5; }
.pp-card__question .el-icon { margin-top: 2px; flex-shrink: 0; color: #14b8a6; }
.pp-card__rec { display: flex; align-items: flex-start; gap: 6px; font-size: 12px; color: #0e7490; line-height: 1.5; }
.pp-card__rec .el-icon { margin-top: 1px; flex-shrink: 0; }
.pp-card__rec--empty { color: var(--text-tertiary); font-style: italic; }
.pp-card__foot { display: flex; align-items: center; gap: 8px; margin-top: 2px; }
.pp-priority { display: flex; align-items: center; }

@media (max-width: 1100px) {
  .canvas-grid { grid-template-columns: 1fr; }
  .hero { flex-direction: column; }
  .hero__metrics { justify-content: space-around; }
}
</style>
