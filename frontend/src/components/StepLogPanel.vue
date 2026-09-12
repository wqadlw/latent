<template>
  <div class="step-log">
    <!-- 头部：标题 + 图例 + 刷新 -->
    <div class="step-log__head">
      <div class="step-log__title">
        <el-icon><Histogram /></el-icon>
        <span>步骤透明日志 · 全流程可复现</span>
      </div>
      <div class="step-log__legend">
        <span class="lg"><i class="dot dot-ok"></i>命中真实 API</span>
        <span class="lg"><i class="dot dot-mock"></i>模拟演示</span>
        <span class="lg"><i class="dot dot-human"></i>人工 / 系统</span>
      </div>
      <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <!-- 列头：序号 | 当前阶段 | 发送内容摘要 | 等待 API 返回 | 响应耗时 | 提取结果 | 下一步动作 -->
    <div class="sl-grid sl-grid--head">
      <div class="sl-col sl-col--idx">序号</div>
      <div class="sl-col sl-col--stage">当前阶段</div>
      <div class="sl-col sl-col--summary">发送内容摘要</div>
      <div class="sl-col sl-col--expect">等待 API 返回</div>
      <div class="sl-col sl-col--latency">响应耗时</div>
      <div class="sl-col sl-col--extract">提取结果</div>
      <div class="sl-col sl-col--next">下一步动作</div>
    </div>

    <div v-if="loading && !rows.length" class="sl-empty"><el-icon class="is-loading"><Loading /></el-icon> 加载步骤日志…</div>
    <div v-else-if="!rows.length" class="sl-empty">暂无步骤日志（运行开始后逐步生成）</div>

    <template v-else>
      <div
        v-for="r in rows"
        :key="r.index"
        class="sl-row"
        :class="['st-' + r.status, expanded[r.index] ? 'is-open' : '']"
        @click="toggle(r.index)"
      >
        <div class="sl-grid">
          <div class="sl-col sl-col--idx">
            <span class="sl-idx">{{ r.index }}</span>
            <el-tag size="small" :type="stepType(r.status)">{{ stepLabel(r.status) }}</el-tag>
          </div>
          <div class="sl-col sl-col--stage">
            <div class="sl-stage">{{ r.title }}</div>
            <div class="sl-meta">
              <span :class="['sl-role', 'role-' + (r.api_role || 'system')]">{{ roleLabel(r.api_role) }}</span>
              <span v-if="r.api_model && r.api_model !== 'mock-simulator'" class="sl-model">{{ r.api_model }}</span>
            </div>
          </div>
          <div class="sl-col sl-col--summary">
            <span class="sl-summary">{{ r.send_summary }}</span>
            <el-icon v-if="r.request_payload" class="sl-expand-ico"><ArrowRight /></el-icon>
          </div>
          <div class="sl-col sl-col--expect">
            <span v-if="isObj(r.expected_fields)">{{ fieldList(r.expected_fields).join('、') }}</span>
            <span v-else class="muted">—</span>
          </div>
          <div class="sl-col sl-col--latency">
            <span v-if="r.response_latency_ms" :class="latClass(r)">{{ r.response_latency_ms }} ms</span>
            <span v-else class="muted">—</span>
          </div>
          <div class="sl-col sl-col--extract">
            <span class="sl-extract">{{ r.extracted_result || '—' }}</span>
          </div>
          <div class="sl-col sl-col--next">
            <span class="sl-next">{{ r.next_action || '—' }}</span>
          </div>
        </div>

        <!-- 展开：完整发送内容（可直接复制复现） -->
        <div v-if="expanded[r.index]" class="sl-detail" @click.stop>
          <div class="sl-detail__head">
            <span>发送给 API 的完整内容（复制后粘贴给任意网页 AI 即可复现本步骤）</span>
            <el-button size="small" :icon="DocumentCopy" @click="copyText(r.request_payload, '步骤 ' + r.index + ' 发送内容')">复制完整发送内容</el-button>
          </div>
          <pre class="sl-payload" v-if="r.request_payload">{{ r.request_payload }}</pre>
          <div v-else class="sl-nopayload">本步骤为系统 / 人工步骤，不调用 API。</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Histogram, Refresh, ArrowRight, DocumentCopy, Loading } from '@element-plus/icons-vue'
import { browserStudioApi } from '../api'

const props = defineProps({
  runId: { type: Number, required: true },
  running: { type: Boolean, default: false },
})

const rows = ref([])
const loading = ref(false)
const expanded = reactive({})
let pollTimer = null

async function load() {
  if (!props.runId) return
  loading.value = true
  try {
    const res = await browserStudioApi.stepLogs(props.runId)
    rows.value = (res.data && res.data.rows) || []
  } catch (e) { /* 拦截器已提示 */ }
  finally { loading.value = false }
}

function toggle(i) { expanded[i] = !expanded[i] }

// ============ 展示辅助 ============
function stepLabel(s) {
  return { pending: '待执行', running: '执行中', done: '完成', failed: '失败', skipped: '跳过' }[s] || s || '—'
}
function stepType(s) {
  return { pending: 'info', running: 'primary', done: 'success', failed: 'danger', skipped: 'info' }[s] || 'info'
}
function roleLabel(role) {
  return {
    research: '🔍 选题调研', writing: '✍️ 正文撰写', review: '🔎 审核优化',
    general: '⚙️ 通用', human: '👤 人工确认', system: '⚙️ 系统',
  }[role] || (role ? role : '⚙️ 系统')
}
function isObj(v) {
  return v && typeof v === 'object' && Object.keys(v).length
}
function fieldList(obj) {
  if (!isObj(obj)) return []
  return Object.keys(obj)
}
function latClass(r) {
  if (r.api_role === 'human' || r.api_role === 'system') return 'lat-human'
  if ((r.api_model || '').includes('mock')) return 'lat-mock'
  return 'lat-ok'
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
    ElMessage.success(`已复制：${label}`)
  } catch (e) { ElMessage.error('复制失败，请手动选择文本复制') }
}

