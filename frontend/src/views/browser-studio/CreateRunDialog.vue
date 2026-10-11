<template>
  <el-dialog v-model="visible" title="新建 AI 创作运行" width="780px" top="5vh">
    <!-- 顶部：9 步流水线全景 -->
    <div class="pipe-strip">
      <template v-for="(s, i) in pipelineSteps" :key="i">
        <div class="pipe-node">
          <span class="pipe-no">{{ i + 1 }}</span>
          <span class="pipe-label">{{ s }}</span>
        </div>
        <span v-if="i < pipelineSteps.length - 1" class="pipe-arrow">→</span>
      </template>
    </div>

    <el-alert type="info" :closable="false" show-icon class="wz-alert"
      title="此部件已链接你的内容库"
      description="下面 5 步即可发起一次完整的 AI 创作 → 过审 → 发布运行。步骤 2 可从「关键词选题库 / 客户画像库 / 意图问题库 / 知识库 / 规则库」里挑这篇文章要用的内容；不挑则自动带入系统全部对应内容，且你日后改了库，下次创作也会实时变。" />

    <!-- 步骤 1：目标需求 -->
    <div class="wz-step">
      <div class="wz-step-title"><span class="wz-badge">1</span>这篇文章要达成什么（目标需求）</div>
      <el-input v-model="form.name" placeholder="运行名称（可选，便于在列表里区分）" style="margin-bottom:10px" />
      <el-input v-model="form.subject" type="textarea" :rows="3"
        placeholder="引导 AI 选题方向（可留空，由 AI 基于系统内容自主选定高价值选题）" />
      <div class="chip-row">
        <span class="chip" @click="form.subject='我们这类设备采购前，客户最常问 AI 的 5 个问题'">示例：采购前客户常问 AI 的问题</span>
        <span class="chip" @click="form.subject='用我们方案后，客户最关心的 3 个落地指标'">示例：客户最关心的落地指标</span>
      </div>
    </div>

    <!-- 步骤 2：选内容来源 -->
    <div class="wz-step">
      <div class="wz-step-title"><span class="wz-badge">2</span>这篇文章用哪些内容（从系统库里挑）</div>
      <div class="lib-grid">
        <div class="lib-col">
          <div class="lib-label">关键词（可多选 · 按分组）<span class="lib-tip">决定软文打哪些词</span></div>
          <el-select v-model="form.keyword_ids" multiple filterable placeholder="不挑=自动带入全部关键词" style="width:100%" :loading="libLoading">
            <el-option-group v-for="g in keywordOptionsByGroup" :key="g.id" :label="g.name">
              <el-option v-for="k in g.items" :key="k.id" :label="k.word" :value="k.id" />
            </el-option-group>
          </el-select>
          <el-input v-model="kwSearch" placeholder="搜索关键词" clearable size="small" style="margin-top:8px" />
        </div>
        <div class="lib-col">
          <div class="lib-label">目标客户（客户画像库）<span class="lib-tip">可多选，覆盖多类读者</span></div>
          <el-select v-model="form.target_persona_ids" multiple filterable placeholder="不挑=自动带入系统全部画像" style="width:100%" :loading="libLoading">
            <el-option v-for="t in libOpts.targetPersonas" :key="t.id" :label="`${t.name}（${roleLabel(t.role_type)}）`" :value="t.id" />
          </el-select>
        </div>
        <div class="lib-col">
          <div class="lib-label">意图问题（意图问题库）</div>
          <el-select v-model="form.intent_question_ids" multiple filterable placeholder="不挑=自动带入系统全部意图（按上面画像联动）" style="width:100%" :loading="libLoading">
            <el-option v-for="q in filteredIntentQuestions" :key="q.id" :label="(q.question || '').slice(0, 40)" :value="q.id" />
          </el-select>
        </div>
        <div class="lib-col">
          <div class="lib-label">知识库要点</div>
          <el-select v-model="form.knowledge_item_ids" multiple filterable placeholder="不挑=自动带入全部知识" style="width:100%" :loading="libLoading">
            <el-option v-for="k in libOpts.knowledgeItems" :key="k.id" :label="(k.title || k.name || '').slice(0, 40)" :value="k.id" />
          </el-select>
        </div>
        <div class="lib-col">
          <div class="lib-label">规则库红线</div>
          <el-select v-model="form.rule_ids" multiple filterable placeholder="不挑=自动带入全部启用规则" style="width:100%" :loading="libLoading">
            <el-option v-for="r in libOpts.rules" :key="r.id" :label="`${ruleTypeLabel(r.rule_type)}：${(r.content || '').slice(0, 30)}`" :value="r.id" />
          </el-select>
        </div>
      </div>
      <div class="form-hint">
        这些都是你系统里已经沉淀的内容。挑了 → 这篇只用你挑的；不挑 → 自动用系统当前全部对应内容（<b>你改了库，下一篇会自动跟着变</b>）。开始创作时，这些会作为「背景资料」连同目标需求、创作理念、作品要求、平台要求、AI 搜索要求一起发给 AI。
      </div>
    </div>

    <!-- 步骤 3：发布平台 -->
    <div class="wz-step">
      <div class="wz-step-title"><span class="wz-badge">3</span>发布到哪个平台</div>
      <div class="card-row">
        <div v-for="p in platformOptions" :key="p.value" class="pick-card"
          :class="{ active: form.platform === p.value }" @click="selectPlatform(p)">
          <div class="pick-name">{{ p.label }}</div>
          <div class="pick-desc">{{ p.desc }}</div>
          <div class="pick-mode mode-chip" :class="modeOptionClass(p.mode)">{{ modeOptionText(p.mode) }}</div>
        </div>
      </div>
      <div class="mode-row">
        <span class="mode-label">发布模式</span>
        <el-radio-group v-model="form.publish_mode">
          <el-radio-button label="platform">平台合规模式（中性·标题无品牌·品牌≤2次·带 AIGC 标识）</el-radio-button>
          <el-radio-button label="geo">强品牌 / GEO 模式（品牌突出·被 AI 推荐引用）</el-radio-button>
          <el-radio-button label="green">绿色吸粉模式（纯涨粉·品牌顺带一提≤2次·不软文营销）</el-radio-button>
        </el-radio-group>
        <div class="form-hint">
          内容平台（搜狐/知乎/网易）默认「平台合规模式」，规避软文广告判定；发到官网/自建站自动走「强品牌/GEO + 产出 MDX 代码」；
          「绿色吸粉模式」用于纯自媒体涨粉文章，不以营销为目的，品牌仅在文中自然偶提（≤2 次），提升账号权重与信用分。
        </div>
      </div>
    </div>

    <!-- 步骤 4：AI 引擎 -->
    <div class="wz-step">
      <div class="wz-step-title"><span class="wz-badge">4</span>用哪个 AI 引擎创作</div>
      <div class="card-row">
        <div v-for="e in engineOptions" :key="e.value" class="pick-card"
          :class="{ active: form.ai_engine === e.value }" @click="form.ai_engine = e.value">
          <div class="pick-name">
            {{ e.label }}
            <el-tag v-if="e.recommend" size="small" type="success" effect="dark">推荐</el-tag>
          </div>
          <div class="pick-desc">{{ e.desc }}</div>
        </div>
      </div>
      <div v-if="form.ai_engine === 'doubao'" class="sub-field">
        <div class="sub-label">豆包登录态凭证</div>
        <el-select v-model="form.doubao_credential_id" placeholder="留空则自动回退模拟" clearable style="width:100%">
          <el-option v-for="c in doubaoCreds" :key="c.id" :label="`#${c.id} ${c.note || '豆包cookie'}`" :value="c.id" />
        </el-select>
        <div class="form-hint">在「发布中心 → 凭证」上传 platform='doubao' 的 cookie 后可选；不选则自动回退「模拟演示」。</div>
      </div>
      <div class="expert-team">
        <span class="et-title">多专家协同团队（主编统一协调）：</span>
        <el-tag v-for="x in expertTeam" :key="x.role" size="small" :class="['et-tag', x.tag]">{{ x.role }}</el-tag>
        <el-tooltip v-for="x in expertTeam" :key="'tip-'+x.role" :content="x.desc" placement="top">
          <span :class="['et-dot', x.tag]"></span>
        </el-tooltip>
      </div>
    </div>

    <!-- 步骤 5：发布策略 -->
    <div class="wz-step">
      <div class="wz-step-title"><span class="wz-badge">5</span>发布策略</div>
      <div class="pub-row">
        <el-switch v-model="form.auto_publish" />
        <span class="form-hint">开启则你点「满意，加入内容中心」后自动发布到平台（仍过合规拦截）；否则需再点「发布到平台」</span>
      </div>
      <div class="auto-context">
        <span class="ac-title">本运行会自动带入的系统内容：</span>
        <el-tag v-for="t in autoContextTags" :key="t" size="small" type="info" effect="plain" class="ac-tag">{{ t }}</el-tag>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="creating" @click="onCreate">创建并启动 ▶</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 新建 AI 创作运行（5 步可视化向导）。
 *
 * 拆出来时顺手做的一件事：**它自己拉自己要用的数据**。
 * 原来 `loadLibOptions()`（6 个接口并发）和 `loadOptions()`（豆包凭证）都挂在父组件上，
 * 但只有这个弹窗用得到。放在父组件意味着「打开一次弹窗要惊动整个壳去加载数据」，
 * 也意味着父组件要替弹窗保管 libOpts / libLoading / kwSearch 三份状态。
 * 现在这些都是弹窗自己的事，父组件只知道「用户点了新建」和「创建成功了」。
 *
 * 父组件用法：
 *   <CreateRunDialog ref="createRef" :industry-id="industryId()" @created="onRunCreated" />
 *   createRef.value.open()
 *
 * `created` 事件带新运行的 id，父组件据此刷新列表并选中它。
 */
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  browserStudioApi, platformCredentialApi, keywordGroupApi, keywordApi,
  targetPersonaApi, intentQuestionApi, knowledgeApi, ruleApi,
} from '../../api'
import { PLATFORM_OPTIONS } from '../../constants/platforms'
import {
  ENGINE_OPTIONS as engineOptions,
  PIPELINE_STEPS as pipelineSteps,
  AUTO_CONTEXT_TAGS as autoContextTags,
  EXPERT_TEAM as expertTeam,
  modeOptionText, modeOptionClass, roleLabel, ruleTypeLabel,
} from '../../constants/browserStudio'
// 模式徽标配色 + .pc-tip 等跨组件共用样式。
// ⚠️ 必须在 script 里 import，**不能**在 <style scoped> 里 @import ——
// 后者会把导入的规则也打上 scope 属性，等于把共享样式变成了组件私有，共享就白做了。
import './studio-shared.css'

