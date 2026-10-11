<template>
  <el-dialog v-model="visible" title="发布前软文预检" width="640px" append-to-body>
    <div v-loading="loading" element-loading-text="正在跑综合质量闸门…">
      <template v-if="result">
        <el-alert
          v-if="!result.has_content"
          type="warning" :closable="false" show-icon
          title="尚未生成终稿，无法预检"
          description="请先完成创作流程（①连接 → ⑥GEO终稿）生成终稿后再确认/发布。"
        />
        <template v-else>
          <el-alert
            :type="result.gate_pass ? 'success' : 'error'"
            :closable="false" show-icon
            :title="result.verdict"
            :description="`发布模式：${result.mode}${result.output_format === 'mdx' ? '（官网 MDX）' : ''}`"
          />
          <el-descriptions :column="2" border size="small" class="pc-metrics">
            <el-descriptions-item label="综合闸门">
              <el-tag :type="result.gate_pass ? 'success' : 'danger'" size="small">
                {{ result.gate_pass ? '通过' : '未过' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="平台基础合规">
              <el-tag :type="result.compliance_pass ? 'success' : 'danger'" size="small">
                {{ result.compliance_pass ? '通过' : '未过' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="GEO 评分">
              <span :class="result.geo_pass ? 'pc-ok' : 'pc-warn'">
                {{ result.geo_score }} 分{{ result.geo_pass ? '（达标≥70）' : '（未达标）' }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item v-if="result.platform_compliance" label="软文风险分">
              <el-tag :type="riskTagType(result.platform_compliance.risk_level)" size="small">
                {{ result.platform_compliance.risk_score }} 分 · {{ result.platform_compliance.risk_level }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>

          <div v-if="result.platform_compliance && result.platform_compliance.soft_issues && result.platform_compliance.soft_issues.length" class="pc-block">
            <div class="pc-block-title">软文特征信号（平台算法重点判定项）</div>
            <ul class="pc-issue-list">
              <li v-for="(it, i) in result.platform_compliance.soft_issues" :key="'s'+i">{{ it }}</li>
            </ul>
          </div>

          <div v-if="result.issues && result.issues.length" class="pc-block">
            <div class="pc-block-title">全部问题清单（合规 / GEO / 软文）</div>
            <ul class="pc-issue-list">
              <li v-for="(it, i) in result.issues" :key="'i'+i">{{ it }}</li>
            </ul>
          </div>

          <el-alert
            v-if="!result.gate_pass"
            type="warning" :closable="false" class="pc-tip"
            title="提示"
            description="该文章在目标平台大概率会被判软文广告或违规而拒稿。建议回到「GEO 强化 / 整改」步骤洗稿降风险，或改用 geo 强品牌模式后重新预检。"
          />
        </template>
      </template>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :disabled="result && !result.has_content"
        @click="onProceed"
      >
        {{ action === 'publish' ? '仍要发布' : '仍要确认' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 发布前软文预检（P2-1 / C 项补全）。
 *
 * 这是「确认 / 发布」的强制闸门：先跑一遍综合质量检查，把结论摊给用户看，
 * 用户看完再决定要不要继续。所以它**不做**确认/发布本身——
 * 那两件事要动运行状态、要刷新列表、要开轮询，属于父组件的编排职责。
 * 这里只 emit `proceed`，把决定交回去。
 *
 * 数据获取放在组件内（而不是父组件取好再传）：预检结果的生命周期和弹窗完全一致，
 * 放外面反而要父组件多维护一份「结果 + loading + action」状态。
 *
 * 父组件用法：
 *   <PrecheckDialog ref="precheckRef" @proceed="onPrecheckProceed" />
 *   precheckRef.value.open(runId, 'confirm' | 'publish')
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { browserStudioApi } from '../../api'
import { riskTagType } from '../../constants/browserStudio'
import './studio-shared.css'

const emit = defineEmits(['proceed'])

const visible = ref(false)
const loading = ref(false)
const result = ref(null)
const action = ref('confirm')

/**
 * 打开弹窗并立即拉预检结果。
 * @param {number} runId  生产任务 id
 * @param {'confirm'|'publish'} act  用户接下来想做什么（决定按钮文案）
 */
async function open(runId, act) {
  if (!runId) return
  action.value = act || 'confirm'
  loading.value = true
  visible.value = true
  result.value = null
  try {
    const res = await browserStudioApi.precheck(runId)
    // ⚠️ 拦截器（api/index.js）已经 `return response.data`，即把 axios 外壳拆掉、
    // 直接给到后端体 `{ code, data }`。所以结果就是 `res.data`。
    // 这里原先写的是 `res.data.data` —— 多拆了一层，恒为 undefined，
    // 于是 result 永远是 null、弹窗正文永远是空的。
    // 「发布前预检」这个强制闸门因此从来没有展示过任何结论。
    if (res?.code === 0 && res.data) result.value = res.data
    else {
      ElMessage.warning((res && res.msg) || '预检未返回结果')
      visible.value = false
    }
  } catch (e) {
    ElMessage.warning('预检请求失败：' + (e?.response?.data?.message || e.message || '网络错误'))
    visible.value = false
    return
  } finally {
    loading.value = false
  }
}

function onProceed() {
  visible.value = false
  emit('proceed', action.value)
}

defineExpose({ open })
</script>

<style scoped>
/* ⚠️ `.pc-tip` 在 studio-shared.css（非 scoped）—— 它被本组件和文章改写弹窗共用，
   写在 scoped 里够不到对方。 */

.pc-metrics { margin: 12px 0; }
.pc-ok { color: var(--accent-emerald); font-weight: 600; }
.pc-warn { color: var(--amber-500); font-weight: 600; }
.pc-block { margin: 10px 0; }
.pc-block-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.pc-issue-list { margin: 0; padding-left: 18px; max-height: 220px; overflow-y: auto; }
.pc-issue-list li { font-size: 12.5px; line-height: 1.7; color: var(--text-secondary); }
</style>
