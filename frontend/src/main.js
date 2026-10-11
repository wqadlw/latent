import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import { ElMessageBox } from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import { writeClipboard } from './utils/clipboard'
import 'element-plus/dist/index.css'
import './styles/main.css'
import './styles/element-overrides.css'

// ===== 防御性兜底：拦截 setAttribute 的非法属性名（如 '0'）=====
// 某些第三方组件（element-plus）在更新分支里可能把数组下标当属性名，
// 触发 InvalidCharacterError 并冒泡为 Vue runtime-15，导致页面报错/白屏。
// 浏览器本就会拒绝这些非法属性名，这里直接在源头吞掉该错误并打印真实调用栈，
// 既消除崩溃，又保留定位线索（stack 中的组件名即为元凶）。
;(function patchSetAttributeGuard() {
  const _orig = Element.prototype.setAttribute
  Element.prototype.setAttribute = function (name, value) {
    try {
      return _orig.call(this, name, value)
    } catch (e) {
      if (e && e.name === 'InvalidCharacterError') {
        console.warn('[setAttribute 跳过非法属性名]', { name, value, stack: new Error().stack })
        return
      }
      throw e
    }
  }
})()

const app = createApp(App)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// ===== 全局错误兜底：捕获渲染/异步/生命周期中的异常，避免整页白屏，并展示真实报错便于定位 =====
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
// 良性「取消」判定：ElMessageBox.confirm 在用户点「取消」/按 ESC/点 X 时会
// reject 出字符串 'cancel' / 'close'（少数场景是同名 message 的对象）。这属于
// 正常交互流程，不是错误，必须在全局兜底里直接忽略，否则会冒泡成 Vue runtime-6
// （出错组件 ElButton、错误信息 cancel）并弹出报错框，干扰用户。
function isBenignCancel(err) {
  const v = (err && typeof err === 'object' && 'message' in err) ? err.message : err
  return v === 'cancel' || v === 'close'
}
// 同一条错误只弹一次，避免无限刷屏；全局熔断防止错误风暴把页面卡死
let __lastErrSig = ''
let __errCount = 0
let __errTotal = 0
const __ERR_MAX = 5
function showErrorOverlay(title, detail) {
  if (window.__DIAG_NO_OVERLAY__) { console.error('[DIAG]', title, '\n', detail); return }
  if (__errTotal >= __ERR_MAX) {
    console.error('[错误过多，已停止弹窗，仅打印]', title, '\n', detail)
    return
  }
  const sig = title + '|' + detail
  if (sig === __lastErrSig) {
    if (__errCount >= 3) return
  } else {
    __lastErrSig = sig
    __errCount = 0
  }
  __errCount++
  __errTotal++
  ElMessageBox.alert(
    '<pre style="white-space:pre-wrap;word-break:break-word;max-height:340px;overflow:auto;font-size:12px;line-height:1.7;margin:0;font-family:monospace;">' + escapeHtml(detail) + '</pre>',
    title,
    {
      dangerouslyUseHTMLString: true,
      confirmButtonText: '刷新重试',
      showCancelButton: true,
      cancelButtonText: '复制报错',
      callback: (action) => {
        if (action === 'confirm') {
          window.location.reload()
        } else if (action === 'cancel') {
          // 复制报错到剪贴板。writeClipboard 本身不弹提示、失败静默返回 false，
          // 正好符合「全局错误弹窗里不再叠一层 toast」的诉求，用户仍可手动选中文本。
          writeClipboard(detail)
        }
      },
    }
  ).catch(() => {})
}

// 1) 渲染 / 生命周期 / watcher 中的异常（Vue 接不住时由下面 window 监听兜底）
app.config.errorHandler = (err, instance, info) => {
  // 用户在确认框点「取消」不是错误，直接忽略
  if (isBenignCancel(err)) return
  const compName =
    instance?.$options?.name ||
    instance?.$options?.__name ||
    instance?.type?.name ||
    '匿名组件（生产构建可能丢失名字）'
  const compFile = instance?.$options?.__file || ''
  console.error('[全局渲染错误] 组件=', compName, '文件=', compFile, 'info=', info, err)
  const msg = err && err.message ? err.message : String(err)
  const detail = [
    '发生位置(info)：' + info,
    '出错组件：' + compName + (compFile ? (' (' + compFile + ')') : ''),
    '错误信息：' + msg,
    err && err.stack ? ('堆栈：\n' + err.stack) : '(无堆栈信息)'
  ].join('\n\n')
  showErrorOverlay('页面渲染出错（请把下方内容截图/复制反馈）', detail)
}

// 2) 路由懒加载失败：发版后旧标签页哈希 chunk 失效时自动刷新一次自愈（防死循环）
router.onError((err) => {
  console.error('[路由错误]', err)
  const msg = (err && err.message) ? err.message : ''
  const isChunkError = msg.includes('Failed to fetch dynamically imported module')
    || msg.includes('Importing a module script failed')
    || msg.includes('error loading dynamically imported module')
  if (isChunkError && !window.__chunk_reload__) {
    window.__chunk_reload__ = true
    window.location.reload()
    return
  }
  showErrorOverlay('页面加载失败', '路由加载失败：\n' + msg)
})

// 3) 最后一道防线：未被 Vue 接住的全局错误 / 未处理的 Promise 拒绝
window.addEventListener('error', (e) => {
  const msg = (e.error && e.error.message) || e.message || ''
  // 良性噪声：Element Plus 等组件在 ResizeObserver 回调中触发布局变更时，
  // 浏览器会抛 "ResizeObserver loop completed with undelivered notifications."（无堆栈）。
  // 这不影响任何功能，属 Chrome 已知良性通知，直接忽略，避免误弹错误框干扰用户。
  if (msg.includes('ResizeObserver loop')) {
    console.debug('[忽略良性 ResizeObserver 循环通知]', msg)
    return
  }
  const err = e.error || e
  console.error('[全局未捕获错误]', err)
  showErrorOverlay(
    '脚本运行出错',
    ['错误信息：' + msg, err && err.stack ? ('堆栈：\n' + err.stack) : '(无堆栈信息)'].join('\n\n')
  )
})
window.addEventListener('unhandledrejection', (e) => {
  const reason = e.reason
  // 确认框取消导致的 promise 拒绝属正常流程，忽略且阻止其继续冒泡
  if (isBenignCancel(reason)) { e.preventDefault(); return }
  console.error('[未处理的 Promise 拒绝]', reason)
  const msg = reason && reason.message ? reason.message : String(reason)
  showErrorOverlay(
    '异步任务出错',
    ['错误信息：' + msg, reason && reason.stack ? ('堆栈：\n' + reason.stack) : '(无堆栈信息)'].join('\n\n')
  )
})

app.mount('#app')
