<template>
  <div class="bg-library">
    <el-alert
      class="bl-banner"
      :closable="false"
      type="primary"
      show-icon
    >
      <template #title>
        <strong>背景库 · 一键整理并投喂给任意 AI</strong>
      </template>
      <template #default>
        本板块把「品牌资产 + 知识库」实时整理成一份完整的背景资料。
        <b>硬性背景</b>由系统结合当前知识库内容生成、可自由编辑；其余知识点与品牌可按需增删。
        选好后点「一键复制」，即可把背景粘贴给任意 AI，让它先了解我们、再据此创作。
      </template>
    </el-alert>

    <el-row :gutter="16" v-loading="loading">
      <!-- 左：编辑区 -->
      <el-col :xs="24" :lg="14">
        <!-- 硬性背景 -->
        <el-card class="bl-card" shadow="never">
          <template #header>
            <div class="bl-card__head">
              <span class="bl-card__title"><el-icon><Memo /></el-icon> 一、硬性背景（核心 · 可编辑）</span>
              <div class="bl-card__actions">
                <el-button size="small" :icon="Refresh" :loading="generating" @click="regenerate">重新生成</el-button>
                <el-button size="small" type="primary" :icon="Check" :loading="saving" @click="save">保存</el-button>
              </div>
            </div>
          </template>
          <el-input
            v-model="hardBackground"
            type="textarea"
            :rows="14"
            placeholder="系统将结合当前知识库自动生成硬性背景，您可在此直接编辑……"
            resize="vertical"
          />
          <div class="bl-hint" v-if="!hasSaved">
            <el-icon><InfoFilled /></el-icon> 当前为系统自动生成的默认硬性背景，编辑后点「保存」即可留存。
          </div>
        </el-card>

        <!-- 品牌资产 -->
        <el-card class="bl-card" shadow="never">
          <template #header>
            <div class="bl-card__head">
              <span class="bl-card__title"><el-icon><GoldMedal /></el-icon> 二、品牌资产（可整体开关）</span>
              <el-switch
                v-model="includeBrand"
                active-text="包含"
                inactive-text="不包含"
                inline-prompt
              />
            </div>
          </template>
          <template v-if="brand">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="公司名称">{{ brand.brand_name || '—' }}</el-descriptions-item>
              <el-descriptions-item label="定位语">{{ brand.slogan || '—' }}</el-descriptions-item>
              <el-descriptions-item label="官网">{{ brand.official_website || '—' }}</el-descriptions-item>
              <el-descriptions-item label="核心产品">{{ brand.core_products || '—' }}</el-descriptions-item>
              <el-descriptions-item label="独特卖点">{{ brand.unique_selling_points || '—' }}</el-descriptions-item>
              <el-descriptions-item label="品牌故事">{{ brand.brand_story || '—' }}</el-descriptions-item>
            </el-descriptions>
          </template>
          <el-empty v-else description="本行业暂无品牌资产，可在「品牌资产库」中创建" :image-size="60" />
        </el-card>

        <!-- 知识库要点 -->
        <el-card class="bl-card" shadow="never">
          <template #header>
            <div class="bl-card__head">
              <span class="bl-card__title"><el-icon><Collection /></el-icon> 三、知识库要点（按需勾选 · 可增删）</span>
              <div class="bl-card__actions">
                <el-button size="small" @click="toggleAll(true)">全选</el-button>
                <el-button size="small" @click="toggleAll(false)">全不选</el-button>
                <span class="bl-count">已选 <b>{{ selectedCount }}</b> / {{ totalCount }}</span>
              </div>
            </div>
          </template>
          <el-collapse v-model="activeCats">
            <el-collapse-item v-for="cat in categories" :key="cat.id" :name="cat.id" :disabled="cat.items.length === 0">
              <template #title>
                <span class="bl-cat-title">
                  <span class="bl-dot" :style="{ background: cat.color }"></span>
                  {{ cat.name }}
                  <el-tag size="small" round type="info">{{ catCount(cat) }}</el-tag>
                </span>
              </template>
              <div class="bl-kw-grid">
                <label
                  v-for="item in cat.items"
                  :key="item.id"
                  class="bl-kw-item"
                  :class="{ 'is-excluded': excludedSet.has(item.id) }"
                >
                  <el-checkbox
                    :model-value="!excludedSet.has(item.id)"
                    @change="() => toggleItem(item)"
                  />
                  <span class="bl-kw-name">
                    {{ item.title }}
                    <el-tag v-if="item.importance === 'high'" size="small" type="danger" effect="plain">重要</el-tag>
                  </span>
                </label>
              </div>
            </el-collapse-item>
          </el-collapse>
          <el-empty v-if="!categories.length" description="本行业暂无知识点" :image-size="60" />
        </el-card>
      </el-col>

      <!-- 右：预览 + 复制 -->
      <el-col :xs="24" :lg="10">
        <el-card class="bl-card bl-preview" shadow="never">
          <template #header>
            <div class="bl-card__head">
              <span class="bl-card__title"><el-icon><Document /></el-icon> 四、投喂文本预览</span>
              <el-button type="success" size="small" :icon="CopyDocument" @click="copy">一键复制</el-button>
            </div>
          </template>
          <el-input
            :model-value="copyText"
            type="textarea"
            :rows="26"
            readonly
            resize="none"
            class="bl-preview__text"
          />
          <div class="bl-preview__stat">
            预计字数 ≈ {{ copyText.length }} 字 · 包含硬性背景 + {{ includeBrand && brand ? '品牌资产 + ' : '' }}{{ selectedCount }} 条知识点
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Memo, Refresh, Check, GoldMedal, Collection, Document, CopyDocument, InfoFilled,
} from '@element-plus/icons-vue'
import { useAppStore } from '../../store/app'
import { backgroundApi } from '../../api'
import { writeClipboard } from '../../utils/clipboard'

