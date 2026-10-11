<template>
  <div class="geo-monitor-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button :icon="MagicStick" @click="seedDefaults" :loading="seeding">一键灌入默认模板</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建监测任务</el-button>
    </Teleport>

    <!-- 顶部：GEO 价值说明 + 看板指标 -->
    <section class="hero">
      <div class="hero__lead">
        <div class="hero__tags">
          <span class="hero__eyebrow"><el-icon><Monitor /></el-icon> GEO 作战 · 模块⑥ 闭环验证</span>
          <el-tag size="small" effect="plain" class="hero__industry"><el-icon><OfficeBuilding /></el-icon> 当前行业：{{ store.currentIndustryName }}</el-tag>
        </div>
        <h2 class="hero__title">AI 推荐监测：验证 AI 是否真的推荐我们</h2>
        <p class="hero__desc">闭环最后一环：对标豆包/文心一言/DeepSeek 等 AI 平台，确认目标客户提问时 AI 是否提及我们的品牌。系统生成各平台提问提示词 → 你复制去 AI 粘贴 → 把 AI 答复回传 → 本地解析 AI 认可度 3 指标（品牌提及率 / 引用长度 / 情感倾向）。</p>
      </div>
      <div class="hero__metrics">
        <div class="metric">
          <div class="metric__num">{{ stats.monitor_count || 0 }}</div>
          <div class="metric__label">监测任务</div>
        </div>
        <div class="metric">
          <div class="metric__num">{{ stats.reply_count || 0 }}</div>
          <div class="metric__label">AI 答复</div>
        </div>
        <div class="metric" :class="{ 'metric--warn': (stats.mention_rate || 0) < 50 }">
          <div class="metric__num">{{ stats.mention_rate || 0 }}<span class="metric__unit">%</span></div>
          <div class="metric__label">品牌提及率</div>
        </div>
        <div class="metric">
          <div class="metric__num">{{ stats.positive_rate || 0 }}<span class="metric__unit">%</span></div>
          <div class="metric__label">正面提及占比</div>
        </div>
        <div class="metric" :class="{ 'metric--warn': (stats.recommended_rate || 0) < 30 }">
          <div class="metric__num">{{ stats.recommended_rate || 0 }}<span class="metric__unit">%</span></div>
          <div class="metric__label">AI 推荐率</div>
        </div>
      </div>
    </section>

    <!-- 各平台提及率明细 -->
    <div class="platform-breakdown" v-if="stats.platforms && stats.platforms.length">
      <div class="pb-title">各 AI 平台提及率</div>
      <div class="pb-bars">
        <div v-for="p in stats.platforms" :key="p.platform" class="pb-item">
          <span class="pb-name">{{ p.platform }}</span>
          <div class="pb-track">
            <div class="pb-fill" :style="{ width: p.mention_rate + '%', background: p.mention_rate >= 50 ? '#10b981' : p.mention_rate > 0 ? '#f59e0b' : '#94a3b8' }"></div>
          </div>
          <span class="pb-val">{{ p.mentioned }}/{{ p.total }}</span>
        </div>
      </div>
    </div>

    <!-- 监测任务列表 -->
    <div class="monitor-list" v-loading="loading">
      <div v-for="m in list" :key="m.id" class="monitor-card">
        <div class="mc-head">
          <div class="mc-title-row">
            <span class="mc-name">{{ m.name || m.target_query.slice(0, 30) }}</span>
            <div class="mc-stats">
              <el-tag size="small" :type="m.mention_rate >= 50 ? 'success' : m.mention_rate > 0 ? 'warning' : 'info'" effect="plain">
                提及率 {{ m.mention_rate }}%
              </el-tag>
              <el-tag size="small" type="info" effect="plain">{{ m.reply_count }} 个平台已测</el-tag>
            </div>
          </div>
          <div class="mc-query">
            <el-icon><ChatDotRound /></el-icon>
            <span>{{ m.target_query }}</span>
          </div>
          <div class="mc-brand">
            <span class="mc-brand-label">监测品牌：</span>
            <el-tag size="small" type="danger" effect="dark">{{ m.brand_name }}</el-tag>
            <span class="mc-platforms" v-if="m.platforms">
              <el-tag v-for="p in parsePlatforms(m.platforms)" :key="p" size="small" effect="plain" class="mc-platform-tag">{{ p }}</el-tag>
            </span>
          </div>
        </div>
        <div class="mc-actions">
          <el-button type="primary" size="small" :icon="Search" @click="openDetail(m)">开始监测</el-button>
          <el-button text size="small" :icon="Edit" @click="openEdit(m)">编辑</el-button>
          <el-button text size="small" type="danger" :icon="Delete" @click="remove(m)">删除</el-button>
        </div>
      </div>
      <EmptyState v-if="!loading && list.length === 0" title="暂无监测任务" description="点击右上角「新建监测任务」，设定目标问题与品牌名，开始验证 AI 是否推荐你" icon="Monitor" />
    </div>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑监测任务' : '新建监测任务'" width="600px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="任务名称">
          <el-input v-model="form.name" placeholder="可选，如「敏感肌修护 - 品牌提及监测」" />
        </el-form-item>
        <el-form-item label="目标问题" required>
          <el-input v-model="form.target_query" type="textarea" :rows="3" placeholder="向 AI 提的问题，如「敏感肌修护面霜推荐哪个品牌比较好？」" />
        </el-form-item>
        <el-form-item label="品牌名" required>
          <el-input v-model="form.brand_name" placeholder="要监测的品牌名，如「莱宝」" />
        </el-form-item>
        <el-form-item label="对标平台">
          <el-select v-model="selectedPlatforms" multiple placeholder="选择要对标的 AI 平台" style="width: 100%;">
            <el-option v-for="p in aiPlatforms" :key="p.name" :label="p.name" :value="p.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 监测详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detailTitle" size="720px" direction="rtl">
      <div class="detail-content" v-if="currentMonitor">
        <!-- 步骤引导 -->
        <div class="steps-guide">
          <div class="step">
            <div class="step__num">1</div>
            <div class="step__text"><b>复制提问提示词</b> → 去对应 AI 平台粘贴提问</div>
          </div>
          <div class="step">
            <div class="step__num">2</div>
            <div class="step__text"><b>把 AI 的回复</b>粘贴回下方的输入框</div>
          </div>
          <div class="step">
            <div class="step__num">3</div>
            <div class="step__text">系统<b>本地解析</b>品牌提及率 / 引用长度 / 情感倾向</div>
          </div>
        </div>

        <!-- 品牌信息 -->
        <div class="brand-bar">
          <span>监测品牌：</span>
          <el-tag type="danger" effect="dark">{{ currentMonitor.brand_name }}</el-tag>
        </div>

        <!-- 各平台回复列表 -->
        <div class="reply-section" v-loading="replyLoading">
          <div v-for="p in detailPlatforms" :key="p" class="reply-block">
            <div class="rb-head">
              <span class="rb-platform">{{ p }}</span>
              <el-button text size="small" :icon="CopyDocument" @click="copyPrompt(p)">复制提问提示词</el-button>
            </div>

            <!-- 已有回复 -->
            <div v-if="repliesMap[p]" class="rb-result">
              <div class="rb-metrics">
                <div class="rb-metric" :class="{ 'rb-metric--hit': repliesMap[p].mentioned }">
                  <span class="rb-metric-label">品牌提及</span>
                  <span class="rb-metric-val">{{ repliesMap[p].mentioned ? `是 (${repliesMap[p].mention_count}次)` : '否' }}</span>
                </div>
                <div class="rb-metric">
                  <span class="rb-metric-label">引用长度</span>
                  <span class="rb-metric-val">{{ repliesMap[p].citation_length }} 字</span>
                </div>
                <div class="rb-metric">
                  <span class="rb-metric-label">情感倾向</span>
                  <span class="rb-metric-val" :class="'sentiment-' + repliesMap[p].sentiment">{{ sentimentLabel(repliesMap[p].sentiment) }}</span>
                </div>
                <div class="rb-metric" :class="{ 'rb-metric--hit': repliesMap[p].recommended }">
                  <span class="rb-metric-label">AI 推荐</span>
                  <span class="rb-metric-val">{{ repliesMap[p].recommended ? '是' : '否' }}</span>
                </div>
                <div class="rb-metric">
                  <span class="rb-metric-label">有价值正面</span>
                  <span class="rb-metric-val" :class="{ 'sentiment-positive': repliesMap[p].valuable_positive }">{{ repliesMap[p].valuable_positive ? '是' : '否' }}</span>
                </div>
              </div>
              <div class="rb-snippet" v-if="repliesMap[p].snippet">
                <div class="rb-snippet-label">提及片段：</div>
                <div class="rb-snippet-text">{{ repliesMap[p].snippet }}</div>
              </div>
              <div class="rb-reply-preview" v-if="repliesMap[p].ai_reply">
                <details>
                  <summary>查看 AI 回复原文</summary>
                  <div class="rb-reply-full">{{ repliesMap[p].ai_reply }}</div>
                </details>
              </div>
              <div class="rb-actions">
                <el-button text size="small" :icon="RefreshLeft" @click="reopenInput(p)">重新粘贴</el-button>
                <el-button text size="small" type="danger" :icon="Delete" @click="deleteReply(repliesMap[p])">删除</el-button>
              </div>
            </div>

            <!-- 输入区 -->
            <div v-else class="rb-input-area">
              <el-input v-model="replyInputs[p]" type="textarea" :rows="6" :placeholder="`把 ${p} 的回复粘贴到这里...`" />
              <div class="rb-input-foot">
                <el-button type="primary" size="small" @click="submitReply(p)" :loading="replySaving[p]">回传并解析</el-button>
                <el-button text size="small" @click="copyPrompt(p)">先复制提问提示词</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete, Search, CopyDocument, Monitor, RefreshLeft, OfficeBuilding, ChatDotRound, MagicStick } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { geoMonitorApi } from '../api'
