// README 界面预览截图。
//
// 与 shot-*.mjs（阶段验收，带结构断言）不同：本脚本**只负责产出 README 用的成品图**，
// 固定 1440×900 视口、不滚动，保证 5 张图尺寸一致、拼在 README 里视觉整齐。
//
// ⚠️ 它刻意指向**演示库**（.demo/demo.db），不要指向开发库：
// 开发库里既有真实业务内容，又有验收脚本残留的 __D5_VERIFY__ 之类标记行，
// 截出来既难看又有泄露风险。演示库由 backend/scripts/seed_demo.py 灌出（虚构品牌「润初」）。
//
// 用法：
//   # 1) 造演示库
//   cd backend && APP_DB_PATH=../.demo/demo.db venv/Scripts/python.exe scripts/seed_demo.py --reset
//   # 2) 起演示实例（不要用 8765，那是开发实例）
//   APP_DB_PATH=../.demo/demo.db APP_PORT=8766 APP_NO_BROWSER=1 venv/Scripts/python.exe run.py
//   # 3) 截图
//   cd frontend && node scripts/shot-readme.mjs
//
// 环境变量：SHOT_URL（默认 http://127.0.0.1:8766）、OUT_DIR（默认 ../docs/screenshots）

import { chromium } from 'playwright-core'

const BASE = process.env.SHOT_URL || 'http://127.0.0.1:8766'
const OUT = process.env.OUT_DIR || '../docs/screenshots'
const USER = process.env.SMOKE_USER || 'admin'
const PASS = process.env.SMOKE_PASS || 'admin123'

const VIEWPORT = { width: 1440, height: 900 }

// README 的 5 张主预览 + 阶段新增能力的 4 张补充图
const PAGES = [
  { path: '/dashboard', file: '01-dashboard.png', desc: '工作台' },
  { path: '/production', file: '02-production.png', desc: '软文生产（选中一个已完成任务，展示 10 步）', selectFirstTask: true },
  { path: '/prompt-library', file: '03-prompt-library.png', desc: 'AI 提示词库' },
  { path: '/knowledge', file: '04-knowledge.png', desc: '知识库' },
  { path: '/geo-canvas', file: '05-geo-canvas.png', desc: 'GEO 定位画布' },

  { path: '/pipeline', file: '06-pipeline.png', desc: '批量生产与队列' },
  { path: '/browser-studio', file: '07-browser-studio.png', desc: '浏览器工作室' },
  { path: '/geo-visibility', file: '08-geo-visibility.png', desc: 'AI 可见性看板' },
  { path: '/geo-loop', file: '09-geo-loop.png', desc: '归因闭环' },
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
  console.log(`登录成功：${user.username}（${user.role}）  目标：${BASE}`)

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: VIEWPORT })

  const errs = []
  page.on('pageerror', (e) => errs.push(`${page.url()} :: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errs.push(`${page.url()} :: [console] ${m.text()}`)
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

  let ok = 0
  for (const p of PAGES) {
    try {
      await page.goto(BASE + p.path, { waitUntil: 'networkidle', timeout: 30000 })
      await page.waitForTimeout(1200)

      if (p.selectFirstTask) {
        // 不选中任务时右侧是空状态，截图会显得「功能没做」。
        // 优先挑「已完成」的：10 步全绿 + 正文齐全，最能体现完整流程。
        const done = page.locator('.task-panel .task-card--done').first()
        const any = page.locator('.task-panel .task-card').first()
        const target = (await done.count()) ? done : any
        if (await target.count()) {
          await target.click({ timeout: 5000 })
          await page.waitForTimeout(1800)
        } else {
          console.log(`  ⚠ ${p.path} 未找到可点击的任务卡片，右侧可能是空状态`)
        }
      }

      // ⚠️ 页面滚动发生在内层 `.content` 容器，不是 body —— 只调 window.scrollTo 没用。
      // 放在**截图前**（而不是导航后）：选中任务等交互本身也可能把容器滚走。
      // 不做这一步，页头会被推出视口，截出来像「页面坏了」。
      await page.evaluate(() => {
        const c = document.querySelector('.content')
        if (c) c.scrollTop = 0
        window.scrollTo(0, 0)
      })
      await page.waitForTimeout(250)

      await page.screenshot({ path: `${OUT}/${p.file}` })
      console.log(`✓ ${p.file.padEnd(26)} ${p.desc}`)
      ok += 1
    } catch (e) {
      console.log(`✗ ${p.file.padEnd(26)} ${p.path} —— ${e.message.split('\n')[0]}`)
    }
  }

  console.log(`\n${ok}/${PAGES.length} 张已生成 → ${OUT}`)
  if (errs.length) {
    console.log('\n⚠️ 运行时错误：')
    errs.slice(0, 10).forEach((e) => console.log('  ' + e))
  } else {
    console.log('无运行时错误。')
  }

  await browser.close()
  if (ok !== PAGES.length) process.exit(1)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
