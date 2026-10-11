<template>
  <el-dialog v-model="visible" title="文章改写模式" width="760px" append-to-body @open="loadBrands">
    <el-form :model="form" label-width="100px" class="rewrite-form">
      <el-form-item label="待改写原文" required>
        <el-input
          v-model="form.source_text"
          type="textarea"
          :rows="8"
          placeholder="把被判软文 / 低质、或想换发布模式的文章整篇粘贴到这里…"
        />
      </el-form-item>
      <el-form-item label="目标发布模式">
        <el-radio-group v-model="form.target_mode">
          <el-radio value="geo">geo 强品牌</el-radio>
          <el-radio value="platform">平台合规</el-radio>
          <el-radio value="green">绿色吸粉</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="品牌">
        <el-select v-model="form.brand_asset_id" placeholder="用行业默认品牌" clearable style="width: 100%">
          <el-option v-for="b in brandOptions" :key="b.id" :label="b.brand_name" :value="b.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="引擎">
        <el-radio-group v-model="form.ai_engine">
          <el-radio value="deepseek">DeepSeek（真实改写）</el-radio>
          <el-radio value="mock">Mock（演示）</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item>
        <el-button type="warning" :loading="loading" @click="doRewrite">开始改写</el-button>
      </el-form-item>
    </el-form>

    <div v-if="result" class="rewrite-result">
      <div class="rewrite-risk">
        <div class="rewrite-risk__item" :class="riskClass(result.source_risk && result.source_risk.risk_score)">
          <div class="rewrite-risk__label">改写前软文风险</div>
          <div class="rewrite-risk__val">
            {{ result.source_risk ? result.source_risk.risk_score : '—' }}
            <small v-if="result.source_risk">{{ result.source_risk.risk_level }}</small>
          </div>
        </div>
        <div class="rewrite-risk__arrow">→</div>
        <div class="rewrite-risk__item" :class="riskClass(result.platform_compliance && result.platform_compliance.risk_score)">
          <div class="rewrite-risk__label">改写后软文风险</div>
          <div class="rewrite-risk__val">
            {{ result.platform_compliance ? result.platform_compliance.risk_score : (result.target_mode === 'geo' ? '不评' : '—') }}
            <small v-if="result.platform_compliance">{{ result.platform_compliance.risk_level }}</small>
          </div>
        </div>
        <div class="rewrite-risk__engine">引擎：{{ result.engine === 'mock' ? 'Mock 演示' : 'DeepSeek' }}</div>
      </div>

      <el-alert
        :type="result.gate_pass ? 'success' : 'warning'"
        :closable="false"
        class="pc-tip"
        :title="result.verdict"
      />

      <div class="rewrite-out__head">
        <span>改写后的文章（{{ modeLabel(result.target_mode) }}）</span>
        <el-button size="small" @click="copyRewrite">复制全文</el-button>
      </div>
      <el-input
        :model-value="result.rewritten_text"
        type="textarea"
        :rows="12"
        readonly
        class="rewrite-out"
      />

      <div v-if="result.issues && result.issues.length" class="rewrite-issues">
        <div class="rewrite-issues__title">预检明细</div>
        <ul>
          <li v-for="(it, i) in result.issues" :key="i">{{ it }}</li>
        </ul>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
/**
 * 文章改写模式（P2-3）：贴被判软文 → 按目标模式一键改写。
 *
 * 从 BrowserStudio.vue（1412 行）拆出来的第一个组件。
 * 选它先拆，是因为它是**依赖最少、最自足**的一块：
 * 自己的表单、自己的结果、自己的请求，只从父组件拿一个 industryId，
 * 对外只暴露一个 `open()`。先拆这样的块，能最低风险地把「拆分范式」跑通，
 * 再动运行列表 / 详情面板那些真正互相纠缠的部分。
 *
 * 父组件用法：
 *   <RewriteDialog ref="rewriteRef" :industry-id="industryId()" />
 *   rewriteRef.value.open()      // 点横幅时调用
 */
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { browserStudioApi, brandAssetApi } from '../../api'
import { modeLabel } from '../../constants/modes'
import { writeClipboard } from '../../utils/clipboard'
import './studio-shared.css'

