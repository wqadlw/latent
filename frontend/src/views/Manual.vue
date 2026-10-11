<template>
  <div class="manual-page">
    <!-- 顶部 -->
    <div class="card manual-hero">
      <div class="hero-main">
        <div class="hero-title">
          <el-icon class="hero-icon"><Reading /></el-icon>
          <div>
            <h1>操作手册 · 全流程复现指南</h1>
            <p>浏览器工作室自动化发布系统的完整 10 步流程。每一步都标明「发什么给 AI、等什么返回、取什么结果、下一步做什么」。照着做，任何人都能用网页 AI 手动复现整个流程。</p>
          </div>
        </div>
      </div>
      <div class="hero-ops">
        <el-radio-group v-model="previewMode" size="small" @change="loadContext">
          <el-radio-button v-for="m in modes" :key="m.value" :label="m.value">{{ m.label }}</el-radio-button>
        </el-radio-group>
        <el-button :icon="DocumentCopy" size="small" @click="copyAll">复制完整手册</el-button>
      </div>
    </div>

    <!-- ① 总览 -->
    <div class="card man-section">
      <div class="man-section__head">
        <span class="man-no">①</span>
        <h2>全流程总览（10 步）</h2>
      </div>
      <p class="man-intro">从选题到发布，系统按以下 10 步顺序执行。前 7 步由 AI 自动完成，第 8 步人工确认，第 9 步发布。每一步都用独立的 API 角色调度（见下表）。</p>
      <div class="man-overview">
        <div v-for="s in steps" :key="s.step_key" class="ov-node">
          <div class="ov-no">{{ s.step_no }}</div>
          <div class="ov-body">
            <div class="ov-title">{{ s.title }}</div>
            <div class="ov-meta">
              <span class="ov-agent" :class="agentClass(s.agent)">{{ agentLabel(s.agent) }}</span>
              <span class="ov-role" :class="'orr-' + stepRole(s.step_key)">{{ stepRoleLabel(s.step_key) }}</span>
            </div>
          </div>
          <span v-if="s.step_no < steps.length" class="ov-arrow">→</span>
        </div>
      </div>
      <el-alert class="man-note" type="info" :closable="false" show-icon
        title="三 API 角色路由"
        description="research（选题调研·大纲，开 thinking 推理）→ 步骤①②；writing（正文撰写·精修，非推理）→ 步骤③④⑤；review（审核优化·整改，开 thinking）→ 步骤⑥⑦；人工 → 步骤⑧⑨。每个角色独立 API Key，按任务类型分流。" />
    </div>

    <!-- ② 背景注入内容 -->
    <div class="card man-section">
      <div class="man-section__head">
        <span class="man-no">②</span>
        <h2>背景内容（每次都会注入提示词）</h2>
        <span class="man-mode-tag" :class="modeTagClass(previewMode)">{{ modeLabel(previewMode, modes) }}</span>
      </div>
      <p class="man-intro">以下内容会以占位符形式注入到每一步的提示词中。手动复现时，请把对应内容粘贴到你的提示词中。</p>
      <div class="man-ctx-grid">
        <div class="man-ctx-block">
          <div class="man-ctx-title"><i class="dot dot-geo"></i>品牌策略 <code>{'{brand_policy}'}</code></div>
          <pre class="man-pre">{{ context.brand_policy || '—' }}</pre>
          <el-button size="small" text :icon="DocumentCopy" @click="copyText(context.brand_policy, '品牌策略')">复制</el-button>
        </div>
        <div class="man-ctx-block">
          <div class="man-ctx-title"><i class="dot dot-fact"></i>模式目标 <code>{'{mode_goal}'}</code></div>
          <pre class="man-pre">{{ context.mode_goal || '—' }}</pre>
          <el-button size="small" text :icon="DocumentCopy" @click="copyText(context.mode_goal, '模式目标')">复制</el-button>
        </div>
        <div class="man-ctx-block man-ctx-block--wide">
          <div class="man-ctx-title"><i class="dot dot-planner"></i>专家团队配置 <code>{'{expert_team}'}</code></div>
          <pre class="man-pre">{{ context.expert_team || '—' }}</pre>
          <el-button size="small" text :icon="DocumentCopy" @click="copyText(context.expert_team, '专家团队配置')">复制</el-button>
        </div>
      </div>
    </div>

    <!-- ③ 逐步复现指南 -->
    <div class="card man-section">
      <div class="man-section__head">
        <span class="man-no">③</span>
        <h2>逐步复现指南（每步可复制给网页 AI）</h2>
        <el-tag type="info" effect="plain" size="small">{{ steps.length }} 步</el-tag>
      </div>
      <p class="man-intro">展开任意一步，复制「发送内容」粘贴给网页 AI，把 AI 返回的结果填回系统对应步骤即可。每步都标明预期返回字段和下一步动作。</p>

      <div class="man-steps">
        <div v-for="s in steps" :key="s.step_key" class="man-step">
          <div class="man-step__head" @click="toggle(s.step_key)">
            <span class="man-step__no">{{ s.step_no }}</span>
            <span class="man-step__title">{{ s.title }}</span>
            <span class="man-step__role" :class="'orr-' + stepRole(s.step_key)">{{ stepRoleLabel(s.step_key) }}</span>
            <span class="man-step__agent" :class="agentClass(s.agent)">{{ agentLabel(s.agent) }}</span>
            <el-icon class="man-step__arrow" :class="{ 'is-open': openMap[s.step_key] }"><ArrowRight /></el-icon>
          </div>
          <transition name="expand">
            <div v-show="openMap[s.step_key]" class="man-step__body">
              <div class="man-step__desc">{{ stepDesc(s.step_key) }}</div>

              <!-- 发送内容 -->
              <div class="man-field">
                <div class="man-field__label">
                  <i class="dot dot-send"></i>发送给 AI 的完整内容
                  <el-button size="small" text :icon="DocumentCopy" @click="copyText(stepPrompt(s.step_key), s.title + ' 提示词')">复制</el-button>
                </div>
                <pre class="man-pre man-pre--send">{{ stepPrompt(s.step_key) || '（本步为系统/人工操作，无 AI 调用）' }}</pre>
              </div>

              <!-- 预期返回 -->
              <div class="man-field">
                <div class="man-field__label"><i class="dot dot-recv"></i>预期返回字段</div>
                <div class="man-fields">
                  <span v-for="f in stepExpected(s.step_key)" :key="f" class="man-field-tag">{{ f }}</span>
                </div>
              </div>

              <!-- 下一步 -->
              <div class="man-field">
                <div class="man-field__label"><i class="dot dot-next"></i>下一步动作</div>
                <div class="man-next">{{ stepNext(s.step_key) }}</div>
              </div>

              <!-- 手动复现提示 -->
              <div class="man-howto">
                <el-icon><InfoFilled /></el-icon>
                <span>{{ stepHowTo(s.step_key) }}</span>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>

    <!-- ④ 三 API 调度说明 -->
    <div class="card man-section">
      <div class="man-section__head">
        <span class="man-no">④</span>
        <h2>三 API 调度说明</h2>
      </div>
      <div class="man-api-grid">
        <div class="man-api-card">
          <span class="man-api-chip orr-research">research</span>
          <div class="man-api-title">选题调研 · 大纲</div>
          <div class="man-api-desc">负责步骤 ①②：明晰任务、产出大纲。开启 thinking 推理，规划质量更高。</div>
          <div class="man-api-steps">用于：clarify · outline</div>
        </div>
        <div class="man-api-card">
          <span class="man-api-chip orr-writing">writing</span>
          <div class="man-api-title">正文撰写 · 精修</div>
          <div class="man-api-desc">负责步骤 ③④⑤：初稿、去 AI 味、GEO 终稿。非推理模式，速度快。</div>
          <div class="man-api-steps">用于：draft · depolish · geo</div>
        </div>
        <div class="man-api-card">
          <span class="man-api-chip orr-review">review</span>
          <div class="man-api-title">审核优化 · 整改</div>
          <div class="man-api-desc">负责步骤 ⑥⑦：评审、下达整改指令。开启 thinking 推理，把关质量。</div>
          <div class="man-api-steps">用于：review · revise</div>
        </div>
      </div>
      <el-alert class="man-note" type="success" :closable="false" show-icon
        title="负载均衡 + 故障自动切换"
        description="同一角色可配置多个 API Key，系统按 round-robin 轮询分流；某个 Key 鉴权失败/限流/超时时自动切换到同角色其他 Key。每次调用记录响应耗时(ms)，可在「自动化指挥中心」查看。" />
    </div>

    <!-- ⑤ 合规发布策略 -->
    <div class="card man-section">
      <div class="man-section__head">
        <span class="man-no">⑤</span>
        <h2>各平台合规发布策略</h2>
        <el-tag type="info" effect="plain" size="small">{{ strategies.length }} 个平台</el-tag>
      </div>
      <div class="man-ps-grid">
        <div v-for="s in strategies" :key="s.id" class="man-ps-card">
          <div class="man-ps-head">
            <span class="man-ps-name">{{ s.platform_name }}</span>
            <span class="man-ps-mode" :class="modeTagClass(s.publish_mode)">{{ modeLabel(s.publish_mode, modes) }}</span>
          </div>
          <div class="man-ps-body">
            <div class="man-ps-line"><span class="man-ps-k">标题</span>{{ s.title_min_len }}–{{ s.title_max_len }} 字</div>
            <div class="man-ps-line"><span class="man-ps-k">字数</span>{{ s.min_words }}–{{ s.max_words }} 字</div>
            <div class="man-ps-line"><span class="man-ps-k">结构</span>{{ s.structure_rules }}</div>
            <div class="man-ps-line"><span class="man-ps-k">段落</span>{{ s.paragraph_rules }}</div>
            <div class="man-ps-line"><span class="man-ps-k">违禁</span>{{ s.banned_words_rule }}</div>
            <div class="man-ps-line"><span class="man-ps-k">软文</span>{{ s.soft_ad_rule }}</div>
            <div class="man-ps-line"><span class="man-ps-k">发布</span>{{ pubModeTypeLabel(s.publish_mode_type) }}</div>
            <div class="man-ps-line"><span class="man-ps-k">GEO</span>关键词密度 {{ s.geo_keyword_density }} · 结构化摘要 {{ s.geo_structured_summary ? '是' : '否' }} · 标题信息量 {{ s.geo_title_info ? '是' : '否' }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ⑥ 质量闸门 -->
    <div class="card man-section">
      <div class="man-section__head">
        <span class="man-no">⑥</span>
        <h2>质量闸门（确保文章发得出且发挥作用）</h2>
      </div>
      <div class="man-gate-grid">
        <div class="man-gate-card man-gate-card--hard">
          <div class="man-gate-title"><i class="dot dot-hard"></i>硬闸门（不通过 = 拦截）</div>
          <ul class="man-gate-list">
            <li>违禁词检测：极限词/绝对化用语/虚假宣传词零容忍</li>
            <li>硬广检测：站外引流链接/私人联系方式（微信/电话/邮箱）零容忍</li>
            <li>AI 味检测：机械排比/万能开头/套话结尾等 AI 痕迹需清除</li>
          </ul>
        </div>
        <div class="man-gate-card man-gate-card--geo">
          <div class="man-gate-title"><i class="dot dot-geo"></i>GEO 闸门（geo 模式 ≥70 分才放行）</div>
          <ul class="man-gate-list">
            <li>品牌提及：品牌名出现次数（geo 模式 ≥3 次）</li>
            <li>结构化摘要：是否有清晰的摘要/要点</li>
            <li>关键词密度：目标关键词分布是否合理</li>
            <li>标题信息量：标题是否含关键信息</li>
            <li>权威信号：是否有案例/数据/专利等支撑</li>
            <li>可引用性：内容是否便于 AI 抓取引用</li>
          </ul>
        </div>
        <div class="man-gate-card man-gate-card--soft">
          <div class="man-gate-title"><i class="dot dot-soft"></i>建议项（不阻塞，仅提示优化）</div>
          <ul class="man-gate-list">
            <li>字数检查：是否符合平台要求区间</li>
            <li>结构检查：是否有清晰的小标题分层</li>
            <li>段落规范：段落长度是否适中</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Reading, ArrowRight, DocumentCopy, InfoFilled } from '@element-plus/icons-vue'
