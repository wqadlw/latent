<template>
  <div class="prompt-center">
    <el-alert class="pc-banner" :closable="false" type="success" show-icon>
      <template #title><strong>提示词三体系 · 已收口为统一视图</strong></template>
      <template #default>
        本页把三套提示词体系统一呈现：
        <b>① 自动化指挥中心</b>（automation_prompt，全局、可编辑）<b>② AI 提示词库</b>（prompt_library_item，按行业）
        <b>③ 阶段常量</b>（STAGE_PROMPTS，为 ① 中 STAGE_* 的出厂默认）。
        自动化路径与手动路径共享同一套「大纲→初稿→洗稿→GEO」流水线，差异仅在命名（depolish ↔ rewrite）。
        两者分别由编排引擎(orchestrator)与生成引擎(generation)消费，本视图为只读总览，便于一处核对。
      </template>
    </el-alert>

    <div class="pc-toolbar">
      <el-radio-group v-model="systemFilter" size="small">
        <el-radio-button label="all">全部体系</el-radio-button>
        <el-radio-button label="automation">自动化指挥中心</el-radio-button>
        <el-radio-button label="library">AI 提示词库</el-radio-button>
      </el-radio-group>
      <el-input v-model="keyword" placeholder="搜索名称 / 标识 / 内容…" :prefix-icon="Search" size="small" clearable style="width: 280px" />
      <span class="pc-stat">共 {{ filtered.length }} 条</span>
    </div>

    <el-table :data="filtered" row-key="uid" border stripe size="small" class="pc-table" v-loading="loading">
      <el-table-column type="expand">
        <template #default="{ row }">
          <pre class="pc-content">{{ row.content || '（无内容）' }}</pre>
        </template>
      </el-table-column>
      <el-table-column prop="group" label="功能域" width="120">
        <template #default="{ row }"><el-tag size="small" effect="plain">{{ row.group }}</el-tag></template>
      </el-table-column>
      <el-table-column label="体系" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="row.system === 'automation' ? 'warning' : 'primary'">
            {{ row.system === 'automation' ? '自动化指挥中心' : 'AI提示词库' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="rawCat" label="原生分类" width="110" />
      <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="ident" label="标识" width="180" show-overflow-tooltip>
        <template #default="{ row }"><code class="pc-code">{{ row.ident }}</code></template>
      </el-table-column>
      <el-table-column label="预览" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">{{ preview(row.content) }}</template>
      </el-table-column>
      <el-table-column label="标记" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.isDefault" size="small" type="success" effect="plain">默认</el-tag>
          <span v-if="row.usageCount != null" class="pc-usage">用 {{ row.usageCount }}</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Memo } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { automationPromptApi, promptLibraryApi } from '../api'

const store = useAppStore()
const industryId = computed(() => store.currentIndustryId)

const loading = ref(false)
const systemFilter = ref('all')
const keyword = ref('')
const rows = ref([])

const CAT_LABEL = {
  team: '团队设定', system: '系统提示', planner: '主编·规划', stage: '阶段提示',
  writer: '写手', revise: '整改/质量闸', mdx: '官方MDX',
  outline: '大纲', draft: '初稿', rewrite: '洗稿/改写', illustration: '配图', geo: 'GEO强化',
}

function unifiedGroup(system, category, key) {
  if (system === 'automation' && category === 'stage') {
    const k = (key || '').toLowerCase()
    if (k.includes('outline')) return '大纲'
    if (k.includes('draft')) return '初稿'
    if (k.includes('depolish')) return '洗稿/改写'
    if (k.includes('geo')) return 'GEO强化'
    if (k.includes('research')) return '调研'
    if (k.includes('search_opt')) return '搜索优化'
    return '阶段提示'
  }
  if (system === 'automation') return CAT_LABEL[category] || category || '其他'
  return CAT_LABEL[category] || category || '其他'
}

function preview(text) {
  const t = (text || '').replace(/\s+/g, ' ').trim()
  return t.length > 80 ? t.slice(0, 80) + '…' : t
}

async function load() {
  loading.value = true
  try {
    const out = []
    // ① 自动化指挥中心
    try {
      const a = await automationPromptApi.list()
      const list = a.data || a || []
      list.forEach((p, i) => out.push({
        uid: `a-${p.key || i}`,
        system: 'automation',
        group: unifiedGroup('automation', p.category, p.key),
        rawCat: p.category || '',
        name: p.name || p.key || '',
        ident: p.key || '',
        content: p.content || '',
        isDefault: false,
        usageCount: null,
      }))
    } catch (e) { /* 自动化提示词缺失不阻塞总览 */ }
    // ② AI 提示词库（按当前行业）
    if (industryId.value) {
      try {
        const l = await promptLibraryApi.list(industryId.value)
        const list = l.data || l || []
        list.forEach((p, i) => out.push({
          uid: `l-${p.id || i}`,
          system: 'library',
          group: unifiedGroup('library', p.category, p.id),
          rawCat: p.category || '',
          name: p.name || '',
          ident: String(p.id ?? ''),
          content: p.content || '',
          isDefault: !!p.is_default,
          usageCount: p.usage_count,
        }))
      } catch (e) { /* 提示词库缺失不阻塞总览 */ }
    }
    rows.value = out
  } catch (e) {
    ElMessage.error('加载提示词总览失败：' + (e?.message || ''))
  } finally {
    loading.value = false
  }
}

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter(r => {
    if (systemFilter.value !== 'all' && r.system !== systemFilter.value) return false
    if (!kw) return true
    return (r.name + ' ' + r.ident + ' ' + (r.content || '')).toLowerCase().includes(kw)
  })
})

onMounted(load)
</script>

<style scoped>
.prompt-center { padding: 4px 0; }
.pc-banner { margin-bottom: 14px; }
.pc-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.pc-stat { color: #64748b; font-size: 13px; }
.pc-table { margin-bottom: 12px; }
.pc-code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; color: #475569; }
.pc-usage { color: #94a3b8; font-size: 12px; margin-left: 4px; }
.pc-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  max-height: 360px;
  overflow: auto;
  margin: 0;
  padding: 8px 12px;
  background: #f8fafc;
}
</style>
