<template>
  <div class="keyword-view">
    <Teleport :to="pageActionsTarget" v-if="pageActionsTarget">
      <el-button :icon="Upload" @click="batchDialog = true">批量导入</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建关键词</el-button>
    </Teleport>

    <!-- 顶部：GEO 关键词/选题价值说明 + 指标 -->
    <section class="hero">
      <div class="hero__lead">
        <span class="hero__eyebrow"><el-icon><Key /></el-icon> GEO 作战 · 关键词与选题</span>
        <h2 class="hero__title">用关键词与选题，把「客户搜索意图」接进 GEO 内容生产</h2>
        <p class="hero__desc">关键词按分组管理、可批量导入；选题落进平台与账号矩阵。三者共同决定软文该打哪些词、发往哪里——是 GEO 命中搜索意图的抓手。</p>
      </div>
      <div class="hero__metrics">
        <div class="metric">
          <div class="metric__num">{{ keywords.length }}</div>
          <div class="metric__label">关键词</div>
        </div>
        <div class="metric metric--cat">
          <div class="metric__num">{{ groups.length }}</div>
          <div class="metric__label">分组</div>
        </div>
        <div class="metric metric--ok">
          <div class="metric__num">{{ topics.length }}</div>
          <div class="metric__label">选题</div>
        </div>
      </div>
    </section>

    <!-- 分段切换 -->
    <div class="section-tabs">
      <button class="section-tab" :class="{ active: activeTab === 'keyword' }" @click="activeTab = 'keyword'">
        <el-icon><Key /></el-icon> 关键词库
      </button>
      <button class="section-tab" :class="{ active: activeTab === 'topic' }" @click="activeTab = 'topic'">
        <el-icon><Tickets /></el-icon> 选题池
      </button>
      <button class="section-tab" :class="{ active: activeTab === 'matrix' }" @click="activeTab = 'matrix'">
        <el-icon><Grid /></el-icon> 矩阵视图
      </button>
    </div>

    <!-- 批量导入提示词板块：让其他 AI 帮你把任意格式关键词转成可导入格式 -->
    <div v-if="activeTab === 'keyword'" class="kw-import-prompt-banner">
      <div class="kip-head" @click="kipOpen = !kipOpen">
        <el-icon class="kip-icon"><MagicStick /></el-icon>
        <div class="kip-head-text">
          <span class="kip-title">批量导入提示词</span>
          <span class="kip-hint">把下面这段发给任意 AI（ChatGPT / Claude / 通义 / DeepSeek），它能把你手里各种格式的关键词转成本系统可直接批量导入的格式</span>
        </div>
        <el-icon class="kip-chevron" :class="{ 'is-open': kipOpen }"><ArrowDown /></el-icon>
      </div>
      <div v-show="kipOpen" class="kip-body">
        <el-input :model-value="KW_IMPORT_PROMPT" type="textarea" :rows="14" readonly class="kip-textarea" />
        <div class="kip-foot">
          <el-button type="primary" :icon="CopyDocument" @click="copyKwImportPrompt">一键复制提示词</el-button>
          <el-button :icon="Upload" @click="batchDialog = true">打开批量导入</el-button>
          <span class="kip-tip">复制后粘贴给 AI，把转换结果粘到批量导入框即可</span>
        </div>
      </div>
    </div>

    <!-- 关键词库（分组 + 排序 + 搜索） -->
    <div v-show="activeTab === 'keyword'" class="kw-layout">
      <!-- 左侧分组 -->
      <div class="group-panel">
        <div class="panel-head">
          <span class="panel-title">分组</span>
          <el-button size="small" type="primary" link :icon="Plus" @click="openGroupCreate">新建分组</el-button>
        </div>
        <transition-group name="cat-list" tag="div" class="group-list">
          <div class="group-item" key="__all__" :class="{ 'is-active': activeGroup === null }" @click="activeGroup = null">
            <el-icon><Collection /></el-icon>
            <span>全部</span>
            <el-tag size="small" round>{{ totalCount }}</el-tag>
          </div>
          <div
            v-for="g in groups"
            :key="g.id"
            class="group-item"
            :class="{ 'is-active': activeGroup === g.id }"
            draggable="true"
            @click="activeGroup = g.id"
            @dragstart="onGroupDragStart(g, $event)"
            @dragover.prevent="onGroupDragOver($event)"
            @drop="onGroupDrop(g)"
          >
            <el-icon class="group-drag" title="拖拽排序"><Rank /></el-icon>
            <el-icon class="group-icon" :style="{ color: g.color || '#6366f1' }"><component :is="groupIconOf(g)" /></el-icon>
            <span class="group-name">{{ g.name }}</span>
            <el-tag size="small" round>{{ g.item_count }}</el-tag>
            <div class="group-actions" @click.stop>
              <el-button text size="small" :icon="Edit" title="编辑分组" @click="openGroupEdit(g)" />
              <el-button text size="small" type="danger" :icon="Delete" title="删除分组" @click="removeGroup(g)" />
            </div>
          </div>
          <div
            v-if="uncategorizedCount > 0"
            class="group-item"
            key="__uncat__"
            :class="{ 'is-active': activeGroup === -1 }"
            @click="activeGroup = -1"
          >
            <el-icon class="group-icon" style="color:#94a3b8"><Document /></el-icon>
            <span class="group-name">未分组</span>
            <el-tag size="small" round>{{ uncategorizedCount }}</el-tag>
          </div>
        </transition-group>
      </div>

      <!-- 右侧关键词 -->
      <div class="item-panel" v-loading="loading">
        <div class="panel-head">
          <div class="head-left">
            <span class="panel-title">关键词列表</span>
            <el-tag size="small" type="info" round>{{ displayKeywords.length }}</el-tag>
          </div>
          <div class="head-right">
            <el-select v-model="kwSortBy" size="small" class="kw-sort" style="width: 128px">
              <el-option label="默认顺序" value="default" />
              <el-option label="按关键词" value="word" />
              <el-option label="按优先级" value="priority" />
              <el-option label="按类型" value="type" />
              <el-option label="按关联产品" value="related_product" />
            </el-select>
            <el-button size="small" :icon="kwSortDir === 'asc' ? SortUp : SortDown"
                       :disabled="kwSortBy === 'default'"
                       :title="kwSortDir === 'asc' ? '升序' : '降序'"
                       @click="kwSortDir = kwSortDir === 'asc' ? 'desc' : 'asc'">
              {{ kwSortDir === 'asc' ? '升序' : '降序' }}
            </el-button>
            <el-select v-model="filterType" placeholder="全部类型" clearable size="small" style="width: 124px;">
              <el-option label="核心品牌词" value="brand" />
              <el-option label="产品词" value="product" />
              <el-option label="长尾词" value="long_tail" />
              <el-option label="问题词" value="question" />
            </el-select>
          </div>
        </div>
        <div class="kw-toolbar">
          <el-input v-model="kwSearch" placeholder="查找关键词 / 关联产品 / 标签..." size="small" :prefix-icon="Search" clearable style="flex: 1;" />
          <el-button size="small" :icon="Operation" :type="batchMode ? 'primary' : 'default'" @click="batchMode = !batchMode">
            {{ batchMode ? '退出批量' : '批量管理' }}
          </el-button>
        </div>
        <!-- 关键词列表（窗口化虚拟滚动） -->
        <div class="vtable" :class="{ batch: batchMode }">
          <div class="kw-grid vtable__head">
            <div class="kw-cell sel">
              <el-checkbox v-if="batchMode" :model-value="kwSelection.length === displayKeywords.length && displayKeywords.length > 0" @change="toggleKwSelectAll" />
            </div>
            <div class="kw-cell">关键词</div>
            <div class="kw-cell">分组</div>
            <div class="kw-cell">类型</div>
            <div class="kw-cell">优先级</div>
            <div class="kw-cell">关联产品</div>
            <div class="kw-cell">标签</div>
            <div class="kw-cell">操作</div>
          </div>
          <VirtualList
            class="vtable__body"
            :items="displayKeywords"
            :row-height="52"
            :gap="0"
            :focus-id="focusId"
            :get-key="(it) => it.id"
            #default="{ item, index }"
          >
            <div class="kw-grid kw-row" :class="[index % 2 === 1 ? 'striped' : '', 'focus-row-' + item.id]" :data-focus-id="item.id">
              <div class="kw-cell sel">
                <el-checkbox v-if="batchMode" :model-value="kwSelection.includes(item.id)" @change="() => toggleKwSelect(item)" />
              </div>
              <div class="kw-cell"><span class="kw-word">{{ item.word }}</span></div>
              <div class="kw-cell">
                <span v-if="groupNameOf(item.group_id)" class="kw-group-tag">
                  <span class="kw-group-dot" :style="{ background: groupColorOf(item.group_id) }"></span>{{ groupNameOf(item.group_id) }}
                </span>
                <span v-else class="kw-group-none">未分组</span>
              </div>
              <div class="kw-cell">
                <el-tag size="small" :type="typeColor(item.type)" effect="light">{{ typeLabel(item.type) }}</el-tag>
              </div>
              <div class="kw-cell">
                <el-rate :model-value="item.priority" disabled size="small" />
              </div>
              <div class="kw-cell kw-ellipsis">{{ item.related_product || '—' }}</div>
              <div class="kw-cell kw-ellipsis">{{ item.tags || '—' }}</div>
              <div class="kw-cell kw-actions">
                <el-button text size="small" :icon="Edit" @click="openEdit(item)">编辑</el-button>
                <el-button text size="small" type="danger" :icon="Delete" @click="remove(item)">删除</el-button>
              </div>
            </div>
          </VirtualList>
        </div>
        <!-- 批量操作条 -->
        <div v-if="batchMode && kwSelection.length" class="batch-bar">
          <span class="batch-count">已选 <b>{{ kwSelection.length }}</b> 个</span>
          <span class="batch-label">改分组：</span>
          <el-select v-model="batchTargetGroup" placeholder="选择分组" size="small" clearable style="width: 160px" @change="onBatchMoveGroup">
            <el-option label="未分组" :value="null" />
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
          <el-button size="small" type="danger" :icon="Delete" :loading="batchSubmitting" @click="onBatchDeleteKw">删除</el-button>
          <el-button size="small" @click="clearKwSelection">取消选择</el-button>
        </div>
        <EmptyState v-if="!loading && displayKeywords.length === 0" title="暂无关键词" size="small" icon="Key" />
      </div>
    </div>

    <!-- 选题池（卡片式，展示描述/关联关键词/平台账号/状态） -->
    <div v-show="activeTab === 'topic'" v-loading="loading">
      <div class="topic-toolbar">
        <span class="topic-toolbar__title">选题列表 <el-tag size="small" round type="info">{{ topics.length }}</el-tag></span>
        <el-input v-model="topicSearch" placeholder="搜索选题标题..." size="small" :prefix-icon="Search" clearable style="width: 240px;" />
        <el-button type="primary" size="small" :icon="Plus" @click="openTopicCreate">新建选题</el-button>
      </div>
      <div class="topic-card-grid" v-if="filteredTopics.length">
        <div v-for="t in filteredTopics" :key="t.id" class="topic-card" :data-focus-id="t.id">
          <div class="topic-card__head">
            <span class="topic-card__title">{{ t.title }}</span>
            <el-tag size="small" :type="t.status === 'done' ? 'success' : 'info'" effect="light">
              {{ { pending: '待处理', processing: '进行中', done: '已完成' }[t.status] || t.status }}
            </el-tag>
          </div>
          <div class="topic-card__desc" v-if="t.description">{{ t.description }}</div>
          <div class="topic-card__desc topic-card__desc--empty" v-else>暂无描述</div>
          <div class="topic-card__kws" v-if="topicKeywordNames(t.keyword_id_list).length">
            <span class="topic-card__kws-label"><el-icon><Key /></el-icon></span>
            <el-tag v-for="kn in topicKeywordNames(t.keyword_id_list).slice(0, 6)" :key="kn.id" size="small" effect="plain" class="topic-kw-tag">{{ kn.word }}</el-tag>
            <span v-if="topicKeywordNames(t.keyword_id_list).length > 6" class="topic-kw-more">+{{ topicKeywordNames(t.keyword_id_list).length - 6 }}</span>
          </div>
          <div class="topic-card__foot">
            <span class="topic-card__meta" v-if="getPlatformName(t.platform_id) !== '—'">
              <el-tag size="small" effect="dark">{{ getPlatformName(t.platform_id) }}</el-tag>
            </span>
            <span class="topic-card__meta">{{ getAccountName(t.account_id) }}</span>
            <span class="topic-card__meta topic-card__date">{{ t.plan_date || '未排期' }}</span>
            <div class="topic-card__actions">
              <el-button text size="small" :icon="Edit" @click="openTopicEdit(t)">编辑</el-button>
              <el-button text size="small" type="danger" :icon="Delete" @click="removeTopic(t)">删除</el-button>
            </div>
          </div>
        </div>
      </div>
      <EmptyState v-if="!loading && filteredTopics.length === 0" title="暂无选题" size="small" icon="Tickets" />
    </div>

    <!-- 矩阵视图 -->
    <div v-show="activeTab === 'matrix'" v-loading="loading">
      <div v-for="m in matrix" :key="m.platform.id" class="matrix-card">
        <div class="matrix-card__head">
          <el-tag size="small" effect="dark">{{ m.platform.name }}</el-tag>
          <span class="matrix-card__info">字数 {{ m.platform.word_count_min }}-{{ m.platform.word_count_max }}</span>
        </div>
        <div v-if="m.accounts.length === 0" style="padding: 20px; text-align: center; color: var(--text-tertiary); font-size: 13px;">暂无账号</div>
        <div v-for="acc in m.accounts" :key="acc.account.id" class="matrix-acc">
          <div class="matrix-acc__name">{{ acc.account.account_name }}</div>
          <div v-if="acc.topics.length === 0" style="font-size: 12px; color: var(--text-tertiary); padding: 4px 0;">暂无选题</div>
          <div v-for="t in acc.topics" :key="t.id" class="matrix-topic">
            <el-tag size="small" :type="t.status === 'done' ? 'success' : 'info'" effect="plain">{{ { pending: '待', processing: '中', done: '完' }[t.status] }}</el-tag>
            <span class="matrix-topic__title">{{ t.title }}</span>
            <span class="matrix-topic__date">{{ t.plan_date || '' }}</span>
          </div>
        </div>
      </div>
      <EmptyState v-if="!loading && matrix.length === 0" title="暂无矩阵数据" size="small" icon="Grid" />
    </div>

    <!-- 关键词弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑关键词' : '新建关键词'" width="480px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="关键词"><el-input v-model="form.word" /></el-form-item>
        <el-form-item label="分组">
          <el-select v-model="form.group_id" placeholder="未分组" clearable style="width: 100%;">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.type" style="width: 100%;">
            <el-option label="核心品牌词" value="brand" />
            <el-option label="产品词" value="product" />
            <el-option label="长尾词" value="long_tail" />
            <el-option label="问题词" value="question" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-rate v-model="form.priority" />
        </el-form-item>
        <el-form-item label="关联产品"><el-input v-model="form.related_product" /></el-form-item>
        <el-form-item label="标签"><el-input v-model="form.tags" placeholder="逗号分隔" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 关键词分组弹窗 -->
    <el-dialog v-model="groupDialog" :title="editingGroup ? '编辑分组' : '新建分组'" width="440px">
      <el-form :model="groupForm" label-width="72px">
        <el-form-item label="分组名称"><el-input v-model="groupForm.name" placeholder="如：品牌词 / 竞品词 / 618活动" /></el-form-item>
        <el-form-item label="主题色">
          <el-color-picker v-model="groupForm.color" />
          <el-input v-model="groupForm.color" style="width: 110px; margin-left: 10px;" />
        </el-form-item>
        <el-form-item label="图标">
          <el-select v-model="groupForm.icon" placeholder="选择图标" style="width: 100%;">
            <el-option v-for="ic in iconOptions" :key="ic" :label="ic" :value="ic">
              <el-icon style="vertical-align: middle;"><component :is="iconMap[ic]" v-if="iconMap[ic]" /></el-icon>
              <span style="margin-left: 8px;">{{ ic }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="groupForm.description" type="textarea" :rows="2" placeholder="可选" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="groupDialog = false">取消</el-button>
        <el-button type="primary" @click="saveGroup" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 选题弹窗 -->
    <el-dialog v-model="topicDialog" :title="editingTopic ? '编辑选题' : '新建选题'" width="560px">
      <el-form :model="topicForm" label-width="80px">
        <el-form-item label="选题标题"><el-input v-model="topicForm.title" /></el-form-item>
        <el-form-item label="选题描述">
          <el-input v-model="topicForm.description" type="textarea" :rows="2" placeholder="选题的核心角度/要打的关键词意图（可选）" />
        </el-form-item>
        <el-form-item label="关联关键词">
          <el-select v-model="topicSelectedKeywords" multiple filterable placeholder="选择该选题要打的关键词" style="width: 100%;">
            <el-option v-for="k in keywords" :key="k.id" :label="k.word + (k.related_product ? ` (${k.related_product})` : '')" :value="k.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="topicForm.platform_id" style="width: 100%;">
            <el-option v-for="p in platforms" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="账号">
          <el-select v-model="topicForm.account_id" style="width: 100%;">
            <el-option v-for="a in accounts" :key="a.id" :label="a.account_name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="计划日期"><el-input v-model="topicForm.plan_date" placeholder="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="topicForm.status" style="width: 100%;">
            <el-option label="待处理" value="pending" />
            <el-option label="进行中" value="processing" />
            <el-option label="已完成" value="done" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="topicDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTopic" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入关键词弹窗 -->
    <el-dialog v-model="batchDialog" title="批量导入关键词" width="640px" @closed="resetBatch">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        <template #title>支持三种方式</template>
        ① 每行一个关键词；② 逗号 / 制表符分隔字段：<b>词, 类型, 优先级, 关联产品, 标签</b>；③ 直接粘贴 JSON 数组。也可上传 .txt / .csv / .json 文件。
      </el-alert>
      <el-form label-width="88px">
        <el-form-item label="默认类型">
          <el-select v-model="batchType" style="width: 100%;">
            <el-option label="核心品牌词" value="brand" />
            <el-option label="产品词" value="product" />
            <el-option label="长尾词" value="long_tail" />
            <el-option label="问题词" value="question" />
          </el-select>
          <div class="form-hint">未单独指定类型的行将使用该类型</div>
        </el-form-item>
        <el-form-item label="导入到分组">
          <el-select v-model="batchGroupId" placeholder="不指定（导入到「未分组」）" clearable style="width: 100%;">
            <el-option v-for="g in groups" :key="g.id" :label="`${g.name}`" :value="g.id" />
          </el-select>
          <div class="form-hint">
            把这一批关键词导入到指定分组；也可在「数据」里用第 6 列写分组名（<b>词, 类型, 优先级, 产品, 标签, 分组名</b>），自动建组并归入。留空则进「未分组」。
          </div>
        </el-form-item>
        <el-form-item label="数据">
          <el-input
            v-model="batchText"
            type="textarea"
            :rows="10"
            placeholder="示例：&#10;人工智能写作&#10;AI软文, long_tail, 3, 智能写作助手, 教程&#10;SEO优化, long_tail, 2"
            @input="updateBatchPreview"
          />
        </el-form-item>
        <el-form-item label="或上传文件">
          <el-upload
            action="#"
            :auto-upload="false"
            :show-file-list="true"
            :on-change="handleBatchFile"
            :before-upload="() => false"
            accept=".txt,.csv,.json"
            style="width: 100%;"
          >
            <el-button :icon="Document">选择文件</el-button>
            <template #tip><div class="form-hint">支持 .txt（每行一词）/ .csv / .json 数组</div></template>
          </el-upload>
        </el-form-item>
        <el-form-item v-if="batchPreview.count > 0">
          <div class="batch-preview">
            待导入 <b>{{ batchPreview.count }}</b> 条
            <span v-if="batchPreview.sample.length" class="batch-preview-sample">
              （预览：{{ batchPreview.sample.join('、') }}{{ batchPreview.count > batchPreview.sample.length ? ' …' : '' }}）
            </span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button text @click="downloadKeywordTemplate">下载模板</el-button>
        <el-button @click="batchDialog = false">取消</el-button>
        <el-button type="primary" @click="doBatchImport" :loading="batchImporting" :disabled="batchPreview.count === 0">
          导入 {{ batchPreview.count || '' }} 条
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
const pageActionsTarget = inject('pageActionsTarget', null)
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFocusScroll } from '../composables/useFocusScroll'
import { Plus, Edit, Delete, Key, Tickets, Grid, Upload, Document, MagicStick, CopyDocument, ArrowDown, Collection, SortUp, SortDown, Search, Folder, Reading, Notebook, Box, ChatDotRound, Flag, Files, Operation, Rank } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { keywordApi, keywordGroupApi, topicApi, platformApi, accountApi } from '../api'
import EmptyState from '../components/EmptyState.vue'
import VirtualList from '../components/VirtualList.vue'

