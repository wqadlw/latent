/**
 * 「列表里按 id 找名称」——全站统一实现。
 *
 * 这段逻辑在 10 个文件里被抄了 10 遍（getPlatformName / getAccountName /
 * getPersonaName / getCategoryName…），而且抄出了 3 种回退行为：
 *   有的返回 `'—'`、有的返回 `''`、有的返回 `平台#3`。
 * 同一个「账号已删除」的情况，在资产页显示「—」，在生产页显示空白，
 * 用户看到的是「这里没数据」和「这里坏了」两种感受。
 *
 * 统一的回退是 `'—'`（明确的「没有」），需要别的回退就显式传 fallback
 * （`Production.vue` 就传了 `''`，因为那里是子组件里的内联小字，空串更自然）。
 */

/** 能被 nameById 处理的最小行形状：必须有 id，取名字段可自定义 */
export interface NamedRow {
  id?: number | string | null
  [key: string]: unknown
}

/**
 * 从列表里按 id 取某个字段。
 *
 * @param list              数据源（可以是 ref 解包后的响应式数组）
 * @param id                目标 id；为 null/undefined/'' 时直接返回 fallback
 * @param key               取哪个字段，默认 'name'
 * @param fallback          找不到时的显示值，默认 '—'
 *
 * 为什么空 id 要短路：`''`/`null` 在表单里非常常见（未选择）。
 * 若不做短路，`find` 会拿 `undefined` 去比，一旦列表里恰好有个
 * `id: undefined` 的行就会错配。
 *
 * 返回值统一 `String()` 化：调用方（模板插值、`!== '—'` 比较）只关心文本，
 * 而数据源里的 name 字段类型不受控（可能来自后端 JSON 的数字/布尔）。
 */
export function nameById<T extends NamedRow>(
  list: readonly T[] | null | undefined,
  id: number | string | null | undefined,
  key: string = 'name',
  fallback: string = '—',
): string {
  if (id === null || id === undefined || id === '') return fallback
  const hit = (list || []).find((x) => x && x.id === id)
  const value = hit ? hit[key] : undefined
  // 用 truthy 判断（而非只判 null/undefined）以保持与重构前逐字一致的显示行为
  return value ? String(value) : fallback
}

/**
 * 在「分类 → 行数组」的映射里**跨分类**按 id 找一行。
 *
 * 生产流程的提示词选项就是这种形状：`options.prompts = { outline: [...], draft: [...] }`。
 * 提示词 id 是全局唯一的，但界面上按分类分组展示，所以按 id 反查时必须扫遍所有分类 ——
 * 只看当前分类会在「选了大纲提示词却按初稿分类去查」时静默返回 null。
 *
 * @param map 分类 → 行数组
 * @param id  目标 id
 * @returns   命中的行，找不到返回 null
 */
export function findInCategoryMap<T extends NamedRow>(
  map: Record<string, T[]> | null | undefined,
  id: number | string | null | undefined,
): T | null {
  if (id === null || id === undefined || id === '') return null
  for (const key of Object.keys(map || {})) {
    const hit = (map![key] || []).find((x) => x && x.id === id)
    if (hit) return hit
  }
  return null
}
