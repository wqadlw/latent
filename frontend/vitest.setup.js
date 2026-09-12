import { vi } from 'vitest'
import { config } from '@vue/test-utils'
import ElementPlus from 'element-plus'

// Element Plus 全量注册（与 main.js 一致），保证 el-* 组件在单测中可渲染（含 dialog/drawer teleport）
config.global.plugins.push(ElementPlus)

// happy-dom 缺失的浏览器 API polyfill（Element Plus 内部会用到，避免挂载即抛错）
class NoopObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return [] }
}
if (!globalThis.ResizeObserver) globalThis.ResizeObserver = NoopObserver
if (!globalThis.IntersectionObserver) globalThis.IntersectionObserver = NoopObserver
if (!globalThis.matchMedia) {
  globalThis.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() { return false }
  }))
}
