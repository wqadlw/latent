import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// 前端单测门禁配置（Vitest 2.x，happy-dom 环境，复用 vite 的 @ 别名）
// 激活条件：先安装 devDeps（vitest @vue/test-utils happy-dom），再 `npm run test:frontend`
// 该配置不参与 vite build（构建入口为 index.html，tests/ 与 vitest.* 不会被打入产物）
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./vitest.setup.js'],
    include: ['src/**/*.spec.js', 'tests/**/*.spec.js'],
    css: false,
  },
})
