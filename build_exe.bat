@echo off
chcp 65001 >nul
title 打包 Latent.exe

cd /d "%~dp0"

echo ============================================================
echo   打包 显影 Latent（企业级 GEO 运营系统）为单文件 exe
echo ============================================================

REM ---------- 前置检查 ----------
if not exist "backend\venv\Scripts\python.exe" (
    echo [错误] 未找到后端虚拟环境 backend\venv，请先运行 init_env.bat
    pause
    exit /b 1
)

REM ---------- 1/3 构建前端（产物落 backend\static） ----------
echo.
echo [1/3] 正在构建前端...
cd frontend
if not exist "node_modules" (
    echo   未检测到 node_modules，正在安装前端依赖...
    call npm install
)
call npm run build
if errorlevel 1 (
    echo [错误] 前端构建失败
    cd ..
    pause
    exit /b 1
)
cd ..

REM ---------- 2/3 确保 pyinstaller 已安装 ----------
echo.
echo [2/3] 正在检查 PyInstaller...
backend\venv\Scripts\python.exe -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo   正在安装 PyInstaller...
    backend\venv\Scripts\python.exe -m pip install pyinstaller -q
)

REM ---------- 3/3 打包 ----------
echo.
echo [3/3] 正在打包 exe（首次较慢，请耐心等待）...
cd backend
venv\Scripts\python.exe -m PyInstaller --noconfirm Latent.spec
if errorlevel 1 (
    echo [错误] 打包失败
    cd ..
    pause
    exit /b 1
)
cd ..

echo.
echo ============================================================
echo   打包完成！
echo   产物: backend\dist\Latent.exe
echo   当前 database.db 中的数据已作为「种子」随 exe 一起打包，
echo   首次运行时自动还原到 exe 旁边的 data\database.db。
echo   复制到其他电脑：Latent.exe 一个文件即可。
echo ============================================================
pause
