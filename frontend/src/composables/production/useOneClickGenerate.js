import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { productionApi } from '../../api'
import { writeClipboard } from '../../utils/clipboard'
import { STEP_TO_CAT, CAT_PROMPT_FIELD, CAT_CONTENT_FIELD, CAT_LABEL } from '../../constants/production'

/**
 * 一键生成：调用后端已配置的 LLM 直接产出内容，与「手动渲染提示词」模式并存。
 *
 * 未配置 LLM 时后端返回 `need_config`，这里把渲染好的提示词留在输入框里，
 * **引导用户走手动模式** —— 不能报个错就结束，否则用户会以为功能坏了。
 *
 * @param {object}   deps
 * @param {object}   deps.currentTask   当前任务 ref
 * @param {object}   deps.selections    useProductionSelections 的返回值
 * @param {object}   deps.renderedPrompt 已渲染提示词的 ref（need_config 时回填）
 * @param {object}   deps.cvar          useCustomVarDialog 的返回值
 * @param {object}   deps.geo           useGeoGate 的返回值（geo 步生成后要喂给终检）
 * @param {Function} deps.saveDraft     静默保存（采纳结果后写入任务）
 */
export function useOneClickGenerate({ currentTask, selections, renderedPrompt, cvar, geo, saveDraft }) {
  const genDialogVisible = ref(false)
  const genLoading = ref(false)
  const genAccepting = ref(false)
  const genData = ref(null)
  const genStep = ref('')

  async function generateByAI() {
    const step = STEP_TO_CAT[currentTask.value?.current_step]
    if (!step) return
    const promptId = currentTask.value[CAT_PROMPT_FIELD[step]]
    if (!promptId) {
      ElMessage.warning('请先选择提示词')
      return
    }
    // 自定义变量：先弹窗填写，再生成
    cvar.askCustomVars(promptId, (vars) => doGenerate(step, vars))
  }

  async function doGenerate(category, customVarsMap) {
    genLoading.value = true
    try {
      const res = await productionApi.generate(currentTask.value.id, {
        step: category,
        prompt_id: currentTask.value[CAT_PROMPT_FIELD[category]],
        keyword_ids: selections.selectedKeywordIds.value,
        knowledge_item_ids: selections.selectedKnowledgeIds.value,
        rule_ids: selections.selectedRuleIds.value,
        custom_vars: customVarsMap,
      })
      const d = res.data || {}
      if (d.need_config) {
        // 未配置 LLM：把渲染后的提示词留在输入框，引导手动模式
        renderedPrompt.value = d.rendered || ''
        ElMessage.warning(d.error || '未配置 LLM（如 DeepSeek），已为你生成提示词，可复制给 AI 工具')
        return
      }
      genData.value = d
      genStep.value = category
      genDialogVisible.value = true
    } catch (e) {
      /* 拦截器已提示 */
    } finally {
      genLoading.value = false
    }
  }

  /** 采纳生成结果：geo 步走终检解析写回，其余步直接写入对应内容字段。 */
  async function acceptGen() {
    const d = genData.value
    if (!d) return
    genAccepting.value = true
    try {
      if (genStep.value === 'geo') {
        // geo 步：把 AI 四段结果喂给 geo-finalize 解析并写回（标题/正文/评分/建议）
        geo.setFinalizeImportText(d.text)
        await geo.runGeoFinalize()
      } else {
        currentTask.value[CAT_CONTENT_FIELD[genStep.value]] = d.text
        await saveDraft(true)
        ElMessage.success('已写入' + (CAT_LABEL[genStep.value] || '内容'))
      }
      genDialogVisible.value = false
    } finally {
      genAccepting.value = false
    }
  }

  async function copyGenText() {
    if (!genData.value?.text) return
    if (await writeClipboard(genData.value.text)) ElMessage.success('已复制生成内容')
    else ElMessage.error('复制失败')
  }

  return { genDialogVisible, genLoading, genAccepting, genData, genStep, generateByAI, doGenerate, acceptGen, copyGenText }
}
