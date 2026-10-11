// 截图 /pipeline 流水线工作台（Phase C 视觉验收）
// 用法：node scripts/shot-pipeline.mjs
// 依赖：后端已在 8765 运行，且已执行 scripts/seed_pipeline_demo.py 播种演示批次。

import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'
const OUT = process.env.OUT_DIR || '../docs/screenshots'
const USER = process.env.SEED_USER || 'admin'
const PASS = process.env.SEED_PASS || 'admin123'

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

  // 注入令牌后再进入应用，跳过登录页
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
  await page.evaluate(
    ([t, u]) => {
      localStorage.setItem('acm_token', t)
      localStorage.setItem('acm_user', JSON.stringify(u))
      localStorage.setItem('currentIndustryId', '1') // 演示批次属于行业 1
    },
    [token, user],
  )

  await page.goto(BASE + '/pipeline', { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForTimeout(2500) // 等队列/批次接口回来并渲染

  const errs = []
  page.on('pageerror', (e) => errs.push(e.message))

  await page.screenshot({ path: `${OUT}/C-流水线工作台.png`, fullPage: true })
  console.log(`✓ 已保存 ${OUT}/C-流水线工作台.png`)

  // 页面滚动发生在内层 .content 容器（非 body），滚动到批次区再截一张
  await page.evaluate(() => {
    const el = document.querySelector('.content')
    if (el) el.scrollTop = el.scrollHeight
  })
  await page.waitForTimeout(800)
  await page.screenshot({ path: `${OUT}/C-流水线工作台-批次区.png` })
  console.log(`✓ 已保存 ${OUT}/C-流水线工作台-批次区.png`)

  if (errs.length) console.log('运行时错误：', errs)
  await browser.close()
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
