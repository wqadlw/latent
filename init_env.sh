#!/usr/bin/env bash
# 环境初始化脚本 - Linux/Mac
set -e
cd "$(dirname "$0")/backend"

echo "============================================================"
echo "  多行业提示词矩阵管理系统 v2.0.0 - 环境初始化"
echo "============================================================"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 python3，请先安装 Python 3.9+"
    exit 1
fi

echo "[1/3] 正在创建虚拟环境..."
python3 -m venv venv

echo "[2/3] 正在激活虚拟环境并升级 pip..."
source venv/bin/activate
pip install --upgrade pip -q

echo "[3/3] 正在安装依赖包..."
pip install -r requirements.txt -q

echo ""
echo "============================================================"
echo "  环境初始化完成！"
echo "  请运行 bash start.sh 启动系统"
echo "============================================================"
