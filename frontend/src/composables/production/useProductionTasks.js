import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { productionApi } from '../../api'
import { formatMonthDay } from '../../utils/format'
import { TARGET_NEEDS_DEFAULT } from '../../constants/production'

/**
 * 生产任务的**生命周期**：列表 → 选中 → 逐步保存 → 版本回滚 → 删除。
 *
 * 这里只负责「任务这条记录本身」，不碰提示词渲染、GEO 评分、发布 ——
 * 那些各自有独立的 composable。`saveDraft` 由**调用方**（视图）持有，
 * 因为它要同时读取任务记录与勾选态，放在任何一侧都会造成循环依赖。
 *
 * @param {object}   deps
 * @param {object}   deps.store                Pinia app store（读 currentIndustryId）
 * @param {object}   deps.options              生产选项（reactive），本模块会 `Object.assign` 填充
 * @param {object}   deps.selections           useProductionSelections 的返回值
 * @param {Function} deps.saveDraft            静默保存
 * @param {object}   deps.illuState            第 10 步配图状态（reactive），选中任务时装载
 * @param {Function} deps.recommendationMethod 配图建议模式的 computed
 * @param {Function} deps.clearRenderedPrompt  清空已渲染提示词
 *   —— 切换任务 / 换步骤后旧提示词必须失效，否则用户会拿着「上一步的提示词」去问 AI
 */
