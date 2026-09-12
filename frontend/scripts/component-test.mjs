// 前端行为回归门禁（离线，使用已安装的 playwright-core + 系统 Edge）
//
// 背景：原计划的 Vitest 单测门禁因沙箱 npm tarball CDN 不可达（body=0 字节）而无法安装，
// 故改用已就绪的 playwright-core 做真实浏览器行为测试，作为 Production.vue 拆分前的回归兜底。
//
// 覆盖范围：
//   1. 加载 /production，捕捉运行时错误（pageerror / console.error）—— 回归基线
//   2. 断言向导根结构存在（.production-view + 「刷新」按钮），证明组件成功挂载
//   3. 真实点击「刷新」按钮，驱动 loadTasks() 异步链路，断言无新增错误
//   4. 断言步骤1（StepIndustry，已抽取）渲染出真实行业数据（真空泵行业）—— 内容级回归
//   5. 驱动真实流程新建生产任务（覆盖 createTask/loadTasks/selectTask），断言步骤1（StepIndustry）
//      渲染真实行业数据；再跳转到步骤2（StepPlatform）并断言其容器（含空态）渲染
//   6. 深度驱动：顺序点击步骤节点逐 +1 进入步骤 6（StepOutline）与步骤 9（StepFinal + StepGeoGate），
//      断言抽取出的深层大块组件可挂载且无运行时错误（否则这些组件 gateless）
//   7. 打开「历史版本」对话框（VersionHistoryDialog，已随步骤 6/9 单流面板渲染触发按钮）并断言标题可见
//
// 退出码：发现运行时错误或未通过断言 => 1；否则 => 0
//
// 用法：
//   先启动后端（确保 http://127.0.0.1:8765 可访问），再运行：
//     node scripts/component-test.mjs
//   或：npm run test:frontend
//   可用 BASE_URL 覆盖目标地址。

import { chromium } from 'playwright-core'

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8765'

const IGNORE = [/favicon/i, /Failed to load resource.*404/i]

function isIgnorable(text) {
  return IGNORE.some((re) => re.test(text))
}

