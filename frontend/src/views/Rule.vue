<template>
  <div class="rule-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button :icon="MagicStick" @click="seedDefaults" :loading="seeding">一键灌入默认模板</el-button>
      <el-button :icon="Upload" @click="openBatchImport">批量导入</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建规则</el-button>
    </Teleport>

    <!-- 三大规则库概览（可点击切换） -->
    <div class="rule-overview">
      <div
        v-for="(m, key) in TYPE_META"
        :key="key"
        class="overview-card"
        :class="{ active: activeTab === key }"
        :style="{ '--rc': m.color }"
        @click="activeTab = key"
      >
        <div class="overview-icon"><el-icon><component :is="m.icon" /></el-icon></div>
        <div class="overview-main">
          <div class="overview-name">{{ m.label }}</div>
          <div class="overview-count"><b>{{ counts[key] || 0 }}</b> 条规则</div>
        </div>
      </div>
    </div>

    <!-- 批量导入提示词板块：让其他 AI 把任意格式规则转成可导入格式 -->
    <div class="rule-import-prompt-banner">
      <div class="rip-head" @click="ripOpen = !ripOpen">
        <el-icon class="rip-icon"><MagicStick /></el-icon>
        <div class="rip-head-text">
          <span class="rip-title">批量导入提示词</span>
          <span class="rip-hint">把下面这段发给任意 AI（ChatGPT / Claude / 通义 / DeepSeek），它能把你手里各种格式的规则整理成本系统可直接批量导入的格式</span>
        </div>
        <el-icon class="rip-chevron" :class="{ 'is-open': ripOpen }"><ArrowDown /></el-icon>
      </div>
      <div v-show="ripOpen" class="rip-body">
        <el-input :model-value="promptText" type="textarea" :rows="14" readonly class="rip-textarea" />
        <div class="rip-foot">
          <el-button type="primary" :icon="CopyDocument" @click="copyRuleImportPrompt">一键复制提示词</el-button>
          <el-button :icon="MagicStick" @click="loadPrompt" :loading="promptLoading">重新生成</el-button>
          <el-button :icon="Upload" @click="openBatchImport">打开批量导入</el-button>
          <span class="rip-tip" v-if="promptMeta">基于 <b>{{ promptMeta.existing_count }}</b> 条已有规则生成</span>
        </div>
      </div>
    </div>

    <!-- 当前类型说明 -->
    <div class="rule-desc" :style="{ '--rc': TYPE_META[activeTab].color }">
      <el-icon><component :is="TYPE_META[activeTab].icon" /></el-icon>
      <span>{{ TYPE_META[activeTab].desc }}</span>
    </div>

    <!-- 规则列表 -->
    <div class="rule-list" v-loading="loading">
      <div v-for="(r, idx) in list" :key="r.id" class="rule-card" :data-focus-id="r.id" :style="{ '--rc': TYPE_META[activeTab].color }">
        <span class="rule-card__stripe"></span>
        <div class="rule-card__left">
          <span class="rule-card__no">{{ idx + 1 }}</span>
          <div class="rule-card__body">
            <div class="rule-card__content">{{ r.content }}</div>
            <div class="rule-card__meta">
              <span class="status-dot" :class="r.status ? 'on' : 'off'"></span>
              <span class="status-text">{{ r.status ? '已启用' : '已停用' }}</span>
              <el-tag v-if="r.platform_ids && r.platform_ids !== 'all'" size="small" type="info" effect="plain">指定平台</el-tag>
              <span class="rule-card__time">排序 {{ r.sort }}</span>
            </div>
          </div>
        </div>
        <div class="rule-card__actions">
          <el-switch v-model="r.status" :active-value="1" :inactive-value="0" size="small" @change="toggleStatus(r)" />
          <el-button text size="small" :icon="Edit" @click="openEdit(r)">编辑</el-button>
          <el-button text size="small" type="danger" :icon="Delete" @click="remove(r)">删除</el-button>
        </div>
      </div>
      <EmptyState v-if="!loading && list.length === 0" title="暂无规则" description="点击右上角「新建规则」或「批量导入」" icon="SetUp" />
    </div>

    <!-- 弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑规则' : '新建规则'" width="560px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="规则类型">
          <el-select v-model="form.rule_type" style="width: 100%;">
            <el-option label="AI SEO 规则" value="ai_seo" />
            <el-option label="去 AI 味规则" value="anti_ai" />
            <el-option label="平台合规规则" value="compliance" />
            <el-option label="创作规则" value="creation" />
          </el-select>
        </el-form-item>
        <el-form-item label="规则内容">
          <el-input v-model="form.content" type="textarea" :rows="4" placeholder="输入规则内容" />
        </el-form-item>
        <el-form-item label="适用平台">
          <el-input v-model="form.platform_ids" placeholder="all 表示全部，或输入平台ID逗号分隔" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.status" :active-value="1" :inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入 -->
    <el-dialog v-model="batchDialog" title="批量导入规则" width="600px" @closed="resetBatch">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        <template #title>每行一条规则</template>
        将导入到当前选中的类型：<b>{{ TYPE_META[activeTab].label }}</b>。也可上传 .txt / .csv 文件（每行一条），或先下载模板。
      </el-alert>
      <el-form label-width="80px">
        <el-form-item label="规则内容">
          <el-input v-model="batchText" type="textarea" :rows="10" placeholder="每行一条规则内容" />
        </el-form-item>
        <el-form-item label="或上传文件">
          <el-upload
            action="#"
            :auto-upload="false"
            :show-file-list="true"
            :on-change="handleBatchFile"
            :before-upload="() => false"
            accept=".txt,.csv"
            style="width: 100%;"
          >
            <el-button :icon="Document">选择文件</el-button>
            <template #tip><div class="rip-form-hint">支持 .txt / .csv（每行一条规则）</div></template>
          </el-upload>
        </el-form-item>
        <el-form-item v-if="batchCount > 0">
          <div class="rip-batch-preview">待导入 <b>{{ batchCount }}</b> 条</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button text @click="downloadRuleTemplate">下载模板</el-button>
        <el-button @click="batchDialog = false">取消</el-button>
        <el-button type="primary" @click="doBatchImport" :loading="saving" :disabled="batchCount === 0">
          导入 {{ batchCount || '' }} 条
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, inject, markRaw } from 'vue'
import { useRoute } from 'vue-router'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFocusScroll } from '../composables/useFocusScroll'
import { Plus, Edit, Delete, Upload, TrendCharts, MagicStick, Lock, SetUp, ArrowDown, CopyDocument, Document } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { ruleApi } from '../api'
import EmptyState from '../components/EmptyState.vue'

