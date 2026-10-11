// 构建后无头冒烟测试
// 遍历所有路由，用系统 Edge（playwright-core channel: 'msedge'，无需下载浏览器）加载，
// 收集运行时错误（pageerror / console.error）。任一路由出现未捕获异常即视为失败并退出码 1。
//
// 会先登录并把令牌写进 localStorage —— 否则路由守卫会把每条路由都重定向到 /login，
// 冒烟测试将只是反复渲染登录页，页面组件根本没被执行（假绿）。
//
// 用法：
//   先启动后端（uvicorn 或打包后的 Latent.exe），确保 http://127.0.0.1:8765 可访问，
//   再运行：  node scripts/smoke.mjs
//   或：      npm run build:check   （= vite build && node scripts/smoke.mjs）
// 可用 SMOKE_URL 环境变量覆盖目标地址，如 SMOKE_URL=http://localhost:3000 node scripts/smoke.mjs
// 账号可用 SMOKE_USER / SMOKE_PASS 覆盖（默认 admin / admin123）。
// 若后端不可达或登录失败，则退化为未登录模式（仅验证登录页可加载）并给出警告。

import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'
const USER = process.env.SMOKE_USER || 'admin'
const PASS = process.env.SMOKE_PASS || 'admin123'

// 所有一级路由（Layout 下的子路由）
// 所有一级路由（Layout 下的子路由）。
// ⚠️ 这份清单必须覆盖侧边栏的全部链接 —— 下面 assertSmokeCoversMenu() 会强制校验，
// 缺一条就直接失败。历史教训：D7 之前这里只有 19 条，静默漏掉
// /prompt-center、/settings、/publish、/manual 四条从未被冒烟访问过。
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
  '/prompt-center',
  '/rule',
  '/settings',
  '/geo-canvas',
  '/persona',
  '/intent-question',
  '/geo-monitor',
  '/geo-visibility',
  '/geo-loop',
  '/pipeline',
  '/publish',
  '/browser-studio',
  '/automation-studio',
  '/manual',
]

// 已知可忽略的良性报错（网络/资源类），避免误报
const IGNORE = [/favicon/i, /Failed to load resource.*404/i]

function isIgnorable(text) {
  return IGNORE.some((re) => re.test(text))
}

// 登录并返回 { token, user }；失败返回 null（退化为未登录模式）
async function login() {
  try {
    const res = await fetch(`${BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: USER, password: PASS }),
    })
    const body = await res.json()
    if (body.code !== 0) {
      console.warn(`⚠ 登录失败（${body.msg || body.code}），将以未登录模式运行，页面组件不会被真正渲染。`)
      return null
    }
    return { token: body.data.token, user: body.data.user }
  } catch (e) {
    console.warn(`⚠ 无法登录（${e.message}），将以未登录模式运行。`)
    return null
  }
}

/**
 * 侧边栏里的每个链接都必须在 ROUTES 里出现，否则冒烟测试存在覆盖盲区。
 * 这里刻意**不**反过来要求 ROUTES ⊆ 侧边栏 —— 有些页面可能刻意不进菜单但仍需冒烟。
 */
async function assertSmokeCoversMenu(page) {
  await page.goto(BASE + '/dashboard', { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForTimeout(900)
  const navPaths = await page.evaluate(() =>
    [...document.querySelectorAll('.nav-item')].map((el) => el.getAttribute('href')).filter(Boolean),
  )
  if (!navPaths.length) {
    console.log('✗ 侧边栏未渲染出任何菜单项（.nav-item = 0），无法校验冒烟覆盖度。')
    process.exit(1)
  }
  const missing = navPaths.filter((p) => !ROUTES.includes(p))
  if (missing.length) {
    console.log(`✗ 冒烟清单存在覆盖盲区，以下侧边栏页面从未被测试：${missing.join(', ')}`)
    process.exit(1)
  }
  console.log(`冒烟覆盖度校验通过：侧边栏 ${navPaths.length} 个链接全部在清单内。`)
}

async function main() {
  const auth = await login()
  if (auth) console.log(`已登录：${auth.user.username}（${auth.user.role}），将按真实页面渲染。\n`)

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

  // 注入令牌，否则每条路由都会被守卫重定向到 /login
  if (auth) {
    await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
    await page.evaluate(
      ([t, u]) => {
        localStorage.setItem('acm_token', t)
        localStorage.setItem('acm_user', JSON.stringify(u))
      },
      [auth.token, auth.user],
    )
  }

  // 守卫：冒烟清单必须覆盖侧边栏里的每一个链接。
  // 侧边栏由 router 派生（src/constants/menu.js），所以它就是「用户能到达的页面」的运行时真源；
  // 上面这份手写的 ROUTES 只是缓存。少了页面却不报错，就是「假绿」——
  // 页面从未被访问过，却显示「全部通过」。
  await assertSmokeCoversMenu(page)

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
    // 未登录模式下若被重定向到 /login，说明这条路由没被真正验证
    if (!auth && page.url().includes('/login')) {
      console.log(`- ${r}  （未登录，重定向到登录页，未验证）`)
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
