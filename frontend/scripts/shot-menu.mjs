// 阶段 D · D7-1 侧边栏菜单的**结构验收**。
//
// 为什么必须单独写一个脚本：
//   D7 把菜单从「Layout.vue 里手工维护的第二份事实」改成了「由 router.getRoutes() 派生」。
//   这个改动最危险的失败模式是**静默**的 —— 菜单少一项、组顺序变了、徽标丢了，
//   页面照样渲染、照样没有报错，build 与 smoke 全绿，只有人眼盯着侧边栏才看得出来。
//   所以这里把「菜单应该长什么样」写成**可执行的期望值**，逐项比对。
//
// 覆盖：
//   1. 7 个分组的**顺序与名称**
//   2. 23 个菜单项的 **path → 标题 → 徽标** 映射，且顺序一致
//   3. 顶栏「分组 / 标题」不再出现「发布自动化 / 发布自动化」这种同名漂移
//   4. 当前路由高亮（is-active 只命中一个）
//   5. 折叠后文案真的隐藏（计算样式，v-show 是否生效）
//
// 用法：node scripts/shot-menu.mjs
// 依赖：后端已在 8765 运行（脚本会自行登录）。
// 可用 SMOKE_URL / SMOKE_USER / SMOKE_PASS 覆盖。

import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'
const OUT = process.env.OUT_DIR || '../docs/screenshots'
const USER = process.env.SMOKE_USER || 'admin'
const PASS = process.env.SMOKE_PASS || 'admin123'

// ⚠️ 这是**规格**，不是实现。它刻意硬编码 —— 只有与实现相互独立，断言才有意义。
// 改菜单时：先改 router/index.js，再改这里，让「改了哪一项」在 diff 里显式可见。
const EXPECTED = [
  { group: '工作台', items: [['/dashboard', '工作台', '']] },
  {
    group: '内容生产',
    items: [
      ['/production', '软文生产', ''],
      ['/content', '内容中心', 'NEW'],
    ],
  },
  { group: '品牌资产', items: [['/brand-asset', '品牌资产库', 'NEW']] },
  {
    group: '基础配置',
    items: [
      ['/industry', '行业空间', ''],
      ['/platform', '平台账号人设', ''],
      ['/knowledge', '知识库', ''],
      ['/keyword', '关键词选题', ''],
    ],
  },
  {
    group: 'AI配置',
    items: [
      ['/prompt-library', 'AI提示词库', '4类'],
      ['/prompt-center', '提示词总览', '收口'],
      ['/rule', '规则库', ''],
      ['/settings', 'LLM 配置', 'NEW'],
    ],
  },
  {
    group: 'GEO 作战',
    items: [
      ['/geo-canvas', 'GEO 定位画布', 'NEW'],
      ['/persona', '客户画像', ''],
      ['/intent-question', '意图问题库', ''],
      ['/geo-monitor', 'AI推荐监测', ''],
      ['/geo-visibility', 'AI可见性看板', 'NEW'],
      ['/geo-loop', '归因闭环', 'NEW'],
    ],
  },
  {
    group: '发布自动化',
    items: [
      ['/pipeline', '批量生产与队列', 'NEW'],
      ['/publish', '发布中心', 'NEW'],
      ['/browser-studio', '浏览器工作室', 'NEW'],
      ['/automation-studio', '自动化指挥中心', 'NEW'],
      ['/manual', '操作手册', ''],
    ],
  },
]

const EXPECTED_ITEM_COUNT = EXPECTED.reduce((n, g) => n + g.items.length, 0)

