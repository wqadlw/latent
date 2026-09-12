// 聚焦验证：第4步重设计 + 移除 geo-rail + 移除变量中心
// 用法：node scripts/verify_step4.mjs  （需后端 8765 已启动并提供新构建的前端）
import { chromium } from 'playwright-core'

const base = 'http://127.0.0.1:8765'
const errors = []
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage()
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message))

const result = {}

// ---------- 1) Production：无 geo-rail，任务卡 GEO 徽标存在 ----------
await page.goto(base + '/production', { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
result.geoRailCount = await page.locator('.geo-rail').count()
result.taskBadges = await page.locator('.geo-score-badge').count()

// 打开第一个任务 → 进入第4步
const firstTask = page.locator('.task-card').first()
if (await firstTask.count() > 0) {
  await firstTask.click()
  await page.waitForTimeout(1200)
  const step4 = page.locator('.step-node', { hasText: '目标客户需求' }).first()
  if (await step4.count() > 0) {
    await step4.click()
    await page.waitForTimeout(1000)
  }
  result.step4NeedsForm = await page.locator('.geo-demand__needs').count()
  result.step4SignalPreview = await page.locator('.geo-signal-preview').count()
  result.step4PainChecks = await page.locator('.geo-demand__needs .el-checkbox').count()
  result.step4SaveBtn = await page.getByRole('button', { name: '保存需求' }).count()
}

// ---------- 2) PromptLibrary：无变量中心，变量面板保留 ----------
await page.goto(base + '/prompt-library', { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
result.vcItemCount = await page.locator('.vc-item').count()
result.varCenterBtn = await page.getByText('变量中心', { exact: true }).count()
// 变量面板在「新建/编辑提示词」对话框内，需打开编辑器才能看到
const createBtn = page.getByRole('button', { name: '新建提示词' })
if (await createBtn.count() > 0) {
  await createBtn.click()
  await page.waitForTimeout(1000)
}
result.varPanel = await page.locator('.var-panel').count()
result.injectDefaultsBtn = await page.getByRole('button', { name: '本类默认变量' }).count()
result.geoVarGroup = await page.locator('.var-group--geo').count()

result.runtimeErrors = errors
console.log(JSON.stringify(result, null, 2))
await browser.close()

// 断言
const fail = []
if (result.geoRailCount !== 0) fail.push('geo-rail 仍存在')
if (result.taskBadges < 1) fail.push('任务卡 GEO 徽标缺失')
if (result.step4NeedsForm !== 1) fail.push('第4步需求表单缺失')
if (result.step4SignalPreview < 1) fail.push('第4步信号预览缺失')
if (result.step4PainChecks < 1) fail.push('第4步痛点勾选项缺失')
if (result.step4SaveBtn !== 1) fail.push('第4步保存按钮缺失')
if (result.vcItemCount !== 0) fail.push('变量中心 .vc-item 仍存在')
if (result.varCenterBtn !== 0) fail.push('变量中心按钮仍存在')
if (result.varPanel < 1) fail.push('变量面板被误删（对话框内）')
if (result.injectDefaultsBtn < 1) fail.push('一键灌入本类默认变量按钮被误删')
if (errors.length) fail.push('存在运行时错误: ' + errors.join(' | '))

if (fail.length) {
  console.error('\n❌ 验证失败:\n - ' + fail.join('\n - '))
  process.exit(1)
} else {
  console.log('\n✅ 验证通过：geo-rail 已移除、第4步需求设计师就位、变量中心已移除且变量面板保留')
}
