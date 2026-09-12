@echo off
chcp 65001 >nul
title 多行业提示词矩阵管理系统 v1.0.0

cd /d "%~dp0backend"

if not exist "venv\Scripts\activate.bat" (
    echo [错误] 未找到虚拟环境 venv，请先运行 init_env.bat
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo ============================================================
echo   多行业提示词矩阵管理系统 v1.0.0
echo ============================================================
echo   服务地址: http://127.0.0.1:8765
echo   API文档:  http://127.0.0.1:8765/docs
echo   默认账号: admin / admin123
echo ============================================================
echo   浏览器将自动打开，如未打开请手动访问上述地址
echo   服务异常退出会自动重启（守护模式）；彻底停止请关闭本窗口
echo ============================================================

REM 启动前先清理占用 8765 端口的旧进程，避免端口冲突导致启动失败
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
    echo [守护] 发现占用 8765 的旧进程 PID=%%p，正在结束...
    taskkill /F /PID %%p >nul 2>&1
)

:guard_loop
python run.py
echo.
echo [守护] 服务已退出（退出码 %errorlevel%），3 秒后自动重启... 若为手动停止，请直接关闭本窗口。
timeout /t 3 /nobreak >nul
goto guard_loop