import { automationPromptApi } from '../api'
import { copyText } from '../utils/clipboard'
import { modeLabel, modeTagClass } from '../constants/modes'

const steps = ref([])
const prompts = ref([])
const strategies = ref([])
const modes = ref([])
const context = reactive({ brand_policy: '', mode_goal: '', expert_team: '', official_site_url: '' })
const previewMode = ref('geo')
const openMap = reactive({})

// 步骤 → 提示词 key / API 角色：单一真源来自后端 /api/automation-prompts/meta。
// 这里的字面量仅作「请求到达前的防御默认值」，loadAll 会用后端返回值覆盖，
// 从而彻底消除前后端双份映射漂移（后端改了映射，前端自动跟随）。
const meta = reactive({
  step_prompt_keys: {
    clarify: 'PLANNER_CLARIFY_PROMPT',
    outline: 'PLANNER_OUTLINE_PROMPT',
    draft: 'STAGE_draft',
    depolish: 'STAGE_depolish',
    geo: 'STAGE_geo',
    review: 'PLANNER_REVIEW_PROMPT',
    revise: 'PLANNER_DIRECTIVE_PROMPT',
  },
  role_by_step: {
    clarify: 'research', outline: 'research',
    draft: 'writing', depolish: 'writing', geo: 'writing',
    review: 'review', revise: 'review',
    confirm: 'human', publish: 'system',
  },
})
const ROLE_LABEL = {
  research: '选题调研 API', writing: '正文撰写 API', review: '审核优化 API',
  human: '人工操作', system: '系统操作',
}

