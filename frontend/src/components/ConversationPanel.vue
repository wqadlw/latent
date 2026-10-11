<template>
  <div class="conv">
    <!-- 头部：统计 + 刷新 -->
    <div class="conv__head">
      <div class="conv__title">
        <el-icon><ChatDotRound /></el-icon>
        <span>创作对话 · 主编指令↔写手改写</span>
      </div>
      <div class="conv__stats">
        <el-tag size="small" type="info" v-if="data.mode">模式：{{ modeLabel(data.mode) }}</el-tag>
        <el-tag size="small" type="warning" v-if="reviseRounds.length">整改 {{ reviseRounds.length }} 轮</el-tag>
        <el-tag size="small" class="role-planner">{{ plannerMsgs.length }} 条主编</el-tag>
        <el-tag size="small" class="role-writer">{{ writerMsgs.length }} 条写手</el-tag>
      </div>
      <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <div v-if="loading && !allMessages.length" class="conv-empty"><el-icon class="is-loading"><Loading /></el-icon> 加载创作对话…</div>
    <div v-else-if="!data.has_data" class="conv-empty">暂无创作对话（运行开始后逐步生成主编指令与写手产出）</div>

    <template v-else>
      <!-- 区块一：主编↔写手 对话流（按时间混合） -->
      <div class="conv-section-title"><span class="bar"></span>主编 ↔ 写手 对话流</div>
      <div
        v-for="m in allMessages"
        :key="m.index"
        class="bubble-row"
        :class="['sp-' + (m.agent || 'system'), m.agent === 'writer' ? 'is-writer' : 'is-planner']"
      >
        <div class="bubble-avatar" :class="m.agent === 'writer' ? 'av-writer' : 'av-planner'">
          {{ m.agent === 'writer' ? '写手' : '主编' }}
        </div>
        <div class="bubble">
          <div class="bubble__head">
            <span class="bubble__stage">{{ m.title || m.step_key }}</span>
            <el-tag size="small" class="bubble__tag">{{ stepKeyLabel(m.step_key) }}</el-tag>
            <span v-if="m.latency_ms" class="bubble__lat">{{ m.latency_ms }} ms</span>
            <el-button size="small" text :icon="DocumentCopy" class="bubble__copy" @click="copyText(m.text, m.title || m.step_key)">复制</el-button>
          </div>
          <pre class="bubble__text" v-if="m.text">{{ m.text }}</pre>
          <div v-else class="bubble__empty">（无文本产出）</div>
        </div>
      </div>

      <!-- 区块二：整改多轮（最结构化的主编指令→写手改写→主编评语） -->
      <template v-if="reviseRounds.length">
        <div class="conv-section-title"><span class="bar"></span>整改多轮对话（主编指令 → 写手改写 → 主编评语）</div>
        <div v-for="r in reviseRounds" :key="r.round" class="revise-card">
          <div class="revise-card__head">
            <span class="revise-badge">第 {{ r.round }} 轮</span>
            <el-tag size="small" :type="r.gate_pass ? 'success' : 'danger'">
              GEO {{ r.geo_score ?? '—' }} {{ r.gate_pass ? '达标' : '待优化' }}
            </el-tag>
            <span class="revise-meta">改写前 {{ r.before_len ?? '—' }} 字 → 改写后 {{ r.after_len ?? '—' }} 字</span>
          </div>

          <div class="revise-block is-planner">
            <div class="revise-block__label"><i class="dot dot-planner"></i>主编·整改指令</div>
            <pre class="revise-block__text" v-if="r.planner_directives">{{ r.planner_directives }}</pre>
            <div v-else class="revise-block__empty">（无指令）</div>
          </div>

          <div class="revise-block is-writer">
            <div class="revise-block__label"><i class="dot dot-writer"></i>写手·改写后</div>
            <pre class="revise-block__text" v-if="r.after">{{ r.after }}</pre>
            <div v-else class="revise-block__empty">（无改写稿）</div>
          </div>

          <div class="revise-block is-planner" v-if="r.editor_review">
            <div class="revise-block__label"><i class="dot dot-planner"></i>主编·本轮评语</div>
            <pre class="revise-block__text">{{ r.editor_review }}</pre>
          </div>

          <div class="revise-block__issues" v-if="r.issues && r.issues.length">
            <span class="issues-label">遗留问题：</span>
            <span v-for="(it, i) in r.issues.slice(0, 5)" :key="i" class="issue-chip">{{ it }}</span>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { ChatDotRound, Refresh, DocumentCopy, Loading } from '@element-plus/icons-vue'
import { browserStudioApi } from '../api'
import { copyText } from '../utils/clipboard'
import { modeLabel } from '../constants/modes'

const props = defineProps({
  runId: { type: Number, required: true },
  running: { type: Boolean, default: false },
})

const data = ref({ has_data: false, revise_rounds: [], planner_messages: [], writer_messages: [], mode: '' })
const loading = ref(false)
let pollTimer = null

const reviseRounds = computed(() => data.value.revise_rounds || [])
const plannerMsgs = computed(() => data.value.planner_messages || [])
const writerMsgs = computed(() => data.value.writer_messages || [])
const allMessages = computed(() =>
  [...plannerMsgs.value, ...writerMsgs.value].sort((a, b) => (a.index || 0) - (b.index || 0))
)

