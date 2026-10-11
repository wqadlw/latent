// 知识库 / 关键词（D5 拆分）的视觉 + 结构验收。
//
// 每拆出一块就跑一次，确认「拆出来的组件长得和拆之前一样」，并且**真的渲染了内容**。
//
// 为什么带断言而不只是截图：D4 的教训 —— 组件拆出去后若 prop 没传进来，
// 页面会静默退化成空状态，那也是一张「正常」的截图。只截图不断言 = 假绿。
//
// ⚠️ 本机开发库是空的（knowledge/keyword/topic 全为 0 条）。
// 在空库上断言「列表有内容」永远失败，把断言放宽成「不报错」又等于没断言。
// 所以本脚本**先自己造一条标记数据**（幂等：已存在就复用），断言完再删掉，
// 保证「列表真的渲染出了行」这件事被真正验证到，且跑完不留痕。
//
// 用法：node scripts/shot-knowledge.mjs
// 依赖：后端已在 8765 运行。

import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'
const OUT = process.env.OUT_DIR || '../docs/screenshots'
const USER = process.env.SMOKE_USER || 'admin'
const PASS = process.env.SMOKE_PASS || 'admin123'
const INDUSTRY = Number(process.env.SMOKE_INDUSTRY || 1)

// 标记数据用的名字；跑完会删掉。
const MARK = '__D5_VERIFY__'

