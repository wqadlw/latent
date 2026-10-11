// 提示词库（D6-3 拆分）的视觉 + 结构验收。
//
// 与 shot-production.mjs / shot-knowledge.mjs 同源：**先造标记数据 → 断言 → 清理**。
// 只截图不断言 = 假绿（D4 的教训：组件拆出去后 prop 没传进来，页面会静默退化成空状态，
// 那也是一张「正常」的截图）。
//
// 本脚本覆盖的是**拆 PromptLibrary.vue 时最容易坏的那些结构**：
//   1. hero 三个指标、分类卡（5 类）、提示词列表真的渲染出卡片
//   2. 编辑器弹窗：三栏骨架（变量面板 / 编辑器）、变量分组、元提示词折叠区
//   3. 点变量 → 真的插进内容框（函数 prop 接线）
//   4. 变量检测回填（`detected-vars` 出现，且不含未解析告警）
//   5. **编辑既有提示词** → 表单与自定义变量被载入（openEdit / initialCustomVars 接线）
//   6. **保存** → 编辑器抛出的 `variable_schema` 真的落库（save(payload) 新签名）
//   7. 只读查看抽屉：打开 / 复制全文（关抽屉 + 使用次数 +1）/ 转编辑
//   8. **批量导入** → doImport(payload) 新签名、弹窗重置、成功提示文案非空
//
// 用法：node scripts/shot-prompt-library.mjs
// 依赖：后端已在 8765 运行。

import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'
const OUT = process.env.OUT_DIR || '../docs/screenshots'
const USER = process.env.SMOKE_USER || 'admin'
const PASS = process.env.SMOKE_PASS || 'admin123'
const INDUSTRY = Number(process.env.SMOKE_INDUSTRY || 1)

const MARK = '__D6_PL_VERIFY__'
const IMPORT_MARK = MARK + '_IMP'
const PROBE_VAR = 'd6_probe_var'
const EDITED_DESC = MARK + '_EDITED'
// 用一个内置变量，确保变量检测走的是白名单分支（不触发未解析告警）
const CONTENT = `# 角色\n你是一位资深的{industry_name}行业内容专家。\n\n# 任务\n围绕「{keywords}」写一篇面向{platform_name}的大纲。`
const SEED_DESC = 'D6-3 验收用，跑完即删'

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
  const post = async (p, body) => await (await fetch(BASE + '/api' + p, { method: 'POST', headers: h, body: JSON.stringify(body) })).json()
  const put = async (p, body) => await (await fetch(BASE + '/api' + p, { method: 'PUT', headers: h, body: JSON.stringify(body) })).json()
  const del = async (p) => (await (await fetch(BASE + '/api' + p, { method: 'DELETE', headers: h })).json())
  return { get, post, put, del }
}

/** 从列表接口里按 id 取单条（后端没有 GET /prompt-library/{id} 这个路由）。 */
async function getItem(api, id) {
  const list = await api.get(`/prompt-library?industry_id=${INDUSTRY}`)
  return (list || []).find((p) => p.id === id) || null
}

/**
 * 幂等造数：确保 outline 分类下有一条**状态已知**的标记提示词。
 *
 * ⚠️ 命中已有行时也要**刷回标准状态**，不能直接返回：
 * 上一次跑崩了可能留下被本脚本改过的内容（比如验收写进去的探针变量），
 * 那样断言就会「碰巧通过」—— 起点不确定的造数等于没有造数。
 */
async function seed(api) {
  const ids = { promptIds: [], importIds: [] }
  const canonical = {
    name: MARK,
    category: 'outline',
    content: CONTENT,
    description: SEED_DESC,
    tags: 'verify',
    is_default: 0,
    // ⚠️ 卡片上展示的是 `variables`（自动检测到的变量），**不是** `variable_schema`（自定义变量定义）。
    // 这两个字段容易混：只写 variable_schema 的话卡片变量区会是空的。
    variables: ['industry_name', 'keywords', 'platform_name'],
    variable_schema: [{ name: 'brand_name', desc: '品牌名' }],
    industry_id: INDUSTRY,
  }
  const list = await api.get(`/prompt-library?industry_id=${INDUSTRY}`)
  const hit = (list || []).find((p) => p.name === MARK)
  if (hit) {
    await api.put(`/prompt-library/${hit.id}`, { ...canonical, id: hit.id })
    ids.promptId = hit.id
    return ids
  }
  const r = await api.post('/prompt-library', canonical)
  if (r.data && r.data.id) {
    ids.promptIds.push(r.data.id)
    ids.promptId = r.data.id
  }
  return ids
}