async function load() {
  if (!props.runId) return
  loading.value = true
  try {
    const res = await browserStudioApi.conversation(props.runId)
    // 拦截器已拆掉 axios 外壳，res 就是后端体 { code, data }。
    // 原先写 res.data.data —— 多拆一层，恒为 undefined，于是每次都回退到初始值
    // `{ has_data: false, ... }`：这个「创作对话」面板从来没能显示出任何一条消息。
    data.value = res?.data || data.value
  } catch (e) { /* 拦截器已提示 */ }
  finally { loading.value = false }
}

// ============ 展示辅助 ============
function stepKeyLabel(k) {
  return {
    clarify: '明晰', outline: '大纲', draft: '初稿', depolish: '去AI味',
    geo: 'GEO终稿', review: '评审', revise: '整改', confirm: '确认', publish: '发布',
    clarified_brief: '简报', editor_review: '评语', final: '终稿',
  }[k] || k || '—'
}
// copyText 已抽到 utils/clipboard.js（全站统一实现）

// ============ 轮询 ============
function startPolling() {
  stopPolling()
  if (props.running) pollTimer = setInterval(load, 3000)
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}
watch(() => props.runId, (id) => { if (id) { load(); startPolling() } })
watch(() => props.running, () => startPolling())
onMounted(() => { load(); startPolling() })
onBeforeUnmount(stopPolling)
</script>

<style scoped>
.conv { border: 1px solid var(--border-light); border-radius: var(--radius-lg); padding: 14px 16px; background: var(--bg-page); }
.conv__head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.conv__title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.conv__title .el-icon { color: var(--brand-600); font-size: 18px; }
.conv__stats { display: flex; gap: 8px; flex-wrap: wrap; }
.conv__stats .role-planner { background: #ede9fe; color: #6d28d9; border: none; }
.conv__stats .role-writer { background: #e0f2fe; color: #0369a1; border: none; }
.conv__head .el-button { margin-left: auto; }

.conv-empty { padding: 24px; text-align: center; color: var(--text-quaternary); font-size: 13px; display: flex; align-items: center; justify-content: center; gap: 8px; }

.conv-section-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; color: var(--text-secondary); margin: 14px 0 10px; }
.conv-section-title .bar { width: 4px; height: 14px; border-radius: 2px; background: var(--brand-500); }

/* 对话气泡 */
.bubble-row { display: flex; gap: 10px; margin-bottom: 12px; align-items: flex-start; }
.bubble-row.is-writer { flex-direction: row-reverse; }
.bubble-avatar { flex-shrink: 0; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: #fff; }
.av-planner { background: linear-gradient(135deg, #7c3aed, #6d28d9); }
.av-writer { background: linear-gradient(135deg, #0ea5e9, #0369a1); }
.bubble { max-width: 82%; background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 10px 12px; }
.bubble-row.is-planner .bubble { border-left: 3px solid #7c3aed; }
.bubble-row.is-writer .bubble { border-right: 3px solid #0ea5e9; background: #f0f9ff; }
.bubble__head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.bubble__stage { font-weight: 600; color: var(--text-primary); font-size: 12.5px; }
.bubble__tag { font-size: 10px; }
.bubble__lat { font-size: 10.5px; color: var(--text-tertiary); font-family: var(--font-mono, monospace); }
.bubble__copy { margin-left: auto; }
.bubble__text { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12.5px; line-height: 1.7; color: var(--text-secondary); max-height: 360px; overflow: auto; font-family: var(--font-sans, inherit); }
.bubble__empty { font-size: 12px; color: var(--text-quaternary); }

/* 整改轮次卡 */
.revise-card { border: 1px solid var(--border-light); border-radius: var(--radius-md); background: var(--bg-card); padding: 12px; margin-bottom: 12px; }
.revise-card__head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.revise-badge { font-size: 12px; font-weight: 700; color: #fff; background: var(--brand-600); padding: 2px 10px; border-radius: 10px; }
.revise-meta { font-size: 11.5px; color: var(--text-tertiary); }
.revise-block { border-radius: var(--radius-sm); padding: 8px 10px; margin-bottom: 8px; }
.revise-block.is-planner { background: #f5f3ff; border-left: 3px solid #7c3aed; }
.revise-block.is-writer { background: #f0f9ff; border-left: 3px solid #0ea5e9; }
.revise-block__label { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700; margin-bottom: 5px; }
.revise-block__label .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-planner { background: #7c3aed; } .dot-writer { background: #0ea5e9; }
.revise-block__text { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12.5px; line-height: 1.7; color: var(--text-secondary); max-height: 320px; overflow: auto; font-family: var(--font-sans, inherit); }
.revise-block__empty { font-size: 12px; color: var(--text-quaternary); }
.revise-block__issues { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.issues-label { font-size: 11.5px; color: var(--text-tertiary); }
.issue-chip { font-size: 11px; background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; border-radius: 8px; padding: 1px 8px; }

@media (max-width: 1200px) {
  .bubble { max-width: 88%; }
}
</style>