const props = defineProps({
  /** 当前行业 id；为 0 时后端走「无行业」分支 */
  industryId: { type: Number, default: 0 },
})

const emit = defineEmits(['created'])

const platformOptions = PLATFORM_OPTIONS

const visible = ref(false)
const creating = ref(false)
const doubaoCreds = ref([])

function emptyForm() {
  return {
    name: '', subject: '', platform: 'sohu', publish_mode: 'platform',
    ai_engine: 'deepseek',
    doubao_credential_id: 0,
    auto_publish: false,
    keyword_ids: [], target_persona_ids: [], intent_question_ids: [],
    knowledge_item_ids: [], rule_ids: [],
  }
}

const form = reactive(emptyForm())

// 链接系统内容库：从各库拉取可选清单，用户显式选择这篇文章的内容来源
const libOpts = reactive({
  keywordGroups: [], keywords: [], targetPersonas: [], intentQuestions: [],
  knowledgeItems: [], rules: [],
})
const libLoading = ref(false)
const kwSearch = ref('')

/** 关键词按分组归类（供多选下拉分组展示），并按 kwSearch 过滤 */
const keywordOptionsByGroup = computed(() => {
  const q = (kwSearch.value || '').trim().toLowerCase()
  const groups = []
  for (const g of libOpts.keywordGroups) {
    const ks = libOpts.keywords.filter(k => k.group_id === g.id && (!q || (k.word || '').toLowerCase().includes(q)))
    if (ks.length) groups.push({ id: g.id, name: g.name, color: g.color, items: ks })
  }
  const ungrouped = libOpts.keywords.filter(k => !k.group_id && (!q || (k.word || '').toLowerCase().includes(q)))
  if (ungrouped.length) groups.push({ id: 0, name: '未分组', color: '#94a3b8', items: ungrouped })
  return groups
})