import { writeClipboard } from '../utils/clipboard'
import EmptyState from '../components/EmptyState.vue'

const pageActionsTarget = inject('pageActionsTarget', null)
const store = useAppStore()

const loading = ref(false)
const saving = ref(false)
const seeding = ref(false)
const list = ref([])
const stats = ref({})
const aiPlatforms = ref([])

// 弹窗
const dialogVisible = ref(false)
const editing = ref(false)
const form = ref({ name: '', target_query: '', brand_name: '', note: '', industry_id: 0 })
const selectedPlatforms = ref([])

// 详情抽屉
const detailVisible = ref(false)
const currentMonitor = ref(null)
const replies = ref([])
const replyLoading = ref(false)
const replyInputs = ref({})
const replySaving = ref({})
const activeInputPlatforms = ref(new Set())

const detailTitle = computed(() => {
  if (!currentMonitor.value) return '监测详情'
  return currentMonitor.value.name || (currentMonitor.value.target_query || '').slice(0, 30)
})

const detailPlatforms = computed(() => {
  if (!currentMonitor.value) return []
  try {
    const ps = JSON.parse(currentMonitor.value.platforms || '[]')
    return ps.length ? ps : aiPlatforms.value.map(p => p.name)
  } catch {
    return aiPlatforms.value.map(p => p.name)
  }
})

