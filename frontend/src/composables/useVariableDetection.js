import { ref, computed, watch } from 'vue'
import { promptLibraryApi } from '../api'

/**
 * 变量检测：随编辑器内容变化，向后台问「这段文本里有哪些变量、是不是白名单内的」。
 *
 * 用途有两个，都在编辑器里：
 *   - `detectedVars`   已识别变量（含是否内置），渲染成标签条
 *   - `unresolvedVars` 非白名单变量 —— 渲染时会被**原样保留**成 `{xxx}` 喂给 AI，
 *     不报错但会污染输入、拉低产出质量，极难排查。所以保存前要拦一道。
 *
 * ⚠️ 原实现写的是 `watch(..., { debounce: 500 })`。
 * **Vue 的 watch 没有 `debounce` 这个选项**，它会被静默忽略 ——
 * 也就是说这段代码实际上**每敲一个字符就打一次接口**，而且没人发现。
 * 这里改成真正的手写防抖，并加了请求序号防乱序覆盖。
 *
 * @param {Function} content 取当前内容的 getter（如 `() => form.value.content`）
 * @param {number}   delay   防抖毫秒数
 */
export function useVariableDetection(content, delay = 400) {
  const detectedVars = ref([])

  let timer = null
  let seq = 0 // 请求序号：慢的旧响应不许覆盖快的新响应

  watch(content, (val) => {
    if (timer) clearTimeout(timer)
    if (!val) {
      detectedVars.value = []
      return
    }
    timer = setTimeout(async () => {
      const mine = ++seq
      try {
        const res = await promptLibraryApi.detectVariables(val)
        if (mine === seq) detectedVars.value = res.data || []
      } catch {
        /* 检测失败不该打断编辑，静默忽略 */
      }
    }, delay)
  })

  /** 不在系统白名单内的变量名 —— 渲染时会原样保留为 `{变量名}`。 */
  const unresolvedVars = computed(() => detectedVars.value.filter((v) => !v.is_builtin).map((v) => v.key))

  return { detectedVars, unresolvedVars }
}