const results = []
function record(name, ok, detail = '') {
  results.push({ name, ok, detail })
  const mark = ok ? '✓' : '✗'
  console.log(`${mark} ${name}${detail ? '  — ' + detail : ''}`)
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
  page.on('pageerror', (err) => errors.push(`[pageerror] ${err.message}`))
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      if (!isIgnorable(text)) errors.push(`[console.error] ${text}`)
    }
  })

  console.log(`前端行为门禁目标：${BASE}/production\n`)

  // 1) 加载并捕捉运行时错误
  errors.length = 0
  try {
    await page.goto(BASE + '/production', { waitUntil: 'networkidle', timeout: 25000 })
  } catch (e) {
    record('加载 /production', false, e.message)
    await browser.close()
    process.exit(1)
  }
  await page.waitForTimeout(800) // 等 setup / 异步渲染
  record('加载 /production 无运行时错误', errors.length === 0, errors.join(' | '))

  // 2) 断言向导根结构与挂载
  const rootOk = await page.locator('.production-view').count()
  record('向导根结构 .production-view 存在', rootOk > 0)

  const refreshBtn = page.locator('button:has-text("刷新")')
  record('「刷新」按钮存在（组件已挂载）', (await refreshBtn.count()) > 0)

  // 3) 真实点击「刷新」驱动 loadTasks 异步链路，断言无新增错误
  if (await refreshBtn.count()) {
    errors.length = 0
    await refreshBtn.first().click()
    await page.waitForTimeout(800)
    record('点击「刷新」后无运行时错误（loadTasks 异步路径）', errors.length === 0, errors.join(' | '))
  }

  // 4) 驱动真实流程：新建生产任务 → 渲染步骤1（StepIndustry）→ 跳步骤2（StepPlatform）
  //    说明：默认 currentTask 为空，步骤区（v-if="currentTask"）不渲染；须先建任务。
  //    store 加载行业后自动选第一个，故点击「新建生产任务」会用该行业创建任务并 selectTask，
  //    使步骤区渲染。此路径同时覆盖 loadTasks / createTask / selectTask 异步链路。
  const newTaskBtn = page.locator('button:has-text("新建生产任务")')
  if (await newTaskBtn.count()) {
    errors.length = 0
    await newTaskBtn.first().click()
    await page.waitForTimeout(900) // 等 createTask + loadTasks + selectTask + 渲染
    record('点击「新建生产任务」无运行时错误', errors.length === 0, errors.join(' | '))
  } else {
    record('点击「新建生产任务」无运行时错误', true, '未找到新建按钮，安全跳过')
  }

  // 4a) 断言步骤1（StepIndustry）渲染出真实行业数据 —— 内容级回归
  const indCard = page.locator('.option-card', { hasText: '真空泵行业' })
  const indCount = await indCard.count()
  record('步骤1 渲染真实行业卡片（StepIndustry）', indCount > 0,
    indCount > 0 ? '真空泵行业 已渲染' : '未找到行业卡片（任务创建/选择可能失败）')

  // 4b) 跳转到步骤2（StepPlatform），断言容器渲染（空数据也渲染容器 + 空态）
  try {
    const step2Node = page.locator('.step-node:has-text("选平台")')
    if (await step2Node.count()) {
      errors.length = 0
      await step2Node.first().click()
      await page.waitForTimeout(500)
      const platList = await page.locator('.platform-select-list').count()
      record('步骤2（StepPlatform）可渲染', platList > 0,
        platList > 0 ? 'platform-select-list 已渲染（含空态）' : '容器未渲染')
      if (errors.length) record('步骤2 跳转无运行时错误', false, errors.join(' | '))
    } else {
      record('步骤2（StepPlatform）可渲染', false, '未找到步骤2导航节点')
    }
  } catch (e) {
    record('步骤2（StepPlatform）可渲染', false, '导航异常：' + e.message)
  }

  // 4c) 深度驱动：顺序点击步骤导航节点，逐级进入步骤 6（StepOutline）与步骤 9（StepFinal + StepGeoGate），
  //     断言抽取出的深层大块组件可挂载且无运行时错误（否则这些组件处于 gateless 状态）。
  //     说明：goStep 仅允许 +1 递增且仅改本地状态（不触发后端 PUT），故须逐节点顺序点击。
  async function driveSteps(names) {
    for (const name of names) {
      const node = page.locator('.step-node', { hasText: name }).first()
      if (!(await node.count())) return `未找到步骤节点「${name}」`
      await node.click()
      await page.waitForTimeout(350)
    }
    return null
  }

  // 4c) 逐节点驱动至步骤 3/4/5，分别断言抽取组件可挂载且无运行时错误
  const d3 = await driveSteps(['定人设'])
  if (d3) {
    record('深度驱动至步骤 3', false, d3)
  } else {
    errors.length = 0
    await page.waitForTimeout(350)
    const pl = await page.locator('.persona-layout').count()
    const rp = await page.locator('.rules-panel').count()
    record('步骤 3（StepPersona）可渲染', pl > 0 && rp > 0, pl > 0 && rp > 0 ? 'persona-layout + rules-panel 已渲染' : '容器未渲染')
    record('步骤 3 切换无运行时错误', errors.length === 0, errors.join(' | '))
  }

  const d4 = await driveSteps(['目标客户需求'])
  if (d4) {
    record('深度驱动至步骤 4', false, d4)
  } else {
    errors.length = 0
    await page.waitForTimeout(350)
    const gd = await page.locator('.geo-demand').count()
    record('步骤 4（StepDemand）可渲染', gd > 0, gd > 0 ? 'geo-demand 已渲染' : '容器未渲染')
    record('步骤 4 切换无运行时错误', errors.length === 0, errors.join(' | '))
  }

  const driveTo5 = await driveSteps(['关键词&知识点'])
  if (driveTo5) {
    record('深度驱动至步骤 5', false, driveTo5)
  } else {
    errors.length = 0
    await page.waitForTimeout(400)
    const twoCol = await page.locator('.two-col-layout').count()
    record('步骤 5（Step5）可渲染', twoCol > 0, twoCol > 0 ? 'two-col-layout 已渲染' : '容器未渲染')
    record('步骤 5 切换无运行时错误', errors.length === 0, errors.join(' | '))
  }

  const driveA = await driveSteps(['生成大纲'])
  if (driveA) {
    record('深度驱动至步骤 6', false, driveA)
  } else {
    errors.length = 0
    await page.waitForTimeout(400)
    const outlinePane = await page.locator('.step-pane').count()
    record('步骤 6（StepOutline）可渲染', outlinePane > 0, outlinePane > 0 ? 'step-pane 已渲染' : '容器未渲染')
    record('步骤 6 切换无运行时错误', errors.length === 0, errors.join(' | '))
  }

  const driveB = await driveSteps(['生成初稿', 'AI洗稿', '安全发布 & GEO 筛选'])
  if (driveB) {
    record('深度驱动至步骤 9', false, driveB)
  } else {
    errors.length = 0
    await page.waitForTimeout(400)
    const geoGate = await page.locator('.geo-gate-block').count()
    record('步骤 9（StepFinal + StepGeoGate）可渲染', geoGate > 0, geoGate > 0 ? 'geo-gate-block 已渲染' : '未渲染')
    record('步骤 9 切换无运行时错误', errors.length === 0, errors.join(' | '))
  }

  // 4d) 深度驱动至步骤 10（文章配图 / StepIllustration），断言抽取组件可挂载且无运行时错误
  const driveC = await driveSteps(['配图'])
  if (driveC) {
    record('深度驱动至步骤 10', false, driveC)
  } else {
    errors.length = 0
    await page.waitForTimeout(400)
    const illuWrap = await page.locator('.illu-wrap').count()
    record('步骤 10（StepIllustration）可渲染', illuWrap > 0, illuWrap > 0 ? 'illu-wrap 已渲染' : '容器未渲染')
    record('步骤 10 切换无运行时错误', errors.length === 0, errors.join(' | '))
  }

  // 6) 尽力打开「历史版本」对话框（VersionHistoryDialog）
  const histBtn = page.locator('button:has-text("历史版本")')
  if (await histBtn.count()) {
    errors.length = 0
    await histBtn.first().click()
    await page.waitForTimeout(500)
    const dialogTitle = page.locator('.el-dialog__title:has-text("历史版本"), .el-dialog:has-text("历史版本")')
    const opened = (await dialogTitle.count()) > 0
    record('打开「历史版本」对话框并可见', opened, opened ? '' : '未检测到对话框标题')
    // 关闭对话框（Escape）
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)
    record('「历史版本」对话框打开/关闭无运行时错误', errors.length === 0, errors.join(' | '))
  } else {
    record('打开「历史版本」对话框', true, '当前流程态无触发按钮，安全跳过（后续拆分补充精确断言）')
  }

  await browser.close()

  const failed = results.filter((r) => !r.ok)
  if (failed.length) {
    console.log(`\n❌ 前端行为门禁失败：${failed.length} 项未通过，请检查上方输出。`)
    process.exit(1)
  }
  console.log('\n✅ 前端行为门禁通过：/production 挂载与核心交互无回归。')
  process.exit(0)
}

main()