const repliesMap = computed(() => {
  const map = {}
  for (const r of replies.value) {
    map[r.platform] = r
  }
  return map
})

function parsePlatforms(platformsStr) {
  try {
    return JSON.parse(platformsStr || '[]')
  } catch {
    return []
  }
}

function sentimentLabel(s) {
  const map = { positive: '正面', neutral: '中性', negative: '负面' }
  return map[s] || s
}

async function loadList() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const res = await geoMonitorApi.list(store.currentIndustryId)
    list.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  if (!store.currentIndustryId) return
  try {
    const res = await geoMonitorApi.stats(store.currentIndustryId)
    stats.value = res.data || {}
  } catch {}
}

async function loadPlatforms() {
  try {
    const res = await geoMonitorApi.platforms()
    aiPlatforms.value = res.data || []
  } catch {}
}

async function seedDefaults() {
  seeding.value = true
  try {
    const res = await geoMonitorApi.seedDefaults(store.currentIndustryId)
    ElMessage.success(res.msg || '已灌入')
    await loadList()
    await loadStats()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '灌入失败')
  } finally {
    seeding.value = false
  }
}

function openCreate() {
  editing.value = false
  form.value = { name: '', target_query: '', brand_name: '', note: '', industry_id: store.currentIndustryId }
  selectedPlatforms.value = aiPlatforms.value.slice(0, 4).map(p => p.name)
  dialogVisible.value = true
}

function openEdit(m) {
  editing.value = true
  form.value = { ...m, industry_id: store.currentIndustryId }
  selectedPlatforms.value = parsePlatforms(m.platforms)
  dialogVisible.value = true
}

