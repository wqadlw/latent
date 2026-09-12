// 构建后无头冒烟测试
// 遍历所有路由，用系统 Edge（playwright-core channel: 'msedge'，无需下载浏览器）加载，
// 收集运行时错误（pageerror / console.error）。任一路由出现未捕获异常即视为失败并退出码 1。
//
// 用法：
//   先启动后端（uvicorn 或打包后的 PromptMatrix.exe），确保 http://127.0.0.1:8765 可访问，
//   再运行：  node scripts/smoke.mjs
//   或：      npm run build:check   （= vite build && node scripts/smoke.mjs）
// 可用 SMOKE_URL 环境变量覆盖目标地址，如 SMOKE_URL=http://localhost:3000 node scripts/smoke.mjs

import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'

// 所有一级路由（Layout 下的子路由）
const ROUTES = [
  '/dashboard',
  '/production',
  '/content',
  '/brand-asset',
  '/industry',
  '/platform',
  '/knowledge',
  '/keyword',
  '/prompt-library',
  '/rule',
  '/persona',
  '/intent-question',
  '/geo-canvas',
  '/geo-monitor',
  '/browser-studio',
  '/automation-studio',
]

// 已知可忽略的良性报错（网络/资源类），避免误报
const IGNORE = [/favicon/i, /Failed to load resource.*404/i]

function isIgnorable(text) {
  return IGNORE.some((re) => re.test(text))
}

async function main() {
  let browser
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true })
  } catch (e) {
    console.error('无法启动浏览器（playwright-core + 系统 Edge）。请确认已安装 Microsoft Edge。')
    console.error('错误详情：', e.message)
    process.exit(2)
  }

  const page = await browser.newPage()
  const errors = []
  let hadFatal = false

  page.on('pageerror', (err) => {
    errors.push(`[pageerror] ${err.message}`)
  })
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      if (!isIgnorable(text)) errors.push(`[console.error] ${text}`)
    }
  })

  console.log(`冒烟测试目标：${BASE}\n`)
  for (const r of ROUTES) {
    errors.length = 0
    try {
      await page.goto(BASE + r, { waitUntil: 'networkidle', timeout: 25000 })
    } catch (e) {
      console.log(`✗ ${r}  导航失败: ${e.message}`)
      hadFatal = true
      continue
    }
    // 等待组件 setup 执行完，捕捉异步报错
    await page.waitForTimeout(700)
    if (errors.length) {
      console.log(`✗ ${r}  发现 ${errors.length} 个运行时错误:`)
      errors.forEach((line) => console.log('    ' + line))
      hadFatal = true
    } else {
      console.log(`✓ ${r}`)
    }
  }

  await browser.close()

  if (hadFatal) {
    console.log('\n❌ 冒烟测试失败：存在运行时错误，请检查上方输出。')
    process.exit(1)
  }
  console.log('\n✅ 冒烟测试通过：所有路由加载无运行时错误。')
  process.exit(0)
}

main()
