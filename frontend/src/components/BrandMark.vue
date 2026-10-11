<template>
  <!--
    品牌标记「显影 Latent」——**全站唯一来源**。

    为什么抽成组件：侧边栏、登录页、以及后续可能出现的空状态页都要用同一个图形。
    各自内联一份 SVG，改一次就要改 N 处，早晚漂移成三个不同的 logo。
    这与「版本号只在 version.py 定义一次」是同一条原则。

    图形语义：双层六边形构成光圈 —— 外层是镜筒，内层灰环是光圈叶片，
    中心圆点是最终显影的焦点。整个隐喻对应产品的核心动作：
    内容从「潜影」（未被 AI 收录）到「显影」（被引用）。

    关于底板（chip）
    ----------------
    默认**不加底板**。应用外壳（侧边栏 #0b1120、登录页深色品牌区）本身就是深色，
    而品牌墨黑 #1C1917 与它们几乎同色，加底板只会糊成一团。
    现代深色后台的通行做法就是裸字形 —— 靠形状和配色立住，而不是靠一块方底板。
    底板仅在需要独立轮廓的场合（favicon、应用图标）使用，见 index.html。
  -->
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 32 32"
    fill="none"
    role="img"
    :aria-label="label"
  >
    <title>{{ label }}</title>
    <rect v-if="chip" x="1" y="1" width="30" height="30" rx="8" :fill="chipColor" />
    <path
      d="M16 4.2 L26.22 10.1 L26.22 21.9 L16 27.8 L5.78 21.9 L5.78 10.1 Z"
      :stroke="foreground"
      :stroke-width="2.4"
      stroke-linejoin="round"
    />
    <path
      d="M21.8 16 L18.9 21.02 L13.1 21.02 L10.2 16 L13.1 10.98 L18.9 10.98 Z"
      :stroke="accent"
      :stroke-width="2.1"
      stroke-linejoin="round"
    />
    <circle cx="16" cy="16" r="2.3" :fill="foreground" />
  </svg>
</template>

<script setup>
/**
 * 品牌标记。
 *
 * @prop size       渲染尺寸（px）。侧边栏 30，登录页 38。
 * @prop foreground 主色。深色底传 #FFFFFF，浅色底用默认品牌墨黑。
 * @prop accent     辅色（光圈叶片）。深色底用浅灰，浅色底用深灰以保证对比度。
 * @prop chip       是否绘制圆角底板。默认 false（裸字形）。
 * @prop chipColor  底板色。
 */
defineProps({
  size: { type: [Number, String], default: 30 },
  foreground: { type: String, default: '#1C1917' },
  accent: { type: String, default: '#6B7280' },
  chip: { type: Boolean, default: false },
  chipColor: { type: String, default: '#1C1917' },
  label: { type: String, default: '显影 Latent' },
})
</script>
