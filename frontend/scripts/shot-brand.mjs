// 截图品牌门面（登录页品牌区 + 侧边栏 logo），用于核对 logo 辅色。
// 用法：node scripts/shot-brand.mjs

import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'
const OUT = process.env.OUT_DIR || '../docs/screenshots'

async function login() {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin123' }),
  })
  const body = await res.json()
  if (body.code !== 0) throw new Error('登录失败：' + JSON.stringify(body))
  return body.data
}

const browser = await chromium.launch({ channel: 'msedge', headless: true })

// 1) 登录页（未登录状态）
const p1 = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await p1.goto(BASE + '/login', { waitUntil: 'networkidle', timeout: 30000 })
await p1.waitForTimeout(900)
await p1.screenshot({ path: `${OUT}/品牌-登录页.png` })
console.log(`✓ ${OUT}/品牌-登录页.png`)
await p1.close()

// 2) 侧边栏 logo（登录后）
const { token, user } = await login()
const p2 = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await p2.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
await p2.evaluate(
  ([t, u]) => {
    localStorage.setItem('acm_token', t)
    localStorage.setItem('acm_user', JSON.stringify(u))
  },
  [token, user],
)
await p2.goto(BASE + '/dashboard', { waitUntil: 'networkidle', timeout: 30000 })
await p2.waitForTimeout(1200)
// 只截侧边栏顶部一块，便于看清 30px 的 logo
await p2.screenshot({ path: `${OUT}/品牌-侧边栏.png`, clip: { x: 0, y: 0, width: 240, height: 160 } })
console.log(`✓ ${OUT}/品牌-侧边栏.png`)
await p2.close()

await browser.close()
