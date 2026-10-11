<script setup>
/**
 * 工作台两栏容器（左栏 + 主区，右栏为预留槽）。
 *
 * 为什么会有这个组件：
 *   D4–D6 拆完之后，同一个「左栏 + 主区」结构被抄了 6 份，宽度有 5 个值、gap 有 4 个值、
 *   高度策略有 5 种（详见 docs/PhaseD-D7-三栏工作台与菜单单一来源.md 的 1.2 节）。
 *   差异本身是合理的，但**每一份都从零写一遍**不是 —— 于是间距、断点、滚动契约各写各的，
 *   修一处漏五处。这个组件把这些收敛成一个显式 API。
 *
 * 与「不要为拆而拆」的关系：
 *   D5 曾刻意**不建**计划里的 components/catalog/ 公共层，理由是「两边差异大于共性」。
 *   这里相反 —— 6 处是同一个实体，只是参数不同，所以值得抽。判据不是「有没有重复」，
 *   而是「**重复的是不是同一件事**」。
 *
 * ⚠️ 根元素**就是** grid 容器（不额外包一层），这样父组件传进来的 class 会通过
 *   attrs fallthrough 落在根上 —— 既有的验收钩子类名（`.prod-layout` / `.kw-layout` /
 *   `.studio__body` / `.iq-body`）因此可以原样保留，`shot-*.mjs` 的断言不用改。
 *
 * ⚠️ 关于 `detail` 槽：计划里写的是「左·中·右三槽」，但实证结果是**没有任何页面是三栏** ——
 *   详情要么是 el-drawer 浮层，要么本来就长在右栏里。槽位保留（成本 3 行），
 *   但**当前无调用方**。不要为了「把三栏用起来」去把浮层改成常驻列 —— 那是交互变更，不是重构。
 */
import { computed, useSlots } from 'vue'

const props = defineProps({
  /** 左栏宽度。5 个使用方各有取值：220 / 232 / 268 / 300 / 320 */
  asideWidth: { type: String, default: '280px' },
  /** 栏间距。统一到 16px 是本组件「视觉一致」的主要落点 */
  gap: { type: String, default: '16px' },
  /** 交叉轴对齐：Knowledge 用 start（左栏不拉伸），其余用默认 stretch */
  align: { type: String, default: 'stretch' },
  /** 作为 flex 子项撑满父容器剩余高度（父容器需是 flex 列）。Production / BrowserStudio 用 */
  fill: { type: Boolean, default: false },
  /** 显式最小高度。Keyword 500px / IntentQuestion 540px 用 */
  minHeight: { type: String, default: '' },
  /** 折叠左栏（宽度归零）。⚠️ 当前只有 Production 接了折叠按钮 */
  collapsed: { type: Boolean, default: false },
})

const slots = useSlots()
const hasDetail = computed(() => !!slots.detail)

// 用 CSS 变量而不是动态 class 拼装：变量能被使用方的内联 style 覆盖，
// 也方便在 DevTools 里直接改数值调试。
const styleVars = computed(() => {
  const vars = {
    '--wb-aside': props.collapsed ? '0px' : props.asideWidth,
    '--wb-gap': props.gap,
    '--wb-align': props.align,
  }
  if (props.minHeight) vars['--wb-min-height'] = props.minHeight
  return vars
})
</script>

<template>
  <div
    class="wb"
    :class="{ 'wb--fill': fill, 'wb--3col': hasDetail, 'wb--collapsed': collapsed }"
    :style="styleVars"
  >
    <aside class="wb__aside"><slot name="aside" /></aside>
    <div class="wb__main"><slot name="main" /></div>
    <div v-if="hasDetail" class="wb__detail"><slot name="detail" /></div>
  </div>
</template>

<style scoped>
.wb {
  display: grid;
  /* minmax(0, 1fr) 而不是 1fr：`1fr` 隐含 minmax(auto, 1fr)，
     内容比列宽时列**不肯收缩**，会把整个容器顶宽 —— 主区里那些
     `overflow: auto` 的表格/虚拟列表就会从「内部滚动」变成「整页横向滚动」。 */
  grid-template-columns: var(--wb-aside, 280px) minmax(0, 1fr);
  gap: var(--wb-gap, 16px);
  align-items: var(--wb-align, stretch);
  min-height: var(--wb-min-height, auto);
}

/* 右栏只在真的传了 detail 槽时才占位 —— 否则会留一条空列 */
.wb--3col {
  grid-template-columns: var(--wb-aside, 280px) minmax(0, 1fr) var(--wb-detail, 360px);
}

.wb--fill {
  flex: 1 1 auto;
  min-height: 0;
}

/* 折叠：列宽归零 + 裁剪溢出，否则左栏内容会盖到主区上 */
.wb--collapsed {
  grid-template-columns: 0 minmax(0, 1fr);
}
.wb--collapsed.wb--3col {
  grid-template-columns: 0 minmax(0, 1fr) var(--wb-detail, 360px);
}
/* 折叠时直接不渲染左栏，而不是「宽度 0 + overflow:hidden」——
   后者在窄屏单列时会留下一列空的 0 宽轨道，且子元素的 min-width:auto 会顶开。 */
.wb--collapsed .wb__aside {
  display: none;
}

/* ⚠️ display: contents 是本组件的关键设计，别改成普通块级盒子。
   槽位包裹元素**不产生盒子**，使用方传进来的元素因此仍然是 .wb 的直接网格项 ——
   与 D7 之前「子元素就是网格项」的写法逐字等价。若给包裹元素一个真实盒子，
   就会多出一层，「子元素撑满列高」要靠 height:100% 才能维持，
   而 .task-panel / .iq-side 这类子元素并没有写 height:100% —— 会静默塌成内容高度。 */
.wb__aside,
.wb__main,
.wb__detail {
  display: contents;
}

/* 窄屏单列。断点与既有 .kw-layout / .iq-body 保持一致，不引入新断点 */
@media (max-width: 1024px) {
  .wb,
  .wb--3col,
  .wb--collapsed,
  .wb--collapsed.wb--3col {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
