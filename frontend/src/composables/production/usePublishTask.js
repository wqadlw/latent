import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { productionApi, publishApi } from '../../api'

/**
 * 第 9 步的两种「出去」动作：
 *   - `createPublishTask()` 走**发布中心**（建一条 publish_job，人工审核后执行）
 *   - `publishTask()`       直接标记文章已发布（底部操作栏的「发布文章」）
 *
 * 两者都受 GEO 闸门约束，但策略不同：
 *   建发布任务要求**先有最终正文**（硬拦截，因为没正文建任务没意义）；
 *   直接发布只**提示** GEO 分数不达标（软拦截，允许用户坚持）。
 *
 * @param {object}   deps
 * @param {object}   deps.currentTask   当前任务 ref
 * @param {object}   deps.store         Pinia app store（读 currentIndustryId）
 * @param {object}   deps.finalizeResult GEO 终检结果 ref（优先用它作为发布内容）
 * @param {Function} deps.saveDraft     静默保存
 * @param {Function} deps.goStep        跳转到指定步骤（GEO 不达标时引导回第 9 步）
 * @param {Function} deps.loadTasks     刷新任务列表
 * @param {Function} deps.selectTask    重新选中任务（发布后刷新任务态）
 * @param {object}   deps.tasks         任务列表 ref
 */
export function usePublishTask({ currentTask, store, finalizeResult, saveDraft, goStep, loadTasks, selectTask, tasks }) {
  const publishDialog = ref(false)
  const publishSaving = ref(false)
  const publishPlatforms = ref([])
  const publishForm = reactive({ platform: '', adapter_type: 'playwright', scheduled_at: '' })

  /** 选中的平台若是 api 适配器，默认降级为 mock —— 只有 playwright 适配器支持真发。 */
  function onPublishPlatformChange() {
    const p = publishPlatforms.value.find((x) => x.platform === publishForm.platform)
    if (p && p.adapter_type === 'api') publishForm.adapter_type = 'mock'
  }

  async function openPublishDialog() {
    if (!currentTask.value?.id) return
    if (!currentTask.value.final_content?.trim()) {
      ElMessage.warning('请先在上方完成 GEO 终稿导入，生成最终正文后再建发布任务')
      return
    }
    try {
      const res = await publishApi.platforms(store.currentIndustryId)
      publishPlatforms.value = res.data || []
    } catch (e) {
      publishPlatforms.value = []
    }
    // 默认选第一个非 api 适配器的平台（api 平台不能真发）
    publishForm.platform = (publishPlatforms.value.find((p) => p.adapter_type !== 'api') || {}).platform || ''
    publishForm.adapter_type = 'playwright'
    publishForm.scheduled_at = ''
    publishDialog.value = true
  }

  async function createPublishTask() {
    if (!publishForm.platform) {
      ElMessage.warning('请选择目标平台')
      return
    }
    const title = finalizeResult.value?.final_title || currentTask.value.final_title || currentTask.value.title
    const content = finalizeResult.value?.final_content || currentTask.value.final_content
    if (!content?.trim()) {
      ElMessage.warning('缺少最终正文，无法建任务')
      return
    }
    publishSaving.value = true
    try {
      await publishApi.createJob({
        industry_id: store.currentIndustryId,
        task_id: currentTask.value.id,
        platform: publishForm.platform,
        adapter_type: publishForm.adapter_type,
        title,
        content,
        scheduled_at: publishForm.scheduled_at || '',
      })
      ElMessage.success('已创建发布任务，请在左侧「发布中心」审核并执行')
      publishDialog.value = false
    } catch (e) {
      /* 拦截器已提示 */
    } finally {
      publishSaving.value = false
    }
  }

  /** 底部操作栏的「发布文章」：GEO 未达标时软提示，允许用户坚持发布。 */
  async function publishTask() {
    if (!currentTask.value.final_content?.trim()) {
      ElMessage.warning('请先回填最终文章内容')
      return
    }
    const sc = currentTask.value.geo_score
    const geoMsg =
      sc == null
        ? '尚未运行 GEO 评分——建议在「安全发布 & GEO 筛选」步骤先评分，确认内容可被 AI 抓取引用后再发布。'
        : sc >= 70
          ? `当前 GEO 评分 ${sc}/100（已达标闸门）。确认发布该文章？`
          : `当前 GEO 评分 ${sc}/100 未达 70 闸门，建议先优化 GEO 信号（品牌实体/事实密度/意图覆盖）。仍要发布？`
    try {
      await ElMessageBox.confirm(geoMsg, '发布确认（GEO 闸门）', {
        type: 'warning',
        confirmButtonText: sc != null && sc < 70 ? '仍要发布' : '确认发布',
        cancelButtonText: '去优化',
      })
    } catch {
      // 用户选了「去优化」：GEO 不达标时跳回第 9 步
      if (sc != null && sc < 70) goStep(9)
      return
    }
    await saveDraft(true)
    await productionApi.publish(currentTask.value.id, { publish_url: currentTask.value.publish_url || '' })
    ElMessage.success('文章已发布，任务完成')
    await loadTasks()
    const updated = tasks.value.find((t) => t.id === currentTask.value.id)
    if (updated) await selectTask(updated)
  }

  return {
    publishDialog,
    publishSaving,
    publishPlatforms,
    publishForm,
    onPublishPlatformChange,
    openPublishDialog,
    createPublishTask,
    publishTask,
  }
}