export function useProductionTasks({
  store,
  options,
  selections,
  saveDraft,
  illuState,
  recommendationMethod,
  clearRenderedPrompt,
}) {
  const loadingTasks = ref(false)
  const loadingOptions = ref(false)
  const tasks = ref([])
  const currentTask = ref(null)

  /** 第 4 步核心需求（随任务加载/切换实时解析）。 */
  const step4Needs = reactive({ ...TARGET_NEEDS_DEFAULT })

  /** 解析任务保存的 target_needs（容错：字段缺失/格式错误时回退默认值）。 */
  function parseTargetNeeds(raw) {
    const def = { expected_recommendation: '', required_signals: [], must_address_pains: [] }
    if (!raw) return def
    try {
      const p = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (p && typeof p === 'object') {
        def.expected_recommendation = p.expected_recommendation || ''
        def.required_signals = Array.isArray(p.required_signals) ? p.required_signals : []
        def.must_address_pains = Array.isArray(p.must_address_pains) ? p.must_address_pains : []
      }
    } catch (e) {
      /* 忽略损坏数据，使用默认 */
    }
    return def
  }

  async function loadTasks() {
    if (!store.currentIndustryId) return
    loadingTasks.value = true
    try {
      const res = await productionApi.list({ industry_id: store.currentIndustryId })
      tasks.value = res.data || []
    } finally {
      loadingTasks.value = false
    }
  }

  async function createTask() {
    if (!store.currentIndustryId) {
      ElMessage.warning('请先选择行业')
      return
    }
    const res = await productionApi.create({
      industry_id: store.currentIndustryId,
      title: `软文任务 ${formatMonthDay(new Date())}`,
    })
    ElMessage.success('已创建新任务')
    await loadTasks()
    await selectTask(res.data)
  }

  async function handleDelete(t) {
    try {
      await ElMessageBox.confirm(
        `确定要删除「${t.title || '任务 #' + t.id}」吗？删除后不可恢复。`,
        '删除生产任务',
        { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' },
      )
    } catch {
      return
    }
    await productionApi.delete(t.id)
    ElMessage.success('已删除任务')
    // 若删除的是当前打开的任务，回退到空态
    if (currentTask.value && currentTask.value.id === t.id) {
      currentTask.value = null
      illuState.plan = null
    }
    await loadTasks()
  }

  async function selectTask(t) {
    currentTask.value = { ...t }
    selections.resetFromTask(t)
    // 第 4 步：按任务已存 target_needs 解析核心需求（画像/意图/必含信号/痛点）
    Object.assign(step4Needs, parseTargetNeeds(t.target_needs))
    clearRenderedPrompt()
    // 第 8 步：载入已保存的配图方案（后端存储为 { meta, recommendation, plan }，兼容旧版数组）
    illuState.plan = null
    illuState.promptId = 0
    illuState.style = ''
    if (t.illustration_plan) {
      try {
        const parsed = JSON.parse(t.illustration_plan)
        if (Array.isArray(parsed)) {
          illuState.plan = { plan: parsed }
        } else {
          illuState.plan = parsed
          illuState.promptId = parsed.meta?.prompt_id || 0
          illuState.style = parsed.meta?.style || ''
        }
      } catch {
        illuState.plan = null
      }
    }
    if (t.industry_id) await loadOptions()
    // 进入第10步时，默认按配图建议选择模式（AI 生图 / 网络搜图）
    if (currentTask.value.current_step === 10) {
      illuState.method = recommendationMethod.value || 'ai'
    }
  }

  async function loadOptions() {
    if (!currentTask.value?.id) return
    loadingOptions.value = true
    try {
      const res = await productionApi.options(currentTask.value.id)
      Object.assign(options, res.data)
    } finally {
      loadingOptions.value = false
    }
  }

  /* ============ 步骤导航 ============ */

  /** 允许「前进一格」或任意「后退」；跳步由后端 current_step 的单调性保证。 */
  function goStep(no) {
    if (no <= currentTask.value.current_step + 1) {
      currentTask.value.current_step = no
      clearRenderedPrompt()
    } else {
      ElMessage.warning('请先完成前面的步骤')
    }
  }

  function prevStep() {
    if (currentTask.value.current_step > 1) {
      currentTask.value.current_step--
      clearRenderedPrompt()
    }
  }

  async function nextStep() {
    await saveDraft(true)
    if (currentTask.value.current_step < 9) {
      currentTask.value.current_step++
      clearRenderedPrompt()
    }
  }

  /* ============ 分步保存 ============ */

  async function saveStep1(ind) {
    currentTask.value.industry_id = ind.id
    currentTask.value.industry_snapshot = ind.name
    await saveDraft(true)
    await loadOptions()
    ElMessage.success(`已选择行业：${ind.name}`)
  }

  async function saveStep2(p) {
    currentTask.value.platform_id = p.id
    currentTask.value.platform_snapshot = p.name
    await saveDraft(true)
    // 重新拉取选项，使第 3 步账号按所选平台过滤（与账号人设绑定）
    await loadOptions()
    ElMessage.success(`已选择平台：${p.name}`)
  }

  async function saveStep3Account(a) {
    currentTask.value.account_id = a.id
    currentTask.value.account_snapshot = a.account_name
    await saveDraft(true)
  }

  async function saveStep3Persona(p) {
    currentTask.value.persona_id = p.id
    currentTask.value.persona_snapshot = p.name
    await saveDraft(true)
    ElMessage.success('人设账号已确定')
  }

  /* ============ 版本 / 历史管理 ============ */

  const versionDialog = ref(false)
  const versionList = ref([])
  const versionStep = ref('')

  async function openVersions(step) {
    if (!currentTask.value) return
    versionStep.value = step
    versionDialog.value = true
    versionList.value = []
    const res = await productionApi.versions(currentTask.value.id, step)
    versionList.value = res.data || []
  }

  async function restoreVersion(v) {
    try {
      await ElMessageBox.confirm(`确定回滚到 v${v.version_no} 吗？当前内容将被覆盖`, '回滚确认', { type: 'warning' })
    } catch {
      return
    }
    await productionApi.restoreVersion(currentTask.value.id, v.id)
    const field = {
      outline: 'outline_content',
      draft: 'draft_content',
      rewrite: 'rewrite_content',
      safety: 'safety_report',
      final: 'final_content',
    }[v.step]
    if (field && currentTask.value) currentTask.value[field] = v.content
    ElMessage.success('已回滚到该版本')
    versionDialog.value = false
  }

  return {
    loadingTasks,
    loadingOptions,
    tasks,
    currentTask,
    step4Needs,
    loadTasks,
    createTask,
    handleDelete,
    selectTask,
    loadOptions,
    goStep,
    prevStep,
    nextStep,
    saveStep1,
    saveStep2,
    saveStep3Account,
    saveStep3Persona,
    versionDialog,
    versionList,
    versionStep,
    openVersions,
    restoreVersion,
  }
}
