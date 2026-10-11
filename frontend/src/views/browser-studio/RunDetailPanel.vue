<template>
  <section class="run-detail" v-if="run">
    <div class="detail-head">
      <div>
        <h2 class="detail-title">{{ run.name }}</h2>
        <p class="detail-sub">
          目标需求：{{ run.subject || '（未填写，AI 自主选题）' }}
          <el-tag size="small" class="muted">{{ engineLabel(run.ai_engine || (run.mock_doubao ? 'mock' : 'deepseek')) }}</el-tag>
          <el-tag size="small" :type="runModeType(run)">{{ runModeTag(run).text }}</el-tag>
          <el-tag v-if="run.auto_publish" size="small" type="warning">自动发布</el-tag>
          <el-tag v-if="run.confirmed" size="small" type="success">已入内容中心</el-tag>
        </p>
      </div>
      <div class="detail-actions">
        <el-button
          v-if="run.status === 'await_confirm'"
          type="success" @click="emit('confirm')"
        >✓ 满意，加入内容中心</el-button>
        <el-button
          v-if="canPublish && run.output_format !== 'mdx'"
          type="primary" @click="emit('publish')"
        >发布到平台</el-button>
        <el-tag v-if="run.output_format === 'mdx'" type="info" effect="plain" class="mdx-ready-tag">
          官网 MDX 已就绪 · 复制上方代码粘贴至官网 Astro 项目
        </el-tag>
        <el-button
          v-if="run.status !== 'running' && run.status !== 'await_confirm'"
          :type="run.status === 'failed' ? 'warning' : 'primary'"
          @click="emit('start')"
        >{{ restartLabel }}</el-button>
        <el-button v-if="run.status === 'running'" type="info" loading>运行中…</el-button>
        <el-button :icon="Delete" @click="emit('delete')">删除</el-button>
      </div>
    </div>

    <!-- 9 步流水线 -->
    <div class="pipeline">
      <div
        v-for="(s, i) in run.steps"
        :key="s.id"
        class="step"
        :class="['step--' + s.status]"
      >
        <div class="step__rail">
          <div class="step__dot"></div>
          <div v-if="i < run.steps.length - 1" class="step__line"></div>
        </div>
        <div class="step__main">
          <div class="step__row">
            <span class="step__no">步骤 {{ s.step_no }}</span>
            <span class="step__title">{{ s.title }}</span>
            <span class="agent-badge" :class="'agent-' + (s.agent || 'system')">{{ agentLabel(s.agent) }}</span>
            <el-tag :type="stepType(s.status)" size="small">{{ stepLabel(s.status) }}</el-tag>
            <span v-if="s.attempts" class="step__attempts">重试 {{ s.attempts }} 次</span>
            <div class="step__ops">
              <el-button
                v-if="s.status === 'failed' && s.step_key === 'publish'"
                size="small" type="warning" @click="emit('retryPublish')"
              >重试发布</el-button>
              <el-button
                v-if="s.status === 'failed' && s.step_key !== 'publish'"
                size="small" type="danger" @click="emit('retry')"
              >重跑</el-button>
              <el-button
                v-if="stepOutput(s.step_key) || s.result_json || s.log"
                size="small" text @click="toggleStep(s)"
              >{{ expanded[s.id] ? '收起' : '看 AI 原文' }}</el-button>
            </div>
          </div>
          <div v-if="s.status === 'failed' && s.last_error" class="step__err">{{ s.last_error }}</div>
          <div v-if="expanded[s.id]" class="step__detail">
            <div v-if="stepOutput(s.step_key)" class="step__aiout">
              <div class="step__aiout-title">本步骤 AI 返回原文（可回溯 / 复制）</div>
              <pre>{{ stepOutput(s.step_key) }}</pre>
              <el-button size="small" :icon="DocumentCopy" @click="copyText(stepOutput(s.step_key), '本步骤AI原文')">复制</el-button>
            </div>
            <div v-if="s.log" class="step__log"><pre>{{ s.log }}</pre></div>
            <div v-if="s.result_json" class="step__result">
              <div class="step__result-title">步骤结果（JSON）</div>
              <pre>{{ pretty(s.result_json) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ 步骤透明日志 / 创作对话（P2-2 可视化） ============ -->
    <div class="step-log-wrap" v-if="run.steps && run.steps.length">
      <el-tabs v-model="logTab" class="studio-tabs">
        <el-tab-pane label="步骤透明日志" name="logs">
          <el-divider>每步「发送了什么 / 等多久 / 取到什么 / 下一步」（可直接复制给网页 AI 复现）</el-divider>
          <StepLogPanel :run-id="run.id" :running="run.status === 'running'" />
        </el-tab-pane>
        <el-tab-pane label="创作对话 · 主编↔写手" name="conv">
          <ConversationPanel :run-id="run.id" :running="run.status === 'running'" />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- ============ AI 逐轮产出（每轮 AI 返回的内容都可见） ============ -->
    <div class="rounds" v-if="hasAnyStage">
      <el-divider>AI 逐轮产出（多专家协同：主编📋 总协调 · 写手✍️ 落地 · 合规官/GEO优化师/数据核查员 由主编评审把关，每一轮都可见）</el-divider>

      <div class="round-card" v-if="run.clarified_brief">
        <div class="round-card__head"><span class="round-badge b0">①b</span> 主编·创作简报（明晰选题）
          <el-tag size="small" class="agent-planner-mini">主编</el-tag>
          <el-button size="small" text :icon="DocumentCopy" @click="copyText(run.clarified_brief, '创作简报')">复制</el-button>
        </div>
        <pre class="round-text">{{ run.clarified_brief }}</pre>
      </div>

      <div class="round-card" v-if="run.outline_content">
        <div class="round-card__head"><span class="round-badge b1">①</span> 选题大纲 <el-button size="small" text :icon="DocumentCopy" @click="copyText(run.outline_content, '大纲')">复制</el-button></div>
        <pre class="round-text">{{ run.outline_content }}</pre>
      </div>
      <div class="round-card" v-if="run.draft_content">
        <div class="round-card__head"><span class="round-badge b2">②</span> 初稿 <el-button size="small" text :icon="DocumentCopy" @click="copyText(run.draft_content, '初稿')">复制</el-button></div>
        <pre class="round-text">{{ run.draft_content }}</pre>
      </div>
      <div class="round-card" v-if="run.rewrite_content">
        <div class="round-card__head"><span class="round-badge b3">③</span> 去AI味精修稿 <el-button size="small" text :icon="DocumentCopy" @click="copyText(run.rewrite_content, '精修稿')">复制</el-button></div>
        <pre class="round-text">{{ run.rewrite_content }}</pre>
      </div>
      <div class="round-card" v-if="run.geo_content">
        <div class="round-card__head"><span class="round-badge b4">④</span> GEO 强化终稿（原始） <el-button size="small" text :icon="DocumentCopy" @click="copyText(run.geo_content, 'GEO终稿')">复制</el-button></div>
        <pre class="round-text">{{ run.geo_content }}</pre>
      </div>
      <div class="round-card round-card--revise" v-if="reviseList.length">
        <div class="round-card__head"><span class="round-badge b5">⑦</span> 闭环整改（{{ reviseList.length }} 轮：主编指令 → 写手改写 → 主编二次评语）</div>
        <div class="revise-item" v-for="(rd, i) in reviseList" :key="i">
          <div class="revise-item__h">
            <span class="round-badge b5">⑦</span> 第 {{ rd.round }} 轮
            <span class="revise-meta">整改前 {{ rd.before_len }} 字 → 写手改后 {{ rd.after_len }} 字 · GEO {{ rd.geo_score }} · {{ rd.gate_pass ? '已达标' : '仍待优化' }}</span>
            <el-button size="small" text :icon="DocumentCopy" @click="copyText(rd.after, `第${rd.round}轮改写结果`)">复制</el-button>
          </div>
          <div class="revise-role" v-if="rd.before">
            <div class="revise-role__tag agent-writer">✍️ 整改前（写手原稿）</div>
            <pre class="round-text revise-before">{{ rd.before }}</pre>
          </div>
          <div class="revise-role">
            <div class="revise-role__tag agent-planner">📋 主编·整改指令（为什么改 / 改什么）</div>
            <pre class="round-text">{{ rd.planner_directives }}</pre>
          </div>
          <div class="revise-role">
            <div class="revise-role__tag agent-writer">✍️ 写手·改写结果（执行主编指令后）</div>
            <pre class="round-text">{{ rd.after }}</pre>
          </div>
          <div class="revise-role" v-if="rd.editor_review">
            <div class="revise-role__tag agent-planner">📋 主编·本轮二次评语</div>
            <pre class="round-text revise-review">{{ rd.editor_review }}</pre>
          </div>
          <div class="revise-item__issues">
            <span v-for="(it, j) in rd.issues" :key="j" class="issue-chip">{{ it }}</span>
          </div>
        </div>
      </div>
      <!-- 一次过审 · 无需整改 -->
      <div class="round-card round-card--pass" v-if="!reviseList.length && run.review_result">
        <div class="round-card__head"><span class="round-badge b4">⑦</span> 闭环整改：一次过审，无需整改</div>
        <div class="revise-pass-hint">终稿在第⑥步评审中已通过综合闸门（平台过审 + GEO 达标），无需触发整改循环。</div>
      </div>
    </div>

    <!-- ============ 平台过审 + GEO 评分卡 ============ -->
    <div class="review-card" v-if="review">
      <el-divider>平台过审 + GEO 评分（第⑥步自检）</el-divider>
      <div class="review-head">
        <div class="review-gate">
          <div class="gate-pill" :class="review.gate_pass ? 'pass' : 'fail'">
            {{ review.gate_pass ? '综合通过' : '需整改' }}
          </div>
          <div class="gate-sub">
            <span>平台过审：<b :class="review.compliance_pass ? 'good' : 'warn'">{{ review.compliance_pass ? '通过' : '未通过' }}</b></span>
            <span>GEO 评分：<b :class="review.geo_score >= 70 ? 'good' : 'warn'">{{ review.geo_score }}</b> / 100（≥70 达标）</span>
          </div>
        </div>
        <div class="review-diagnosis" v-if="geoDiag" :style="{ borderColor: geoDiag.color }">
          <div class="review-diagnosis__label" :style="{ color: geoDiag.color }">{{ geoDiag.label }}</div>
          <div class="review-diagnosis__desc">{{ geoDiag.desc }}</div>
        </div>
      </div>

      <!-- 主编自然语言评语 -->
      <div class="editor-review" v-if="run.editor_review">
        <div class="editor-review__title">📋 主编·评审评语（汇总合规官 / GEO优化师 / 数据核查员 意见，人话版：为什么没过 / 主要差距在哪）</div>
        <pre class="editor-review__text">{{ run.editor_review }}</pre>
      </div>

      <!-- GEO 六维 + 心智温度 -->
      <div class="dims" v-if="geoDims">
        <div class="dim" v-for="(v, k) in geoDims" :key="k">
          <div class="dim__top"><span>{{ dimLabel(k) }}</span><span class="dim__val">{{ v }}</span></div>
          <div class="dim__bar"><i :style="{ width: dimPct(k, v) + '%', background: dimColor(k, v) }"></i></div>
        </div>
      </div>
      <div class="mind" v-if="mindDims">
        <div class="mind__title">心智温度（人感）：{{ mindScore }}</div>
        <div class="dims dims--mind">
          <div class="dim" v-for="(v, k) in mindDims" :key="k">
            <div class="dim__top"><span>{{ mindLabel(k) }}</span><span class="dim__val">{{ v }}</span></div>
            <div class="dim__bar"><i :style="{ width: Math.min(v, 25) / 25 * 100 + '%', background: v >= 6 ? '#10b981' : '#f59e0b' }"></i></div>
          </div>
        </div>
      </div>

      <div class="review-issues" v-if="review.issues && review.issues.length">
        <div class="review-issues__title">可执行整改清单（主编按专家归属下达，已回写 AI 本轮整改）</div>
        <ul>
          <li v-for="(it, i) in review.issues" :key="i" :class="it.startsWith('[平台合规') ? 'lvl-a' : 'lvl-b'">{{ it }}</li>
        </ul>
      </div>
    </div>

    <!-- ============ 终稿（可复制 · 双格式切换） ============ -->
    <div class="result-block" v-if="run.final_content">
      <!-- 官网 / 自建站：MDX 代码产出（可复制） -->
      <template v-if="run.output_format === 'mdx'">
        <el-divider>官网 MDX 产出（可复制代码 · 直接粘贴到 Astro 项目）</el-divider>
        <div class="mdx-hint">
          产出形态：<b>MDX 代码</b>（官网/自建站）。按固定模板生成，包含 Frontmatter + 六段结构 + 4 列数据对比表 + 引用块，
          <b>严禁 &lt;Image /&gt; 组件与 emoji</b>，严肃工业风。封面图文件名已按约定路径给出，请将配图放到对应目录后发布。
        </div>
        <!-- 文件名（.mdx）可复制 -->
        <div class="copy-row">
          <div class="copy-label">文件名</div>
          <div class="copy-body">
            <div class="mdx-fname">{{ mdxFileName || '（运行后生成 .mdx 文件名）' }}</div>
            <el-button size="small" :icon="DocumentCopy" @click="copyText(mdxFileName, '.mdx 文件名')" :disabled="!mdxFileName">复制文件名</el-button>
          </div>
        </div>
        <!-- 配图文件名列表可复制 -->
        <div class="copy-row" v-if="mdxImages.length">
          <div class="copy-label">配图文件名</div>
          <div class="copy-body">
            <div class="mdx-imglist">
              <code v-for="(img, i) in mdxImages" :key="i" class="mdx-img">{{ img }}</code>
            </div>
            <el-button size="small" :icon="DocumentCopy" @click="copyText(mdxImages.join('\n'), '配图文件名')">复制全部配图文件名</el-button>
          </div>
        </div>
        <!-- 封面图（frontmatter cover 字段） -->
        <div class="copy-row">
          <div class="copy-label">封面图</div>
          <div class="copy-body">
            <div class="mdx-cover">{{ mdxCoverImage || '（见下方 MDX frontmatter 的 cover 字段）' }}</div>
            <el-button size="small" :icon="DocumentCopy" @click="copyText(mdxCoverImage, '封面图文件名')" :disabled="!mdxCoverImage">复制图片文件名</el-button>
          </div>
        </div>
        <div class="copy-row">
          <div class="copy-label">MDX</div>
          <div class="copy-body">
            <pre class="final-content-md mdx-code">{{ run.final_content }}</pre>
            <el-button size="small" :icon="DocumentCopy" @click="copyText(run.final_content, 'MDX 代码')">复制 MDX 代码</el-button>
          </div>
        </div>

        <!-- 自动化发布提示词（官网 MDX 模板 · 有序存放） -->
        <el-collapse v-if="run.publish_prompt" class="briefing-collapse">
          <el-collapse-item title="📦 自动化发布提示词（官网 MDX 模板 · 专门部件有序存放）" name="pubprompt">
            <div class="briefing-sub">下面这份提示词是「官网/自建站」模式的自动化发布提示词，已专门存放在平台的 publish_prompt 字段，编排时自动注入主编工作流，确保每次官网产出都遵循同一套 MDX 规范。</div>
            <pre class="briefing-pre">{{ run.publish_prompt }}</pre>
            <el-button size="small" :icon="DocumentCopy" @click="copyText(run.publish_prompt, '自动化发布提示词')">复制自动化发布提示词</el-button>
          </el-collapse-item>
        </el-collapse>
      </template>

      <!-- 内容平台 / 绿色吸粉：常规文章（Markdown / 纯文本 双格式切换） -->
      <template v-else>
        <el-divider>最终文章（可复制 · 双格式切换）</el-divider>
        <div class="fmt-toggle">
          <el-radio-group v-model="finalFormat" size="small">
            <el-radio-button label="markdown">Markdown 格式（AI 搜索友好）</el-radio-button>
            <el-radio-button label="plain">纯文本格式（可直接复制）</el-radio-button>
          </el-radio-group>
        </div>
        <div class="copy-row">
          <div class="copy-label">标题</div>
          <div class="copy-body">
            <div class="final-title">{{ run.final_title }}</div>
            <el-button size="small" :icon="DocumentCopy" @click="copyText(run.final_title, '标题')">复制标题</el-button>
          </div>
        </div>
        <div class="copy-row">
          <div class="copy-label">正文</div>
          <div class="copy-body">
            <pre v-if="finalFormat === 'markdown'" class="final-content-md">{{ run.final_content }}</pre>
            <pre v-else class="final-content-plain">{{ finalContentPlain }}</pre>
            <div class="copy-hint" v-if="finalFormat === 'markdown'">已含 #/## 标题、- 列表、**加粗**、FAQ 小节，便于 AI 检索引用与一键发布到支持 Markdown 的平台。</div>
            <div class="copy-hint" v-else>已转换为纯文本格式，去掉了 Markdown 标记但保留段落结构，可直接复制到不支持 Markdown 的平台发布。</div>
            <el-button size="small" :icon="DocumentCopy" @click="copyText(finalFormat === 'markdown' ? run.final_content : finalContentPlain, '正文')">复制正文</el-button>
          </div>
        </div>
      </template>

      <div class="result-links">
        <el-tag v-if="run.content_asset_id" type="success" effect="plain">已存档 · 内容资产 #{{ run.content_asset_id }}</el-tag>
        <el-tag v-if="run.sohu_job_id" :type="jobTagType(run)" effect="plain">
          发布任务 #{{ run.sohu_job_id }} · {{ jobStatusText(run) }}
        </el-tag>
        <a v-if="run.sohu_job_id && sohuUrl(run)" :href="sohuUrl(run)" target="_blank" class="result-url">查看发布链接 ↗</a>
      </div>

      <!-- 派发给 AI 的总指令 + 背景资料 -->
      <el-collapse class="briefing-collapse">
        <el-collapse-item title="查看派发给 AI 的「总指令 + 整合好的全部背景资料」" name="briefing">
          <div class="briefing-section">
            <div class="briefing-sub">① 选题大纲阶段指令</div>
            <pre class="briefing-pre">{{ (run.stage_prompts||{}).outline }}</pre>
            <div class="briefing-sub">② 初稿阶段指令</div>
            <pre class="briefing-pre">{{ (run.stage_prompts||{}).draft }}</pre>
            <div class="briefing-sub">③ 去AI味精修阶段指令</div>
            <pre class="briefing-pre">{{ (run.stage_prompts||{}).depolish }}</pre>
            <div class="briefing-sub">④ GEO强化 + 过审阶段指令（含 FINAL 契约）</div>
            <pre class="briefing-pre">{{ (run.stage_prompts||{}).geo }}</pre>
            <el-button size="small" :icon="DocumentCopy" @click="copyText(allStagePrompts, '全部阶段指令')">复制全部阶段指令</el-button>

            <div class="briefing-sub">⑤ 整合好的全部背景资料（目标需求 / 品牌资产 / 平台 / 账号人设 / 知识库 / 关键词 / 规则库 / 客户画像 + 意图问题）</div>
            <pre class="briefing-pre">{{ run.briefing }}</pre>
            <el-button size="small" :icon="DocumentCopy" @click="copyText(run.briefing, '背景资料')">复制背景资料</el-button>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
    <div v-else class="result-empty">
      <el-icon><DocumentDelete /></el-icon>
      <span>终稿尚未生成（运行完成后此处显示 AI 产出文章，且每轮 AI 返回都可在上方「AI 逐轮产出」中查看）</span>
    </div>
  </section>

  <section class="run-detail run-detail--empty" v-else>
    <el-empty description="选择左侧运行查看详情" />
  </section>
</template>

<script setup>
/**
 * 浏览器工作室 —— 右侧「运行详情」面板。
 *
 * 这是工作室最大的一块展示逻辑：9 步流水线、逐轮产出、过审评分卡、终稿复制区、
 * 派发给 AI 的总指令/背景资料。全部是「把一条运行渲染出来」，因此整块搬进来。
 *
 * 边界（和壳的分工）：
 *   - 本组件**不改运行状态、不轮询**。它只 `emit` 用户意图：
 *     confirm / publish / start / retry / retryPublish / delete。
 *     真正的请求 + 轮询 + 列表刷新都留在壳里 —— 那些是「跨面板的编排」，不属于详情展示。
 *   - 空状态（未选中运行）也归本组件：右栏本来就是「要么显示详情，要么提示去左边选」。
 *     这样 `.run-detail` 系列样式只需存在一处。
 *
 * 组件恒挂载（壳不写 v-if），靠内部 `run` 是否为空切换；因此 `logTab` / `expanded` /
 * `finalFormat` 这些交互状态在切换运行之间会保留 —— 与拆分前行为一致。
 */
import { ref, reactive, computed } from 'vue'
import { Delete, DocumentDelete, DocumentCopy } from '@element-plus/icons-vue'
import StepLogPanel from '../../components/StepLogPanel.vue'
import ConversationPanel from '../../components/ConversationPanel.vue'
import { copyText } from '../../utils/clipboard'
import { markdownToPlain } from '../../utils/markdown'
import {
  agentLabel, engineLabel, stepLabel, stepType,
  runModeTag, runModeType,
  dimLabel, mindLabel, dimPct, dimColor,
} from '../../constants/browserStudio'

const props = defineProps({
  /** 当前选中的运行详情对象；为空表示未选中 */
  run: { type: Object, default: null },
})

const emit = defineEmits(['confirm', 'publish', 'start', 'retry', 'retryPublish', 'delete'])

// 交互状态（只影响本面板的展开/页签/格式切换）
const logTab = ref('logs')
const expanded = reactive({})
const finalFormat = ref('markdown')

// ============ 计算属性 ============
const review = computed(() => {
  const r = props.run && props.run.review_result
  return (r && Object.keys(r).length) ? r : null
})
const geoObj = computed(() => (review.value && review.value.geo) || null)
const geoDims = computed(() => (geoObj.value && geoObj.value.dimensions) || null)
const geoDiag = computed(() => (geoObj.value && geoObj.value.diagnosis) || null)
const mindObj = computed(() => (geoObj.value && geoObj.value.mind_resonance) || null)
const mindDims = computed(() => (mindObj.value && mindObj.value.dimensions) || null)
const mindScore = computed(() => (mindObj.value && mindObj.value.score) || 0)
const reviseList = computed(() => {
  const rr = props.run && props.run.revise_rounds
  return Array.isArray(rr) ? rr : []
})
const hasAnyStage = computed(() =>
  props.run && (props.run.outline_content || props.run.draft_content ||
    props.run.rewrite_content || props.run.geo_content || reviseList.value.length)
)
const canPublish = computed(() => {
  const s = props.run
  if (!s) return false
  return !!s.confirmed && !s.sohu_job_id && s.status !== 'running'
})
const restartLabel = computed(() => {
  const s = props.run && props.run.status
  if (s === 'created') return '启动'
  if (s === 'await_confirm') return '重跑'
  return '重新启动'
})
const allStagePrompts = computed(() => {
  const sp = (props.run && props.run.stage_prompts) || {}
  return ['【① 选题大纲】', sp.outline, '\n【② 初稿】', sp.draft, '\n【③ 去AI味精修】', sp.depolish, '\n【④ GEO强化+过审】', sp.geo, '\n【整改】', sp.revise].filter(Boolean).join('\n\n')
})

// Markdown → 纯文本（实现已抽到 utils/markdown.js，可被其它页面复用）
const finalContentPlain = computed(() => markdownToPlain((props.run && props.run.final_content) || ''))

// 从 MDX frontmatter 中解析封面图文件名（约定路径 @/assets/news/industry/xingwen/xxx.jpg）
const mdxCoverImage = computed(() => {
  const t = (props.run && props.run.final_content) || ''
  const m = t.match(/cover:\s*['"]?([^\n'"]+)['"]?/)
  return m ? m[1].trim() : ''
})
// 后端解析出的 .mdx 文件名（可直接复制用于官网 Astro 项目）
const mdxFileName = computed(() => ((props.run && props.run.mdx_filename) || '').trim())
// 后端解析出的建议配图文件名列表（JSON 数组）
const mdxImages = computed(() => {
  const v = props.run && props.run.mdx_images
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v) {
    try { const p = JSON.parse(v); return Array.isArray(p) ? p : [] } catch (e) { return [] }
  }
  return []
})

// ============ 展示辅助 ============
function toggleStep(s) {
  expanded[s.id] = !expanded[s.id]
}

// 步骤 → 该步骤 AI 返回原文（逐轮可见）
function stepOutput(key) {
  const s = props.run
  if (!s) return ''
  if (key === 'clarify') return s.clarified_brief
  if (key === 'outline') return s.outline_content
  if (key === 'draft') return s.draft_content
  if (key === 'depolish') return s.rewrite_content
  if (key === 'geo') return s.geo_content
  if (key === 'review') return s.editor_review || ''
  return ''
}

function jobStatusText(r) {
  const pub = (r.steps || []).find(s => s.step_key === 'publish')
  if (pub && pub.result_json) {
    try { return JSON.parse(pub.result_json).status || '' } catch (e) {}
  }
  return ''
}
function jobTagType(r) {
  const t = jobStatusText(r)
  return { published: 'success', failed: 'danger', approved: 'warning', publishing: 'primary' }[t] || 'info'
}
function sohuUrl(r) {
  const pub = (r.steps || []).find(s => s.step_key === 'publish')
  if (pub && pub.result_json) {
    try { return JSON.parse(pub.result_json).url || '' } catch (e) {}
  }
  return ''
}
function pretty(jsonStr) {
  try { return JSON.stringify(JSON.parse(jsonStr), null, 2) } catch (e) { return jsonStr }
}
</script>

<style scoped>
.run-detail { flex: 1; background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-lg); padding: 20px; overflow-y: auto; }
.run-detail--empty { display: flex; align-items: center; justify-content: center; }
.detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.detail-title { margin: 0; font-size: 18px; color: var(--text-primary); }
.detail-sub { margin: 6px 0 0; font-size: 13px; color: var(--text-tertiary); }
.detail-sub .el-tag { margin-left: 6px; }
.detail-actions { display: flex; gap: 8px; flex-shrink: 0; flex-wrap: wrap; }

