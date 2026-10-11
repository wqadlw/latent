import { ElMessage } from 'element-plus'
import { productionApi } from '../../api'
import { writeClipboard } from '../../utils/clipboard'
import { PROMPT_FIELD_BY_CATEGORY } from '../../constants/production'

/**
 * 提示词渲染：把「已选关键词 + 知识点 + 规则 + 自定义变量」拼成可直接粘贴给 AI 的提示词。
 *
 * 与「一键生成」的区别：这里只**渲染**提示词（用户自己拿去外部 AI 工具用），
 * 不调用 LLM。一键生成在 `useOneClickGenerate`，但两者共用自定义变量弹窗。
 *
 * @param {object} deps
 * @param {object} deps.currentTask    当前任务 ref
 * @param {object} deps.options        生产选项（reactive）
 * @param {object} deps.selections     useProductionSelections 的返回值
 * @param {object} deps.cvar           useCustomVarDialog 的返回值
 * @param {object} deps.renderedPrompt 已渲染提示词的 ref。⚠️ 由**视图**持有而不是本模块创建：
 *   「切换任务 / 换步骤要清空提示词」这件事发生在 `useProductionTasks` 里，
 *   若 ref 建在这里就会形成两个 composable 的循环依赖。
 */
export function usePromptRender({ currentTask, options, selections, cvar, renderedPrompt }) {
  /**
   * 写作步骤可用的提示词 = **严格按当前步骤的分类过滤**，确保与生产流程强耦合：
   * outline→outline、draft→draft、rewrite→rewrite、geo（第9步）→geo，互不串类。
   */
  function writingPrompts(cat) {
    return options.prompts?.[cat] || []
  }

  async function renderPrompt(category) {
    const promptId = currentTask.value[PROMPT_FIELD_BY_CATEGORY[category]]
    if (!promptId) {
      ElMessage.warning('请先选择提示词')
      return
    }
    // 若选中提示词含自定义变量，先弹窗填写，再渲染
    cvar.askCustomVars(promptId, (vars) => doRender(category, vars))
  }

  async function doRender(category, customVarsMap) {
    const promptId = currentTask.value[PROMPT_FIELD_BY_CATEGORY[category]]
    const res = await productionApi.render({
      task_id: currentTask.value.id,
      prompt_id: promptId,
      category,
      keyword_ids: selections.selectedKeywordIds.value,
      knowledge_item_ids: selections.selectedKnowledgeIds.value,
      rule_ids: selections.selectedRuleIds.value,
      custom_vars: customVarsMap,
    })
    renderedPrompt.value = res.data.rendered
    // 后端安全网：若有未解析变量，明确提醒，避免静默污染
    if (res.data && res.data.unresolved && res.data.unresolved.length) {
      ElMessage.warning('注意：' + res.data.unresolved.map((k) => '{' + k + '}').join(' ') + ' 未解析，已原样保留在提示词中')
    } else {
      ElMessage.success('提示词已生成，可复制到 AI 工具')
    }
  }

  /** 复制已生成的提示词到剪贴板，便于粘贴到外部 AI 工具。 */
  async function copyRenderedPrompt() {
    if (!renderedPrompt.value) {
      ElMessage.warning('请先生成提示词')
      return
    }
    if (await writeClipboard(renderedPrompt.value)) ElMessage.success('提示词已复制，可粘贴到 AI 工具')
    else ElMessage.error('复制失败，请手动选择文本复制')
  }

  return { writingPrompts, renderPrompt, doRender, copyRenderedPrompt }
}