const store = useAppStore()
const route = useRoute()
const focusId = computed(() => route.query.focus)
const loading = ref(false)
const saving = ref(false)
const activeTab = ref('keyword')
const keywords = ref([])
const groups = ref([])
const activeGroup = ref(null) // null=全部, -1=未分组, 否则 group_id
// 分组图标（与知识库分类保持一致）
const iconMap = {
  Folder, MagicStick, Document, Reading, Notebook, Box, ChatDotRound, Flag, Collection, Files
}
const iconOptions = ['Folder', 'MagicStick', 'Document', 'Reading', 'Notebook', 'Box', 'ChatDotRound', 'Flag', 'Collection']
function groupIconOf(g) { return iconMap[g?.icon] || Folder }
const kwSearch = ref('')
const kwSortBy = ref('default') // default/word/priority/type/related_product
const kwSortDir = ref('asc') // asc/desc
const topics = ref([])
const matrix = ref([])
const platforms = ref([])
const accounts = ref([])
const filterType = ref('')

const dialogVisible = ref(false)
const editing = ref(false)
const form = ref({ word: '', group_id: null, type: 'long_tail', priority: 2, related_product: '', tags: '' })

// ========== 分组 ==========
const groupDialog = ref(false)
const editingGroup = ref(false)
const groupForm = ref({ name: '', color: '#6366f1', icon: 'Folder', description: '', industry_id: null })

