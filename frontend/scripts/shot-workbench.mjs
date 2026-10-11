// 阶段 D · D7-2 两栏工作台容器的**布局验收**。
//
// 为什么必须用「计算样式」而不是「截图」或「结构断言」：
//   D7-2 把 5 处各自手写的两栏布局收进 WorkbenchLayout。这个改动最危险的失败模式是
//   **子元素不再撑满栏位** —— 页面照样渲染、没有报错、结构断言（元素存在吗）全绿，
//   但左栏塌成内容宽度、或者主区不再内部滚动。这些只有算出来的几何量能发现。
//
//   特别地：WorkbenchLayout 的槽位包裹元素用了 `display: contents`（不产生盒子），
//   使用方传进来的元素才是真正的网格项。若哪天有人把它改成普通块级盒子，
//   上面**所有**断言依然全绿（元素还在、类名还在），只有「子元素宽度 = 栏宽」会红。
//
// 覆盖（每页两条 + 一条全局）：
//   1. 容器 display:grid，且列轨道 = [栏宽, 剩余]
//   2. 左栏子元素的实际宽度 === 栏宽（证明它是网格项，而不是被包在盒子里）
//   3. 栏间距统一为 16px（D7「各页视觉一致」的验收点）
//   4. 视口收窄到 1024px 以下 → 单列
//
// 用法：node scripts/shot-workbench.mjs
// 依赖：后端已在 8765 运行（脚本自行登录；工作室无运行记录时会造一条带标记的数据并在 finally 清理）。

import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'
const OUT = process.env.OUT_DIR || '../docs/screenshots'
const USER = process.env.SMOKE_USER || 'admin'
const PASS = process.env.SMOKE_PASS || 'admin123'

const MARK = '__D7_WB_VERIFY__'
const INDUSTRY_ID = 1
const GAP = '16px'

// 每页的：路由 / 容器选择器 / 期望栏宽 / 左栏子元素选择器（用于证明它真的占住了栏位）
// `stretch`：该页左栏是否应被拉伸到与容器等高（Knowledge 用 align=start，故为 false）。
// 这一条是 `display: contents` 的直接行为证据 —— 槽位包裹元素一旦变成真实盒子，
// 子元素就不再是网格项，高度会塌成内容高度，而**宽度仍然正确**，只有这条能发现。
const PAGES = [
  { path: '/knowledge', name: '知识库', container: '.kw-layout', rail: '220px', aside: '.category-panel', stretch: false },
  { path: '/keyword', name: '关键词选题', container: '.kw-layout', rail: '232px', aside: '.group-panel', stretch: true },
  { path: '/intent-question', name: '意图问题库', container: '.iq-body', rail: '268px', aside: '.iq-side', stretch: true },
  { path: '/production', name: '软文生产', container: '.prod-layout', rail: '320px', aside: '.task-panel', stretch: true },
  { path: '/browser-studio', name: '浏览器工作室', container: '.studio__body', rail: '300px', aside: '.run-list', stretch: true },
]

let failures = 0
function check(label, ok, detail = '') {
  if (ok) console.log(`  ✓ ${label}`)
  else {
    failures++
    console.log(`  ❌ ${label}${detail ? '  → ' + detail : ''}`)
  }
}

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

/** 走 REST 直连，避免依赖页面（造数/清理必须在页面之外完成） */
async function api(token, path, init = {}) {
  const res = await fetch(BASE + '/api' + path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(init.headers || {}),
    },
  })
  return res.json()
}

/** 浏览器工作室在「没有运行记录」时渲染的是空状态，工作台容器根本不存在 —— 造一条 */
async function seedStudioRun(token) {
  const listed = await api(token, `/browser-studio?industry_id=${INDUSTRY_ID}`)
  const runs = (listed && listed.data) || []
  const mine = runs.filter((r) => r.name === MARK)
  // 幂等：命中已有标记行时不直接返回，而是复用（不新建，避免累积）
  if (mine.length) return { created: false, ids: mine.map((r) => r.id) }
  const created = await api(token, '/browser-studio', {
    method: 'POST',
    body: JSON.stringify({ industry_id: INDUSTRY_ID, name: MARK }),
  })
  if (created.code !== 0) throw new Error('造数失败：' + JSON.stringify(created))
  return { created: true, ids: [created.data.id] }
}

async function cleanupStudioRun(token, ids) {
  for (const id of ids) {
    await api(token, `/browser-studio/${id}`, { method: 'DELETE' })
  }
}