const TYPE_META = {
  ai_seo: { label: 'AI SEO 规则', color: '#2563eb', desc: '指导内容在搜索引擎与 AI 收录中更易被检索、引用、获得排名。', icon: markRaw(TrendCharts) },
  anti_ai: { label: '去 AI 味规则', color: '#7c3aed', desc: '约束行文口吻与结构，降低机械感、提升真人可读性。', icon: markRaw(MagicStick) },
  compliance: { label: '平台合规规则', color: '#d97706', desc: '满足各平台内容合规要求，规避限流、下架等风险。', icon: markRaw(Lock) },
  creation: { label: '创作规则', color: '#059669', desc: '结构化优先、数据案例驱动、语言精准化，让内容同时被 AI 提取与用户信任。', icon: markRaw(Document) },
}

const store = useAppStore()
const route = useRoute()
const loading = ref(false)
const saving = ref(false)
const activeTab = ref('ai_seo')
const list = ref([])
const dialogVisible = ref(false)
const editing = ref(false)
const form = ref({ rule_type: 'ai_seo', content: '', platform_ids: 'all', status: 1 })
const batchDialog = ref(false)
const batchText = ref('')
const counts = ref({ ai_seo: 0, anti_ai: 0, compliance: 0, creation: 0 })
const seeding = ref(false)

// 辅助提示词板块
const ripOpen = ref(false)
const promptText = ref('')
const promptLoading = ref(false)
const promptMeta = ref(null)

async function loadPrompt() {
  if (!store.currentIndustryId) return
  promptLoading.value = true
  try {
    const res = await ruleApi.assistantPrompt(store.currentIndustryId)
    promptText.value = res.data.prompt
    promptMeta.value = { existing_count: res.data.existing_count, counts: res.data.counts }
  } catch (e) {
    ElMessage.error('生成提示词失败：' + (e?.response?.data?.detail || ''))
  } finally { promptLoading.value = false }
}

