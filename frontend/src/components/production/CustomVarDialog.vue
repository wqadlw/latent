<template>
  <el-dialog v-model="visible" title="填写自定义变量" width="520px">
    <div class="cvar-tip">该提示词包含自定义变量，请填写后再生成：</div>
    <el-form label-width="130px">
      <el-form-item v-for="cv in list" :key="cv.name" :label="'{' + cv.name + '}'">
        <el-input v-model="cv.value" :placeholder="(cv.desc || '') + '（' + cv.name + '）'" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="$emit('confirm')">生成提示词</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  list: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'confirm'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
</script>