async function cleanup(api, ids) {
  // 后端 DELETE 是软删除（is_deleted=1），墓碑会留在库里；页面上看不到残留。
  for (const id of [...(ids.promptIds || []), ...(ids.importIds || [])]) {
    await api.del(`/prompt-library/${id}`).catch(() => {})
  }
}

async function main() {
  const { token, user } = await login()
  console.log(`登录成功：${user.username}（${user.role}）`)

  const api = makeClient(token)

  // ⚠️ 造数必须在 try 里面：中途失败时若在 try 外，finally 的 cleanup 不会跑，标记数据会永久残留。
  let seeded = { promptIds: [], importIds: [] }

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  // 抽屉的「复制全文」走 navigator.clipboard（127.0.0.1 属安全上下文，会走这条分支），
  // headless 下必须显式授权，否则 writeText 抛异常 → copyContent 返回 false → 抽屉不关，
  // 断言会红得莫名其妙（那是环境问题，不是代码问题）。
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE })

  const errs = []
  const warns = []
  page.on('pageerror', (e) => errs.push('[pageerror] ' + e.message))
  page.on('console', (m) => {
    const t = m.text()
    if (m.type() === 'error') errs.push('[console] ' + t)
    // Vue 对「模板里引用了未注册组件」只发 warn，页面不报错、那一块静默消失 —— 必须单独捕获。
    if (m.type() === 'warning' && /Failed to resolve (component|directive)|is not defined|not defined on instance/.test(t)) {
      warns.push('[console] ' + t.split('\n')[0])
    }
  })

  /** 最近一条 ElMessage 的文本（toast 是全局挂载的，不在页面组件树里）。 */
  const lastToast = () =>
    page.evaluate(() => {
      const els = document.querySelectorAll('.el-message')
      const el = els[els.length - 1]
      return el ? el.querySelector('.el-message__content')?.textContent || '' : ''
    })

  const dialogOpen = () =>
    page.evaluate(() => {
      const el = document.querySelector('.el-dialog')
      return !!el && el.getBoundingClientRect().width > 0
    })

  const drawerOpen = () =>
    page.evaluate(() => {
      const el = document.querySelector('.el-drawer')
      return !!el && el.getBoundingClientRect().width > 0
    })

  try {
    seeded = await seed(api)
    console.log(`已就绪标记数据：promptId=${seeded.promptId}（新建 ${JSON.stringify(seeded.promptIds)}）\n`)

    /**
     * 关掉当前弹窗。
     * ⚠️ 不要用 `Escape`：Element Plus 的 el-dialog 关掉后**仍留在 DOM 里**（v-show），
     * 而 Escape 在某些焦点位置不会生效 —— 弹窗没关时后面那些卡片点击会被遮罩拦掉，
     * Playwright 报的却是「被 sidebar 拦截」，极难排查。所以点「取消」按钮并等它真的不可见。
     */
    async function closeDialog() {
      const cancel = page.getByRole('button', { name: '取消' }).first()
      if (await cancel.count()) await cancel.click().catch(() => {})
      await page.waitForTimeout(1500)
      check('编辑器弹窗已关闭', !(await dialogOpen()))
    }

    await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
    await page.evaluate(
      ([t, u, ind]) => {
        localStorage.setItem('acm_token', t)
        localStorage.setItem('acm_user', JSON.stringify(u))
        localStorage.setItem('currentIndustryId', String(ind))
      },
      [token, user, INDUSTRY],
    )

    await page.goto(BASE + '/prompt-library', { waitUntil: 'networkidle', timeout: 30000 })
    await page.waitForTimeout(2500)
    await page.screenshot({ path: `${OUT}/D6-提示词库-主视图.png`, fullPage: true })
    console.log(`✓ 提示词库主视图 → ${OUT}/D6-提示词库-主视图.png`)

    // 标记卡片：后续所有卡片交互都限定在它里面，避免列表顺序变化导致点错。
    const markerCard = page.locator('.prompt-item').filter({ hasText: MARK }).first()

    console.log('  主视图结构断言：')
    const shell = await page.evaluate(() => ({
      view: !!document.querySelector('.prompt-library-view'),
      hero: !!document.querySelector('.hero'),
      metrics: document.querySelectorAll('.hero .metric').length,
      catCards: document.querySelectorAll('.category-grid .category-card').length,
      activeCat: (document.querySelector('.category-card.is-active .cat-name') || {}).textContent || '',
      items: document.querySelectorAll('.prompt-list .prompt-item').length,
      banner: !!document.querySelector('.batch-import-banner'),
    }))
    console.log(`    view=${shell.view} hero=${shell.hero} 指标=${shell.metrics} 分类卡=${shell.catCards} 提示词卡=${shell.items}`)
    check('prompt-library-view 渲染', shell.view)
    check('hero 渲染', shell.hero)
    check('三个指标渲染', shell.metrics === 3, `实际 ${shell.metrics}`)
    check('5 个分类卡渲染', shell.catCards === 5, `实际 ${shell.catCards}`)
    check('默认选中「大纲类提示词」', shell.activeCat.trim() === '大纲类提示词', JSON.stringify(shell.activeCat.trim()))
    check('批量导入横幅渲染', shell.banner)
    check('提示词列表渲染出卡片（非空态）', shell.items > 0, `实际 ${shell.items}`)

    // 卡片内容断言：证明卡片不是空壳
    const card = await page.evaluate(() => {
      const el = document.querySelector('.prompt-list .prompt-item')
      if (!el) return null
      return {
        name: (el.querySelector('.prompt-item__name') || {}).textContent || '',
        preview: (el.querySelector('.prompt-item__preview-text') || {}).textContent || '',
        varTags: el.querySelectorAll('.prompt-item__vars .var-tag').length,
        actions: el.querySelectorAll('.prompt-item__actions .el-button').length,
      }
    })
    console.log(`    首卡：名称=${JSON.stringify((card?.name || '').trim())} 变量标签=${card?.varTags} 操作按钮=${card?.actions}`)
    check('首卡名称正确', (card?.name || '').trim() === MARK, JSON.stringify((card?.name || '').trim()))
    check('首卡渲染提示词预览文本', (card?.preview || '').includes('行业内容专家'))
    check('首卡渲染变量标签', (card?.varTags || 0) > 0, `实际 ${card?.varTags}`)
    check('首卡 5 个操作按钮', card?.actions === 5, `实际 ${card?.actions}`)

    // 操作行不能溢出卡片。
    // ⚠️ 这是一条**真实缺陷**的回归护栏：卡片是 `minmax(300px, 1fr)` 自适应列宽，
    // 窄列装不下 5 个按钮时，`justify-content: flex-end` 会把整行**向左**溢出卡片，
    // 第一个按钮「查看」会跑到侧边栏底下被盖住 —— 用户点不到，而且页面上没有任何报错。
    const overflow = await page.evaluate(() => {
      const item = document.querySelector('.prompt-list .prompt-item')
      const acts = item?.querySelector('.prompt-item__actions')
      if (!item || !acts) return null
      const i = item.getBoundingClientRect()
      const a = acts.getBoundingClientRect()
      const first = acts.querySelector('.el-button')?.getBoundingClientRect()
      return {
        leftGap: Math.round(a.left - i.left),
        rightGap: Math.round(i.right - a.right),
        firstBtnLeftGap: first ? Math.round(first.left - i.left) : null,
      }
    })
    console.log(`    操作行相对卡片：左 ${overflow?.leftGap}px 右 ${overflow?.rightGap}px；首按钮左 ${overflow?.firstBtnLeftGap}px`)
    check(
      '操作行未溢出卡片（否则首个按钮会被侧边栏盖住）',
      overflow && overflow.leftGap >= 0 && overflow.rightGap >= -1 && overflow.firstBtnLeftGap >= 0,
      JSON.stringify(overflow),
    )

    // ⚠️ 样式必须单独验：共享样式表是**非 scoped** 的，漏掉 import 时页面结构完全正常、
    // 上面所有结构断言照样全绿，但整页会退化成无样式的裸 HTML。
    // 只有「算出来的样式」能发现这种失败 —— 这是共享样式接线的唯一护栏。
    //
    // 注意这条护栏的**边界**：CSS 一旦被任一组件 import 就是全局生效的，
    // 所以它验证的是「整张表有没有被加载」，**不能**发现「5 个组件里漏了 1 个 import」
    // （那在今天的构建产物里是无害的）。要改成单点引入时，先想清楚这个边界。
    const styles = await page.evaluate(() => {
      const item = document.querySelector('.prompt-list .prompt-item')
      const acts = item?.querySelector('.prompt-item__actions')
      if (!item || !acts) return null
      return {
        borderLeft: getComputedStyle(item).borderLeftWidth,
        actionsDisplay: getComputedStyle(acts).display,
        actionsWrap: getComputedStyle(acts).flexWrap,
      }
    })
    console.log(`    计算样式：border-left=${styles?.borderLeft} actions.display=${styles?.actionsDisplay} flex-wrap=${styles?.actionsWrap}`)
    check(
      '共享样式表已生效（prompt-library-shared.css 已 import）',
      styles?.borderLeft === '3px',
      JSON.stringify(styles),
    )
    check(
      '操作行 flex + wrap 未回退（真实缺陷的修复仍生效）',
      styles?.actionsDisplay === 'flex' && styles?.actionsWrap === 'wrap',
      JSON.stringify(styles),
    )

    // ================= 编辑器弹窗（新建） =================
    const newBtn = page.getByRole('button', { name: '新建提示词' }).first()
    if (!(await newBtn.count())) {
      check('找到「新建提示词」按钮', false)
    } else {
      await newBtn.click()
      await page.waitForTimeout(1500)
      await page.screenshot({ path: `${OUT}/D6-提示词库-编辑器.png` })
      console.log(`✓ 提示词库编辑器 → ${OUT}/D6-提示词库-编辑器.png`)

      console.log('  编辑器结构断言：')
      const ed = await page.evaluate(() => ({
        dialog: !!document.querySelector('.el-dialog'),
        layout: !!document.querySelector('.editor-layout'),
        varPanel: !!document.querySelector('.var-panel'),
        editorCenter: !!document.querySelector('.editor-center'),
        varGroups: document.querySelectorAll('.var-panel .var-group').length,
        varItems: document.querySelectorAll('.var-panel .var-item').length,
        metaBox: !!document.querySelector('.meta-prompt-box'),
        metaBodyVisible: (() => {
          const el = document.querySelector('.meta-prompt-body')
          return !!el && el.style.display !== 'none'
        })(),
      }))
      console.log(`    dialog=${ed.dialog} 三栏=${ed.layout} 变量面板=${ed.varPanel} 编辑器=${ed.editorCenter} 变量组=${ed.varGroups} 变量项=${ed.varItems}`)
      check('编辑器弹窗打开', ed.dialog)
      check('编辑器三栏布局渲染', ed.layout)
      check('变量面板渲染', ed.varPanel)
      check('编辑器中栏渲染', ed.editorCenter)
      check('变量分组渲染（≥1 组）', ed.varGroups >= 1, `实际 ${ed.varGroups}`)
      check('变量项渲染（来自后端白名单）', ed.varItems > 5, `实际 ${ed.varItems}`)
      check('元提示词折叠区渲染', ed.metaBox)
      check('元提示词默认收起', !ed.metaBodyVisible)

      // 展开元提示词：断言内容真的来自 constants（长度足够、含关键段落）
      await page.locator('.meta-prompt-head').first().click()
      await page.waitForTimeout(800)
      const mp = await page.evaluate(() => {
        const ta = document.querySelector('.meta-prompt-body textarea')
        return { visible: !!ta, len: ta ? ta.value.length : 0, hasRole: !!ta && ta.value.includes('# 角色(Role)') }
      })
      console.log(`    元提示词：textarea=${mp.visible} 长度=${mp.len} 含「# 角色(Role)」=${mp.hasRole}`)
      check('展开后元提示词 textarea 渲染', mp.visible)
      check('元提示词内容完整（>2000 字）', mp.len > 2000, `实际 ${mp.len}`)
      check('元提示词含四段式标题', mp.hasRole)
      await page.locator('.meta-prompt-head').first().click()
      await page.waitForTimeout(400)

      // 点变量 → 真的插进内容框
      const varItem = page.locator('.var-panel .var-item').first()
      const varKey = (await varItem.locator('.var-item-key').first().textContent()).trim()
      await varItem.click()
      await page.waitForTimeout(1200)
      const afterInsert = await page.evaluate(() => {
        const ta = document.querySelector('.editor-center textarea')
        return {
          value: ta ? ta.value : '',
          detected: document.querySelectorAll('.detected-vars .dv-tag').length,
          unresolvedAlert: !!document.querySelector('.unresolved-alert'),
        }
      })
      console.log(`    点变量 ${varKey} → 内容框含该变量=${afterInsert.value.includes(varKey)} 检测到变量=${afterInsert.detected} 未解析告警=${afterInsert.unresolvedAlert}`)
      check('点变量插入到内容框（insertVariable 生效）', afterInsert.value.includes(varKey))
      check('变量检测回填（detectVariables 生效）', afterInsert.detected > 0, `实际 ${afterInsert.detected}`)
      check('白名单变量不触发未解析告警', !afterInsert.unresolvedAlert)

      // 「本类默认变量」一键灌入
      const injectBtn = page.getByRole('button', { name: '本类默认变量' }).first()
      if (await injectBtn.count()) {
        await injectBtn.click()
        await page.waitForTimeout(1000)
        const afterInject = await page.evaluate(() => {
          const ta = document.querySelector('.editor-center textarea')
          return ta ? ta.value : ''
        })
        console.log(`    灌入后内容长度=${afterInject.length} 含 {knowledge_content}=${afterInject.includes('{knowledge_content}')}`)
        check('「本类默认变量」灌入生效', afterInject.includes('{knowledge_content}'))
      } else {
        check('找到「本类默认变量」按钮', false)
      }

      await closeDialog()
    }

    // ================= 编辑既有提示词（openEdit / initialCustomVars / save(payload)） =================
    const editBtn = markerCard.locator('.prompt-item__actions .el-button', { hasText: '编辑' }).first()
    if (!(await editBtn.count())) {
      check('找到「编辑」按钮', false)
    } else {
      await editBtn.click()
      await page.waitForTimeout(1800)
      console.log('  编辑既有提示词断言：')
      const ed2 = await page.evaluate(() => {
        const dlg = document.querySelector('.el-dialog')
        if (!dlg) return null
        const items = dlg.querySelectorAll('.prompt-form .el-form-item')
        return {
          title: (dlg.querySelector('.el-dialog__title') || {}).textContent || '',
          name: items[0]?.querySelector('input')?.value ?? null,
          desc: items[2]?.querySelector('input')?.value ?? null,
          content: dlg.querySelector('.prompt-form textarea')?.value ?? null,
          customVars: [...dlg.querySelectorAll('.var-panel .custom-var-item')].map(
            (r) => r.querySelector('input')?.value || '',
          ),
        }
      })
      console.log(`    标题=${JSON.stringify(ed2?.title.trim())} 名称=${JSON.stringify(ed2?.name)} 自定义变量=${JSON.stringify(ed2?.customVars)}`)
      check('编辑模式标题正确（editing prop 生效）', (ed2?.title || '').trim() === '编辑提示词', JSON.stringify(ed2?.title))
      check('表单载入被编辑项的名称（openEdit 填 form）', ed2?.name === MARK, JSON.stringify(ed2?.name))
      check('表单载入被编辑项的描述', ed2?.desc === SEED_DESC, JSON.stringify(ed2?.desc))
      check('表单载入被编辑项的内容', (ed2?.content || '').includes('行业内容专家'))
      // 这一条是 initialCustomVars 的唯一护栏：schema 存在后端 JSON 列里，
      // 不在打开弹窗时读出来，用户一保存就会把它清空（静默数据丢失）。
      check(
        '自定义变量按 variable_schema 载入（initialCustomVars 接线）',
        (ed2?.customVars || []).length === 1 && ed2.customVars[0] === 'brand_name',
        JSON.stringify(ed2?.customVars),
      )

      // 追加一个探针变量 + 改描述，用来证明 save(payload) 真的把这些写回了后端
      const addVarBtn = page.getByRole('button', { name: '添加' }).first()
      if (await addVarBtn.count()) {
        await addVarBtn.click()
        await page.waitForTimeout(500)
        const rows = page.locator('.var-panel .custom-var-item')
        const lastRow = rows.last()
        await lastRow.locator('input').first().fill(PROBE_VAR)
        await lastRow.locator('input').nth(1).fill('D6 探针变量')
        await page.locator('.prompt-form .el-form-item').nth(2).locator('input').fill(EDITED_DESC)
        await page.waitForTimeout(300)

        const saveBtn = page.getByRole('button', { name: '保存' }).first()
        await saveBtn.click()
        await page.waitForTimeout(2500)
        const toast = await lastToast()
        console.log(`    保存 toast=${JSON.stringify(toast)}`)

        const row = await getItem(api, seeded.promptId)
        let vs = []
        try {
          vs = JSON.parse(row?.variable_schema || '[]')
        } catch {
          vs = []
        }
        const names = (Array.isArray(vs) ? vs : []).map((v) => v?.name || v)
        console.log(`    后端 variable_schema=${JSON.stringify(names)} 描述=${JSON.stringify(row?.description)}`)
        check('保存后弹窗关闭', !(await dialogOpen()))
        check('save(payload) 把探针自定义变量写回后端', names.includes(PROBE_VAR), JSON.stringify(names))
        check('save(payload) 保留了原有自定义变量', names.includes('brand_name'), JSON.stringify(names))
        check('save(payload) 把表单其它字段写回后端', row?.description === EDITED_DESC, JSON.stringify(row?.description))
      } else {
        check('找到「添加」自定义变量按钮', false)
      }
    }

    // ================= 只读查看抽屉（打开 / 复制全文 / 转编辑） =================
    const viewBtn = markerCard.locator('.prompt-item__actions .el-button', { hasText: '查看' }).first()
    if (await viewBtn.count()) {
      await viewBtn.click()
      await page.waitForTimeout(1200)
      await page.screenshot({ path: `${OUT}/D6-提示词库-查看抽屉.png` })
      console.log(`✓ 提示词库查看抽屉 → ${OUT}/D6-提示词库-查看抽屉.png`)
      const dr = await page.evaluate(() => ({
        drawer: !!document.querySelector('.el-drawer'),
        meta: document.querySelectorAll('.el-drawer .view-meta .el-tag').length,
        body: (document.querySelector('.el-drawer .view-body-text') || {}).textContent || '',
        vars: document.querySelectorAll('.el-drawer .view-vars .var-tag').length,
      }))
      console.log(`    抽屉=${dr.drawer} 元信息标签=${dr.meta} 变量标签=${dr.vars} 正文长度=${dr.body.length}`)
      check('查看抽屉打开', dr.drawer)
      check('抽屉渲染元信息标签', dr.meta > 0, `实际 ${dr.meta}`)
      check('抽屉渲染变量标签', dr.vars > 0, `实际 ${dr.vars}`)
      check('抽屉渲染提示词全文', dr.body.includes('行业内容专家'))

      // 复制全文 → 关抽屉 + 使用次数 +1（证明 onDrawerCopy → copyContent 接线）
      const before = (await getItem(api, seeded.promptId))?.usage_count || 0
      const copyBtn = page.locator('.el-drawer .view-foot .el-button', { hasText: '复制全文' }).first()
      if (await copyBtn.count()) {
        await copyBtn.click()
        await page.waitForTimeout(1800)
        const after = (await getItem(api, seeded.promptId))?.usage_count || 0
        console.log(`    使用次数 ${before} → ${after}`)
        check('抽屉「复制全文」后抽屉自动关闭（onDrawerCopy 接线）', !(await drawerOpen()))
        check('抽屉「复制全文」累加使用次数（copyContent 生效）', after === before + 1, `${before} → ${after}`)
      } else {
        check('找到抽屉「复制全文」按钮', false)
      }

      // 再开一次 → 点「编辑」应关抽屉并打开编辑器（onDrawerEdit 接线）
      await viewBtn.click()
      await page.waitForTimeout(1200)
      const drawerEditBtn = page.locator('.el-drawer .view-foot .el-button', { hasText: '编辑' }).first()
      if (await drawerEditBtn.count()) {
        await drawerEditBtn.click()
        await page.waitForTimeout(1800)
        const st = await page.evaluate(() => {
          const d = document.querySelector('.el-drawer')
          const dlg = document.querySelector('.el-dialog')
          return {
            drawerVisible: !!d && d.getBoundingClientRect().width > 0,
            dialogVisible: !!dlg && dlg.getBoundingClientRect().width > 0,
            title: (document.querySelector('.el-dialog__title') || {}).textContent || '',
          }
        })
        console.log(`    抽屉可见=${st.drawerVisible} 编辑器可见=${st.dialogVisible} 标题=${JSON.stringify(st.title.trim())}`)
        check('抽屉「编辑」后抽屉关闭（onDrawerEdit 接线）', !st.drawerVisible)
        check('抽屉「编辑」打开了编辑器', st.dialogVisible)
        check('抽屉「编辑」打开的是编辑模式', st.title.trim() === '编辑提示词', JSON.stringify(st.title))
        await closeDialog()
      } else {
        check('找到抽屉「编辑」按钮', false)
      }
    } else {
      check('找到「查看」按钮', false)
    }

    // ================= 批量导入（doImport(payload) / 弹窗重置 / 成功文案） =================
    const importBtn = page.locator('.batch-import-banner .el-button', { hasText: '批量导入' }).first()
    if (!(await importBtn.count())) {
      check('找到批量导入按钮', false)
    } else {
      await importBtn.click()
      await page.waitForTimeout(1200)
      console.log('  批量导入断言：')
      const ta = page.locator('textarea[placeholder^="JSON数组格式"]')
      const payload = JSON.stringify([
        { name: IMPORT_MARK, category: 'outline', content: '导入验证：{industry_name} 的 {keywords}', description: 'D6-3 导入验收', tags: 'verify' },
      ])
      await ta.fill(payload)
      await page.getByRole('button', { name: '导入', exact: true }).first().click()
      await page.waitForTimeout(2500)

      const toast = await lastToast()
      const afterImport = await page.evaluate(() => {
        const t = document.querySelector('textarea[placeholder^="JSON数组格式"]')
        return { value: t ? t.value : null }
      })
      const imported = (await api.get(`/prompt-library?industry_id=${INDUSTRY}`) || []).find(
        (p) => p.name === IMPORT_MARK,
      )
      if (imported) seeded.importIds.push(imported.id)

      console.log(`    toast=${JSON.stringify(toast)} 输入框残留长度=${afterImport.value?.length}`)
      check('导入的提示词已落库（doImport(payload) 接线）', !!imported, imported ? `id=${imported.id}` : '未找到')
      check('导入后弹窗关闭', !(await dialogOpen()))
      // ⚠️ 后端 `POST /import` 的文案在**顶层** `msg`，不在 `data.msg`。
      // 取值写错不会报错，只会弹一个没有文字的绿色 toast —— 用户看到「导入成功了个寂寞」。
      check(
        '导入成功提示文案非空（res.msg 取值正确）',
        /成功导入/.test(toast),
        JSON.stringify(toast),
      )
      check('导入后弹窗输入被重置（importDialogRef.reset）', afterImport.value === '', JSON.stringify(afterImport.value))
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