.pipeline { margin-top: 18px; }
.step { display: flex; gap: 12px; }
.step__rail { display: flex; flex-direction: column; align-items: center; width: 20px; }
.step__dot { width: 14px; height: 14px; border-radius: 50%; margin-top: 4px; background: var(--slate-300); border: 2px solid #fff; box-shadow: 0 0 0 2px var(--slate-300); flex-shrink: 0; }
.step--running .step__dot { background: var(--brand-500); box-shadow: 0 0 0 2px var(--brand-300); animation: pulse 1.2s infinite; }
.step--done .step__dot { background: var(--accent-emerald); box-shadow: 0 0 0 2px var(--emerald-300); }
.step--failed .step__dot { background: var(--red-500); box-shadow: 0 0 0 2px var(--red-300); }
.step__line { flex: 1; width: 2px; background: var(--border-light); margin: 4px 0; }
.step__main { flex: 1; padding-bottom: 16px; }
.step__row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.step__no { font-size: 12px; color: var(--text-quaternary); font-weight: 600; }
.step__title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.agent-badge { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 10px; white-space: nowrap; }
.agent-planner { background: #ede9fe; color: #6d28d9; }
.agent-writer { background: #e0f2fe; color: #0369a1; }
.agent-dual { background: #fef3c7; color: #b45309; }
.agent-system { background: #f1f5f9; color: #475569; }
.agent-planner-mini { background: #ede9fe; color: #6d28d9; border: none; }
.agent-compliance { background: #fee2e2; color: #b91c1c; }
.agent-geo { background: #dcfce7; color: #15803d; }
.agent-fact { background: #fef9c3; color: #a16207; }
.step__attempts { font-size: 11px; color: var(--text-tertiary); }
.step__ops { margin-left: auto; display: flex; gap: 6px; }
.step__err { margin-top: 6px; font-size: 12px; color: var(--red-500); background: var(--red-50); padding: 6px 10px; border-radius: var(--radius-sm); }
.step__detail { margin-top: 8px; }
.step__aiout { background: var(--bg-page); border: 1px solid var(--brand-200, #bfdbfe); border-radius: var(--radius-sm); padding: 10px; margin-bottom: 8px; }
.step__aiout-title { font-size: 12px; color: var(--brand-600); margin-bottom: 4px; font-weight: 600; }
.step__aiout pre, .step__log pre, .step__result pre { background: var(--bg-page); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 10px; font-size: 12px; color: var(--text-secondary); white-space: pre-wrap; word-break: break-all; max-height: 280px; overflow: auto; margin: 0; }
.step__result-title { font-size: 12px; color: var(--text-tertiary); margin: 8px 0 4px; }

.rounds { margin-top: 6px; }
.round-card { border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 12px 14px; margin-bottom: 12px; background: var(--bg-page); }
.round-card--revise { background: #fff7ed; border-color: #fed7aa; }
.round-card__head { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px; }
.round-card__head .el-button { margin-left: auto; }
.round-badge { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; color: #fff; font-size: 12px; font-weight: 700; }
.round-badge.b1 { background: #6366f1; } .round-badge.b2 { background: #0ea5e9; } .round-badge.b3 { background: #10b981; }
.round-badge.b4 { background: #f59e0b; } .round-badge.b5 { background: #ef4444; } .round-badge.b0 { background: #7c3aed; }
.round-text { background: #fff; border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 10px 12px; font-size: 13px; line-height: 1.7; color: var(--text-primary); white-space: pre-wrap; word-break: break-word; max-height: 360px; overflow: auto; margin: 0; }
.revise-item { border-top: 1px dashed #fdba74; padding: 10px 0; }
.revise-item:first-of-type { border-top: none; }
.revise-item__h { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-secondary); font-weight: 700; }
.revise-meta { font-size: 11px; color: var(--text-tertiary); font-weight: 500; }
.revise-role { margin-top: 8px; }
.revise-role__tag { display: inline-block; font-size: 11px; font-weight: 700; padding: 2px 10px; border-radius: 10px; margin-bottom: 4px; }
.revise-role .round-text { max-height: 240px; }
.revise-review { background: #faf5ff; border-color: #e9d5ff; }
.revise-before { background: #fffbeb; border-color: #fde68a; max-height: 200px; }
.revise-item__issues { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.issue-chip { font-size: 11px; background: #ffedd5; color: #c2410c; padding: 2px 8px; border-radius: 10px; }
.round-card--pass { background: #ecfdf5; border-color: #a7f3d0; }
.revise-pass-hint { font-size: 13px; color: #059669; line-height: 1.6; padding: 8px 0; }
.editor-review { margin-top: 12px; background: #faf5ff; border: 1px solid #e9d5ff; border-radius: var(--radius-sm); padding: 10px 12px; }
.editor-review__title { font-size: 12px; font-weight: 700; color: #6d28d9; margin-bottom: 4px; }
.editor-review__text { background: #fff; border: 1px solid #e9d5ff; border-radius: var(--radius-sm); padding: 10px 12px; font-size: 13px; line-height: 1.7; color: var(--text-primary); white-space: pre-wrap; word-break: break-word; max-height: 220px; overflow: auto; margin: 0; font-family: inherit; }

.review-card { margin-top: 6px; }
.review-head { display: flex; gap: 16px; flex-wrap: wrap; align-items: stretch; }
.review-gate { display: flex; flex-direction: column; gap: 8px; }
.gate-pill { align-self: flex-start; font-size: 14px; font-weight: 700; padding: 6px 16px; border-radius: 20px; }
.gate-pill.pass { background: var(--emerald-50, #ecfdf5); color: var(--accent-emerald); }
.gate-pill.fail { background: var(--red-50, #fef0f0); color: var(--red-600); }
.gate-sub { display: flex; flex-direction: column; gap: 2px; font-size: 13px; color: var(--text-tertiary); }
.gate-sub b.good { color: var(--accent-emerald); } .gate-sub b.warn { color: var(--amber-500); }
.review-diagnosis { flex: 1; min-width: 220px; border: 1px solid var(--border-light); border-left-width: 4px; border-radius: var(--radius-sm); padding: 8px 12px; }
.review-diagnosis__label { font-size: 14px; font-weight: 700; }
.review-diagnosis__desc { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; line-height: 1.6; }

.dims { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px 16px; margin-top: 12px; }
.dims--mind { grid-template-columns: repeat(5, 1fr); }
.dim__top { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-secondary); margin-bottom: 3px; }
.dim__val { font-weight: 700; }
.dim__bar { height: 7px; background: var(--bg-mute, #f1f5f9); border-radius: 4px; overflow: hidden; }
.dim__bar i { display: block; height: 100%; border-radius: 4px; transition: width .4s; }
.mind { margin-top: 12px; }
.mind__title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }

.review-issues { margin-top: 12px; }
.review-issues__title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px; }
.review-issues ul { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 4px; }
.review-issues li { font-size: 13px; line-height: 1.6; }
.review-issues li.lvl-a { color: var(--red-600); }
.review-issues li.lvl-b { color: var(--amber-600, #d97706); }

.result-block { margin-top: 6px; }
.copy-row { display: flex; gap: 12px; margin-bottom: 14px; align-items: flex-start; }
.copy-label { width: 44px; flex-shrink: 0; font-size: 13px; font-weight: 600; color: var(--text-tertiary); padding-top: 8px; }
.copy-body { flex: 1; min-width: 0; }
.final-title { font-size: 17px; font-weight: 700; color: var(--text-primary); margin-bottom: 8px; line-height: 1.5; }
.final-content-md { background: var(--bg-page); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 12px 14px; font-size: 14px; line-height: 1.8; color: var(--text-primary); white-space: pre-wrap; word-break: break-word; max-height: 420px; overflow: auto; margin: 0 0 8px; font-family: inherit; }
.final-content-plain { background: var(--bg-page); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 12px 14px; font-size: 14px; line-height: 1.8; color: var(--text-primary); white-space: pre-wrap; word-break: break-word; max-height: 420px; overflow: auto; margin: 0 0 8px; font-family: inherit; }
.fmt-toggle { margin-bottom: 14px; }
.copy-hint { font-size: 12px; color: var(--text-quaternary); line-height: 1.6; margin: 0 0 8px; }
.result-links { display: flex; align-items: center; gap: 10px; margin-top: 6px; flex-wrap: wrap; }
.result-url { font-size: 13px; color: var(--brand-600); text-decoration: none; }
.result-empty { margin-top: 24px; display: flex; flex-direction: column; align-items: center; gap: 8px; color: var(--text-quaternary); font-size: 13px; text-align: center; }

.mdx-ready-tag { max-width: 340px; line-height: 1.5; }
.mdx-hint { font-size: 12.5px; color: var(--text-tertiary); line-height: 1.7; margin-bottom: 14px; background: var(--bg-page); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 10px 12px; }
.mdx-hint b { color: var(--accent-emerald); }
.mdx-fname { color: var(--brand-700); background: var(--brand-50); border: 1px solid var(--brand-200, #bfdbfe); border-radius: var(--radius-sm); padding: 6px 10px; font-family: var(--font-mono, monospace); font-size: 13px; word-break: break-all; font-weight: 600; }
.mdx-imglist { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.mdx-img { color: var(--brand-600); background: var(--brand-50); border: 1px solid var(--brand-200, #bfdbfe); border-radius: var(--radius-sm); padding: 4px 10px; font-family: var(--font-mono, monospace); font-size: 12.5px; word-break: break-all; }
.mdx-cover { color: var(--brand-600); background: var(--brand-50); border: 1px solid var(--brand-200, #bfdbfe); border-radius: var(--radius-sm); padding: 6px 10px; font-family: var(--font-mono, monospace); font-size: 13px; word-break: break-all; }
.mdx-code { font-family: var(--font-mono, monospace); white-space: pre-wrap; word-break: break-word; line-height: 1.6; }

.briefing-collapse { margin-top: 16px; }
.briefing-section { padding: 4px 0; }
.briefing-sub { font-size: 13px; font-weight: 600; color: var(--text-primary); margin: 12px 0 6px; }
.briefing-sub:first-child { margin-top: 0; }
.briefing-pre { background: var(--bg-page); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 12px 14px; font-size: 12.5px; line-height: 1.7; color: var(--text-secondary); white-space: pre-wrap; word-break: break-word; max-height: 360px; overflow: auto; margin: 0 0 8px; font-family: var(--font-mono, monospace); }

@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .4; } }
</style>
