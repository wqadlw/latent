<template>
  <div class="studio">
    <!-- 文章改写模式 横幅（P2-3，显眼入口）：贴被判软文 → 一键按模式改写 -->
    <div class="rewrite-banner" @click="openRewrite">
      <div class="rewrite-banner__text">
        <div class="rewrite-banner__title">文章改写模式</div>
        <div class="rewrite-banner__desc">把被判软文 / 低质的文章贴进来，一键按 geo / 平台合规 / 绿色吸粉 模式改写，软文风险从 X 降到 Y。</div>
      </div>
      <el-button type="warning" size="large" @click.stop="openRewrite">立即改写 →</el-button>
    </div>

    <!-- 空状态 -->
    <div v-if="!runs.length && !loading" class="empty">
      <el-empty description="还没有浏览器工作室运行">
        <el-button type="primary" @click="openCreate">新建运行</el-button>
      </el-empty>
    </div>

    <div v-else class="studio__body">
      <!-- 左：运行列表 -->
      <aside class="run-list">
        <div class="run-list__head">
          <span class="run-list__title">运行（{{ runs.length }}）</span>
          <div class="run-list__ops">
            <el-button size="small" type="primary" :icon="Plus" @click="openCreate">新建运行</el-button>
            <el-button size="small" :icon="Refresh" @click="loadRuns">刷新</el-button>
          </div>
        </div>
        <div class="run-list__items">
          <div
            v-for="r in runs"
            :key="r.id"
            class="run-card"
            :class="{ 'is-active': selectedId === r.id }"
            @click="selectRun(r.id)"
          >
            <div class="run-card__top">
              <span class="run-card__name">{{ r.name }}</span>
              <el-tag :type="statusType(r.status)" size="small" effect="dark">{{ statusLabel(r.status) }}</el-tag>
            </div>
            <div class="run-card__meta">
              <span>{{ platformLabel(r.platform) }}</span>
              <span class="tag-mock">{{ engineLabel(r.ai_engine || (r.mock_doubao ? 'mock' : 'deepseek')) }}</span>
              <span class="tag-mode" :class="runModeTag(r).cls">{{ runModeTag(r).text }}</span>
              <span class="run-card__time">{{ fmtTime(r.create_time) }}</span>
            </div>
            <div class="run-card__geo" v-if="r.geo_score">
              GEO <b :class="r.geo_score >= 70 ? 'good' : 'warn'">{{ r.geo_score }}</b>
            </div>
            <div v-if="r.error" class="run-card__err">{{ r.error }}</div>
          </div>
        </div>
      </aside>

      <!-- 右：运行详情 -->
      <section class="run-detail" v-if="selected">
        <div class="detail-head">
          <div>
            <h2 class="detail-title">{{ selected.name }}</h2>
            <p class="detail-sub">
              目标需求：{{ selected.subject || '（未填写，AI 自主选题）' }}
              <el-tag size="small" class="muted">{{ engineLabel(selected.ai_engine || (selected.mock_doubao ? 'mock' : 'deepseek')) }}</el-tag>
              <el-tag size="small" :type="runModeType(selected)">{{ runModeTag(selected).text }}</el-tag>
              <el-tag v-if="selected.auto_publish" size="small" type="warning">自动发布</el-tag>
              <el-tag v-if="selected.confirmed" size="small" type="success">已入内容中心</el-tag>
            </p>
          </div>
          <div class="detail-actions">
            <el-button
              v-if="selected.status === 'await_confirm'"
              type="success" @click="onConfirm"
            >✓ 满意，加入内容中心</el-button>
            <el-button
              v-if="canPublish && selected.output_format !== 'mdx'"
              type="primary" @click="onPublish"
            >发布到平台</el-button>
            <el-tag v-if="selected.output_format === 'mdx'" type="info" effect="plain" class="mdx-ready-tag">
              官网 MDX 已就绪 · 复制上方代码粘贴至官网 Astro 项目
            </el-tag>
            <el-button
              v-if="selected.status !== 'running' && selected.status !== 'await_confirm'"
              :type="selected.status === 'failed' ? 'warning' : 'primary'"
              @click="onStart"
            >{{ restartLabel }}</el-button>
            <el-button v-if="selected.status === 'running'" type="info" loading>运行中…</el-button>
            <el-button :icon="Delete" @click="onDelete">删除</el-button>
          </div>
        </div>

        <!-- 9 步流水线 -->
        <div class="pipeline">
          <div
            v-for="(s, i) in selected.steps"
            :key="s.id"
            class="step"
            :class="['step--' + s.status]"
          >
            <div class="step__rail">
              <div class="step__dot"></div>
              <div v-if="i < selected.steps.length - 1" class="step__line"></div>
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
                    size="small" type="warning" @click="onRetryPublish"
                  >重试发布</el-button>
                  <el-button
                    v-if="s.status === 'failed' && s.step_key !== 'publish'"
                    size="small" type="danger" @click="onRetry"
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
        <div class="step-log-wrap" v-if="selected.steps && selected.steps.length">
          <el-tabs v-model="logTab" class="studio-tabs">
            <el-tab-pane label="步骤透明日志" name="logs">
              <el-divider>每步「发送了什么 / 等多久 / 取到什么 / 下一步」（可直接复制给网页 AI 复现）</el-divider>
              <StepLogPanel :run-id="selected.id" :running="selected.status === 'running'" />
            </el-tab-pane>
            <el-tab-pane label="创作对话 · 主编↔写手" name="conv">
              <ConversationPanel :run-id="selected.id" :running="selected.status === 'running'" />
            </el-tab-pane>
          </el-tabs>
        </div>

        <!-- ============ AI 逐轮产出（每轮 AI 返回的内容都可见） ============ -->
        <div class="rounds" v-if="hasAnyStage">
          <el-divider>AI 逐轮产出（多专家协同：主编📋 总协调 · 写手✍️ 落地 · 合规官/GEO优化师/数据核查员 由主编评审把关，每一轮都可见）</el-divider>

          <div class="round-card" v-if="selected.clarified_brief">
            <div class="round-card__head"><span class="round-badge b0">①b</span> 主编·创作简报（明晰选题）
              <el-tag size="small" class="agent-planner-mini">主编</el-tag>
              <el-button size="small" text :icon="DocumentCopy" @click="copyText(selected.clarified_brief, '创作简报')">复制</el-button>
            </div>
            <pre class="round-text">{{ selected.clarified_brief }}</pre>
          </div>

          <div class="round-card" v-if="selected.outline_content">
            <div class="round-card__head"><span class="round-badge b1">①</span> 选题大纲 <el-button size="small" text :icon="DocumentCopy" @click="copyText(selected.outline_content, '大纲')">复制</el-button></div>
            <pre class="round-text">{{ selected.outline_content }}</pre>
          </div>
          <div class="round-card" v-if="selected.draft_content">
            <div class="round-card__head"><span class="round-badge b2">②</span> 初稿 <el-button size="small" text :icon="DocumentCopy" @click="copyText(selected.draft_content, '初稿')">复制</el-button></div>
            <pre class="round-text">{{ selected.draft_content }}</pre>
          </div>
          <div class="round-card" v-if="selected.rewrite_content">
            <div class="round-card__head"><span class="round-badge b3">③</span> 去AI味精修稿 <el-button size="small" text :icon="DocumentCopy" @click="copyText(selected.rewrite_content, '精修稿')">复制</el-button></div>
            <pre class="round-text">{{ selected.rewrite_content }}</pre>
          </div>
          <div class="round-card" v-if="selected.geo_content">
            <div class="round-card__head"><span class="round-badge b4">④</span> GEO 强化终稿（原始） <el-button size="small" text :icon="DocumentCopy" @click="copyText(selected.geo_content, 'GEO终稿')">复制</el-button></div>
            <pre class="round-text">{{ selected.geo_content }}</pre>
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
          <div class="round-card round-card--pass" v-if="!reviseList.length && selected.review_result">
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
          <div class="editor-review" v-if="selected.editor_review">
            <div class="editor-review__title">📋 主编·评审评语（汇总合规官 / GEO优化师 / 数据核查员 意见，人话版：为什么没过 / 主要差距在哪）</div>
            <pre class="editor-review__text">{{ selected.editor_review }}</pre>
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
        <div class="result-block" v-if="selected.final_content">
          <!-- 官网 / 自建站：MDX 代码产出（可复制） -->
          <template v-if="selected.output_format === 'mdx'">
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
                <pre class="final-content-md mdx-code">{{ selected.final_content }}</pre>
                <el-button size="small" :icon="DocumentCopy" @click="copyText(selected.final_content, 'MDX 代码')">复制 MDX 代码</el-button>
              </div>
            </div>

            <!-- 自动化发布提示词（官网 MDX 模板 · 有序存放） -->
            <el-collapse v-if="selected.publish_prompt" class="briefing-collapse">
              <el-collapse-item title="📦 自动化发布提示词（官网 MDX 模板 · 专门部件有序存放）" name="pubprompt">
                <div class="briefing-sub">下面这份提示词是「官网/自建站」模式的自动化发布提示词，已专门存放在平台的 publish_prompt 字段，编排时自动注入主编工作流，确保每次官网产出都遵循同一套 MDX 规范。</div>
                <pre class="briefing-pre">{{ selected.publish_prompt }}</pre>
                <el-button size="small" :icon="DocumentCopy" @click="copyText(selected.publish_prompt, '自动化发布提示词')">复制自动化发布提示词</el-button>
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
                <div class="final-title">{{ selected.final_title }}</div>
                <el-button size="small" :icon="DocumentCopy" @click="copyText(selected.final_title, '标题')">复制标题</el-button>
              </div>
            </div>
            <div class="copy-row">
              <div class="copy-label">正文</div>
              <div class="copy-body">
                <pre v-if="finalFormat === 'markdown'" class="final-content-md">{{ selected.final_content }}</pre>
                <pre v-else class="final-content-plain">{{ finalContentPlain }}</pre>
                <div class="copy-hint" v-if="finalFormat === 'markdown'">已含 #/## 标题、- 列表、**加粗**、FAQ 小节，便于 AI 检索引用与一键发布到支持 Markdown 的平台。</div>
                <div class="copy-hint" v-else>已转换为纯文本格式，去掉了 Markdown 标记但保留段落结构，可直接复制到不支持 Markdown 的平台发布。</div>
                <el-button size="small" :icon="DocumentCopy" @click="copyText(finalFormat === 'markdown' ? selected.final_content : finalContentPlain, '正文')">复制正文</el-button>
              </div>
            </div>
          </template>

          <div class="result-links">
            <el-tag v-if="selected.content_asset_id" type="success" effect="plain">已存档 · 内容资产 #{{ selected.content_asset_id }}</el-tag>
            <el-tag v-if="selected.sohu_job_id" :type="jobTagType(selected)" effect="plain">
              发布任务 #{{ selected.sohu_job_id }} · {{ jobStatusText(selected) }}
            </el-tag>
            <a v-if="selected.sohu_job_id && sohuUrl(selected)" :href="sohuUrl(selected)" target="_blank" class="result-url">查看发布链接 ↗</a>
          </div>

          <!-- 派发给 AI 的总指令 + 背景资料 -->
          <el-collapse class="briefing-collapse">
            <el-collapse-item title="查看派发给 AI 的「总指令 + 整合好的全部背景资料」" name="briefing">
              <div class="briefing-section">
                <div class="briefing-sub">① 选题大纲阶段指令</div>
                <pre class="briefing-pre">{{ (selected.stage_prompts||{}).outline }}</pre>
                <div class="briefing-sub">② 初稿阶段指令</div>
                <pre class="briefing-pre">{{ (selected.stage_prompts||{}).draft }}</pre>
                <div class="briefing-sub">③ 去AI味精修阶段指令</div>
                <pre class="briefing-pre">{{ (selected.stage_prompts||{}).depolish }}</pre>
                <div class="briefing-sub">④ GEO强化 + 过审阶段指令（含 FINAL 契约）</div>
                <pre class="briefing-pre">{{ (selected.stage_prompts||{}).geo }}</pre>
                <el-button size="small" :icon="DocumentCopy" @click="copyText(allStagePrompts, '全部阶段指令')">复制全部阶段指令</el-button>

                <div class="briefing-sub">⑤ 整合好的全部背景资料（目标需求 / 品牌资产 / 平台 / 账号人设 / 知识库 / 关键词 / 规则库 / 客户画像 + 意图问题）</div>
                <pre class="briefing-pre">{{ selected.briefing }}</pre>
                <el-button size="small" :icon="DocumentCopy" @click="copyText(selected.briefing, '背景资料')">复制背景资料</el-button>
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
    </div>

    <!-- 新建运行对话框（可视化向导） -->
    <el-dialog v-model="dialogVisible" title="新建 AI 创作运行" width="780px" top="5vh">
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

      <!-- 步骤 2：选内容来源（链接关键词选题库 / 客户画像库 / 意图问题库 / 知识库 / 规则库） -->
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

      <!-- 步骤 3：发布平台（卡片） -->
      <div class="wz-step">
        <div class="wz-step-title"><span class="wz-badge">3</span>发布到哪个平台</div>
        <div class="card-row">
          <div v-for="p in platformOptions" :key="p.value" class="pick-card"
            :class="{ active: form.platform === p.value }" @click="selectPlatform(p)">
            <div class="pick-name">{{ p.label }}</div>
            <div class="pick-desc">{{ p.desc }}</div>
            <div class="pick-mode" :class="modeOptionClass(p.mode)">{{ modeOptionText(p.mode) }}</div>
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

      <!-- 步骤 4：AI 引擎（卡片） -->
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
            <el-option v-for="c in options.doubaoCreds" :key="c.id" :label="`#${c.id} ${c.note || '豆包cookie'}`" :value="c.id" />
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
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onCreate">创建并启动 ▶</el-button>
      </template>
    </el-dialog>

    <!-- 发布前软文预检（P2-1 / C 项补全）：确认/发布前强制弹窗，展示综合闸门结果 -->
    <el-dialog v-model="precheckVisible" title="发布前软文预检" width="640px" append-to-body>
      <div v-loading="precheckLoading" element-loading-text="正在跑综合质量闸门…">
        <template v-if="precheckResult">
          <el-alert
            v-if="!precheckResult.has_content"
            type="warning" :closable="false" show-icon
            title="尚未生成终稿，无法预检"
            description="请先完成创作流程（①连接 → ⑥GEO终稿）生成终稿后再确认/发布。"
          />
          <template v-else>
            <el-alert
              :type="precheckResult.gate_pass ? 'success' : 'error'"
              :closable="false" show-icon
              :title="precheckResult.verdict"
              :description="`发布模式：${precheckResult.mode}${precheckResult.output_format === 'mdx' ? '（官网 MDX）' : ''}`"
            />
            <el-descriptions :column="2" border size="small" class="pc-metrics">
              <el-descriptions-item label="综合闸门">
                <el-tag :type="precheckResult.gate_pass ? 'success' : 'danger'" size="small">
                  {{ precheckResult.gate_pass ? '通过' : '未过' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="平台基础合规">
                <el-tag :type="precheckResult.compliance_pass ? 'success' : 'danger'" size="small">
                  {{ precheckResult.compliance_pass ? '通过' : '未过' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="GEO 评分">
                <span :class="precheckResult.geo_pass ? 'pc-ok' : 'pc-warn'">
                  {{ precheckResult.geo_score }} 分{{ precheckResult.geo_pass ? '（达标≥70）' : '（未达标）' }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item v-if="precheckResult.platform_compliance" label="软文风险分">
                <el-tag :type="riskTagType(precheckResult.platform_compliance.risk_level)" size="small">
                  {{ precheckResult.platform_compliance.risk_score }} 分 · {{ precheckResult.platform_compliance.risk_level }}
                </el-tag>
              </el-descriptions-item>
            </el-descriptions>

            <div v-if="precheckResult.platform_compliance && precheckResult.platform_compliance.soft_issues && precheckResult.platform_compliance.soft_issues.length" class="pc-block">
              <div class="pc-block-title">软文特征信号（平台算法重点判定项）</div>
              <ul class="pc-issue-list">
                <li v-for="(it, i) in precheckResult.platform_compliance.soft_issues" :key="'s'+i">{{ it }}</li>
              </ul>
            </div>

            <div v-if="precheckResult.issues && precheckResult.issues.length" class="pc-block">
              <div class="pc-block-title">全部问题清单（合规 / GEO / 软文）</div>
              <ul class="pc-issue-list">
                <li v-for="(it, i) in precheckResult.issues" :key="'i'+i">{{ it }}</li>
              </ul>
            </div>

            <el-alert
              v-if="!precheckResult.gate_pass"
              type="warning" :closable="false" class="pc-tip"
              title="提示"
              description="该文章在目标平台大概率会被判软文广告或违规而拒稿。建议回到「GEO 强化 / 整改」步骤洗稿降风险，或改用 geo 强品牌模式后重新预检。"
            />
          </template>
        </template>
      </div>
      <template #footer>
        <el-button @click="precheckVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="precheckResult && !precheckResult.has_content"
          @click="onPrecheckProceed"
        >
          {{ precheckAction === 'publish' ? '仍要发布' : '仍要确认' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 文章改写模式对话框（P2-3） -->
    <el-dialog v-model="rewriteVisible" title="文章改写模式" width="760px" append-to-body @open="loadRewriteBrands">
      <el-form :model="rewriteForm" label-width="100px" class="rewrite-form">
        <el-form-item label="待改写原文" required>
          <el-input
            v-model="rewriteForm.source_text"
            type="textarea"
            :rows="8"
            placeholder="把被判软文 / 低质、或想换发布模式的文章整篇粘贴到这里…"
          />
        </el-form-item>
        <el-form-item label="目标发布模式">
          <el-radio-group v-model="rewriteForm.target_mode">
            <el-radio value="geo">geo 强品牌</el-radio>
            <el-radio value="platform">平台合规</el-radio>
            <el-radio value="green">绿色吸粉</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="品牌">
          <el-select v-model="rewriteForm.brand_asset_id" placeholder="用行业默认品牌" clearable style="width: 100%">
            <el-option v-for="b in rewriteBrandOptions" :key="b.id" :label="b.brand_name" :value="b.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="引擎">
          <el-radio-group v-model="rewriteForm.ai_engine">
            <el-radio value="deepseek">DeepSeek（真实改写）</el-radio>
            <el-radio value="mock">Mock（演示）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-button type="warning" :loading="rewriteLoading" @click="doRewrite">开始改写</el-button>
        </el-form-item>
      </el-form>

      <div v-if="rewriteResult" class="rewrite-result">
        <div class="rewrite-risk">
          <div class="rewrite-risk__item" :class="riskClass(rewriteResult.source_risk && rewriteResult.source_risk.risk_score)">
            <div class="rewrite-risk__label">改写前软文风险</div>
            <div class="rewrite-risk__val">
              {{ rewriteResult.source_risk ? rewriteResult.source_risk.risk_score : '—' }}
              <small v-if="rewriteResult.source_risk">{{ rewriteResult.source_risk.risk_level }}</small>
            </div>
          </div>
          <div class="rewrite-risk__arrow">→</div>
          <div class="rewrite-risk__item" :class="riskClass(rewriteResult.platform_compliance && rewriteResult.platform_compliance.risk_score)">
            <div class="rewrite-risk__label">改写后软文风险</div>
            <div class="rewrite-risk__val">
              {{ rewriteResult.platform_compliance ? rewriteResult.platform_compliance.risk_score : (rewriteResult.target_mode === 'geo' ? '不评' : '—') }}
              <small v-if="rewriteResult.platform_compliance">{{ rewriteResult.platform_compliance.risk_level }}</small>
            </div>
          </div>
          <div class="rewrite-risk__engine">引擎：{{ rewriteResult.engine === 'mock' ? 'Mock 演示' : 'DeepSeek' }}</div>
        </div>

        <el-alert
          :type="rewriteResult.gate_pass ? 'success' : 'warning'"
          :closable="false"
          class="pc-tip"
          :title="rewriteResult.verdict"
        />

        <div class="rewrite-out__head">
          <span>改写后的文章（{{ modeLabel(rewriteResult.target_mode) }}）</span>
          <el-button size="small" @click="copyRewrite">复制全文</el-button>
        </div>
        <el-input
          :model-value="rewriteResult.rewritten_text"
          type="textarea"
          :rows="12"
          readonly
          class="rewrite-out"
        />

        <div v-if="rewriteResult.issues && rewriteResult.issues.length" class="rewrite-issues">
          <div class="rewrite-issues__title">预检明细</div>
          <ul>
            <li v-for="(it, i) in rewriteResult.issues" :key="i">{{ it }}</li>
          </ul>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Delete, DocumentDelete, DocumentCopy, Plus } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { browserStudioApi, platformCredentialApi, keywordApi, keywordGroupApi, targetPersonaApi, intentQuestionApi, knowledgeApi, ruleApi, brandAssetApi } from '../api'
import StepLogPanel from '../components/StepLogPanel.vue'
import ConversationPanel from '../components/ConversationPanel.vue'

const store = useAppStore()

const runs = ref([])
const loading = ref(false)
const selectedId = ref(0)
const selected = ref(null)
const logTab = ref('logs')
const dialogVisible = ref(false)
const expanded = reactive({})
let pollTimer = null
const finalFormat = ref('markdown')

// 文章改写模式（P2-3）：贴被判软文 → 按目标模式改写
const rewriteVisible = ref(false)
const rewriteLoading = ref(false)
const rewriteResult = ref(null)
const rewriteBrandOptions = ref([])
const rewriteForm = reactive({
  source_text: '',
  target_mode: 'platform',
  brand_asset_id: null,
  ai_engine: 'mock',
})

const platformOptions = [
  { value: 'sohu', label: '搜狐号', desc: '综合资讯，利于被搜索引擎收录', mode: 'platform' },
  { value: 'zhihu', label: '知乎', desc: '专业问答，利于被 AI 引用作答', mode: 'platform' },
  { value: 'wangyi', label: '网易号', desc: '泛流量，适合品牌曝光', mode: 'platform' },
  { value: 'official', label: '官网 / 自建站', desc: '自有阵地（Astro 站），产出可复制 MDX 代码', mode: 'official' },
]

const engineOptions = [
  { value: 'deepseek', label: 'DeepSeek（API）', desc: '多专家协同：主编(总协调)用 deepseek-v4-pro+thinking 推理做规划/评审/整改；写手用同模型非推理落地；合规官/GEO优化师/数据核查员由系统自检+主编评审共同把关', recommend: true },
  { value: 'doubao', label: '豆包（浏览器自动化）', desc: '真实打开豆包官网，自动复制粘贴对话（需上传豆包 cookie）', recommend: false },
  { value: 'mock', label: '模拟演示', desc: '无需任何配置，直接跑通全流程用于验证', recommend: false },
]

// 10 步双智能体流水线全景（新建向导顶部展示）
const pipelineSteps = [
  '连接引擎', '主编·明晰', '主编·大纲', '写手·初稿', '写手·精修',
  '写手·GEO终稿', '主编·评审', '闭环整改', '满意确认', '发布平台',
]

// 本运行自动带入的系统内容（新建向导中展示，强调“已内置全部内容”）
const autoContextTags = ['目标需求', '品牌资产', '账号人设', '知识库', '关键词', '规则库', '客户画像', '意图问题库']

// 多专家团队（新建向导中展示，强调“多角色协同创作”）
const expertTeam = [
  { role: '主编', tag: 'agent-planner', desc: '总协调：定方向、定大纲、终审把关、下达整改指令' },
  { role: '写手', tag: 'agent-writer', desc: '落地：初稿 / 去AI味 / GEO终稿 / 按指令改写' },
  { role: '合规官', tag: 'agent-compliance', desc: '平台合规红线：违禁词 / 硬广 / 站外引流 / 联系方式' },
  { role: 'GEO优化师', tag: 'agent-geo', desc: '搜索可见性：品牌实体 / 关键词 / FAQ / 意图覆盖' },
  { role: '数据核查员', tag: 'agent-fact', desc: '事实与数据：不夸大、不虚构、可溯源' },
]

const form = reactive({
  name: '', subject: '', platform: 'sohu', publish_mode: 'platform',
  ai_engine: 'deepseek',
  doubao_credential_id: 0,
  auto_publish: false,
  keyword_ids: [], target_persona_ids: [], intent_question_ids: [],
  knowledge_item_ids: [], rule_ids: [],
})

// 链接系统内容库：新建运行时从各库拉取可选清单，用户显式选择这篇文章的内容来源
const libOpts = reactive({
  keywordGroups: [], keywords: [], targetPersonas: [], intentQuestions: [],
  knowledgeItems: [], rules: [],
})
const libLoading = ref(false)
const kwSearch = ref('')
// 关键词按分组归类（供多选下拉分组展示）
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
// 意图问题按已选客户画像过滤（与 Production 流水线一致：不挑=全部；挑了=只显该画像下问题）
const filteredIntentQuestions = computed(() => {
  const sel = form.target_persona_ids || []
  if (!sel.length) return libOpts.intentQuestions
  return (libOpts.intentQuestions || []).filter(q => q.persona_id != null && sel.includes(q.persona_id))
})

// 选平台时同步默认发布模式（内容平台→平台合规；官网/自建站→强品牌/GEO，产出形态由平台决定为 MDX），用户可手动覆盖
function selectPlatform(p) {
  form.platform = p.value
  // official 平台在后端会强制 geo + mdx 产出，这里把发布模式默认置 geo，避免传非白名单值
  form.publish_mode = (p.mode === 'platform' || p.mode === 'green' || p.mode === 'geo') ? p.mode : 'geo'
}

const options = reactive({ doubaoCreds: [] })

const industryId = () => Number(store.currentIndustryId) || 0

// ============ 计算属性 ============
const review = computed(() => {
  const r = selected.value && selected.value.review_result
  return (r && Object.keys(r).length) ? r : null
})
const geoObj = computed(() => (review.value && review.value.geo) || null)
const geoDims = computed(() => (geoObj.value && geoObj.value.dimensions) || null)
const geoDiag = computed(() => (geoObj.value && geoObj.value.diagnosis) || null)
const mindObj = computed(() => (geoObj.value && geoObj.value.mind_resonance) || null)
const mindDims = computed(() => (mindObj.value && mindObj.value.dimensions) || null)
const mindScore = computed(() => (mindObj.value && mindObj.value.score) || 0)
const reviseList = computed(() => {
  const rr = selected.value && selected.value.revise_rounds
  return Array.isArray(rr) ? rr : []
})
const hasAnyStage = computed(() =>
  selected.value && (selected.value.outline_content || selected.value.draft_content ||
    selected.value.rewrite_content || selected.value.geo_content || reviseList.value.length)
)
const canPublish = computed(() => {
  const s = selected.value
  if (!s) return false
  return !!s.confirmed && !s.sohu_job_id && s.status !== 'running'
})
const restartLabel = computed(() => {
  const s = selected.value && selected.value.status
  if (s === 'created') return '启动'
  if (s === 'await_confirm') return '重跑'
  return '重新启动'
})
const allStagePrompts = computed(() => {
  const sp = (selected.value && selected.value.stage_prompts) || {}
  return ['【① 选题大纲】', sp.outline, '\n【② 初稿】', sp.draft, '\n【③ 去AI味精修】', sp.depolish, '\n【④ GEO强化+过审】', sp.geo, '\n【整改】', sp.revise].filter(Boolean).join('\n\n')
})

// Markdown → 纯文本转换（前端版，去掉 Markdown 标记但保留段落结构）
function markdownToPlain(md) {
  if (!md) return ''
  let t = md
  // 代码块
  t = t.replace(/```[\s\S]*?```/g, m => m.replace(/```/g, '').trim())
  // 行内代码
  t = t.replace(/`([^`]+)`/g, '$1')
  // 标题 #~###### → 保留文字
  t = t.replace(/^#{1,6}\s*/gm, '')
  // 粗体/斜体
  t = t.replace(/\*\*(.+?)\*\*/g, '$1')
  t = t.replace(/__(.+?)__/g, '$1')
  t = t.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, '$1')
  // 链接 [text](url) -> text
  t = t.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
  // 引用
  t = t.replace(/^>\s?/gm, '')
  // 无序列表 - * + → 保留文字，去掉符号
  t = t.replace(/^\s*[-*+]\s+/gm, '\u00b7 ')
  // 有序列表 1. → 保留文字
  t = t.replace(/^\s*\d+\.\s+/gm, '')
  // 分隔线
  t = t.replace(/^(\s*[-*_]){3,}\s*$/gm, '')
  // 表格分隔行
  t = t.replace(/^\s*\|?[\-: ]+\|[\-: |]+\|?\s*$/gm, '')
  // 表格列分隔
  t = t.replace(/(?<=\S)\s*\|\s*(?=\S)/g, ' | ')
  // 折叠多余空行
  t = t.replace(/\n{3,}/g, '\n\n')
  return t.trim()
}
const finalContentPlain = computed(() => markdownToPlain(selected.value?.final_content || ''))

// 从 MDX frontmatter 中解析封面图文件名（约定路径 @/assets/news/industry/xingwen/xxx.jpg）
const mdxCoverImage = computed(() => {
  const t = selected.value?.final_content || ''
  const m = t.match(/cover:\s*['"]?([^\n'"]+)['"]?/)
  return m ? m[1].trim() : ''
})
// 后端解析出的 .mdx 文件名（可直接复制用于官网 Astro 项目）
const mdxFileName = computed(() => (selected.value?.mdx_filename || '').trim())
// 后端解析出的建议配图文件名列表（JSON 数组）
const mdxImages = computed(() => {
  const v = selected.value?.mdx_images
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v) {
    try { const p = JSON.parse(v); return Array.isArray(p) ? p : [] } catch (e) { return [] }
  }
  return []
})

// ============ 加载 ============
async function loadRuns() {
  loading.value = true
  try {
    const res = await browserStudioApi.list(industryId())
    runs.value = (res.data || []).filter(r => !r.is_deleted)
    if (!selectedId.value && runs.value.length) {
      await selectRun(runs.value[0].id)
    } else if (selectedId.value) {
      await selectRun(selectedId.value, true)
    }
  } finally {
    loading.value = false
  }
}

async function selectRun(id, silent = false) {
  selectedId.value = id
  const res = await browserStudioApi.get(id)
  selected.value = res.data
  startPolling()
}

async function loadOptions() {
  const ind = industryId()
  try {
    const pc = await platformCredentialApi.list(ind)
    options.doubaoCreds = (pc.data || []).filter(c => c.platform === 'doubao')
  } catch (e) { /* 忽略 */ }
}

// 拉取各内容库清单，供新建运行向导选择这篇文章的内容来源
async function loadLibOptions() {
  const ind = industryId()
  libLoading.value = true
  try {
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
  } catch (e) { /* 忽略 */ }
  finally { libLoading.value = false }
}

// ============ 文章改写模式（P2-3） ============
function openRewrite() {
  rewriteResult.value = null
  rewriteVisible.value = true
}

async function loadRewriteBrands() {
  try {
    const res = await brandAssetApi.list(industryId())
    rewriteBrandOptions.value = res.data || []
  } catch (e) {
    rewriteBrandOptions.value = []
  }
}

function riskClass(score) {
  if (score === null || score === undefined) return ''
  if (score >= 70) return 'is-high'
  if (score >= 40) return 'is-mid'
  return 'is-low'
}

function modeLabel(m) {
  return { geo: 'geo 强品牌', platform: '平台合规', green: '绿色吸粉' }[m] || m
}

async function doRewrite() {
  if (!rewriteForm.source_text.trim()) {
    ElMessage.warning('请先粘贴待改写的原文')
    return
  }
  rewriteLoading.value = true
  try {
    const payload = {
      industry_id: industryId(),
      source_text: rewriteForm.source_text,
      target_mode: rewriteForm.target_mode,
      brand_asset_id: rewriteForm.brand_asset_id || null,
      ai_engine: rewriteForm.ai_engine,
    }
    const res = await browserStudioApi.rewrite(payload)
    if (res.code === 0 && res.data && res.data.ok) {
      rewriteResult.value = res.data
    } else {
      ElMessage.warning((res.data && res.data.error) || '改写失败')
    }
  } catch (e) {
    ElMessage.warning('改写请求失败：' + (e?.response?.data?.error || e.message || e))
  }
  finally {
    rewriteLoading.value = false
  }
}

function copyRewrite() {
  const txt = rewriteResult.value?.rewritten_text || ''
  if (navigator.clipboard) {
    navigator.clipboard.writeText(txt).then(() => ElMessage.success('已复制改写稿'))
  } else {
    ElMessage.warning('当前环境不支持自动复制，请手动选择')
  }
}

// ============ 操作 ============
function openCreate() {
  Object.assign(form, {
    name: '', subject: '', platform: 'sohu', publish_mode: 'platform',
    ai_engine: 'deepseek', doubao_credential_id: 0, auto_publish: false,
    keyword_ids: [], target_persona_ids: [], intent_question_ids: [],
    knowledge_item_ids: [], rule_ids: [],
  })
  dialogVisible.value = true
  loadLibOptions()
}

async function onCreate() {
  const payload = {
    name: form.name, subject: form.subject, platform: form.platform,
    industry_id: industryId(),
    ai_engine: form.ai_engine,
    doubao_credential_id: form.ai_engine === 'doubao' ? form.doubao_credential_id : 0,
    auto_publish: form.auto_publish,
    publish_mode: form.publish_mode,
    keyword_ids: form.keyword_ids,
    target_persona_ids: form.target_persona_ids,
    intent_question_ids: form.intent_question_ids,
    knowledge_item_ids: form.knowledge_item_ids,
    rule_ids: form.rule_ids,
  }
  const res = await browserStudioApi.create(payload)
  dialogVisible.value = false
  const id = res.data.id
  await browserStudioApi.start(id)
  const eng = form.ai_engine === 'deepseek' ? 'DeepSeek' : (form.ai_engine === 'doubao' ? '豆包' : '模拟演示')
  ElMessage.success(`已创建并启动（${eng} 引擎，双智能体 10 步流水线）`)
  await loadRuns()
  await selectRun(id)
}

async function onStart() {
  const res = await browserStudioApi.start(selected.value.id)
  if (res.data && res.data.ok) {
    ElMessage.success('已启动')
    startPolling()
  } else {
    ElMessage.warning((res.data && res.data.msg) || '无法启动')
  }
}

async function onRetry() {
  await browserStudioApi.retry(selected.value.id)
  ElMessage.success('已重新启动（重跑全流程）')
  startPolling()
}

// —— 发布前软文预检（P2-1 / C 项补全）——
const precheckVisible = ref(false)
const precheckLoading = ref(false)
const precheckResult = ref(null)
const precheckAction = ref('')   // 'confirm' | 'publish'

async function openPrecheck(action) {
  if (!selected.value) return
  precheckAction.value = action
  precheckLoading.value = true
  precheckVisible.value = true
  precheckResult.value = null
  try {
    const res = await browserStudioApi.precheck(selected.value.id)
    precheckResult.value = (res.data && res.data.data) ? res.data.data : null
  } catch (e) {
    ElMessage.warning('预检请求失败：' + (e?.response?.data?.message || e.message || '网络错误'))
    precheckVisible.value = false
    return
  } finally {
    precheckLoading.value = false
  }
}

// 弹窗里点「仍要确认 / 仍要发布」才真正执行
async function onPrecheckProceed() {
  const action = precheckAction.value
  precheckVisible.value = false
  if (action === 'confirm') await doConfirm()
  else await doPublish()
}

async function doConfirm() {
  const res = await browserStudioApi.confirm(selected.value.id)
  if (res.data && res.data.ok) {
    ElMessage.success(`已加入内容中心（资产 #${res.data.asset_id}）`)
    await selectRun(selected.value.id, true)
    if (res.data.status === 'succeeded') startPolling()
  } else {
    ElMessage.warning((res.data && res.data.error) || '确认失败')
  }
}

async function doPublish() {
  const res = await browserStudioApi.publish(selected.value.id)
  if (res.data && (res.data.ok || res.data.intercepted)) {
    if (res.data.intercepted) ElMessage.warning('合规未完全通过，已拦截自动发布并转人工审核')
    else ElMessage.success('已创建发布任务')
    await selectRun(selected.value.id, true)
    startPolling()
  } else {
    ElMessage.warning((res.data && res.data.error) || '发布失败')
  }
}

// 软文风险等级 → 颜色标签
function riskTagType(level) {
  if (level === '高') return 'danger'
  if (level === '中') return 'warning'
  return 'success'
}

async function onConfirm() {
  await openPrecheck('confirm')
}

async function onPublish() {
  await openPrecheck('publish')
}

async function onRetryPublish() {
  const res = await browserStudioApi.retryPublish(selected.value.id)
  if (res.data && res.data.ok) ElMessage.success('已重新发布')
  else ElMessage.warning((res.data && res.data.error) || '重试发布失败')
  await selectRun(selected.value.id, true)
}

async function onDelete() {
  await ElMessageBox.confirm('确认删除该运行？步骤记录将一并隐藏。', '删除确认', { type: 'warning' })
  await browserStudioApi.remove(selected.value.id)
  ElMessage.success('已删除')
  selectedId.value = 0
  selected.value = null
  await loadRuns()
}

function toggleStep(s) {
  expanded[s.id] = !expanded[s.id]
}

// 步骤 → 该步骤 AI 返回原文（逐轮可见）
function stepOutput(key) {
  const s = selected.value
  if (!s) return ''
  if (key === 'clarify') return s.clarified_brief
  if (key === 'outline') return s.outline_content
  if (key === 'draft') return s.draft_content
  if (key === 'depolish') return s.rewrite_content
  if (key === 'geo') return s.geo_content
  if (key === 'review') return s.editor_review || ''
  return ''
}
function roleLabel(rt) {
  const m = { decision_maker: '决策层', technical: '技术层', procurement: '采购层' }
  return m[rt] || rt || '其他'
}
function ruleTypeLabel(t) {
  const m = { ai_seo: 'AI SEO', anti_ai: '去AI味', compliance: '合规', creation: '创作' }
  return m[t] || t || '规则'
}

async function copyText(text, label) {
  if (!text) { ElMessage.warning('没有可复制的内容'); return }
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'; ta.style.opacity = '0'
      document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta)
    }
    ElMessage.success(`已复制${label || '内容'}`)
  } catch (e) {
    ElMessage.error('复制失败，请手动选择文本复制')
  }
}

// ============ 轮询 ============
function startPolling() {
  stopPolling()
  if (selected.value && selected.value.status === 'running') {
    pollTimer = setInterval(async () => {
      if (!selectedId.value) return
      try {
        const res = await browserStudioApi.get(selectedId.value)
        selected.value = res.data
        if (res.data.status !== 'running') stopPolling()
      } catch (e) { stopPolling() }
    }, 2500)
  }
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

// ============ 展示辅助 ============
function statusLabel(s) {
  return { created: '已创建', running: '运行中', succeeded: '成功', partial: '部分成功', failed: '失败', await_confirm: '待你确认', confirmed: '已确认' }[s] || s
}
function engineLabel(e) {
  return { deepseek: 'DeepSeek', doubao: '豆包', mock: '模拟演示' }[e] || e || 'DeepSeek'
}
function agentLabel(a) {
  return { planner: '📋 主编', writer: '✍️ 写手', dual: '📋✍️ 双角色', system: '⚙️ 系统' }[a] || '⚙️ 系统'
}
function statusType(s) {
  return { created: 'info', running: 'primary', succeeded: 'success', partial: 'warning', failed: 'danger', await_confirm: 'warning', confirmed: 'success' }[s] || 'info'
}
function stepLabel(s) {
  return { pending: '待执行', running: '执行中', done: '完成', failed: '失败', skipped: '跳过' }[s] || s
}
function stepType(s) {
  return { pending: 'info', running: 'primary', done: 'success', failed: 'danger', skipped: 'info' }[s] || 'info'
}
function platformLabel(p) {
  return (platformOptions.find(x => x.value === p) || {}).label || p
}
// 新建向导：平台卡片上的模式角标文案 / 样式类
function modeOptionText(m) {
  if (m === 'platform') return '平台合规'
  if (m === 'official') return '官网 MDX'
  if (m === 'green') return '绿色吸粉'
  return '强品牌/GEO'
}
function modeOptionClass(m) {
  if (m === 'platform') return 'm-platform'
  if (m === 'official') return 'm-official'
  if (m === 'green') return 'm-green'
  return 'm-geo'
}
// 列表 / 详情：根据运行实际模式 + 产出形态给出统一徽标（三模式 + 官网 MDX 分支）
function runModeTag(r) {
  if ((r.output_format || '') === 'mdx') return { text: '官网 MDX', cls: 'm-official' }
  if (r.publish_mode === 'platform') return { text: '平台合规', cls: 'm-platform' }
  if (r.publish_mode === 'green') return { text: '绿色吸粉', cls: 'm-green' }
  return { text: '强品牌/GEO', cls: 'm-geo' }
}
function runModeType(r) {
  if ((r.output_format || '') === 'mdx') return 'primary'
  if (r.publish_mode === 'platform') return 'info'
  if (r.publish_mode === 'green') return 'success'
  return 'danger'
}
const DIM_LABELS = {
  entity_signals: '实体信号', fact_density: '事实密度', intent_coverage: '意图覆盖',
  qa_form: '问答形态', structure: '结构可提取', attributable: '信号可归属',
}
const DIM_WEIGHTS = { entity_signals: 25, fact_density: 20, intent_coverage: 20, qa_form: 15, structure: 10, attributable: 10 }
const MIND_LABELS = {
  storytelling: '叙事感', scenario: '场景化', reader_perspective: '读者视角',
  language_warmth: '语言温度', pain_resonance: '痛点共鸣',
}
function dimLabel(k) { return DIM_LABELS[k] || k }
function mindLabel(k) { return MIND_LABELS[k] || k }
function dimPct(k, v) {
  const w = DIM_WEIGHTS[k] || 20
  return Math.min(100, Math.round((Number(v) || 0) / w * 100))
}
function dimColor(k, v) {
  const w = DIM_WEIGHTS[k] || 20
  const ratio = (Number(v) || 0) / w
  if (ratio >= 0.7) return '#10b981'
  if (ratio >= 0.4) return '#f59e0b'
  return '#ef4444'
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
function fmtTime(t) {
  return (t || '').slice(0, 16).replace('T', ' ')
}
function pretty(jsonStr) {
  try { return JSON.stringify(JSON.parse(jsonStr), null, 2) } catch (e) { return jsonStr }
}

onMounted(async () => {
  await loadOptions()
  await loadRuns()
})
onBeforeUnmount(stopPolling)
</script>

<style scoped>
.studio { height: 100%; }
.studio__body { display: flex; gap: 16px; height: 100%; align-items: stretch; }

.run-list { width: 300px; flex-shrink: 0; background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-lg); display: flex; flex-direction: column; overflow: hidden; }
.run-list__head { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-bottom: 1px solid var(--border-light); }
.run-list__title { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.run-list__items { flex: 1; overflow-y: auto; padding: 8px; }
.run-card { padding: 10px 12px; border-radius: var(--radius-md); border: 1px solid transparent; cursor: pointer; margin-bottom: 6px; transition: all .16s; }
.run-card:hover { background: var(--slate-50); }
.run-card.is-active { border-color: var(--brand-400); background: var(--brand-50); }
.run-card__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.run-card__name { font-weight: 600; font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-card__meta { display: flex; align-items: center; gap: 8px; margin-top: 4px; font-size: 12px; color: var(--text-tertiary); }
.run-card__geo { margin-top: 4px; font-size: 12px; color: var(--text-tertiary); }
.run-card__geo b { font-size: 13px; }
.run-card__geo .good { color: var(--accent-emerald); }
.run-card__geo .warn { color: var(--amber-500); }
.tag-mock { color: var(--brand-600); }
.tag-mode { padding: 1px 7px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.tag-mode.m-platform { background: #e0f2fe; color: #0369a1; }
.tag-mode.m-geo { background: #fef3c7; color: #b45309; }
.tag-mode.m-green { background: #dcfce7; color: #15803d; }
.tag-mode.m-official { background: #ede9fe; color: #6d28d9; }
.run-card__time { margin-left: auto; }

/* 新建向导：平台卡片上的模式角标 + 发布模式选择行 */
.pick-mode { margin-top: 6px; display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.pick-mode.m-platform { background: #e0f2fe; color: #0369a1; }
.pick-mode.m-geo { background: #fef3c7; color: #b45309; }
.pick-mode.m-official { background: #ede9fe; color: #6d28d9; }
.mode-row { margin-top: 12px; display: flex; flex-direction: column; gap: 6px; }
.mode-row .mode-label { font-size: 13px; font-weight: 600; color: var(--text-secondary); }
.run-card__err { margin-top: 4px; font-size: 11px; color: var(--red-500); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

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
.expert-team { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 12px; padding: 10px 12px; background: var(--bg-page); border: 1px dashed var(--border-light); border-radius: var(--radius-sm); }
.et-title { font-size: 12px; color: var(--text-tertiary); font-weight: 600; }
.et-tag { border: none; }
.et-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-left: 2px; cursor: help; }
.et-dot.agent-compliance { background: #b91c1c; }
.et-dot.agent-geo { background: #15803d; }
.et-dot.agent-fact { background: #a16207; }
.et-dot.agent-planner { background: #6d28d9; }
.et-dot.agent-writer { background: #0369a1; }
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
.run-list__ops { display: flex; gap: 6px; }

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

.create-form { max-height: 70vh; overflow-y: auto; padding-right: 8px; }
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
.sub-field { margin-top: 10px; }
.sub-label { font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }
.chip-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.chip { font-size: 12px; color: var(--brand-600); background: var(--brand-50); border: 1px dashed var(--brand-300); border-radius: 999px; padding: 3px 10px; cursor: pointer; transition: all .16s; }
.chip:hover { background: var(--brand-100); }
.pub-row { display: flex; align-items: center; gap: 10px; }
.auto-context { margin-top: 12px; padding: 10px 12px; background: var(--slate-50); border-radius: 8px; }
.ac-title { font-size: 12px; color: var(--text-secondary); font-weight: 600; }
.ac-tag { margin: 4px 4px 0 0; }

/* 新建向导：步骤2 内容来源选择网格 */
.lib-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 16px; }
.lib-col { display: flex; flex-direction: column; }
.lib-label { font-size: 12px; color: var(--text-secondary); font-weight: 600; margin-bottom: 6px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.lib-tip { font-size: 11px; color: var(--text-tertiary); font-weight: 400; }
@media (max-width: 720px) { .lib-grid { grid-template-columns: 1fr; } }

@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .4; } }
.empty { height: 100%; display: flex; align-items: center; justify-content: center; }

/* —— 发布前软文预检弹窗 —— */
.pc-metrics { margin: 12px 0; }
.pc-ok { color: var(--accent-emerald); font-weight: 600; }
.pc-warn { color: var(--amber-500); font-weight: 600; }
.pc-block { margin: 10px 0; }
.pc-block-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.pc-issue-list { margin: 0; padding-left: 18px; max-height: 220px; overflow-y: auto; }
.pc-issue-list li { font-size: 12.5px; line-height: 1.7; color: var(--text-secondary); }
.pc-tip { margin-top: 12px; }

/* 文章改写模式 横幅（P2-3） */
.rewrite-banner {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  margin: 0 0 16px; padding: 16px 20px;
  background: linear-gradient(90deg, #fff7e6 0%, #fffbe6 100%);
  border: 1px solid #ffe58f; border-radius: 12px; cursor: pointer;
}
[data-theme="dark"] .rewrite-banner { background: linear-gradient(90deg, #3a2f12 0%, #2e2a14 100%); border-color: #5c4a16; }
.rewrite-banner__title { font-size: 16px; font-weight: 700; color: #ad6800; }
[data-theme="dark"] .rewrite-banner__title { color: #ffd666; }
.rewrite-banner__desc { margin-top: 4px; font-size: 13px; color: #8a6d3b; }
[data-theme="dark"] .rewrite-banner__desc { color: #c9b78a; }

.rewrite-form { margin-top: 4px; }
.rewrite-result { margin-top: 18px; border-top: 1px dashed var(--border-light); padding-top: 16px; }
.rewrite-risk { display: flex; align-items: center; gap: 18px; margin-bottom: 14px; }
.rewrite-risk__item {
  flex: 1; text-align: center; padding: 12px; border-radius: 10px; background: var(--bg-secondary, #f7f8fa);
  border: 1px solid var(--border-light);
}
.rewrite-risk__label { font-size: 12px; color: var(--text-secondary); }
.rewrite-risk__val { font-size: 26px; font-weight: 800; margin-top: 4px; }
.rewrite-risk__val small { font-size: 12px; font-weight: 600; margin-left: 4px; }
.rewrite-risk__arrow { font-size: 22px; color: var(--text-quaternary); }
.rewrite-risk__engine { font-size: 12px; color: var(--text-secondary); align-self: flex-end; padding-bottom: 12px; }
.is-high { color: #cf1322; border-color: #ffa39e !important; background: #fff1f0 !important; }
.is-mid { color: #d46b08; border-color: #ffd591 !important; background: #fff7e6 !important; }
.is-low { color: #389e0d; border-color: #b7eb8f !important; background: #f6ffed !important; }
.rewrite-out__head { display: flex; align-items: center; justify-content: space-between; margin: 12px 0 6px; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.rewrite-out { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; }
.rewrite-issues { margin-top: 12px; }
.rewrite-issues__title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.rewrite-issues ul { margin: 0; padding-left: 18px; }
.rewrite-issues li { font-size: 12.5px; line-height: 1.7; color: var(--text-secondary); }
</style>