// 每步的详细说明
const STEP_DETAIL = {
  clarify: {
    desc: '主编（research 角色）分析选题意图，明确写作方向、目标读者、核心卖点，输出结构化简报。',
    expected: ['写作方向', '目标读者', '核心卖点', '文章基调', '字数建议'],
    next: '拿到明晰简报后，进入步骤②出大纲。',
    howto: '复制下方提示词粘贴给 DeepSeek，把返回的 JSON 简报填回系统「明晰」步骤。',
  },
  outline: {
    desc: '主编（research 角色）根据简报产出文章大纲，含标题、各小节标题与要点、整体结构。',
    expected: ['标题', '大纲结构', '各小节要点', '字数分配'],
    next: '大纲确认后，进入步骤③写初稿。',
    howto: '复制提示词 + 上一步的简报一起发给 AI，把返回的大纲填回系统「大纲」步骤。',
  },
  draft: {
    desc: '写手（writing 角色）根据大纲写出完整初稿，遵循品牌策略与模式目标。',
    expected: ['完整文章正文', '标题', '字数'],
    next: '初稿完成后，进入步骤④去 AI 味。',
    howto: '复制提示词 + 大纲发给 AI，把返回的文章正文填回系统「初稿」步骤。',
  },
  depolish: {
    desc: '写手（writing 角色）去除初稿的 AI 味（机械排比、万能开头、套话结尾等），让文章读起来像人写的。',
    expected: ['去AI味后的正文', '修改说明'],
    next: '去 AI 味后，进入步骤⑤ GEO 强化。',
    howto: '复制提示词 + 初稿发给 AI，把返回的精修稿填回系统「去AI味」步骤。',
  },
  geo: {
    desc: '写手（writing 角色）按 GEO 策略强化文章：品牌提及、结构化摘要、关键词密度、权威信号、可引用性。',
    expected: ['GEO强化终稿', 'GEO信号清单', '品牌提及次数'],
    next: 'GEO 终稿完成后，进入步骤⑥主编评审。',
    howto: '复制提示词 + 去AI味稿发给 AI，把返回的 GEO 终稿填回系统「GEO终稿」步骤。',
  },
  review: {
    desc: '主编（review 角色）对终稿做合规检查 + GEO 评分 + 评审意见，决定是否放行。',
    expected: ['compliance_pass', 'geo_score', 'gate_pass', 'editor_review'],
    next: '若闸门通过，进入步骤⑧人工确认；若未通过，进入步骤⑦整改。',
    howto: '复制提示词 + GEO 终稿发给 AI，把返回的评审结果填回系统「评审」步骤。',
  },
  revise: {
    desc: '主编下达整改指令 → 写手按指令改写 → 主编二次评审。最多 3 轮，达标即停。',
    expected: ['planner_directives', '改写后正文', '二次评审', 'geo_score', 'gate_pass'],
    next: '整改达标后，进入步骤⑧人工确认。',
    howto: '把主编指令 + 待改稿发给 AI，把改写结果填回系统「整改」步骤。',
  },
  confirm: {
    desc: '人工闸门：你检查终稿是否满意。满意则加入内容中心（ContentAsset），不满意可重跑或手动修改。',
    expected: ['人工确认', '是否加入内容中心'],
    next: '确认后进入步骤⑨发布到平台（可设自动发布或手动点发布）。',
    howto: '本步无 AI 调用。阅读终稿，满意就点「满意，加入内容中心」按钮。',
  },
  publish: {
    desc: '系统创建发布任务（PublishJob），含人工审核闸门。含违禁/引流词则自动转人工审核。',
    expected: ['job_id', '发布状态', '发布URL'],
    next: '发布成功后，文章进入平台。后续可在「AI推荐监测」验证 GEO 效果。',
    howto: '本步为系统操作。点「发布」按钮即可。如含违禁词会自动转人工审核。',
  },
  connect: {
    desc: '系统连接写作引擎（DeepSeek/豆包/Mock），初始化运行上下文。',
    expected: ['引擎状态', '发布模式', '品牌策略'],
    next: '连接成功后，进入步骤①明晰任务。',
    howto: '本步为系统操作，无需手动干预。',
  },
}