const topicDialog = ref(false)
const editingTopic = ref(false)
const topicForm = ref({ title: '', platform_id: null, account_id: null, plan_date: '', status: 'pending', description: '', keyword_id_list: '', industry_id: null })
const topicSearch = ref('')
const topicSelectedKeywords = ref([])

const filteredTopics = computed(() => {
  const q = (topicSearch.value || '').trim().toLowerCase()
  if (!q) return topics.value
  return topics.value.filter(t => (t.title || '').toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q))
})

function topicKeywordNames(idListStr) {
  if (!idListStr) return []
  const ids = String(idListStr).split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n) && n > 0)
  return ids.map(id => keywords.value.find(k => k.id === id)).filter(Boolean)
}

// 分组计数与查找
const totalCount = computed(() => keywords.value.length)
const uncategorizedCount = computed(() => keywords.value.filter(k => k.group_id == null).length)
function groupById(id) { return groups.value.find(g => g.id === id) }
function groupNameOf(id) { return groupById(id)?.name || '' }
function groupColorOf(id) { return groupById(id)?.color || '#6366f1' }

// ========== 分组拖拽排序 ==========
const dragGroupId = ref(null)
function onGroupDragStart(g, e) {
  dragGroupId.value = g.id
  if (e.dataTransfer) { e.dataTransfer.effectAllowed = 'move' }
}
function onGroupDragOver(e) { e.dataTransfer.dropEffect = 'move' }
async function onGroupDrop(target) {
  const from = dragGroupId.value
  dragGroupId.value = null
  if (from == null || from === target.id) return
  const fromIdx = groups.value.findIndex(g => g.id === from)
  const toIdx = groups.value.findIndex(g => g.id === target.id)
  if (fromIdx < 0 || toIdx < 0) return
  const arr = [...groups.value]
  const [moved] = arr.splice(fromIdx, 1)
  arr.splice(toIdx, 0, moved)
  groups.value = arr
  try {
    await keywordGroupApi.sort(arr.map((g, i) => ({ id: g.id, sort: i })))
    ElMessage.success('分组顺序已更新')
  } catch (err) {
    ElMessage.error('分组排序失败')
  }
}

