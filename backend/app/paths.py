"""
运行路径解析（兼容源码运行与 PyInstaller 打包 exe）

- resource_dir(): 只读资源根目录。
    * 打包(exe)模式：PyInstaller 解压临时目录 sys._MEIPASS（static 等资源打包在此）
    * 源码模式：backend/ 目录
- app_dir(): 可写数据根目录（数据库等需持久化、可写）。
    * 打包(exe)模式：exe 文件所在目录（data/database.db 生成在 exe 旁边，重启不丢）
    * 源码模式：backend/ 目录（与原行为一致）
"""
import os
import sys


def _is_frozen() -> bool:
    """是否运行在 PyInstaller 打包出的 exe 中。"""
    return getattr(sys, "frozen", False)


# backend/ 目录（本文件位于 backend/app/paths.py，上两级即 backend/）
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir() -> str:
    """只读资源根目录。"""
    if _is_frozen():
        # PyInstaller 会把 --add-data 的资源解压到 sys._MEIPASS
        return getattr(sys, "_MEIPASS", _BACKEND_DIR)
    return _BACKEND_DIR


def app_dir() -> str:
    """可写数据根目录（持久化）。"""
    if _is_frozen():
        # exe 所在目录，保证数据库落在 exe 旁边而非临时解压目录
        return os.path.dirname(os.path.abspath(sys.executable))
    return _BACKEND_DIR