function stepRole(key) { return meta.role_by_step[key] || 'system' }
function stepRoleLabel(key) { return ROLE_LABEL[stepRole(key)] || key }
function stepDesc(key) { return (STEP_DETAIL[key] || {}).desc || '' }
function stepExpected(key) { return (STEP_DETAIL[key] || {}).expected || [] }
function stepNext(key) { return (STEP_DETAIL[key] || {}).next || '' }
function stepHowTo(key) { return (STEP_DETAIL[key] || {}).howto || '' }

// 步骤 → 提示词 key 映射：委托后端 meta.step_prompt_keys（见上方 meta 定义）

function stepPrompt(key) {
  if (key === 'connect' || key === 'confirm' || key === 'publish') return ''
  const pk = meta.step_prompt_keys[key]
  if (!pk) return ''
  const p = prompts.value.find(x => x.key === pk)
  if (!p) return ''
  return injectContext(p.content || p.draft || '')
}

function injectContext(text) {
  if (!text) return ''
  const map = {
    '{brand_policy}': context.brand_policy,
    '{mode_goal}': context.mode_goal,
    '{expert_team}': context.expert_team,
    '{official_site_url}': context.official_site_url,
  }
  let t = text
  for (const [k, v] of Object.entries(map)) {
    if (v) t = t.split(k).join(v)
  }
  return t
}

