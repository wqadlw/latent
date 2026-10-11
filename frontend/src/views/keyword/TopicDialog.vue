<template>
  <el-dialog v-model="visible" :title="editing ? '编辑选题' : '新建选题'" width="560px">
    <el-form :model="form" label-width="80px">
      <el-form-item label="选题标题"><el-input v-model="form.title" /></el-form-item>
      <el-form-item label="选题描述">
        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="选题的核心角度/要打的关键词意图（可选）" />
      </el-form-item>
      <el-form-item label="关联关键词">
        <el-select v-model="selectedKeywords" multiple filterable placeholder="选择该选题要打的关键词" style="width: 100%;">
          <el-option v-for="k in keywords" :key="k.id" :label="k.word + (k.related_product ? ` (${k.related_product})` : '')" :value="k.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="平台">
        <el-select v-model="form.platform_id" style="width: 100%;">
          <el-option v-for="p in platforms" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="账号">
        <el-select v-model="form.account_id" style="width: 100%;">
          <el-option v-for="a in accounts" :key="a.id" :label="a.account_name" :value="a.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="计划日期"><el-input v-model="form.plan_date" placeholder="YYYY-MM-DD" /></el-form-item>
      <el-form-item label="状态">
        <el-select v-model="form.status" style="width: 100%;">
          <el-option v-for="(label, value) in TOPIC_STATUS_LABEL" :key="value" :label="label" :value="value" />
        </el-select>
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
 * 新建 / 编辑选题。
 *
 * 需要 keywords / platforms / accounts 三张表来填下拉，由壳传入。
 * 状态选项直接从 `TOPIC_STATUS_LABEL` 派生，不再手抄一遍「待处理/进行中/已完成」。
 * 关键词多选在表单里是数组，落库前拼成逗号串（`keyword_id_list`）。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { topicApi } from '../../api'
import { TOPIC_STATUS_LABEL } from '../../constants/status'

const props = defineProps({
  keywords: { type: Array, default: () => [] },
  platforms: { type: Array, default: () => [] },
  accounts: { type: Array, default: () => [] },
  industryId: { type: [Number, String], default: 0 },
})
const emit = defineEmits(['saved'])

const visible = ref(false)
const editing = ref(false)
const saving = ref(false)
const form = ref({ title: '', platform_id: null, account_id: null, plan_date: '', status: 'pending', description: '', keyword_id_list: '' })
const selectedKeywords = ref([])

function openCreate() {
  editing.value = false
  form.value = {
    title: '', platform_id: props.platforms[0]?.id, account_id: props.accounts[0]?.id,
    plan_date: '', status: 'pending', description: '', keyword_id_list: '', industry_id: props.industryId,
  }
  selectedKeywords.value = []
  visible.value = true
}

function openEdit(row) {
  editing.value = true
  form.value = { ...row, industry_id: props.industryId }
  selectedKeywords.value = String(row.keyword_id_list || '')
    .split(',').map((s) => parseInt(s.trim())).filter((n) => !isNaN(n) && n > 0)
  visible.value = true
}

async function save() {
  if (!form.value.title?.trim()) { ElMessage.warning('请输入选题标题'); return }
  form.value.keyword_id_list = selectedKeywords.value.join(',')
  saving.value = true
  try {
    if (editing.value) await topicApi.update(form.value.id, form.value)
    else await topicApi.create(form.value)
    ElMessage.success('保存成功')
    visible.value = false
    emit('saved')
  } finally {
    saving.value = false
  }
}

defineExpose({ openCreate, openEdit })
</script>
