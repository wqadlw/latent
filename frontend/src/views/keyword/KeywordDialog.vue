<template>
  <el-dialog v-model="visible" :title="editing ? '编辑关键词' : '新建关键词'" width="480px">
    <el-form :model="form" label-width="80px">
      <el-form-item label="关键词"><el-input v-model="form.word" /></el-form-item>
      <el-form-item label="分组">
        <el-select v-model="form.group_id" placeholder="未分组" clearable style="width: 100%;">
          <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="类型">
        <el-select v-model="form.type" style="width: 100%;">
          <el-option v-for="o in KEYWORD_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="优先级">
        <el-rate v-model="form.priority" />
      </el-form-item>
      <el-form-item label="关联产品"><el-input v-model="form.related_product" /></el-form-item>
      <el-form-item label="标签"><el-input v-model="form.tags" placeholder="逗号分隔" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="save" :loading="saving">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 新建 / 编辑关键词。自己管表单与保存请求，成功后 emit `saved` 让壳重新拉数。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { keywordApi } from '../../api'
import { KEYWORD_TYPE_OPTIONS } from '../../constants/status'

const props = defineProps({
  groups: { type: Array, default: () => [] },
  industryId: { type: [Number, String], default: 0 },
})
const emit = defineEmits(['saved'])

const visible = ref(false)
const editing = ref(false)
const saving = ref(false)
const form = ref({ word: '', group_id: null, type: 'long_tail', priority: 2, related_product: '', tags: '' })

/** @param presetGroupId 从当前选中的分组带过来，新建时预填 */
function openCreate(presetGroupId = null) {
  editing.value = false
  form.value = {
    word: '', group_id: presetGroupId, type: 'long_tail', priority: 2,
    related_product: '', tags: '', industry_id: props.industryId,
  }
  visible.value = true
}

function openEdit(row) {
  editing.value = true
  form.value = { ...row }
  visible.value = true
}

async function save() {
  if (!form.value.word?.trim()) { ElMessage.warning('请输入关键词'); return }
  saving.value = true
  try {
    if (editing.value) await keywordApi.update(form.value.id, form.value)
    else await keywordApi.create(form.value)
    ElMessage.success('保存成功')
    visible.value = false
    emit('saved')
  } finally {
    saving.value = false
  }
}

defineExpose({ openCreate, openEdit })
</script>
