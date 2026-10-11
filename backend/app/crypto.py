"""
字段级加密：让敏感值在 SQLite 里以**密文**落库，在 Python 侧以**明文**呈现。

为什么用 SQLAlchemy ``TypeDecorator`` 而不是在路由里手动加解密
------------------------------------------------------------
``llm_config.api_key`` 在 12 处被直接读成 ``c.api_key``（routers/llm.py、
services/llm_scheduler.py、services/doubao_studio.py 等）。逐个改调用点既容易漏改，
又会把加密逻辑散进业务代码。``TypeDecorator`` 只在「写库(bind)」与「读库(result)」
两个边界各转换一次，**20 个路由、4 个 service 一行都不用改**。

兼容性
------
历史数据是明文。``decrypt_secret`` 对不带 ``enc:v1:`` 前缀的值原样返回，
因此老库可以直接用，不需要停机刷数据；启动时的幂等迁移会逐步把明文转成密文。

降级
----
``cryptography`` 未安装时打印一次醒目告警并退化为明文存储，保证系统仍能启动
（该依赖已列入 requirements.txt，正常安装不会走到这条路径）。
"""
from __future__ import annotations

import os

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from .paths import app_dir

_PREFIX = "enc:v1:"
_KEY_FILE = os.path.join(app_dir(), "data", ".fernet_key")

_fernet = None
_warned = False


def _get_fernet():
    """惰性初始化 Fernet 实例；密钥落盘到 ``data/.fernet_key`` 以便重启后仍能解密。"""
    global _fernet, _warned
    if _fernet is not None:
        return _fernet
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        if not _warned:
            print("[安全告警] 未安装 cryptography，敏感字段将**明文存储**。"
                  "请执行 pip install -r requirements.txt 后重新保存密钥以启用加密。")
            _warned = True
        return None

    env_key = (os.environ.get("APP_FERNET_KEY") or "").strip()
    if env_key:
        _fernet = Fernet(env_key.encode("utf-8"))
        return _fernet

    os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as fh:
            stored = fh.read().strip()
        if stored:
            _fernet = Fernet(stored)
            return _fernet

    key = Fernet.generate_key()
    with open(_KEY_FILE, "wb") as fh:
        fh.write(key)
    try:
        os.chmod(_KEY_FILE, 0o600)
    except OSError:
        pass
    _fernet = Fernet(key)
    return _fernet


def is_encrypted(value: str) -> bool:
    """判断某个值是否已是密文（用于启动迁移的幂等判断）。"""
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_secret(plain: str) -> str:
    """加密敏感值。空值、已是密文的值原样返回。"""
    if plain is None or plain == "":
        return plain
    if is_encrypted(plain):
        return plain
    fernet = _get_fernet()
    if fernet is None:
        return plain
    return _PREFIX + fernet.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    """解密敏感值。历史明文（无前缀）原样返回；密文损坏时返回空串而非崩溃。"""
    if value is None or value == "":
        return value
    if not is_encrypted(value):
        return value
    fernet = _get_fernet()
    if fernet is None:
        return ""
    from cryptography.fernet import InvalidToken

    try:
        return fernet.decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        # 密钥被换掉或数据被手改 —— 报错并返回空值，避免整个列表接口 500
        print("[安全告警] 检测到无法解密的敏感字段（密钥可能已更换），该字段按空值处理")
        return ""


class EncryptedText(TypeDecorator):
    """透明加密的 TEXT 列：写库加密、读库解密，业务代码无感知。"""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return value
        return encrypt_secret(value)

    def process_result_value(self, value, dialect):
        if value is None or value == "":
            return value
        return decrypt_secret(value)
