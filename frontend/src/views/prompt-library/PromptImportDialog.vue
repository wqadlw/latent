<template>
  <el-dialog :model-value="modelValue" title="批量导入 AI 提示词" width="680px"
    @update:model-value="$emit('update:modelValue', $event)">
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
      <template #title>支持三种方式</template>
      ① 直接粘贴 JSON 数组；② 上传 .json 文件；③ 每条字段：<b>name / category / content / description / tags</b>（category 取值 outline / draft / rewrite / safety / illustration / geo）。
    </el-alert>
    <el-form label-width="80px">
      <el-form-item label="JSON数据">
        <el-input v-model="importData" type="textarea" :rows="10" placeholder='JSON数组格式：[{"name":"GEO软文生成","category":"geo","content":"你是一位 GEO 内容策略专家…","description":"生成带信号的 GEO 软文","tags":"GEO,带信号"}]' />
      </el-form-item>
      <el-form-item label="或上传文件">
        <el-upload
          action="#"
          :auto-upload="false"
          :show-file-list="true"
          :on-change="handleFile"
          :before-upload="() => false"
          accept=".json"
          style="width: 100%;"
        >
          <el-button :icon="Document">选择 .json 文件</el-button>
        </el-upload>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button text @click="$emit('download-template')">下载模板</el-button>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="$emit('submit', importData)" :loading="importing">导入</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Document } from '@element-plus/icons-vue'
import './prompt-library-shared.css'

/**
 * 批量导入提示词弹窗。
 *
 * 本组件只负责「拿到一段 JSON 文本」（粘贴或读文件），
 * **解析与调接口留在视图**：导入失败要区分「JSON 格式错」和「后端校验错」，
 * 那种错误处理属于页面编排，塞进弹窗会让它无法复用于其它导入入口。
 */
defineProps({
  modelValue: { type: Boolean, default: false },
  importing: { type: Boolean, default: false },
})
defineEmits(['update:modelValue', 'submit', 'download-template'])

const importData = ref('')

function handleFile(file) {
  const f = file.raw || file
  if (!f) return
  const reader = new FileReader()
  reader.onload = (e) => {
    importData.value = e.target.result || ''
    ElMessage.info(`已读取文件：${file.name}`)
  }
  reader.readAsText(f)
}

/**
 * 清空输入。视图在**关闭**弹窗时调用 ——
 * 上一次没导成功的脏 JSON 留在框里，会让人以为已经导过了。
 */
defineExpose({ reset: () => (importData.value = '') })
</script>
