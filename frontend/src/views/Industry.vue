<template>
  <div class="industry-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button type="primary" :icon="Plus" @click="openCreate">新建行业</el-button>
    </Teleport>

    <div class="industry-grid" v-loading="loading">
      <div v-for="ind in list" :key="ind.id" class="industry-card" :class="{ 'is-current': ind.id === store.currentIndustryId }">
        <div class="industry-card__header">
          <div class="industry-card__icon">
            <el-icon><OfficeBuilding /></el-icon>
          </div>
          <div class="industry-card__info">
            <div class="industry-card__name">{{ ind.name }}</div>
            <div class="industry-card__stats">
              <span>{{ ind.platform_count || 0 }} 平台</span>
              <span>{{ ind.account_count || 0 }} 账号</span>
              <span>{{ ind.keyword_count || 0 }} 关键词</span>
              <span>{{ ind.content_count || 0 }} 内容</span>
            </div>
          </div>
          <el-tag v-if="ind.id === store.currentIndustryId" size="small" type="primary" effect="dark">当前</el-tag>
        </div>
        <div class="industry-card__desc">{{ ind.description || '暂无描述' }}</div>
        <div class="industry-card__footer">
          <el-button text type="primary" size="small" @click="switchTo(ind)">切换到此行业</el-button>
          <div class="industry-card__actions">
            <el-button text size="small" :icon="CopyDocument" @click="openClone(ind)" />
            <el-button text size="small" :icon="Edit" @click="openEdit(ind)" />
            <el-button text size="small" type="danger" :icon="Delete" @click="remove(ind)" />
          </div>
        </div>
      </div>
      <EmptyState v-if="!loading && list.length === 0" title="暂无行业" description="点击右上角「新建行业」创建第一个行业空间" icon="OfficeBuilding">
        <el-button type="primary" :icon="Plus" @click="openCreate">立即创建</el-button>
      </EmptyState>
    </div>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑行业' : '新建行业'" width="480px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="行业名称">
          <el-input v-model="form.name" placeholder="如：真空泵行业" />
        </el-form-item>
        <el-form-item label="行业描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="行业描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 克隆弹窗 -->
    <el-dialog v-model="cloneDialog" title="克隆行业" width="480px">
      <el-form :model="cloneForm" label-width="80px">
        <el-form-item label="源行业">
          <el-input :model-value="cloneForm.source_name" disabled />
        </el-form-item>
        <el-form-item label="新名称">
          <el-input v-model="cloneForm.new_name" placeholder="新行业名称" />
        </el-form-item>
        <el-form-item label="新描述">
          <el-input v-model="cloneForm.new_description" type="textarea" :rows="2" placeholder="新行业描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cloneDialog = false">取消</el-button>
        <el-button type="primary" @click="doClone" :loading="saving">确认克隆</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete, CopyDocument, OfficeBuilding } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { industryApi } from '../api'
import EmptyState from '../components/EmptyState.vue'

const store = useAppStore()
const loading = ref(false)
const saving = ref(false)
const list = ref([])
const dialogVisible = ref(false)
const editing = ref(false)
const form = ref({ name: '', description: '' })
const cloneDialog = ref(false)
const cloneForm = ref({ source_id: null, source_name: '', new_name: '', new_description: '' })

async function loadList() {
  loading.value = true
  try {
    const res = await industryApi.list()
    list.value = res.data || []
  } finally {
    loading.value = false
  }
}

function switchTo(ind) {
  store.setIndustry(ind.id)
  ElMessage.success(`已切换到行业：${ind.name}`)
}

function openCreate() {
  editing.value = false
  form.value = { name: '', description: '' }
  dialogVisible.value = true
}

function openEdit(ind) {
  editing.value = true
  form.value = { ...ind }
  dialogVisible.value = true
}

async function save() {
  if (!form.value.name?.trim()) { ElMessage.warning('请输入行业名称'); return }
  saving.value = true
  try {
    let res
    if (editing.value) {
      res = await industryApi.update(form.value.id, form.value)
      if (res.code !== 0) { ElMessage.error(res.msg || '更新失败'); return }
      ElMessage.success('更新成功')
    } else {
      res = await industryApi.create(form.value)
      if (res.code !== 0) { ElMessage.error(res.msg || '创建失败'); return }
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadList()
    await store.loadIndustries()
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '操作失败，请重试'
    ElMessage.error(msg)
  } finally {
    saving.value = false
  }
}

async function remove(ind) {
  try {
    await ElMessageBox.confirm(`确定删除行业「${ind.name}」吗？该操作将删除所有关联数据。`, '提示', { type: 'warning' })
  } catch (e) {
    return  // 用户取消确认，静默返回，不弹错误
  }
  try {
    await industryApi.delete(ind.id)
    ElMessage.success('删除成功')
    await loadList()
    await store.loadIndustries()
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.message || ''
    ElMessage.error('删除失败' + (detail ? `：${detail}` : ''))
  }
}

function openClone(ind) {
  cloneForm.value = { source_id: ind.id, source_name: ind.name, new_name: `${ind.name}_副本`, new_description: ind.description }
  cloneDialog.value = true
}

async function doClone() {
  if (!cloneForm.value.new_name?.trim()) { ElMessage.warning('请输入新行业名称'); return }
  saving.value = true
  try {
    await industryApi.clone(cloneForm.value.source_id, { new_name: cloneForm.value.new_name, new_description: cloneForm.value.new_description })
    ElMessage.success('克隆成功')
    cloneDialog.value = false
    await loadList()
    await store.loadIndustries()
  } finally {
    saving.value = false
  }
}

onMounted(() => { loadList() })
</script>

<style scoped>
.industry-view { display: flex; flex-direction: column; gap: 16px; }
.industry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
  min-height: 200px;
}
.industry-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 20px;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.industry-card:hover {
  border-color: var(--brand-300);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}
.industry-card.is-current {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px var(--brand-50);
}
.industry-card__header { display: flex; align-items: center; gap: 12px; }
.industry-card__icon {
  width: 44px; height: 44px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--brand-50), var(--brand-100));
  color: var(--brand-600);
  display: flex; align-items: center; justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}
.industry-card__info { flex: 1; min-width: 0; }
.industry-card__name { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.industry-card__stats { display: flex; gap: 10px; font-size: 11px; color: var(--text-tertiary); margin-top: 4px; }
.industry-card__desc {
  font-size: 13px; color: var(--text-secondary); line-height: 1.6;
  min-height: 40px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.industry-card__footer {
  display: flex; align-items: center; justify-content: space-between;
  padding-top: 12px; border-top: 1px solid var(--border-light);
}
.industry-card__actions { display: flex; gap: 4px; }
</style>