/** 意图问题按已选客户画像过滤（与 Production 流水线一致：不挑=全部；挑了=只显该画像下问题） */
const filteredIntentQuestions = computed(() => {
  const sel = form.target_persona_ids || []
  if (!sel.length) return libOpts.intentQuestions
  return (libOpts.intentQuestions || []).filter(q => q.persona_id != null && sel.includes(q.persona_id))
})

/** 选平台时同步默认发布模式（内容平台→平台合规；官网/自建站→强品牌/GEO），用户可手动覆盖 */
function selectPlatform(p) {
  form.platform = p.value
  // official 平台在后端会强制 geo + mdx 产出，这里把发布模式默认置 geo，避免传非白名单值
  form.publish_mode = (p.mode === 'platform' || p.mode === 'green' || p.mode === 'geo') ? p.mode : 'geo'
}

async function loadLibOptions() {
  const ind = props.industryId
  libLoading.value = true
  try {
    // 六个库各自 catch：某个库挂了不该让整个向导空白（其余库照常可选）
    const [grp, kw, tp, iq, ki, rl] = await Promise.all([
      keywordGroupApi.list(ind).catch(() => ({ data: [] })),
      keywordApi.list(ind).catch(() => ({ data: [] })),
      targetPersonaApi.list(ind).catch(() => ({ data: [] })),
      intentQuestionApi.list(ind).catch(() => ({ data: [] })),
      knowledgeApi.listItems(ind).catch(() => ({ data: [] })),
      ruleApi.list(ind).catch(() => ({ data: [] })),
    ])
    libOpts.keywordGroups = grp.data || []
    libOpts.keywords = kw.data || []
    libOpts.targetPersonas = tp.data || []
    libOpts.intentQuestions = iq.data || []
    libOpts.knowledgeItems = ki.data || []
    libOpts.rules = rl.data || []
  } catch { /* 各库已单独兜底，这里只防 Promise.all 本身抛错 */ }
  finally { libLoading.value = false }
}

