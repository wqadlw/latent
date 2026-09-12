import { chromium } from 'playwright-core'

const BASE = process.env.SMOKE_URL || 'http://127.0.0.1:8765'
const URL = BASE + '/knowledge'

const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error' && !/favicon|404/.test(m.text())) errors.push('CONSOLE: ' + m.text()) })

await page.goto(URL, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)

// 统计知识点卡片数量与首行列数
const stats = await page.evaluate(() => {
  const cards = Array.from(document.querySelectorAll('.item-card'))
  const rows = Array.from(document.querySelectorAll('.item-row'))
  // 通过首行卡片的 offsetTop 判断一行几列
  let cols = 0
  if (cards.length) {
    const top = cards[0].offsetTop
    cols = cards.filter((c) => c.offsetTop === top).length
  }
  // 检查是否有卡片内容被裁切（scrollHeight > clientHeight 且 overflow hidden）
  const cropped = cards.filter((c) => {
    const cs = getComputedStyle(c)
    return cs.overflow === 'hidden' && c.scrollHeight > c.clientHeight + 1
  }).length
  const gridList = document.querySelector('.item-list.grid')
  const gridCols = gridList ? getComputedStyle(gridList).gridTemplateColumns.split(' ').length : 0
  return {
    cardCount: cards.length,
    rowCount: rows.length,
    firstRowCols: cols,
    computedGridCols: gridCols,
    croppedCards: cropped,
    itemListWidth: gridList ? Math.round(gridList.clientWidth) : 0,
  }
})

console.log('VERIFY', JSON.stringify(stats, null, 2))
await page.screenshot({ path: 'knowledge-verify.png', fullPage: false })
console.log('errors:', errors.length ? errors : 'none')
await browser.close()
