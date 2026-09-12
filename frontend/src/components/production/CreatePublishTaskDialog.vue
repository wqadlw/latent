<template>
  <el-dialog v-model="visible" title="创建自动化发布任务" width="560px">
    <el-form label-width="92px">
      <el-form-item label="目标平台" required>
        <el-select v-model="form.platform" style="width: 100%" @change="$emit('platform-change')">
          <el-option
            v-for="p in platforms"
            :key="p.platform"
            :label="p.name + (p.adapter_type === 'api' ? '（官方API暂缓）' : '（浏览器自动化）')"
            :value="p.platform"
            :disabled="p.adapter_type === 'api'"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="适配器">
        <el-radio-group v-model="form.adapter_type">
          <el-radio value="playwright">Playwright（真实发布）</el-radio>
          <el-radio value="mock">Mock 测试（不走浏览器）</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="计划时间">
        <el-date-picker v-model="form.scheduled_at" type="datetime" placeholder="可选，留空立即审核" style="width: 100%" value-format="YYYY-MM-DD HH:mm:ss" />
      </el-form-item>
      <el-alert
        v-if="form.adapter_type === 'playwright'"
        type="info" :closable="false" show-icon
        title="真实发布需先在「发布中心」配置该平台 cookie 凭证；执行时若未配置将失败。无浏览器环境可用 Mock 测试验证链路。"
      />
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :icon="Promotion" :loading="saving" @click="$emit('create')">创建（进入待审核）</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
import { Promotion } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  form: { type: Object, required: true },
  platforms: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'platform-change', 'create'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
</script>
