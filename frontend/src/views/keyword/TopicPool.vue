<template>
  <div v-loading="loading">
    <div class="topic-toolbar">
      <span class="topic-toolbar__title">选题列表 <el-tag size="small" round type="info">{{ topics.length }}</el-tag></span>
      <el-input v-model="search" placeholder="搜索选题标题..." size="small" :prefix-icon="Search" clearable style="width: 240px;" />
      <el-button type="primary" size="small" :icon="Plus" @click="emit('create')">新建选题</el-button>
    </div>
    <div class="topic-card-grid" v-if="filtered.length">
      <div v-for="t in filtered" :key="t.id" class="topic-card" :data-focus-id="t.id">
        <div class="topic-card__head">
          <span class="topic-card__title">{{ t.title }}</span>
          <el-tag size="small" :type="topicStatusType(t.status)" effect="light">
            {{ topicStatusLabel(t.status) }}
          </el-tag>
        </div>
        <div class="topic-card__desc" v-if="t.description">{{ t.description }}</div>
        <div class="topic-card__desc topic-card__desc--empty" v-else>暂无描述</div>
        <div class="topic-card__kws" v-if="keywordNames(t.keyword_id_list).length">
          <span class="topic-card__kws-label"><el-icon><Key /></el-icon></span>
          <el-tag v-for="kn in keywordNames(t.keyword_id_list).slice(0, 6)" :key="kn.id" size="small" effect="plain" class="topic-kw-tag">{{ kn.word }}</el-tag>
          <span v-if="keywordNames(t.keyword_id_list).length > 6" class="topic-kw-more">+{{ keywordNames(t.keyword_id_list).length - 6 }}</span>
        </div>
        <div class="topic-card__foot">
          <span class="topic-card__meta" v-if="getPlatformName(t.platform_id) !== '—'">
            <el-tag size="small" effect="dark">{{ getPlatformName(t.platform_id) }}</el-tag>
          </span>
          <span class="topic-card__meta">{{ getAccountName(t.account_id) }}</span>
          <span class="topic-card__meta topic-card__date">{{ t.plan_date || '未排期' }}</span>
          <div class="topic-card__actions">
            <el-button text size="small" :icon="Edit" @click="emit('edit', t)">编辑</el-button>
            <el-button text size="small" type="danger" :icon="Delete" @click="remove(t)">删除</el-button>
          </div>
        </div>
      </div>
    </div>
    <EmptyState v-if="!loading && filtered.length === 0" title="暂无选题" size="small" icon="Tickets" />
  </div>
</template>

<script setup>
/**
 * 选题池（卡片式）：展示描述 / 关联关键词 / 平台账号 / 排期。
 *
 * 需要 keywords / platforms / accounts 三张表来把 id 翻成名字，所以由壳传入。
 * 删除是条目级动作，自己发请求 + emit `changed`；新建/编辑只 emit 意图。
 */
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete, Key, Search } from '@element-plus/icons-vue'
import { topicApi } from '../../api'
import { topicStatusLabel, topicStatusType } from '../../constants/status'
import { nameById } from '../../utils/lookup'
import EmptyState from '../../components/EmptyState.vue'

const props = defineProps({
  topics: { type: Array, default: () => [] },
  keywords: { type: Array, default: () => [] },
  platforms: { type: Array, default: () => [] },
  accounts: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['create', 'edit', 'changed'])

const search = ref('')

const filtered = computed(() => {
  const q = (search.value || '').trim().toLowerCase()
  if (!q) return props.topics
  return props.topics.filter(
    (t) => (t.title || '').toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q),
  )
})

/** `keyword_id_list` 是逗号分隔的 id 字符串，翻成关键词对象数组 */
function keywordNames(idListStr) {
  if (!idListStr) return []
  const ids = String(idListStr).split(',').map((s) => parseInt(s.trim())).filter((n) => !isNaN(n) && n > 0)
  return ids.map((id) => props.keywords.find((k) => k.id === id)).filter(Boolean)
}

const getPlatformName = (id) => nameById(props.platforms, id)
const getAccountName = (id) => nameById(props.accounts, id, 'account_name')

async function remove(row) {
  await ElMessageBox.confirm(`确定删除选题「${row.title}」吗？`, '提示', { type: 'warning' })
  await topicApi.delete(row.id)
  ElMessage.success('删除成功')
  emit('changed')
}
</script>

<style scoped>
/* 选题池卡片式 */
.topic-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.topic-toolbar__title { font-size: 14px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 6px; }
.topic-card-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px;
}
.topic-card {
  display: flex; flex-direction: column; gap: 8px;
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-left: 3px solid #6366f1; border-radius: var(--radius-lg);
  padding: 14px 16px; transition: transform .18s, box-shadow .18s;
}
.topic-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
.topic-card__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.topic-card__title { font-size: 14px; font-weight: 700; color: var(--text-primary); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.topic-card__desc { font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.topic-card__desc--empty { color: var(--text-tertiary); font-style: italic; }
.topic-card__kws { display: flex; gap: 4px; flex-wrap: wrap; align-items: center; }
.topic-card__kws-label { display: flex; align-items: center; color: var(--text-tertiary); font-size: 12px; }
.topic-kw-tag { font-size: 11px; }
.topic-kw-more { font-size: 11px; color: var(--text-tertiary); }
.topic-card__foot { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 4px; padding-top: 8px; border-top: 1px dashed var(--border-light); }
.topic-card__meta { font-size: 12px; color: var(--text-tertiary); }
.topic-card__date { margin-left: auto; }
.topic-card__actions { display: flex; gap: 2px; }
</style>
