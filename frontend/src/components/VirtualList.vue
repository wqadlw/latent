<template>
  <div ref="root" class="vlist" @scroll.passive="onScroll">
    <div class="vlist__spacer" :style="{ height: totalHeight + 'px' }">
      <div class="vlist__window" :style="windowStyle">
        <div
          v-for="(item, i) in visibleItems"
          :key="keyOf(item, startIndex * columns + i)"
          class="vlist__cell"
          :data-focus-id="isFocus(item, startIndex * columns + i) ? String(focusId) : undefined"
        >
          <slot :item="item" :index="startIndex * columns + i" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

const props = defineProps({
  // 完整数据（不过滤的版本由父组件传入，父组件自行 filter 后传进来）
  items: { type: Array, default: () => [] },
  // 单行高度（px），不含 gap；卡片应与此高度一致（卡片内 overflow:hidden）
  rowHeight: { type: Number, default: 120 },
  // 行/列间距（px）
  gap: { type: Number, default: 8 },
  // 单列最小宽度；容器宽度 >= 该值时才会多列。设很大(如 99999)即强制单列。
  minColWidth: { type: Number, default: 99999 },
  // 上下多渲染的行数，避免快速滚动白屏
  overscan: { type: Number, default: 4 },
  // 取 key 的函数
  getKey: { type: Function, default: (it) => it?.id },
  // 全局搜索定位目标 id；变化时自动滚动到对应行并渲染，配合 useFocusScroll
  focusId: { type: [String, Number], default: null },
})

const root = ref(null)
const scrollTop = ref(0)
const viewportH = ref(600)
const width = ref(0)
let ro = null

const stride = computed(() => props.rowHeight + props.gap)
const columns = computed(() => {
  if (!width.value) return 1
  const c = Math.floor((width.value + props.gap) / (props.minColWidth + props.gap))
  return Math.max(1, c)
})
const rowCount = computed(() => Math.ceil(props.items.length / columns.value))
const totalHeight = computed(() => rowCount.value * stride.value)
const startIndex = computed(() =>
  Math.max(0, Math.floor(scrollTop.value / stride.value) - props.overscan)
)
const endIndex = computed(() =>
  Math.min(rowCount.value, Math.ceil((scrollTop.value + viewportH.value) / stride.value) + props.overscan)
)
const visibleItems = computed(() =>
  props.items.slice(startIndex.value * columns.value, endIndex.value * columns.value)
)
const offsetY = computed(() => startIndex.value * stride.value)
const windowStyle = computed(() => ({
  position: 'absolute',
  top: offsetY.value + 'px',
  left: '0',
  right: '0',
  display: 'grid',
  gridTemplateColumns: `repeat(${columns.value}, minmax(0, 1fr))`,
  gridAutoRows: props.rowHeight + 'px',
  gap: props.gap + 'px',
  padding: props.gap + 'px',
}))

function keyOf(item, index) {
  const k = props.getKey(item)
  return k != null ? k : 'idx-' + index
}
function isFocus(item, index) {
  if (props.focusId == null) return false
  return String(props.getKey(item)) === String(props.focusId)
}
function onScroll(e) {
  scrollTop.value = e.target.scrollTop
}
function measure() {
  if (!root.value) return
  // 仅在尺寸真实变化时写入响应式值，避免无谓重渲染再次触发 observer
  const h = root.value.clientHeight
  const w = root.value.clientWidth
  if (h !== viewportH.value) viewportH.value = h
  if (w !== width.value) width.value = w
}

onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined' && root.value) {
    // 用 rAF 包裹，打断「observer 回调 → 同步改尺寸 → 再次触发 observer」的循环，
    // 消除浏览器原生的 "ResizeObserver loop completed with undelivered notifications." 通知。
    ro = new ResizeObserver(() => requestAnimationFrame(measure))
    ro.observe(root.value)
  }
})
onBeforeUnmount(() => {
  if (ro && root.value) ro.disconnect()
})

// 数据量变化（含筛选/切分类）时：若正在定位则滚动到目标，否则回到顶部
watch(
  () => props.items.length,
  () => {
    if (props.focusId != null) {
      scrollToFocus()
    } else if (root.value) {
      root.value.scrollTop = 0
      scrollTop.value = 0
    }
  }
)

// 全局搜索定位：滚动到目标行，使其进入可见窗口并被渲染（useFocusScroll 才能 querySelector 到）
watch(
  () => props.focusId,
  () => scrollToFocus()
)

function scrollToFocus() {
  const id = props.focusId
  if (id == null || !root.value) return
  const idx = props.items.findIndex((it) => String(props.getKey(it)) === String(id))
  if (idx < 0) return
  const row = Math.floor(idx / columns.value)
  const target = Math.max(0, row * stride.value - viewportH.value / 2 + props.rowHeight / 2)
  root.value.scrollTop = target
  scrollTop.value = target
  nextTick(() => measure())
}
</script>

<style scoped>
.vlist {
  height: 100%;
  width: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;
  -webkit-overflow-scrolling: touch;
}
.vlist__spacer {
  position: relative;
  width: 100%;
}
.vlist__window {
  width: 100%;
}
.vlist__cell {
  min-width: 0;
}
</style>
