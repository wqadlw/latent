<template>
  <div class="asset-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button :icon="Refresh" @click="loadList">刷新</el-button>
    </Teleport>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-input v-model="searchKey" placeholder="搜索标题/正文" :prefix-icon="Search" clearable style="width: 240px" @keyup.enter="loadList" />
      <el-select v-model="filterPlatform" placeholder="平台" clearable style="width: 140px" @change="loadList">
        <el-option v-for="p in platforms" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-model="filterPublish" placeholder="发布状态" clearable style="width: 140px" @change="loadList">
        <el-option label="待发布" value="pending" />
        <el-option label="已发布" value="published" />
        <el-option label="已下架" value="offline" />
      </el-select>
    </div>

    <!-- 资产列表（窗口化虚拟滚动） -->
    <div class="table-card" v-loading="loading">
      <div class="vtable">
        <div class="vrow-grid vtable__head">
          <div class="vcell col-title">标题</div>
          <div class="vcell col-platform">平台</div>
          <div class="vcell col-account">账号</div>
          <div class="vcell col-status">发布状态</div>
          <div class="vcell col-time">创建时间</div>
          <div class="vcell col-actions">操作</div>
        </div>
        <VirtualList
          class="vtable__body"
          :items="list"
          :row-height="52"
          :gap="0"
          :get-key="(it) => it.id"
          #default="{ item, index }"
        >
          <div class="vrow-grid vrow" :class="index % 2 === 1 ? 'striped' : ''">
            <div class="vcell col-title"><span class="vtitle">{{ item.title }}</span></div>
            <div class="vcell col-platform">{{ getPlatformName(item.platform_id) }}</div>
            <div class="vcell col-account">{{ getAccountName(item.account_id) }}</div>
            <div class="vcell col-status">
              <el-tag size="small" :type="assetPublishType(item.publish_status)" effect="light">{{ assetPublishLabel(item.publish_status) }}</el-tag>
            </div>
            <div class="vcell col-time">{{ formatDateTime(item.create_time) }}</div>
            <div class="vcell col-actions">
              <el-button text size="small" :icon="View" @click="viewContent(item)">查看</el-button>
              <el-button text size="small" :icon="CopyDocument" @click="checkSimilar(item)">相似度</el-button>
              <el-button text size="small" type="danger" :icon="Delete" @click="deleteContent(item)">删除</el-button>
            </div>
          </div>
        </VirtualList>
      </div>
      <EmptyState v-if="!loading && list.length === 0" title="暂无内容资产" description="所有审核通过的内容统一入库" icon="FolderOpened" />
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="viewDialog" title="内容详情" width="720px" top="5vh">
      <div v-if="current" class="detail-content">
        <h3 class="detail-title">{{ current.title }}</h3>
        <div class="detail-meta">
          <el-tag size="small">{{ getPlatformName(current.platform_id) }}</el-tag>
          <span>{{ getAccountName(current.account_id) }}</span>
          <span>{{ formatDateTime(current.create_time) }}</span>
        </div>
        <div class="detail-body">{{ current.content }}</div>
      </div>
    </el-dialog>

    <!-- 相似度弹窗 -->
    <el-dialog v-model="similarDialog" title="相似度检测" width="600px">
      <div v-if="similarList.length === 0" style="text-align: center; padding: 40px; color: var(--text-tertiary);">未检测到相似内容</div>
      <div v-for="s in similarList" :key="s.id" class="similar-item">
        <span class="similar-title">{{ s.title }}</span>
        <el-progress :percentage="s.similarity" :color="s.similarity > 70 ? '#f43f5e' : '#f59e0b'" :stroke-width="8" style="width: 200px;" />
        <span class="similar-value">{{ s.similarity }}%</span>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, inject } from 'vue'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, View, Delete, CopyDocument, FolderOpened } from '@element-plus/icons-vue'
import { useAppStore } from '../../store/app'
import { contentApi, platformApi, accountApi } from '../../api'
import { formatDateTime } from '../../utils/format'
import { assetPublishLabel, assetPublishType } from '../../constants/status'
import { nameById } from '../../utils/lookup'
import EmptyState from '../EmptyState.vue'
import VirtualList from '../VirtualList.vue'

const store = useAppStore()
const loading = ref(false)
const list = ref([])
const searchKey = ref('')
const filterPlatform = ref('')
const filterPublish = ref('')
const platforms = ref([])
const accounts = ref([])
const viewDialog = ref(false)
const current = ref(null)
const similarDialog = ref(false)
const similarList = ref([])

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
  const res = await contentApi.list(store.currentIndustryId, 'pass', filterPublish.value, filterPlatform.value, searchKey.value)
  list.value = res.data || []
}

const getPlatformName = (id) => nameById(platforms.value, id)
const getAccountName = (id) => nameById(accounts.value, id, 'account_name')

function viewContent(row) {
  current.value = row
  viewDialog.value = true
}

async function checkSimilar(row) {
  const res = await contentApi.similarity(row.id)
  similarList.value = res.data || []
  similarDialog.value = true
}

async function deleteContent(row) {
  await ElMessageBox.confirm(`确定删除内容「${row.title}」？`, '提示', { type: 'warning' })
  await contentApi.delete(row.id)
  ElMessage.success('已删除')
  await loadList()
}

watch(() => store.currentIndustryId, loadAll)
onMounted(loadAll)
</script>

<style scoped>
.asset-view { display: flex; flex-direction: column; gap: 16px; height: 100%; }
.filter-bar { display: flex; gap: 12px; flex-wrap: wrap; }
.table-card {
  flex: 1; min-height: 0; display: flex; flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.vtable { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.vtable__body { flex: 1; min-height: 0; }
.vrow-grid {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) 120px 140px 100px 160px 200px;
  align-items: center;
}
.vtable__head {
  height: 44px; flex-shrink: 0;
  background: var(--bg-secondary, #f8fafc);
  border-bottom: 1px solid var(--border-light);
  font-size: 13px; font-weight: 600; color: var(--text-secondary);
}
.vrow { height: 100%; border-bottom: 1px solid var(--border-light); }
.vrow.striped { background: rgba(148, 163, 184, 0.08); }
.vrow:hover { background: rgba(99, 102, 241, 0.06); }
.vcell { padding: 0 14px; font-size: 13px; color: var(--text-secondary); overflow: hidden; }
.vcell.col-actions { display: flex; gap: 2px; justify-content: flex-start; }
.vtitle {
  font-weight: 600; color: var(--text-primary);
  display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.detail-content { padding: 4px; }
.detail-title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin-bottom: 10px; }
.detail-meta { display: flex; align-items: center; gap: 12px; font-size: 13px; color: var(--text-tertiary); margin-bottom: 16px; }
.detail-body { font-size: 14px; color: var(--text-secondary); line-height: 1.8; white-space: pre-wrap; }

.similar-item {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 0; border-bottom: 1px solid var(--border-light);
}
.similar-item:last-child { border-bottom: none; }
.similar-title { flex: 1; font-size: 13px; color: var(--text-primary); }
.similar-value { font-size: 13px; font-weight: 600; color: var(--text-primary); width: 50px; text-align: right; }
</style>
