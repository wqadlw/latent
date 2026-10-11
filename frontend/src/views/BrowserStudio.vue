<template>
  <div class="studio">
    <!-- 文章改写模式：横幅留在壳里（属于页面布局），功能体在 RewriteDialog -->
    <div class="rewrite-banner" @click="rewriteRef?.open()">
      <div class="rewrite-banner__text">
        <div class="rewrite-banner__title">文章改写模式</div>
        <div class="rewrite-banner__desc">把被判软文 / 低质的文章贴进来，一键按 geo / 平台合规 / 绿色吸粉 模式改写，软文风险从 X 降到 Y。</div>
      </div>
      <el-button type="warning" size="large" @click.stop="rewriteRef?.open()">立即改写 →</el-button>
    </div>

    <!-- 空状态 -->
    <div v-if="!runs.length && !loading" class="empty">
      <el-empty description="还没有浏览器工作室运行">
        <el-button type="primary" @click="openCreate">新建运行</el-button>
      </el-empty>
    </div>

    <WorkbenchLayout v-else class="studio__body" aside-width="300px" fill>
      <template #aside>
        <!-- 左：运行列表（已抽到 views/browser-studio/RunListPanel.vue） -->
        <RunListPanel
          :runs="runs"
          :selected-id="selectedId"
          @select="selectRun"
          @create="openCreate"
          @refresh="loadRuns"
        />
      </template>

      <template #main>
        <!-- 右：运行详情（已抽到 views/browser-studio/RunDetailPanel.vue）。
             空状态也在子组件里 —— 右栏本来就是「要么详情，要么提示去左边选」。 -->
        <RunDetailPanel
          :run="selected"
          @confirm="onConfirm"
          @publish="onPublish"
          @start="onStart"
          @retry="onRetry"
          @retry-publish="onRetryPublish"
          @delete="onDelete"
        />
      </template>
    </WorkbenchLayout>

    <!-- 新建运行对话框（可视化向导）已抽到 views/browser-studio/CreateRunDialog.vue -->
    <CreateRunDialog ref="createRef" :industry-id="industryId()" @created="onRunCreated" />

    <!-- 发布前软文预检（P2-1 / C 项补全）已抽到 views/browser-studio/PrecheckDialog.vue -->
    <PrecheckDialog ref="precheckRef" @proceed="onPrecheckProceed" />

    <!-- 文章改写模式对话框（P2-3）已抽到 views/browser-studio/RewriteDialog.vue -->
    <RewriteDialog ref="rewriteRef" :industry-id="industryId()" />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAppStore } from '../store/app'
import { browserStudioApi } from '../api'
import RewriteDialog from './browser-studio/RewriteDialog.vue'
import PrecheckDialog from './browser-studio/PrecheckDialog.vue'
import CreateRunDialog from './browser-studio/CreateRunDialog.vue'
import RunListPanel from './browser-studio/RunListPanel.vue'
import RunDetailPanel from './browser-studio/RunDetailPanel.vue'
import WorkbenchLayout from '../components/layout/WorkbenchLayout.vue'
// 说明：5 个面板/弹窗抽出后，壳已不再直接渲染任何「步骤 / 状态 / 维度 / 平台」文案，
// 因此 constants/browserStudio 的整套标签函数、StepLogPanel、ConversationPanel、
// copyText、markdownToPlain、formatDateTime、Element 图标，以及共享样式
// studio-shared.css（壳已不用 .mode-chip / .pc-tip）都随各自的面板搬走了。
// 壳现在只管三件事：取数、轮询、动作编排，加上页面级布局（横幅 / 空状态 / 两栏容器）。
// ENGINE_OPTIONS 等向导专属常量在 CreateRunDialog.vue；PLATFORM_OPTIONS 在 RunListPanel.vue。

const store = useAppStore()

const runs = ref([])
const loading = ref(false)
const selectedId = ref(0)
const selected = ref(null)
let pollTimer = null

