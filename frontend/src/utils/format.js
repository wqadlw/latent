/**
 * 日期时间格式化 —— 全站统一实现。
 *
 * 为什么集中：此前同一件事在 8 个文件里有至少 5 种写法
 * （`t.slice(0,16)`、`toLocaleString('zh-CN')` 的三种参数组合、自写 `fmtDate`…）。
 * 重复本身不是最大问题，**不一致**才是：同一个时间戳在不同页面显示成不同样子，
 * 用户会怀疑数据不对。
 *
 * ⚠️ 关键设计决策：`formatDateTime` 用**字符串解析**而不是 `new Date()`。
 * 后端的 create_time 是 SQLAlchemy 的 naive DateTime，序列化成 `2026-10-11T11:30:00`
 * （无时区后缀）。用 `new Date()` 解析会走本地时区——目前恰好等价，
 * 但只要将来后端改带 `Z`（UTC），所有时间会集体偏移 8 小时。
 * 字符串截取没有这个隐患，且与重构前的显示逐字一致。
 */

/** 把入参安全地转成 Date；无效返回 null */
function toDate(value) {
  if (!value) return null
  const d = value instanceof Date ? value : new Date(value)
  return isNaN(d.getTime()) ? null : d
}

/**
 * `2026-10-11 11:30` —— 列表、卡片里的默认时间显示。
 * 输入 `2026-10-11T11:30:00` 或带空格的形式均可。
 */
export function formatDateTime(value, fallback = '—') {
  if (!value) return fallback
  const s = String(value)
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/)
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : s
}

/** `10-11 11:30` —— 空间紧张时省略年份（仪表盘等） */
export function formatMonthDay(value, fallback = '—') {
  const d = toDate(value)
  if (!d) return fallback
  return d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

/** `10-11` —— 只要月日 */
export function formatShortDate(value, fallback = '—') {
  const d = toDate(value)
  if (!d) return fallback
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit' })
}

/**
 * `2026/10/11 11:30:00` —— 需要精确到秒的场合（版本历史等）。
 * 固定 24 小时制：中文环境下默认会渲染成「上午11:30:00」，混排时不整齐。
 */
export function formatFullDateTime(value, fallback = '—') {
  const d = toDate(value)
  if (!d) return fallback
  return d.toLocaleString('zh-CN', { hour12: false })
}

/** Date → `2026-10-11`（用于文件名、日期 key，不做本地化） */
export function toDateKey(date) {
  const d = toDate(date)
  if (!d) return ''
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** 日期加减天数，返回新 Date（不修改入参） */
export function addDays(date, n) {
  const d = toDate(date)
  if (!d) return null
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}
