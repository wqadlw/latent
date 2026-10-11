/**
 * 侧边栏菜单的**唯一来源**：路由表。
 *
 * 为什么要有这个文件：
 *   在 D7 之前，`Layout.vue` 里有一份**手工维护**的 `menuGroups`（23 项），
 *   而 `router/index.js` 的 `meta` 是另一份。两份事实必然漂移，实测已经漂了：
 *     - 组顺序不同（路由里「发布自动化」在「GEO 作战」之前，菜单里在之后）
 *     - `/publish` 的标题不同（meta 写「发布自动化」，菜单写「发布中心」）
 *   更糟的是 `/publish` 的 `meta.group` 也叫「发布自动化」，于是顶栏渲染成
 *   「发布自动化 / 发布自动化」——组名与标题一模一样，层级感消失。
 *
 * 现在的契约：
 *   想改菜单？**只改 `router/index.js` 的 `meta`**。改标题改 `meta.title`，
 *   改分组改 `meta.group`，改徽标改 `meta.badge`，改顺序就调整路由的声明顺序。
 *   这个文件里**不允许**出现任何菜单文案字面量。
 *
 * 组顺序 = 路由声明顺序（首次出现的顺序），不额外维护排序表 ——
 * 与 vue-element-admin 的做法一致（侧边栏完全由路由派生）。
 * 想调组顺序，就在 `router/index.js` 里把路由块挪一下位置。
 */

/**
 * 把 `router.getRoutes()` 的扁平记录列表整理成侧边栏分组。
 *
 * @param {Array<{path: string, meta?: object}>} routes
 *        `router.getRoutes()` 的返回值。注意它返回的是**扁平化**的记录，
 *        且子路由的 `path` 已经是**完整路径**（如 `/dashboard`），
 *        不需要再做父子拼接。
 * @returns {Array<{title: string, items: Array<{path: string, title: string, icon: string, badge: string}>}>}
 */
export function buildMenuGroups(routes) {
  const groups = []
  const byTitle = new Map()

  for (const route of routes || []) {
    const meta = route.meta || {}

    // 不进菜单的三类记录：
    //   1) 没有 meta.group —— 登录页、Layout 壳（`/`）、以及任何刻意不进菜单的页面
    //   2) meta.hidden —— 显式声明隐藏（404 兜底页）
    //   3) 带参数的通配路径 —— `:pathMatch(.*)*`，它没有稳定的可点击地址
    if (!meta.group || meta.hidden) continue
    if (!route.path || route.path.includes(':')) continue

    let group = byTitle.get(meta.group)
    if (!group) {
      group = { title: meta.group, items: [] }
      byTitle.set(meta.group, group)
      groups.push(group)
    }

    group.items.push({
      path: route.path,
      // meta.title 缺失时回落到路径本身，而不是静默产出空标题（空标题在侧边栏里
      // 就是一个只有图标的空行，肉眼很难发现，属于「静默失效」）
      title: meta.title || route.path,
      icon: meta.icon || '',
      badge: meta.badge || '',
    })
  }

  return groups
}
