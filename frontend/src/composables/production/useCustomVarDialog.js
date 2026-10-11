import { ref } from 'vue'
import { parseJsonArray } from '../../utils/json'
import { findInCategoryMap } from '../../utils/lookup'

/**
 * 自定义变量填写弹窗。
 *
 * 提示词模板里可以带 `{变量名}`，渲染 / 一键生成之前必须先让用户填值。
 * 这个弹窗被**两个动作共用**（渲染提示词、一键生成），所以单独抽出来。
 *
 * ⚠️ 原实现用 `cvarPendingAction = 'render' | 'generate'` 这个字符串来分发回调，
 * 意味着每加一个用得上自定义变量的动作，就要在 `confirmCvar` 里多写一个分支。
 * 这里改成**存回调**：谁打开弹窗谁把自己的「填完了要做什么」交进来。
 *
 * @param {object} deps
 * @param {object} deps.options  生产选项（reactive）。⚠️ 必须传整个 reactive 对象而不是
 *   `options.prompts` —— `loadOptions()` 会 `Object.assign` **替换**掉 prompts，
 *   提前取出的引用会指向过期数据，导致按 id 找不到提示词（静默不弹自定义变量框）。
 */
export function useCustomVarDialog({ options }) {
  const cvarDialog = ref(false)
  const cvarList = ref([])
  let pending = null

  /** 跨分类按 id 找提示词（含 geo），用于读取 variable_schema。 */
  function findPromptById(id) {
    return findInCategoryMap(options.prompts, id)
  }

  /**
   * 若该提示词声明了自定义变量 → 打开弹窗，用户确认后回调 `onFilled(varsMap)`，返回 true。
   * 若没有自定义变量 → **立刻**回调 `onFilled({})`，返回 false（调用方不必再管）。
   *
   * @returns {boolean} 是否弹出了弹窗（调用方据此决定要不要提前 return）
   */
  function askCustomVars(promptId, onFilled) {
    const prompt = findPromptById(promptId)
    const custom = parseJsonArray(prompt?.variable_schema).filter((v) => v && v.name)
    if (!custom.length) {
      onFilled({})
      return false
    }
    cvarList.value = custom.map((v) => ({ name: v.name, desc: v.desc || '', value: '' }))
    pending = onFilled
    cvarDialog.value = true
    return true
  }

  function confirmCvar() {
    const cv = {}
    cvarList.value.forEach((v) => {
      if (v.name) cv[v.name] = v.value || ''
    })
    cvarDialog.value = false
    const fn = pending
    pending = null
    if (fn) fn(cv)
  }

  return { cvarDialog, cvarList, askCustomVars, confirmCvar, findPromptById }
}
