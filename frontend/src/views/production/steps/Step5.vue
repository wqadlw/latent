<template>
  <div class="step-pane">
    <StepHeader :no="5" title="选择关键词 & 知识点" desc="从关键词库勾选关键词，从知识库挑选要注入大纲的知识点" />
    <div class="two-col-layout" v-loading="loadingOptions">
      <!-- 左栏：关键词 -->
      <div class="triple-col triple-left">
        <div class="col-header">
          <span class="col-title">关键词库</span>
          <el-tag size="small" type="info">{{ selectedKeywordIds.length }}/{{ options.keywords?.length || 0 }}</el-tag>
        </div>
        <!-- 分组筛选条 -->
        <div class="cat-filter-bar kw-filter-bar">
          <div class="cat-filter-chip" :class="{ active: kwGroupFilter === null }" @click="kwGroupFilter = null">全部</div>
          <div
            v-for="g in options.keyword_groups || []"
            :key="g.group.id"
            class="cat-filter-chip"
            :class="{ active: kwGroupFilter === g.group.id }"
            :style="kwGroupFilter === g.group.id ? { background: g.group.color, borderColor: g.group.color, color: '#fff' } : {}"
            @click="kwGroupFilter = g.group.id"
          ><el-icon class="kw-filter-icon" v-if="groupIconOfKw(g)"><component :is="groupIconOfKw(g)" /></el-icon>{{ g.group.name }} ({{ g.count }})</div>
        </div>
        <!-- 搜索 + 排序 -->
        <div class="kw-kw-toolbar">
          <el-input v-model="keywordSearch" placeholder="搜索关键词..." size="small" :prefix-icon="Search" clearable />
          <el-select v-model="kwSortBy" size="small" style="width: 108px">
            <el-option label="按优先级" value="priority" />
            <el-option label="按关键词" value="word" />
            <el-option label="按类型" value="type" />
          </el-select>
          <el-button size="small" :icon="kwSortDir === 'asc' ? SortUp : SortDown" :title="kwSortDir === 'asc' ? '升序' : '降序'" @click="kwSortDir = kwSortDir === 'asc' ? 'desc' : 'asc'" />
        </div>
        <div class="keyword-pool">
          <div
            v-for="k in filteredKeywords"
            :key="k.id"
            class="keyword-chip"
            :class="{ selected: selectedKeywordIds.includes(k.id) }"
            :style="(!selectedKeywordIds.includes(k.id) && groupColorOfKw(k.group_id)) ? { borderLeftColor: groupColorOfKw(k.group_id), borderLeftWidth: '3px' } : {}"
            @click="toggleKeyword(k.id)"
          >
            <span v-if="groupColorOfKw(k.group_id)" class="kw-chip-dot" :style="{ background: groupColorOfKw(k.group_id) }"></span>
            {{ k.word }}
          </div>
          <div v-if="filteredKeywords.length === 0" class="empty-tip" style="padding: 20px">暂无关键词</div>
        </div>
      </div>

      <!-- 中栏：知识库知识点（重设计：分类分组 + 全选 + 折叠） -->
      <div class="triple-col triple-center">
        <div class="col-header">
          <span class="col-title">知识库知识点</span>
          <div style="display: flex; gap: 6px; align-items: center;">
            <el-tag size="small" type="success">{{ selectedKnowledgeIds.length }} 已选</el-tag>
            <el-button text size="small" @click="clearKnowledge">清空</el-button>
          </div>
        </div>
        <div class="kc-toolbar">
          <el-select v-model="knowledgeSortBy" size="small" class="kc-sort" style="width: 132px">
            <el-option label="默认顺序" value="default" />
            <el-option label="重要性优先" value="importance" />
            <el-option label="最近更新" value="update_time" />
            <el-option label="标题 A-Z" value="title" />
          </el-select>
          <el-input v-model="knowledgeSearch" placeholder="搜索知识点标题 / 摘要 / 标签..." size="small" :prefix-icon="Search" clearable style="flex: 1;" />
        </div>

        <!-- 分类筛选条（修正字段：category.id / name / color） -->
        <div class="cat-filter-bar">
          <div
            class="cat-filter-chip"
            :class="{ active: selectedCatFilter === null }"
            @click="selectedCatFilter = null"
          >全部 ({{ totalKnowledgeCount }})</div>
          <div
            v-for="g in options.knowledge_grouped || []"
            :key="g.category.id"
            class="cat-filter-chip"
            :class="{ active: selectedCatFilter === g.category.id }"
            :style="selectedCatFilter === g.category.id ? { background: g.category.color, borderColor: g.category.color, color: '#fff' } : {}"
            @click="selectedCatFilter = g.category.id"
          >
            {{ g.category.name }} ({{ g.count }})
          </div>
        </div>

        <!-- 知识点分组列表（每个分类一个区块，可全选 / 折叠） -->
        <div class="kc-sections">
          <section v-for="sec in knowledgeSections" :key="sec.category.id" class="kc-section">
            <div class="kc-section__head">
              <span class="kc-section__dot" :style="{ background: sec.category.color }"></span>
              <span class="kc-section__name">{{ sec.category.name }}</span>
              <span class="kc-section__count">{{ sec.items.length }}</span>
              <div class="kc-section__ops">
                <button class="kc-section__btn" @click="toggleCategoryAll(sec)">{{ isCategoryAllSelected(sec) ? '取消全选' : '全选' }}</button>
                <button class="kc-section__btn" @click="toggleCollapse(sec.category.id)">{{ collapsedCats[sec.category.id] ? '展开' : '收起' }}</button>
              </div>
            </div>
            <div v-show="!collapsedCats[sec.category.id]" class="kc-section__body">
              <div
                v-for="ki in sec.items"
                :key="ki.id"
                class="knowledge-card-v4"
                :class="{ selected: selectedKnowledgeIds.includes(ki.id) }"
                @click="toggleKnowledge(ki.id)"
              >
                <div class="kc-header">
                  <span class="kc-title">{{ ki.title }}</span>
                  <el-icon v-if="selectedKnowledgeIds.includes(ki.id)" class="kc-check"><CircleCheckFilled /></el-icon>
                </div>
                <div v-if="ki.summary" class="kc-summary">{{ ki.summary }}</div>
                <div v-else class="kc-summary kc-summary-fallback">{{ (ki.content || '').slice(0, 60) }}{{ (ki.content || '').length > 60 ? '...' : '' }}</div>
                <div class="kc-footer">
                  <el-tag v-if="ki.importance === 'high'" size="small" type="danger" effect="plain">高重要</el-tag>
                  <el-tag v-else-if="ki.importance === 'normal'" size="small" type="info" effect="plain">普通</el-tag>
                  <span v-if="ki.tags" class="kc-tags">{{ ki.tags }}</span>
                  <el-button text size="small" :icon="View" @click.stop="previewKnowledge(ki)" class="kc-preview-btn">预览</el-button>
                </div>
              </div>
            </div>
          </section>
          <div v-if="knowledgeSections.length === 0" class="empty-tip" style="padding: 20px">
            暂无知识点，请先在知识库中添加
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import StepHeader from '../../../components/production/StepHeader.vue'
import { ref, reactive, computed } from 'vue'
import {
  Folder, MagicStick, Document, Reading, Notebook, Box, ChatDotRound, Flag, Collection, Files,
  Search, View, SortUp, SortDown, CircleCheckFilled,
} from '@element-plus/icons-vue'

