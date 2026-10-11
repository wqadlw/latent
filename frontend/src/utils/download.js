/**
 * 文件下载 —— 全站统一实现。
 *
 * 为什么集中：这段「造 Blob → createObjectURL → 造 <a> → click → revoke」的样板
 * 在 7 个文件里逐字复制过。它有三个容易抄漏的点，集中一次就只需要对一次：
 *
 * 1. **必须 revokeObjectURL**，否则每下载一次就泄漏一份 Blob 内存直到刷新页面。
 *    有几种抄法把 `a.href` 直接传给 revoke（能工作，因为 a.href 会读回绝对 URL），
 *    但可读性差、且一旦中间改过 a.href 就 revoke 错对象。
 * 2. **`<a>` 不必挂到 document 上**——现代浏览器 `a.click()` 即可触发下载。
 * 3. **CSV 的 BOM**：Excel 读 UTF-8 CSV 时不认 BOM 就会把中文显示成乱码，
 *    所以导出 CSV 必须在开头写 `\uFEFF`。
 */

/** 触发一次浏览器下载 */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/** 下载纯文本（默认 UTF-8） */
export function downloadText(text, filename, mime = 'text/plain;charset=utf-8') {
  downloadBlob(new Blob([text], { type: mime }), filename)
}

/** 下载 JSON（自动缩进，便于人工查看/二次编辑） */
export function downloadJson(data, filename) {
  downloadBlob(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }), filename)
}

/**
 * 把二维数组转成 CSV 文本。
 * 每个单元格用双引号包裹、内部双引号转义为两个——这是 RFC 4180 的做法，
 * 能正确处理内容里含逗号/换行/引号的情况。
 */
export function toCsv(rows) {
  return rows
    .map(r => r.map(c => `"${(c ?? '').toString().replace(/"/g, '""')}"`).join(','))
    .join('\n')
}

/**
 * 下载 CSV。默认加 BOM，否则 Excel 打开中文会乱码。
 * @param {Array<Array>} rows 二维数组（含表头行）
 * @param {string} filename
 * @param {boolean} [withBom=true]
 */
export function downloadCsv(rows, filename, withBom = true) {
  const csv = toCsv(rows)
  downloadBlob(new Blob([(withBom ? '\uFEFF' : '') + csv], { type: 'text/csv;charset=utf-8' }), filename)
}