// 文章改写模式（P2-3）的状态与请求已整体搬进 views/browser-studio/RewriteDialog.vue。
// 壳只保留一个 ref 用来调用它的 open()。
const rewriteRef = ref(null)

// 新建运行向导（5 步）的状态与请求已整体搬进 views/browser-studio/CreateRunDialog.vue。
// 壳只保留一个 ref：调用它的 open()，并在它报告「创建成功」后刷新列表。
const createRef = ref(null)

// 平台选项 / platformLabel 只被运行列表用到，已随 RunListPanel.vue 搬走
// （platformLabel 本来就是 constants/platforms.js 里的既有实现，壳里那份是重复品）。

// engineOptions / pipelineSteps / autoContextTags / expertTeam 已抽到
// constants/browserStudio.js（纯数据，视图里不再重复定义）

// form / libOpts / kwSearch / keywordOptionsByGroup / filteredIntentQuestions /
// selectPlatform / options.doubaoCreds 已随新建向导搬进 CreateRunDialog.vue。
// 这些数据只有那个弹窗用得到，留在壳里等于让壳替弹窗保管状态。

const industryId = () => Number(store.currentIndustryId) || 0

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

// 拉取内容库清单 / 豆包凭证 —— 已随新建向导搬进 CreateRunDialog.vue。

// ============ 操作 ============
function openCreate() {
  createRef.value?.open()
}

/** 新建向导创建成功后的回调：刷新列表并选中刚创建的那条运行。 */
async function onRunCreated(id) {
  await loadRuns()
  if (id) await selectRun(id)
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
// 弹窗自身（取数 + 展示 + 按钮文案）已搬进 views/browser-studio/PrecheckDialog.vue。
// 壳只负责「谁来打开它」和「用户点了继续之后做什么」。
const precheckRef = ref(null)

// 弹窗里点「仍要确认 / 仍要发布」才真正执行
async function onPrecheckProceed(action) {
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

async function onConfirm() {
  precheckRef.value?.open(selected.value?.id, 'confirm')
}

async function onPublish() {
  precheckRef.value?.open(selected.value?.id, 'publish')
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

onMounted(async () => {
  // loadOptions()（内容库/凭证清单）已随新建向导搬进 CreateRunDialog.vue，
  // 由弹窗在打开时自取。壳在这里再调一次会直接 ReferenceError，
  // 导致 loadRuns() 永不执行、运行列表恒为空。
  await loadRuns()
})
onBeforeUnmount(stopPolling)
</script>

<style scoped>
/* 让 .studio 成为 flex 列，工作台才能用 fill（flex:1）撑满 ——
   此前 .studio__body 靠 height:100% 实现，两页的高度策略因此不一致。 */
.studio { height: 100%; display: flex; flex-direction: column; }
/* .studio__body 的布局已收进 WorkbenchLayout（D7-2）：左栏 300px + fill。
   类名保留作为验收钩子。 */

/* .run-list / .run-card 系列（含 .run-card__err、.tag-mock）已随标记搬进
   views/browser-studio/RunListPanel.vue —— 样式跟着标记走，不留孤儿规则。 */

/* .run-detail / .detail-* / .pipeline / .step* / .round* / .review* / .dims / .mdx-* /
   .briefing-* 以及 @keyframes pulse 已随标记搬进
   views/browser-studio/RunDetailPanel.vue —— 样式跟着标记走，不留孤儿规则。 */

.empty { flex: 1; display: flex; align-items: center; justify-content: center; }

/* —— 发布前软文预检弹窗 —— */
/* .pc-* 一组（预检弹窗的指标表 / 问题清单 / 提示条）已随 PrecheckDialog.vue 搬走。
   .pc-tip 例外 —— 它同时被改写弹窗用到，放在 browser-studio/studio-shared.css。 */

/* 文章改写模式 横幅（P2-3）：横幅本身留在本视图，故样式留在这里。
   弹窗内部的 .rewrite-form / .rewrite-risk / .is-high 等已随组件搬到 RewriteDialog.vue。 */
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
</style>
