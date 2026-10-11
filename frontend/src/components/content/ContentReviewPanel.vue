<template>
  <div class="content-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button :icon="Refresh" @click="loadList">刷新</el-button>
    </Teleport>

    <!-- 分段切换 -->
    <div class="section-tabs">
      <button class="section-tab" :class="{ active: filterReview === '' }" @click="setFilter('')">全部</button>
      <button class="section-tab" :class="{ active: filterReview === 'pending' }" @click="setFilter('pending')">待审核</button>
      <button class="section-tab" :class="{ active: filterReview === 'pass' }" @click="setFilter('pass')">已通过</button>
      <button class="section-tab" :class="{ active: filterReview === 'reject' }" @click="setFilter('reject')">已驳回</button>
    </div>

    <!-- 内容列表（窗口化虚拟滚动） -->
    <VirtualList
      class="content-list"
      v-loading="loading"
      :items="list"
      :row-height="156"
      :gap="8"
      :get-key="(it) => it.id"
      #default="{ item }"
    >
      <div class="content-card">
        <div class="content-card__main">
          <div class="content-card__header">
            <span class="content-card__title">{{ item.title || '未命名内容' }}</span>
            <el-tag size="small" :type="reviewStatusType(item.review_status)" effect="light">{{ reviewStatusLabel(item.review_status) }}</el-tag>
          </div>
          <div class="content-card__excerpt">{{ (item.content || '').slice(0, 120) }}{{ (item.content || '').length > 120 ? '...' : '' }}</div>
          <div class="content-card__meta">
            <span><el-icon><Connection /></el-icon> {{ getPlatformName(item.platform_id) }}</span>
            <span><el-icon><User /></el-icon> {{ getAccountName(item.account_id) }}</span>
            <span><el-icon><Clock /></el-icon> {{ formatDateTime(item.create_time) }}</span>
          </div>
        </div>
        <div class="content-card__actions">
          <el-button text size="small" :icon="View" @click="viewDetail(item)">查看</el-button>
          <el-button v-if="item.review_status === 'pending'" text size="small" type="success" @click="review(item, 'pass')">通过</el-button>
          <el-button v-if="item.review_status === 'pending'" text size="small" type="danger" @click="review(item, 'reject')">驳回</el-button>
          <el-button v-if="item.review_status === 'pass'" text size="small" type="primary" @click="openPublish(item)">发布</el-button>
          <el-button text size="small" type="danger" :icon="Delete" @click="remove(item)">删除</el-button>
        </div>
      </div>
    </VirtualList>
    <EmptyState v-if="!loading && list.length === 0" title="暂无内容" description="运营使用提示词在外部AI生成软文后，粘贴回系统对应选题下" icon="Document" />

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailDialog" title="内容详情" width="720px" top="5vh">
      <div v-if="current" class="detail-content">
        <h3 class="detail-title">{{ current.title }}</h3>
        <div class="detail-meta">
          <el-tag size="small" :type="reviewStatusType(current.review_status)">{{ reviewStatusLabel(current.review_status) }}</el-tag>
          <span>{{ getPlatformName(current.platform_id) }}</span>
          <span>{{ formatDateTime(current.create_time) }}</span>
        </div>
        <div class="detail-body">{{ current.content }}</div>
      </div>
    </el-dialog>

    <!-- 发布弹窗 -->
    <el-dialog v-model="publishDialog" title="发布内容" width="480px">
      <el-form :model="publishForm" label-width="100px">
        <el-form-item label="发布状态">
          <el-select v-model="publishForm.publish_status" style="width: 100%;">
            <el-option label="已发布" value="published" />
            <el-option label="已下架" value="offline" />
          </el-select>
        </el-form-item>
        <el-form-item label="发布链接"><el-input v-model="publishForm.publish_url" /></el-form-item>
        <el-form-item label="发布时间"><el-input v-model="publishForm.publish_time" placeholder="YYYY-MM-DD" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="publishDialog = false">取消</el-button>
        <el-button type="primary" @click="submitPublish">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, inject } from 'vue'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, View, Delete, Connection, User, Clock, Document } from '@element-plus/icons-vue'
