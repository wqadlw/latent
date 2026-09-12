#!/usr/bin/env bash
# 多行业提示词矩阵管理系统 - Linux/Mac 启动脚本
# 注意：不使用 set -e，否则守护循环中 python 崩溃会直接退出脚本
cd "$(dirname "$0")/backend"

if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "[错误] 未找到虚拟环境 venv，请先运行初始化脚本"
    exit 1
fi

# 启动前清理占用 8765 端口的旧进程，避免端口冲突
OLD_PID=$(lsof -ti tcp:8765 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
    echo "[守护] 发现占用 8765 的旧进程 PID=$OLD_PID，正在结束..."
    kill -9 $OLD_PID 2>/dev/null || true
fi

echo "============================================================"
echo "  多行业提示词矩阵管理系统 v2.0.0"
echo "============================================================"
echo "  服务地址: http://127.0.0.1:8765"
echo "  API文档:  http://127.0.0.1:8765/docs"
echo "  默认账号: admin / admin123"
echo "============================================================"
echo "  浏览器将自动打开，如未打开请手动访问上述地址"
echo "  服务异常退出会自动重启（守护模式）；彻底停止请按 Ctrl+C"
echo "============================================================"

# Ctrl+C 干净退出守护循环，而非重启
trap 'echo; echo "[守护] 收到停止信号，退出。"; exit 0' INT TERM

while true; do
    python run.py
    code=$?
    echo
    echo "[守护] 服务已退出（退出码 $code），3 秒后自动重启... 按 Ctrl+C 可终止。"
    sleep 3
done
