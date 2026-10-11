// 浏览器工作室（D4 拆分）的视觉验收。
//
// 每拆出一块就跑一次，确认「拆出来的组件长得和拆之前一样」。
// 这是 D4 唯一能证明「样式没跟着标记一起丢」的手段——
// smoke.mjs 只抓运行时错误，抓不到「组件渲染了但样式没了」。
//
// 用法：node scripts/shot-studio.mjs
// 依赖：后端已在 8765 运行。

import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'
const OUT = process.env.OUT_DIR || '../docs/screenshots'
const USER = process.env.SMOKE_USER || 'admin'
const PASS = process.env.SMOKE_PASS || 'admin123'

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
  page.on('pageerror', (e) => errs.push('[pageerror] ' + e.message))
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

  await page.goto(BASE + '/browser-studio', { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForTimeout(2500)
  await page.screenshot({ path: `${OUT}/D4-工作室-主视图.png`, fullPage: true })
  console.log(`✓ 主视图 → ${OUT}/D4-工作室-主视图.png`)

  // 运行列表里的模式徽标是 `.tag-mode.mode-chip`，配色同样来自 studio-shared.css。
  // 壳一度漏 import 这张表 —— 那样徽标会退化成没有底色的裸文字（截图里很难肉眼分辨），
  // 所以这里直接量计算样式。
  const tagChips = await page.$$eval('.tag-mode.mode-chip', (els) =>
    els.map((e) => ({ text: e.textContent.trim(), bg: getComputedStyle(e).backgroundColor })),
  )
  if (tagChips.length) {
    console.log('  运行列表模式徽标：')
    for (const c of tagChips) console.log(`    ${c.text.padEnd(8)} bg=${c.bg}`)
  } else {
    console.log('  （无运行记录，跳过运行列表徽标测量）')
  }

  // 新建运行向导（5 步，已抽到 CreateRunDialog.vue）
  // 这一步同时验证两件事：① 拆出来的向导还能打开；② 平台卡片上的 `.pick-mode.mode-chip`
  // 四色是否真的生效（`.m-green` 曾经漏写，合并进 studio-shared.css 后才补齐）。
  const createBtn = page.getByRole('button', { name: '新建运行' }).first()
  if (await createBtn.count()) {
    await createBtn.click({ timeout: 5000 })
    await page.waitForTimeout(1800)
    await page.screenshot({ path: `${OUT}/D4-工作室-新建向导.png`, fullPage: true })
    console.log(`✓ 新建向导 → ${OUT}/D4-工作室-新建向导.png`)

    // 量一下平台卡片模式角标的实际底色：若共享样式没生效，会退化成透明。
    const chips = await page.$$eval('.pick-mode.mode-chip', (els) =>
      els.map((e) => ({
        text: e.textContent.trim(),
        cls: e.className,
        bg: getComputedStyle(e).backgroundColor,
        color: getComputedStyle(e).color,
      })),
    )
    console.log('  平台卡片模式角标：')
    for (const c of chips) console.log(`    ${c.text.padEnd(8)} bg=${c.bg} color=${c.color}`)

    await page.keyboard.press('Escape')
    await page.waitForTimeout(600)
  } else {
    console.log('⚠ 没找到「新建运行」按钮，跳过向导截图')
  }

  // 文章改写弹窗：点顶部横幅打开（横幅在壳里，弹窗在 RewriteDialog.vue）
  const banner = page.getByText('文章改写模式', { exact: true }).first()
  if (await banner.count()) {
    await banner.click({ timeout: 5000 })
    await page.waitForTimeout(1200)
    await page.screenshot({ path: `${OUT}/D4-工作室-改写弹窗.png` })
    console.log(`✓ 改写弹窗 → ${OUT}/D4-工作室-改写弹窗.png`)
    await page.keyboard.press('Escape')
    await page.waitForTimeout(600)
  } else {
    console.log('⚠ 没找到「文章改写模式」横幅，跳过弹窗截图')
  }

  // 运行详情：点第一条运行
  const firstRun = page.locator('.run-card').first()
  if (await firstRun.count()) {
    await firstRun.click({ timeout: 5000 })
    await page.waitForTimeout(2000)
    await page.screenshot({ path: `${OUT}/D4-工作室-运行详情.png`, fullPage: true })
    console.log(`✓ 运行详情 → ${OUT}/D4-工作室-运行详情.png`)

    // 断言「详情面板真的渲染了内容」而不是退化成空状态。
    // 光看截图不够：RunDetailPanel 拆出去后若 `run` 没传进来，页面会静默显示
    // 「选择左侧运行查看详情」—— 那也是一张「正常」的截图。
    const probe = await page.evaluate(() => ({
      empty: document.querySelectorAll('.run-detail--empty').length,
      detail: document.querySelectorAll('.run-detail:not(.run-detail--empty)').length,
      steps: document.querySelectorAll('.run-detail .step').length,
      title: (document.querySelector('.detail-title') || {}).textContent || '',
      hasPipeline: !!document.querySelector('.run-detail .pipeline'),
      hasTabs: !!document.querySelector('.run-detail .studio-tabs'),
      hasRoundCards: document.querySelectorAll('.run-detail .round-card').length,
      hasFinalBlock: !!document.querySelector('.run-detail .result-block, .run-detail .result-empty'),
    }))
    console.log('  详情面板断言：')
    console.log(`    非空详情容器=${probe.detail}  空状态容器=${probe.empty}`)
    console.log(`    流水线步骤数=${probe.steps}  pipeline=${probe.hasPipeline}  tabs=${probe.hasTabs}`)
    console.log(`    逐轮产出卡片=${probe.hasRoundCards}  终稿区=${probe.hasFinalBlock}`)
    console.log(`    标题=${JSON.stringify(probe.title)}`)
    if (probe.detail !== 1 || probe.empty !== 0 || probe.steps === 0 || !probe.hasPipeline) {
      console.log('  ❌ 详情面板断言失败：面板没有渲染出应有的结构')
      process.exitCode = 1
    } else {
      console.log('  ✅ 详情面板结构完整')
    }

    // 预检弹窗：点「满意，加入内容中心」（需要该运行已有终稿）
    const confirmBtn = page.getByRole('button', { name: /加入内容中心/ }).first()
    if (await confirmBtn.count()) {
      await confirmBtn.click({ timeout: 5000 })
      await page.waitForTimeout(2500)
      await page.screenshot({ path: `${OUT}/D4-工作室-预检弹窗.png` })
      console.log(`✓ 预检弹窗 → ${OUT}/D4-工作室-预检弹窗.png`)
      await page.keyboard.press('Escape')
      await page.waitForTimeout(600)
    } else {
      console.log('⚠ 没有「加入内容中心」按钮，跳过预检弹窗截图')
    }

    // 创作对话页签：验证 ConversationPanel 的双重解包修复（修前恒为空）
    const convTab = page.getByText('创作对话', { exact: false }).first()
    if (await convTab.count()) {
      await convTab.click({ timeout: 5000 })
      await page.waitForTimeout(2000)
      await page.screenshot({ path: `${OUT}/D4-工作室-创作对话.png`, fullPage: true })
      console.log(`✓ 创作对话 → ${OUT}/D4-工作室-创作对话.png`)
    } else {
      console.log('⚠ 没找到「创作对话」页签')
    }
  } else {
    console.log('⚠ 没有运行记录，跳过详情截图')
  }

  if (errs.length) {
    console.log('\n运行时错误：')
    errs.forEach((e) => console.log('  ' + e))
    process.exitCode = 1
  } else {
    console.log('\n无运行时错误。')
  }
  await browser.close()
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