function toggle(key) { openMap[key] = !openMap[key] }

const agentMeta = {
  planner: { label: '📋 主编', cls: 'agent-planner' },
  writer: { label: '✍️ 写手', cls: 'agent-writer' },
  system: { label: '⚙️ 系统/人工', cls: 'agent-system' },
  dual: { label: '📋✍️ 双角色', cls: 'agent-dual' },
}
function agentLabel(a) { return (agentMeta[a] || {}).label || a }
function agentClass(a) { return (agentMeta[a] || {}).cls || '' }

function pubModeTypeLabel(t) {
  return { direct: '直接发布', draft: '存草稿', scheduled: '定时发布' }[t] || t || '直接发布'
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
  } catch (e) { /* ignore */ }
}

async function loadAll() {
  const [pr, st, ps, cs, mt] = await Promise.all([
    automationPromptApi.list(),
    automationPromptApi.steps(),
    automationPromptApi.publishStrategies(),
    automationPromptApi.context(previewMode.value),
    automationPromptApi.meta(),
  ])
  prompts.value = (pr.data || []).map(p => ({ ...p }))
  steps.value = st.data || []
  strategies.value = ps.data || []
  const d = cs.data || {}
  context.brand_policy = d.brand_policy || ''
  context.mode_goal = d.mode_goal || ''
  context.expert_team = d.expert_team || ''
  context.official_site_url = d.official_site_url || ''
  modes.value = d.modes || []
  // 用后端单一真源覆盖前端防御默认值（步骤→提示词key / 步骤→API角色）
  if (mt.data) {
    if (mt.data.step_prompt_keys) meta.step_prompt_keys = mt.data.step_prompt_keys
    if (mt.data.role_by_step) meta.role_by_step = mt.data.role_by_step
  }
  // 默认展开第一步
  if (steps.value.length) openMap[steps.value[0].step_key] = true
}

