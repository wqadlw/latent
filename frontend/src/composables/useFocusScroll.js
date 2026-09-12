import { watch } from 'vue'
import { useRoute } from 'vue-router'

/**
 * 全局搜索跳转定位：监听 URL 上的 ?focus=<id>&t=<timestamp> 参数，
 * 等待目标列表渲染完成后，将对应行滚动到视口中央并做短暂高亮。
 * 适用于带 data-focus-id 的普通元素，以及 el-table 行（约定 row-class 为 focus-row-<id>）。
 */
export function useFocusScroll() {
  const route = useRoute()

  function scrollTo(id) {
    if (!id) return
    let tries = 0
    const tick = () => {
      let el = document.querySelector(`[data-focus-id="${id}"]`)
      if (!el) el = document.querySelector(`.focus-row-${id}`)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        // 主题无关的高亮：用 outline，避免依赖明暗主题色
        el.style.outline = '2px solid #6366f1'
        el.style.outlineOffset = '-2px'
        el.style.transition = 'outline-color .3s ease'
        setTimeout(() => {
          el.style.outlineColor = 'transparent'
          setTimeout(() => {
            el.style.outline = ''
            el.style.outlineOffset = ''
            el.style.transition = ''
          }, 350)
        }, 1700)
      } else if (tries++ < 30) {
        // 列表可能还在异步加载 / 标签页还在切换，重试最多 ~3s
        setTimeout(tick, 100)
      }
    }
    setTimeout(tick, 60)
  }

  // t 时间戳保证即使是同一路由、同一 id 也能重新触发定位
  watch(() => route.query.t, () => scrollTo(route.query.focus), { immediate: true })
}