const props = defineProps({
  /** 当前行业 id；为 0 时后端会走「无行业」分支 */
  industryId: { type: Number, default: 0 },
})

const visible = ref(false)
const loading = ref(false)
const result = ref(null)
const brandOptions = ref([])
const form = reactive({
  source_text: '',
  target_mode: 'platform',
  brand_asset_id: null,
  ai_engine: 'mock',
})

/** 打开弹窗。每次打开都清掉上一次的结果，避免「新开窗却看到旧改写稿」。 */
function open() {
  result.value = null
  visible.value = true
}

async function loadBrands() {
  try {
    const res = await brandAssetApi.list(props.industryId)
    brandOptions.value = res.data || []
  } catch {
    // 品牌列表拉不到不该阻塞改写——后端会用行业默认品牌
    brandOptions.value = []
  }
}

/** 风险分 → 高/中/低配色类。分档与后端 platform_compliance 的口径一致。 */
function riskClass(score) {
  if (score === null || score === undefined) return ''
  if (score >= 70) return 'is-high'
  if (score >= 40) return 'is-mid'
  return 'is-low'
}

async function doRewrite() {
  if (!form.source_text.trim()) {
    ElMessage.warning('请先粘贴待改写的原文')
    return
  }
  loading.value = true
  try {
    const res = await browserStudioApi.rewrite({
      industry_id: props.industryId,
      source_text: form.source_text,
      target_mode: form.target_mode,
      brand_asset_id: form.brand_asset_id || null,
      ai_engine: form.ai_engine,
    })
    if (res.code === 0 && res.data && res.data.ok) {
      result.value = res.data
    } else {
      ElMessage.warning((res.data && res.data.error) || '改写失败')
    }
  } catch (e) {
    ElMessage.warning('改写请求失败：' + (e?.response?.data?.error || e.message || e))
  } finally {
    loading.value = false
  }
}

async function copyRewrite() {
  const txt = result.value?.rewritten_text || ''
  if (await writeClipboard(txt)) {
    ElMessage.success('已复制改写稿')
  } else {
    ElMessage.warning('没有可复制的内容，或当前环境不支持自动复制')
  }
}

defineExpose({ open })
</script>

<style scoped>
/* ⚠️ `.pc-tip` 不在这里 —— 它被本组件和预检弹窗共用，
   写在 scoped 里够不到对方，所以放在 studio-shared.css（非 scoped）。 */

.rewrite-form { margin-top: 4px; }
.rewrite-result { margin-top: 18px; border-top: 1px dashed var(--border-light); padding-top: 16px; }
.rewrite-risk { display: flex; align-items: center; gap: 18px; margin-bottom: 14px; }
.rewrite-risk__item {
  flex: 1; text-align: center; padding: 12px; border-radius: 10px; background: var(--bg-secondary);
  border: 1px solid var(--border-light);
}
.rewrite-risk__label { font-size: 12px; color: var(--text-secondary); }
.rewrite-risk__val { font-size: 26px; font-weight: 800; margin-top: 4px; }
.rewrite-risk__val small { font-size: 12px; font-weight: 600; margin-left: 4px; }
.rewrite-risk__arrow { font-size: 22px; color: var(--text-quaternary); }
.rewrite-risk__engine { font-size: 12px; color: var(--text-secondary); align-self: flex-end; padding-bottom: 12px; }

/* 风险档位配色。这三个类只被本组件的 riskClass() 用到，故随组件一起搬过来。 */
.is-high { color: #cf1322; border-color: #ffa39e !important; background: #fff1f0 !important; }
.is-mid { color: #d46b08; border-color: #ffd591 !important; background: #fff7e6 !important; }
.is-low { color: #389e0d; border-color: #b7eb8f !important; background: #f6ffed !important; }

.rewrite-out__head { display: flex; align-items: center; justify-content: space-between; margin: 12px 0 6px; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.rewrite-out { font-family: var(--font-mono); font-size: 12.5px; }
.rewrite-issues { margin-top: 12px; }
.rewrite-issues__title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.rewrite-issues ul { margin: 0; padding-left: 18px; }
.rewrite-issues li { font-size: 12.5px; line-height: 1.7; color: var(--text-secondary); }
</style>