// 步骤 5：关键词 & 知识点选择。父组件保留 selectedKeywordIds / selectedKnowledgeIds 等共享状态，
// 本组件把仅本步骤使用的 UI 状态（搜索/筛选/排序/折叠）与派生计算收归自身，父仅透传共享数据与变更函数。
const props = defineProps({
  options: { type: Object, required: true },
  loadingOptions: { type: Boolean, default: false },
  selectedKeywordIds: { type: Array, default: () => [] },
  selectedKnowledgeIds: { type: Array, default: () => [] },
  toggleKeyword: { type: Function, required: true },
  toggleKnowledge: { type: Function, required: true },
  clearKnowledge: { type: Function, required: true },
  toggleCategoryAll: { type: Function, required: true },
  previewKnowledge: { type: Function, required: true },
})

// —— 仅本步骤使用的本地 UI 状态 ——
const keywordSearch = ref('')
const kwGroupFilter = ref(null) // null=全部, 0=未分组, 否则 group.id
const kwSortBy = ref('priority')
const kwSortDir = ref('desc')
const knowledgeSearch = ref('')
const selectedCatFilter = ref(null)
const collapsedCats = reactive({}) // category_id -> true(收起)
const knowledgeSortBy = ref('default') // default/importance/update_time/title

function sortItems(items) {
  const arr = items.slice()
  if (knowledgeSortBy.value === 'importance') {
    const w = { high: 0, normal: 1, low: 2 }
    arr.sort((a, b) => (w[a.importance] ?? 9) - (w[b.importance] ?? 9))
  } else if (knowledgeSortBy.value === 'update_time') {
    arr.sort((a, b) => (b.update_time || '').localeCompare(a.update_time || ''))
  } else if (knowledgeSortBy.value === 'title') {
    arr.sort((a, b) => (a.title || '').localeCompare(b.title || '', 'zh'))
  }
  return arr
}

