// 阶段 D · D2 地基修复的视觉验收：截取本次改动涉及的三个视图。
//
// 改了什么 → 要看什么：
//   /keyword    选题卡片的「状态」标签改走 constants/status.js（processing 由灰变橙）
//   /content    运营日历 chip 的状态文案 + 未排期列表的状态文案
//   /dashboard  最近任务的「状态」标签 + 时间列（由 2026-10-11T11:30 变成 2026-10-11 11:30）
//
// 用法：node scripts/shot-d2.mjs
// 依赖：后端已在 8765 运行。

import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'
const OUT = process.env.OUT_DIR || '../docs/screenshots'
const USER = process.env.SMOKE_USER || 'admin'
const PASS = process.env.SMOKE_PASS || 'admin123'

const PAGES = [
  // /keyword 默认落在「关键词库」页签（本地为空），选题状态标签在「选题池」里
  { path: '/keyword', file: 'D2-关键词-选题状态标签.png', clickText: '选题池' },
  // /content 默认落在「内容审核」页签（本地库为空时是一片空白），
  // 必须点进「运营中心」才能看到运营日历的状态 chip
  { path: '/content', file: 'D2-内容中心-运营日历.png', clickText: '运营中心' },
  { path: '/dashboard', file: 'D2-仪表盘-任务状态与时间.png' },
]

async function login() {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  })
  const body = await res.json()
  if (body.code !== 0) throw new Error('登录失败：' + JSON.stringify(body))
  return { token: body.data.token, user: body.data.user }
}

async function main() {
  const { token, user } = await login()
  console.log(`登录成功：${user.username}（${user.role}）`)

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })

  const errs = []
  page.on('pageerror', (e) => errs.push(e.message))
  page.on('console', (m) => {
    if (m.type() === 'error') errs.push('[console] ' + m.text())
  })

  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
  await page.evaluate(
    ([t, u]) => {
      localStorage.setItem('acm_token', t)
      localStorage.setItem('acm_user', JSON.stringify(u))
      localStorage.setItem('currentIndustryId', '1')
    },
    [token, user],
  )

  for (const p of PAGES) {
    await page.goto(BASE + p.path, { waitUntil: 'networkidle', timeout: 30000 })
    await page.waitForTimeout(1500)
    if (p.clickText) {
      const tab = page.getByText(p.clickText, { exact: true }).first()
      await tab.click({ timeout: 5000 })
      await page.waitForTimeout(1500)
    }
    await page.screenshot({ path: `${OUT}/${p.file}`, fullPage: true })
    console.log(`✓ ${p.path} → ${OUT}/${p.file}`)
  }

  if (errs.length) {
    console.log('\n运行时错误：')
    errs.forEach((e) => console.log('  ' + e))
  } else {
    console.log('\n无运行时错误。')
  }
  await browser.close()
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
