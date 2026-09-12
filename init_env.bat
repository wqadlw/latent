@echo off
chcp 65001 >nul
title 初始化运行环境

cd /d "%~dp0backend"

echo ============================================================
echo   多行业提示词矩阵管理系统 - 环境初始化
echo ============================================================

REM 检查 Python
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+ 并添加到 PATH
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] 正在创建虚拟环境...
python -m venv venv
if errorlevel 1 (
    echo [错误] 虚拟环境创建失败
    pause
    exit /b 1
)

echo [2/3] 正在激活虚拟环境并升级 pip...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip -q

echo [3/3] 正在安装依赖包...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   环境初始化完成！
echo   请双击 start.bat 启动系统
echo ============================================================
pause
