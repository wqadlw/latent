<template>
  <div class="auto-studio">
    <!-- ============ 顶部：标题 + 模式切换 + 批量操作 ============ -->
    <div class="as-header card">
      <div class="as-header__main">
        <div class="as-header__title">
          <el-icon class="as-header__icon"><SetUp /></el-icon>
          <div>
            <h1>自动化指挥中心</h1>
            <p>自动化全流程可视化 · 每步提示词与专家角色可编辑 · 改动实时生效于后续运行</p>
          </div>
        </div>
      </div>
      <div class="as-header__ops">
        <span class="as-mode-label">预览背景内容（发布模式）</span>
        <el-radio-group v-model="previewMode" size="small" @change="loadContext">
          <el-radio-button v-for="m in modes" :key="m.value" :label="m.value">{{ m.label }}</el-radio-button>
        </el-radio-group>
        <el-button
          type="primary" size="small" :icon="Check" :disabled="!dirtyKeys.length"
          :loading="savingAll" @click="saveAll"
        >保存全部改动（{{ dirtyKeys.length }}）</el-button>
      </div>
    </div>

    <!-- ============ A. 工作流可视化（10 步 + 专家角色） ============ -->
    <div class="card as-section">
      <div class="as-section__head">
        <h2>① 自动化工作流可视化</h2>
        <div class="as-legend">
          <span class="as-legend__item"><i class="dot agent-planner"></i>主编（总协调）</span>
          <span class="as-legend__item"><i class="dot agent-writer"></i>写手（落地）</span>
          <span class="as-legend__item"><i class="dot agent-system"></i>系统 / 人工</span>
          <span class="as-legend__item"><i class="dot agent-dual"></i>双角色协同</span>
        </div>
      </div>
      <div class="as-pipe">
        <div v-for="(s, i) in steps" :key="s.step_key" class="as-pipe__node">
          <div class="as-pipe__top">
            <span class="as-pipe__no">{{ s.step_no }}</span>
            <span class="as-pipe__agent" :class="agentMeta[s.agent]?.cls">{{ agentMeta[s.agent]?.label }}</span>
          </div>
          <div class="as-pipe__title">{{ s.title }}</div>
          <el-tooltip v-if="agentMeta[s.agent]?.desc" :content="agentMeta[s.agent].desc" placement="top">
            <div class="as-pipe__hint">{{ agentMeta[s.agent].desc }}</div>
          </el-tooltip>
          <span v-if="i < steps.length - 1" class="as-pipe__arrow">→</span>
        </div>
      </div>
      <el-alert
        class="as-pipe__note" type="info" :closable="false" show-icon
        title="双智能体协同"
        description="主编（规划/评审/整改指令，thinking 推理）与写手（初稿/去AI味/GEO终稿/改写，非推理）分工；合规官 / GEO 优化师 / 数据核查员由系统自检 + 主编评审共同把关。下方每个流程对应的提示词均可单独编辑。"
      />
    </div>

    <!-- ============ B. 背景内容预览（按模式解析注入） ============ -->
    <div class="card as-section">
      <div class="as-section__head">
        <h2>② 背景内容预览（会注入到提示词的上下文）</h2>
        <span class="as-mode-tag" :class="modeTagClass(previewMode)">{{ modeLabel(previewMode) }}</span>
      </div>
      <div class="as-ctx">
        <div class="as-ctx__block">
          <div class="as-ctx__title"><i class="dot agent-geo"></i>品牌策略（{brand_policy}）</div>
          <pre class="as-ctx__pre">{{ context.brand_policy || '—' }}</pre>
        </div>
        <div class="as-ctx__block">
          <div class="as-ctx__title"><i class="dot agent-fact"></i>模式目标（{mode_goal}）</div>
          <pre class="as-ctx__pre">{{ context.mode_goal || '—' }}</pre>
        </div>
        <div class="as-ctx__block as-ctx__block--wide">
          <div class="as-ctx__title"><i class="dot agent-planner"></i>专家团队配置（{expert_team}）</div>
          <pre class="as-ctx__pre">{{ context.expert_team || '—' }}</pre>
        </div>
        <div class="as-ctx__block as-ctx__block--wide" v-if="context.official_site_url">
          <div class="as-ctx__title"><i class="dot agent-writer"></i>官网地址（{official_site_url}）</div>
          <pre class="as-ctx__pre">{{ context.official_site_url }}</pre>
        </div>
      </div>
      <div class="as-ctx__hint">
        上文四项即运行时会注入提示词占位符的实际内容。其中「专家团队配置」本身也是可编辑提示词（见下方列表），其它三项由系统按发布模式自动生成。
      </div>
    </div>

    <!-- ============ C. 提示词清单（可编辑 / 可复制 / 可重置） ============ -->
    <div class="card as-section">
      <div class="as-section__head">
        <h2>③ 自动化提示词清单（每个流程用了什么提示词）</h2>
        <el-tag type="info" effect="plain" size="small">{{ prompts.length }} 条 · 改动后点「保存」即生效</el-tag>
      </div>

      <!-- 分类切换 -->
      <div class="as-tabs">
        <button
          v-for="(c, key) in catMeta" :key="key"
          class="as-tab" :class="{ 'is-active': activeCat === key }"
          @click="activeCat = key"
        >{{ c.label }}<span class="as-tab__count">{{ key === 'all' ? prompts.length : catCounts[key] || 0 }}</span></button>
      </div>

      <!-- 提示词卡网格 -->
      <div class="as-grid">
        <div
          v-for="p in filteredPrompts" :key="p.key"
          class="as-prompt" :class="{ 'is-dirty': isDirty(p), 'is-mdx': p.category === 'mdx' }"
        >
          <div class="as-prompt__head">
            <div class="as-prompt__titles">
              <span class="as-prompt__name">{{ p.name }}</span>
              <span class="as-prompt__role" :class="roleClass(p.expert_role)">{{ p.expert_role }}</span>
              <span class="as-prompt__cat">{{ catMeta[p.category]?.label || p.category }}</span>
              <span v-if="p.step_no" class="as-prompt__step">用于步骤 {{ p.step_no }}</span>
            </div>
            <div class="as-prompt__status">
              <el-tag v-if="isDirty(p)" size="small" type="warning" effect="plain">已修改</el-tag>
              <el-tag v-else-if="isChangedFromDefault(p)" size="small" type="success" effect="plain">自定义</el-tag>
            </div>
          </div>

          <!-- 编辑 / 预览切换 -->
          <div class="as-prompt__toolbar">
            <el-radio-group v-model="editState[p.key].mode" size="small">
              <el-radio-button label="edit">编辑原始模板</el-radio-button>
              <el-radio-button label="preview">预览（注入后）</el-radio-button>
            </el-radio-group>
          </div>

          <el-input
            v-if="editState[p.key].mode === 'edit'"
            v-model="editState[p.key].draft"
            type="textarea"
            class="as-prompt__area"
            :rows="10"
            resize="vertical"
            @input="onEdit(p)"
          />
          <pre v-else class="as-prompt__preview">{{ previewContent(p) }}</pre>

          <div class="as-prompt__foot">
            <div class="as-prompt__foot-left">
              <el-button size="small" type="primary" :loading="editState[p.key].saving" :disabled="!isDirty(p)" @click="saveOne(p)">保存</el-button>
              <el-button size="small" :icon="RefreshLeft" :disabled="!isDirty(p)" @click="discard(p)">撤销</el-button>
              <el-button size="small" :icon="Refresh" @click="resetOne(p)">重置默认</el-button>
            </div>
            <el-button size="small" :icon="DocumentCopy" @click="copyText(editState[p.key].draft, p.name)">复制</el-button>
          </div>
        </div>
      </div>

      <el-empty v-if="!filteredPrompts.length" description="该分类下暂无提示词" />
    </div>

    <!-- ============ D. 三 API 智能调度（按角色分流 + 负载均衡 + 故障切换） ============ -->
    <div class="card as-section">
      <div class="as-section__head">
        <h2>④ 三 API 智能调度（按任务类型分流 · 负载均衡 · 故障自动切换）</h2>
        <el-button size="small" :icon="Refresh" :loading="schedLoading" @click="loadScheduler">刷新</el-button>
      </div>
      <div v-if="sched" class="sched">
        <el-alert class="sched__note" :type="sched.all_mock ? 'warning' : 'success'" :closable="false" show-icon
          :title="sched.all_mock ? '当前全部回退「模拟演示」模式（未配置真实 API）' : '已接入真实 DeepSeek API'"
          :description="sched.all_mock
            ? '在「设置 → LLM 配置」为 选题调研(research) / 正文撰写(writing) / 审核优化(review) 三个角色各添加至少一个启用配置（填 api_key）即可启用真实调度、负载均衡与失败自动切换。'
            : '三角色均已配置真实 API：运行时会按角色轮询分流、同角色多配置负载均衡，单个配置鉴权/限流/超时失败时自动切换到同角色其他配置，并记录每次调用耗时(ms)。'" />
        <div class="sched__roles">
          <div v-for="role in sched.roles" :key="role.role" class="sched-role">
            <div class="sched-role__head">
              <span class="sched-role__name" :class="'rr-' + role.role">{{ roleLabel(role.role) }}</span>
              <span class="sched-role__desc">{{ role.desc }}</span>
              <el-tag size="small" type="info">配置池 {{ role.pool_size }}</el-tag>
            </div>
            <div v-if="!role.configs.length" class="sched-role__empty">无专门配置（将用 general 兜底）</div>
            <div v-for="c in role.configs" :key="c.config_id" class="sched-cfg">
              <span class="sched-cfg__name">{{ c.name }}</span>
              <span class="sched-cfg__provider">{{ c.provider }}</span>
              <span class="sched-cfg__model">{{ c.model }}</span>
              <span class="sched-cfg__lat" :class="c.last_latency_ms == null ? 'lat-none' : 'lat-ok'">
                {{ c.last_latency_ms != null ? c.last_latency_ms + ' ms' : '尚无调用' }}
              </span>
              <span class="sched-cfg__fail" :class="c.fail_count ? 'fail-bad' : 'fail-ok'">
                {{ c.fail_count ? c.fail_count + ' 次失败' : '健康' }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ E. 各平台合规发布策略（格式 / 禁区 / 发布模式 / AI 抓取优化） ============ -->
    <div class="card as-section">
      <div class="as-section__head">
        <h2>⑤ 各平台合规发布策略（格式要求 / 禁止标准 / 发布模式 / AI 搜索抓取优化）</h2>
        <el-tag type="info" effect="plain" size="small">{{ strategies.length }} 个平台</el-tag>
      </div>
      <div class="ps-grid">
        <div v-for="s in strategies" :key="s.id" class="ps-card">
          <div class="ps-card__head">
            <span class="ps-card__name">{{ s.platform_name }}</span>
            <span class="ps-mode" :class="modeTagClass(s.publish_mode)">{{ modeLabel(s.publish_mode) }}</span>
            <el-button size="small" text :icon="Edit" @click="openStrategy(s)">编辑</el-button>
          </div>
          <div class="ps-card__body">
            <div class="ps-line"><span class="ps-k">标题</span><span class="ps-v">{{ s.title_min_len }}–{{ s.title_max_len }} 字</span></div>
            <div class="ps-line"><span class="ps-k">字数</span><span class="ps-v">{{ s.min_words }}–{{ s.max_words }} 字</span></div>
            <div class="ps-line"><span class="ps-k">结构</span><span class="ps-v">{{ s.structure_rules }}</span></div>
            <div class="ps-line"><span class="ps-k">段落</span><span class="ps-v">{{ s.paragraph_rules }}</span></div>
            <div class="ps-line"><span class="ps-k">违禁</span><span class="ps-v">{{ s.banned_words_rule }}</span></div>
            <div class="ps-line"><span class="ps-k">软文</span><span class="ps-v">{{ s.soft_ad_rule }}</span></div>
            <div class="ps-line"><span class="ps-k">发布</span><span class="ps-v">{{ pubModeTypeLabel(s.publish_mode_type) }}</span></div>
            <div class="ps-line"><span class="ps-k">GEO</span><span class="ps-v">关键词密度 {{ s.geo_keyword_density }} · 结构化摘要 {{ s.geo_structured_summary ? '是' : '否' }} · 标题信息量 {{ s.geo_title_info ? '是' : '否' }}</span></div>
          </div>
        </div>
      </div>

      <!-- 编辑对话框 -->
      <el-dialog v-model="strategyDlg" title="编辑平台合规发布策略" width="760px" top="5vh">
        <el-form label-width="104px" v-if="editing">
          <div class="ps-edit-row">
            <el-form-item label="标题长度">
              <el-input-number v-model="editing.title_min_len" :min="1" :max="100" size="small" /> –
              <el-input-number v-model="editing.title_max_len" :min="1" :max="100" size="small" />
            </el-form-item>
            <el-form-item label="字数范围">
              <el-input-number v-model="editing.min_words" :min="100" :max="8000" size="small" /> –
              <el-input-number v-model="editing.max_words" :min="100" :max="8000" size="small" />
            </el-form-item>
          </div>
          <el-form-item label="发布模式">
            <el-select v-model="editing.publish_mode_type" size="small" style="width:200px">
              <el-option label="直接发布" value="direct" />
              <el-option label="存草稿" value="draft" />
              <el-option label="定时发布" value="scheduled" />
            </el-select>
          </el-form-item>
          <el-form-item label="结构规范"><el-input v-model="editing.structure_rules" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="段落规范"><el-input v-model="editing.paragraph_rules" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="违禁词规则"><el-input v-model="editing.banned_words_rule" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="软文检测"><el-input v-model="editing.soft_ad_rule" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="GEO 关键词密度"><el-input v-model="editing.geo_keyword_density" style="width:160px" /></el-form-item>
          <el-form-item label="结构化摘要"><el-switch v-model="editing.geo_structured_summary" :active-value="1" :inactive-value="0" /></el-form-item>
          <el-form-item label="标题信息量"><el-switch v-model="editing.geo_title_info" :active-value="1" :inactive-value="0" /></el-form-item>
          <el-form-item label="GEO 备注"><el-input v-model="editing.geo_notes" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="editing.notes" type="textarea" :rows="2" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="strategyDlg = false">取消</el-button>
          <el-button type="primary" :loading="savingStrategy" @click="saveStrategy">保存</el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { SetUp, Check, Refresh, RefreshLeft, DocumentCopy, Edit } from '@element-plus/icons-vue'
import { automationPromptApi } from '../api'

// ============ 元数据 ============
const agentMeta = {
  planner: { label: '📋 主编', cls: 'agent-planner', desc: '总协调：定方向、定大纲、终审把关、下达整改指令' },
  writer: { label: '✍️ 写手', cls: 'agent-writer', desc: '落地：初稿 / 去AI味 / GEO终稿 / 按指令改写' },
  system: { label: '⚙️ 系统', cls: 'agent-system', desc: '连接引擎 / 人工确认 / 发布平台' },
  dual: { label: '📋✍️ 双角色', cls: 'agent-dual', desc: '主编指令 + 写手执行，闭环整改' },
}

const catMeta = {
  all: { label: '全部' },
  team: { label: '专家团队' },
  system: { label: '创作总纲' },
  stage: { label: '写手逐阶段' },
  planner: { label: '主编智能体' },
  writer: { label: '写手改写' },
  revise: { label: '整改指令' },
  mdx: { label: '官网 MDX' },
}

const roleClass = (r) => {
  if (r === '主编') return 'agent-planner'
  if (r === '写手') return 'agent-writer'
  return 'agent-system'
}

// ============ 状态 ============
const prompts = ref([])
const steps = ref([])
const modes = ref([])
const context = reactive({ brand_policy: '', mode_goal: '', expert_team: '', official_site_url: '' })
const previewMode = ref('geo')
const activeCat = ref('all')
const savingAll = ref(false)
const editState = reactive({})  // key -> { draft, mode:'edit', saving:false }

// 三 API 调度状态
const sched = ref(null)
const schedLoading = ref(false)
// 各平台合规发布策略
const strategies = ref([])
const strategyDlg = ref(false)
const editing = ref(null)
const savingStrategy = ref(false)

// 每个提示词的编辑状态初始化
function ensureState(p) {
  if (!editState[p.key]) {
    editState[p.key] = { draft: p.content || '', mode: 'edit', saving: false }
  } else {
    // 同步 draft 到最新 content（重置/保存后）
    editState[p.key].draft = p.content || ''
  }
}

// ============ 计算属性 ============
const filteredPrompts = computed(() => {
  const list = activeCat.value === 'all' ? prompts.value : prompts.value.filter(p => p.category === activeCat.value)
  return list
})
const catCounts = computed(() => {
  const c = {}
  for (const p of prompts.value) c[p.category] = (c[p.category] || 0) + 1
  return c
})
const dirtyKeys = computed(() =>
  prompts.value.filter(p => isDirty(p)).map(p => p.key)
)

function isDirty(p) {
  const st = editState[p.key]
  if (!st) return false
  return (st.draft || '') !== (p.content || '')
}
function isChangedFromDefault(p) {
  return (p.content || '') !== (p.default_content || '')
}

// 预览注入后：把占位符替换为当前模式解析出的实际内容
function previewContent(p) {
  let t = editState[p.key]?.draft || p.content || ''
  const map = {
    '{brand_policy}': context.brand_policy,
    '{mode_goal}': context.mode_goal,
    '{expert_team}': context.expert_team,
    '{official_site_url}': context.official_site_url,
  }
  for (const [k, v] of Object.entries(map)) {
    if (v) t = t.split(k).join(v)
  }
  return t
}

function modeTagClass(m) {
  return { geo: 'm-geo', platform: 'm-platform', green: 'm-green', official: 'm-official' }[m] || 'm-geo'
}
function modeLabel(m) {
  return (modes.value.find(x => x.value === m) || {}).label || m
}

// ============ 加载 ============
async function loadAll() {
  const [pr, st] = await Promise.all([
    automationPromptApi.list(),
    automationPromptApi.steps(),
  ])
  prompts.value = (pr.data || []).map(p => ({ ...p }))
  steps.value = st.data || []
  prompts.value.forEach(ensureState)
  await loadContext()
  // 调度状态 + 合规策略（无强依赖，并行加载）
  await Promise.all([loadScheduler(), loadStrategies()])
}
async function loadContext() {
  try {
    const res = await automationPromptApi.context(previewMode.value)
    const d = res.data || {}
    context.brand_policy = d.brand_policy || ''
    context.mode_goal = d.mode_goal || ''
    context.expert_team = d.expert_team || ''
    context.official_site_url = d.official_site_url || ''
    modes.value = d.modes || modes.value
  } catch (e) { /* 忽略 */ }
}

// ============ 三 API 调度 / 合规策略 ============
async function loadScheduler() {
  schedLoading.value = true
  try {
    const res = await automationPromptApi.schedulerStatus()
    sched.value = res.data || null
  } catch (e) { /* 拦截器提示 */ }
  finally { schedLoading.value = false }
}
async function loadStrategies() {
  try {
    const res = await automationPromptApi.publishStrategies()
    strategies.value = res.data || []
  } catch (e) { /* 拦截器提示 */ }
}
function openStrategy(s) {
  editing.value = { ...s }
  strategyDlg.value = true
}
async function saveStrategy() {
  if (!editing.value) return
  savingStrategy.value = true
  const e = editing.value
  const payload = {
    title_min_len: e.title_min_len, title_max_len: e.title_max_len,
    min_words: e.min_words, max_words: e.max_words,
    structure_rules: e.structure_rules, paragraph_rules: e.paragraph_rules,
    banned_words_rule: e.banned_words_rule, soft_ad_rule: e.soft_ad_rule,
    publish_mode_type: e.publish_mode_type,
    geo_keyword_density: e.geo_keyword_density,
    geo_structured_summary: e.geo_structured_summary,
    geo_title_info: e.geo_title_info,
    geo_notes: e.geo_notes, notes: e.notes,
  }
  try {
    await automationPromptApi.updateStrategy(e.id, payload)
    ElMessage.success('已保存平台合规策略')
    strategyDlg.value = false
    await loadStrategies()
  } catch (e) { /* 拦截器提示 */ }
  finally { savingStrategy.value = false }
}
function roleLabel(role) {
  return {
    research: '① 选题调研 (research)',
    writing: '② 正文撰写 (writing)',
    review: '③ 审核优化 (review)',
    general: '④ 通用 (general)',
  }[role] || role || '—'
}
function pubModeTypeLabel(t) {
  return { direct: '直接发布', draft: '存草稿', scheduled: '定时发布' }[t] || t || '直接发布'
}

// ============ 编辑操作 ============
function onEdit(p) { /* 仅触发 computed 重算（dirty） */ void p }

async function saveOne(p) {
  const st = editState[p.key]
  st.saving = true
  try {
    await automationPromptApi.update(p.key, st.draft)
    p.content = st.draft
    ElMessage.success(`已保存：${p.name}`)
    if (p.key === 'EXPERT_TEAM_DESC') await loadContext()  // 专家团队改动即时反映到背景预览
  } catch (e) { /* 错误已在拦截器提示 */ }
  finally { st.saving = false }
}
function discard(p) {
  editState[p.key].draft = p.content || ''
}
async function resetOne(p) {
  await ElMessageBox.confirm(`确认将「${p.name}」重置为出厂默认？当前自定义内容将丢失。`, '重置提示词', { type: 'warning' })
  const res = await automationPromptApi.reset(p.key)
  // 重新拉取该条最新内容
  const fresh = (await automationPromptApi.list()).data || []
  const f = fresh.find(x => x.key === p.key)
  if (f) {
    p.content = f.content
    p.default_content = f.default_content
    editState[p.key].draft = f.content
  }
  if (p.key === 'EXPERT_TEAM_DESC') await loadContext()
  ElMessage.success('已重置为默认')
}
async function saveAll() {
  savingAll.value = true
  try {
    const tasks = prompts.value.filter(isDirty).map(p => automationPromptApi.update(p.key, editState[p.key].draft).then(() => { p.content = editState[p.key].draft }))
    await Promise.all(tasks)
    if (dirtyKeys.value.includes('EXPERT_TEAM_DESC')) await loadContext()
    ElMessage.success('已保存全部改动')
  } catch (e) { /* 拦截器提示 */ }
  finally { savingAll.value = false }
}

async function copyText(text, label) {
  if (!text) { ElMessage.warning('没有可复制的内容'); return }
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text)
    else {
      const ta = document.createElement('textarea')
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'
      document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta)
    }
    ElMessage.success(`已复制：${label || '内容'}`)
  } catch (e) { ElMessage.error('复制失败，请手动选择文本复制') }
}

