/**
 * 剪贴板工具 —— 全站统一实现。
 *
 * 为什么必须统一：这段逻辑原本在 10 个文件里各抄了一份，而且抄歪成了三个版本
 * （有的带空值判断、有的带降级回退、有的连 label 都没有）。复制是高频动作，
 * 一旦某个版本在 http 环境下静默失败，用户只会觉得「这个按钮坏了」，
 * 排查成本远高于把它收成一份。
 *
 * 关键点：`navigator.clipboard` 只在**安全上下文**（https / localhost）可用。
 * 内网用 IP 访问（如 http://192.168.x.x:8765）时它是 undefined，
 * 所以必须有 textarea + execCommand 的降级路径，否则局域网部署下复制全挂。
 */
import { ElMessage } from 'element-plus'

/**
 * 只做「写入剪贴板」，不弹任何提示。返回是否成功。
 *
 * 给需要自定义成功文案的调用方用（如「已复制 搜狐 提问提示词，去粘贴提问吧」），
 * 这样它们也能拿到安全上下文降级能力，而不必被迫改成统一的提示语。
 *
 * @param {string} text
 * @returns {Promise<boolean>}
 */
export async function writeClipboard(text) {
  if (!text) return false
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      // 非安全上下文降级：clipboard API 不可用，用隐藏 textarea + execCommand
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    return true
  } catch (e) {
    return false
  }
}

/**
 * 复制文本到剪贴板，并弹出统一提示。
 *
 * @param {string} text  要复制的内容
 * @param {string} [label] 成功提示里显示的名字，如「标题」「MDX 代码」
 * @returns {Promise<boolean>} 是否复制成功
 */
export async function copyText(text, label = '') {
  if (!text) {
    ElMessage.warning('没有可复制的内容')
    return false
  }
  const ok = await writeClipboard(text)
  if (ok) ElMessage.success(label ? `已复制：${label}` : '已复制')
  else ElMessage.error('复制失败，请手动选择文本复制')
  return ok
}

export default copyText
