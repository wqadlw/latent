<template>
  <el-dialog :model-value="modelValue" title="AI 写提示词（让 AI 为系统写标准模板）" width="720px"
    @update:model-value="$emit('update:modelValue', $event)">
    <el-alert type="info" :closable="false" show-icon class="ai-tip">
      <template #title>AI 会严格按照系统变量白名单生成</template>
      生成的提示词只会使用系统支持的内置变量（如 {brand_name} / {geo_signals}），可直接被生产链路渲染。若未配置 LLM，请先在「LLM 配置」页填写 Key，或手动编写。
    </el-alert>
    <el-form label-width="88px" style="margin-top: 12px;">
      <el-form-item label="类别">
        <el-select v-model="form.category" style="width: 100%">
          <el-option v-for="c in categories" :key="c.key" :label="c.name" :value="c.key" />
        </el-select>
      </el-form-item>
      <el-form-item label="名称（可选）">
        <el-input v-model="form.name" placeholder="留空将自动命名" />
      </el-form-item>
      <el-form-item label="要求描述">
        <el-input v-model="form.requirement" type="textarea" :rows="3" placeholder="例如：面向小红书的口语化大纲，强植入品牌信号，并呼应目标客户问 AI 的问题" />
      </el-form-item>
    </el-form>
    <div v-if="result" class="ai-result">
      <el-alert v-if="result.non_builtin && result.non_builtin.length" type="warning" :closable="false" show-icon
        :title="'有 ' + result.non_builtin.length + ' 个变量不在白名单：' + result.non_builtin.map(k => '{'+k+'}').join(' ')" />
      <!-- 生成结果允许就地微调后再保存，所以直接写回 result.content -->
      <el-input v-model="result.content" type="textarea" :rows="14" />
    </div>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
      <el-button :icon="CopyDocument" :disabled="!result" @click="$emit('copy')">复制</el-button>
      <el-button type="success" :disabled="!result" @click="$emit('save')">保存为提示词</el-button>
      <el-button type="primary" :icon="Cpu" :loading="loading" @click="$emit('generate')">生成</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { CopyDocument, Cpu } from '@element-plus/icons-vue'
import './prompt-library-shared.css'

/**
 * 「AI 写提示词」弹窗：让后端调用 LLM，按变量白名单起草一条标准模板。
 *
 * `form`（aiForm）与 `result`（aiResult）都由**视图**持有并作为 prop 传进来：
 * 视图在「保存为提示词」时要读 `form.category/name/requirement`，
 * 也要读 `result.content` 填进编辑器。放组件里就得再往外抛一遍，反而更绕。
 * 这与 `StepIllustration` 就地改 `illuState` 是同一个约定。
 */
defineProps({
  modelValue: { type: Boolean, default: false },
  categories: { type: Array, default: () => [] },
  /** 视图持有的 reactive 表单对象（本组件就地修改） */
  form: { type: Object, required: true },
  /** 生成结果（含 content / non_builtin），就地可编辑 */
  result: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})
defineEmits(['update:modelValue', 'generate', 'copy', 'save'])
</script>