let failures = 0
function check(label, ok, detail = '') {
  if (ok) {
    console.log(`  ✓ ${label}`)
  } else {
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

/** 从真实 DOM 里读出侧边栏结构（组 + 项，保持渲染顺序） */
async function readMenu(page) {
  return page.evaluate(() => {
    const nav = document.querySelector('.sidebar__nav')
    if (!nav) return null
    const groups = []
    let cur = null
    for (const el of nav.children) {
      if (el.classList.contains('nav-group-label')) {
        cur = { group: el.textContent.trim(), items: [] }
        groups.push(cur)
      } else if (el.classList.contains('nav-item') && cur) {
        const textEl = el.querySelector('.nav-item__text')
        const badgeEl = el.querySelector('.nav-item__badge')
        cur.items.push({
          path: el.getAttribute('href'),
          title: textEl ? textEl.textContent.trim() : '',
          badge: badgeEl ? badgeEl.textContent.trim() : '',
        })
      }
    }
    return groups
  })
}

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

  await page.goto(BASE + '/dashboard', { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForTimeout(1200)

  console.log('—— 1. 菜单结构（由路由派生）——')
  const actual = await readMenu(page)
  if (!actual) {
    check('侧边栏存在', false, '.sidebar__nav 未渲染')
    await browser.close()
    process.exit(1)
  }

  check(
    `分组数量 = ${EXPECTED.length}`,
    actual.length === EXPECTED.length,
    `实际 ${actual.length}：${actual.map((g) => g.group).join(' / ')}`,
  )
  check(
    '分组顺序与名称完全一致',
    actual.map((g) => g.group).join('|') === EXPECTED.map((g) => g.group).join('|'),
    `实际：${actual.map((g) => g.group).join(' / ')}`,
  )

  const flatActual = actual.flatMap((g) => g.items.map((it) => ({ ...it, group: g.group })))
  const flatExpect = EXPECTED.flatMap((g) => g.items.map(([path, title, badge]) => ({ path, title, badge, group: g.group })))

  check(`菜单项总数 = ${EXPECTED_ITEM_COUNT}`, flatActual.length === EXPECTED_ITEM_COUNT, `实际 ${flatActual.length}`)

  // 逐项比对 path → 标题 → 徽标。逐项报错，避免「总数对了但顺序错了」被放过。
  const mismatches = []
  for (let i = 0; i < Math.max(flatActual.length, flatExpect.length); i++) {
    const a = flatActual[i]
    const e = flatExpect[i]
    if (!a) { mismatches.push(`第${i + 1}项缺失：应为 ${e.path}`); continue }
    if (!e) { mismatches.push(`第${i + 1}项多余：实际 ${a.path}`); continue }
    if (a.path !== e.path) mismatches.push(`第${i + 1}项路径：期望 ${e.path}，实际 ${a.path}`)
    else if (a.title !== e.title) mismatches.push(`${e.path} 标题：期望「${e.title}」，实际「${a.title}」`)
    else if (a.badge !== e.badge) mismatches.push(`${e.path} 徽标：期望「${e.badge}」，实际「${a.badge}」`)
  }
  check('path / 标题 / 徽标 逐项一致（含顺序）', mismatches.length === 0, mismatches.slice(0, 6).join('；'))

  // 单独把「标题漂移」拎出来报，因为这是 D7 修掉的那个真实缺陷
  const publish = flatActual.find((it) => it.path === '/publish')
  check(
    '/publish 的菜单标题是「发布中心」（不再是漂移前的「发布自动化」）',
    publish && publish.title === '发布中心',
    publish ? `实际「${publish.title}」` : '未找到 /publish',
  )

  console.log('\n—— 2. 顶栏不再出现「分组 / 标题」同名 ——')
  await page.goto(BASE + '/publish', { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForTimeout(900)
  const topbar = await page.evaluate(() => ({
    group: (document.querySelector('.topbar__group') || {}).textContent?.trim() || '',
    title: (document.querySelector('.topbar__title') || {}).textContent?.trim() || '',
  }))
  check(
    `顶栏渲染为「${topbar.group} / ${topbar.title}」且两者不同名`,
    topbar.group === '发布自动化' && topbar.title === '发布中心' && topbar.group !== topbar.title,
    JSON.stringify(topbar),
  )

  console.log('\n—— 3. 当前路由高亮 ——')
  await page.goto(BASE + '/knowledge', { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForTimeout(900)
  const active = await page.evaluate(() =>
    [...document.querySelectorAll('.nav-item.is-active')].map((el) => el.getAttribute('href')),
  )
  check(
    '/knowledge 页高亮且仅高亮 /knowledge',
    active.length === 1 && active[0] === '/knowledge',
    JSON.stringify(active),
  )

  console.log('\n—— 4. 折叠后文案真的隐藏（计算样式）——')
  await page.locator('.collapse-btn').click()
  await page.waitForTimeout(600)
  const collapsed = await page.evaluate(() => {
    const text = document.querySelector('.nav-item__text')
    const label = document.querySelector('.nav-group-label')
    const sidebar = document.querySelector('.sidebar')
    return {
      textDisplay: text ? getComputedStyle(text).display : 'no-el',
      labelDisplay: label ? getComputedStyle(label).display : 'no-el',
      sidebarWidth: sidebar ? getComputedStyle(sidebar).width : 'no-el',
    }
  })
  check(
    '折叠后菜单文案 display:none',
    collapsed.textDisplay === 'none',
    JSON.stringify(collapsed),
  )
  check(
    '折叠后分组标题 display:none',
    collapsed.labelDisplay === 'none',
    JSON.stringify(collapsed),
  )
  check('折叠后侧边栏收窄到 64px', collapsed.sidebarWidth === '64px', collapsed.sidebarWidth)

  // 复原，便于截图与后续脚本
  await page.locator('.collapse-btn').click()
  await page.waitForTimeout(500)

  console.log('\n—— 5. 运行时告警 ——')
  check('无运行时错误 / 组件解析告警', warns.length === 0, warns.slice(0, 3).join(' | '))

  // 截图（展开态 + 折叠态）
  await page.goto(BASE + '/dashboard', { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForTimeout(1000)
  await page.screenshot({ path: `${OUT}/D7-侧边栏-菜单.png`, fullPage: false })
  console.log(`\n截图 → ${OUT}/D7-侧边栏-菜单.png`)

  await browser.close()

  if (failures) {
    console.log(`\n❌ 菜单结构断言失败：${failures} 项`)
    process.exit(1)
  }
  console.log('\n✅ 全部菜单结构断言通过。')
  process.exit(0)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
