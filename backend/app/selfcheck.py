"""
启动自检：在服务真正监听端口前，把「会让系统在运行中才炸掉」的环境问题提前报出来。

原则：**只报告、不阻断**（除端口占用外）。本地单机工具的使用者往往不是运维，
与其让他在某个页面点按钮时才看到 ImportError，不如启动时就说清楚缺什么、怎么补。
"""
from __future__ import annotations

import importlib
import os
import socket
import sys

from .paths import app_dir
from .version import APP_TITLE, __version__

# (模块名, 展示名, 是否必需)
_REQUIRED = [
    ("fastapi", "FastAPI", True),
    ("uvicorn", "Uvicorn", True),
    ("sqlalchemy", "SQLAlchemy", True),
    ("pydantic", "Pydantic", True),
    ("multipart", "python-multipart", True),
]
_OPTIONAL = [
    ("playwright", "Playwright（浏览器自动化发布，未安装则相关功能不可用）", False),
    ("cryptography", "cryptography（密钥加密存储，未安装则回退明文存储）", False),
    ("alembic", "Alembic（数据库版本化迁移）", False),
]

_STATUS_OK = "  [OK]  "
_STATUS_WARN = "  [!!]  "
_STATUS_FAIL = "  [XX]  "


def _check_port(host: str, port: int) -> bool:
    """检测端口是否已被占用（能连上说明有人监听）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) != 0


def _check_data_dir() -> tuple[bool, str]:
    """验证数据目录可写 —— 数据库、密钥、日志都落在这里。"""
    data_dir = os.path.join(app_dir(), "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
        probe = os.path.join(data_dir, ".write_probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        return True, data_dir
    except OSError as exc:
        return False, f"{data_dir}（{exc}）"


def run_selfcheck(host: str = "127.0.0.1", port: int = 8765) -> bool:
    """执行自检并打印报告。返回是否全部通过（端口占用视为不通过）。"""
    problems: list[str] = []
    print(f"\n[{APP_TITLE} v{__version__}] 启动自检")

    # 1) Python 版本
    if sys.version_info >= (3, 9):
        print(f"{_STATUS_OK}Python {sys.version.split()[0]}")
    else:
        print(f"{_STATUS_FAIL}Python {sys.version.split()[0]}（要求 >= 3.9）")
        problems.append("Python 版本过低")

    # 2) 依赖
    for module, label, required in _REQUIRED + _OPTIONAL:
        try:
            importlib.import_module(module)
            print(f"{_STATUS_OK}{label}")
        except ImportError:
            if required:
                print(f"{_STATUS_FAIL}{label} —— 缺失，请执行 pip install -r requirements.txt")
                problems.append(f"缺少必需依赖 {label}")
            else:
                print(f"{_STATUS_WARN}{label} —— 未安装")

    # 3) 数据目录
    ok, detail = _check_data_dir()
    print(f"{_STATUS_OK if ok else _STATUS_FAIL}数据目录可写：{detail}")
    if not ok:
        problems.append("数据目录不可写")

    # 4) 端口
    if _check_port(host, port):
        print(f"{_STATUS_OK}端口 {port} 可用")
    else:
        print(f"{_STATUS_FAIL}端口 {port} 已被占用 —— 可能有另一个实例在运行，"
              f"或改用 APP_PORT=<其它端口> 启动")
        problems.append(f"端口 {port} 被占用")

    # 5) 前端构建产物
    from .paths import resource_dir
    index_html = os.path.join(resource_dir(), "static", "index.html")
    if os.path.exists(index_html):
        print(f"{_STATUS_OK}前端构建产物已就绪")
    else:
        print(f"{_STATUS_WARN}前端未构建 —— 仅 API 可用，请在 frontend/ 执行 npm run build")

    if problems:
        print(f"\n  自检发现 {len(problems)} 项问题：")
        for item in problems:
            print(f"    - {item}")
    else:
        print("\n  自检全部通过\n")
    return not problems
