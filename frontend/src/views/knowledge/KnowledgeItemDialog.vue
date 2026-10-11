<template>
  <el-dialog v-model="visible" :title="editing ? '编辑知识点' : '新建知识点'" width="720px" top="5vh">
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
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="save" :loading="saving">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 知识库 —— 新建/编辑知识点弹窗。
 *
 * 自持表单与保存请求。`categories` 由父组件传入（分类在父组件里是共享状态：
 * 左栏、列表、本弹窗、批量导入都要用）。
 *
 * 「分类」右侧那个 + 按钮做的是**就地快捷新建**（一个 prompt 起一个分类），
 * 不打开分类弹窗。原先这段逻辑在视图里，它要跨越组件去改 `form.category_id`；
 * 现在 `form` 就在本组件内，写完直接选中，反而更简单。
 */
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, StarFilled } from '@element-plus/icons-vue'
import { knowledgeApi } from '../../api'

const props = defineProps({
  /** 分类列表（父组件持有） */
  categories: { type: Array, default: () => [] },
  /** 当前行业 id */
  industryId: { type: [Number, String], default: 0 },
})

const emit = defineEmits(['saved', 'category-created'])

const visible = ref(false)
const editing = ref(false)
const saving = ref(false)
const form = ref({ title: '', content: '', category_id: null, tags: '', summary: '', source: '', importance: 'normal', status: 'published' })

function openCreate(presetCategoryId = null) {
  editing.value = false
  form.value = {
    title: '', content: '', category_id: presetCategoryId, tags: '',
    summary: '', source: '', importance: 'normal', status: 'published',
    industry_id: props.industryId,
  }
  visible.value = true
}

function openEdit(item) {
  editing.value = true
  form.value = { ...item }
  visible.value = true
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
    visible.value = false
    emit('saved')
  } finally {
    saving.value = false
  }
}

// ===== 内联创建分类 =====
async function inlineCreateCategory() {
  // ⚠️ 弹窗与请求必须分开 try —— 原先两者共用一个 `catch { /* 用户取消 */ }`，
  // 于是请求里的任何异常（含下面那个真实存在过的取值 bug）都被伪装成「用户取消了」，
  // 既不报错也不提示，功能静默失效。取消是**预期内**的控制流，请求失败不是。
  let name
  try {
    const { value } = await ElMessageBox.prompt('请输入分类名称', '新建分类', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
    })
    name = (value || '').trim()
  } catch {
    return // 用户取消，正常路径
  }
  if (!name) return

  try {
    const res = await knowledgeApi.quickCreateCategory({ industry_id: props.industryId, name })
    ElMessage.success('分类创建成功')
    emit('category-created')
    // 拦截器已经把 axios 外壳拆掉了，res 就是后端体 { code, data }。
    // 这里原先写 res.data.data.id —— 多拆了一层，data.data 恒为 undefined，
    // 取 .id 直接抛错并被上面的 catch 吞掉，导致「新建的分类不会自动选中」。
    if (res?.data?.id) form.value.category_id = res.data.id
  } catch (e) {
    ElMessage.error('创建分类失败：' + (e?.message || e))
  }
}

defineExpose({ openCreate, openEdit })
</script>
