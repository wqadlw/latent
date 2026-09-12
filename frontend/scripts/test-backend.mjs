// 后端单元测试门禁：定位 backend/venv 的 Python，运行 pytest。
// 任一用例失败即退出码 1，令 build:check 整体失败。
// 用法： node scripts/test-backend.mjs   （通常由 npm run build:check 触发）
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const backendDir = resolve(__dirname, '..', '..', 'backend')

// 优先用 venv 内的解释器（Windows: Scripts/python.exe；POSIX: bin/python），回退系统 python
const candidates = [
  resolve(backendDir, 'venv', 'Scripts', 'python.exe'),
  resolve(backendDir, 'venv', 'bin', 'python'),
]
let py = candidates.find(p => existsSync(p)) || (process.platform === 'win32' ? 'python' : 'python3')

console.log('[test:backend] python =', py)
console.log('[test:backend] cwd    =', backendDir)

const r = spawnSync(py, ['-m', 'pytest', '-q'], {
  cwd: backendDir,
  stdio: 'inherit',
})

if (r.error) {
  console.error('[test:backend] 无法启动 pytest：', r.error.message)
  process.exit(1)
}
process.exit(r.status ?? 1)
