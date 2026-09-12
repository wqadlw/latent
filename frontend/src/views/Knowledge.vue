<template>
  <div class="knowledge-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget && kbTab === 'items'">
      <el-dropdown @command="handleExport" trigger="click">
        <el-button :icon="Download">导出</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="json">导出为 JSON</el-dropdown-item>
            <el-dropdown-item command="csv">导出为 CSV</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button :icon="DataAnalysis" @click="showStats = !showStats">统计</el-button>
      <el-button type="warning" :icon="MagicStick" @click="seedDefaults" :loading="seeding">一键灌入默认论据</el-button>
      <el-button type="success" :icon="Upload" @click="openBatchImport">批量导入</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建知识点</el-button>
    </Teleport>

    <el-tabs v-model="kbTab" class="kb-tabs">
      <el-tab-pane label="知识点管理" name="items">
    <!-- 顶部：GEO 论据库价值说明 + 指标 -->
    <section class="hero">
      <div class="hero__lead">
        <span class="hero__eyebrow"><el-icon><Collection /></el-icon> GEO 作战 · 可引用论据库</span>
        <h2 class="hero__title">把行业知识沉淀为「可引用、可溯源」的论据</h2>
        <p class="hero__desc">知识库是 GEO 软文的论据底座：每条知识点都应带事实、来源与重要性，让 AI 在回答时优先引用我们、而非泛泛而谈。按分类管理，支持批量导入与拖拽排序。</p>
      </div>
      <div class="hero__metrics">
        <div class="metric">
          <div class="metric__num">{{ items.length }}</div>
          <div class="metric__label">知识点</div>
        </div>
        <div class="metric metric--cat">
          <div class="metric__num">{{ categories.length }}</div>
          <div class="metric__label">分类</div>
        </div>
        <div class="metric metric--ok">
          <div class="metric__num">{{ highCount }}</div>
          <div class="metric__label">高重要性</div>
        </div>
        <div class="metric metric--pub">
          <div class="metric__num">{{ publishedCount }}</div>
          <div class="metric__label">已发布</div>
        </div>
      </div>
    </section>

    <!-- 统计面板 -->
    <transition name="slide-down">
      <div v-if="showStats && stats" class="stats-bar">
        <div class="stat-item">
          <div class="stat-num">{{ stats.total }}</div>
          <div class="stat-label">知识点总数</div>
        </div>
        <div class="stat-item">
          <div class="stat-num">{{ stats.categories }}</div>
          <div class="stat-label">分类数</div>
        </div>
        <div class="stat-item">
          <div class="stat-num text-amber">{{ stats.by_importance?.high || 0 }}</div>
          <div class="stat-label">高重要性</div>
        </div>
        <div class="stat-item">
          <div class="stat-num text-green">{{ stats.by_status?.published || 0 }}</div>
          <div class="stat-label">已发布</div>
        </div>
        <div class="stat-item">
          <div class="stat-num text-gray">{{ stats.by_status?.draft || 0 }}</div>
          <div class="stat-label">草稿</div>
        </div>
        <div class="stat-item">
          <div class="stat-num">{{ stats.total_views || 0 }}</div>
          <div class="stat-label">总查看次数</div>
        </div>
      </div>
    </transition>

    <div class="kw-layout">
      <!-- 左侧分类 -->
      <div class="category-panel">
        <div class="panel-head">
          <span class="panel-title">分类</span>
          <el-button size="small" type="primary" link @click="openCategoryCreate">新增</el-button>
        </div>
        <transition-group name="cat-list" tag="div" class="category-list">
          <div class="category-item" key="__all__" :class="{ 'is-active': !activeCategory }" @click="activeCategory = null">
            <el-icon><Files /></el-icon>
            <span>全部</span>
            <el-tag size="small" round>{{ totalCount }}</el-tag>
          </div>
          <div
            v-for="c in categories"
            :key="c.id"
            class="category-item"
            :class="{ 'is-active': activeCategory === c.id }"
            @click="activeCategory = c.id"
          >
            <el-icon :style="{ color: c.color || '#6366f1' }"><component :is="iconMap[c.icon] || Folder" /></el-icon>
            <span class="category-name">{{ c.name }}</span>
            <el-tag size="small" round>{{ c.item_count }}</el-tag>
            <div class="category-actions" @click.stop>
              <el-button text size="small" :icon="Edit" title="编辑分类" @click="openCategoryEdit(c)" />
              <el-button text size="small" type="danger" :icon="Delete" title="删除分类" @click="removeCategory(c)" />
            </div>
          </div>
        </transition-group>
      </div>

      <!-- 右侧知识点 -->
      <div class="item-panel">
        <div class="panel-head">
          <div class="head-left">
            <span class="panel-title">知识点列表</span>
            <el-tag v-if="activeCategory" size="small" type="info" closable @close="activeCategory = null">
              {{ getCategoryName(activeCategory) }}
            </el-tag>
          </div>
          <div class="head-right">
            <el-input v-model="search" placeholder="搜索标题/内容/标签..." :prefix-icon="Search" size="small" clearable style="width: 240px" />
            <el-select v-model="sortBy" size="small" class="k-sort" style="width: 132px">
              <el-option label="默认顺序" value="default" />
              <el-option label="按重要度" value="importance" />
              <el-option label="按更新时间" value="update_time" />
              <el-option label="按名称" value="title" />
              <el-option label="按来源" value="source" />
              <el-option label="自定义（拖拽）" value="custom" />
            </el-select>
            <el-tooltip :content="sortDir === 'asc' ? '当前升序，点击切换为降序' : '当前降序，点击切换为升序'">
              <el-button
                size="small"
                :icon="sortDir === 'asc' ? SortUp : SortDown"
                :disabled="sortBy === 'default' || sortBy === 'custom'"
                @click="toggleSortDir"
              >{{ sortDir === 'asc' ? '升序' : '降序' }}</el-button>
            </el-tooltip>
            <el-radio-group v-model="viewMode" size="small">
              <el-radio-button value="grid"><el-icon><Grid /></el-icon></el-radio-button>
              <el-radio-button value="list"><el-icon><List /></el-icon></el-radio-button>
            </el-radio-group>
            <el-button size="small" :icon="Operation" :type="batchMode ? 'primary' : 'default'" @click="batchMode = !batchMode">
              {{ batchMode ? '退出批量' : '批量管理' }}
            </el-button>
          </div>
        </div>

        <!-- 标签过滤 -->
        <div v-if="allTags.length" class="tag-filter-bar">
          <span class="tag-filter-label">标签：</span>
          <el-tag
            v-for="tag in allTags"
            :key="tag"
            :type="activeTags.includes(tag) ? 'primary' : 'info'"
            :effect="activeTags.includes(tag) ? 'dark' : 'plain'"
            size="small"
            class="tag-chip"
            @click="toggleTag(tag)"
          >{{ tag }}</el-tag>
          <el-button v-if="activeTags.length" text size="small" type="danger" @click="activeTags = []">清除</el-button>
        </div>

        <div
          v-loading="loading"
          class="item-list"
          :class="[viewMode, { 'is-batch': batchMode }]"
        >
          <template v-if="viewMode === 'grid'">
            <div
              v-for="item in filteredList"
              :key="item.id"
              class="item-card"
              :data-focus-id="item.id"
              :class="{ 'is-selected': batchMode && selectedItems.includes(item.id), 'is-dragging': dragItemId === item.id }"
              :draggable="sortBy === 'custom'"
              @click="batchMode ? toggleItemSelect(item) : openDetail(item)"
              @dragstart="onItemDragStart(item, $event)"
              @dragover.prevent="onItemDragOver($event)"
              @drop="onItemDrop(item)"
            >
              <el-checkbox v-if="batchMode" class="item-select" :model-value="selectedItems.includes(item.id)" @click.stop @change="() => toggleItemSelect(item)" />
              <el-icon v-if="sortBy === 'custom' && !batchMode" class="item-drag" title="拖拽排序"><Rank /></el-icon>
              <div class="item-card__top">
                <div class="item-card__title-row">
                  <el-icon v-if="item.importance === 'high'" class="imp-high"><StarFilled /></el-icon>
                  <span class="item-card__title">{{ item.title }}</span>
                </div>
                <div class="item-card__badges">
                  <el-tag size="small" :color="getCategoryColor(item.category_id)" effect="light" style="border: none; color: #fff;">
                    {{ getCategoryName(item.category_id) }}
                  </el-tag>
                  <el-tag v-if="item.status === 'draft'" size="small" type="warning">草稿</el-tag>
                </div>
              </div>
              <div class="item-card__summary">{{ item.summary || item.content || '暂无内容' }}</div>
              <div v-if="item.tags" class="item-card__tags">
                <el-tag v-for="t in parseTags(item.tags)" :key="t" size="small" effect="plain" type="info" class="kw-tag">{{ t }}</el-tag>
              </div>
              <div class="item-card__footer">
                <div class="item-card__meta">
                  <span v-if="item.source" class="meta-item"><el-icon><Link /></el-icon>{{ item.source }}</span>
                  <span class="meta-item"><el-icon><View /></el-icon>{{ item.view_count || 0 }}</span>
                  <span class="meta-item">{{ formatTime(item.update_time) }}</span>
                </div>
                <div class="item-card__actions" @click.stop>
                  <el-button text size="small" :icon="Edit" @click="openEdit(item)">编辑</el-button>
                  <el-button text size="small" type="danger" :icon="Delete" @click="remove(item)">删除</el-button>
                </div>
              </div>
            </div>
          </template>
          <template v-else>
            <div
              v-for="item in filteredList"
              :key="item.id"
              class="item-row"
              :data-focus-id="item.id"
              :class="{ 'is-selected': batchMode && selectedItems.includes(item.id), 'is-dragging': dragItemId === item.id }"
              :draggable="sortBy === 'custom'"
              @click="batchMode ? toggleItemSelect(item) : openDetail(item)"
              @dragstart="onItemDragStart(item, $event)"
              @dragover.prevent="onItemDragOver($event)"
              @drop="onItemDrop(item)"
            >
              <el-checkbox v-if="batchMode" class="item-select" :model-value="selectedItems.includes(item.id)" @click.stop @change="() => toggleItemSelect(item)" />
              <el-icon v-if="sortBy === 'custom' && !batchMode" class="item-drag" title="拖拽排序"><Rank /></el-icon>
              <div class="item-row__main">
                <div class="item-row__title-row">
                  <el-icon v-if="item.importance === 'high'" class="imp-high"><StarFilled /></el-icon>
                  <span class="item-row__title">{{ item.title }}</span>
                  <el-tag size="small" :color="getCategoryColor(item.category_id)" effect="light" style="border: none; color: #fff;">{{ getCategoryName(item.category_id) }}</el-tag>
                  <el-tag v-if="item.status === 'draft'" size="small" type="warning">草稿</el-tag>
                </div>
                <div class="item-row__summary">{{ item.summary || item.content || '暂无内容' }}</div>
                <div v-if="item.tags" class="item-row__tags">
                  <el-tag v-for="t in parseTags(item.tags).slice(0, 5)" :key="t" size="small" effect="plain" type="info">{{ t }}</el-tag>
                </div>
              </div>
              <div class="item-row__meta">
                <span v-if="item.source" class="meta-item"><el-icon><Link /></el-icon>{{ item.source }}</span>
                <span class="meta-item"><el-icon><View /></el-icon>{{ item.view_count || 0 }}</span>
                <span class="meta-item">{{ formatTime(item.update_time) }}</span>
              </div>
              <div class="item-row__actions" @click.stop>
                <el-button text size="small" :icon="Edit" @click="openEdit(item)">编辑</el-button>
                <el-button text size="small" type="danger" :icon="Delete" @click="remove(item)">删除</el-button>
              </div>
            </div>
          </template>
        </div>
        <EmptyState v-if="!loading && filteredList.length === 0" title="暂无知识点" desc="点击右上角「新建知识点」开始添加" size="small" icon="Collection" />
        <!-- 批量操作条 -->
        <div v-if="batchMode && selectedItems.length" class="batch-bar">
          <span class="batch-count">已选 <b>{{ selectedItems.length }}</b> 个</span>
          <span class="batch-label">移动分类：</span>
          <el-select v-model="batchTargetCategory" placeholder="选择分类" size="small" clearable style="width: 160px" @change="onBatchMoveCategory">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
          <span class="batch-label">重要度：</span>
          <el-select v-model="batchTargetImportance" placeholder="设置" size="small" clearable style="width: 120px" @change="onBatchSetImportance">
            <el-option label="高" value="high" />
            <el-option label="中" value="normal" />
            <el-option label="低" value="low" />
          </el-select>
          <el-button size="small" type="danger" :icon="Delete" :loading="batchSubmitting" @click="onBatchDeleteItems">删除</el-button>
          <el-button size="small" @click="clearItemSelection">取消选择</el-button>
        </div>
      </div>
    </div>
      </el-tab-pane>
      <el-tab-pane label="背景库" name="background">
        <BackgroundLibrary />
      </el-tab-pane>
    </el-tabs>

    <!-- 分类弹窗 -->
    <el-dialog v-model="categoryDialog" :title="editingCategory ? '编辑分类' : '新建分类'" width="460px">
      <el-form :model="categoryForm" label-width="80px">
        <el-form-item label="分类名称">
          <el-input v-model="categoryForm.name" placeholder="请输入分类名称" />
        </el-form-item>
        <el-form-item label="图标">
          <el-select v-model="categoryForm.icon" placeholder="选择图标" style="width: 100%;">
            <el-option v-for="ic in iconOptions" :key="ic" :label="ic" :value="ic">
              <el-icon style="vertical-align: middle;"><component :is="iconMap[ic]" v-if="iconMap[ic]" /></el-icon>
              <span style="margin-left: 8px;">{{ ic }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="主题色">
          <div class="color-picker-row">
            <div
              v-for="c in colorOptions"
              :key="c"
              class="color-dot"
              :style="{ background: c }"
              :class="{ active: categoryForm.color === c }"
              @click="categoryForm.color = c"
            ></div>
          </div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="categoryForm.description" type="textarea" :rows="2" placeholder="分类描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="categoryDialog = false">取消</el-button>
        <el-button type="primary" @click="saveCategory" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 知识点弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑知识点' : '新建知识点'" width="720px" top="5vh">
      <el-form :model="form" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="知识点标题（必填）" />
        </el-form-item>
        <el-form-item label="分类">
          <div style="display: flex; gap: 8px; width: 100%;">
            <el-select v-model="form.category_id" style="flex: 1;" clearable placeholder="选择分类">
              <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
            </el-select>
            <el-button :icon="Plus" @click="inlineCreateCategory" title="新建分类" />
          </div>
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="form.summary" type="textarea" :rows="2" placeholder="一句话概括这个知识点（可选，用于快速预览）" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="8" placeholder="知识点详细内容" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="重要性">
              <el-select v-model="form.importance" style="width: 100%;">
                <el-option label="高" value="high"><el-icon style="color: #f59e0b;"><StarFilled /></el-icon> 高</el-option>
                <el-option label="普通" value="normal">普通</el-option>
                <el-option label="低" value="low">低</el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width: 100%;">
                <el-option label="已发布" value="published" />
                <el-option label="草稿" value="draft" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="来源">
              <el-input v-model="form.source" placeholder="如：官网/手册" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="标签">
          <el-input v-model="form.tags" placeholder="多个标签用逗号分隔，如：敏感肌,护理,防晒" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 知识点详情抽屉 -->
    <el-drawer v-model="detailDrawer" size="520px" :title="detailItem?.title || '详情'">
      <div v-if="detailItem" class="detail-content">
        <div class="detail-meta">
          <el-tag :color="getCategoryColor(detailItem.category_id)" effect="dark" style="border: none;">
            {{ getCategoryName(detailItem.category_id) }}
          </el-tag>
          <el-tag v-if="detailItem.importance === 'high'" type="warning" effect="dark">
            <el-icon><StarFilled /></el-icon> 高重要性
          </el-tag>
          <el-tag v-if="detailItem.status === 'draft'" type="info">草稿</el-tag>
        </div>
        <div v-if="detailItem.summary" class="detail-section">
          <div class="detail-label">摘要</div>
          <div class="detail-text detail-summary">{{ detailItem.summary }}</div>
        </div>
        <div class="detail-section">
          <div class="detail-label">内容</div>
          <div class="detail-text detail-body">{{ detailItem.content || '暂无内容' }}</div>
        </div>
        <div v-if="detailItem.tags" class="detail-section">
          <div class="detail-label">标签</div>
          <div class="detail-tags">
            <el-tag v-for="t in parseTags(detailItem.tags)" :key="t" size="small" effect="plain">{{ t }}</el-tag>
          </div>
        </div>
        <div class="detail-section detail-info-grid">
          <div v-if="detailItem.source" class="info-item">
            <span class="info-label">来源</span>
            <span class="info-value">{{ detailItem.source }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">查看次数</span>
            <span class="info-value">{{ detailItem.view_count || 0 }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">创建时间</span>
            <span class="info-value">{{ formatTimeFull(detailItem.create_time) }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">更新时间</span>
            <span class="info-value">{{ formatTimeFull(detailItem.update_time) }}</span>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="detailDrawer = false">关闭</el-button>
        <el-button type="primary" :icon="Edit" @click="openEdit(detailItem); detailDrawer = false">编辑</el-button>
      </template>
    </el-drawer>

    <!-- 批量导入弹窗 -->
    <el-dialog v-model="batchDialog" title="批量导入知识点" width="680px">
      <!-- AI 转换助手：让其它 AI 把素材整理成系统支持的 JSON -->
      <div class="ai-extract-box">
        <div class="ai-extract-head" @click="extractOpen = !extractOpen">
          <el-icon class="ae-icon"><MagicStick /></el-icon>
          <span class="ae-title">有现成素材想快速导入？让 AI 帮你整理成系统 JSON</span>
          <el-icon class="ae-chevron" :class="{ 'is-open': extractOpen }"><ArrowDown /></el-icon>
        </div>
        <div v-show="extractOpen" class="ai-extract-body">
          <p class="ae-tip">把你的原始素材（散落笔记、产品文档、对话记录、网页摘录等）粘贴到下方，点「一键复制转换提示词」后发给 ChatGPT / Claude / 通义 / DeepSeek 等任意 AI，它会返回标准 JSON 数组，直接粘到本弹窗的「JSON模式」即可导入。</p>
          <el-input v-model="extractInput" type="textarea" :rows="6" placeholder="在此粘贴你的原始素材（可选）…" />
          <div class="ae-foot">
            <el-button type="primary" :icon="CopyDocument" @click="copyExtractPrompt">一键复制转换提示词</el-button>
            <span class="ae-hint">复制后发给任意 AI，把返回的 JSON 粘到下方「JSON模式」</span>
          </div>
        </div>
      </div>

      <el-form :model="batchForm" label-width="80px">
        <el-form-item label="目标分类">
          <el-select v-model="batchForm.category_id" clearable placeholder="选择分类（可选）" style="width: 100%;">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="导入模式">
          <el-radio-group v-model="batchForm.mode">
            <el-radio value="text">文本模式</el-radio>
            <el-radio value="json">JSON模式</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="内容">
          <el-input
            v-model="batchForm.data"
            type="textarea"
            :rows="10"
            :placeholder="batchForm.mode === 'text' ? '每行一个知识点，格式：标题:内容 或 标题|内容\n也可用三段式：标题|摘要|内容' : 'JSON数组格式：[{&quot;title&quot;:&quot;标题&quot;,&quot;content&quot;:&quot;内容&quot;,&quot;tags&quot;:&quot;标签&quot;,&quot;summary&quot;:&quot;摘要&quot;}]'"
          />
        </el-form-item>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
          <template #title>
            <span v-if="batchForm.mode === 'text'">文本模式：每行一条，用冒号(:)或竖线(|)分隔。支持「标题|摘要|内容」三段式</span>
            <span v-else>JSON模式：粘贴JSON数组，每条支持 title/content/summary/tags/source/importance 字段</span>
          </template>
        </el-alert>
      </el-form>
      <template #footer>
        <el-button @click="batchDialog = false">取消</el-button>
        <el-button type="primary" @click="saveBatch" :loading="batchSaving">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
const pageActionsTarget = inject('pageActionsTarget', null)
const route = useRoute()
const focusId = computed(() => route.query.focus)
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFocusScroll } from '../composables/useFocusScroll'
import {
  Plus, Edit, Delete, Search, Files, Folder, Collection, Upload, Download,
  Grid, List, StarFilled, View, Link, DataAnalysis,
  MagicStick, Document, Reading, Notebook, Box, ChatDotRound, Flag,
  CopyDocument, ArrowDown, Operation, Rank
} from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { knowledgeApi } from '../api'
import EmptyState from '../components/EmptyState.vue'
import BackgroundLibrary from '../components/knowledge/BackgroundLibrary.vue'

const iconMap = {
  Folder, MagicStick, Document, Reading, Notebook, Box, ChatDotRound, Flag, Files
}
const iconOptions = ['Folder', 'MagicStick', 'Document', 'Reading', 'Notebook', 'Box', 'ChatDotRound', 'Flag']
const colorOptions = ['#6366f1', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#8b5cf6', '#64748b']

const store = useAppStore()
const kbTab = ref('items')
const loading = ref(false)
const saving = ref(false)
const seeding = ref(false)
const categories = ref([])
const items = ref([])
const activeCategory = ref(null)
const search = ref('')
const viewMode = ref('grid')
const activeTags = ref([])
const showStats = ref(false)
const stats = ref(null)

const dialogVisible = ref(false)
const editing = ref(false)
const form = ref({ title: '', content: '', category_id: null, tags: '', summary: '', source: '', importance: 'normal', status: 'published' })
const categoryDialog = ref(false)
const editingCategory = ref(false)
const categoryForm = ref({ name: '', icon: 'Folder', color: '#6366f1', description: '' })

const detailDrawer = ref(false)
const detailItem = ref(null)

const totalCount = computed(() => items.value.length)
const highCount = computed(() => items.value.filter(i => i.importance === 'high').length)
const publishedCount = computed(() => items.value.filter(i => i.status === 'published').length)

const allTags = computed(() => {
  const set = new Set()
  items.value.forEach(it => {
    parseTags(it.tags).forEach(t => set.add(t))
  })
  return Array.from(set).slice(0, 20)
})

const filteredList = computed(() => {
  const base = items.value.filter(item => {
    const matchCat = !activeCategory.value || item.category_id === activeCategory.value
    const kw = search.value.toLowerCase()
    const matchSearch = !kw ||
      (item.title || '').toLowerCase().includes(kw) ||
      (item.content || '').toLowerCase().includes(kw) ||
      (item.summary || '').toLowerCase().includes(kw) ||
      (item.tags || '').toLowerCase().includes(kw)
    const matchTag = activeTags.value.length === 0 || parseTags(item.tags).some(t => activeTags.value.includes(t))
    return matchCat && matchSearch && matchTag
  })
  return sortItems(base)
})

// 知识点列表排序（默认 / 重要度 / 更新时间 / 名称 / 来源）+ 升降序
const sortBy = ref('default') // default/importance/update_time/title/source
const sortDir = ref('desc') // asc / desc（默认排序时不生效）
function toggleSortDir() {
  sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
}
function sortItems(list) {
  const arr = [...list]
  if (sortBy.value === 'custom') return arr // 自定义：保持拖拽后的顺序
  const dir = sortDir.value === 'asc' ? 1 : -1
  if (sortBy.value === 'importance') {
    const w = { high: 3, normal: 2, low: 1 }
    arr.sort((a, b) => ((w[b.importance] || 1) - (w[a.importance] || 1)) * dir)
  } else if (sortBy.value === 'update_time') {
    arr.sort((a, b) => (new Date(b.update_time || 0) - new Date(a.update_time || 0)) * dir)
  } else if (sortBy.value === 'title') {
    arr.sort((a, b) => (a.title || '').localeCompare(b.title || '', 'zh-CN') * dir)
  } else if (sortBy.value === 'source') {
    arr.sort((a, b) => {
      const sa = (a.source || '').trim()
      const sb = (b.source || '').trim()
      if (!sa && !sb) return 0
      if (!sa) return 1 // 无来源排最后（不受升降序影响）
      if (!sb) return -1
      return sa.localeCompare(sb, 'zh-CN') * dir
    })
  }
  return arr
}

// ========== 自定义拖拽排序 ==========
const dragItemId = ref(null)
function onItemDragStart(item, e) {
  dragItemId.value = item.id
  if (e.dataTransfer) { e.dataTransfer.effectAllowed = 'move' }
}
function onItemDragOver(e) { e.dataTransfer.dropEffect = 'move' }
async function onItemDrop(target) {
  const from = dragItemId.value
  dragItemId.value = null
  if (from == null || from === target.id) return
  const arr = [...items.value]
  const fromIdx = arr.findIndex(it => it.id === from)
  const toIdx = arr.findIndex(it => it.id === target.id)
  if (fromIdx < 0 || toIdx < 0) return
  const [moved] = arr.splice(fromIdx, 1)
  arr.splice(toIdx, 0, moved)
  items.value = arr
  try {
    await knowledgeApi.sortItems(arr.map((it, i) => ({ id: it.id, sort: i })))
    ElMessage.success('顺序已更新')
  } catch (err) {
    ElMessage.error('排序失败')
    await loadItems()
  }
}

// ========== 批量操作 ==========
const batchMode = ref(false)
const selectedItems = ref([])
const batchTargetCategory = ref(null)
const batchTargetImportance = ref(null)
const batchSubmitting = ref(false)
function toggleItemSelect(item) {
  const i = selectedItems.value.indexOf(item.id)
  if (i >= 0) selectedItems.value.splice(i, 1)
  else selectedItems.value.push(item.id)
}
function clearItemSelection() {
  selectedItems.value = []
  batchTargetCategory.value = null
  batchTargetImportance.value = null
}
async function onBatchMoveCategory(val) {
  if (val == null) return
  const ids = selectedItems.value
  if (!ids.length) return
  batchSubmitting.value = true
  try {
    await knowledgeApi.batchMoveItems({ ids, category_id: val })
    ElMessage.success(`已移动 ${ids.length} 个知识点`)
    batchTargetCategory.value = null
    await loadItems()
    clearItemSelection()
  } finally { batchSubmitting.value = false }
}
async function onBatchSetImportance(val) {
  if (val == null) return
  const ids = selectedItems.value
  if (!ids.length) return
  batchSubmitting.value = true
  try {
    await knowledgeApi.batchStatusItems({ ids, field: 'importance', value: val })
    ElMessage.success(`已设置 ${ids.length} 个知识点的重要度`)
    batchTargetImportance.value = null
    await loadItems()
    clearItemSelection()
  } finally { batchSubmitting.value = false }
}
async function onBatchDeleteItems() {
  const ids = selectedItems.value
  if (!ids.length) return
  await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 个知识点吗？`, '批量删除', { type: 'warning' })
  batchSubmitting.value = true
  try {
    await knowledgeApi.batchDeleteItems({ ids })
    ElMessage.success(`已删除 ${ids.length} 个知识点`)
    await loadItems()
    clearItemSelection()
  } finally { batchSubmitting.value = false }
}

function parseTags(tags) {
  if (!tags) return []
  return String(tags).split(/[,，、\s]+/).filter(Boolean)
}

function toggleTag(tag) {
  const idx = activeTags.value.indexOf(tag)
  if (idx >= 0) activeTags.value.splice(idx, 1)
  else activeTags.value.push(tag)
}

function getCategoryName(id) {
  return categories.value.find(c => c.id === id)?.name || '未分类'
}
function getCategoryColor(id) {
  return categories.value.find(c => c.id === id)?.color || '#94a3b8'
}
function formatTime(t) {
  if (!t) return '—'
  return new Date(t).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit' })
}
function formatTimeFull(t) {
  if (!t) return '—'
  return new Date(t).toLocaleString('zh-CN')
}

async function loadCategories() {
  if (!store.currentIndustryId) return
  const res = await knowledgeApi.listCategories(store.currentIndustryId)
  categories.value = res.data || []
}

async function loadItems() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const res = await knowledgeApi.listItems(store.currentIndustryId, '', '')
    items.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  if (!store.currentIndustryId) return
  try {
    const res = await knowledgeApi.stats(store.currentIndustryId)
    stats.value = res.data
  } catch {}
}

function openCategoryCreate() {
  editingCategory.value = false
  categoryForm.value = { name: '', icon: 'Folder', color: '#6366f1', description: '', industry_id: store.currentIndustryId }
  categoryDialog.value = true
}

function openCategoryEdit(c) {
  editingCategory.value = true
  categoryForm.value = { ...c, industry_id: store.currentIndustryId }
  categoryDialog.value = true
}

async function saveCategory() {
  if (!categoryForm.value.name?.trim()) { ElMessage.warning('请输入分类名称'); return }
  saving.value = true
  try {
    if (editingCategory.value) {
      await knowledgeApi.updateCategory(categoryForm.value.id, categoryForm.value)
      ElMessage.success('更新成功')
    } else {
      await knowledgeApi.createCategory(categoryForm.value)
      ElMessage.success('创建成功')
    }
    categoryDialog.value = false
    await loadCategories()
  } finally {
    saving.value = false
  }
}

async function removeCategory(c) {
  const tip = c.item_count > 0
    ? `确定删除分类「${c.name}」吗？该分类下的 ${c.item_count} 条知识点将变为「未分类」。`
    : `确定删除分类「${c.name}」吗？`
  await ElMessageBox.confirm(tip, '删除分类', { type: 'warning' })
  try {
    await knowledgeApi.deleteCategory(c.id)
    ElMessage.success('分类已删除')
    if (activeCategory.value === c.id) activeCategory.value = null
    await loadCategories()
    if (showStats.value) await loadStats()
  } catch {}
}

function openCreate() {
  editing.value = false
  form.value = {
    title: '', content: '', category_id: activeCategory.value, tags: '',
    summary: '', source: '', importance: 'normal', status: 'published',
    industry_id: store.currentIndustryId
  }
  dialogVisible.value = true
}

function openEdit(item) {
  editing.value = true
  form.value = { ...item }
  dialogVisible.value = true
}

async function openDetail(item) {
  detailItem.value = item
  detailDrawer.value = true
  try {
    const res = await knowledgeApi.getItem(item.id)
    detailItem.value = res.data
    // 更新列表中的查看次数
    const idx = items.value.findIndex(i => i.id === item.id)
    if (idx >= 0) items.value[idx].view_count = res.data.view_count
  } catch {}
}

async function save() {
  if (!form.value.title?.trim()) { ElMessage.warning('请输入标题'); return }
  saving.value = true
  try {
    if (editing.value) {
      await knowledgeApi.updateItem(form.value.id, form.value)
    } else {
      await knowledgeApi.createItem(form.value)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await loadItems()
    await loadCategories()
    if (showStats.value) await loadStats()
  } finally {
    saving.value = false
  }
}

async function remove(item) {
  await ElMessageBox.confirm(`确定删除知识点「${item.title}」吗？`, '提示', { type: 'warning' })
  await knowledgeApi.deleteItem(item.id)
  ElMessage.success('删除成功')
  await loadItems()
  await loadCategories()
  if (showStats.value) await loadStats()
}

async function handleExport(fmt) {
  try {
    const res = await knowledgeApi.exportItems(store.currentIndustryId, fmt, activeCategory.value)
    const blob = new Blob([res], { type: fmt === 'json' ? 'application/json' : 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `knowledge_items.${fmt}`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

watch(() => store.currentIndustryId, async () => {
  activeCategory.value = null
  activeTags.value = []
  await loadCategories()
  await loadItems()
  if (showStats.value) await loadStats()
})

onMounted(async () => {
  await loadCategories()
  await loadItems()
})
// 全局搜索跳转：滚动并高亮定位到具体知识点
useFocusScroll()

// ===== 批量导入 =====
const batchDialog = ref(false)
const batchSaving = ref(false)
const batchForm = ref({ category_id: null, mode: 'text', data: '' })

// AI 转换助手：让其它 AI 把素材整理成系统支持的 JSON
const extractOpen = ref(false)
const extractInput = ref('')

function buildExtractPrompt() {
  const head = `你是「多行业提示词矩阵管理系统」的知识库整理助手。请把我提供的内容提取、归纳，转换为「知识库批量导入」所需的 JSON 数组，每个独立知识点作为数组中的一项。

【字段说明】
- title（必填）：知识点标题，简洁准确，能概括核心内容
- content（必填）：知识点详细内容，保留关键事实、数据、步骤、要点
- summary（可选）：一句话概括该知识点
- tags（可选）：用逗号分隔的标签，如 "敏感肌,防晒,护理"
- source（可选）：来源，如 "官网/产品手册/会议记录"
- importance（可选）：high / normal / low，默认 normal

【输出要求】
1. 只输出一个 JSON 数组，不要输出任何解释、前言、后缀，也不要用 markdown 代码块围栏包裹。
2. 严格使用上述英文字段名（小写），不要自造字段，也不要写成中文键。
3. 把内容拆成尽量独立、不重复的知识点；同一主题过长可拆多条。
4. 若原文零散难以拆分，至少保留一条完整记录，把原文整体放入 content。`
  const raw = extractInput.value.trim()
  const tail = raw
    ? `\n\n【待整理的内容】\n${raw}\n\n请直接输出 JSON 数组：`
    : `\n\n【待整理的内容】\n（请将你的原始素材粘贴在此处，我会立即为你转换为 JSON）\n\n请直接输出 JSON 数组：`
  return head + tail
}

async function copyExtractPrompt() {
  try {
    await navigator.clipboard.writeText(buildExtractPrompt())
    ElMessage.success('转换提示词已复制，发给其它 AI 即可得到 JSON')
  } catch {
    ElMessage.error('复制失败')
  }
}

function openBatchImport() {
  batchForm.value = { category_id: activeCategory.value, mode: 'text', data: '' }
  extractInput.value = ''
  batchDialog.value = true
}

async function seedDefaults() {
  try {
    await ElMessageBox.confirm(
      '将为「可引用论据库」灌入 GEO 默认论据模板（claim+evidence+source 示例，按标题去重，已有则跳过）。灌入后请把示例替换为贵司真实数据。',
      '一键灌入默认论据',
      { type: 'info' },
    )
  } catch {
    return
  }
  seeding.value = true
  try {
    const res = await knowledgeApi.seedDefaults(store.currentIndustryId)
    ElMessage.success(res.data.msg || '灌入完成')
    await loadData()
  } catch (e) {
    ElMessage.error('灌入失败：' + (e?.response?.data?.detail || '请重试'))
  } finally {
    seeding.value = false
  }
}

async function saveBatch() {
  if (!batchForm.value.data.trim()) {
    ElMessage.warning('请输入导入内容')
    return
  }
  batchSaving.value = true
  try {
    let payload = {
      industry_id: store.currentIndustryId,
      category_id: batchForm.value.category_id,
      mode: batchForm.value.mode,
      data: batchForm.value.data,
    }
    if (batchForm.value.mode === 'json') {
      try {
        payload.data = JSON.parse(batchForm.value.data)
      } catch {
        ElMessage.error('JSON格式错误，请检查')
        batchSaving.value = false
        return
      }
    }
    const res = await knowledgeApi.batchImport(payload)
    ElMessage.success(res.data.msg)
    batchDialog.value = false
    await loadItems()
    await loadCategories()
    if (showStats.value) await loadStats()
  } catch (e) {
    ElMessage.error('导入失败')
  } finally {
    batchSaving.value = false
  }
}

// ===== 内联创建分类 =====
async function inlineCreateCategory() {
  try {
    const { value } = await ElMessageBox.prompt('请输入分类名称', '新建分类', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
    })
    if (!value || !value.trim()) return
    const res = await knowledgeApi.quickCreateCategory({
      industry_id: store.currentIndustryId,
      name: value.trim(),
    })
    ElMessage.success('分类创建成功')
    await loadCategories()
    form.value.category_id = res.data.data.id
  } catch {
    // 用户取消
  }
}

watch(showStats, async (v) => {
  if (v && !stats.value) await loadStats()
})
</script>

<style scoped>
.knowledge-view { display: flex; flex-direction: column; gap: 16px; }

/* ===== hero ===== */
.hero {
  display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
  background: linear-gradient(135deg, rgba(99,102,241,0.10), rgba(20,184,166,0.07));
  border: 1px solid var(--border-light); border-left: 4px solid #6366f1;
  border-radius: var(--radius-lg); padding: 18px 22px;
}
.hero__lead { flex: 1; min-width: 320px; display: flex; flex-direction: column; gap: 6px; }
.hero__eyebrow { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; color: #6366f1; letter-spacing: 0.03em; }
.hero__eyebrow .el-icon { font-size: 15px; }
.hero__title { margin: 0; font-size: 17px; font-weight: 700; color: var(--text-primary); line-height: 1.4; }
.hero__desc { margin: 0; font-size: 12.5px; color: var(--text-tertiary); line-height: 1.6; max-width: 720px; }
.hero__metrics { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.metric { min-width: 76px; text-align: center; padding: 8px 12px; background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-md); }
.metric__num { font-size: 20px; font-weight: 700; color: var(--text-primary); line-height: 1.1; }
.metric__label { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
.metric--cat .metric__num { color: var(--brand-600, #6366f1); }
.metric--ok .metric__num { color: #f59e0b; }
.metric--pub .metric__num { color: var(--accent-emerald, #10b981); }

@media (max-width: 768px) {
  .hero { flex-direction: column; align-items: flex-start; }
  .hero__metrics { width: 100%; }
}

.stats-bar {
  display: flex; gap: 24px; padding: 16px 24px;
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-sm);
}
.stat-item { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.stat-num { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.stat-label { font-size: 12px; color: var(--text-tertiary); }
.text-amber { color: #f59e0b; }
.text-green { color: #10b981; }
.text-gray { color: #94a3b8; }

.kw-layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 16px;
  align-items: start;
}
.category-panel, .item-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.category-panel { position: sticky; top: 16px; align-self: start; max-height: calc(100vh - 32px); }
.panel-head {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-light);
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px;
}
.head-left { display: flex; align-items: center; gap: 8px; }
.head-right { display: flex; align-items: center; gap: 8px; }
.k-sort { flex-shrink: 0; }
.panel-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.category-list { flex: 1; overflow-y: auto; padding: 8px; position: relative; }
.category-item {
  position: relative;
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  transition: background 0.22s ease, color 0.22s ease, transform 0.18s cubic-bezier(.34, 1.4, .64, 1);
}
/* 激活态左侧指示条（弹性出现动画） */
.category-item::before {
  content: '';
  position: absolute; left: 0; top: 50%;
  width: 3px; height: 56%;
  border-radius: 0 3px 3px 0;
  background: var(--brand-500);
  transform: translateY(-50%) scaleY(0);
  transform-origin: center;
  opacity: 0;
  transition: transform 0.26s cubic-bezier(.34, 1.56, .64, 1), opacity 0.2s ease;
}
.category-item:hover { background: var(--slate-50); transform: translateX(2px); }
.category-item.is-active {
  background: var(--brand-50); color: var(--brand-600); font-weight: 600;
  transform: translateX(2px);
}
.category-item.is-active::before { transform: translateY(-50%) scaleY(1); opacity: 1; }
.category-item span { flex: 1; }
.category-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.category-actions {
  display: none;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
}
.category-item:hover .category-actions { display: flex; }
.category-actions .el-button { padding: 2px 4px; margin-left: 2px; }

/* 分类增删 / 重排动画 */
.cat-list-enter-active, .cat-list-leave-active { transition: all 0.3s cubic-bezier(.34, 1.4, .64, 1); }
.cat-list-enter-from { opacity: 0; transform: translateX(-14px) scale(0.96); }
.cat-list-leave-to { opacity: 0; transform: translateX(14px) scale(0.96); }
.cat-list-leave-active { position: absolute; width: calc(100% - 16px); }
.cat-list-move { transition: transform 0.3s cubic-bezier(.34, 1.4, .64, 1); }

.tag-filter-bar {
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-light);
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.tag-filter-label { font-size: 12px; color: var(--text-tertiary); }
.tag-chip { cursor: pointer; }

.item-list { width: 100%; }
.item-list.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 12px;
  align-content: start;
}
.item-list.list { display: flex; flex-direction: column; gap: 10px; }

.item-card {
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--brand-400);
  border-radius: var(--radius-md);
  padding: 16px;
  transition: all 0.18s;
  cursor: pointer;
  display: flex; flex-direction: column;
  gap: 10px;
  background: var(--bg-card);
  position: relative;
}
.item-row {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--brand-400);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  cursor: pointer; transition: all 0.18s;
  position: relative;
}
.item-row:hover { border-color: var(--brand-300); box-shadow: 0 4px 12px rgba(99,102,241,.1); transform: translateY(-1px); }
.item-row.is-selected { border-color: var(--brand-400); box-shadow: 0 0 0 2px rgba(99,102,241,.18); }
.item-row.is-dragging { opacity: .4; }
.item-row__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.item-row__title-row { display: flex; align-items: center; gap: 6px; min-width: 0; }
.item-row__title { font-size: 14px; font-weight: 600; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-row__summary { font-size: 13px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-row__tags { display: flex; gap: 4px; flex-wrap: wrap; }
.item-row__meta { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-tertiary); flex-shrink: 0; }
.item-row__actions { display: flex; gap: 2px; flex-shrink: 0; }
.item-card.is-selected { border-color: var(--brand-400); box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.18); }
.item-card.is-dragging { opacity: 0.4; }
.item-card[draggable="true"] { cursor: grab; }
.item-drag {
  position: absolute; top: 10px; right: 10px;
  font-size: 15px; color: var(--text-tertiary); cursor: grab;
  opacity: 0; transition: opacity 0.15s;
}
.item-card:hover .item-drag { opacity: 1; }
.item-select { position: absolute; top: 10px; right: 10px; }
.batch-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 16px; margin-top: 12px;
  background: var(--brand-50); border: 1px solid var(--brand-200, #c7d2fe);
  border-radius: var(--radius-md);
}
.batch-count { font-size: 13px; color: var(--text-secondary); }
.batch-count b { color: var(--brand-600); }
.batch-label { font-size: 13px; color: var(--text-secondary); }
.item-card:hover {
  border-color: var(--brand-300);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.1);
  transform: translateY(-1px);
}
.item-card__top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.item-card__title-row { display: flex; align-items: center; gap: 4px; flex: 1; min-width: 0; }
.imp-high { color: #f59e0b; flex-shrink: 0; }
.item-card__title {
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.item-card__badges { display: flex; gap: 4px; flex-shrink: 0; }
.item-card__summary {
  font-size: 13px; color: var(--text-secondary); line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  margin: 0; min-height: 0;
}
.item-card__tags { display: flex; gap: 4px; flex-wrap: wrap; margin: 0; }
.kw-tag { max-width: 140px; overflow: hidden; text-overflow: ellipsis; }
.item-card__footer {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding-top: 0; border-top: 1px dashed var(--border-light);
}
.item-card__meta { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-tertiary); overflow: hidden; }
.meta-item { display: flex; align-items: center; gap: 2px; white-space: nowrap; }
.item-card__actions { display: flex; gap: 2px; flex-shrink: 0; }

/* 详情抽屉 */
.detail-content { padding: 0 4px; }
.detail-meta { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
.detail-section { margin-bottom: 20px; }
.detail-label { font-size: 12px; color: var(--text-tertiary); margin-bottom: 8px; font-weight: 600; }
.detail-text { font-size: 14px; color: var(--text-primary); line-height: 1.8; }
.detail-summary { color: var(--text-secondary); font-style: italic; padding: 10px 12px; background: var(--slate-50); border-radius: var(--radius-md); border-left: 3px solid var(--brand-400); }
.detail-body { white-space: pre-wrap; word-break: break-word; }
.detail-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.detail-info-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
  padding: 12px; background: var(--slate-50); border-radius: var(--radius-md);
}
.info-item { display: flex; flex-direction: column; gap: 2px; }
.info-label { font-size: 11px; color: var(--text-tertiary); }
.info-value { font-size: 13px; color: var(--text-primary); }

/* 分类弹窗 */
.color-picker-row { display: flex; gap: 8px; flex-wrap: wrap; }
.color-dot {
  width: 28px; height: 28px; border-radius: 50%; cursor: pointer;
  border: 2px solid transparent; transition: all 0.16s;
}
.color-dot:hover { transform: scale(1.1); }
.color-dot.active { border-color: var(--text-primary); box-shadow: 0 0 0 2px var(--bg-card), 0 0 0 4px var(--brand-400); }

.slide-down-enter-active, .slide-down-leave-active { transition: all 0.3s ease; }
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; transform: translateY(-10px); }

/* AI 转换助手（批量导入弹窗内） */
.ai-extract-box {
  background: linear-gradient(135deg, var(--brand-50), var(--slate-50));
  border: 1px solid var(--brand-200);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  overflow: hidden;
}
.ai-extract-head {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; cursor: pointer; user-select: none;
  transition: background 0.15s;
}
.ai-extract-head:hover { background: var(--brand-100); }
.ae-icon { color: var(--brand-500); font-size: 16px; }
.ae-title { flex: 1; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.ae-chevron { color: var(--text-tertiary); transition: transform 0.2s; }
.ae-chevron.is-open { transform: rotate(180deg); }
.ai-extract-body { padding: 0 14px 14px; }
.ae-tip { font-size: 12px; color: var(--text-secondary); line-height: 1.6; margin: 0 0 10px; }
.ae-foot { display: flex; align-items: center; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
.ae-hint { font-size: 11px; color: var(--text-tertiary); }

@media (max-width: 1024px) {
  .kw-layout { grid-template-columns: 1fr; }
  .item-list.grid { grid-template-columns: 1fr; }
}
</style>
