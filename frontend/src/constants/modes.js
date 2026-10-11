/**
 * 生成模式（publish_mode）→ 中文文案的单一真源。
 *
 * 这套文案原本散在 5 处，且**已经漂移**：
 *   - 浏览器工作室的新建向导：'官网 MDX'（带空格）
 *   - 对话面板：'官网MDX'（不带空格）
 *   - 浏览器工作室列表：'geo 强品牌'
 *   - 对话面板：'强品牌/GEO'
 * 同一个模式在两页显示成两个词，用户会以为它们是不同的东西。
 *
 * 与 constants/platforms.js 的关系：平台（sohu/zhihu/…）决定**发到哪**，
 * 模式（geo/platform/green/official）决定**怎么产**。platforms.js 里每个平台带
 * 一个 `mode` 字段，就是用它来推导本文件的取值。
 *
 * ⚠️ 「官网 MDX」既是一个模式（official），也是一种产出形态（output_format === 'mdx'）。
 * 后端对官网运行会强制 geo + mdx，所以展示时 output_format 优先——
 * 这个判断在 constants/browserStudio.js 的 runModeTag() 里，不要在这里重复。
 */

export const MODE_LABEL = {
  geo: '强品牌/GEO',
  platform: '平台合规',
  green: '绿色吸粉',
  official: '官网 MDX',
}

/**
 * 模式 → 中文。
 *
 * @param {string} mode
 * @param {Array}  [list]  接口返回的 modes 列表（[{value,label}]）。
 *                         传了就优先用服务端的文案——服务端是权威，
 *                         本地 MODE_LABEL 只是「接口还没回来」时的兜底。
 */
export function modeLabel(mode, list) {
  if (list && list.length) {
    const hit = list.find((x) => x && x.value === mode)
    if (hit?.label) return hit.label
  }
  return MODE_LABEL[mode] || mode || '—'
}

/**
 * 模式 → 徽标样式类（Manual.vue / AutomationStudio.vue 里那套 .m-* 类名）。
 * 这两个视图各写了一份逐字相同的映射，属于典型的「复制粘贴后忘了合并」——
 * 将来加一个新模式，只改一处就会让两个页面的徽标颜色不一致。
 */
export const MODE_TAG_CLASS = {
  geo: 'm-geo',
  platform: 'm-platform',
  green: 'm-green',
  official: 'm-official',
}

/** 未知模式回退到 geo 的样式，保证徽标不丢底色。 */
export const modeTagClass = (m) => MODE_TAG_CLASS[m] || 'm-geo'