async function save() {
  if (!form.value.target_query?.trim()) { ElMessage.warning('请输入目标问题'); return }
  if (!form.value.brand_name?.trim()) { ElMessage.warning('请输入品牌名'); return }
  saving.value = true
  try {
    const payload = {
      ...form.value,
      platforms: JSON.stringify(selectedPlatforms.value),
      industry_id: store.currentIndustryId,
    }
    if (editing.value) {
      await geoMonitorApi.update(form.value.id, payload)
    } else {
      await geoMonitorApi.create(payload)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await loadList()
    await loadStats()
  } finally {
    saving.value = false
  }
}

async function remove(m) {
  await ElMessageBox.confirm('确定删除该监测任务及其所有回复吗？', '提示', { type: 'warning' })
  await geoMonitorApi.delete(m.id)
  ElMessage.success('已删除')
  await loadList()
  await loadStats()
}

// 详情抽屉
async function openDetail(m) {
  currentMonitor.value = m
  detailVisible.value = true
  replies.value = []
  replyInputs.value = {}
  activeInputPlatforms.value = new Set()
  await loadReplies(m.id)
}

async function loadReplies(monitorId) {
  replyLoading.value = true
  try {
    const res = await geoMonitorApi.listReplies(monitorId)
    replies.value = res.data || []
  } finally {
    replyLoading.value = false
  }
}

async function copyPrompt(platform) {
  try {
    const res = await geoMonitorApi.getPrompt(currentMonitor.value.id, platform)
    const prompt = res.data?.prompt || ''
    // 用底层 writeClipboard 保留本处自定义提示语，同时获得非安全上下文降级
    if (await writeClipboard(prompt)) {
      ElMessage.success(`已复制 ${platform} 提问提示词，去粘贴提问吧`)
    } else {
      ElMessage.error('复制失败')
    }
  } catch {
    ElMessage.error('复制失败')
  }
}

async function submitReply(platform) {
  const text = replyInputs.value[platform]?.trim()
  if (!text) { ElMessage.warning('请先粘贴 AI 的回复内容'); return }
  replySaving.value = { ...replySaving.value, [platform]: true }
  try {
    const res = await geoMonitorApi.importReply(currentMonitor.value.id, { platform, ai_reply: text })
    ElMessage.success(res.msg || '已解析')
    replyInputs.value = { ...replyInputs.value, [platform]: '' }
    activeInputPlatforms.value.delete(platform)
    await loadReplies(currentMonitor.value.id)
    await loadList()
    await loadStats()
  } catch (e) {
    ElMessage.error('解析失败：' + (e?.response?.data?.detail || '请重试'))
  } finally {
    replySaving.value = { ...replySaving.value, [platform]: false }
  }
}

function reopenInput(platform) {
  activeInputPlatforms.value.add(platform)
  // 临时从 replies 中移除该平台的显示，让输入框出现
  replies.value = replies.value.filter(r => r.platform !== platform)
}

async function deleteReply(reply) {
  await ElMessageBox.confirm(`确定删除 ${reply.platform} 的回复吗？`, '提示', { type: 'warning' })
  await geoMonitorApi.deleteReply(reply.id)
  ElMessage.success('已删除')
  await loadReplies(currentMonitor.value.id)
  await loadList()
  await loadStats()
}

watch(() => store.currentIndustryId, async () => { await loadList(); await loadStats() })
onMounted(async () => {
  await loadPlatforms()
  await loadList()
  await loadStats()
})
</script>

<style scoped>
.geo-monitor-view { display: flex; flex-direction: column; gap: 16px; }

/* hero */
.hero {
  display: flex; gap: 24px; align-items: stretch;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 20px 24px;
}
.hero__lead { flex: 1; min-width: 0; }
.hero__tags { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.hero__eyebrow {
  font-size: 12px; font-weight: 600; color: #4f46e5;
  display: flex; align-items: center; gap: 4px;
}
.hero__industry { font-size: 12px; }
.hero__title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin: 0 0 6px; }
.hero__desc { font-size: 13px; color: var(--text-secondary); line-height: 1.7; margin: 0; }
.hero__metrics { display: flex; gap: 24px; flex-shrink: 0; }
.metric { text-align: center; min-width: 70px; }
.metric__num { font-size: 28px; font-weight: 800; color: var(--text-primary); line-height: 1.2; }
.metric__unit { font-size: 14px; font-weight: 600; color: var(--text-tertiary); }
.metric__label { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }
.metric--warn .metric__num { color: #f59e0b; }

/* platform breakdown */
.platform-breakdown {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
}
.pb-title { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; }
.pb-bars { display: flex; flex-direction: column; gap: 8px; }
.pb-item { display: flex; align-items: center; gap: 12px; }
.pb-name { font-size: 13px; color: var(--text-secondary); width: 80px; flex-shrink: 0; }
.pb-track { flex: 1; height: 8px; background: var(--bg-hover); border-radius: 4px; overflow: hidden; }
.pb-fill { height: 100%; border-radius: 4px; transition: width .3s ease; }
.pb-val { font-size: 12px; color: var(--text-tertiary); width: 50px; text-align: right; flex-shrink: 0; }

/* monitor list */
.monitor-list { display: flex; flex-direction: column; gap: 10px; min-height: 200px; }
.monitor-card {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  border-left: 3px solid #4f46e5;
}
.monitor-card:hover { box-shadow: var(--shadow-sm); }
.mc-head { flex: 1; min-width: 0; }
.mc-title-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 6px; }
.mc-name { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.mc-stats { display: flex; gap: 6px; flex-shrink: 0; }
.mc-query {
  display: flex; align-items: flex-start; gap: 6px;
  font-size: 13px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 6px;
}
.mc-query .el-icon { margin-top: 2px; flex-shrink: 0; color: var(--text-tertiary); }
.mc-brand { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.mc-brand-label { font-size: 12px; color: var(--text-tertiary); }
.mc-platforms { display: flex; gap: 4px; flex-wrap: wrap; margin-left: 4px; }
.mc-platform-tag { font-size: 11px; }
.mc-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }

/* detail drawer */
.detail-content { display: flex; flex-direction: column; gap: 16px; }
.steps-guide {
  background: color-mix(in srgb, #4f46e5 6%, var(--bg-card));
  border: 1px solid color-mix(in srgb, #4f46e5 20%, var(--border-light));
  border-radius: var(--radius-md);
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 10px;
}
.step { display: flex; align-items: center; gap: 10px; }
.step__num {
  width: 24px; height: 24px; border-radius: 50%;
  background: #4f46e5; color: #fff;
  font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.step__text { font-size: 13px; color: var(--text-secondary); }
.step__text b { color: var(--text-primary); }

.brand-bar {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--text-secondary);
}

/* reply blocks */
.reply-section { display: flex; flex-direction: column; gap: 14px; }
.reply-block {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 14px 16px;
}
.rb-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.rb-platform { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.rb-result { display: flex; flex-direction: column; gap: 10px; }
.rb-metrics { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.rb-metric {
  display: flex; flex-direction: column; gap: 2px;
  padding: 8px 10px;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
}
.rb-metric--hit { background: color-mix(in srgb, #10b981 12%, transparent); }
.rb-metric-label { font-size: 11px; color: var(--text-tertiary); }
.rb-metric-val { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.rb-metric--hit .rb-metric-val { color: #10b981; }
.sentiment-positive { color: #10b981 !important; }
.sentiment-negative { color: #ef4444 !important; }
.sentiment-neutral { color: var(--text-tertiary) !important; }
.rb-snippet {
  background: color-mix(in srgb, #f59e0b 6%, var(--bg-hover));
  border-left: 3px solid #f59e0b;
  border-radius: var(--radius-sm);
  padding: 8px 12px;
}
.rb-snippet-label { font-size: 12px; font-weight: 600; color: #f59e0b; margin-bottom: 4px; }
.rb-snippet-text { font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; }
.rb-reply-preview { font-size: 12px; }
.rb-reply-preview summary { cursor: pointer; color: var(--text-tertiary); }
.rb-reply-full {
  font-size: 12px; color: var(--text-secondary); line-height: 1.6;
  max-height: 200px; overflow-y: auto;
  padding: 8px; background: var(--bg-hover); border-radius: var(--radius-sm);
  margin-top: 6px;
}
.rb-actions { display: flex; gap: 6px; }
.rb-input-area { display: flex; flex-direction: column; gap: 8px; }
.rb-input-foot { display: flex; align-items: center; gap: 8px; }

@media (max-width: 768px) {
  .hero { flex-direction: column; }
  .hero__metrics { justify-content: space-around; }
  .rb-metrics { grid-template-columns: repeat(2, 1fr); }
}
</style>
