<template>
  <div class="settings-page">
    <div class="page-head">
      <div>
        <h2>LLM 配置</h2>
        <p class="sub">配置 DeepSeek 大模型，用于软文生产「一键生成」。与「复制提示词给 AI → 粘贴结果回系统」的手动模式并存，互不排斥。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增配置</el-button>
    </div>

    <!-- ============ 三 API 角色配置向导 ============ -->
    <div class="role-wizard">
      <div class="rw-head">
        <h3>三 API 智能调度 · 角色配置向导</h3>
        <span class="rw-sub">浏览器工作室自动化发布按任务类型分流，请为每个角色各添加一个 DeepSeek API（可用不同 Key 实现账号隔离）</span>
      </div>
      <div class="rw-grid">
        <div v-for="r in roleWizard" :key="r.role" class="rw-card" :class="{ 'rw-card--ok': r.has }">
          <div class="rw-card__head">
            <span class="rw-chip" :class="'rw-' + r.role">{{ r.short }}</span>
            <span class="rw-title">{{ r.label }}</span>
          </div>
          <div class="rw-card__desc">{{ r.desc }}</div>
          <div v-if="r.configs.length" class="rw-card__cfgs">
            <div v-for="c in r.configs" :key="c.id" class="rw-cfg-line">
              <span class="rw-cfg-name">{{ c.name }}</span>
              <span class="rw-cfg-model">{{ c.model }}</span>
            </div>
          </div>
          <div v-else class="rw-card__empty">未配置 · 将用 general 兜底</div>
          <el-button size="small" :type="r.has ? 'default' : 'primary'" plain :icon="Plus" @click="quickAddRole(r.role)">
            {{ r.has ? '再加一个' : '为该角色添加配置' }}
          </el-button>
        </div>
      </div>
      <el-alert
        class="rw-tip" :type="wizardAllOk ? 'success' : 'warning'" :closable="false" show-icon
        :title="wizardAllOk ? '三角色均已配置真实 API，自动化调度已就绪' : '提示：三角色各配一个 API Key（可用不同账号），即可实现按任务类型分流 + 负载均衡 + 故障自动切换'"
        description="research→选题调研/大纲；writing→正文撰写/精修/GEO终稿；review→审核优化/整改。在「自动化指挥中心」可查看实时调度状态与每次调用耗时。"
      />
    </div>

    <!-- ============ 配置列表（卡片式） ============ -->
    <div class="cfg-list">
      <div class="cfg-list__head">
        <h3>全部 LLM 配置 <span class="cfg-count">{{ configs.length }} 个</span></h3>
        <div class="cfg-list__ops">
          <el-input v-model="search" placeholder="搜索名称/模型/角色…" :prefix-icon="Search" clearable size="small" style="width:220px" />
        </div>
      </div>

      <div v-loading="loading" class="cfg-grid">
        <div v-for="row in filteredConfigs" :key="row.id" class="cfg-item" :class="{ 'cfg-item--off': row.status !== 1 }">
          <div class="cfg-item__top">
            <div class="cfg-item__name-line">
              <span class="cfg-item__name">{{ row.name }}</span>
              <span v-if="row.is_default" class="cfg-chip cfg-chip--default">默认</span>
            </div>
            <div class="cfg-item__role-line">
              <span class="cfg-chip" :class="'cfg-chip--' + (row.role || 'general')">{{ roleLabel(row.role) }}</span>
              <span class="cfg-item__provider">{{ providerLabel(row.provider) }}</span>
            </div>
          </div>
          <div class="cfg-item__mid">
            <div class="cfg-meta"><span class="cfg-meta__k">模型</span><span class="cfg-meta__v">{{ row.model || '—' }}</span></div>
            <div class="cfg-meta"><span class="cfg-meta__k">字数</span><span class="cfg-meta__v">{{ row.max_tokens || 2000 }}</span></div>
            <div class="cfg-meta"><span class="cfg-meta__k">超时</span><span class="cfg-meta__v">{{ row.timeout || 60 }}s</span></div>
            <div class="cfg-meta"><span class="cfg-meta__k">状态</span>
              <span class="cfg-status" :class="row.status === 1 ? 'cfg-status--on' : 'cfg-status--off'">
                {{ row.status === 1 ? '启用' : '停用' }}
              </span>
            </div>
          </div>
          <div class="cfg-item__actions">
            <el-tooltip content="测试连接" placement="top">
              <button class="act-btn act-btn--test" :class="{ 'is-loading': row._testing }" @click="testConfig(row)">
                <el-icon><Connection /></el-icon>
              </button>
            </el-tooltip>
            <el-tooltip content="设为默认" placement="top">
              <button class="act-btn" :disabled="row.is_default" @click="setDefault(row)">
                <el-icon><Star /></el-icon>
              </button>
            </el-tooltip>
            <el-tooltip content="编辑" placement="top">
              <button class="act-btn act-btn--edit" @click="openEdit(row)">
                <el-icon><Edit /></el-icon>
              </button>
            </el-tooltip>
            <el-tooltip content="删除" placement="top">
              <button class="act-btn act-btn--del" @click="remove(row)">
                <el-icon><Delete /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
        <el-empty v-if="!filteredConfigs.length && !loading" description="暂无 LLM 配置，点击右上角新增" />
      </div>
    </div>

    <!-- ============ 编辑/新增对话框 ============ -->
    <el-dialog v-model="dialogVisible" :title="editing.id ? '编辑 LLM 配置' : '新增 LLM 配置'" width="580px" top="6vh">
      <el-form :model="form" label-width="96px" class="cfg-form">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="如：选题调研 API" />
        </el-form-item>
        <el-form-item label="供应商">
          <el-select v-model="form.provider" @change="onProviderChange" style="width:100%">
            <el-option v-for="p in providers" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key" required>
          <el-input v-model="form.api_key" type="password" show-password placeholder="sk-...（仅保存在本地数据库）" />
        </el-form-item>
        <el-form-item label="接口地址">
          <el-input v-model="form.base_url" placeholder="留空使用供应商默认地址" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="form.model" placeholder="如 deepseek-v4-pro" />
          <div class="form-hint">DeepSeek v4 推荐 <b>deepseek-v4-pro</b>（开启 thinking 推理，规划/评审质量更高）；也可用 deepseek-v4-flash。旧的 deepseek-chat / deepseek-reasoner 将于 2026/07/24 弃用。</div>
        </el-form-item>
        <el-form-item label="调度角色">
          <el-select v-model="form.role" style="width:100%">
            <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
          <div class="form-hint">浏览器工作室自动化发布按任务类型分流：<b>选题调研/大纲</b>→research、<b>正文撰写/精修/GEO</b>→writing、<b>审核优化/整改</b>→review；留空或 general 作兜底。同一角色可建多个配置实现负载均衡与故障切换。</div>
        </el-form-item>
        <div class="cfg-form__row">
          <el-form-item label="温度">
            <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" />
          </el-form-item>
          <el-form-item label="最大字数">
            <el-input-number v-model="form.max_tokens" :min="256" :max="8000" :step="256" />
          </el-form-item>
        </div>
        <div class="cfg-form__row">
          <el-form-item label="超时(秒)">
            <el-input-number v-model="form.timeout" :min="10" :max="300" :step="10" />
          </el-form-item>
          <el-form-item label="设为默认">
            <el-switch v-model="form.is_default" />
          </el-form-item>
        </div>
        <el-form-item label="启用">
          <el-switch v-model="form.status" :active-value="1" :inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Plus, Search, Edit, Delete, Star, Connection } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAppStore } from '../store/app'
