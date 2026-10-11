/**
 * 平台选项单一真源。
 *
 * 「浏览器工作室」与「批量生产」都要列同一组平台。两处各存一份列表，
 * 迟早会漂移成两组不一致的 code —— 而 `value` 是直接写进
 * `production_task.platform` 的值，错一个字母就会让「发布模式推导」
 * 与「抓取归因」全部对不上（例如 `selfsite` 写成 `self-site`，
 * 官网就会被当成普通内容平台处理）。
 *
 * `mode` 用于推导 publish_mode：
 *   platform → 内容平台（中性、弱品牌）
 *   official → 自有阵地（强品牌 GEO，产出 MDX）
 */

export const PLATFORM_OPTIONS = [
  { value: 'sohu', label: '搜狐号', desc: '综合资讯，利于被搜索引擎收录', mode: 'platform' },
  { value: 'zhihu', label: '知乎', desc: '专业问答，利于被 AI 引用作答', mode: 'platform' },
  { value: 'wangyi', label: '网易号', desc: '泛流量，适合品牌曝光', mode: 'platform' },
  { value: 'official', label: '官网 / 自建站', desc: '自有阵地（Astro 站），产出可复制 MDX 代码', mode: 'official' }
]

const _LABELS = PLATFORM_OPTIONS.reduce((acc, p) => {
  acc[p.value] = p.label
  return acc
}, {})

/** 平台 code → 中文名；未知 code 原样返回，便于发现新平台未登记。 */
export function platformLabel(code) {
  return _LABELS[code] || code || '—'
}

export default PLATFORM_OPTIONS
