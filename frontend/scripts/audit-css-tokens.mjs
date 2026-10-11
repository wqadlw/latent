// 扫描 src/ 下所有 var(--x) 引用，与 main.css 中定义的 token 比对。
// 目的：找出「引用了但没定义」的 CSS 变量 —— 这些会静默失效（除非写了 fallback）。
// 用法：node scripts/audit-css-tokens.mjs
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, extname } from 'node:path'

const SRC = 'src'
const TOKEN_FILES = ['src/styles/main.css', 'src/styles/element-overrides.css']

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) walk(p, out)
    else if (['.vue', '.css', '.js', '.ts'].includes(extname(p))) out.push(p)
  }
  return out
}

// 1) 收集已定义 token
const defined = new Set()
for (const f of TOKEN_FILES) {
  const css = readFileSync(f, 'utf8')
  for (const m of css.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gim)) defined.add(m[1])
}

// 1b) 收集「运行时注入」的局部变量。
// 这类变量不在样式表里定义，而是组件通过 :style="{ '--x': value }" 就地注入，
// 属于合法用法（作用域绑定到该元素），扫描时必须排除，否则是误报。
const runtimeInjected = new Set()
for (const f of walk(SRC)) {
  const src = readFileSync(f, 'utf8')
  for (const m of src.matchAll(/['"](--[a-z0-9-]+)['"]\s*:/gi)) runtimeInjected.add(m[1])
}

// 1c) Element Plus 运行时注入的自有变量（--el-*），同理排除
const isThirdParty = (tok) => tok.startsWith('--el-')

// 2) 收集引用（区分有无 fallback）
const used = new Map() // token -> [{file, line, hasFallback}]
for (const f of walk(SRC)) {
  const lines = readFileSync(f, 'utf8').split('\n')
  lines.forEach((line, i) => {
    for (const m of line.matchAll(/var\(\s*(--[a-z0-9-]+)\s*(,)?/gi)) {
      const tok = m[1]
      const hasFallback = !!m[2]
      if (!used.has(tok)) used.set(tok, [])
      used.get(tok).push({ file: f.replace(/\\/g, '/'), line: i + 1, hasFallback })
    }
  })
}

const missing = []
for (const [tok, refs] of used) {
  if (defined.has(tok)) continue
  if (runtimeInjected.has(tok)) continue // 运行时注入，合法
  if (isThirdParty(tok)) continue        // Element Plus 自有
  const noFallback = refs.filter(r => !r.hasFallback)
  missing.push({ tok, total: refs.length, broken: noFallback.length, refs })
}
missing.sort((a, b) => b.broken - a.broken || b.total - a.total)

console.log(`已定义 token：${defined.size} 个`)
console.log(`被引用 token：${used.size} 个`)
console.log(`运行时注入（已排除）：${[...runtimeInjected].join(', ') || '无'}`)
console.log(`未定义且非注入：${missing.length} 个\n`)

const brokenTotal = missing.filter(m => m.broken > 0)
console.log(`【A】未定义且无 fallback —— 静默失效，共 ${brokenTotal.length} 个 token：`)
for (const m of brokenTotal) {
  const files = [...new Set(m.refs.filter(r => !r.hasFallback).map(r => r.file))]
  console.log(`  ${m.tok.padEnd(18)} 无fallback引用 ${String(m.broken).padStart(3)} 处 / 共 ${String(m.total).padStart(3)} 处  → ${files.slice(0, 4).join(', ')}${files.length > 4 ? ` 等 ${files.length} 文件` : ''}`)
}

const onlyFallback = missing.filter(m => m.broken === 0)
if (onlyFallback.length) {
  console.log(`\n【B】未定义但有 fallback —— 能显示，但语义已漂移，共 ${onlyFallback.length} 个：`)
  console.log('  ' + onlyFallback.map(m => m.tok).join(', '))
}

// 3) 反向：定义了但从未被引用的 token
const unused = [...defined].filter(t => !used.has(t))
if (unused.length) {
  console.log(`\n【C】已定义但未被引用，共 ${unused.length} 个：`)
  console.log('  ' + unused.join(', '))
}

// 退出码 = 门禁。
// A 类（未定义且无 fallback）必须为 0：这类声明会被浏览器整条丢弃、静默回退到继承色，
// 不报错也不警告，靠人眼 review 基本抓不到 —— 只能靠这里拦。
// B/C 类**不作为门禁**：B 类有 fallback、能显示；C 类里的完整色阶
// （--red-* / --amber-* / --emerald-* 各 7 档）是刻意保留的设计系统资产，
// 要求「引用数=定义数」只会逼人删掉色阶，反而更差。
if (brokenTotal.length > 0) {
  console.error(`\n❌ 存在 ${brokenTotal.length} 个静默失效的设计令牌（A 类），必须在 styles/main.css 补齐。`)
  process.exit(1)
}
console.log('\n✅ 无静默失效的设计令牌（A 类 = 0）。')