import { llmApi } from '../api'

const store = useAppStore()
const configs = ref([])
const providers = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editing = ref({ id: 0 })
const search = ref('')

const emptyForm = () => ({
  name: '默认',
  provider: 'deepseek',
  api_key: '',
  base_url: '',
  model: 'deepseek-v4-pro',
  temperature: 0.7,
  max_tokens: 6000,
  timeout: 120,
  is_default: 0,
  status: 1,
  role: 'general',
  sort: 0,
})

// 三 API 调度角色
const ROLE_OPTIONS = [
  { value: 'research', label: '选题调研 / 大纲（research）' },
  { value: 'writing', label: '正文撰写 / 精修 / GEO（writing）' },
  { value: 'review', label: '审核优化 / 整改（review）' },
  { value: 'general', label: '兜底通用（general）' },
]
const ROLE_META = {
  research: { label: '选题调研·大纲', short: 'research', desc: '定方向、定选题、出大纲（thinking 推理）' },
  writing: { label: '正文撰写·精修', short: 'writing', desc: '初稿 / 去AI味 / GEO终稿 / 改写' },
  review: { label: '审核优化·整改', short: 'review', desc: '评审、下达整改指令、终审把关' },
  general: { label: '兜底通用', short: 'general', desc: '无专用角色时兜底' },
}
function roleLabel(role) {
  return (ROLE_META[role] || ROLE_META.general).label
}
function roleTagType(role) {
  return { research: 'warning', writing: 'success', review: 'danger', general: 'info' }[role] || 'info'
}
const form = ref(emptyForm())

