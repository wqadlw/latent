<template>
  <div class="geo-loop-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button :icon="Upload" @click="importDialog = true">导入访问日志</el-button>
      <el-button type="primary" :icon="Refresh" @click="load" :loading="loading">刷新</el-button>
    </Teleport>

    <!-- 顶部 -->
    <section class="hero">
      <div class="hero__lead">
        <div class="hero__tags">
          <span class="hero__eyebrow"><el-icon><Connection /></el-icon> GEO 作战 · 归因闭环</span>
          <el-tag size="small" effect="plain">
            <el-icon><OfficeBuilding /></el-icon> {{ store.currentIndustryName }}
          </el-tag>
        </div>
        <h2 class="hero__title">归因闭环：发了多少 → AI 看了多少 → 引用了几篇</h2>
        <p class="hero__desc">
          把「收录观测」与「AI 引用分析」接成一条链：
          <strong>发布 → 收录 → 引用 → 排名</strong>。
          每一环都能点进去看原始记录，最后回流成可执行的选题。
          <span class="hero__warn">只被搜索引擎抓过不等于 AI 收录</span>——两者分开统计。
        </p>
      </div>

      <div class="filters">
        <el-radio-group v-model="days" size="small" @change="load">
          <el-radio-button :value="30">近 30 天</el-radio-button>
          <el-radio-button :value="90">近 90 天</el-radio-button>
          <el-radio-button :value="365">近一年</el-radio-button>
        </el-radio-group>
      </div>
    </section>

    <div v-loading="loading" class="board">
      <!-- ① 闭环诊断 -->
      <section class="panel panel--diag" :class="diagClass">
        <div class="diag">
          <el-icon class="diag__icon"><component :is="diagIcon" /></el-icon>
          <div class="diag__body">
            <div class="diag__label">{{ health.label || '闭环尚未开始' }}</div>
            <div class="diag__detail">{{ health.detail }}</div>
            <div v-if="health.next_step" class="diag__next">
              <el-icon><ArrowRight /></el-icon> {{ health.next_step }}
            </div>
            <!-- 路径配错的**证据**：只报「路径对不上」而不给出具体是哪两条，
                 运营还得自己去日志里翻。把成对的路径直接摊开，一眼就能改。 -->
            <ul v-if="nearMiss.length" class="diag__evidence">
              <li v-for="m in nearMiss.slice(0, 5)" :key="m.hit_path">
                <code class="diag__path diag__path--hit">{{ m.hit_path }}</code>
                <span class="diag__arrow">↔</span>
                <code class="diag__path diag__path--pub">{{ m.published_path }}</code>
                <span class="diag__hits">{{ m.ai_hits }} 次</span>
              </li>
            </ul>
          </div>
          <div v-if="health.transition_rate != null" class="diag__rate">
            {{ (health.transition_rate * 100).toFixed(1) }}%
            <span class="diag__rate-label">该环节转化率</span>
          </div>
        </div>
      </section>

      <!-- ② 四阶段漏斗 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">四阶段漏斗</h3>
          <span class="panel__note">
            <!-- 只有存在「别处的流量」时才展开拆解；全部命中本行业时括号里
                 只会重复同一个数字，反而干扰阅读。 -->
            窗口内 AI 抓取 {{ funnel.ai_crawl_total || 0 }} 次<template v-if="hasHitSplit">（本行业内容命中 {{ funnel.matched_ai_hits || 0 }} 次<template
              v-if="funnel.other_industry_ai_hits"
            > · 其他行业空间 {{ funnel.other_industry_ai_hits }} 次</template><template
              v-if="funnel.unmatched_ai_hits"
            > · <span class="warn-text">对不上任何内容 {{ funnel.unmatched_ai_hits }} 次</span></template>）</template>
            <template v-if="funnel.search_only_count">
              · <span class="warn-text">{{ funnel.search_only_count }} 篇只被搜索引擎抓过，AI 从未到访</span>
            </template>
          </span>
        </div>
        <div class="funnel">
          <template v-for="(s, i) in stages" :key="s.key">
            <div v-if="i > 0" class="funnel__gap">
              <span class="funnel__arrow">↓</span>
              <span class="funnel__conv" :class="convClass(s)">
                转化 {{ (s.rate_of_prev * 100).toFixed(1) }}%
              </span>
              <span v-if="s.rate_of_prev < 0.5" class="funnel__flag">流失最大</span>
            </div>
            <div class="funnel__row">
              <div class="funnel__label">
                <span class="funnel__name">{{ s.label }}</span>
                <el-tooltip placement="top" effect="dark" :content="s.desc">
                  <el-icon class="funnel__help"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="funnel__track">
                <div class="funnel__fill" :style="{ width: (s.rate_of_published * 100) + '%' }"></div>
              </div>
              <div class="funnel__value">
                <strong>{{ s.value }}</strong>
                <span class="funnel__pct">{{ (s.rate_of_published * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </template>
        </div>
        <EmptyState
          v-if="!funnel.counts || !funnel.counts.published"
          size="small"
          icon="Files"
          title="还没有已发布的内容"
          description="闭环的起点是「已填写发布 URL」的内容 —— 先在软文生产里完成并发布"
        />
      </section>

      <!-- ③ 回流选题 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">
            回流选题
            <el-tag size="small" type="success" effect="plain">观测 → 动作</el-tag>
          </h3>
          <span class="panel__note">按「越该先做越靠前」排序</span>
        </div>
        <div v-if="recycle.length" class="recycles">
          <div v-for="(r, i) in recycle" :key="i" class="recycle" :class="'recycle--' + r.kind">
            <div class="recycle__head">
              <el-tag size="small" :type="kindType(r.kind)" effect="dark">{{ kindLabel(r.kind) }}</el-tag>
              <el-tag size="small" :type="priorityType(r.priority)" effect="plain">{{ r.priority }}优先</el-tag>
              <span class="recycle__basis">{{ r.basis }}</span>
            </div>
            <div class="recycle__title">{{ r.title }}</div>
            <div class="recycle__reason">{{ r.reason }}</div>
            <div class="recycle__action">
              <el-icon><Right /></el-icon>
              <span>{{ r.action }}</span>
            </div>
            <div class="recycle__foot">
              <el-button v-if="r.url" size="small" text :icon="View" @click="openJourney(r.url)">查看旅程</el-button>
              <el-button size="small" text :icon="CopyDocument" @click="copyText(r.action)">复制动作</el-button>
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          size="small"
          icon="Reading"
          title="暂无回流建议"
          description="需要有已发布内容才能生成回流动作"
        />
      </section>

      <!-- ④ 内容归因表 -->
      <section class="panel">
        <div class="panel__head">
          <h3 class="panel__title">内容归因</h3>
          <div class="filters">
            <el-select v-model="statusFilter" size="small" clearable placeholder="全部状态" style="width: 150px">
              <el-option label="未被 AI 抓取" value="not_crawled" />
              <el-option label="已抓取未被引用" value="crawled_only" />
              <el-option label="已被引用" value="cited" />
              <el-option label="已进前 3" value="top3" />
            </el-select>
          </div>
        </div>
        <el-table v-if="filteredAttribution.length" :data="filteredAttribution" size="small" class="table">
          <el-table-column label="标题" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="c-title">{{ row.title }}</div>
              <a v-if="row.url" :href="row.url" target="_blank" rel="noopener" class="c-url">{{ row.url }}</a>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="140" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)" effect="plain">{{ row.status_label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="AI 抓取" width="90" align="center">
            <template #default="{ row }">
              <span :class="row.ai_hits ? '' : 'dim'">{{ row.ai_hits }}</span>
            </template>
          </el-table-column>
          <el-table-column label="抓取器" width="140" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.ai_bots && row.ai_bots.length" class="bots">{{ row.ai_bots.join('、') }}</span>
              <span v-else class="dim">—</span>
            </template>
          </el-table-column>
          <el-table-column label="被引用" width="80" align="center">
            <template #default="{ row }">
              <span :class="row.cited_times ? '' : 'dim'">{{ row.cited_times }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最佳名次" width="90" align="center">
            <template #default="{ row }">
              <span :class="row.best_rank && row.best_rank <= 3 ? 'rank--top' : 'dim'">
                {{ row.best_rank || '—' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" align="center">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="openJourney(row.url)">旅程</el-button>
            </template>
          </el-table-column>
        </el-table>
        <EmptyState
          v-else
          size="small"
          icon="Document"
          title="暂无归因数据"
          description="需要有已填写发布 URL 的内容，并导入过站点访问日志"
        />
      </section>
    </div>

    <!-- 内容旅程抽屉 -->
    <el-drawer v-model="drawer" size="680px" :title="journey ? journey.path : '内容旅程'">
      <div v-if="journey" class="journey">
        <div class="journey__stats">
          <div class="js">
            <div class="js__num">{{ journey.ai_hits }}</div>
            <div class="js__label">AI 抓取</div>
          </div>
          <div class="js">
            <div class="js__num">{{ journey.search_hits }}</div>
            <div class="js__label">搜索引擎抓取</div>
          </div>
          <div class="js">
            <div class="js__num">{{ journey.cited_times }}</div>
            <div class="js__label">被引用</div>
          </div>
          <div class="js" :class="journey.best_rank && journey.best_rank <= 3 ? 'js--good' : ''">
            <div class="js__num">{{ journey.best_rank || '—' }}</div>
            <div class="js__label">最佳名次</div>
          </div>
        </div>

        <el-alert :title="journey.status_label" :description="journey.action"
                  :type="statusType(journey.status)" show-icon :closable="false" class="journey__alert" />

        <div class="journey__section">
          <h4>AI 引用记录（{{ (journey.citations || []).length }}）</h4>
          <div v-if="(journey.citations || []).length" class="jlist">
            <div v-for="c in journey.citations" :key="c.source_id" class="jitem">
              <span class="jitem__rank" :class="c.rank <= 3 ? 'jitem__rank--top' : ''">{{ c.rank }}</span>
              <div class="jitem__body">
                <div class="jitem__kw">{{ c.keyword || '（未记录问题）' }}</div>
                <div class="jitem__meta">
                  <span>{{ c.domain }}</span>
                  <span v-if="c.is_owned" class="own">自有站点</span>
                  <span class="dim">{{ c.create_time }}</span>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="jempty">从未被 AI 引用</div>
        </div>

        <div class="journey__section">
          <h4>抓取记录（{{ (journey.crawl_records || []).length }}）</h4>
          <div v-if="(journey.crawl_records || []).length" class="jlist">
            <div v-for="h in journey.crawl_records" :key="h.id" class="jitem">
              <span class="jitem__dot" :class="'dot--' + h.bot_class"></span>
              <div class="jitem__body">
                <div class="jitem__kw">
                  {{ h.bot_name }}
                  <el-tag size="small" effect="plain" :type="botType(h.bot_class)">
                    {{ botLabel(h.bot_class) }}
                  </el-tag>
                </div>
                <div class="jitem__meta">
                  <span>{{ h.time }}</span>
                  <span>{{ h.method }} {{ h.status_code }}</span>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="jempty">从未被抓取 —— 检查 sitemap.xml / llms.txt 与 robots.txt</div>
        </div>
      </div>
    </el-drawer>

    <!-- 导入访问日志 -->
    <el-dialog v-model="importDialog" title="导入站点访问日志" width="640px">
      <p class="dlg__hint">
        把外部站点的 Nginx / Apache 访问日志（Combined Log Format）粘贴进来。
        系统会在本地解析、分类爬虫、归因到具体文章 —— 不会上传到任何第三方。
      </p>
      <el-input v-model="logText" type="textarea" :rows="10"
                placeholder='127.0.0.1 - - [10/Oct/2026:20:57:06 +0800] "GET /case/vacuum-pump HTTP/1.1" 200 1234 "-" "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)"' />
      <template #footer>
        <el-button @click="importDialog = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="doImport">解析并导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Connection, OfficeBuilding, Refresh, Upload, QuestionFilled, ArrowRight, Right,
  View, CopyDocument, WarningFilled, InfoFilled, CircleCloseFilled
} from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { crawlerApi } from '../api'
import { copyText } from '../utils/clipboard'
import EmptyState from '../components/EmptyState.vue'

const store = useAppStore()
const pageActionsTarget = inject('pageActionsTarget', null)

const loading = ref(false)
const importing = ref(false)
const importDialog = ref(false)
const logText = ref('')
const days = ref(90)
const statusFilter = ref('')
const drawer = ref(false)

const funnel = ref({ counts: {}, stages: [] })
const health = ref({})
const attribution = ref([])
const recycle = ref([])
const journey = ref(null)

const stages = computed(() => funnel.value.stages || [])

const filteredAttribution = computed(() => {
  if (!statusFilter.value) return attribution.value
  return attribution.value.filter((r) => r.status === statusFilter.value)
})

// 路径配错的成对证据，直接摊在诊断条里，省得运营再去翻日志
const nearMiss = computed(() => health.value?.funnel?.near_miss || [])

// 只有存在「不属于本行业的 AI 流量」时才需要展开拆解
const hasHitSplit = computed(
  () => !!(funnel.value.other_industry_ai_hits || funnel.value.unmatched_ai_hits),
)

const diagClass = computed(() => {
  if (health.value.stage === 'empty') return 'panel--muted'
  // 路径配错是**静默失败**：看板一切正常，指标却全是 0。给最高级别的提示。
  if (health.value.bottleneck === 'path_mismatch') return 'panel--bad'
  return health.value.bottleneck === 'push_index' ? 'panel--bad' : 'panel--warn'
})
const diagIcon = computed(() => {
  if (health.value.stage === 'empty') return InfoFilled
  if (health.value.bottleneck === 'path_mismatch') return WarningFilled
  return health.value.bottleneck === 'push_index' ? CircleCloseFilled : WarningFilled
})

const statusType = (s) =>
  ({ not_crawled: 'danger', crawled_only: 'warning', cited: 'primary', top3: 'success' }[s] || 'info')
const kindType = (k) => ({ replicate: 'success', push_index: 'danger', improve: 'warning' }[k] || 'info')
const kindLabel = (k) => ({ replicate: '复制已验证模式', push_index: '推动收录', improve: '提升可引用性' }[k] || k)
const priorityType = (p) => ({ 高: 'danger', 中: 'warning', 低: 'info' }[p] || 'info')
const botType = (c) => ({ ai_bot: 'danger', search_bot: 'warning', other_bot: 'info' }[c] || 'info')
const botLabel = (c) =>
  ({ ai_bot: 'AI 抓取器', search_bot: '搜索引擎', other_bot: '其他爬虫', human: '人类', unknown: '未识别' }[c] || c)

// 转化率低于 50% 视为该环节明显漏水，标红提示
const convClass = (s) => (s.rate_of_prev < 0.5 ? 'funnel__conv--bad' : '')

const load = async () => {
  const industryId = store.currentIndustryId
  if (!industryId) return
  loading.value = true
  try {
    const res = await crawlerApi.loopOverview({ industry_id: industryId, days: days.value })
    const d = res.data || {}
    funnel.value = d.funnel || { counts: {}, stages: [] }
    health.value = d.health || {}
    attribution.value = d.attribution || []
    recycle.value = d.recycle || []
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

const openJourney = async (url) => {
  if (!url) return
  try {
    const res = await crawlerApi.journey({
      url, industry_id: store.currentIndustryId, days: 365,
    })
    journey.value = res.data
    drawer.value = true
  } catch (e) {
    /* 拦截器已提示 */
  }
}

const doImport = async () => {
  if (!logText.value.trim()) {
    ElMessage.warning('请先粘贴日志内容')
    return
  }
  importing.value = true
  try {
    const res = await crawlerApi.importLog({ text: logText.value, skip_human: true, dedupe: true })
    const d = res.data || {}
    ElMessage.success(
      `解析 ${d.parsed} 行，导入 ${d.imported} 条抓取记录，归因到内容 ${d.attributed} 条`
    )
    importDialog.value = false
    logText.value = ''
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    importing.value = false
  }
}

// copyText 已抽到 utils/clipboard.js（全站统一实现）

onMounted(load)
watch(() => store.currentIndustryId, load)
</script>

<style scoped>
.geo-loop-view { padding: 20px 24px 40px; }

.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 18px;
}
.hero__lead { max-width: 760px; }
.hero__tags { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.hero__eyebrow {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; font-weight: 600; color: var(--brand-600);
}
.hero__title { margin: 0 0 6px; font-size: 20px; font-weight: 700; color: var(--text-primary); }
.hero__desc { margin: 0; font-size: 13px; line-height: 1.7; color: var(--text-secondary); }
.hero__desc strong { color: var(--brand-600); }
.hero__warn { color: var(--accent-amber); font-weight: 600; }
.filters { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.warn-text { color: var(--accent-amber); font-weight: 600; }
.dim { color: var(--text-quaternary); }

.board { display: flex; flex-direction: column; gap: 16px; }
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 16px 18px 18px;
  box-shadow: var(--shadow-xs);
}
.panel__head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 14px; flex-wrap: wrap;
}
.panel__title {
  margin: 0; font-size: 15px; font-weight: 600; color: var(--text-primary);
  display: flex; align-items: center; gap: 8px;
}
.panel__note { font-size: 12px; color: var(--text-tertiary); }

/* ---------- 诊断条 ---------- */
.panel--diag { padding: 0; overflow: hidden; }
.panel--bad .diag { background: rgba(244, 63, 94, 0.07); border-left: 3px solid var(--accent-rose); }
.panel--warn .diag { background: rgba(245, 158, 11, 0.07); border-left: 3px solid var(--accent-amber); }
.panel--muted .diag { background: var(--slate-50); border-left: 3px solid var(--slate-300); }
.diag { display: flex; align-items: center; gap: 14px; padding: 16px 18px; }
.diag__icon { font-size: 26px; flex-shrink: 0; }
.panel--bad .diag__icon { color: var(--accent-rose); }
.panel--warn .diag__icon { color: var(--accent-amber); }
.panel--muted .diag__icon { color: var(--text-tertiary); }
.diag__body { flex: 1; min-width: 0; }
.diag__label { font-size: 14px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.diag__detail { font-size: 13px; line-height: 1.7; color: var(--text-secondary); }
.diag__next {
  display: flex; align-items: center; gap: 4px;
  margin-top: 6px; font-size: 12px; color: var(--brand-600); font-weight: 600;
}
.diag__rate {
  flex-shrink: 0; text-align: right; font-size: 22px; font-weight: 700;
  color: var(--text-primary); font-variant-numeric: tabular-nums;
}
.diag__rate-label { display: block; font-size: 11px; font-weight: 400; color: var(--text-tertiary); }
.diag__evidence { list-style: none; margin: 8px 0 0; padding: 0; }
.diag__evidence li {
  display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
  margin-top: 4px; font-size: 12px;
}
.diag__path {
  padding: 1px 6px; border-radius: 3px; font-size: 11px;
  font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
  border: 1px solid transparent;
}
.diag__path--hit {
  background: rgba(244, 63, 94, 0.1); color: var(--accent-rose);
  border-color: rgba(244, 63, 94, 0.28);
}
.diag__path--pub {
  background: rgba(16, 185, 129, 0.1); color: var(--accent-emerald);
  border-color: rgba(16, 185, 129, 0.28);
}
.diag__arrow { color: var(--text-tertiary); }
.diag__hits { color: var(--text-tertiary); font-variant-numeric: tabular-nums; }

/* ---------- 漏斗 ---------- */
.funnel { display: flex; flex-direction: column; }
.funnel__row { display: flex; align-items: center; gap: 12px; }
.funnel__label {
  width: 96px; flex-shrink: 0; display: flex; align-items: center; gap: 4px;
  font-size: 13px; font-weight: 600; color: var(--text-primary);
}
.funnel__help { cursor: help; color: var(--text-quaternary); font-size: 12px; }
.funnel__track {
  flex: 1; height: 22px; background: var(--slate-100);
  border-radius: var(--radius-sm); overflow: hidden;
}
.funnel__fill {
  height: 100%; background: linear-gradient(90deg, var(--brand-500), var(--brand-400));
  border-radius: var(--radius-sm); transition: width 0.4s ease; min-width: 2px;
}
.funnel__value {
  width: 84px; flex-shrink: 0; text-align: right;
  font-variant-numeric: tabular-nums;
}
.funnel__value strong { font-size: 16px; color: var(--text-primary); }
.funnel__pct { margin-left: 6px; font-size: 12px; color: var(--text-tertiary); }
.funnel__gap {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 0 4px 96px; font-size: 12px;
}
.funnel__arrow { color: var(--text-quaternary); }
.funnel__conv { color: var(--text-tertiary); }
.funnel__conv--bad { color: var(--accent-rose); font-weight: 600; }
.funnel__flag {
  padding: 1px 6px; border-radius: var(--radius-full);
  background: rgba(244, 63, 94, 0.1); color: var(--accent-rose);
  font-size: 11px; font-weight: 600;
}

/* ---------- 回流 ---------- */
.recycles { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 12px; }
.recycle {
  border: 1px solid var(--border-light); border-radius: var(--radius-md);
  padding: 12px 14px; background: var(--slate-50);
}
.recycle--replicate { border-left: 3px solid var(--accent-emerald); }
.recycle--push_index { border-left: 3px solid var(--accent-rose); }
.recycle--improve { border-left: 3px solid var(--accent-amber); }
.recycle__head { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.recycle__basis { font-size: 11px; color: var(--text-tertiary); margin-left: auto; }
.recycle__title { font-size: 13px; font-weight: 600; line-height: 1.6; color: var(--text-primary); margin-bottom: 4px; }
.recycle__reason { font-size: 12px; color: var(--text-tertiary); line-height: 1.6; }
.recycle__action {
  display: flex; align-items: flex-start; gap: 4px;
  margin-top: 8px; padding: 8px 10px;
  background: var(--bg-card); border-radius: var(--radius-sm);
  font-size: 12px; line-height: 1.6; color: var(--text-secondary);
}
.recycle__action .el-icon { margin-top: 3px; color: var(--brand-500); flex-shrink: 0; }
.recycle__foot { margin-top: 6px; display: flex; gap: 4px; }

/* ---------- 归因表 ---------- */
.table { width: 100%; }
.c-title { font-weight: 600; color: var(--text-primary); }
.c-url { font-size: 11px; color: var(--text-tertiary); word-break: break-all; }
.bots { font-size: 12px; color: var(--text-secondary); }
.rank--top { color: var(--accent-amber); font-weight: 700; }

/* ---------- 旅程 ---------- */
.journey__stats {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px;
}
.js {
  text-align: center; padding: 10px 6px;
  background: var(--slate-50); border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}
.js--good { border-color: rgba(16, 185, 129, 0.35); background: rgba(16, 185, 129, 0.06); }
.js__num { font-size: 20px; font-weight: 700; color: var(--text-primary); font-variant-numeric: tabular-nums; }
.js__label { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
.journey__alert { margin-bottom: 16px; }
.journey__section { margin-bottom: 20px; }
.journey__section h4 {
  margin: 0 0 8px; font-size: 13px; font-weight: 600; color: var(--text-primary);
}
.jlist { display: flex; flex-direction: column; }
.jitem {
  display: flex; gap: 10px; padding: 9px 0;
  border-bottom: 1px solid var(--border-light);
}
.jitem__rank {
  flex-shrink: 0; width: 20px; height: 20px; border-radius: var(--radius-sm);
  background: var(--slate-400); color: #fff; font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.jitem__rank--top { background: var(--accent-amber); }
.jitem__dot {
  flex-shrink: 0; width: 8px; height: 8px; border-radius: 50%; margin-top: 6px;
  background: var(--slate-300);
}
.dot--ai_bot { background: var(--accent-rose); }
.dot--search_bot { background: var(--accent-amber); }
.dot--other_bot { background: var(--slate-400); }
.jitem__body { flex: 1; min-width: 0; }
.jitem__kw {
  font-size: 13px; font-weight: 600; color: var(--text-primary);
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.jitem__meta {
  display: flex; gap: 10px; font-size: 11px; color: var(--text-tertiary); margin-top: 2px;
}
.jitem__meta .own { color: var(--accent-emerald); font-weight: 600; }
.jempty { font-size: 12px; color: var(--text-tertiary); padding: 12px 0; }

.dlg__hint { margin: 0 0 10px; font-size: 12px; line-height: 1.7; color: var(--text-secondary); }
</style>
