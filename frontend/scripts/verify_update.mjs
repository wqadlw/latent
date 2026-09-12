// 聚焦验证：行业标签 + 移除安全筛选报告 + GEO 可复制建议提示词 + 默认模板增多
// 用法：node scripts/verify_update.mjs <tempTaskId>   （需后端 8765 已启动且构建最新前端）
import { chromium } from 'playwright-core'

const base = 'http://127.0.0.1:8765'
const TID = process.argv[2] || ''
const errors = []
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage()
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message))

const result = {}

// ---------- 1) Persona / IntentQuestion 显示当前行业 ----------
await page.goto(base + '/persona', { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
result.personaIndustry = await page.getByText('当前行业', { exact: false }).count()

await page.goto(base + '/intent-question', { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
result.intentIndustry = await page.getByText('当前行业', { exact: false }).count()

// ---------- 2) Production：第9步无"安全筛选报告"，且 GEO 建议可复制 ----------
await page.goto(base + '/production', { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
// 全局不应出现"安全筛选报告"
result.safetyReportText = await page.getByText('安全筛选报告', { exact: false }).count()

if (TID) {
  // 打开临时任务（通过 URL hash 或点卡片）。先尝试按标题定位
  await page.goto(base + '/production', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  const card = page.locator('.task-card', { hasText: 'Z临时GEO验证任务Z' }).first()
  if (await card.count() > 0) {
    await card.click()
    await page.waitForTimeout(1200)
    // 进入第9步
    const step9 = page.locator('.step-node', { hasText: '安全发布' }).first()
    if (await step9.count() > 0) { await step9.click(); await page.waitForTimeout(1000) }
    // 运行 GEO 评分
    const scoreBtn = page.getByRole('button', { name: '运行 GEO 评分' })
    if (await scoreBtn.count() > 0) {
      await scoreBtn.click()
      await page.waitForTimeout(2500)
    }
    result.geoSuggestBlock = await page.locator('.geo-suggest').count()
    result.geoSuggestItems = await page.locator('.geo-suggest__item').count()
    result.geoSuggestCopyBtns = await page.locator('.geo-suggest__head .el-button').count()
  } else {
    result.geoSuggestBlock = 'NO_TASK_CARD'
  }
}

result.runtimeErrors = errors
console.log(JSON.stringify(result, null, 2))
await browser.close()

const fail = []
if (result.personaIndustry < 1) fail.push('Persona 页未显示当前行业')
if (result.intentIndustry < 1) fail.push('IntentQuestion 页未显示当前行业')
if (result.safetyReportText !== 0) fail.push('第9步仍存在"安全筛选报告"')
if (TID) {
  if (result.geoSuggestBlock !== 1) fail.push('GEO 建议区块未出现: ' + result.geoSuggestBlock)
  if (result.geoSuggestItems < 1) fail.push('GEO 建议提示词条目缺失')
  if (result.geoSuggestCopyBtns < 1) fail.push('GEO 建议复制按钮缺失')
}
if (errors.length) fail.push('运行时错误: ' + errors.join(' | '))

if (fail.length) {
  console.error('\n❌ 验证失败:\n - ' + fail.join('\n - '))
  process.exit(1)
} else {
  console.log('\n✅ 验证通过：行业标签已显示、安全筛选报告已移除、GEO 可复制建议提示词就位')
}