// 三角色配置向导
const roleWizard = computed(() => {
  const roles = ['research', 'writing', 'review']
  return roles.map(role => {
    const cs = configs.value.filter(c => (c.role || 'general') === role && c.status === 1)
    return {
      role,
      short: ROLE_META[role].short,
      label: ROLE_META[role].label,
      desc: ROLE_META[role].desc,
      configs: cs,
      has: cs.length > 0,
    }
  })
})
const wizardAllOk = computed(() => roleWizard.value.every(r => r.has))

const filteredConfigs = computed(() => {
  if (!search.value) return configs.value
  const q = search.value.toLowerCase()
  return configs.value.filter(c =>
    (c.name || '').toLowerCase().includes(q) ||
    (c.model || '').toLowerCase().includes(q) ||
    (roleLabel(c.role)).toLowerCase().includes(q)
  )
})

function providerLabel(v) {
  const p = providers.value.find((x) => x.value === v)
  return p ? p.label : v
}

async function loadProviders() {
  try {
    const res = await llmApi.providers()
    providers.value = res.data || []
  } catch (e) { /* ignore */ }
}

async function loadConfigs() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const res = await llmApi.listConfigs(store.currentIndustryId)
    configs.value = res.data || []
  } finally {
    loading.value = false
  }
}

function onProviderChange(v) {
  const p = providers.value.find((x) => x.value === v)
  if (p) {
    if (!form.value.base_url) form.value.base_url = p.default_base_url || ''
    if (!form.value.model) form.value.model = p.default_model || ''
  }
}

function openCreate() {
  editing.value = { id: 0 }
  form.value = emptyForm()
  if (providers.value.length) {
    const p = providers.value[0]
    form.value.provider = p.value
    form.value.base_url = p.default_base_url || ''
    form.value.model = p.default_model || ''
  }
  dialogVisible.value = true
}

