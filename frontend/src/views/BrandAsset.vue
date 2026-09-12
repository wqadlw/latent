<template>
  <div class="brand-asset-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button type="primary" :icon="Plus" @click="openCreate">新建品牌资产</el-button>
    </Teleport>

    <div class="brand-grid" v-loading="loading">
      <div v-for="item in list" :key="item.id" class="brand-card" :class="{ 'is-default': item.is_default }">
        <div class="brand-card__header">
          <div class="brand-card__icon">
            <el-icon><GoldMedal /></el-icon>
          </div>
          <div class="brand-card__info">
            <div class="brand-card__name">{{ item.brand_name }}</div>
            <div class="brand-card__slogan" v-if="item.slogan">{{ item.slogan }}</div>
          </div>
          <el-tag v-if="item.is_default" size="small" type="success" effect="dark">默认</el-tag>
        </div>
        <div class="brand-card__body">
          <div class="info-row" v-if="item.official_website">
            <el-icon><Link /></el-icon>
            <span>{{ item.official_website }}</span>
          </div>
          <div class="info-row" v-if="item.contact_phone">
            <el-icon><Phone /></el-icon>
            <span>{{ item.contact_phone }}</span>
          </div>
          <div class="info-row" v-if="item.contact_wechat">
            <el-icon><ChatDotRound /></el-icon>
            <span>{{ item.contact_wechat }}</span>
          </div>
          <div class="info-row" v-if="item.core_products">
            <el-icon><Goods /></el-icon>
            <span class="multi-line">{{ item.core_products }}</span>
          </div>
          <div class="info-row" v-if="item.unique_selling_points">
            <el-icon><Star /></el-icon>
            <span class="multi-line">{{ item.unique_selling_points }}</span>
          </div>
          <div class="info-row" v-if="item.target_keywords">
            <el-icon><Key /></el-icon>
            <span class="multi-line">{{ item.target_keywords }}</span>
          </div>
        </div>
        <div class="brand-card__footer">
          <el-button v-if="!item.is_default" text size="small" type="success" @click="setDefault(item)">设为默认</el-button>
          <el-button text size="small" :icon="Edit" @click="openEdit(item)">编辑</el-button>
          <el-button text size="small" type="danger" :icon="Delete" @click="remove(item)">删除</el-button>
        </div>
      </div>
      <EmptyState v-if="!loading && list.length === 0" title="暂无品牌资产" description="新建品牌资产后，系统会自动将其注入到所有提示词模板中" icon="GoldMedal">
        <el-button type="primary" :icon="Plus" @click="openCreate">立即创建</el-button>
      </EmptyState>
    </div>

    <!-- 弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑品牌资产' : '新建品牌资产'" width="680px" top="5vh">
      <el-form :model="form" label-width="120px">
        <el-form-item label="品牌名称"><el-input v-model="form.brand_name" /></el-form-item>
        <el-form-item label="品牌口号"><el-input v-model="form.slogan" /></el-form-item>
        <el-form-item label="官网"><el-input v-model="form.official_website" /></el-form-item>
        <el-form-item label="联系电话"><el-input v-model="form.contact_phone" /></el-form-item>
        <el-form-item label="微信"><el-input v-model="form.contact_wechat" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.contact_email" /></el-form-item>
        <el-form-item label="核心产品"><el-input v-model="form.core_products" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="独特卖点"><el-input v-model="form.unique_selling_points" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="目标关键词"><el-input v-model="form.target_keywords" type="textarea" :rows="2" placeholder="逗号分隔" /></el-form-item>
        <el-form-item label="品牌故事"><el-input v-model="form.brand_story" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="设为默认"><el-switch v-model="form.is_default" :active-value="1" :inactive-value="0" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, inject } from 'vue'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete, GoldMedal, Link, Phone, ChatDotRound, Goods, Star, Key } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { brandAssetApi } from '../api'
import EmptyState from '../components/EmptyState.vue'

const store = useAppStore()
const loading = ref(false)
const saving = ref(false)
const list = ref([])
const dialogVisible = ref(false)
const editing = ref(false)
const form = ref({})

async function loadList() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const res = await brandAssetApi.list(store.currentIndustryId)
    list.value = res.data || []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = false
  form.value = {
    brand_name: '', slogan: '', official_website: '', contact_phone: '', contact_wechat: '',
    contact_email: '', core_products: '', unique_selling_points: '', target_keywords: '',
    brand_story: '', is_default: 0, industry_id: store.currentIndustryId,
  }
  dialogVisible.value = true
}

function openEdit(item) {
  editing.value = true
  form.value = { ...item }
  dialogVisible.value = true
}

async function save() {
  if (!form.value.brand_name?.trim()) { ElMessage.warning('请输入品牌名称'); return }
  saving.value = true
  try {
    if (editing.value) {
      await brandAssetApi.update(form.value.id, form.value)
    } else {
      await brandAssetApi.create(form.value)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await loadList()
  } finally {
    saving.value = false
  }
}

async function remove(item) {
  await ElMessageBox.confirm(`确定删除品牌资产「${item.brand_name}」吗？`, '提示', { type: 'warning' })
  await brandAssetApi.delete(item.id)
  ElMessage.success('删除成功')
  await loadList()
}

async function setDefault(item) {
  await brandAssetApi.setDefault(item.id)
  ElMessage.success('已设为默认品牌')
  await loadList()
}

watch(() => store.currentIndustryId, loadList)
onMounted(loadList)
</script>

<style scoped>
.brand-asset-view { display: flex; flex-direction: column; gap: 16px; }
.brand-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
  min-height: 200px;
}
.brand-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: all 0.2s ease;
}
.brand-card:hover { box-shadow: var(--shadow-md); transform: translateY(-2px); }
.brand-card.is-default { border-color: var(--accent-emerald); }
.brand-card.is-default::before {
  content: ''; display: block; height: 3px;
  background: linear-gradient(90deg, var(--accent-emerald), #34d399);
}
.brand-card__header { padding: 16px 18px 12px; border-bottom: 1px solid var(--border-light); display: flex; align-items: center; gap: 12px; }
.brand-card__icon {
  width: 40px; height: 40px; border-radius: var(--radius-md);
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  color: var(--accent-amber);
  display: flex; align-items: center; justify-content: center; font-size: 20px;
  flex-shrink: 0;
}
.brand-card__info { flex: 1; min-width: 0; }
.brand-card__name { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.brand-card__slogan { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }
.brand-card__body { padding: 14px 18px; flex: 1; }
.info-row {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: 13px; color: var(--text-secondary); margin-bottom: 10px;
}
.info-row .el-icon { color: var(--brand-500); margin-top: 2px; flex-shrink: 0; }
.info-row .multi-line { white-space: pre-wrap; line-height: 1.5; }
.brand-card__footer {
  display: flex; justify-content: flex-end; gap: 4px;
  padding: 10px 12px; border-top: 1px solid var(--border-light);
  background: var(--slate-50);
}
</style>