const store = useAppStore()
const industryId = computed(() => store.currentIndustryId)

const loading = ref(false)
const saving = ref(false)
const generating = ref(false)

const hardBackground = ref('')
const hasSaved = ref(false)
const includeBrand = ref(true)
const brand = ref(null)
const categories = ref([])
const excludedSet = ref(new Set())
const activeCats = ref([])

const totalCount = computed(() =>
  categories.value.reduce((n, c) => n + c.items.length, 0)
)
const selectedCount = computed(() =>
  categories.value.reduce((n, c) => n + c.items.filter(it => !excludedSet.value.has(it.id)).length, 0)
)

function catCount(cat) {
  return cat.items.filter(it => !excludedSet.value.has(it.id)).length
}

function buildCopyText() {
  const lines = []
  lines.push('# 背景资料（投喂给 AI 的创作上下文）')
  lines.push('> 复制以下内容发送给任意 AI，即可让其先了解我们的背景，再据此创作。\n')

  lines.push('## 一、硬性背景')
  lines.push((hardBackground.value || '').trim() || '（未填写硬性背景）')
  lines.push('')

  if (includeBrand.value && brand.value) {
    lines.push('## 二、品牌资产')
    const b = brand.value
    if (b.brand_name) lines.push(`- 公司名称：${b.brand_name}`)
    if (b.slogan) lines.push(`- 定位语：${b.slogan}`)
    if (b.official_website) lines.push(`- 官网：${b.official_website}`)
    if (b.core_products) lines.push(`- 核心产品：${b.core_products}`)
    if (b.unique_selling_points) lines.push(`- 独特卖点：${b.unique_selling_points}`)
    if (b.brand_story) lines.push(`- 品牌故事：${b.brand_story}`)
    lines.push('')
  }

  lines.push('## 三、知识库要点')
  let any = false
  for (const cat of categories.value) {
    const its = cat.items.filter(it => !excludedSet.value.has(it.id))
    if (!its.length) continue
    any = true
    lines.push(`### ${cat.name}`)
    for (const it of its) {
      const body = (it.summary || it.content || '').trim().replace(/\s+/g, ' ')
      const shown = body.length > 200 ? body.slice(0, 200) + '…' : body
      lines.push(`- ${it.title}${shown ? '：' + shown : ''}`)
    }
    lines.push('')
  }
  if (!any) lines.push('（未选择任何知识点）\n')

  return lines.join('\n')
}

const copyText = computed(() => buildCopyText())

async function load() {
  if (!industryId.value) return
  loading.value = true
  try {
    const res = await backgroundApi.get(industryId.value)
    const d = res.data || {}
    hardBackground.value = d.hard_background || ''
    hasSaved.value = !!d.has_saved
    includeBrand.value = d.include_brand !== 0
    brand.value = d.brand || null
    categories.value = d.categories || []
    excludedSet.value = new Set(d.excluded_item_ids || [])
    activeCats.value = categories.value.map(c => c.id).filter(id => id !== 0)
  } catch (e) {
    ElMessage.error('加载背景库失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!industryId.value) return
  saving.value = true
  try {
    const res = await backgroundApi.save({
      industry_id: industryId.value,
      hard_background: hardBackground.value,
      include_brand: includeBrand.value ? 1 : 0,
      excluded_item_ids: Array.from(excludedSet.value),
    })
    hasSaved.value = !!(res.data && res.data.has_saved)
    ElMessage.success('背景库已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function regenerate() {
  if (!industryId.value) return
  generating.value = true
  try {
    const res = await backgroundApi.generate(industryId.value)
    hardBackground.value = res.data?.hard_background || ''
    ElMessage.success('已根据当前知识库重新生成硬性背景（记得点保存）')
  } catch (e) {
    ElMessage.error('生成失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    generating.value = false
  }
}

function toggleItem(item) {
  const s = new Set(excludedSet.value)
  if (s.has(item.id)) s.delete(item.id)
  else s.add(item.id)
  excludedSet.value = s
}

function toggleAll(include) {
  const s = new Set(excludedSet.value)
  for (const cat of categories.value) {
    for (const it of cat.items) {
      if (include) s.delete(it.id)
      else s.add(it.id)
    }
  }
  excludedSet.value = s
}

async function copy() {
  const text = copyText.value
  if (!text.trim()) {
    ElMessage.warning('暂无可复制的内容')
    return
  }
  // 用底层 writeClipboard 保留本处自定义提示语，同时获得非安全上下文降级
  if (await writeClipboard(text)) {
    ElMessage.success('已复制背景资料，可粘贴给任意 AI')
  } else {
    ElMessage.error('复制失败，请手动选择预览文本复制')
  }
}

onMounted(load)
watch(industryId, (v, old) => { if (v && v !== old) load() })
</script>

<style scoped>
.bg-library { padding: 4px 0; }
.bl-banner { margin-bottom: 14px; }
.bl-card { margin-bottom: 14px; }
.bl-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.bl-card__title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}
.bl-card__actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.bl-count { color: #64748b; font-size: 13px; }
.bl-hint {
  margin-top: 8px;
  color: #b45309;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.bl-cat-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.bl-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.bl-kw-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 6px 12px;
}
.bl-kw-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 4px 6px;
  border-radius: 6px;
  cursor: pointer;
}
.bl-kw-item.is-excluded { opacity: 0.45; }
.bl-kw-name { font-size: 13px; line-height: 1.5; }
.bl-preview { position: sticky; top: 12px; }
.bl-preview__text { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
.bl-preview__stat { margin-top: 8px; color: #64748b; font-size: 12px; }
</style>