// 展开时自动加载（仅首次）
watch(ripOpen, (v) => {
  if (v && !promptText.value) loadPrompt()
})

function copyRuleImportPrompt() {
  if (!promptText.value) { ElMessage.warning('提示词未加载，请先展开面板'); return }
  navigator.clipboard.writeText(promptText.value)
    .then(() => ElMessage.success('已复制提示词，粘贴给任意 AI 即可'))
    .catch(() => ElMessage.error('复制失败，请手动选择文本复制'))
}

async function loadList() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const res = await ruleApi.list(store.currentIndustryId, activeTab.value)
    list.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function loadCounts() {
  if (!store.currentIndustryId) return
  try {
    const types = ['ai_seo', 'anti_ai', 'compliance', 'creation']
    const results = await Promise.all(types.map(t => ruleApi.list(store.currentIndustryId, t)))
    types.forEach((t, i) => { counts.value[t] = (results[i].data || []).length })
  } catch {}
}

function openCreate() {
  editing.value = false
  form.value = { rule_type: activeTab.value, content: '', platform_ids: 'all', status: 1, industry_id: store.currentIndustryId }
  dialogVisible.value = true
}

function openEdit(r) {
  editing.value = true
  form.value = { ...r }
  dialogVisible.value = true
}

async function save() {
  if (!form.value.content?.trim()) { ElMessage.warning('请输入规则内容'); return }
  saving.value = true
  try {
    if (editing.value) {
      await ruleApi.update(form.value.id, form.value)
    } else {
      await ruleApi.create(form.value)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await loadList()
    await loadCounts()
  } finally {
    saving.value = false
  }
}

async function remove(r) {
  await ElMessageBox.confirm('确定删除该规则吗？', '提示', { type: 'warning' })
  await ruleApi.delete(r.id)
  ElMessage.success('删除成功')
  await loadList()
  await loadCounts()
}

async function toggleStatus(r) {
  await ruleApi.toggleStatus(r.id, r.status)
  ElMessage.success(r.status ? '已启用' : '已停用')
}

function openBatchImport() {
  batchText.value = ''
  batchDialog.value = true
}

async function doBatchImport() {
  const contents = batchText.value.split('\n').map(s => s.trim()).filter(Boolean)
  if (!contents.length) { ElMessage.warning('请输入规则内容'); return }
  saving.value = true
  try {
    await ruleApi.batchImport({
      industry_id: store.currentIndustryId,
      rule_type: activeTab.value,
      contents,
      platform_ids: 'all',
    })
    ElMessage.success(`已导入 ${contents.length} 条`)
    batchDialog.value = false
    await loadList()
    await loadCounts()
  } finally {
    saving.value = false
  }
}

const batchCount = computed(() => batchText.value.split('\n').map(s => s.trim()).filter(Boolean).length)

function handleBatchFile(file) {
  const f = file.raw || file
  if (!f) return
  const reader = new FileReader()
  reader.onload = (e) => {
    batchText.value = e.target.result || ''
    ElMessage.info(`已读取文件：${file.name}，共 ${batchCount.value} 条`)
  }
  reader.readAsText(f)
}

function downloadRuleTemplate() {
  const sample = [
    '核心关键词在标题、首段、小标题中自然出现，避免堆砌',
    '多用短句和口语化表达，避免长难句与从句堆砌',
    '联系方式仅在文末出现一次，不在正文中穿插',
  ]
  const blob = new Blob([sample.join('\n')], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'rule_import_template.txt'
  a.click()
  URL.revokeObjectURL(url)
}

function resetBatch() {
  batchText.value = ''
}

async function seedDefaults() {
  try {
    await ElMessageBox.confirm('将为四大规则库灌入默认模板（已有规则的类型会跳过），是否继续？', '一键灌入默认模板', { type: 'info' })
  } catch { return }
  seeding.value = true
  try {
    const res = await ruleApi.seedDefaults(store.currentIndustryId)
    ElMessage.success(res.data.msg || '灌入完成')
    await loadList()
    await loadCounts()
  } catch (e) {
    ElMessage.error('灌入失败：' + (e?.response?.data?.detail || '请重试'))
  } finally {
    seeding.value = false
  }
}

watch(() => store.currentIndustryId, async () => { await loadList(); await loadCounts() })
watch(activeTab, loadList)
// 全局搜索跳转：自动切到结果所在的规则类型标签
watch(() => route.query.tab, (t) => { if (t) activeTab.value = t }, { immediate: true })
useFocusScroll()
onMounted(async () => { await loadCounts(); await loadList() })
</script>

<style scoped>
.rule-view { display: flex; flex-direction: column; gap: 16px; }

/* 三大规则库概览卡 */
.rule-overview {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.overview-card {
  display: flex; align-items: center; gap: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 14px 16px;
  cursor: pointer;
  border-left: 3px solid var(--rc);
}
.overview-card:hover { box-shadow: var(--shadow-sm); }
.overview-card.active { border-color: var(--rc); background: color-mix(in srgb, var(--rc) 6%, var(--bg-card)); }
.overview-icon {
  width: 36px; height: 36px; border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--rc) 12%, transparent);
  color: var(--rc); font-size: 18px; flex-shrink: 0;
}
.overview-main { min-width: 0; }
.overview-name { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.overview-count { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }
.overview-count b { color: var(--rc); font-size: 14px; }

/* 类型说明条 */
.rule-desc {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; color: var(--text-secondary); line-height: 1.6;
  background: color-mix(in srgb, var(--rc) 7%, var(--bg-card));
  border: 1px solid color-mix(in srgb, var(--rc) 25%, var(--border-light));
  border-radius: var(--radius-md);
  padding: 10px 14px;
}
.rule-desc .el-icon { color: var(--rc); font-size: 16px; flex-shrink: 0; }

.rule-list { display: flex; flex-direction: column; gap: 8px; min-height: 200px; }
.rule-card {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 14px 20px 14px 16px;
  position: relative;
  overflow: hidden;
}
.rule-card:hover { box-shadow: var(--shadow-sm); }
.rule-card__stripe { position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--rc); }
.rule-card__left { display: flex; align-items: center; gap: 14px; flex: 1; min-width: 0; }
.rule-card__no {
  width: 28px; height: 28px;
  border-radius: var(--radius-full);
  background: color-mix(in srgb, var(--rc) 12%, transparent);
  color: var(--rc);
  font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.rule-card__body { flex: 1; min-width: 0; }
.rule-card__content { font-size: 13.5px; color: var(--text-primary); line-height: 1.6; margin-bottom: 6px; }
.rule-card__meta { display: flex; align-items: center; gap: 8px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.status-dot.on { background: #16a34a; }
.status-dot.off { background: var(--text-tertiary); }
.status-text { font-size: 12px; color: var(--text-secondary); }
.rule-card__time { font-size: 12px; color: var(--text-tertiary); }
.rule-card__actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

@media (max-width: 1024px) {
  .rule-overview { grid-template-columns: 1fr; }
}

/* 批量导入提示词板块 */
.rule-import-prompt-banner {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-left: 3px solid #7c3aed;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.rip-head { display: flex; align-items: center; gap: 12px; padding: 12px 16px; cursor: pointer; }
.rip-icon { color: #7c3aed; font-size: 18px; flex-shrink: 0; }
.rip-head-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.rip-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.rip-hint { font-size: 12px; color: var(--text-tertiary); line-height: 1.5; }
.rip-chevron { color: var(--text-tertiary); transition: transform .2s; flex-shrink: 0; }
.rip-chevron.is-open { transform: rotate(180deg); }
.rip-body { padding: 0 16px 14px; }
.rip-textarea :deep(.el-textarea__inner) { font-family: 'SF Mono', 'Monaco', monospace; font-size: 12px; }
.rip-foot { display: flex; align-items: center; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
.rip-tip { font-size: 12px; color: var(--text-tertiary); }
.rip-form-hint { font-size: 12px; color: var(--text-tertiary); line-height: 1.5; margin-top: 2px; }
.rip-batch-preview { font-size: 13px; color: var(--text-secondary); background: color-mix(in srgb, #7c3aed 8%, var(--bg-card)); padding: 8px 12px; border-radius: var(--radius-md); width: 100%; }
.rip-batch-preview b { color: #7c3aed; }
</style>