let failed = 0
function check(label, ok, extra = '') {
  console.log(`    ${ok ? '✅' : '❌'} ${label}${extra ? '  ' + extra : ''}`)
  if (!ok) failed++
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

function makeClient(token) {
  const h = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
  const get = async (p) => (await (await fetch(BASE + '/api' + p, { headers: h })).json()).data
  const post = async (p, body) => (await (await fetch(BASE + '/api' + p, { method: 'POST', headers: h, body: JSON.stringify(body) })).json())
  const del = async (p) => (await (await fetch(BASE + '/api' + p, { method: 'DELETE', headers: h })).json())
  return { get, post, del }
}

/** 幂等造数：返回 { created: [...], ids: {...} } */
async function seed(api) {
  const ids = { categoryIds: [], itemIds: [], groupIds: [], keywordIds: [], platformIds: [], accountIds: [], topicIds: [] }

  // --- 知识库 ---
  const cats = await api.get(`/knowledge/category?industry_id=${INDUSTRY}`)
  let cat = (cats || []).find((c) => c.name === MARK)
  if (!cat) {
    const r = await api.post('/knowledge/category', {
      name: MARK, icon: 'Collection', color: '#6366f1', description: 'D5 验收用，跑完即删', industry_id: INDUSTRY,
    })
    cat = r.data
    ids.categoryIds.push(cat.id)
  }
  const items = await api.get(`/knowledge/item?industry_id=${INDUSTRY}`)
  if (!(items || []).some((i) => i.title === MARK)) {
    const r = await api.post('/knowledge/item', {
      title: MARK, content: 'D5 验收用知识点，跑完即删。', summary: '验收标记',
      category_id: cat.id, tags: 'verify', source: 'd5', importance: 'high', status: 'published',
      industry_id: INDUSTRY,
    })
    if (r.data && r.data.id) ids.itemIds.push(r.data.id)
  }

  // --- 关键词 ---
  const groups = await api.get(`/keyword-group?industry_id=${INDUSTRY}`)
  let grp = (groups || []).find((g) => g.name === MARK)
  if (!grp) {
    const r = await api.post('/keyword-group', {
      name: MARK, color: '#0ea5e9', icon: 'Collection', description: 'D5 验收用，跑完即删', industry_id: INDUSTRY,
    })
    grp = r.data
    ids.groupIds.push(grp.id)
  }
  const kws = await api.get(`/keyword?industry_id=${INDUSTRY}`)
  let kw = (kws || []).find((k) => k.word === MARK)
  if (!kw) {
    const r = await api.post('/keyword', {
      word: MARK, group_id: grp.id, type: 'long_tail', priority: 3,
      related_product: 'D5 验收', tags: 'verify', industry_id: INDUSTRY,
    })
    kw = r.data
    if (kw && kw.id) ids.keywordIds.push(kw.id)
  }

  // --- 平台 / 账号 / 选题 ---
  // 为什么连这些也造：TopicPool 与 MatrixView 是本次新拆出来的组件，
  // 不造数的话它们只会在**空状态**下被验证 —— 又一次「断言在空数据上假过」。
  //
  // 账号**故意不传 persona_id**：这正是 D5 发现的那个 500 缺陷的触发路径
  // （`Account.persona_id` 曾是 `default=0` + `PRAGMA foreign_keys=ON` → 外键失败）。
  // 缺陷已修（`default=None`，回归测试见 `backend/tests/test_account_api.py`），
  // 这里顺带把它当成一条端到端回归。
  const plats = await api.get(`/platform?industry_id=${INDUSTRY}`)
  let plat = (plats || []).find((p) => p.name === MARK)
  if (!plat) {
    const r = await api.post('/platform', {
      industry_id: INDUSTRY, name: MARK, word_count_min: 800, word_count_max: 1500, sort: 999,
    })
    plat = r.data
    if (plat && plat.id) ids.platformIds.push(plat.id)
  }
  const accs = await api.get(`/account?industry_id=${INDUSTRY}`)
  let acc = (accs || []).find((a) => a.account_name === MARK)
  if (!acc) {
    const r = await api.post('/account', {
      industry_id: INDUSTRY, platform_id: plat.id, account_name: MARK, status: 1, sort: 999,
    })
    acc = r.data
    if (acc && acc.id) ids.accountIds.push(acc.id)
  }
  const tps = await api.get(`/topic?industry_id=${INDUSTRY}`)
  if (!(tps || []).some((t) => t.title === MARK)) {
    const r = await api.post('/topic', {
      industry_id: INDUSTRY, platform_id: plat.id, account_id: acc.id, title: MARK,
      keyword_id_list: kw && kw.id ? String(kw.id) : '', status: 'pending', plan_date: '2026-10-11', sort: 999,
    })
    if (r.data && r.data.id) ids.topicIds.push(r.data.id)
  }

  return ids
}

async function cleanup(api, ids) {
  // 注意：后端的 DELETE 是**软删除**（`is_deleted=1`），所以这里删掉的行会作为墓碑留在库里。
  // 跑多次会积累墓碑 —— 这是 API 的正常语义，不是泄漏：所有 `is_deleted=0` 的计数都回到 0，
  // 页面上看不到任何残留。若日后介意，再考虑给脚本加一个直连库的清理分支。
  for (const id of ids.topicIds) await api.del(`/topic/${id}`).catch(() => {})
  for (const id of ids.accountIds) await api.del(`/account/${id}`).catch(() => {})
  for (const id of ids.platformIds) await api.del(`/platform/${id}`).catch(() => {})
  for (const id of ids.keywordIds) await api.del(`/keyword/${id}`).catch(() => {})
  for (const id of ids.groupIds) await api.del(`/keyword-group/${id}`).catch(() => {})
  for (const id of ids.itemIds) await api.del(`/knowledge/item/${id}`).catch(() => {})
  for (const id of ids.categoryIds) await api.del(`/knowledge/category/${id}`).catch(() => {})
}

async function main() {
  const { token, user } = await login()
  console.log(`登录成功：${user.username}（${user.role}）`)

  const api = makeClient(token)

  // ⚠️ 造数必须**在 try 里面**：造数中途失败（例如后端 500）时若它在 try 外，
  // finally 里的 cleanup 就不会执行，已经写进去的标记数据会**永久残留**。
  // 这个坑已经踩过一次 —— 修 account 的 500 时，platform/keyword/item 全漏在库里。
  let seeded = { categoryIds: [], itemIds: [], groupIds: [], keywordIds: [], platformIds: [], accountIds: [], topicIds: [] }

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })

  const errs = []
  page.on('pageerror', (e) => errs.push('[pageerror] ' + e.message))
  page.on('console', (m) => {
    if (m.type() === 'error') errs.push('[console] ' + m.text())
  })

  try {
    seeded = await seed(api)
    console.log(`已就绪标记数据（新建 ${JSON.stringify(seeded)}，已存在的复用）\n`)

    await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
    await page.evaluate(
      ([t, u, ind]) => {
        localStorage.setItem('acm_token', t)
        localStorage.setItem('acm_user', JSON.stringify(u))
        localStorage.setItem('currentIndustryId', String(ind))
      },
      [token, user, INDUSTRY],
    )

    // ============================ 知识库 ============================
    await page.goto(BASE + '/knowledge', { waitUntil: 'networkidle', timeout: 30000 })
    await page.waitForTimeout(2500)
    await page.screenshot({ path: `${OUT}/D5-知识库-主视图.png`, fullPage: true })
    console.log(`✓ 知识库主视图 → ${OUT}/D5-知识库-主视图.png`)

    console.log('  知识库结构断言：')
    const kb = await page.evaluate(() => ({
      hero: !!document.querySelector('.hero'),
      metrics: document.querySelectorAll('.hero .metric').length,
      categoryItems: document.querySelectorAll('.category-panel .category-item').length,
      itemCards: document.querySelectorAll('.item-panel .item-card, .item-panel .item-row').length,
    }))
    console.log(`    hero=${kb.hero}  指标=${kb.metrics}  分类项=${kb.categoryItems}  知识卡片=${kb.itemCards}`)
    check('hero 渲染', kb.hero)
    check('四个指标渲染', kb.metrics === 4, `实际 ${kb.metrics}`)
    check('左侧分类面板渲染出分类项', kb.categoryItems >= 2, `实际 ${kb.categoryItems}（含「全部」+ 标记分类）`)
    check('右侧知识点列表渲染出行', kb.itemCards > 0, `实际 ${kb.itemCards}`)

    // 分类弹窗：验证图标下拉来自共享真源（10 项，含此前 Knowledge 缺失的 Collection）
    const newCatBtn = page.getByRole('button', { name: '新增' }).first()
    if (await newCatBtn.count()) {
      await newCatBtn.click({ timeout: 5000 })
      await page.waitForTimeout(1200)
      await page.screenshot({ path: `${OUT}/D5-知识库-分类弹窗.png` })
      console.log(`✓ 知识库分类弹窗 → ${OUT}/D5-知识库-分类弹窗.png`)

      // 页面上 4 个 el-dialog 都在 DOM 里（未打开的只是隐藏），
      // 必须限定到可见的 overlay，否则会数到别的弹窗的下拉。
      const iconSelect = page.locator('.el-overlay:visible .el-dialog .el-select').first()
      let iconCount = 0
      if (await iconSelect.count()) {
        await iconSelect.click()
        await page.waitForTimeout(800)
        iconCount = await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').count()
        await page.keyboard.press('Escape')
        await page.waitForTimeout(400)
      }
      console.log('    图标下拉项数：', iconCount)
      check('图标下拉来自共享真源（10 项）', iconCount === 10, `实际 ${iconCount}`)
      await page.keyboard.press('Escape')
      await page.waitForTimeout(500)
    } else {
      check('找到「新增」分类按钮', false)
    }

    // ============================ 关键词 ============================
    await page.goto(BASE + '/keyword', { waitUntil: 'networkidle', timeout: 30000 })
    await page.waitForTimeout(2500)
    await page.screenshot({ path: `${OUT}/D5-关键词-主视图.png`, fullPage: true })
    console.log(`✓ 关键词主视图 → ${OUT}/D5-关键词-主视图.png`)

    console.log('  关键词结构断言：')
    const kw = await page.evaluate(() => ({
      hero: !!document.querySelector('.hero'),
      metrics: document.querySelectorAll('.hero .metric').length,
      tabs: document.querySelectorAll('.section-tab').length,
      groupItems: document.querySelectorAll('.group-panel .group-item').length,
      kwRows: document.querySelectorAll('.item-panel .vtable .kw-row').length,
      kwHead: document.querySelectorAll('.item-panel .vtable__head .kw-cell').length,
    }))
    console.log(`    hero=${kw.hero}  指标=${kw.metrics}  分段=${kw.tabs}  分组项=${kw.groupItems}  关键词行=${kw.kwRows}  表头格=${kw.kwHead}`)
    check('hero 渲染', kw.hero)
    check('三个分段切换', kw.tabs === 3, `实际 ${kw.tabs}`)
    check('左侧分组面板渲染出分组项', kw.groupItems >= 2, `实际 ${kw.groupItems}`)
    check('关键词虚拟列表渲染出行', kw.kwRows > 0, `实际 ${kw.kwRows}`)
    check('关键词表头 8 列', kw.kwHead === 8, `实际 ${kw.kwHead}`)

    // 切到选题池 / 矩阵，确认这两个 tab 没被拆坏。
    // 已造了 platform+account+topic，所以这里必须**渲染出卡片**，空状态反而算失败。
    const tabProbes = [
      ['选题池', 'D5-关键词-选题池.png', '.topic-toolbar', '.topic-card', /暂无选题/],
      ['矩阵', 'D5-关键词-矩阵.png', null, '.matrix-card', /暂无矩阵数据/],
    ]
    for (const [label, file, structSel, dataSel, emptyRe] of tabProbes) {
      const tab = page.locator('.section-tab', { hasText: label }).first()
      if (!(await tab.count())) { check(`找到「${label}」分段`, false); continue }
      await tab.click()
      await page.waitForTimeout(1500)
      await page.screenshot({ path: `${OUT}/${file}`, fullPage: true })
      console.log(`✓ 关键词「${label}」→ ${OUT}/${file}`)
      if (structSel) {
        const n = await page.locator(structSel).count()
        check(`「${label}」工具栏渲染`, n > 0, `${structSel} 实际 ${n}`)
      }
      const n = await page.locator(dataSel).count()
      const emptyShown = await page.getByText(emptyRe).count()
      check(`「${label}」渲染出卡片（非空状态）`, n > 0 && emptyShown === 0, `${dataSel}=${n} 空状态=${emptyShown}`)
    }

    // 矩阵要多看两层：平台卡 → 账号行 → 选题行，缺一层都说明拆组件时数据没透传下去
    const mx = await page.evaluate(() => ({
      cards: document.querySelectorAll('.matrix-card').length,
      accs: document.querySelectorAll('.matrix-acc').length,
      topics: document.querySelectorAll('.matrix-topic').length,
      accName: (document.querySelector('.matrix-acc__name') || {}).textContent || '',
    }))
    console.log(`    矩阵：平台卡=${mx.cards} 账号行=${mx.accs} 选题行=${mx.topics} 账号名=${JSON.stringify(mx.accName.trim())}`)
    check('矩阵渲染出账号行', mx.accs > 0, `实际 ${mx.accs}`)
    check('矩阵渲染出选题行', mx.topics > 0, `实际 ${mx.topics}`)
    check('矩阵账号名正确透传', mx.accName.trim() === MARK, `实际 ${JSON.stringify(mx.accName.trim())}`)
  } finally {
    await browser.close()
    await cleanup(api, seeded)
    console.log('\n已清理标记数据。')
  }

  if (errs.length) {
    console.log('\n运行时错误：')
    errs.forEach((e) => console.log('  ' + e))
    process.exitCode = 1
  }
  if (failed) {
    console.log(`\n❌ ${failed} 项结构断言失败。`)
    process.exitCode = 1
  } else if (!errs.length) {
    console.log('\n✅ 全部结构断言通过，无运行时错误。')
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
