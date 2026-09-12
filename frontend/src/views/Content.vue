<template>
  <div class="hub-view">
    <!-- 合并后的统一入口：内容审核 / 内容资产 / 运营中心 -->
    <div class="hub-tabs">
      <button class="hub-tab" :class="{ active: tab === 'review' }" @click="tab = 'review'">
        <el-icon><Document /></el-icon><span>内容审核</span>
        <el-badge v-if="pendingCount" :value="pendingCount" class="hub-tab__badge" type="warning" />
      </button>
      <button class="hub-tab" :class="{ active: tab === 'asset' }" @click="tab = 'asset'">
        <el-icon><FolderOpened /></el-icon><span>内容资产</span>
      </button>
      <button class="hub-tab" :class="{ active: tab === 'ops' }" @click="tab = 'ops'">
        <el-icon><Calendar /></el-icon><span>运营中心</span>
      </button>
    </div>

    <div class="hub-body">
      <ContentReviewPanel v-if="tab === 'review'" />
      <ContentAssetPanel v-if="tab === 'asset'" />
      <ContentOpsPanel v-if="tab === 'ops'" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { Document, FolderOpened, Calendar } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { contentApi } from '../api'
import ContentReviewPanel from '../components/content/ContentReviewPanel.vue'
import ContentAssetPanel from '../components/content/ContentAssetPanel.vue'
import ContentOpsPanel from '../components/content/ContentOpsPanel.vue'

const store = useAppStore()
const tab = ref('review')
const pendingCount = ref(0)

async function loadPendingCount() {
  if (!store.currentIndustryId) return
  try {
    const res = await contentApi.list(store.currentIndustryId, 'pending')
    pendingCount.value = (res.data || []).length
  } catch (e) {
    /* 角标非关键，失败静默 */
  }
}

watch(() => store.currentIndustryId, loadPendingCount)
onMounted(loadPendingCount)
</script>

<style scoped>
.hub-view { display: flex; flex-direction: column; gap: 16px; height: 100%; }
.hub-tabs {
  display: flex; gap: 8px; flex-shrink: 0;
}
.hub-tab {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 9px 20px; border-radius: var(--radius-md);
  border: 1px solid var(--border-light); background: var(--bg-card);
  color: var(--text-secondary); font-size: 13.5px; font-weight: 600;
  cursor: pointer; transition: all 0.16s;
  position: relative;
}
.hub-tab .el-icon { font-size: 16px; }
.hub-tab:hover { border-color: var(--brand-300); color: var(--brand-600); }
.hub-tab.active {
  background: linear-gradient(135deg, var(--brand-600), var(--brand-500));
  color: #fff; border-color: transparent;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
}
.hub-tab__badge { margin-left: 2px; }
.hub-body {
  flex: 1; min-height: 0; display: flex; flex-direction: column;
}
</style>
