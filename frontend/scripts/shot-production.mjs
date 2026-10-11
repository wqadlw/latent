// 软文生产（D6 拆分）的视觉 + 结构验收。
//
// 与 shot-knowledge.mjs 同源：**先造标记数据 → 断言 → 清理**。
// 为什么不能只截图：D4 的教训 —— 拆组件时 prop 没透传，页面会静默退化成空状态，
// 那也是一张「正常」的截图。空库上断言「有内容」又永远失败。
//
// 本脚本覆盖的是**拆 Production.vue 时最容易坏的那些结构**：
//   1. 左侧任务面板真的渲染出任务卡（不是空态）
//   2. 选中任务后右侧工作区出现，步骤导航 10 个节点
//   3. 当前步骤内容真的渲染出 .step-pane + .step-header（说明 step 组件被挂上了）
//   4. 底部操作栏与「第 N 步 / 共 10 步」指示器
//   5. 步骤跳转后换成另一个 step 组件（证明 v-if 链没被拆断）
//   6. 两个页面级双栏布局的 grid 列宽没变（拆组件时最容易丢的 CSS）
//   7. 5 个页面级弹窗仍在 DOM 里（它们挂在 <template> 之外的顶层）
//
// 用法：node scripts/shot-production.mjs
// 依赖：后端已在 8765 运行。

import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'
const OUT = process.env.OUT_DIR || '../docs/screenshots'
const USER = process.env.SMOKE_USER || 'admin'
const PASS = process.env.SMOKE_PASS || 'admin123'

// 标记任务名；跑完会删掉。
const MARK = '__D6_VERIFY__'

// 第 9 步 GEO 体检用的样本正文。要够长、带品牌实体与数据，
// 否则本地启发式评分可能直接判 0 分、诊断横幅不渲染。
const GEO_SAMPLE = [
  `【${MARK} 软文验收样本】`,
  '',
  '很多企业采购负责人在挑选设备时，最怕遇到两个问题：一是参数虚标，二是售后找不到人。',
  '据某制造企业设备科李总介绍，他们在 2025 年 3 月一次性采购了 12 台设备，',
  '上线运行 6 个月后，综合故障率从 4.2% 下降到 1.1%，单条产线年节省维护成本约 18 万元。',
  '',
  '常见问题：',
  'Q1：交付周期要多久？A：标准机型 15 个工作日，定制机型 30 个工作日。',
  'Q2：售后响应多久？A：全国 48 小时上门，核心城市 24 小时。',
  'Q3：能否先试用？A：支持 30 天试用，不满意可全额退款。',
  '',
  '如果你也在为选型纠结，不妨先看看这份实测数据。',
  '想要详细选型方案，可以访问官网 www.example.com 或致电 400-000-0000 咨询。',
].join('\n')

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
  const put = async (p, body) => (await (await fetch(BASE + '/api' + p, { method: 'PUT', headers: h, body: JSON.stringify(body) })).json())
  const del = async (p) => (await (await fetch(BASE + '/api' + p, { method: 'DELETE', headers: h })).json())
  return { get, post, put, del }
}