function quickAddRole(role) {
  editing.value = { id: 0 }
  form.value = emptyForm()
  form.value.role = role
  form.value.max_tokens = 6000
  form.value.timeout = 120
  const names = { research: '选题调研 API', writing: '正文撰写 API', review: '审核优化 API' }
  form.value.name = names[role] || 'LLM 配置'
  if (providers.value.length) {
    const p = providers.value[0]
    form.value.provider = p.value
    form.value.base_url = p.default_base_url || ''
    form.value.model = p.default_model || 'deepseek-v4-pro'
  }
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = { id: row.id }
  form.value = {
    name: row.name,
    provider: row.provider,
    api_key: row.api_key || '',
    base_url: row.base_url || '',
    model: row.model || '',
    temperature: parseFloat(row.temperature) || 0.7,
    max_tokens: row.max_tokens || 6000,
    timeout: row.timeout || 120,
    is_default: row.is_default || 0,
    status: row.status === 0 ? 0 : 1,
    role: row.role || 'general',
    sort: row.sort || 0,
  }
  dialogVisible.value = true
}

async function save() {
  if (!form.value.api_key) {
    ElMessage.warning('请填写 API Key')
    return
  }
  saving.value = true
  try {
    const payload = {
      industry_id: store.currentIndustryId,
      name: form.value.name,
      provider: form.value.provider,
      api_key: form.value.api_key,
      base_url: form.value.base_url,
      model: form.value.model,
      temperature: String(form.value.temperature),
      max_tokens: form.value.max_tokens,
      timeout: form.value.timeout,
      is_default: form.value.is_default ? 1 : 0,
      status: form.value.status,
      role: form.value.role || 'general',
      sort: form.value.sort || 0,
    }
    if (editing.value.id) {
      await llmApi.updateConfig(editing.value.id, payload)
    } else {
      await llmApi.createConfig(payload)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await loadConfigs()
  } finally {
    saving.value = false
  }
}

async function testConfig(row) {
  row._testing = true
  try {
    const res = await llmApi.test(row.id)
    const d = res.data || {}
    if (d.ok) {
      ElMessage.success('连接成功：' + (d.reply || '').slice(0, 40))
    } else {
      ElMessage.error('连接失败：' + (d.error || '未知错误'))
    }
  } finally {
    row._testing = false
  }
}

async function setDefault(row) {
  await llmApi.setDefault(row.id)
  ElMessage.success('已设为默认')
  await loadConfigs()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除配置「${row.name}」？`, '提示', { type: 'warning' })
  } catch (e) {
    return
  }
  await llmApi.deleteConfig(row.id)
  ElMessage.success('已删除')
  await loadConfigs()
}

onMounted(() => {
  loadProviders()
  loadConfigs()
})
watch(() => store.currentIndustryId, () => loadConfigs())
</script>

<style scoped>
.settings-page { display: flex; flex-direction: column; gap: 18px; }

.page-head {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
}
.page-head h2 { margin: 0 0 4px; font-size: 20px; color: var(--text-primary); }
.page-head .sub { margin: 0; color: var(--text-tertiary); font-size: 13px; max-width: 760px; line-height: 1.6; }

/* ============ 三 API 角色向导 ============ */
.role-wizard {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  box-shadow: var(--shadow-sm);
}
.rw-head { margin-bottom: 14px; }
.rw-head h3 { margin: 0 0 3px; font-size: 15px; font-weight: 700; color: var(--text-primary); }
.rw-head .rw-sub { font-size: 12.5px; color: var(--text-tertiary); }
.rw-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.rw-card {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 14px;
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: var(--transition);
}
.rw-card--ok { border-color: var(--accent-emerald); background: #f0fdf4; }
.rw-card__head { display: flex; align-items: center; gap: 8px; }
.rw-chip {
  font-size: 11px; font-weight: 700; padding: 2px 9px; border-radius: 10px; white-space: nowrap;
}
.rw-research { background: #ede9fe; color: #6d28d9; }
.rw-writing { background: #e0f2fe; color: #0369a1; }
.rw-review { background: #dcfce7; color: #15803d; }
.rw-title { font-size: 13px; font-weight: 700; color: var(--text-primary); }
.rw-card__desc { font-size: 11.5px; color: var(--text-tertiary); line-height: 1.5; }
.rw-card__cfgs { display: flex; flex-direction: column; gap: 4px; }
.rw-cfg-line { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12px; }
.rw-cfg-name { color: var(--text-secondary); font-weight: 600; }
.rw-cfg-model { color: var(--text-tertiary); font-family: var(--font-mono, monospace); font-size: 11px; }
.rw-card__empty { font-size: 12px; color: var(--accent-amber); font-weight: 500; }
.rw-tip { margin-top: 14px; }

/* ============ 配置列表 ============ */
.cfg-list {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  box-shadow: var(--shadow-sm);
}
.cfg-list__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.cfg-list__head h3 { margin: 0; font-size: 15px; font-weight: 700; color: var(--text-primary); }
.cfg-count { font-size: 12px; color: var(--text-tertiary); font-weight: 500; margin-left: 6px; }
.cfg-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }

.cfg-item {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 14px;
  background: var(--bg-card);
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: var(--transition);
}
.cfg-item:hover { box-shadow: var(--shadow-md); border-color: var(--brand-300); }
.cfg-item--off { opacity: 0.62; }
.cfg-item__top { display: flex; flex-direction: column; gap: 6px; }
.cfg-item__name-line { display: flex; align-items: center; gap: 8px; }
.cfg-item__name { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.cfg-item__role-line { display: flex; align-items: center; gap: 8px; }
.cfg-item__provider { font-size: 11px; color: var(--text-tertiary); }
.cfg-chip { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 10px; white-space: nowrap; }
.cfg-chip--default { background: var(--accent-emerald); color: #fff; }
.cfg-chip--research { background: #ede9fe; color: #6d28d9; }
.cfg-chip--writing { background: #e0f2fe; color: #0369a1; }
.cfg-chip--review { background: #dcfce7; color: #15803d; }
.cfg-chip--general { background: var(--slate-100); color: var(--slate-600); }

.cfg-item__mid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; }
.cfg-meta { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.cfg-meta__k { color: var(--text-tertiary); font-weight: 600; width: 32px; flex-shrink: 0; }
.cfg-meta__v { color: var(--text-secondary); word-break: break-all; }
.cfg-status { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 9px; }
.cfg-status--on { background: #ecfdf5; color: #059669; }
.cfg-status--off { background: var(--slate-100); color: var(--slate-500); }

.cfg-item__actions { display: flex; gap: 6px; padding-top: 4px; border-top: 1px dashed var(--border-light); }
.act-btn {
  width: 32px; height: 32px; border: 1px solid var(--border-light); background: var(--bg-card);
  border-radius: var(--radius-sm); cursor: pointer; display: flex; align-items: center; justify-content: center;
  color: var(--text-secondary); font-size: 15px; transition: var(--transition-fast);
}
.act-btn:hover { border-color: var(--brand-400); color: var(--brand-600); background: var(--brand-50); }
.act-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.act-btn:disabled:hover { border-color: var(--border-light); color: var(--text-secondary); background: var(--bg-card); }
.act-btn--test:hover { border-color: var(--accent-sky); color: var(--accent-sky); background: #f0f9ff; }
.act-btn--edit:hover { border-color: var(--brand-400); color: var(--brand-600); background: var(--brand-50); }
.act-btn--del:hover { border-color: var(--accent-rose); color: var(--accent-rose); background: #fff1f2; }
.act-btn.is-loading { opacity: 0.6; pointer-events: none; }

/* ============ 对话框 ============ */
.cfg-form { padding-right: 12px; }
.cfg-form__row { display: flex; gap: 16px; }
.cfg-form__row .el-form-item { flex: 1; }
.form-hint { margin-top: 6px; color: var(--text-tertiary); font-size: 12px; line-height: 1.6; }
.form-hint b { color: var(--brand-600); }

@media (max-width: 900px) {
  .rw-grid { grid-template-columns: 1fr; }
  .cfg-grid { grid-template-columns: 1fr; }
  .cfg-form__row { flex-direction: column; gap: 0; }
}
</style>