const iconMap = {
  Folder, MagicStick, Document, Reading, Notebook, Box, ChatDotRound, Flag, Collection, Files,
}
function groupColorOfKw(id) {
  if (!id) return ''
  const grp = (props.options.keyword_groups || []).find(g => g.group.id === id)
  return grp ? grp.group.color : ''
}
function groupIconOfKw(g) { return iconMap[g?.group?.icon] || Folder }

const filteredKeywords = computed(() => {
  let arr = props.options.keywords || []
  if (kwGroupFilter.value != null) {
    if (kwGroupFilter.value === 0) arr = arr.filter(k => !k.group_id)
    else arr = arr.filter(k => k.group_id === kwGroupFilter.value)
  }
  const kw = keywordSearch.value.toLowerCase()
  if (kw) arr = arr.filter(k => (k.word || '').toLowerCase().includes(kw))
  const by = kwSortBy.value
  const dir = kwSortDir.value === 'asc' ? 1 : -1
  arr = [...arr].sort((a, b) => {
    if (by === 'priority') return (a.priority - b.priority) * dir
    const va = (a[by] || '').toString()
    const vb = (b[by] || '').toString()
    return va.localeCompare(vb, 'zh-CN') * dir
  })
  return arr
})

const totalKnowledgeCount = computed(() => {
  return (props.options.knowledge_grouped || []).reduce((sum, g) => sum + (g.count || (g.items ? g.items.length : 0)), 0)
})

const knowledgeSections = computed(() => {
  let sections = (props.options.knowledge_grouped || []).map(g => ({
    category: g.category || { id: 0, name: '未分类', color: '#94a3b8' },
    items: g.items ? g.items.slice() : [],
  }))
  if (selectedCatFilter.value !== null) {
    sections = sections.filter(s => s.category.id === selectedCatFilter.value)
  }
  if (knowledgeSearch.value) {
    const kw = knowledgeSearch.value.toLowerCase()
    sections = sections
      .map(s => ({
        category: s.category,
        items: s.items.filter(ki =>
          (ki.title || '').toLowerCase().includes(kw) ||
          (ki.summary || '').toLowerCase().includes(kw) ||
          (ki.content || '').toLowerCase().includes(kw) ||
          (ki.tags || '').toLowerCase().includes(kw)
        ),
      }))
      .filter(s => s.items.length > 0)
  }
  return sections.map(s => ({ ...s, items: sortItems(s.items) }))
})

function isCategoryAllSelected(sec) {
  if (!sec.items.length) return false
  return sec.items.every(ki => props.selectedKnowledgeIds.includes(ki.id))
}
function toggleCollapse(catId) {
  collapsedCats[catId] = !collapsedCats[catId]
}

// toggleCategoryAll 由父组件透传（父持有 selectedKnowledgeIds 真源），本组件仅提供读取用的判断
</script>