/** 幂等造数：返回 { industryId, platformId, taskIds: [] } */
async function seed(api) {
  const ids = { taskIds: [] }

  // 行业必须存在，否则页面根本进不来（store 会清空 currentIndustryId）。
  const industries = await api.get('/industry')
  if (!(industries || []).length) throw new Error('库里没有行业，无法验证生产页（请先初始化数据）')
  ids.industryId = Number(process.env.SMOKE_INDUSTRY || industries[0].id)

  // 平台：第 2 步要断言「真的渲染出平台卡」，空库上只能验证空态 —— 又是「断言在空数据上假过」。
  const plats = await api.get(`/platform?industry_id=${ids.industryId}`)
  let plat = (plats || []).find((p) => p.name === MARK)
  if (!plat && !(plats || []).length) {
    const r = await api.post('/platform', {
      industry_id: ids.industryId, name: MARK, word_count_min: 800, word_count_max: 1500, sort: 999,
    })
    plat = r.data
    if (plat && plat.id) ids.platformIds = [plat.id]
  }
  plat = plat || (plats || [])[0]
  ids.platformId = plat && plat.id

  // 账号：第 3 步要断言「点账号卡能选中」，空库上只能验证空态。
  // ⚠️ 故意**不传 persona_id** —— 这正是 D5 发现的那个 500 缺陷的触发路径
  // （`Account.persona_id` 曾是 `default=0` + `PRAGMA foreign_keys=ON` → 外键失败）。
  // 缺陷已修（`default=None`，回归测试见 `backend/tests/test_account_api.py`），
  // 这里顺带把它当成一条端到端回归。
  const accs = await api.get(`/account?industry_id=${ids.industryId}`)
  if (!(accs || []).some((a) => a.account_name === MARK)) {
    const r = await api.post('/account', {
      industry_id: ids.industryId, platform_id: ids.platformId, account_name: MARK, status: 1, sort: 999,
    })
    if (r.data && r.data.id) ids.accountIds = [r.data.id]
  }

  // 关键词 / 知识点：第 5 步要断言「点关键词 chip 能勾上」，空库上只能验证空态。
  const groups = await api.get(`/keyword-group?industry_id=${ids.industryId}`)
  let grp = (groups || []).find((g) => g.name === MARK)
  if (!grp) {
    const r = await api.post('/keyword-group', {
      name: MARK, color: '#0ea5e9', icon: 'Collection', description: 'D6 验收用，跑完即删', industry_id: ids.industryId,
    })
    grp = r.data
    if (grp && grp.id) ids.groupIds = [grp.id]
  }
  const kws = await api.get(`/keyword?industry_id=${ids.industryId}`)
  if (!(kws || []).some((k) => k.word === MARK)) {
    const r = await api.post('/keyword', {
      word: MARK, group_id: grp && grp.id, type: 'long_tail', priority: 3,
      related_product: 'D6 验收', tags: 'verify', industry_id: ids.industryId,
    })
    if (r.data && r.data.id) ids.keywordIds = [r.data.id]
  }

  const cats = await api.get(`/knowledge/category?industry_id=${ids.industryId}`)
  let cat = (cats || []).find((c) => c.name === MARK)
  if (!cat) {
    const r = await api.post('/knowledge/category', {
      name: MARK, icon: 'Collection', color: '#6366f1', description: 'D6 验收用，跑完即删', industry_id: ids.industryId,
    })
    cat = r.data
    if (cat && cat.id) ids.categoryIds = [cat.id]
  }
  const items = await api.get(`/knowledge/item?industry_id=${ids.industryId}`)
  if (!(items || []).some((i) => i.title === MARK)) {
    const r = await api.post('/knowledge/item', {
      title: MARK, content: 'D6 验收用知识点，跑完即删。', summary: '验收标记',
      category_id: cat && cat.id, tags: 'verify', source: 'd6', importance: 'high', status: 'published',
      industry_id: ids.industryId,
    })
    if (r.data && r.data.id) ids.itemIds = [r.data.id]
  }

  const list = await api.get(`/production?industry_id=${ids.industryId}`)
  let task = (list || []).find((t) => t.title === MARK)
  if (!task) {
    const r = await api.post('/production', { industry_id: ids.industryId, title: MARK })
    task = r.data
    if (task && task.id) ids.taskIds.push(task.id)
  }
  ids.taskId = task && task.id
  // 绑上平台，让第 2 步有卡可点、第 3 步的账号列表按平台过滤。
  // ⚠️ 刻意**只写 platform_id，不写 platform_snapshot** —— snapshot 留给「点平台卡」那一步去写，
  // 这样后面就能用「snapshot 是否被写入」来证明 saveStep2 → saveDraft 真的落库了。
  // 若这里顺手把 snapshot 也写上，那条断言就会变成恒真（假绿）。
  if (ids.taskId && ids.platformId) {
    await api.put(`/production/${ids.taskId}`, { platform_id: ids.platformId, platform_snapshot: '' })
  }
  return ids
}

async function cleanup(api, ids) {
  // 后端的 DELETE 是**软删除**（is_deleted=1），删掉的行会作为墓碑留在库里。
  // 这不是泄漏：所有 is_deleted=0 的计数都回到 0，页面上看不到残留。
  for (const id of ids.taskIds || []) await api.del(`/production/${id}`).catch(() => {})
  for (const id of ids.accountIds || []) await api.del(`/account/${id}`).catch(() => {})
  for (const id of ids.keywordIds || []) await api.del(`/keyword/${id}`).catch(() => {})
  for (const id of ids.groupIds || []) await api.del(`/keyword-group/${id}`).catch(() => {})
  for (const id of ids.itemIds || []) await api.del(`/knowledge/item/${id}`).catch(() => {})
  for (const id of ids.categoryIds || []) await api.del(`/knowledge/category/${id}`).catch(() => {})
  for (const id of ids.platformIds || []) await api.del(`/platform/${id}`).catch(() => {})
}