// ============ 轮询 ============
function startPolling() {
  stopPolling()
  if (props.running) {
    pollTimer = setInterval(load, 2500)
  }
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

watch(() => props.runId, (id) => { if (id) { Object.keys(expanded).forEach(k => delete expanded[k]); load(); startPolling() } })
watch(() => props.running, () => startPolling())

onMounted(() => { load(); startPolling() })
onBeforeUnmount(stopPolling)
</script>

<style scoped>
.step-log { border: 1px solid var(--border-light); border-radius: var(--radius-lg); padding: 14px 16px; background: var(--bg-page); }
.step-log__head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.step-log__title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.step-log__title .el-icon { color: var(--brand-600); font-size: 18px; }
.step-log__legend { display: flex; gap: 12px; font-size: 11px; color: var(--text-tertiary); }
.step-log__legend .lg { display: inline-flex; align-items: center; gap: 4px; }
.step-log__legend .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-ok { background: #10b981; } .dot-mock { background: #f59e0b; } .dot-human { background: #64748b; }
.step-log__head .el-button { margin-left: auto; }

/* 网格布局：7 列 */
.sl-grid {
  display: grid;
  grid-template-columns: 64px 1.5fr 1.7fr 1.2fr 88px 1.5fr 1.5fr;
  gap: 10px; align-items: start;
}
.sl-grid--head {
  font-size: 11px; font-weight: 700; color: var(--text-tertiary);
  padding: 6px 10px; border-bottom: 1px solid var(--border-light); margin-bottom: 4px;
  position: sticky; top: 0; background: var(--bg-page); z-index: 1;
}
.sl-col { font-size: 12px; color: var(--text-secondary); line-height: 1.5; min-width: 0; }
.sl-col--summary, .sl-col--extract, .sl-col--next { word-break: break-word; }
.sl-col--idx { display: flex; align-items: center; gap: 6px; }
.sl-idx { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: var(--slate-200); color: var(--text-primary); font-size: 12px; font-weight: 700; flex-shrink: 0; }
.sl-stage { font-weight: 600; color: var(--text-primary); font-size: 12.5px; }
.sl-meta { display: flex; align-items: center; gap: 6px; margin-top: 3px; flex-wrap: wrap; }
.sl-role { font-size: 10.5px; font-weight: 700; padding: 1px 7px; border-radius: 9px; white-space: nowrap; }
.role-research { background: #ede9fe; color: #6d28d9; }
.role-writing { background: #e0f2fe; color: #0369a1; }
.role-review { background: #dcfce7; color: #15803d; }
.role-general { background: #f1f5f9; color: #475569; }
.role-human { background: #fef3c7; color: #b45309; }
.role-system { background: #f1f5f9; color: #475569; }
.sl-model { font-size: 10.5px; color: var(--text-tertiary); font-family: var(--font-mono, monospace); }
.sl-summary { color: var(--text-secondary); }
.sl-expand-ico { color: var(--text-quaternary); vertical-align: middle; transition: transform .16s; }
.sl-row.is-open .sl-expand-ico { transform: rotate(90deg); color: var(--brand-500); }
.muted { color: var(--text-quaternary); }
.sl-lat { font-weight: 700; font-family: var(--font-mono, monospace); }
.lat-ok { color: #10b981; } .lat-mock { color: #f59e0b; } .lat-human { color: #64748b; }
.sl-extract, .sl-next { color: var(--text-secondary); }

/* 行 */
.sl-row { border: 1px solid var(--border-light); border-radius: var(--radius-md); background: var(--bg-card); padding: 8px 10px; margin-bottom: 6px; cursor: pointer; transition: all .16s; }
.sl-row:hover { border-color: var(--brand-300); }
.sl-row.st-running { border-color: var(--brand-400); box-shadow: 0 0 0 2px var(--brand-100); }
.sl-row.st-failed { border-color: var(--red-300); }
.sl-row.st-done { border-color: #bbf7d0; }
.sl-row.is-open { border-color: var(--brand-500); }

.sl-detail { margin-top: 8px; border-top: 1px dashed var(--border-light); padding-top: 8px; }
.sl-detail__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 11.5px; color: var(--text-tertiary); margin-bottom: 6px; }
.sl-payload { background: #0f172a; color: #e2e8f0; border-radius: var(--radius-sm); padding: 12px 14px; font-size: 12px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; max-height: 420px; overflow: auto; margin: 0; font-family: var(--font-mono, monospace); }
.sl-nopayload { font-size: 12px; color: var(--text-quaternary); padding: 8px 0; }
.sl-empty { padding: 24px; text-align: center; color: var(--text-quaternary); font-size: 13px; display: flex; align-items: center; justify-content: center; gap: 8px; }

@media (max-width: 1200px) {
  .sl-grid { grid-template-columns: 56px 1.4fr 1.6fr 1fr 80px 1.4fr 1.4fr; }
}
</style>