// ========== 关键词批量操作 ==========
const batchMode = ref(false)
const kwSelection = ref([])
const batchTargetGroup = ref(null)
const batchSubmitting = ref(false)
function toggleKwSelect(item) {
  const i = kwSelection.value.indexOf(item.id)
  if (i >= 0) kwSelection.value.splice(i, 1)
  else kwSelection.value.push(item.id)
}
function toggleKwSelectAll(val) {
  kwSelection.value = val ? displayKeywords.value.map(k => k.id) : []
}
function clearKwSelection() {
  kwSelection.value = []
}
async function onBatchMoveGroup(val) {
  const ids = kwSelection.value
  if (!ids.length) return
  batchSubmitting.value = true
  try {
    await keywordApi.batchGroup({ ids, group_id: val })
    ElMessage.success(`已将 ${ids.length} 个关键词移到「${val == null ? '未分组' : (groupNameOf(val) || '未分组')}」`)
    batchTargetGroup.value = null
    await loadAll()
    clearKwSelection()
  } finally { batchSubmitting.value = false }
}
async function onBatchDeleteKw() {
  const ids = kwSelection.value
  if (!ids.length) return
  await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 个关键词吗？`, '批量删除', { type: 'warning' })
  batchSubmitting.value = true
  try {
    await keywordApi.batchDelete({ ids })
    ElMessage.success(`已删除 ${ids.length} 个关键词`)
    clearKwSelection()
    await loadAll()
  } finally { batchSubmitting.value = false }
}

// 关键词列表：分组筛选 + 类型筛选 + 搜索 + 排序（升/降序）
const displayKeywords = computed(() => {
  let arr = keywords.value
  if (activeGroup.value === -1) {
    arr = arr.filter(k => k.group_id == null)
  } else if (activeGroup.value != null) {
    arr = arr.filter(k => k.group_id === activeGroup.value)
  }
  if (filterType.value) arr = arr.filter(k => k.type === filterType.value)
  const q = (kwSearch.value || '').trim().toLowerCase()
  if (q) {
    arr = arr.filter(k =>
      (k.word || '').toLowerCase().includes(q) ||
      (k.related_product || '').toLowerCase().includes(q) ||
      (k.tags || '').toLowerCase().includes(q)
    )
  }
  const by = kwSortBy.value
  const dir = kwSortDir.value === 'asc' ? 1 : -1
  if (by !== 'default') {
    arr = [...arr].sort((a, b) => {
      if (by === 'priority') return (a.priority - b.priority) * dir
      const va = (a[by] || '').toString()
      const vb = (b[by] || '').toString()
      return va.localeCompare(vb, 'zh-CN') * dir
    })
  }
  return arr
})

function typeLabel(t) { return { brand: '品牌词', product: '产品词', long_tail: '长尾词', question: '问题词' }[t] || t }
function typeColor(t) { return { brand: 'danger', product: 'warning', long_tail: 'info', question: 'success' }[t] || 'info' }
function getPlatformName(id) { return platforms.value.find(p => p.id === id)?.name || '—' }
function getAccountName(id) { return accounts.value.find(a => a.id === id)?.account_name || '—' }

async function loadAll() {
  if (!store.currentIndustryId) return
  loading.value = true
  try {
    const [k, g, t, p, a] = await Promise.all([
      keywordApi.list(store.currentIndustryId),
      keywordGroupApi.list(store.currentIndustryId),
      topicApi.list(store.currentIndustryId),
      platformApi.list(store.currentIndustryId),
      accountApi.list(store.currentIndustryId),
    ])
    keywords.value = k.data || []
    groups.value = g.data || []
    topics.value = t.data || []
    platforms.value = p.data || []
    accounts.value = a.data || []
  } finally {
    loading.value = false
  }
}

async function loadMatrix() {
  if (!store.currentIndustryId) return
  const res = await topicApi.matrix(store.currentIndustryId)
  matrix.value = res.data || []
}

function openCreate() {
  editing.value = false
  form.value = { word: '', group_id: activeGroup.value && activeGroup.value > 0 ? activeGroup.value : null, type: 'long_tail', priority: 2, related_product: '', tags: '', industry_id: store.currentIndustryId }
  dialogVisible.value = true
}
function openEdit(row) {
  editing.value = true
  form.value = { ...row }
  dialogVisible.value = true
}
async function save() {
  if (!form.value.word?.trim()) { ElMessage.warning('请输入关键词'); return }
  saving.value = true
  try {
    if (editing.value) {
      await keywordApi.update(form.value.id, form.value)
    } else {
      await keywordApi.create(form.value)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await loadAll()
  } finally {
    saving.value = false
  }
}
async function remove(row) {
  await ElMessageBox.confirm(`确定删除关键词「${row.word}」吗？`, '提示', { type: 'warning' })
  await keywordApi.delete(row.id)
  ElMessage.success('删除成功')
  await loadAll()
}

// ========== 分组管理 ==========
function openGroupCreate() {
  editingGroup.value = false
  groupForm.value = { name: '', color: '#6366f1', icon: 'Folder', description: '', industry_id: store.currentIndustryId }
  groupDialog.value = true
}
function openGroupEdit(g) {
  editingGroup.value = true
  groupForm.value = { ...g, industry_id: store.currentIndustryId }
  groupDialog.value = true
}
async function saveGroup() {
  if (!groupForm.value.name?.trim()) { ElMessage.warning('请输入分组名称'); return }
  saving.value = true
  try {
    if (editingGroup.value) {
      await keywordGroupApi.update(groupForm.value.id, groupForm.value)
      ElMessage.success('分组已更新')
    } else {
      await keywordGroupApi.create(groupForm.value)
      ElMessage.success('分组已创建')
    }
    groupDialog.value = false
    await loadAll()
  } finally {
    saving.value = false
  }
}
async function removeGroup(g) {
  const tip = g.item_count > 0
    ? `确定删除分组「${g.name}」吗？该分组下的 ${g.item_count} 个关键词将变为「未分组」。`
    : `确定删除分组「${g.name}」吗？`
  await ElMessageBox.confirm(tip, '删除分组', { type: 'warning' })
  await keywordGroupApi.delete(g.id)
  ElMessage.success('分组已删除')
  if (activeGroup.value === g.id) activeGroup.value = null
  await loadAll()
}

function openTopicCreate() {
  editingTopic.value = false
  topicForm.value = { title: '', platform_id: platforms.value[0]?.id, account_id: accounts.value[0]?.id, plan_date: '', status: 'pending', description: '', keyword_id_list: '', industry_id: store.currentIndustryId }
  topicSelectedKeywords.value = []
  topicDialog.value = true
}
function openTopicEdit(row) {
  editingTopic.value = true
  topicForm.value = { ...row, industry_id: store.currentIndustryId }
  const ids = String(row.keyword_id_list || '').split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n) && n > 0)
  topicSelectedKeywords.value = ids
  topicDialog.value = true
}
async function saveTopic() {
  if (!topicForm.value.title?.trim()) { ElMessage.warning('请输入选题标题'); return }
  topicForm.value.keyword_id_list = topicSelectedKeywords.value.join(',')
  saving.value = true
  try {
    if (editingTopic.value) {
      await topicApi.update(topicForm.value.id, topicForm.value)
    } else {
      await topicApi.create(topicForm.value)
    }
    ElMessage.success('保存成功')
    topicDialog.value = false
    await loadAll()
  } finally {
    saving.value = false
  }
}
async function removeTopic(row) {
  await ElMessageBox.confirm(`确定删除选题「${row.title}」吗？`, '提示', { type: 'warning' })
  await topicApi.delete(row.id)
  ElMessage.success('删除成功')
  await loadAll()
}

// ========== 批量导入关键词 ==========
const batchDialog = ref(false)
const batchType = ref('long_tail')
const batchGroupId = ref(null)   // 导入到指定分组
const batchText = ref('')
const batchImporting = ref(false)
const batchPreview = ref({ count: 0, sample: [] })
const VALID_BATCH_TYPES = ['brand', 'product', 'long_tail', 'question']

// 批量导入提示词板块：让其他 AI 把任意格式关键词转成可导入格式
const kipOpen = ref(false)
const KW_IMPORT_PROMPT = `你是一个关键词格式转换助手。我会给你一批关键词（可能是各种格式：逐行、逗号分隔、表格、带分类/优先级/产品/标签的混合文本等），请把它们转换成下面三种格式之一，方便我批量导入到关键词管理系统。

系统支持的批量导入格式（三选一，默认输出格式2）：
1. 简单格式：每行一个关键词
2. 字段格式：每行一条，用逗号分隔，字段顺序为：关键词, 类型, 优先级, 关联产品, 标签, 分组名
   - 类型取值：brand(核心品牌词) / product(产品词) / long_tail(长尾词) / question(问题词)
   - 优先级取值：1 / 2 / 3（3最高，默认2）
   - 关联产品、标签、分组名可选，没有则留空；分组名不存在会自动新建并归入
3. JSON 数组格式：[{"word":"关键词","type":"long_tail","priority":2,"related_product":"","tags":"","group_name":"品牌词"}]

要求：
- 识别每条关键词的合理类型（品牌名→brand，具体产品→product，长尾/泛词→long_tail，疑问句→question）
- 如有优先级信息则保留，否则默认 2
- 去除重复词、空行、无意义符号
- 默认输出"字段格式（格式2）"，除非我指定其他格式
- 只输出转换结果，不要额外解释

请等待我发送关键词后再转换。`
function copyKwImportPrompt() {
  navigator.clipboard.writeText(KW_IMPORT_PROMPT)
    .then(() => ElMessage.success('已复制提示词，粘贴给任意 AI 即可'))
    .catch(() => ElMessage.error('复制失败，请手动选择文本复制'))
}

function parseBatchInput(text) {
  if (!text || !text.trim()) return []
  const trimmed = text.trim()
  if (trimmed.startsWith('[')) {
    try {
      const arr = JSON.parse(trimmed)
      if (Array.isArray(arr)) {
        return arr.map(it => {
          if (typeof it === 'string') return { word: it.trim() }
          return {
            word: (it.word || '').trim(),
            type: it.type || '',
            priority: it.priority ?? 2,
            related_product: it.related_product || '',
            tags: it.tags || '',
          }
        }).filter(x => x.word)
      }
    } catch (e) { /* 非合法 JSON，继续按文本处理 */ }
  }
  const items = []
  for (const raw of trimmed.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    const sep = line.includes('\t') ? '\t' : (line.includes(',') ? ',' : null)
    if (sep) {
      const parts = line.split(sep).map(s => s.trim())
      const word = parts[0]
      if (!word) continue
      const type = parts[1] && VALID_BATCH_TYPES.includes(parts[1]) ? parts[1] : ''
      const priority = ['1', '2', '3'].includes(parts[2]) ? Number(parts[2]) : 2
      const group_name = (parts[5] || '').trim() || undefined
      items.push({ word, type, priority, related_product: parts[3] || '', tags: parts[4] || '', group_name })
    } else {
      items.push({ word: line, type: '', priority: 2, related_product: '', tags: '', group_name: undefined })
    }
  }
  return items
}

function updateBatchPreview() {
  const items = parseBatchInput(batchText.value)
  batchPreview.value = { count: items.length, sample: items.slice(0, 6).map(i => i.word) }
  return items
}

function handleBatchFile(file) {
  const f = file.raw || file
  if (!f) return
  const reader = new FileReader()
  reader.onload = (e) => {
    batchText.value = e.target.result || ''
    updateBatchPreview()
    ElMessage.info(`已读取文件：${file.name}`)
  }
  reader.readAsText(f)
}

async function doBatchImport() {
  const items = updateBatchPreview()
  if (items.length === 0) { ElMessage.warning('没有可导入的关键词'); return }
  batchImporting.value = true
  try {
    const res = await keywordApi.batchImport({
      industry_id: store.currentIndustryId,
      default_type: batchType.value,
      group_id: batchGroupId.value || undefined,
      items,
    })
    const d = res.data || {}
    if (d.errors && d.errors.length) console.warn('批量导入部分失败：', d.errors)
    ElMessage.success(d.msg || '导入完成')
    batchDialog.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error('导入失败：' + (e?.response?.data?.detail || '请检查数据格式'))
  } finally {
    batchImporting.value = false
  }
}

function downloadKeywordTemplate() {
  const sample = [
    { word: '人工智能写作', type: 'long_tail', priority: 3, related_product: '智能写作助手', tags: '教程' },
    { word: 'SEO优化技巧', type: 'long_tail', priority: 2, related_product: '', tags: '干货' },
  ]
  const blob = new Blob([JSON.stringify(sample, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'keyword_import_template.json'
  a.click()
  URL.revokeObjectURL(url)
}

function resetBatch() {
  batchText.value = ''
  batchGroupId.value = null
  batchPreview.value = { count: 0, sample: [] }
}

watch(() => store.currentIndustryId, loadAll)
watch(activeTab, (v) => { if (v === 'matrix') loadMatrix() })
// 全局搜索跳转：定位关键词时确保停留在「关键词库」分页
watch(() => route.query.focus, (f) => { if (f) activeTab.value = 'keyword' }, { immediate: true })
useFocusScroll()
onMounted(loadAll)
</script>

<style scoped>
.keyword-view { display: flex; flex-direction: column; gap: 16px; }

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
.metric--ok .metric__num { color: var(--accent-emerald, #10b981); }

@media (max-width: 768px) {
  .hero { flex-direction: column; align-items: flex-start; }
  .hero__metrics { width: 100%; }
}
.table-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  min-height: 300px;
  display: flex; flex-direction: column;
}
.table-head { padding: 14px 20px; border-bottom: 1px solid var(--border-light); display: flex; align-items: center; justify-content: space-between; }
.table-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }

/* 关键词 / 选题 窗口化虚拟滚动表格 */
.vtable { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.vtable__body { flex: 1; min-height: 0; }
.vtable__head {
  height: 44px; flex-shrink: 0;
  background: var(--bg-secondary, #f8fafc);
  border-bottom: 1px solid var(--border-light);
  font-size: 13px; font-weight: 600; color: var(--text-secondary);
}
.kw-grid {
  display: grid;
  grid-template-columns: 0 160px 130px 110px 100px minmax(140px, 1.2fr) minmax(140px, 1.2fr) 156px;
  align-items: center;
}
.kw-grid.batch {
  grid-template-columns: 48px 160px 130px 110px 100px minmax(140px, 1.2fr) minmax(140px, 1.2fr) 156px;
}
.topic-grid {
  display: grid;
  grid-template-columns: minmax(200px, 1.4fr) 120px 120px 120px 100px 156px;
  align-items: center;
}
.kw-row { height: 100%; border-bottom: 1px solid var(--border-light); }
.kw-row.striped { background: rgba(148, 163, 184, 0.08); }
.kw-row:hover { background: rgba(99, 102, 241, 0.06); }
.kw-cell { padding: 0 14px; font-size: 13px; color: var(--text-secondary); overflow: hidden; min-width: 0; }
.kw-cell.sel { display: flex; align-items: center; justify-content: center; overflow: hidden; }
.kw-cell.kw-actions { display: flex; gap: 2px; justify-content: flex-start; padding: 0 8px; }
.kw-actions .el-button { flex-shrink: 0; white-space: nowrap; }
.kw-actions .el-button:not(.el-button--danger):hover { color: var(--brand-600); background: var(--brand-50); }
.kw-actions .el-button--danger { color: #f56c6c; font-weight: 600; }
.kw-actions .el-button--danger:hover { color: #f56c6c; background: #fef2f2; }
.kw-word { font-weight: 600; color: var(--text-primary); display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kw-ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 关键词库：分组 + 列表布局 */
.kw-layout { display: grid; grid-template-columns: 232px 1fr; gap: 16px; min-height: 500px; }
.group-panel, .item-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.panel-head {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-light);
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px;
}
.head-left { display: flex; align-items: center; gap: 8px; }
.head-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.kw-sort { flex-shrink: 0; }
.panel-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.group-list { flex: 1; overflow-y: auto; padding: 8px; position: relative; }
.group-item {
  position: relative;
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.16s, transform 0.16s;
  font-size: 13px;
  color: var(--text-secondary);
}
.group-item::before {
  content: '';
  position: absolute; left: 0; top: 50%;
  width: 3px; height: 0;
  background: var(--brand-500, #6366f1);
  border-radius: 0 3px 3px 0;
  transform: translateY(-50%);
  transition: height 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.group-item:hover { background: var(--slate-50); transform: translateX(2px); }
.group-item.is-active { background: var(--brand-50); color: var(--brand-600); font-weight: 600; }
.group-item.is-active::before { height: 60%; }
.group-item span { flex: 1; }
.group-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.group-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.group-icon { font-size: 16px; flex-shrink: 0; }
.group-actions { display: none; align-items: center; gap: 0; flex-shrink: 0; }
.group-item:hover .group-actions { display: flex; }
.group-actions .el-button { padding: 2px 4px; margin-left: 2px; }
.group-drag { font-size: 14px; color: var(--text-tertiary); cursor: grab; opacity: 0; transition: opacity 0.15s; flex-shrink: 0; }
.group-item:hover .group-drag { opacity: 1; }
.group-item[draggable="true"] { cursor: grab; }
.group-item.dragging { opacity: 0.4; }
.batch-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 16px; margin-top: 10px;
  background: var(--brand-50); border: 1px solid var(--brand-200, #c7d2fe);
  border-radius: var(--radius-md);
}
.batch-count { font-size: 13px; color: var(--text-secondary); }
.batch-count b { color: var(--brand-600); }
.batch-label { font-size: 13px; color: var(--text-secondary); }
.kw-toolbar {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; border-bottom: 1px solid var(--border-light);
  flex-wrap: wrap;
}
.kw-group-tag { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-secondary); }
.kw-group-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.kw-group-none { font-size: 13px; color: var(--text-tertiary); }
/* 分组列表增删/重排动画 */
.cat-list-enter-active, .cat-list-leave-active { transition: all 0.25s ease; }
.cat-list-enter-from { opacity: 0; transform: translateX(-12px); }
.cat-list-leave-to { opacity: 0; transform: translateX(12px); }
.cat-list-move { transition: transform 0.25s ease; }
.cat-list-leave-active { position: absolute; width: calc(100% - 16px); }

@media (max-width: 1024px) {
  .kw-layout { grid-template-columns: 1fr; }
}

.matrix-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  margin-bottom: 12px;
  box-shadow: var(--shadow-sm);
}
.matrix-card__head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.matrix-card__info { font-size: 12px; color: var(--text-tertiary); }
.matrix-acc { padding: 8px 0; border-top: 1px dashed var(--border-light); }
.matrix-acc__name { font-weight: 600; font-size: 13px; margin-bottom: 4px; color: var(--text-primary); }
.matrix-topic {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}
.matrix-topic__title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-secondary); }
.matrix-topic__date { color: var(--text-tertiary); }

.form-hint { font-size: 12px; color: var(--text-tertiary); line-height: 1.5; margin-top: 2px; }
.batch-preview { font-size: 13px; color: var(--text-secondary); background: var(--bg-hover, #f5f7fa); padding: 8px 12px; border-radius: var(--radius-md, 8px); width: 100%; }
.batch-preview b { color: var(--brand-500, #6366f1); }
.batch-preview-sample { color: var(--text-tertiary); }

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

/* 批量导入提示词板块 */
.kw-import-prompt-banner {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-left: 3px solid #8b5cf6;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.kip-head { display: flex; align-items: center; gap: 12px; padding: 12px 16px; cursor: pointer; }
.kip-icon { color: #8b5cf6; font-size: 18px; flex-shrink: 0; }
.kip-head-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.kip-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.kip-hint { font-size: 12px; color: var(--text-tertiary); line-height: 1.5; }
.kip-chevron { color: var(--text-tertiary); transition: transform .2s; flex-shrink: 0; }
.kip-chevron.is-open { transform: rotate(180deg); }
.kip-body { padding: 0 16px 14px; }
.kip-textarea :deep(.el-textarea__inner) { font-family: 'SF Mono', 'Monaco', monospace; font-size: 12px; }
.kip-foot { display: flex; align-items: center; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
.kip-tip { font-size: 12px; color: var(--text-tertiary); }
</style>
