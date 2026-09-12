<template>
  <div class="not-found">
    <div class="nf-icon">
      <el-icon :size="56"><Search /></el-icon>
    </div>
    <h1 class="nf-code">404</h1>
    <p class="nf-title">页面不存在</p>
    <p class="nf-desc">你访问的地址无法匹配到任何页面，可能已被移动、重命名，或链接拼写有误。</p>
    <div class="nf-actions">
      <el-button type="primary" :icon="HomeFilled" @click="goHome">返回工作台</el-button>
      <el-button :icon="Refresh" @click="refresh">刷新当前地址</el-button>
    </div>
    <p class="nf-path">当前路径：{{ currentPath }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { HomeFilled, Refresh, Search } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const currentPath = computed(() => route.fullPath || window.location.pathname)
const goHome = () => router.push('/dashboard')
const refresh = () => window.location.reload()
</script>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  text-align: center;
  padding: 40px;
}
.nf-icon {
  color: var(--brand-400);
  margin-bottom: 4px;
}
.nf-code {
  font-size: 64px;
  font-weight: 800;
  color: var(--brand-600);
  margin: 0;
  letter-spacing: 2px;
}
.nf-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 4px 0 8px;
}
.nf-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0 0 24px;
  max-width: 440px;
  line-height: 1.7;
}
.nf-actions {
  display: flex;
  gap: 12px;
}
.nf-path {
  margin-top: 24px;
  font-size: 12px;
  color: var(--text-quaternary);
  font-family: monospace;
  word-break: break-all;
  max-width: 90%;
}
</style>