async function loadDoubaoCreds() {
  try {
    const pc = await platformCredentialApi.list(props.industryId)
    doubaoCreds.value = (pc.data || []).filter(c => c.platform === 'doubao')
  } catch { /* 凭证列表拉不到不影响新建——不选就回退模拟 */ }
}

function open() {
  Object.assign(form, emptyForm())
  kwSearch.value = ''
  visible.value = true
  loadLibOptions()
  loadDoubaoCreds()
}

async function onCreate() {
  if (creating.value) return
  creating.value = true
  try {
    const res = await browserStudioApi.create({
      name: form.name, subject: form.subject, platform: form.platform,
      industry_id: props.industryId,
      ai_engine: form.ai_engine,
      doubao_credential_id: form.ai_engine === 'doubao' ? form.doubao_credential_id : 0,
      auto_publish: form.auto_publish,
      publish_mode: form.publish_mode,
      keyword_ids: form.keyword_ids,
      target_persona_ids: form.target_persona_ids,
      intent_question_ids: form.intent_question_ids,
      knowledge_item_ids: form.knowledge_item_ids,
      rule_ids: form.rule_ids,
    })
    const id = res?.data?.id
    if (!id) {
      ElMessage.warning('创建失败：未返回运行 id')
      return
    }
    visible.value = false
    await browserStudioApi.start(id)
    const eng = form.ai_engine === 'deepseek' ? 'DeepSeek' : (form.ai_engine === 'doubao' ? '豆包' : '模拟演示')
    ElMessage.success(`已创建并启动（${eng} 引擎，双智能体 10 步流水线）`)
    emit('created', id)
  } catch (e) {
    ElMessage.warning('创建失败：' + (e?.response?.data?.detail || e?.message || e))
  } finally {
    creating.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
/* ⚠️ 这里没有 `.m-geo/.m-platform/.m-green/.m-official` 的配色 ——
   它和运行列表的 `.tag-mode` 是同一套徽标配色，统一放在 studio-shared.css 的 `.mode-chip` 下，
   两边共用一份（原先 .pick-mode 那份漏了 .m-green）。
   本文件只保留 .pick-mode 自己的排版差异。 */

.form-hint { font-size: 11px; color: var(--text-quaternary); margin-left: 8px; }

/* ===== 新建向导可视化 ===== */
.pipe-strip { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; background: var(--brand-50); border: 1px solid var(--brand-100); border-radius: 10px; padding: 10px 12px; margin-bottom: 12px; }
.pipe-node { display: inline-flex; align-items: center; gap: 6px; }
.pipe-no { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: var(--brand-500); color: #fff; font-size: 11px; font-weight: 700; }
.pipe-label { font-size: 12px; color: var(--text-secondary); white-space: nowrap; }
.pipe-arrow { color: var(--brand-300); margin: 0 2px; font-size: 12px; }
.wz-alert { margin-bottom: 12px; }
.wz-step { padding: 12px 14px; border: 1px solid var(--border-light); border-radius: 10px; margin-bottom: 12px; background: var(--bg-card); }
.wz-step-title { font-weight: 600; font-size: 13px; color: var(--text-primary); margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
.wz-badge { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 6px; background: var(--text-primary); color: #fff; font-size: 12px; font-weight: 700; }
.card-row { display: flex; gap: 10px; flex-wrap: wrap; }
.pick-card { flex: 1; min-width: 150px; border: 1.5px solid var(--border-light); border-radius: 10px; padding: 12px; cursor: pointer; transition: all .16s; background: #fff; }
.pick-card:hover { border-color: var(--brand-300); }
.pick-card.active { border-color: var(--brand-500); background: var(--brand-50); box-shadow: 0 0 0 3px var(--brand-100); }
.pick-name { font-weight: 600; font-size: 13px; color: var(--text-primary); display: flex; align-items: center; gap: 6px; }
.pick-desc { margin-top: 6px; font-size: 12px; color: var(--text-tertiary); line-height: 1.5; }
.pick-mode { margin-top: 6px; display: inline-block; }
.sub-field { margin-top: 10px; }
.sub-label { font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }
.chip-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.chip { font-size: 12px; color: var(--brand-600); background: var(--brand-50); border: 1px dashed var(--brand-300); border-radius: 999px; padding: 3px 10px; cursor: pointer; transition: all .16s; }
.chip:hover { background: var(--brand-100); }
.pub-row { display: flex; align-items: center; gap: 10px; }
.auto-context { margin-top: 12px; padding: 10px 12px; background: var(--slate-50); border-radius: 8px; }
.ac-title { font-size: 12px; color: var(--text-secondary); font-weight: 600; }
.ac-tag { margin: 4px 4px 0 0; }

/* ===== 步骤 2：内容来源选择网格 ===== */
.lib-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 16px; }
.lib-col { display: flex; flex-direction: column; }
.lib-label { font-size: 12px; color: var(--text-secondary); font-weight: 600; margin-bottom: 6px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.lib-tip { font-size: 11px; color: var(--text-tertiary); font-weight: 400; }
@media (max-width: 720px) { .lib-grid { grid-template-columns: 1fr; } }

/* ===== 发布模式选择行 ===== */
.mode-row { margin-top: 12px; display: flex; flex-direction: column; gap: 6px; }
.mode-row .mode-label { font-size: 13px; font-weight: 600; color: var(--text-secondary); }

/* ===== 专家团队 =====
   角色配色（.agent-planner / .agent-writer / .agent-compliance / .agent-geo / .agent-fact）
   与壳里的步骤行角标、以及 AutomationStudio 的 `.dot.agent-*` 用的是同一组色值，
   目前三处各存一份。合并它们需要先确认不会串到 AutomationStudio，
   不在本次拆分范围内 —— 这里先就地保留，改动时注意三处同步。 */
.expert-team { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 12px; padding: 10px 12px; background: var(--bg-page); border: 1px dashed var(--border-light); border-radius: var(--radius-sm); }
.et-title { font-size: 12px; color: var(--text-tertiary); font-weight: 600; }
.et-tag { border: none; }
.et-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-left: 2px; cursor: help; }
.et-tag.agent-planner { background: #ede9fe; color: #6d28d9; }
.et-tag.agent-writer { background: #e0f2fe; color: #0369a1; }
.et-tag.agent-compliance { background: #fee2e2; color: #b91c1c; }
.et-tag.agent-geo { background: #dcfce7; color: #15803d; }
.et-tag.agent-fact { background: #fef9c3; color: #a16207; }
.et-dot.agent-planner { background: #6d28d9; }
.et-dot.agent-writer { background: #0369a1; }
.et-dot.agent-compliance { background: #b91c1c; }
.et-dot.agent-geo { background: #15803d; }
.et-dot.agent-fact { background: #a16207; }
</style>
