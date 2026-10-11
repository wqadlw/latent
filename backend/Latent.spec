# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置：把后端 + 前端静态资源打成单个 exe。

生成：backend/dist/Latent.exe
运行：双击 exe，首次运行时自动将种子数据库还原到 exe 同级目录的 data/database.db，
      后续启动使用已有数据库（数据持久化不会丢失）。浏览器自动打开 http://127.0.0.1:8765

重新打包：
    cd backend
    venv\\Scripts\\python.exe -m PyInstaller --noconfirm Latent.spec
或直接双击项目根目录的 build_exe.bat
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("static", "static"),               # 前端构建产物打进 exe（只读）
    ("data/database.db", "seed_data"),  # 当前数据库作为种子，首次运行时自动还原到 exe 旁
]
binaries = []
hiddenimports = []

# uvicorn[standard] / pydantic(含 rust 扩展 pydantic_core) 需要完整收集，避免运行期缺模块
for pkg in ("uvicorn", "pydantic", "pydantic_core"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# 确保 app 下所有子模块（routers/*）都被打进去
hiddenimports += collect_submodules("app")

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Latent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # 保留控制台窗口，便于看启动日志/报错
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