import { useAppStore } from '../../store/app'
import { contentApi, platformApi, accountApi } from '../../api'
import { formatDateTime } from '../../utils/format'
import { reviewStatusLabel, reviewStatusType } from '../../constants/status'
import { nameById } from '../../utils/lookup'
import EmptyState from '../EmptyState.vue'
import VirtualList from '../VirtualList.vue'

const store = useAppStore()
const loading = ref(false)
const list = ref([])
const filterReview = ref('')
const platforms = ref([])
const accounts = ref([])
const detailDialog = ref(false)
const current = ref(null)
const publishDialog = ref(false)
const publishForm = ref({})

async function loadAll() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const [p, a] = await Promise.all([
      platformApi.list(store.currentIndustryId),
      accountApi.list(store.currentIndustryId),
    ])
    platforms.value = p.data || []
    accounts.value = a.data || []
    await loadList()
  } finally {
    loading.value = false
  }
}

async function loadList() {
  if (!store.currentIndustryId) return
  const res = await contentApi.list(store.currentIndustryId, filterReview.value)
  list.value = res.data || []
}

function setFilter(v) {
  filterReview.value = v
  loadList()
}

const getPlatformName = (id) => nameById(platforms.value, id)
const getAccountName = (id) => nameById(accounts.value, id, 'account_name')

function viewDetail(item) {
  current.value = item
  detailDialog.value = true
}

async function review(item, status) {
  const reason = status === 'reject' ? await ElMessageBox.prompt('请输入驳回原因', '驳回', { type: 'warning' }) : ''
  await contentApi.review(item.id, { review_status: status, reject_reason: reason?.value || '' })
  ElMessage.success(status === 'pass' ? '已通过' : '已驳回')
  await loadList()
}

function openPublish(item) {
  publishForm.value = { id: item.id, publish_status: 'published', publish_url: item.publish_url || '', publish_time: item.publish_time || '' }
  publishDialog.value = true
}

async function submitPublish() {
  await contentApi.publish(publishForm.value.id, publishForm.value)
  ElMessage.success('发布状态已更新')
  publishDialog.value = false
  await loadList()
}

async function remove(item) {
  await ElMessageBox.confirm(`确定删除内容「${item.title}」？`, '提示', { type: 'warning' })
  await contentApi.delete(item.id)
  ElMessage.success('已删除')
  await loadList()
}

watch(() => store.currentIndustryId, loadAll)
onMounted(loadAll)
</script>

<style scoped>
.content-view { display: flex; flex-direction: column; gap: 16px; height: 100%; }
.content-list { flex: 1; min-height: 0; }
.content-card {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
  height: 100%; box-sizing: border-box; overflow: hidden;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  transition: all 0.2s ease;
}
.content-card:hover { border-color: var(--brand-300); box-shadow: var(--shadow-sm); }
.content-card__main { flex: 1; min-width: 0; }
.content-card__header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.content-card__title { font-size: 14.5px; font-weight: 700; color: var(--text-primary); }
.content-card__excerpt {
  font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 10px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.content-card__meta { display: flex; align-items: center; gap: 16px; font-size: 12px; color: var(--text-tertiary); }
.content-card__meta span { display: inline-flex; align-items: center; gap: 4px; }
.content-card__actions { display: flex; flex-direction: row; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 6px 8px; flex-shrink: 0; }

.detail-content { padding: 4px; }
.detail-title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin-bottom: 10px; }
.detail-meta { display: flex; align-items: center; gap: 12px; font-size: 13px; color: var(--text-tertiary); margin-bottom: 16px; }
.detail-body { font-size: 14px; color: var(--text-secondary); line-height: 1.8; white-space: pre-wrap; }
</style>