// copyText 已抽到 utils/clipboard.js（全站统一实现）

function copyAll() {
  let parts = []
  parts.push('=== 操作手册 · 全流程复现指南 ===\n')
  parts.push(`发布模式：${modeLabel(previewMode.value, modes.value)}\n`)
  parts.push('--- 背景内容 ---')
  parts.push(`品牌策略：\n${context.brand_policy}`)
  parts.push(`模式目标：\n${context.mode_goal}`)
  parts.push(`专家团队：\n${context.expert_team}`)
  parts.push('\n--- 10 步流程 ---')
  for (const s of steps.value) {
    parts.push(`\n步骤${s.step_no}：${s.title}（角色：${stepRoleLabel(s.step_key)}）`)
    parts.push(stepDesc(s.step_key))
    parts.push(`预期返回：${stepExpected(s.step_key).join('、')}`)
    parts.push(`下一步：${stepNext(s.step_key)}`)
    const p = stepPrompt(s.step_key)
    if (p) parts.push(`提示词：\n${p}`)
  }
  copyText(parts.join('\n'), '完整手册')
}

onMounted(loadAll)
</script>

<style scoped>
.manual-page { display: flex; flex-direction: column; gap: 16px; }

/* hero */
.manual-hero { padding: 18px 22px; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.hero-title { display: flex; align-items: flex-start; gap: 14px; }
.hero-icon { font-size: 30px; color: var(--brand-600); margin-top: 2px; }
.hero-title h1 { margin: 0 0 4px; font-size: 20px; color: var(--text-primary); }
.hero-title p { margin: 0; font-size: 13px; color: var(--text-tertiary); line-height: 1.6; max-width: 680px; }
.hero-ops { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

/* section */
.man-section { padding: 18px 22px; }
.man-section__head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.man-no {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 50%; background: var(--brand-500); color: #fff;
  font-size: 14px; font-weight: 700; flex-shrink: 0;
}
.man-section__head h2 { margin: 0; font-size: 16px; font-weight: 700; color: var(--text-primary); }
.man-intro { margin: 0 0 14px; font-size: 13px; color: var(--text-tertiary); line-height: 1.6; }
.man-note { margin-top: 14px; }

/* 总览 */
.man-overview { display: flex; align-items: stretch; gap: 0; overflow-x: auto; padding-bottom: 8px; }
.ov-node { position: relative; flex: 0 0 200px; display: flex; gap: 10px; margin-right: 26px; }
.ov-no { width: 28px; height: 28px; border-radius: 50%; background: var(--brand-500); color: #fff; font-size: 13px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.ov-body { flex: 1; }
.ov-title { font-size: 13px; font-weight: 600; color: var(--text-primary); line-height: 1.4; }
.ov-meta { margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap; }
.ov-agent { font-size: 10px; font-weight: 700; padding: 1px 7px; border-radius: 9px; }
.ov-role { font-size: 10px; font-weight: 700; padding: 1px 7px; border-radius: 9px; }
.ov-arrow { position: absolute; right: -20px; top: 14px; color: var(--brand-300); font-size: 16px; font-weight: 700; }

/* agent 色块 */
.agent-planner { background: #ede9fe; color: #6d28d9; }
.agent-writer { background: #e0f2fe; color: #0369a1; }
.agent-system { background: #f1f5f9; color: #475569; }
.agent-dual { background: #fef3c7; color: #b45309; }
/* role 色块 */
.orr-research { background: #ede9fe; color: #6d28d9; }
.orr-writing { background: #e0f2fe; color: #0369a1; }
.orr-review { background: #dcfce7; color: #15803d; }
.orr-human { background: #fef3c7; color: #b45309; }
.orr-system { background: #f1f5f9; color: #475569; }

.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; }
.dot-geo { background: var(--accent-emerald); }
.dot-fact { background: var(--accent-amber); }
.dot-planner { background: var(--brand-500); }
.dot-send { background: var(--accent-sky); }
.dot-recv { background: var(--accent-violet); }
.dot-next { background: var(--accent-emerald); }
.dot-hard { background: var(--accent-rose); }
.dot-soft { background: var(--slate-400); }

/* 背景内容 */
.man-mode-tag { font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 10px; }
.man-mode-tag.m-platform { background: #e0f2fe; color: #0369a1; }
.man-mode-tag.m-geo { background: #fef3c7; color: #b45309; }
.man-mode-tag.m-green { background: #dcfce7; color: #15803d; }
.man-mode-tag.m-official { background: #ede9fe; color: #6d28d9; }
.man-ctx-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.man-ctx-block { background: var(--bg-page); border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 12px 14px; }
.man-ctx-block--wide { grid-column: 1 / -1; }
.man-ctx-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 8px; display: flex; align-items: center; }
.man-ctx-title code { font-size: 11px; background: var(--slate-100); color: var(--text-tertiary); padding: 1px 6px; border-radius: 4px; margin-left: 6px; }
.man-pre {
  background: #fff; border: 1px solid var(--border-light); border-radius: var(--radius-sm);
  padding: 10px 12px; font-size: 12.5px; line-height: 1.7; color: var(--text-secondary);
  white-space: pre-wrap; word-break: break-word; max-height: 260px; overflow: auto; margin: 0 0 6px;
  font-family: var(--font-mono, monospace);
}
.man-pre--send { max-height: 400px; background: #f8fafc; border-color: var(--brand-200); }

/* 步骤 */
.man-steps { display: flex; flex-direction: column; gap: 10px; }
.man-step { border: 1px solid var(--border-light); border-radius: var(--radius-md); overflow: hidden; transition: var(--transition); }
.man-step:hover { border-color: var(--brand-300); }
.man-step__head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; cursor: pointer; background: var(--bg-card); transition: var(--transition-fast); }
.man-step__head:hover { background: var(--bg-page); }
.man-step__no { width: 24px; height: 24px; border-radius: 50%; background: var(--brand-500); color: #fff; font-size: 12px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.man-step__title { font-size: 14px; font-weight: 600; color: var(--text-primary); flex: 1; }
.man-step__role { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 9px; }
.man-step__agent { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 9px; }
.man-step__arrow { margin-left: 4px; color: var(--text-tertiary); transition: transform 0.2s; }
.man-step__arrow.is-open { transform: rotate(90deg); }
.man-step__body { padding: 14px 16px 16px; border-top: 1px solid var(--border-light); background: var(--bg-page); display: flex; flex-direction: column; gap: 14px; }
.man-step__desc { font-size: 13px; color: var(--text-secondary); line-height: 1.6; }
.man-field { display: flex; flex-direction: column; gap: 8px; }
.man-field__label { font-size: 13px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 8px; }
.man-fields { display: flex; gap: 6px; flex-wrap: wrap; }
.man-field-tag { font-size: 12px; background: #fff; border: 1px solid var(--brand-200); color: var(--brand-700); padding: 2px 10px; border-radius: 10px; font-weight: 500; }
.man-next { font-size: 13px; color: var(--text-secondary); background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: var(--radius-sm); padding: 8px 12px; line-height: 1.5; }
.man-howto { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: var(--text-tertiary); background: #fffbeb; border: 1px solid #fde68a; border-radius: var(--radius-sm); padding: 8px 12px; line-height: 1.5; }
.man-howto .el-icon { color: var(--accent-amber); margin-top: 1px; flex-shrink: 0; }

/* API 说明 */
.man-api-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.man-api-card { border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 14px; background: var(--bg-page); }
.man-api-chip { font-size: 11px; font-weight: 700; padding: 2px 10px; border-radius: 10px; display: inline-block; }
.man-api-title { font-size: 14px; font-weight: 700; color: var(--text-primary); margin-top: 8px; }
.man-api-desc { font-size: 12px; color: var(--text-tertiary); line-height: 1.5; margin-top: 6px; }
.man-api-steps { font-size: 11px; color: var(--brand-600); font-family: var(--font-mono, monospace); margin-top: 8px; }

/* 合规策略 */
.man-ps-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.man-ps-card { border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 12px 14px; background: var(--bg-page); }
.man-ps-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.man-ps-name { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.man-ps-mode { font-size: 11px; font-weight: 600; padding: 1px 9px; border-radius: 10px; }
.man-ps-mode.m-platform { background: #e0f2fe; color: #0369a1; }
.man-ps-mode.m-geo { background: #fef3c7; color: #b45309; }
.man-ps-mode.m-green { background: #dcfce7; color: #15803d; }
.man-ps-mode.m-official { background: #ede9fe; color: #6d28d9; }
.man-ps-body { display: flex; flex-direction: column; gap: 5px; }
.man-ps-line { display: flex; gap: 8px; font-size: 12px; line-height: 1.5; }
.man-ps-k { width: 34px; flex-shrink: 0; color: var(--text-tertiary); font-weight: 600; }

/* 闸门 */
.man-gate-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.man-gate-card { border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 14px; }
.man-gate-card--hard { border-color: #fecaca; background: #fef2f2; }
.man-gate-card--geo { border-color: #bbf7d0; background: #f0fdf4; }
.man-gate-card--soft { border-color: var(--border-light); background: var(--bg-page); }
.man-gate-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 10px; display: flex; align-items: center; }
.man-gate-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
.man-gate-list li { font-size: 12px; color: var(--text-secondary); line-height: 1.5; padding-left: 14px; position: relative; }
.man-gate-list li::before { content: '•'; position: absolute; left: 0; color: var(--text-tertiary); }

.expand-enter-active, .expand-leave-active { transition: all 0.2s ease; overflow: hidden; }
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; }
.expand-enter-to, .expand-leave-from { opacity: 1; }

@media (max-width: 1100px) {
  .man-ctx-grid { grid-template-columns: 1fr; }
  .man-api-grid { grid-template-columns: 1fr; }
  .man-gate-grid { grid-template-columns: 1fr; }
}
</style>
