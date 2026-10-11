import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { writeClipboard } from '../../utils/clipboard'
import { RULE_TYPE_META, RULE_TYPE_ORDER } from '../../constants/production'

/**
 * 生产工作台的「勾选态」：已选关键词 / 知识点 / 规则，以及它们的派生视图。
 *
 * 为什么单独成模块：这三份 id 列表被 7 处读写 —— 任务切换时装载、保存草稿时序列化、
 * 渲染提示词与一键生成时作为入参、第 5 步的知识点面板、第 3 步的规则面板。
 * 之前它们散在 `Production.vue` 里，谁都能改，改完还得记得调 `saveDraft`。
 *
 * @param {object}   deps
 * @param {object}   deps.options    生产选项（reactive），需要 `rules` 与 `knowledge_grouped`
 * @param {Function} deps.saveDraft  静默持久化（勾选规则后立刻落库，避免「选了但没生效」）
 */
export function useProductionSelections({ options, saveDraft }) {
  const selectedKeywordIds = ref([])
  const selectedKnowledgeIds = ref([])
  const selectedRuleIds = ref([])

  /* ============ 规则（第 3 步） ============ */

  /** 仅展示该行业下确实有规则的类型分组。 */
  const ruleGroupList = computed(() => {
    const rb = options.rules || {}
    return RULE_TYPE_ORDER
      .filter((rt) => rb[rt] && rb[rt].length)
      .map((rt) => ({ type: rt, meta: RULE_TYPE_META[rt], items: rb[rt] }))
  })

  const hasAnyRules = computed(() => ruleGroupList.value.length > 0)

  /** 已选规则按类型计数（写作步骤据此反馈「已应用规则」）。 */
  const selectedRuleBreakdown = computed(() => {
    const rb = options.rules || {}
    const ids = new Set(selectedRuleIds.value)
    const b = { ai_seo: 0, anti_ai: 0, compliance: 0 }
    for (const rt of RULE_TYPE_ORDER) {
      for (const r of rb[rt] || []) if (ids.has(r.id)) b[rt]++
    }
    return b
  })

  const selectedRuleTotal = computed(
    () => selectedRuleBreakdown.value.ai_seo + selectedRuleBreakdown.value.anti_ai + selectedRuleBreakdown.value.compliance,
  )

  /** 切换规则选择，并**静默持久化** —— 渲染提示词时要保证后端已有这份勾选。 */
  function toggleRule(id) {
    const idx = selectedRuleIds.value.indexOf(id)
    if (idx >= 0) selectedRuleIds.value.splice(idx, 1)
    else selectedRuleIds.value.push(id)
    saveDraft(true)
  }

  const allRulesSelected = computed(() => {
    const all = ruleGroupList.value.flatMap((g) => g.items.map((r) => r.id))
    return all.length > 0 && all.every((id) => selectedRuleIds.value.includes(id))
  })

  function toggleSelectAllRules() {
    selectedRuleIds.value = allRulesSelected.value
      ? []
      : ruleGroupList.value.flatMap((g) => g.items.map((r) => r.id))
    saveDraft(true)
  }

  /* ============ 关键词 / 知识点（第 5 步） ============ */

  function toggleKeyword(id) {
    const idx = selectedKeywordIds.value.indexOf(id)
    if (idx >= 0) selectedKeywordIds.value.splice(idx, 1)
    else selectedKeywordIds.value.push(id)
  }

  function toggleKnowledge(id) {
    const idx = selectedKnowledgeIds.value.indexOf(id)
    if (idx >= 0) selectedKnowledgeIds.value.splice(idx, 1)
    else selectedKnowledgeIds.value.push(id)
  }

  function clearKnowledge() {
    selectedKnowledgeIds.value = []
  }

  /** 某分类是否已被全选。 */
  function isCategoryAllSelected(sec) {
    if (!sec.items.length) return false
    return sec.items.every((ki) => selectedKnowledgeIds.value.includes(ki.id))
  }

  /** 全选 / 取消全选某分类。 */
  function toggleCategoryAll(sec) {
    const ids = sec.items.map((ki) => ki.id)
    const set = new Set(selectedKnowledgeIds.value)
    if (isCategoryAllSelected(sec)) ids.forEach((id) => set.delete(id))
    else ids.forEach((id) => set.add(id))
    selectedKnowledgeIds.value = Array.from(set)
  }

  /** 已选知识点详情（附所属分类），用于右侧面板反馈与「导出大纲素材」。 */
  const selectedKnowledgeItems = computed(() => {
    const result = []
    const seen = new Set()
    for (const g of options.knowledge_grouped || []) {
      for (const ki of g.items || []) {
        if (selectedKnowledgeIds.value.includes(ki.id) && !seen.has(ki.id)) {
          seen.add(ki.id)
          result.push({ ...ki, categoryId: g.category.id, categoryName: g.category.name })
        }
      }
    }
    return result
  })

  /** 已选知识点概览（数量 + 覆盖分类数）。 */
  const selectedKnowledgeSummary = computed(() => {
    const cats = new Set()
    selectedKnowledgeItems.value.forEach((ki) => {
      if (ki.categoryId) cats.add(ki.categoryId)
    })
    return { count: selectedKnowledgeItems.value.length, categoryCount: cats.size }
  })

  /* ============ 知识点预览抽屉 ============ */

  const previewKnowledgeItem = ref(null)
  const previewDrawer = ref(false)

  function previewKnowledge(ki) {
    previewKnowledgeItem.value = ki
    previewDrawer.value = true
  }

  function onPreviewToggle(id) {
    toggleKnowledge(id)
    previewDrawer.value = false
  }

  /** 导出已选知识点为大纲素材（拼成文本，供 AI 直接利用）。 */
  async function exportKnowledgeMaterial() {
    const items = selectedKnowledgeItems.value
    if (!items.length) {
      ElMessage.warning('请先选择知识点')
      return
    }
    const lines = items.map((ki, i) => {
      const body = ki.summary || (ki.content || '').slice(0, 120)
      return body ? `${i + 1}. ${ki.title}\n   ${body}` : `${i + 1}. ${ki.title}`
    })
    const text = `【大纲素材】以下是本文需覆盖的知识点：\n\n${lines.join('\n\n')}`
    if (await writeClipboard(text)) ElMessage.success('已复制大纲素材，可粘贴给 AI')
  }

  /* ============ 与任务记录同步 ============ */

  /** 切换任务时，把任务上逗号分隔的 id 串装回三个数组。 */
  function resetFromTask(t) {
    const parseIds = (s) => (s ? s.split(',').filter(Boolean).map(Number) : [])
    selectedKeywordIds.value = parseIds(t.keyword_ids)
    selectedKnowledgeIds.value = parseIds(t.knowledge_item_ids)
    selectedRuleIds.value = parseIds(t.rule_ids)
  }

  /** 保存草稿时要回写的三串 id。 */
  function toTaskFields() {
    return {
      keyword_ids: selectedKeywordIds.value.join(','),
      knowledge_item_ids: selectedKnowledgeIds.value.join(','),
      rule_ids: selectedRuleIds.value.join(','),
    }
  }

  return {
    selectedKeywordIds,
    selectedKnowledgeIds,
    selectedRuleIds,
    ruleGroupList,
    hasAnyRules,
    selectedRuleBreakdown,
    selectedRuleTotal,
    allRulesSelected,
    toggleRule,
    toggleSelectAllRules,
    toggleKeyword,
    toggleKnowledge,
    clearKnowledge,
    isCategoryAllSelected,
    toggleCategoryAll,
    selectedKnowledgeItems,
    selectedKnowledgeSummary,
    previewKnowledgeItem,
    previewDrawer,
    previewKnowledge,
    onPreviewToggle,
    exportKnowledgeMaterial,
    resetFromTask,
    toTaskFields,
  }
}
