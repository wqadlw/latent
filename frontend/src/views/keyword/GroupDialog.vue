<template>
  <el-dialog v-model="visible" :title="editing ? '编辑分组' : '新建分组'" width="440px">
    <el-form :model="form" label-width="72px">
      <el-form-item label="分组名称"><el-input v-model="form.name" placeholder="如：品牌词 / 竞品词 / 618活动" /></el-form-item>
      <el-form-item label="主题色">
        <el-color-picker v-model="form.color" />
        <el-input v-model="form.color" style="width: 110px; margin-left: 10px;" />
      </el-form-item>
      <el-form-item label="图标">
        <el-select v-model="form.icon" placeholder="选择图标" style="width: 100%;">
          <el-option v-for="ic in ICON_OPTIONS" :key="ic" :label="ic" :value="ic">
            <el-icon style="vertical-align: middle;"><component :is="ICON_MAP[ic]" v-if="ICON_MAP[ic]" /></el-icon>
            <span style="margin-left: 8px;">{{ ic }}</span>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="save" :loading="saving">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 新建 / 编辑关键词分组。图标下拉来自 `constants/icons.js` 单一真源
 * （原先 Knowledge.vue 与 Keyword.vue 各存一份 iconOptions，且已经漂移）。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { keywordGroupApi } from '../../api'
import { ICON_MAP, ICON_OPTIONS } from '../../constants/icons'

const props = defineProps({
  industryId: { type: [Number, String], default: 0 },
})
const emit = defineEmits(['saved'])

const visible = ref(false)
const editing = ref(false)
const saving = ref(false)
const form = ref({ name: '', color: '#6366f1', icon: 'Folder', description: '', industry_id: null })

function openCreate() {
  editing.value = false
  form.value = { name: '', color: '#6366f1', icon: 'Folder', description: '', industry_id: props.industryId }
  visible.value = true
}

function openEdit(g) {
  editing.value = true
  form.value = { ...g, industry_id: props.industryId }
  visible.value = true
}

async function save() {
  if (!form.value.name?.trim()) { ElMessage.warning('请输入分组名称'); return }
  saving.value = true
  try {
    if (editing.value) {
      await keywordGroupApi.update(form.value.id, form.value)
      ElMessage.success('分组已更新')
    } else {
      await keywordGroupApi.create(form.value)
      ElMessage.success('分组已创建')
    }
    visible.value = false
    emit('saved')
  } finally {
    saving.value = false
  }
}

defineExpose({ openCreate, openEdit })
</script>
