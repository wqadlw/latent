<template>
  <div class="global-search" ref="root">
    <el-input
      v-model="query"
      placeholder="全局搜索：关键词 / 规则 / 提示词 / 知识点 / 监测"
      :prefix-icon="Search"
      clearable
      size="default"
      class="gs-input"
      @input="onInput"
      @focus="open = true"
      @clear="clearResults"
    />
    <div v-if="open && showPanel" class="gs-panel" @mousedown.prevent>
      <div v-if="loading" class="gs-loading">搜索中…</div>
      <template v-else>
        <div v-for="grp in groups" :key="grp.key" v-show="grp.items.length">
          <div class="gs-group-title">{{ grp.label }}（{{ grp.items.length }}）</div>
          <div
            v-for="item in grp.items"
            :key="grp.key + item.id"
            class="gs-item"
            @click="go(grp, item)"
          >
            <span class="gs-item__title">{{ item.title }}</span>
            <span class="gs-item__snippet">{{ item.snippet }}</span>
          </div>
        </div>
        <div v-if="!hasAny" class="gs-empty">未找到相关内容</div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import { searchApi } from '@/api'
import { useAppStore } from '@/store/app'

const router = useRouter()
const store = useAppStore()
const root = ref(null)
const query = ref('')
const open = ref(false)
const loading = ref(false)
const data = ref({ keyword: [], rule: [], prompt: [], knowledge: [], intent: [], monitor: [] })

const groups = computed(() => [
  { key: 'keyword', label: '关键词', route: '/keyword', items: data.value.keyword },
  { key: 'rule', label: '规则', route: '/rule', items: data.value.rule, tabKey: 'tab', field: 'type' },
  { key: 'prompt', label: '提示词', route: '/prompt-library', items: data.value.prompt, tabKey: 'cat', field: 'category' },
  { key: 'knowledge', label: '知识点', route: '/knowledge', items: data.value.knowledge },
  { key: 'intent', label: '意图问题', route: '/intent-question', items: data.value.intent },
  { key: 'monitor', label: 'AI推荐监测', route: '/geo-monitor', items: data.value.monitor },
])
const hasAny = computed(() => groups.value.some(g => g.items.length))
const showPanel = computed(() => query.value.trim().length > 0)

let timer = null
function onInput() {
  if (!query.value.trim()) {
    data.value = { keyword: [], rule: [], prompt: [], knowledge: [], intent: [], monitor: [] }
    return
  }
  clearTimeout(timer)
  timer = setTimeout(doSearch, 250)
}
async function doSearch() {
  loading.value = true
  try {
    const res = await searchApi.search(query.value.trim(), store.currentIndustryId)
    data.value = res.data || { keyword: [], rule: [], prompt: [], knowledge: [], intent: [], monitor: [] }
  } finally {
    loading.value = false
  }
}
function go(grp, item) {
  open.value = false
  const q = { focus: item.id, t: Date.now() }
  // 带分页/分类的板块：把目标所在的分组带上，跳转后自动切到对应标签
  if (grp.tabKey && item[grp.field]) q[grp.tabKey] = item[grp.field]
  router.push({ path: grp.route, query: q })
}
function clearResults() {
  data.value = { keyword: [], rule: [], prompt: [], knowledge: [], intent: [], monitor: [] }
}
function onDocClick(e) {
  // 只有点击组件外部时才关闭面板，避免点输入框时面板被自己关掉
  if (open.value && root.value && !root.value.contains(e.target)) {
    open.value = false
  }
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<style scoped>
.global-search {
  position: relative;
  /* 用 flex 基准而不是固定 width：顶栏空间不足时（子视图会 Teleport 进任意多个操作按钮，
     Knowledge 一次塞 5 个）搜索框应当**第一个被压缩**，而不是把左边的标题挤成竖排。
     内层 .gs-input 是 width:100%，所以这里收缩不会撑破输入框。 */
  flex: 0 1 280px;
  min-width: 0;
}
.gs-input { width: 100%; }
.gs-panel {
  position: absolute; top: calc(100% + 6px); left: 0; right: 0; z-index: 2000;
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: 10px; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  max-height: 420px; overflow-y: auto; padding: 6px;
}
.gs-group-title { font-size: 11px; color: var(--text-tertiary); font-weight: 600; padding: 8px 10px 4px; }
.gs-item { padding: 8px 10px; border-radius: 8px; cursor: pointer; }
.gs-item:hover { background: rgba(99, 102, 241, 0.08); }
.gs-item__title { display: block; font-size: 13px; color: var(--text-primary); font-weight: 500; }
.gs-item__snippet {
  display: block; font-size: 12px; color: var(--text-tertiary); margin-top: 2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gs-loading, .gs-empty { padding: 16px; text-align: center; color: var(--text-tertiary); font-size: 13px; }
</style>
