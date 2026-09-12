// 聚焦验证：第2步平台选择重设计（特性/规则/账号人设绑定）+ 选平台后第3步按平台过滤账号
import { chromium } from 'playwright-core'
const base = 'http://127.0.0.1:8765'
const errors = []
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage()
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message))

const result = {}

// 1) 创建临时任务（第2步），拿到 id（用 node 原生 fetch）
const createRes = await fetch(base + '/api/production', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ industry_id: 4, title: 'Z临时平台验证Z', current_step: 2 })
})
const createJson = await createRes.json()
const tid = createJson.data.id

try {
  await page.goto(base + '/production', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)
  const card = page.locator('.task-card', { hasText: 'Z临时平台验证Z' }).first()
  await card.click()
  await page.waitForTimeout(1500)

  // 第2步面板
  result.platformCards = await page.locator('.platform-card').count()
  result.has特性 = await page.getByText('平台特性', { exact: false }).count()
  result.has规则 = await page.getByText('平台规则', { exact: false }).count()
  result.has账号人设 = await page.getByText('账号人设', { exact: false }).count()
  // 搜狐号卡片应展示其绑定账号 + 人设
  const sxCard = page.locator('.platform-card', { hasText: '搜狐号' }).first()
  result.souhuHasAccount = (await sxCard.getByText('真空机械小王', { exact: false }).count()) > 0
  result.souhuHasPersona = (await sxCard.getByText('技术专家老王', { exact: false }).count()) > 0
  // 合规等级以标签形式出现（不再是唯一信息）
  result.complianceTag = await page.locator('.platform-tags .el-tag', { hasText: '合规等级' }).count()

  // 2) 选搜狐号 → 第3步账号应按平台过滤为 1 个
  await sxCard.click()
  await page.waitForTimeout(1500)
  const step3 = page.locator('.step-node', { hasText: '定人设' }).first()
  await step3.click()
  await page.waitForTimeout(1500)
  // 第3步左侧为账号列表（第一个 persona-section）
  const acctSection = page.locator('.persona-section').first()
  result.step3AccountCards = await acctSection.locator('.persona-card').count()
  result.step3AccountShowsPersona = (await acctSection.getByText('技术专家老王', { exact: false }).count()) > 0

  // 3) 回到第2步选百家号（无账号）→ 第3步账号列表应为空
  const back2 = page.locator('.step-node', { hasText: '选平台' }).first()
  await back2.click()
  await page.waitForTimeout(800)
  const bhCard = page.locator('.platform-card', { hasText: '百家号' }).first()
  await bhCard.click()
  await page.waitForTimeout(1200)
  const step3b = page.locator('.step-node', { hasText: '定人设' }).first()
  await step3b.click()
  await page.waitForTimeout(1200)
  result.step3AccountAfterBaijia = await page.locator('.persona-section').first().locator('.persona-card').count()
} finally {
  await fetch(base + '/api/production/' + tid, { method: 'DELETE' })
}

result.runtimeErrors = errors
console.log(JSON.stringify(result, null, 2))

const fail = []
if (result.platformCards < 7) fail.push('平台卡片数不足: ' + result.platformCards)
if (!result.has特性) fail.push('未显示「平台特性」')
if (!result.has规则) fail.push('未显示「平台规则」')
if (!result.has账号人设) fail.push('未显示「账号人设」绑定')
if (!result.souhuHasAccount) fail.push('搜狐号未展示绑定账号 真空机械小王')
if (!result.souhuHasPersona) fail.push('搜狐号未展示绑定人设 技术专家老王')
if (!result.complianceTag) fail.push('合规等级未以标签形式呈现')
if (result.step3AccountCards < 1) fail.push('选搜狐号后第3步未过滤出账号')
if (!result.step3AccountShowsPersona) fail.push('第3步账号卡片未展示绑定人设 技术专家老王')
if (result.step3AccountAfterBaijia !== 0) fail.push('选百家号后第3步仍显示账号(应过滤为空): ' + result.step3AccountAfterBaijia)
if (errors.length) fail.push('运行时错误: ' + errors.join(' | '))

if (fail.length) { console.error('\n❌ 验证失败:\n - ' + fail.join('\n - ')); process.exit(1) }
else console.log('\n✅ 第2步平台重设计 + 账号人设绑定验证通过')
await browser.close()
