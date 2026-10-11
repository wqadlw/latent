<template>
  <el-dialog v-model="visible" :title="editing ? '编辑分类' : '新建分类'" width="460px">
    <el-form :model="form" label-width="80px">
      <el-form-item label="分类名称">
        <el-input v-model="form.name" placeholder="请输入分类名称" />
      </el-form-item>
      <el-form-item label="图标">
        <el-select v-model="form.icon" placeholder="选择图标" style="width: 100%;">
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
            :class="{ active: form.color === c }"
            @click="form.color = c"
          ></div>
        </div>
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="分类描述（可选）" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="save" :loading="saving">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 知识库 —— 新建/编辑分类弹窗。
 *
 * 自持表单状态与保存请求（沿用 D4 的 CreateRunDialog 范式：弹窗自己管自己的事）。
 * 父组件只做两件事：调 `openCreate()` / `openEdit(category)`，然后监听 `saved` 去刷新。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { knowledgeApi } from '../../api'
import { ICON_MAP as iconMap, ICON_OPTIONS as iconOptions } from '../../constants/icons'

const props = defineProps({
  /** 当前行业 id */
  industryId: { type: [Number, String], default: 0 },
})

const emit = defineEmits(['saved'])

// 可选主题色（分类色带用；与分组共用同一套观感）
const colorOptions = ['#6366f1', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#8b5cf6', '#64748b']

const visible = ref(false)
const editing = ref(false)
const saving = ref(false)
const form = ref({ name: '', icon: 'Folder', color: '#6366f1', description: '' })

function openCreate() {
  editing.value = false
  form.value = { name: '', icon: 'Folder', color: '#6366f1', description: '', industry_id: props.industryId }
  visible.value = true
}

function openEdit(category) {
  editing.value = true
  form.value = { ...category, industry_id: props.industryId }
  visible.value = true
}

async function save() {
  if (!form.value.name?.trim()) { ElMessage.warning('请输入分类名称'); return }
  saving.value = true
  try {
    if (editing.value) {
      await knowledgeApi.updateCategory(form.value.id, form.value)
      ElMessage.success('更新成功')
    } else {
      await knowledgeApi.createCategory(form.value)
      ElMessage.success('创建成功')
    }
    visible.value = false
    emit('saved')
  } finally {
    saving.value = false
  }
}

defineExpose({ openCreate, openEdit })
</script>

<style scoped>
.color-picker-row { display: flex; gap: 8px; flex-wrap: wrap; }
.color-dot {
  width: 28px; height: 28px; border-radius: 50%; cursor: pointer;
  border: 2px solid transparent; transition: all 0.16s;
}
.color-dot:hover { transform: scale(1.1); }
.color-dot.active { border-color: var(--text-primary); box-shadow: 0 0 0 2px var(--bg-card), 0 0 0 4px var(--brand-400); }
</style>