/** 读出容器与左栏子元素的几何量 */
async function measure(page, container, aside) {
  return page.evaluate(
    ([c, a]) => {
      const el = document.querySelector(c)
      if (!el) return { missing: true }
      const cs = getComputedStyle(el)
      const child = a ? el.querySelector(a) : null
      const wrapper = el.firstElementChild
      return {
        missing: false,
        display: cs.display,
        columns: cs.gridTemplateColumns,
        columnGap: cs.columnGap,
        height: el.getBoundingClientRect().height,
        asideWidth: child ? getComputedStyle(child).width : 'no-el',
        asideHeight: child ? child.getBoundingClientRect().height : -1,
        asideFound: !!child,
        // 槽位包裹元素必须不产生盒子，使用方的元素才是真正的网格项
        wrapperDisplay: wrapper ? getComputedStyle(wrapper).display : 'no-el',
      }
    },
    [container, aside],
  )
}

const tracks = (s) => String(s || '').trim().split(/\s+/).filter(Boolean)

async function main() {
  const { token, user } = await login()
  console.log(`登录成功：${user.username}（${user.role}）\n`)

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })

  const warns = []
  page.on('pageerror', (e) => warns.push('[pageerror] ' + e.message))
  page.on('console', (m) => {
    const t = m.text()
    if (m.type() === 'error') warns.push('[console.error] ' + t)
    if (m.type() === 'warning' && /Failed to resolve|is not defined|not defined on instance/.test(t)) {
      warns.push('[console.warn] ' + t.split('\n')[0])
    }
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

  let seeded = { created: false, ids: [] }
  try {
    // seed 放在 try 里面 —— 否则造数中途失败时 finally 的清理不会执行，标记数据会永久残留
    seeded = await seedStudioRun(token)
    console.log(seeded.created ? '已造 1 条浏览器工作室运行（用于渲染工作台容器）\n' : '已有标记运行，复用\n')

    for (const p of PAGES) {
      console.log(`—— ${p.name}（${p.path}）——`)
      await page.setViewportSize({ width: 1600, height: 1000 })
      await page.goto(BASE + p.path, { waitUntil: 'networkidle', timeout: 30000 })
      await page.waitForTimeout(1200)

      const wide = await measure(page, p.container, p.aside)
      if (wide.missing) {
        check(`${p.container} 存在`, false, '容器未渲染')
        console.log('')
        continue
      }

      const t = tracks(wide.columns)
      check(`${p.container} 是 grid 容器`, wide.display === 'grid', `display=${wide.display}`)
      check(
        `列轨道 = [${p.rail}, 剩余]`,
        t.length === 2 && t[0] === p.rail,
        `实际 ${wide.columns}`,
      )
      check(
        `左栏子元素实际宽度 = ${p.rail}（证明它是网格项，没被槽位包裹层挡住）`,
        wide.asideWidth === p.rail,
        `${p.aside} width=${wide.asideWidth}${wide.asideFound ? '' : '（元素未找到）'}`,
      )
      check(`栏间距 = ${GAP}（各页统一）`, wide.columnGap === GAP, `columnGap=${wide.columnGap}`)
      check(
        `槽位包裹元素 display:contents（否则子元素不再是网格项）`,
        wide.wrapperDisplay === 'contents',
        `wrapper display=${wide.wrapperDisplay}`,
      )
      if (p.stretch) {
        check(
          `左栏被拉伸到与容器等高（${Math.round(wide.height)}px）`,
          Math.abs(wide.asideHeight - wide.height) <= 1,
          `左栏高 ${Math.round(wide.asideHeight)}px vs 容器高 ${Math.round(wide.height)}px`,
        )
      }

      // 窄屏：≤1024px 必须退化为单列
      await page.setViewportSize({ width: 1000, height: 1000 })
      await page.waitForTimeout(700)
      const narrow = await measure(page, p.container, p.aside)
      const nt = tracks(narrow.columns)
      check(`≤1024px 退化为单列`, nt.length === 1, `实际 ${narrow.columns}`)

      await page.setViewportSize({ width: 1600, height: 1000 })
      await page.waitForTimeout(600)
      await page.screenshot({ path: `${OUT}/D7-工作台-${p.name}.png`, fullPage: false })
      console.log('')
    }

    console.log('—— 运行时告警 ——')
    check('无运行时错误 / 组件解析告警', warns.length === 0, warns.slice(0, 3).join(' | '))
  } finally {
    await cleanupStudioRun(token, seeded.ids)
    console.log(seeded.created ? '\n已清理造数。' : '\n（复用的标记运行未删除）')
    await browser.close()
  }

  if (failures) {
    console.log(`\n❌ 工作台布局断言失败：${failures} 项`)
    process.exit(1)
  }
  console.log('\n✅ 全部工作台布局断言通过。')
  process.exit(0)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
