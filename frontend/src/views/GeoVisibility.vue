<template>
  <div class="geo-visibility-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button :icon="Refresh" @click="load" :loading="loading">刷新</el-button>
      <el-button type="primary" :icon="MagicStick" @click="runCollect" :loading="collecting">
        立即探测
      </el-button>
    </Teleport>

    <!-- 顶部：价值说明 + 6 个 KPI -->
    <section class="hero">
      <div class="hero__lead">
        <div class="hero__tags">
          <span class="hero__eyebrow"><el-icon><DataAnalysis /></el-icon> GEO 作战 · 可见性分析</span>
          <el-tag size="small" effect="plain" class="hero__industry">
            <el-icon><OfficeBuilding /></el-icon> {{ store.currentIndustryName }}
          </el-tag>
        </div>
        <h2 class="hero__title">AI 可见性看板：AI 到底怎么回答我们的问题</h2>
        <p class="hero__desc">
          自动向已配置的模型并发提问，解析回答里是否提到品牌、引用了哪些信源，算出 6 个 GEO 核心指标。
          <strong>「被 AI 引用」与「被 AI 点名」同等重要</strong>——回答里没提你、但把你的站作为前 3 信源引用，同样算可见。
        </p>
      </div>

      <div class="filters">
        <el-radio-group v-model="days" size="small" @change="load">
          <el-radio-button :value="7">近 7 天</el-radio-button>
          <el-radio-button :value="30">近 30 天</el-radio-button>
          <el-radio-button :value="90">近 90 天</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="keyword"
          size="small"
          placeholder="按问题关键词筛选"
          clearable
          style="width: 220px"
          @keyup.enter="load"
          @clear="load"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button size="small" :icon="Search" @click="load">筛选</el-button>
      </div>
    </section>

    <div v-loading="loading" class="board">
      <!-- ① 6 个 KPI 卡片 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">核心指标</h3>
          <span class="panel__note">
            样本 {{ kpis.sample_size || 0 }} 条成功探测
            <el-tooltip placement="top" effect="dark">
              <template #content>
                失败的探测（超时 / 限流 / 熔断）不计入分母，<br />
                否则上游故障会被误读成品牌表现变差。
              </template>
              <el-icon class="panel__help"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </div>
        <div class="kpi-grid">
          <div
            v-for="card in kpiCards"
            :key="card.key"
            class="kpi"
            :class="kpiTone(card)"
          >
            <div class="kpi__label">
              {{ card.label }}
              <el-tooltip placement="top" effect="dark" :content="card.hint">
                <el-icon class="kpi__help"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
            <div class="kpi__value">{{ card.display }}</div>
            <div class="kpi__bar">
              <div class="kpi__fill" :style="{ width: kpiPercent(card) + '%' }"></div>
            </div>
          </div>
        </div>
      </section>

      <!-- ② 日粒度趋势 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">日粒度趋势</h3>
          <div class="legend">
            <span class="legend__item"><i class="dot dot--brand"></i>品牌可见率</span>
            <span class="legend__item"><i class="dot dot--top3"></i>Top3 率</span>
            <span class="legend__item"><i class="dot dot--mood"></i>情感分（50% = 中性）</span>
          </div>
        </div>
        <div v-if="hasTrend" class="chart">
          <svg :viewBox="`0 0 ${chart.w} ${chart.h}`" class="chart__svg" preserveAspectRatio="none">
            <!-- 网格 -->
            <line
              v-for="g in chart.grid"
              :key="'g' + g.y"
              :x1="chart.padL" :x2="chart.w - chart.padR"
              :y1="g.y" :y2="g.y"
              class="grid"
            />
            <text
              v-for="g in chart.grid"
              :key="'gl' + g.y"
              :x="chart.padL - 6" :y="g.y + 3"
              class="axis-text" text-anchor="end"
            >{{ g.label }}</text>

            <!-- 中性基线（情感分 50%） -->
            <line
              :x1="chart.padL" :x2="chart.w - chart.padR"
              :y1="chart.neutralY" :y2="chart.neutralY"
              class="neutral-line"
            />

            <!-- 三条折线 -->
            <polyline :points="chart.brand" class="line line--brand" />
            <polyline :points="chart.top3" class="line line--top3" />
            <polyline :points="chart.mood" class="line line--mood" />

            <!-- 数据点 -->
            <circle
              v-for="(p, i) in chart.brandPoints" :key="'b' + i"
              :cx="p.x" :cy="p.y" r="2.5" class="pt pt--brand"
            >
              <title>{{ p.tip }}</title>
            </circle>

            <!-- x 轴刻度：直接画在 SVG 里，才能和折线共用同一套坐标 -->
            <text
              v-for="(t, i) in chart.xTicks" :key="'xt' + i"
              :x="t.x" :y="chart.h - 3"
              class="axis-text" text-anchor="middle"
            >{{ t.label }}</text>
          </svg>
        </div>
        <EmptyState
          v-else
          size="small"
          icon="TrendCharts"
          title="暂无趋势数据"
          description="点击右上角「立即探测」采集第一批数据"
        />
      </section>

      <!-- ③ 信源偏好榜 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">
            信源偏好榜
            <el-tag size="small" type="warning" effect="plain" class="panel__tag">最有商业价值</el-tag>
          </h3>
          <span class="panel__note">哪些站点被 AI 偏爱引用 —— 直接回答「内容该铺到哪里」</span>
        </div>
        <el-table v-if="sourcePreferences.length" :data="sourcePreferences" size="small" class="table">
          <el-table-column label="#" width="46" align="center">
            <template #default="{ $index }">
              <span class="rank" :class="{ 'rank--top': $index < 3 }">{{ $index + 1 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="信源域名" min-width="180">
            <template #default="{ row }">
              <div class="src">
                <span class="src__domain">{{ row.domain }}</span>
                <el-tag v-if="row.is_owned" size="small" type="success" effect="plain">自有站点</el-tag>
                <el-tag v-else size="small" effect="plain" :type="authorityType(row.authority_level)">
                  {{ authorityLabel(row.authority_level) }}
                </el-tag>
              </div>
              <div v-if="row.titles && row.titles.length" class="src__titles">
                {{ row.titles.join(' / ') }}
              </div>
            </template>
          </el-table-column>
          <el-table-column label="被引用" width="120" align="center">
            <template #default="{ row }">
              <div class="cited">
                <span class="cited__num">{{ row.cited_runs }}</span>
                <div class="cited__track">
                  <div class="cited__fill" :style="{ width: (row.share * 100) + '%' }"></div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="最佳名次" width="90" align="center">
            <template #default="{ row }">
              <span :class="row.best_rank <= 3 ? 'rank--top' : ''">{{ row.best_rank || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="行动建议" min-width="240">
            <template #default="{ row }">
              <span class="action">{{ row.action }}</span>
            </template>
          </el-table-column>
        </el-table>
        <EmptyState
          v-else
          size="small"
          icon="Link"
          title="暂无信源数据"
          description="AI 回答里没有解析出可识别的引用来源"
        />
      </section>

      <!-- ④ 选题回流 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">
            对标选题建议
            <el-tag size="small" type="success" effect="plain" class="panel__tag">看板 → 行动</el-tag>
          </h3>
          <span class="panel__note">AI 爱引谁，就去对标谁 —— 只报数字不给动作的看板等于没做</span>
        </div>
        <div v-if="topicSuggestions.length" class="topics">
          <div v-for="(t, i) in topicSuggestions" :key="i" class="topic">
            <div class="topic__head">
              <el-tag size="small" :type="priorityType(t.priority)" effect="dark">{{ t.priority }}优先</el-tag>
              <span class="topic__domain">{{ t.source_domain }}</span>
              <span class="topic__cited">被引用 {{ t.cited_runs }} 次</span>
            </div>
            <div class="topic__title">{{ t.suggested_title }}</div>
            <div class="topic__reason">{{ t.reason }}</div>
            <el-button size="small" text :icon="CopyDocument" @click="copyText(t.suggested_title)">
              复制选题
            </el-button>
          </div>
        </div>
        <EmptyState
          v-else
          size="small"
          icon="Reading"
          title="暂无选题建议"
          description="需要先有非自有信源被 AI 引用"
        />
      </section>

      <!-- ⑤ 竞品对比 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">竞品提及率对比</h3>
          <el-button size="small" :icon="Plus" @click="seedBaseline" :loading="seeding">
            建立本品牌基线
          </el-button>
        </div>

        <div v-if="gap.has_baseline && gap.behind && gap.behind.length" class="gap gap--warn">
          <el-icon><WarningFilled /></el-icon>
          <span>
            有 <strong>{{ gap.behind.length }}</strong> 家竞品提及率高于我们，最高的是
            <strong>{{ gap.behind[0].name }}</strong>（高 {{ (gap.behind[0].gap * 100).toFixed(1) }} 个百分点）
          </span>
        </div>
        <div v-else-if="gap.has_baseline" class="gap gap--ok">
          <el-icon><CircleCheckFilled /></el-icon>
          <span>当前窗口内没有竞品提及率高于我们</span>
        </div>
        <div v-else class="gap gap--muted">
          <el-icon><InfoFilled /></el-icon>
          <span>尚未建立本品牌基线，无法做对比</span>
        </div>

        <el-table v-if="competitorBoard.length" :data="competitorBoard" size="small" class="table">
          <el-table-column label="品牌" min-width="160">
            <template #default="{ row }">
              <span class="comp__name">{{ row.name }}</span>
              <el-tag v-if="row.is_self" size="small" type="primary" effect="plain">本品牌</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="提及率" min-width="200">
            <template #default="{ row }">
              <div class="rate">
                <div class="rate__track">
                  <div
                    class="rate__fill"
                    :class="row.is_self ? 'rate__fill--self' : ''"
                    :style="{ width: (row.mention_rate * 100) + '%' }"
                  ></div>
                </div>
                <span class="rate__val">{{ (row.mention_rate * 100).toFixed(1) }}%</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="mentioned_runs" label="提及探测数" width="110" align="center" />
          <el-table-column prop="avg_rank" label="平均名次" width="100" align="center">
            <template #default="{ row }">{{ row.avg_rank || '-' }}</template>
          </el-table-column>
          <el-table-column label="正面率" width="100" align="center">
            <template #default="{ row }">{{ (row.positive_rate * 100).toFixed(0) }}%</template>
          </el-table-column>
        </el-table>
        <EmptyState
          v-else
          size="small"
          icon="Trophy"
          title="竞品库为空"
          description="先建立本品牌基线，再录入要对比的竞品"
        />
      </section>

      <!-- ⑥ 最近探测 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">最近探测记录</h3>
          <span class="panel__note">共 {{ runTotal }} 条，参与指标计算 {{ sampled }} 条（每关键词每天最多 5 条）</span>
        </div>
        <el-table v-if="runs.length" :data="runs" size="small" class="table">
          <el-table-column prop="create_time" label="时间" width="160" />
          <el-table-column prop="keyword" label="问题" min-width="180" show-overflow-tooltip />
          <el-table-column prop="provider_key" label="引擎" width="130" show-overflow-tooltip />
          <el-table-column label="状态" width="110" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'completed' ? 'success' : 'danger'" effect="plain">
                {{ row.status === 'completed' ? '成功' : (row.error_code || '失败') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="可见" width="80" align="center">
            <template #default="{ row }">
              <el-icon v-if="row.brand_visible" class="ok"><CircleCheckFilled /></el-icon>
              <el-icon v-else class="no"><CircleCloseFilled /></el-icon>
            </template>
          </el-table-column>
          <el-table-column prop="source_count" label="信源" width="80" align="center" />
          <el-table-column prop="best_brand_rank" label="最佳名次" width="100" align="center">
            <template #default="{ row }">{{ row.best_brand_rank || '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" align="center">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="openRun(row.id)">明细</el-button>
              <el-button size="small" text type="danger" @click="removeRun(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <EmptyState
          v-else
          size="small"
          icon="Document"
          title="暂无探测记录"
          description="点击右上角「立即探测」开始采集"
        />
      </section>
    </div>

    <!-- 探测明细抽屉 -->
    <el-drawer v-model="drawer" size="620px" :title="detail ? detail.keyword : '探测明细'">
      <div v-if="detail" class="detail">
        <div class="detail__meta">
          <el-tag size="small" effect="plain">{{ detail.provider_key || detail.provider_type }}</el-tag>
          <span>{{ detail.create_time }}</span>
          <span v-if="detail.latency_ms">{{ detail.latency_ms }} ms</span>
        </div>
        <div class="detail__section">
          <h4>AI 回答原文</h4>
          <pre class="detail__answer">{{ detail.answer_text || '（空）' }}</pre>
        </div>
        <div class="detail__section">
          <h4>被引用的信源（{{ (detail.sources || []).length }}）</h4>
          <div v-for="s in detail.sources || []" :key="s.id" class="detail__src">
            <span class="detail__rank">{{ s.rank }}</span>
            <div class="detail__srcbody">
              <div class="detail__srctitle">{{ s.title }}</div>
              <a v-if="s.url" :href="s.url" target="_blank" rel="noopener" class="detail__srcurl">{{ s.url }}</a>
              <div class="detail__srcmeta">
                <el-tag size="small" effect="plain" :type="authorityType(s.authority_level)">
                  {{ authorityLabel(s.authority_level) }}
                </el-tag>
                <el-tag v-if="s.is_owned" size="small" type="success" effect="plain">自有站点</el-tag>
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  DataAnalysis, OfficeBuilding, Refresh, Search, MagicStick, QuestionFilled,
  Plus, CopyDocument, CircleCheckFilled, CircleCloseFilled, WarningFilled, InfoFilled
} from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { visibilityApi } from '../api'
import { copyText } from '../utils/clipboard'
import EmptyState from '../components/EmptyState.vue'

const store = useAppStore()
const pageActionsTarget = inject('pageActionsTarget', null)

const loading = ref(false)
const collecting = ref(false)
const seeding = ref(false)
const days = ref(30)
const keyword = ref('')
const drawer = ref(false)
const detail = ref(null)

const kpis = ref({})
const kpiCards = ref([])
const trend = ref([])
const sourcePreferences = ref([])
const topicSuggestions = ref([])
const competitorBoard = ref([])
const gap = ref({})
const runs = ref([])
const runTotal = ref(0)
const sampled = ref(0)

const authorityLabel = (level) =>
  ({ high: '高权威', medium: '行业媒体', low: '长尾' }[level] || '长尾')
const authorityType = (level) =>
  ({ high: 'danger', medium: 'warning', low: 'info' }[level] || 'info')
const priorityType = (p) => ({ 高: 'danger', 中: 'warning', 低: 'info' }[p] || 'info')

// 指标卡片的颜色语义：可见率类越高越好，负面率越高越差
const kpiTone = (card) => {
  const v = card.value
  if (card.key === 'negative_rate') return v > 0 ? 'kpi--bad' : 'kpi--good'
  if (card.key === 'sentiment_score') return v > 0 ? 'kpi--good' : v < 0 ? 'kpi--bad' : ''
  if (card.key === 'brand_visibility' || card.key === 'top3_rate') {
    return v >= 0.5 ? 'kpi--good' : v > 0 ? 'kpi--warn' : 'kpi--bad'
  }
  return v > 0 ? 'kpi--good' : ''
}

// 进度条：情感分从 -1~1 映射到 0~100，其余直接乘 100
const kpiPercent = (card) => {
  const v = card.value
  if (card.key === 'sentiment_score') return Math.round(((v + 1) / 2) * 100)
  return Math.max(0, Math.min(100, Math.round(v * 100)))
}

const hasTrend = computed(() => trend.value.some((p) => p.sample_size > 0))

// 手写 SVG 折线图：项目里没有图表库，也不引 CDN（网络受限），
// 直接用 viewBox 坐标画线，零依赖、可控、可测。
const chart = computed(() => {
  const w = 720, h = 220
  const padL = 44, padR = 16, padT = 14, padB = 26
  const innerW = w - padL - padR
  const innerH = h - padT - padB
  const pts = trend.value
  const n = pts.length

  const xAt = (i) => (n <= 1 ? padL : padL + (innerW * i) / (n - 1))
  // 所有序列都映射到 0~100% 的纵轴；情感分用 (v+1)/2 归一，50% 即中性
  const yAt = (pct) => padT + innerH * (1 - Math.max(0, Math.min(100, pct)) / 100)

  const brandPoints = pts.map((p, i) => ({
    x: xAt(i),
    y: yAt((p.brand_visibility || 0) * 100),
    tip: `${p.date} 可见率 ${((p.brand_visibility || 0) * 100).toFixed(1)}%（样本 ${p.sample_size}）`,
  }))

  const line = (getter) => pts.map((p, i) => `${xAt(i)},${yAt(getter(p))}`).join(' ')

  const grid = [0, 25, 50, 75, 100].map((v) => ({ y: yAt(v), label: v + '%' }))

  // x 轴刻度：最多 6 个，避免标签挤在一起；末点必留
  const step = Math.max(1, Math.ceil(n / 6))
  const xTicks = pts
    .map((p, i) => ({ i, label: p.date.slice(5) }))
    .filter(({ i }) => i % step === 0 || i === n - 1)
    .map(({ i, label }) => ({ x: xAt(i), label }))

  return {
    w, h, padL, padR,
    brand: line((p) => (p.brand_visibility || 0) * 100),
    top3: line((p) => (p.top3_rate || 0) * 100),
    mood: line((p) => ((p.sentiment_score || 0) + 1) / 2 * 100),
    brandPoints,
    grid,
    neutralY: yAt(50),
    xTicks,
  }
})

const load = async () => {
  const industryId = store.currentIndustryId
  if (!industryId) return
  loading.value = true
  try {
    const params = { industry_id: industryId, days: days.value, keyword: keyword.value }
    const [ov, runRes] = await Promise.all([
      visibilityApi.overview(params),
      visibilityApi.runs({ ...params, limit: 20 }),
    ])
    const data = ov.data || {}
    kpis.value = data.kpis || {}
    kpiCards.value = data.kpi_cards || []
    trend.value = data.trend || []
    sourcePreferences.value = data.source_preferences || []
    topicSuggestions.value = data.topic_suggestions || []
    competitorBoard.value = data.competitor_board || []
    gap.value = data.gap_analysis || {}
    runTotal.value = data.run_total || 0
    sampled.value = data.sampled || 0

    const list = runRes.data || {}
    runs.value = list.items || []
  } catch (e) {
    // 拦截器已经弹过错误提示，这里只保证界面回到可用状态
  } finally {
    loading.value = false
  }
}

const runCollect = async () => {
  const industryId = store.currentIndustryId
  if (!industryId) return
  collecting.value = true
  try {
    const res = await visibilityApi.collectMulti({
      industry_id: industryId,
      keyword: keyword.value || '敏感肌修护面霜怎么选',
      targets: [],
      max_workers: 4,
      auto_sync_reply: false,
    })
    const d = res.data || {}
    ElMessage.success(`已完成 ${d.total || 0} 个引擎探测，成功 ${d.succeeded || 0} 个`)
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    collecting.value = false
  }
}

const seedBaseline = async () => {
  seeding.value = true
  try {
    await visibilityApi.seedCompetitors(store.currentIndustryId)
    ElMessage.success('本品牌基线已就绪')
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    seeding.value = false
  }
}

const openRun = async (id) => {
  try {
    const res = await visibilityApi.run(id)
    detail.value = res.data
    drawer.value = true
  } catch (e) {
    /* 拦截器已提示 */
  }
}

const removeRun = async (id) => {
  try {
    await ElMessageBox.confirm('删除后该次探测及其信源数据不可恢复，确认删除？', '删除探测记录', {
      type: 'warning',
    })
  } catch {
    return
  }
  await visibilityApi.deleteRun(id)
  ElMessage.success('已删除')
  await load()
}

// copyText 已抽到 utils/clipboard.js（全站统一实现）

onMounted(load)
watch(() => store.currentIndustryId, load)
</script>

<style scoped>
.geo-visibility-view {
  padding: 20px 24px 40px;
}

/* ---------- 顶部 ---------- */
.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 18px;
}
.hero__lead { max-width: 720px; }
.hero__tags {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.hero__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--brand-600);
}
.hero__title {
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}
.hero__desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
}
.hero__desc strong { color: var(--brand-600); }
.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

/* ---------- 面板 ---------- */
.board { display: flex; flex-direction: column; gap: 16px; }
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 16px 18px 18px;
  box-shadow: var(--shadow-xs);
}
.panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.panel__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.panel__tag { font-weight: 500; }
.panel__note {
  font-size: 12px;
  color: var(--text-tertiary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.panel__help { cursor: help; color: var(--text-quaternary); }

/* ---------- KPI ---------- */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}
/* 窄屏退化为两行三列 —— 6 张卡片挤在一行会窄到看不清数字 */
@media (max-width: 1500px) {
  .kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
.kpi {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  background: var(--slate-50);
}
.kpi--good { border-color: rgba(16, 185, 129, 0.35); background: rgba(16, 185, 129, 0.06); }
.kpi--warn { border-color: rgba(245, 158, 11, 0.35); background: rgba(245, 158, 11, 0.06); }
.kpi--bad  { border-color: rgba(244, 63, 94, 0.35);  background: rgba(244, 63, 94, 0.06); }
.kpi__label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.kpi__help { cursor: help; color: var(--text-quaternary); font-size: 12px; }
.kpi__value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.kpi__bar {
  height: 4px;
  margin-top: 8px;
  background: var(--slate-200);
  border-radius: var(--radius-full);
  overflow: hidden;
}
.kpi__fill {
  height: 100%;
  background: var(--brand-500);
  border-radius: var(--radius-full);
  transition: width 0.3s ease;
}
.kpi--good .kpi__fill { background: var(--accent-emerald); }
.kpi--warn .kpi__fill { background: var(--accent-amber); }
.kpi--bad .kpi__fill { background: var(--accent-rose); }

/* ---------- 图表 ---------- */
.legend { display: flex; gap: 14px; flex-wrap: wrap; }
.legend__item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-secondary);
}
.dot { width: 10px; height: 2px; border-radius: 2px; display: inline-block; }
.dot--brand { background: var(--brand-500); }
.dot--top3 { background: var(--accent-cyan); }
.dot--mood { background: var(--accent-amber); }
.chart { width: 100%; }
.chart__svg { width: 100%; height: 220px; display: block; }
.grid { stroke: var(--border-light); stroke-width: 1; }
.neutral-line { stroke: var(--border-base); stroke-width: 1; stroke-dasharray: 4 4; }
.axis-text { font-size: 10px; fill: var(--text-tertiary); }
.line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.line--brand { stroke: var(--brand-500); }
.line--top3 { stroke: var(--accent-cyan); }
.line--mood { stroke: var(--accent-amber); stroke-dasharray: 5 4; }
.pt { fill: var(--brand-500); }
.pt--brand { cursor: pointer; }

/* ---------- 表格通用 ---------- */
.table { width: 100%; }
.rank {
  display: inline-block;
  min-width: 20px;
  font-size: 12px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}
.rank--top { color: var(--accent-amber); font-weight: 700; }
.src { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.src__domain { font-weight: 600; color: var(--text-primary); }
.src__titles {
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cited { display: flex; align-items: center; gap: 6px; }
.cited__num { font-weight: 700; font-variant-numeric: tabular-nums; min-width: 16px; }
.cited__track {
  flex: 1;
  height: 4px;
  background: var(--slate-200);
  border-radius: var(--radius-full);
  overflow: hidden;
}
.cited__fill { height: 100%; background: var(--brand-500); border-radius: var(--radius-full); }
.action { font-size: 12px; color: var(--text-secondary); line-height: 1.6; }

/* ---------- 选题 ---------- */
.topics { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.topic {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  background: var(--slate-50);
}
.topic__head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.topic__domain { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.topic__cited { font-size: 11px; color: var(--text-tertiary); margin-left: auto; }
.topic__title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.6;
  color: var(--text-primary);
  margin-bottom: 6px;
}
.topic__reason { font-size: 12px; color: var(--text-tertiary); line-height: 1.6; }

/* ---------- 竞品 ---------- */
.gap {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  font-size: 13px;
  margin-bottom: 12px;
}
.gap--warn { background: rgba(244, 63, 94, 0.08); color: #b91c1c; }
.gap--ok { background: rgba(16, 185, 129, 0.08); color: #047857; }
.gap--muted { background: var(--slate-100); color: var(--text-secondary); }
.comp__name { font-weight: 600; margin-right: 6px; }
.rate { display: flex; align-items: center; gap: 8px; }
.rate__track {
  flex: 1;
  height: 6px;
  background: var(--slate-200);
  border-radius: var(--radius-full);
  overflow: hidden;
}
.rate__fill { height: 100%; background: var(--slate-400); border-radius: var(--radius-full); }
.rate__fill--self { background: var(--brand-500); }
.rate__val {
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  min-width: 46px;
  text-align: right;
}
.ok { color: var(--accent-emerald); }
.no { color: var(--slate-300); }

/* ---------- 明细抽屉 ---------- */
.detail__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--text-tertiary);
  margin-bottom: 14px;
}
.detail__section { margin-bottom: 20px; }
.detail__section h4 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.detail__answer {
  margin: 0;
  padding: 12px;
  background: var(--slate-50);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  font-size: 12px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow: auto;
  font-family: inherit;
}
.detail__src {
  display: flex;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-light);
}
.detail__rank {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: var(--radius-sm);
  background: var(--brand-500);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.detail__srcbody { flex: 1; min-width: 0; }
.detail__srctitle { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.detail__srcurl {
  display: block;
  font-size: 11px;
  color: var(--brand-600);
  word-break: break-all;
  margin: 2px 0 4px;
}
.detail__srcmeta { display: flex; gap: 6px; }
</style>
