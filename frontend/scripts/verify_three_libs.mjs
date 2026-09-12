import { chromium } from 'playwright-core'

const BASE = 'http://localhost:8765'
const fail = []
const result = {}

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage()
const errors = []
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', e => errors.push(String(e)))

try {
  // 提示词库：确认新模板渲染数量
  await page.goto(BASE + '/prompt-library', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  result.promptCards = await page.locator('.prompt-item').count()
  result.dualTrustVisible = await page.getByText('双信任', { exact: false }).count()
  result.expertVisible = await page.getByText('专家人设', { exact: false }).count()

  // 知识库：确认一键灌入默认论据按钮
  await page.goto(BASE + '/knowledge', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  result.knowledgeSeedBtn = await page.getByRole('button', { name: '一键灌入默认论据' }).count()

  // 规则库：加载无错
  await page.goto(BASE + '/rule', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1000)
  result.ruleLoaded = await page.getByText('三大规则库', { exact: false }).count()

  result.runtimeErrors = errors
} catch (e) {
  fail.push('异常: ' + e.message)
} finally {
  await browser.close()
}

console.log(JSON.stringify(result, null, 2))
if (result.promptCards < 30) fail.push('提示词卡片数偏少: ' + result.promptCards)
if (result.knowledgeSeedBtn < 1) fail.push('知识库缺少一键灌入默认论据按钮')
if (errors.length) fail.push('运行时错误: ' + errors.length)
console.log(fail.length ? 'FAIL: ' + fail.join(' | ') : 'ALL PASS')