// 切换模式时，预览内容自动刷新（editState 不变）
watch(previewMode, () => { /* loadContext 已在 radio change 触发 */ })

onMounted(loadAll)
</script>

<style scoped>
.auto-studio { display: flex; flex-direction: column; gap: 16px; }

/* ============ 顶部 ============ */
.as-header { padding: 16px 20px; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.as-header__title { display: flex; align-items: center; gap: 12px; }
.as-header__icon { font-size: 26px; color: var(--brand-600); }
.as-header__title h1 { margin: 0; font-size: 18px; color: var(--text-primary); }
.as-header__title p { margin: 3px 0 0; font-size: 12.5px; color: var(--text-tertiary); }
.as-header__ops { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.as-mode-label { font-size: 12px; color: var(--text-secondary); font-weight: 600; }

/* ============ 区块通用 ============ */
.as-section { padding: 18px 20px; }
.as-section__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.as-section__head h2 { margin: 0; font-size: 15px; font-weight: 700; color: var(--text-primary); }

/* ============ 工作流可视化 ============ */
.as-legend { display: flex; gap: 14px; flex-wrap: wrap; }
.as-legend__item { font-size: 12px; color: var(--text-tertiary); display: inline-flex; align-items: center; gap: 5px; }
.as-pipe { display: flex; align-items: stretch; gap: 0; overflow-x: auto; padding-bottom: 8px; }
.as-pipe__node {
  position: relative; flex: 0 0 196px; background: var(--bg-page); border: 1px solid var(--border-light);
  border-radius: var(--radius-md); padding: 12px; margin-right: 26px;
}
.as-pipe__node:last-child { margin-right: 0; }
.as-pipe__top { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.as-pipe__no { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: var(--brand-500); color: #fff; font-size: 12px; font-weight: 700; flex-shrink: 0; }
.as-pipe__agent { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 10px; white-space: nowrap; }
.as-pipe__title { font-size: 13px; font-weight: 600; color: var(--text-primary); line-height: 1.5; }
.as-pipe__hint { margin-top: 6px; font-size: 11px; color: var(--text-tertiary); line-height: 1.5; cursor: help; }
.as-pipe__arrow { position: absolute; right: -22px; top: 50%; transform: translateY(-50%); color: var(--brand-300); font-size: 16px; font-weight: 700; z-index: 2; }
.as-pipe__note { margin-top: 14px; }

/* agent 色块 */
.agent-planner { background: #ede9fe; color: #6d28d9; }
.agent-writer { background: #e0f2fe; color: #0369a1; }
.agent-system { background: #f1f5f9; color: #475569; }
.agent-dual { background: #fef3c7; color: #b45309; }
.agent-geo { background: #dcfce7; color: #15803d; }
.agent-fact { background: #fef9c3; color: #a16207; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; vertical-align: 1px; }

/* ============ 背景内容 ============ */
.as-mode-tag { font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 10px; }
.as-mode-tag.m-platform { background: #e0f2fe; color: #0369a1; }
.as-mode-tag.m-geo { background: #fef3c7; color: #b45309; }
.as-mode-tag.m-green { background: #dcfce7; color: #15803d; }
.as-mode-tag.m-official { background: #ede9fe; color: #6d28d9; }
.as-ctx { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.as-ctx__block { background: var(--bg-page); border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 12px 14px; }
.as-ctx__block--wide { grid-column: 1 / -1; }
.as-ctx__title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 8px; display: flex; align-items: center; }
.as-ctx__pre { background: #fff; border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 10px 12px; font-size: 12.5px; line-height: 1.7; color: var(--text-secondary); white-space: pre-wrap; word-break: break-word; max-height: 220px; overflow: auto; margin: 0; font-family: var(--font-mono, monospace); }
.as-ctx__hint { margin-top: 12px; font-size: 12px; color: var(--text-quaternary); line-height: 1.6; }

/* ============ 提示词清单 ============ */
.as-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
.as-tab {
  display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; font-size: 13px;
  border: 1px solid var(--border-light); background: var(--bg-card); color: var(--text-secondary);
  border-radius: var(--radius-md); cursor: pointer; transition: var(--transition);
}
.as-tab:hover { border-color: var(--brand-300); color: var(--brand-600); }
.as-tab.is-active { background: var(--brand-500); border-color: var(--brand-500); color: #fff; font-weight: 600; }
.as-tab__count { font-size: 11px; background: var(--slate-100); color: var(--text-tertiary); border-radius: 10px; padding: 0 7px; }
.as-tab.is-active .as-tab__count { background: rgba(255,255,255,0.25); color: #fff; }

.as-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.as-prompt { border: 1px solid var(--border-light); border-radius: var(--radius-lg); padding: 14px 16px; background: var(--bg-card); display: flex; flex-direction: column; transition: var(--transition); }
.as-prompt:hover { box-shadow: var(--shadow-md); }
.as-prompt.is-dirty { border-color: var(--amber-400, #fbbf24); box-shadow: 0 0 0 3px rgba(245,158,11,0.12); }
.as-prompt.is-mdx { border-color: #c4b5fd; background: #faf5ff; }
.as-prompt__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.as-prompt__titles { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.as-prompt__name { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.as-prompt__role { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 10px; }
.as-prompt__cat { font-size: 11px; color: var(--text-tertiary); background: var(--slate-100); border-radius: 10px; padding: 1px 8px; }
.as-prompt__step { font-size: 11px; color: var(--brand-600); }
.as-prompt__toolbar { margin-bottom: 8px; }
.as-prompt__area :deep(textarea) { font-family: var(--font-mono, monospace); font-size: 12.5px; line-height: 1.7; color: var(--text-primary); }
.as-prompt__preview { background: var(--bg-page); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 10px 12px; font-size: 12.5px; line-height: 1.7; color: var(--text-secondary); white-space: pre-wrap; word-break: break-word; max-height: 320px; overflow: auto; margin: 0; font-family: var(--font-mono, monospace); }
.as-prompt__foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.as-prompt__foot-left { display: flex; gap: 6px; flex-wrap: wrap; }

/* ============ 三 API 调度状态 ============ */
.sched { display: flex; flex-direction: column; gap: 12px; }
.sched__note { margin: 0; }
.sched__roles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.sched-role { border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 12px 14px; background: var(--bg-page); }
.sched-role__head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.sched-role__name { font-size: 13px; font-weight: 700; padding: 2px 10px; border-radius: 10px; }
.rr-research { background: #ede9fe; color: #6d28d9; }
.rr-writing { background: #e0f2fe; color: #0369a1; }
.rr-review { background: #dcfce7; color: #15803d; }
.rr-general { background: #f1f5f9; color: #475569; }
.sched-role__desc { flex: 1; min-width: 120px; font-size: 11px; color: var(--text-tertiary); line-height: 1.5; }
.sched-role__empty { font-size: 12px; color: var(--text-quaternary); padding: 6px 0; }
.sched-cfg { display: grid; grid-template-columns: 1.2fr 0.9fr 1fr auto auto; gap: 8px; align-items: center; padding: 6px 0; border-top: 1px dashed var(--border-light); font-size: 12px; }
.sched-cfg:first-of-type { border-top: none; }
.sched-cfg__name { font-weight: 600; color: var(--text-primary); }
.sched-cfg__provider, .sched-cfg__model { color: var(--text-tertiary); font-family: var(--font-mono, monospace); font-size: 11px; }
.sched-cfg__lat { font-weight: 700; font-family: var(--font-mono, monospace); }
.sched-cfg__lat.lat-ok { color: #10b981; }
.sched-cfg__lat.lat-none { color: var(--text-quaternary); font-weight: 500; }
.sched-cfg__fail { font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 9px; }
.sched-cfg__fail.fail-ok { background: #ecfdf5; color: #059669; }
.sched-cfg__fail.fail-bad { background: #fef2f2; color: #dc2626; }

/* ============ 各平台合规发布策略 ============ */
.ps-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.ps-card { border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 12px 14px; background: var(--bg-page); display: flex; flex-direction: column; }
.ps-card__head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.ps-card__name { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.ps-mode { font-size: 11px; font-weight: 600; padding: 1px 9px; border-radius: 10px; }
.ps-mode.m-platform { background: #e0f2fe; color: #0369a1; }
.ps-mode.m-geo { background: #fef3c7; color: #b45309; }
.ps-mode.m-green { background: #dcfce7; color: #15803d; }
.ps-mode.m-official { background: #ede9fe; color: #6d28d9; }
.ps-card__head .el-button { margin-left: auto; }
.ps-card__body { display: flex; flex-direction: column; gap: 5px; }
.ps-line { display: flex; gap: 8px; font-size: 12px; line-height: 1.5; }
.ps-k { width: 34px; flex-shrink: 0; color: var(--text-tertiary); font-weight: 600; }
.ps-v { color: var(--text-secondary); word-break: break-word; }
.ps-edit-row { display: flex; gap: 24px; flex-wrap: wrap; }

@media (max-width: 1100px) {
  .as-grid { grid-template-columns: 1fr; }
  .as-ctx { grid-template-columns: 1fr; }
  .sched__roles { grid-template-columns: 1fr; }
}
</style>
