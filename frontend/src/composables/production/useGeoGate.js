import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { productionApi } from '../../api'
import { writeClipboard } from '../../utils/clipboard'
import { GEO_DIM_META, MIND_DIM_META } from '../../constants/production'

/**
 * 第 9 步「GEO 筛选闸门」：本地启发式体检 + AI 终稿导入 + 可复制的优化建议提示词。
 *
 * 「GEO」在这里有两条互不干扰的路径，不要混淆：
 *   - `runLocalGeoScore()`  本地算法打分（六维算法信任 + 五维心智温度），用于快速体检
 *   - `runGeoFinalize()`    把外部 AI 返回的结构化终稿**解析并写回任务**（一步出稿）
 *
 * @param {object}   deps
 * @param {object}   deps.currentTask 当前任务 ref
 * @param {Function} deps.saveDraft   静默保存（评分写回任务后需要落库）
 */
export function useGeoGate({ currentTask, saveDraft }) {
  const geoScoring = ref(false)
  const geoResult = ref(null)
  const finalizing = ref(false)
  const finalizeResult = ref(null)
  const finalizeImportText = ref('')

  function setFinalizeImportText(v) {
    finalizeImportText.value = v
  }

  /** 有任何一版正文就允许跑体检 —— 终稿/精修稿/初稿都算。 */
  const hasFinalContent = computed(
    () => !!(currentTask.value?.final_content || currentTask.value?.rewrite_content || currentTask.value?.draft_content),
  )

  /** 本地启发式兜底（无 AI 时快速体检）。 */
  async function runLocalGeoScore() {
    if (!currentTask.value?.id) return
    geoScoring.value = true
    try {
      const res = await productionApi.geoScore(currentTask.value.id)
      geoResult.value = res.data
      currentTask.value.geo_score = res.data.score
      await saveDraft(true)
      if (res.data.gate_pass) ElMessage.success(`本地体检 ${res.data.score}/100，已通过闸门`)
      else ElMessage.warning(`本地体检 ${res.data.score}/100，未达 ${res.data.gate_threshold} 分闸门，详见待优化项`)
    } catch (e) {
      ElMessage.error('评分失败：' + (e?.response?.data?.detail || ''))
    } finally {
      geoScoring.value = false
    }
  }

  /**
   * 终检合并端点：解析 AI 返回的「安全·GEO 终稿」结构化结果，
   * 评分（优先 AI 分，缺失本地兜底）+ 出稿一步到位。
   */
  async function runGeoFinalize() {
    if (!currentTask.value?.id) return
    if (!finalizeImportText.value.trim()) {
      ElMessage.warning('请先粘贴 AI 返回的完整结果')
      return
    }
    finalizing.value = true
    try {
      const res = await productionApi.geoFinalize(currentTask.value.id, finalizeImportText.value)
      const d = res.data
      finalizeResult.value = d
      // 同步写回任务主记录，使上方主文本框与发布逻辑立即生效
      currentTask.value.final_title = d.final_title
      currentTask.value.final_content = d.final_content
      currentTask.value.geo_score = d.geo_score
      currentTask.value.safety_report = d.safety_report || ''
      await saveDraft(true)
      const gate = d.quality_gate
      if (gate && !gate.gate_pass) {
        const n = (gate.issues && gate.issues.length) || 0
        ElMessage.warning(
          `终检完成，但平台合规闸门未通过（${n} 项待整改），详见下方红色横幅；GEO 评分 ${d.geo_score}/100`,
        )
      } else if (d.geo_score >= 70) {
        ElMessage.success(`终检完成，合规闸门通过 + GEO ${d.geo_score}/100 已达标，可直接复制发布`)
      } else {
        ElMessage.warning(`终检完成，合规闸门通过；GEO 评分 ${d.geo_score}/100 未达 70，建议优化后重跑`)
      }
    } catch (e) {
      ElMessage.error('终检导入失败：' + (e?.response?.data?.detail || e?.message || ''))
    } finally {
      finalizing.value = false
    }
  }

  /**
   * GEO 优化建议提示词（可复制）。
   * 根据评分结果与**薄弱维度**（得分 < 权重 60%）动态生成，可粘贴给 AI 改写。
   * 薄弱维度才生成专项提示词，避免甩给用户一堆用不上的模板。
   */
  const geoSuggestionPrompts = computed(() => {
    const r = geoResult.value
    if (!r) return []
    const score = r.score ?? 0
    const threshold = r.gate_threshold ?? 70
    const dims = r.dimensions || {}
    const weights = r.weights || {}
    const issues = r.issues || []
    const intentQ = r.intent_question || ''
    const rec = r.expected_recommendation || ''
    const signals = (r.signals_present || []).join('、')
    const prompts = []

    // 整体优化提示词
    const lines = []
    lines.push(
      `你是一位 GEO（生成式引擎优化）改写专家。下面是一篇待优化的软文，GEO 评分 ${score}/100（达标阈值 ${threshold}），${r.gate_pass ? '已达标' : '未达标'}。`,
    )
    if (intentQ) lines.push(`该文应服务的目标客户意图问题：${intentQ}`)
    if (rec) lines.push(`期望 AI 推荐我们的角度：${rec}`)
    lines.push('请在不改变核心信息与推荐角度的前提下，针对以下待优化项改写，使其更易被 AI 检索、提取并作为推荐来源引用：')
    if (issues.length) issues.forEach((it) => lines.push('• ' + it))
    else
      lines.push(
        '• 当前未列明具体待优化项，请按 GEO 六维（品牌实体信号/事实密度/意图覆盖/问答形态/结构可提取/信号可归属）整体加强。',
      )
    lines.push(
      '优化重点：补充品牌实体信号（品牌名/官网/联系方式/核心产品）、增加可量化数据、采用问答/FAQ 或疑问式小标题、补充标题层级与列表、增加可溯源证据。直接输出改写后的全文，不要输出说明。',
    )
    prompts.push({ title: '整体 GEO 优化提示词', prompt: lines.join('\n') })

    // 算法信任薄弱维度专项提示词
    for (const key of Object.keys(GEO_DIM_META)) {
      const w = weights[key] || 0
      const d = dims[key] ?? 0
      if (w > 0 && d < w * 0.6) {
        const meta = GEO_DIM_META[key]
        const pl = [
          `你是一位 GEO 优化专家。请聚焦提升文章的「${meta.label}」维度（当前 ${d}/${w}，偏弱）。`,
          intentQ ? `目标客户意图问题：${intentQ}` : '',
          rec ? `期望推荐角度：${rec}` : '',
          `具体做法：${meta.tip}`,
          signals ? `已命中的 GEO 信号：${signals}` : '',
          '请在保持原文核心信息的前提下改写，直接输出优化后的相关段落。',
        ].filter(Boolean)
        prompts.push({ title: `${meta.label} · 专项优化`, prompt: pl.join('\n') })
      }
    }

    // 心智温度薄弱维度专项提示词
    const mind = r.mind_resonance
    if (mind) {
      const mDims = mind.dimensions || {}
      const mWeights = mind.weights || {}
      for (const key of Object.keys(MIND_DIM_META)) {
        const w = mWeights[key] || 0
        const d = mDims[key] ?? 0
        if (w > 0 && d < w * 0.6) {
          const meta = MIND_DIM_META[key]
          const pl = [
            `你是一位内容改写专家。请聚焦提升文章的「${meta.label}」维度（当前 ${d}/${w}，偏弱）。`,
            `这是心智温度诊断（判断内容是否能让真实读者产生情感共鸣与信任感）。`,
            intentQ ? `目标客户意图问题：${intentQ}` : '',
            `具体做法：${meta.tip}`,
            '请在保持原文核心信息与推荐角度的前提下改写，直接输出优化后的相关段落。',
          ].filter(Boolean)
          prompts.push({ title: `心智温度 · ${meta.label} 专项优化`, prompt: pl.join('\n') })
        }
      }
    }
    return prompts
  })

  async function copySuggestion(text) {
    if (await writeClipboard(text)) ElMessage.success('已复制 GEO 建议提示词，可粘贴给 AI 改写')
    else ElMessage.error('复制失败，请手动复制')
  }

  return {
    geoScoring,
    geoResult,
    finalizing,
    finalizeResult,
    finalizeImportText,
    setFinalizeImportText,
    hasFinalContent,
    runLocalGeoScore,
    runGeoFinalize,
    geoSuggestionPrompts,
    copySuggestion,
  }
}
