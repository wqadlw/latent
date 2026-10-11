<template>
  <div class="platform-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button :icon="MagicStick" @click="seedPlatforms" :loading="seeding">一键灌入7大平台</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreatePlatform">新建平台</el-button>
    </Teleport>

    <!-- 分段切换 -->
    <div class="section-tabs">
      <button class="section-tab" :class="{ active: activeTab === 'platform' }" @click="activeTab = 'platform'">
        <el-icon><Connection /></el-icon> 平台管理
      </button>
      <button class="section-tab" :class="{ active: activeTab === 'account' }" @click="activeTab = 'account'">
        <el-icon><User /></el-icon> 账号管理
      </button>
      <button class="section-tab" :class="{ active: activeTab === 'persona' }" @click="activeTab = 'persona'">
        <el-icon><Avatar /></el-icon> 人设管理
      </button>
    </div>

    <!-- 平台管理 -->
    <div v-show="activeTab === 'platform'" class="table-card" v-loading="loading">
      <el-table :data="platforms" stripe style="width: 100%">
        <el-table-column label="平台名称" min-width="160">
          <template #default="{ row }">
            <span style="font-weight: 600;">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="字数区间" width="140">
          <template #default="{ row }">{{ row.word_count_min }} - {{ row.word_count_max }} 字</template>
        </el-table-column>
        <el-table-column label="合规等级" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.compliance_level >= 3 ? 'danger' : row.compliance_level >= 2 ? 'warning' : 'success'" effect="light">
              {{ ['','宽松','标准','严格'][row.compliance_level] || '标准' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="平台特性" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="font-size: 12px; color: var(--text-tertiary);">{{ row.characteristics || parseFeatures(row.config) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平台规则" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="font-size: 12px; color: var(--text-tertiary);">{{ row.rules || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" :icon="Edit" @click="openEditPlatform(row)">编辑</el-button>
            <el-button text size="small" type="danger" :icon="Delete" @click="removePlatform(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <EmptyState v-if="!loading && platforms.length === 0" title="暂无平台" description="点击右上角「一键灌入7大平台」快速初始化" size="small" icon="Connection" />
    </div>

    <!-- 账号管理 -->
    <div v-show="activeTab === 'account'" class="table-card" v-loading="loading">
      <div class="table-head">
        <span class="table-title">账号列表</span>
        <el-button type="primary" size="small" :icon="Plus" @click="openCreateAccount">新建账号</el-button>
      </div>
      <el-table :data="accounts" stripe style="width: 100%">
        <el-table-column label="账号名称" min-width="160">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 8px;">
              <el-avatar :size="32" style="background: linear-gradient(135deg, var(--brand-400), var(--brand-600));">{{ (row.account_name || '?').charAt(0) }}</el-avatar>
              <span style="font-weight: 600;">{{ row.account_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="所属平台" width="120">
          <template #default="{ row }">{{ getPlatformName(row.platform_id) }}</template>
        </el-table-column>
        <el-table-column label="绑定人设" width="120">
          <template #default="{ row }">{{ getPersonaName(row.persona_id) }}</template>
        </el-table-column>
        <el-table-column label="内容赛道" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.content_track || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-switch :model-value="row.status === 1" size="small" @change="(v) => toggleAccount(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" :icon="Edit" @click="openEditAccount(row)">编辑</el-button>
            <el-button text size="small" type="danger" :icon="Delete" @click="removeAccount(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <EmptyState v-if="!loading && accounts.length === 0" title="暂无账号" size="small" icon="User" />
    </div>

    <!-- 人设管理 -->
    <div v-show="activeTab === 'persona'" class="table-card" v-loading="loading">
      <div class="table-head">
        <span class="table-title">人设列表</span>
        <el-button type="primary" size="small" :icon="Plus" @click="openCreatePersona">新建人设</el-button>
      </div>
      <div class="persona-grid">
        <div v-for="p in personas" :key="p.id" class="persona-card">
          <div class="persona-card__header">
            <el-avatar :size="40" style="background: linear-gradient(135deg, var(--accent-violet), var(--brand-600));">{{ (p.name || '?').charAt(0) }}</el-avatar>
            <div style="flex: 1;">
              <div style="font-weight: 600; font-size: 14px;">{{ p.name }}</div>
              <div style="font-size: 12px; color: var(--text-tertiary);">{{ p.identity || '未设置身份' }}</div>
            </div>
          </div>
          <div class="persona-card__body">
            <div v-if="p.tone_style" class="persona-attr"><span>语气风格：</span>{{ p.tone_style }}</div>
            <div v-if="p.contact_rule" class="persona-attr"><span>联系方式：</span>{{ p.contact_rule }}</div>
          </div>
          <div class="persona-card__footer">
            <el-button text size="small" :icon="Edit" @click="openEditPersona(p)">编辑</el-button>
            <el-button text size="small" type="danger" :icon="Delete" @click="removePersona(p)">删除</el-button>
          </div>
        </div>
      </div>
      <EmptyState v-if="!loading && personas.length === 0" title="暂无人设" size="small" icon="Avatar" />
    </div>

    <!-- 平台弹窗 -->
    <el-dialog v-model="platformDialog" :title="editingPlatform ? '编辑平台' : '新建平台'" width="480px">
      <el-form :model="platformForm" label-width="100px">
        <el-form-item label="平台名称"><el-input v-model="platformForm.name" /></el-form-item>
        <el-form-item label="字数区间">
          <div style="display: flex; align-items: center; gap: 8px;">
            <el-input-number v-model="platformForm.word_count_min" :min="100" :step="100" />
            <span>-</span>
            <el-input-number v-model="platformForm.word_count_max" :min="100" :step="100" />
            <span>字</span>
          </div>
        </el-form-item>
        <el-form-item label="合规等级">
          <el-select v-model="platformForm.compliance_level" style="width: 100%;">
            <el-option label="宽松" :value="1" />
            <el-option label="标准" :value="2" />
            <el-option label="严格" :value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="平台特性">
          <el-input v-model="platformForm.characteristics" type="textarea" :rows="3" placeholder="如：门户型平台，搜索权重高，适合品牌背书与长尾收录" />
        </el-form-item>
        <el-form-item label="平台规则">
          <el-input v-model="platformForm.rules" type="textarea" :rows="3" placeholder="如：允许软广，禁止硬广与夸大宣传；文末可自然带出品牌与联系方式" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="platformDialog = false">取消</el-button>
        <el-button type="primary" @click="savePlatform" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 账号弹窗 -->
    <el-dialog v-model="accountDialog" :title="editingAccount ? '编辑账号' : '新建账号'" width="480px">
      <el-form :model="accountForm" label-width="100px">
        <el-form-item label="账号名称"><el-input v-model="accountForm.account_name" /></el-form-item>
        <el-form-item label="所属平台">
          <el-select v-model="accountForm.platform_id" style="width: 100%;">
            <el-option v-for="p in platforms" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="绑定人设">
          <el-select v-model="accountForm.persona_id" style="width: 100%;" clearable>
            <el-option v-for="p in personas" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容赛道"><el-input v-model="accountForm.content_track" placeholder="如：敏感肌修护" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAccount" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 人设弹窗 -->
    <el-dialog v-model="personaDialog" :title="editingPersona ? '编辑人设' : '新建人设'" width="520px">
      <el-form :model="personaForm" label-width="100px">
        <el-form-item label="人设名称"><el-input v-model="personaForm.name" placeholder="如：技术专家老王" /></el-form-item>
        <el-form-item label="身份设定"><el-input v-model="personaForm.identity" type="textarea" :rows="2" placeholder="如：10年护肤研发从业经验" /></el-form-item>
        <el-form-item label="语气风格"><el-input v-model="personaForm.tone_style" type="textarea" :rows="2" placeholder="如：专业严谨但不失亲和" /></el-form-item>
        <el-form-item label="联系方式规则"><el-input v-model="personaForm.contact_rule" type="textarea" :rows="2" placeholder="如：仅在文末自然带出官网与电话" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="personaDialog = false">取消</el-button>
        <el-button type="primary" @click="savePersona" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, inject } from 'vue'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete, MagicStick, Connection, User, Avatar } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { platformApi, personaApi, accountApi, platformPresetApi } from '../api'
import { nameById } from '../utils/lookup'
import EmptyState from '../components/EmptyState.vue'

const store = useAppStore()
const loading = ref(false)
const saving = ref(false)
const seeding = ref(false)
const activeTab = ref('platform')
const platforms = ref([])
const accounts = ref([])
const personas = ref([])

const platformDialog = ref(false)
const editingPlatform = ref(false)
const platformForm = ref({ name: '', word_count_min: 800, word_count_max: 1500, compliance_level: 2, characteristics: '', rules: '' })

const accountDialog = ref(false)
const editingAccount = ref(false)
const accountForm = ref({ account_name: '', platform_id: null, persona_id: null, content_track: '', status: 1 })

const personaDialog = ref(false)
const editingPersona = ref(false)
const personaForm = ref({ name: '', identity: '', tone_style: '', contact_rule: '' })

function parseFeatures(config) {
  try {
    const c = JSON.parse(config || '{}')
    return (c.features || []).join('、')
  } catch { return '' }
}

const getPlatformName = (id) => nameById(platforms.value, id)
const getPersonaName = (id) => nameById(personas.value, id)

async function loadAll() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const [p, a, pe] = await Promise.all([
      platformApi.list(store.currentIndustryId),
      accountApi.list(store.currentIndustryId),
      personaApi.list(store.currentIndustryId),
    ])
    platforms.value = p.data || []
    accounts.value = a.data || []
    personas.value = pe.data || []
  } finally {
    loading.value = false
  }
}

async function seedPlatforms() {
  seeding.value = true
  try {
    const res = await platformPresetApi.seed(store.currentIndustryId)
    ElMessage.success(res.msg)
    await loadAll()
  } finally {
    seeding.value = false
  }
}

// 平台
function openCreatePlatform() {
  editingPlatform.value = false
  platformForm.value = { name: '', word_count_min: 800, word_count_max: 1500, compliance_level: 2, characteristics: '', rules: '', industry_id: store.currentIndustryId }
  platformDialog.value = true
}
function openEditPlatform(row) {
  editingPlatform.value = true
  platformForm.value = { ...row }
  platformDialog.value = true
}
async function savePlatform() {
  if (!platformForm.value.name?.trim()) { ElMessage.warning('请输入平台名称'); return }
  saving.value = true
  try {
    if (editingPlatform.value) {
      await platformApi.update(platformForm.value.id, platformForm.value)
    } else {
      await platformApi.create(platformForm.value)
    }
    ElMessage.success('保存成功')
    platformDialog.value = false
    await loadAll()
  } finally {
    saving.value = false
  }
}
async function removePlatform(row) {
  await ElMessageBox.confirm(`确定删除平台「${row.name}」吗？`, '提示', { type: 'warning' })
  await platformApi.delete(row.id)
  ElMessage.success('删除成功')
  await loadAll()
}

// 账号
function openCreateAccount() {
  editingAccount.value = false
  accountForm.value = { account_name: '', platform_id: platforms.value[0]?.id, persona_id: null, content_track: '', status: 1, industry_id: store.currentIndustryId }
  accountDialog.value = true
}
function openEditAccount(row) {
  editingAccount.value = true
  accountForm.value = { ...row }
  accountDialog.value = true
}
async function saveAccount() {
  if (!accountForm.value.account_name?.trim()) { ElMessage.warning('请输入账号名称'); return }
  saving.value = true
  try {
    if (editingAccount.value) {
      await accountApi.update(accountForm.value.id, accountForm.value)
    } else {
      await accountApi.create(accountForm.value)
    }
    ElMessage.success('保存成功')
    accountDialog.value = false
    await loadAll()
  } finally {
    saving.value = false
  }
}
async function removeAccount(row) {
  await ElMessageBox.confirm(`确定删除账号「${row.account_name}」吗？`, '提示', { type: 'warning' })
  await accountApi.delete(row.id)
  ElMessage.success('删除成功')
  await loadAll()
}
async function toggleAccount(row, v) {
  await accountApi.toggleStatus(row.id, v ? 1 : 0)
  row.status = v ? 1 : 0
  ElMessage.success('状态已更新')
}

// 人设
function openCreatePersona() {
  editingPersona.value = false
  personaForm.value = { name: '', identity: '', tone_style: '', contact_rule: '', industry_id: store.currentIndustryId }
  personaDialog.value = true
}
function openEditPersona(row) {
  editingPersona.value = true
  personaForm.value = { ...row }
  personaDialog.value = true
}
async function savePersona() {
  if (!personaForm.value.name?.trim()) { ElMessage.warning('请输入人设名称'); return }
  saving.value = true
  try {
    if (editingPersona.value) {
      await personaApi.update(personaForm.value.id, personaForm.value)
    } else {
      await personaApi.create(personaForm.value)
    }
    ElMessage.success('保存成功')
    personaDialog.value = false
    await loadAll()
  } finally {
    saving.value = false
  }
}
async function removePersona(row) {
  await ElMessageBox.confirm(`确定删除人设「${row.name}」吗？`, '提示', { type: 'warning' })
  await personaApi.delete(row.id)
  ElMessage.success('删除成功')
  await loadAll()
}

watch(() => store.currentIndustryId, loadAll)
onMounted(loadAll)
</script>

<style scoped>
.platform-view { display: flex; flex-direction: column; gap: 16px; }
.table-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  min-height: 300px;
}
.table-head { padding: 14px 20px; border-bottom: 1px solid var(--border-light); display: flex; align-items: center; justify-content: space-between; }
.table-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }

.persona-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; padding: 20px; }
.persona-card {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 16px;
  display: flex; flex-direction: column; gap: 12px;
}
.persona-card__header { display: flex; align-items: center; gap: 12px; }
.persona-card__body { font-size: 13px; color: var(--text-secondary); line-height: 1.6; }
.persona-attr { margin-bottom: 6px; }
.persona-attr span { color: var(--text-tertiary); }
.persona-card__footer { display: flex; justify-content: flex-end; gap: 4px; padding-top: 10px; border-top: 1px solid var(--border-light); }
</style>
