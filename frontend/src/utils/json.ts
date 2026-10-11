/**
 * JSON 字段的安全解析 —— 全站统一实现。
 *
 * 后端有若干列是「JSON 文本」而非结构化列（`production_task.target_needs`、
 * `illustration_plan`、`platform.config`、`prompt_library.variable_schema`…）。
 * 这些值有三种可能：合法 JSON、历史遗留的坏数据、前端自己刚写进去的对象。
 * 每处各写一遍 `try { JSON.parse } catch {}` 的结果是**回退行为不一致**：
 * 有的回退 `null`、有的回退 `{}`、有的直接抛出去把整页炸掉。
 */

/**
 * 解析 JSON，失败或空值时返回 `fallback`。
 *
 * @param value    原始值（可能是字符串、已经是对象、null/undefined）
 * @param fallback 解析失败时的返回值
 */
export function safeJsonParse<T>(value: unknown, fallback: T): T {
  if (value === null || value === undefined || value === '') return fallback
  if (typeof value !== 'string') return value as T
  try {
    const parsed = JSON.parse(value)
    return parsed === null || parsed === undefined ? fallback : (parsed as T)
  } catch {
    return fallback
  }
}

/**
 * 把「本该是数组的 JSON 字段」解析成数组。
 *
 * ⚠️ 与裸 `JSON.parse` 的区别：解析出**非数组**时返回 `[]` 而不是原样返回。
 * 调用方拿到结果后普遍会 `.filter(...)` / `.map(...)`，
 * 若把对象原样放行，会在渲染期抛 `TypeError`，把整个页面炸成白屏 ——
 * 而这类脏数据完全可能来自历史版本或手工改库。
 */
export function parseJsonArray<T = unknown>(value: unknown): T[] {
  const parsed = safeJsonParse<unknown>(value, null)
  return Array.isArray(parsed) ? (parsed as T[]) : []
}