async function main() {
  const { token, user } = await login()
  console.log(`登录成功：${user.username}（${user.role}）`)

  const api = makeClient(token)

  // ⚠️ 造数必须在 try 里面：造数中途失败时若在 try 外，finally 的 cleanup 不会跑，
  // 标记数据会永久残留（D5 踩过一次）。
  let seeded = { taskIds: [] }

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })

  const errs = []
  const warns = []
  page.on('pageerror', (e) => errs.push('[pageerror] ' + e.message))
  page.on('console', (m) => {
    const t = m.text()
    if (m.type() === 'error') errs.push('[console] ' + t)
    // ⚠️ Vue 在模板里引用了**未注册的组件**时只发 warn（不是 error）：
    //    "Failed to resolve component: Foo"
    // 这恰恰是「拆组件时把某个 import 弄丢」的典型症状 —— 页面不报错，
    // 只是那一块静默消失（又一次「假绿」）。所以必须单独捕获 warn。
    if (m.type() === 'warning' && /Failed to resolve (component|directive)|is not defined|not defined on instance/.test(t)) {
      // Vue 的告警带一长串组件栈，只留第一行，否则刷屏。
      warns.push('[console] ' + t.split('\n')[0])
    }
  })

  try {
    seeded = await seed(api)
    console.log(`已就绪标记数据：industry=${seeded.industryId} task=${seeded.taskId}（新建 ${JSON.stringify(seeded.taskIds)}）\n`)

    await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
    await page.evaluate(
      ([t, u, ind]) => {
        localStorage.setItem('acm_token', t)
        localStorage.setItem('acm_user', JSON.stringify(u))
        localStorage.setItem('currentIndustryId', String(ind))
      },
      [token, user, seeded.industryId],
    )

    // ============================ 生产页 ============================
    await page.goto(BASE + '/production', { waitUntil: 'networkidle', timeout: 30000 })
    await page.waitForTimeout(2500)
    await page.screenshot({ path: `${OUT}/D6-生产-未选任务.png`, fullPage: true })
    console.log(`✓ 生产页（未选任务）→ ${OUT}/D6-生产-未选任务.png`)

    console.log('  生产页骨架断言：')
    const shell = await page.evaluate(() => {
      const layout = document.querySelector('.prod-layout')
      const cs = layout ? getComputedStyle(layout) : null
      return {
        view: !!document.querySelector('.production-view'),
        taskPanel: !!document.querySelector('.task-panel'),
        panelTitle: (document.querySelector('.task-panel .panel-title') || {}).textContent || '',
        workspace: !!document.querySelector('.workspace-panel'),
        emptyWorkspace: !!document.querySelector('.empty-workspace'),
        gridCols: cs ? cs.gridTemplateColumns : '',
        // 页面级弹窗（挂在最外层，不在 .prod-layout 里）
        // ⚠️ 不能用 `.el-dialog` 计数：Element Plus 的 el-dialog 内部是 `v-if="rendered"`，
        // **从未打开过就不渲染 .el-dialog**（惰性）。但它外层那个 `.el-overlay` 是常驻的，
        // 每个 dialog/drawer 恰好贡献一个 —— 所以数 overlay 才是可靠的。
        // 4 个 dialog（版本历史/自定义变量/一键生成结果/建发布任务）+ 1 个 drawer（知识点详情）= 5
        modalDialogs: document.querySelectorAll('.el-overlay.el-modal-dialog').length,
        modalDrawers: document.querySelectorAll('.el-overlay.is-drawer').length,
      }
    })
    console.log(`    view=${shell.view} 任务面板=${shell.taskPanel} 工作区=${shell.workspace} 空态=${shell.emptyWorkspace}`)
    console.log(`    左栏列宽=${JSON.stringify(shell.gridCols)}  页面级弹窗=${shell.modalDialogs} 抽屉=${shell.modalDrawers}`)
    check('production-view 渲染', shell.view)
    check('左侧任务面板渲染', shell.taskPanel)
    check('面板标题为「生产任务」', shell.panelTitle.trim() === '生产任务', JSON.stringify(shell.panelTitle.trim()))
    check('右侧工作区渲染', shell.workspace)
    check('未选任务时显示空工作区引导', shell.emptyWorkspace)
    // 双栏布局：320px 固定 + 1fr。拆组件时最容易把这条 CSS 丢掉。
    check('左栏 320px 双栏布局保持', shell.gridCols.startsWith('320px'), JSON.stringify(shell.gridCols))
    // 5 个页面级弹窗组件都挂上了：VersionHistory / CustomVar / OneClickGenerate / CreatePublishTask / KnowledgePreview
    check('4 个页面级弹窗 + 1 个抽屉都挂载', shell.modalDialogs === 4 && shell.modalDrawers === 1, `dialog=${shell.modalDialogs} drawer=${shell.modalDrawers}`)

    // 任务列表必须有内容（已造标记任务，空态反而是失败）
    const cards = await page.locator('.task-panel .task-card').count()
    const emptyTip = await page.locator('.task-panel .empty-tip').count()
    console.log(`    任务卡=${cards}  空提示=${emptyTip}`)
    check('任务列表渲染出任务卡（非空态）', cards > 0 && emptyTip === 0, `card=${cards} empty=${emptyTip}`)

    // 点击标记任务 → 右侧工作区
    const markCard = page.locator('.task-panel .task-card', { hasText: MARK }).first()
    if (!(await markCard.count())) { check('找到标记任务卡', false); throw new Error('标记任务卡未渲染') }
    await markCard.click()
    await page.waitForTimeout(2000)
    await page.screenshot({ path: `${OUT}/D6-生产-选中任务.png`, fullPage: true })
    console.log(`✓ 生产页（选中任务）→ ${OUT}/D6-生产-选中任务.png`)

    console.log('  工作区结构断言：')
    const ws = await page.evaluate(() => {
      const nav = document.querySelector('.steps-nav')
      const bar = document.querySelector('.action-bar')
      return {
        stepNodes: document.querySelectorAll('.steps-nav .step-node').length,
        stepNames: Array.from(document.querySelectorAll('.steps-nav .step-name')).map((e) => e.textContent.trim()),
        panes: document.querySelectorAll('.step-content .step-pane').length,
        headers: document.querySelectorAll('.step-content .step-header').length,
        headerTitle: (document.querySelector('.step-content .step-header-title') || {}).textContent || '',
        actionBar: !!bar,
        indicator: (document.querySelector('.action-bar .step-indicator') || {}).textContent || '',
        // 操作栏三段：上一步 / 中间指示器 / 右侧按钮组
        btnLeft: !!document.querySelector('.action-bar > .el-button'),
        actionCenter: !!document.querySelector('.action-bar .action-center'),
        actionRight: !!document.querySelector('.action-bar .action-right'),
        emptyWorkspace: !!document.querySelector('.empty-workspace'),
      }
    })
    console.log(`    步骤节点=${ws.stepNodes}  步骤内容 pane=${ws.panes} header=${ws.headers}  标题=${JSON.stringify(ws.headerTitle.trim())}`)
    console.log(`    操作栏=${ws.actionBar}  指示器=${JSON.stringify(ws.indicator.trim())}`)
    check('步骤导航渲染 10 个节点', ws.stepNodes === 10, `实际 ${ws.stepNodes}`)
    check('步骤名与步骤表一致', ws.stepNames[0] === '选行业' && ws.stepNames[9] === '配图', JSON.stringify(ws.stepNames))
    check('当前步骤内容渲染 .step-pane', ws.panes === 1, `实际 ${ws.panes}`)
    check('当前步骤渲染 StepHeader', ws.headers === 1, `实际 ${ws.headers}`)
    check('第 1 步是「选择行业」', ws.headerTitle.trim() === '选择行业', JSON.stringify(ws.headerTitle.trim()))
    check('底部操作栏渲染', ws.actionBar && ws.btnLeft && ws.actionCenter && ws.actionRight)
    check('步骤指示器文案正确', ws.indicator.trim() === '第 1 步 / 共 10 步', JSON.stringify(ws.indicator.trim()))
    check('选中任务后空态消失', !ws.emptyWorkspace)

    // 步骤跳转：点第 2 步 → 应换成 StepPlatform（证明 v-if 链没断）
    const node2 = page.locator('.steps-nav .step-node').nth(1)
    await node2.click()
    await page.waitForTimeout(1500)
    await page.screenshot({ path: `${OUT}/D6-生产-第2步平台.png`, fullPage: true })
    console.log(`✓ 生产页（第 2 步）→ ${OUT}/D6-生产-第2步平台.png`)
    const step2 = await page.evaluate(() => ({
      title: (document.querySelector('.step-content .step-header-title') || {}).textContent || '',
      platformList: !!document.querySelector('.step-content .platform-select-list'),
      industryGrid: !!document.querySelector('.step-content .options-grid'),
      indicator: (document.querySelector('.action-bar .step-indicator') || {}).textContent || '',
    }))
    console.log(`    第2步标题=${JSON.stringify(step2.title.trim())} 平台列表=${step2.platformList} 行业网格=${step2.industryGrid}`)
    check('跳转后渲染 StepPlatform', step2.platformList && !step2.industryGrid)
    check('跳转后标题为「选择发布平台」', step2.title.trim() === '选择发布平台', JSON.stringify(step2.title.trim()))
    check('跳转后指示器更新', step2.indicator.trim() === '第 2 步 / 共 10 步', JSON.stringify(step2.indicator.trim()))

    // ================= 走遍全部 10 步 =================
    // 为什么必须走完 10 步：D6 拆的是「逻辑」，模板里的 step 组件本身不动，
    // 但只要有一个 prop / 函数没接上，对应那一步就会静默变成空壳。
    // 只验证第 1 步 = 把 9 个步骤的回归风险全部放过。
    //
    // goStep() 只允许跳到「当前步 +1」，所以直接改库把任务推到第 10 步，
    // 然后就可以自由点任意步骤节点往回跳（goStep 对「后退」永远放行）。
    await api.put(`/production/${seeded.taskId}`, { current_step: 10 })
    await page.reload({ waitUntil: 'networkidle', timeout: 30000 })
    await page.waitForTimeout(2000)
    await page.locator('.task-panel .task-card', { hasText: MARK }).first().click()
    await page.waitForTimeout(2000)

    // 每步的期望：标题 + 该步独有的结构钩子（钩子缺失 = 组件没挂上或内部结构被拆坏）
    const STEPS = [
      { no: 1, title: '选择行业', hook: '.options-grid', hookLabel: '行业网格', data: '.options-grid .option-card' },
      { no: 2, title: '选择发布平台', hook: '.platform-select-list', hookLabel: '平台列表', data: '.platform-select-list .platform-card' },
      { no: 3, title: '确定人设账号', hook: '.persona-layout', hookLabel: '人设布局' },
      { no: 4, title: '确定目标客户需求', hook: '.geo-demand', hookLabel: 'GEO 需求区' },
      { no: 5, title: '选择关键词 & 知识点', hook: '.two-col-layout', hookLabel: '双栏选择区' },
      { no: 6, title: '生成大纲', hook: '.single-flow', hookLabel: '单流程区' },
      { no: 7, title: '生成文章初稿', hook: '.single-flow', hookLabel: '单流程区' },
      { no: 8, title: 'AI 洗稿精修', hook: '.single-flow', hookLabel: '单流程区' },
      { no: 9, title: '安全发布 & GEO 筛选', hook: '.geo-gate-block', hookLabel: 'GEO 闸门区' },
      { no: 10, title: '文章配图', hook: '.illu-wrap', hookLabel: '配图区' },
    ]

    console.log('  逐步走查（10 步）：')
    for (const s of STEPS) {
      await page.locator('.steps-nav .step-node').nth(s.no - 1).click()
      await page.waitForTimeout(1100)
      const got = await page.evaluate((sel) => ({
        panes: document.querySelectorAll('.step-content .step-pane').length,
        title: (document.querySelector('.step-content .step-header-title') || {}).textContent || '',
        hook: document.querySelectorAll('.step-content ' + sel).length,
        indicator: (document.querySelector('.action-bar .step-indicator') || {}).textContent || '',
      }), s.hook)
      const okTitle = got.title.trim() === s.title
      const okHook = got.hook > 0
      const okPane = got.panes === 1
      const okIdx = got.indicator.trim() === `第 ${s.no} 步 / 共 10 步`
      console.log(`    第${String(s.no).padStart(2)}步 pane=${got.panes} 标题=${JSON.stringify(got.title.trim())} ${s.hook}=${got.hook} 指示器=${JSON.stringify(got.indicator.trim())}`)
      check(`第 ${s.no} 步渲染 .step-pane`, okPane)
      check(`第 ${s.no} 步标题「${s.title}」`, okTitle, JSON.stringify(got.title.trim()))
      check(`第 ${s.no} 步渲染${s.hookLabel}`, okHook, `${s.hook}=${got.hook}`)
      check(`第 ${s.no} 步指示器正确`, okIdx, JSON.stringify(got.indicator.trim()))
      if (s.data) {
        const n = await page.locator('.step-content ' + s.data).count()
        console.log(`        ${s.data} = ${n}`)
        check(`第 ${s.no} 步${s.hookLabel}渲染出条目（非空态）`, n > 0, `实际 ${n}`)
      }
      await page.screenshot({ path: `${OUT}/D6-生产-第${s.no}步.png`, fullPage: true })
    }
    console.log(`✓ 10 步截图 → ${OUT}/D6-生产-第N步.png`)

    // ================= 交互回归：验证「抽出去的逻辑」真的还在工作 =================
    // 上面全是**结构**断言。逻辑搬进 composable 后，结构可以完全不变而行为已经坏掉
    // （典型：函数 prop 没接上 → 点了没反应，但页面不报错）。
    // 所以这里逐步点一遍，用「toast / 选中态 / 落库结果」三重信号确认动作真的执行了。
    console.log('  交互回归：')

    // ⚠️ 先复位到第 10 步再刷新：`goStep()` 只允许「前进一格」，直接点第 5 步会被
    // 「请先完成前面的步骤」挡掉（这一步曾让本脚本自己误报「第 5 步没有关键词 chip」）。
    // 从第 10 步出发，任意**后退**都放行，就能直接点任意步骤。
    await api.put(`/production/${seeded.taskId}`, { current_step: 10 })
    await page.reload({ waitUntil: 'networkidle', timeout: 30000 })
    await page.waitForTimeout(2000)
    await page.locator('.task-panel .task-card', { hasText: MARK }).first().click()
    await page.waitForTimeout(2000)

    /** 等到出现包含指定文案的 el-message（证明事件处理函数真的跑了）。 */
    async function waitToast(text, ms = 4000) {
      try {
        await page.locator('.el-message', { hasText: text }).first().waitFor({ state: 'visible', timeout: ms })
        return true
      } catch {
        return false
      }
    }

    // 第 1 步：点行业卡 → saveStep1（写入 industry_id + snapshot，并重载选项）
    await page.locator('.steps-nav .step-node').nth(0).click()
    await page.waitForTimeout(900)
    const card1 = page.locator('.step-content .options-grid .option-card').first()
    if (await card1.count()) {
      await card1.click()
      check('点行业卡触发 saveStep1（出现「已选择行业」提示）', await waitToast('已选择行业'))
      check('行业卡出现选中态', (await page.locator('.step-content .option-card.selected').count()) > 0)
    } else {
      check('第 1 步有行业卡可点', false)
    }
    await page.waitForTimeout(1200)

    // goStep 的「只能前进一格」守卫：在第 1 步点第 3 步应被拒绝，停留在第 1 步
    await page.locator('.steps-nav .step-node').nth(2).click()
    await page.waitForTimeout(900)
    const guard = (await page.locator('.action-bar .step-indicator').first().textContent()).trim()
    console.log(`    第 1 步时点第 3 步 → 停留 ${JSON.stringify(guard)}`)
    check('goStep 拒绝跳步（第 1 步点第 3 步无效）', guard === '第 1 步 / 共 10 步', JSON.stringify(guard))
    await page.keyboard.press('Escape')
    await page.waitForTimeout(400)

    // 第 2 步：点平台卡 → saveStep2（写入 platform_id 并重载选项）
    await page.locator('.steps-nav .step-node').nth(1).click()
    await page.waitForTimeout(900)
    const card2 = page.locator('.step-content .platform-select-list .platform-card').first()
    if (await card2.count()) {
      await card2.click()
      check('点平台卡触发 saveStep2（出现「已选择平台」提示）', await waitToast('已选择平台'))
      check('平台卡出现选中态', (await page.locator('.step-content .platform-card.selected').count()) > 0)
    } else {
      check('第 2 步有平台卡可点', false)
    }
    await page.waitForTimeout(1200)

    // 落库校验：saveDraft 是**留在视图里**的那一个函数，必须确认它真把数据写回去了。
    // ⚠️ 后端**没有** `GET /production/{id}` 单任务接口（`productionApi.get` 是死代码：
    // 无路由也无调用方），所以只能从列表里找。
    const persisted = (await api.get(`/production?industry_id=${seeded.industryId}`) || []).find(
      (t) => t.id === seeded.taskId,
    )
    if (!persisted) {
      check('任务仍在列表中（saveDraft 未把它改坏）', false)
    } else {
      console.log(`    落库：platform_id=${persisted.platform_id} snapshot=${JSON.stringify(persisted.platform_snapshot)} 标题=${JSON.stringify(persisted.title)}`)
      check('saveDraft 把 platform_id 写回后端', Number(persisted.platform_id) === Number(seeded.platformId), `期望 ${seeded.platformId}，实际 ${persisted.platform_id}`)
      // platform_snapshot 造数时刻意留空，只有「点平台卡」这一步会写它 ——
      // 所以它非空就证明 saveStep2 → saveDraft 这条链路真的落库了。
      check('saveDraft 把 platform_snapshot 写回后端（证明 saveStep2 落库）', !!String(persisted.platform_snapshot || '').trim(), JSON.stringify(persisted.platform_snapshot))
      check('saveDraft 未破坏标题', persisted.title === MARK, JSON.stringify(persisted.title))
    }

    // 第 3 步：点账号卡 → saveStep3Account（写入 account_id）
    await page.locator('.steps-nav .step-node').nth(2).click()
    await page.waitForTimeout(1500)
    const accList = page.locator('.step-content .persona-layout .persona-list').first()
    const accCard = accList.locator('.persona-card').first()
    if (await accCard.count()) {
      await accCard.click()
      await page.waitForTimeout(1200)
      const accSel = await accList.locator('.persona-card.selected').count()
      console.log(`    账号卡选中数=${accSel}`)
      check('点账号卡出现选中态（saveStep3Account 生效）', accSel > 0)
    } else {
      check('第 3 步渲染出账号卡（非空态）', false)
    }

    // 第 4 步：顺路经过（goStep 只允许 +1，跳过它会让后面的点击全部被拒）
    await page.locator('.steps-nav .step-node').nth(3).click()
    await page.waitForTimeout(900)

    // 第 5 步：点关键词 chip → toggleKeyword（勾选态）
    await page.locator('.steps-nav .step-node').nth(4).click()
    await page.waitForTimeout(1800)
    const chip = page.locator('.step-content .keyword-pool .keyword-chip').first()
    if (await chip.count()) {
      await chip.click()
      await page.waitForTimeout(700)
      const selChips = await page.locator('.step-content .keyword-pool .keyword-chip.selected').count()
      console.log(`    关键词 chip 选中数=${selChips}`)
      check('点关键词 chip 出现选中态（toggleKeyword 生效）', selChips === 1, `实际 ${selChips}`)
    } else {
      check('第 5 步有关键词 chip 可点', false)
    }

    // 第 6 步 ↔ 上一步/下一步按钮
    await page.locator('.steps-nav .step-node').nth(5).click()
    await page.waitForTimeout(900)
    await page.getByRole('button', { name: '上一步' }).first().click()
    await page.waitForTimeout(900)
    const afterPrev = await page.locator('.action-bar .step-indicator').first().textContent()
    await page.getByRole('button', { name: '下一步' }).first().click()
    await page.waitForTimeout(1500)
    const afterNext = await page.locator('.action-bar .step-indicator').first().textContent()
    console.log(`    上一步 → ${JSON.stringify(afterPrev.trim())}；下一步 → ${JSON.stringify(afterNext.trim())}`)
    check('「上一步」回到第 5 步', afterPrev.trim() === '第 5 步 / 共 10 步', JSON.stringify(afterPrev.trim()))
    check('「下一步」回到第 6 步', afterNext.trim() === '第 6 步 / 共 10 步', JSON.stringify(afterNext.trim()))

    // ================= 第 6 步：证明页面级弹窗真的能被打开 =================
    // 上面只证明了 5 个弹窗**挂载**了。这里走一遍真实链路（父 → 子组件 props → v-model → 弹窗），
    // 确认拆分后 prop / emit 的接线没有断。
    await page.locator('.steps-nav .step-node').nth(5).click()
    await page.waitForTimeout(1200)
    const verBtn = page.getByRole('button', { name: '历史版本' }).first()
    if (!(await verBtn.count())) {
      check('找到「历史版本」按钮', false)
    } else {
      await verBtn.click()
      await page.waitForTimeout(1200)
      await page.screenshot({ path: `${OUT}/D6-生产-版本历史弹窗.png` })
      console.log(`✓ 生产页（版本历史弹窗）→ ${OUT}/D6-生产-版本历史弹窗.png`)
      const dlg = await page.evaluate(() => {
        return {
          visible: !!document.querySelector('.el-dialog'),
          title: (document.querySelector('.el-dialog__title') || {}).textContent || '',
          body: (document.querySelector('.el-dialog .empty-tip, .el-dialog .version-list') || {}).className || '',
        }
      })
      console.log(`    弹窗标题=${JSON.stringify(dlg.title.trim())} 内容=${JSON.stringify(dlg.body)}`)
      check('「历史版本」弹窗打开', dlg.visible)
      check('弹窗标题正确', dlg.title.trim() === '历史版本', JSON.stringify(dlg.title.trim()))
      check('弹窗内容区渲染（空态或列表）', dlg.body === 'empty-tip' || dlg.body.includes('version-list'), JSON.stringify(dlg.body))
      await page.keyboard.press('Escape')
      await page.waitForTimeout(600)
    }
    // ================= 第 9 步：验证「函数型 prop」真的接上了 =================
    // 结构断言只能证明「组件挂上了」。函数 prop 没传进来时组件**照样渲染**，
    // 只有点下去才会炸（TypeError: xxx is not a function）。
    // 所以这里造一段最终正文，点「本地快速体检」，断言评分结果真的渲染出来 ——
    // 这一条覆盖了 runLocalGeoScore / hasFinalContent / saveDraft 三个接线点。
    await api.put(`/production/${seeded.taskId}`, { current_step: 9, final_content: GEO_SAMPLE })
    await page.reload({ waitUntil: 'networkidle', timeout: 30000 })
    await page.waitForTimeout(2000)
    await page.locator('.task-panel .task-card', { hasText: MARK }).first().click()
    await page.waitForTimeout(2500)

    const probeBtn = page.getByRole('button', { name: '本地快速体检' }).first()
    if (!(await probeBtn.count())) {
      check('找到「本地快速体检」按钮', false)
    } else {
      check('「本地快速体检」按钮已启用（hasFinalContent 生效）', !(await probeBtn.isDisabled()))
      await probeBtn.click()
      await page.waitForTimeout(3500)
      await page.screenshot({ path: `${OUT}/D6-生产-GEO体检结果.png`, fullPage: true })
      console.log(`✓ 生产页（GEO 体检结果）→ ${OUT}/D6-生产-GEO体检结果.png`)
      const geo = await page.evaluate(() => ({
        body: !!document.querySelector('.geo-gate__body'),
        // 算法信任维度（6 个）与心智温度维度（5 个）用的是同一个 .geo-dim 类，
        // 靠父容器区分：.geo-dims 与 .geo-dims--mind
        algoDims: document.querySelectorAll('.geo-gate__body .geo-dims:not(.geo-dims--mind) .geo-dim').length,
        mindDims: document.querySelectorAll('.geo-gate__body .geo-dims--mind .geo-dim').length,
        diagnosis: !!document.querySelector('.geo-diagnosis'),
        scoreTag: (document.querySelector('.geo-gate__actions .el-tag') || {}).textContent || '',
      }))
      console.log(`    GEO 结果体=${geo.body} 算法维度=${geo.algoDims} 心智维度=${geo.mindDims} 诊断横幅=${geo.diagnosis} 分数标签=${JSON.stringify(geo.scoreTag.replace(/\s+/g, ' ').trim())}`)
      check('GEO 体检返回并渲染结果体', geo.body)
      check('GEO 算法信任六维渲染', geo.algoDims === 6, `实际 ${geo.algoDims}`)
      check('GEO 心智温度五维渲染', geo.mindDims === 5, `实际 ${geo.mindDims}`)
      check('双信任诊断横幅渲染', geo.diagnosis)
      check('综合分标签渲染', /综合分\s*[\d.]+\s*\/\s*100/.test(geo.scoreTag), JSON.stringify(geo.scoreTag.trim()))
    }
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
  if (warns.length) {
    console.log('\n⚠️ 未解析组件 / 未定义引用告警（拆组件丢 import 的典型症状）：')
    warns.slice(0, 5).forEach((e) => console.log('  ' + e))
    if (warns.length > 5) console.log(`  … 另有 ${warns.length - 5} 条同类告警`)
    process.exitCode = 1
  }
  if (failed) {
    console.log(`\n❌ ${failed} 项结构断言失败。`)
    process.exitCode = 1
  } else if (!errs.length && !warns.length) {
    console.log('\n✅ 全部结构断言通过，无运行时错误。')
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
