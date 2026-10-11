/**
 * Markdown → 纯文本（前端轻量版）。
 *
 * 用途：平台过审 / 直接复制场景下，把 Markdown 标记剥掉但**保留段落结构**，
 * 让运营能把内容直接粘进不支持 Markdown 的平台。
 *
 * 为什么不用第三方库：这里只需要「去标记」而不是「渲染」，正则足够且零依赖；
 * 引入 marked/remark 反而会带来 XSS 面与打包体积。
 * 已知取舍：不做完整 CommonMark 解析（嵌套引用、HTML 块等按字面处理），
 * 因为输入是我们自己产出的受控文章，不是任意外部 Markdown。
 */

/**
 * @param {string} md Markdown 原文
 * @returns {string} 纯文本
 */
export function markdownToPlain(md) {
  if (!md) return ''
  let t = md
  // 代码块：去掉围栏但保留内容
  t = t.replace(/```[\s\S]*?```/g, m => m.replace(/```/g, '').trim())
  // 行内代码
  t = t.replace(/`([^`]+)`/g, '$1')
  // 标题 #~###### → 保留文字
  t = t.replace(/^#{1,6}\s*/gm, '')
  // 粗体 / 斜体
  t = t.replace(/\*\*(.+?)\*\*/g, '$1')
  t = t.replace(/__(.+?)__/g, '$1')
  t = t.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, '$1')
  // 链接 [text](url) → text
  t = t.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
  // 引用
  t = t.replace(/^>\s?/gm, '')
  // 无序列表 - * + → 换成中点，保留层级感
  t = t.replace(/^\s*[-*+]\s+/gm, '\u00b7 ')
  // 有序列表 1. → 保留文字
  t = t.replace(/^\s*\d+\.\s+/gm, '')
  // 分隔线
  t = t.replace(/^(\s*[-*_]){3,}\s*$/gm, '')
  // 表格分隔行
  t = t.replace(/^\s*\|?[\-: ]+\|[\-: |]+\|?\s*$/gm, '')
  // 表格列分隔
  t = t.replace(/(?<=\S)\s*\|\s*(?=\S)/g, ' | ')
  // 折叠多余空行
  t = t.replace(/\n{3,}/g, '\n\n')
  return t.trim()
}

export default markdownToPlain
