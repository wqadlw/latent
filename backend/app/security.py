"""
安全核心：密码哈希（PBKDF2-HMAC-SHA256）与访问令牌（HS256 JWT）。

刻意**零第三方依赖** —— 与 ``services/llm.py`` 只用标准库的取向保持一致，
不为「给本地单机服务签发一个 token」而引入 pyjwt / passlib / python-jose。
HS256 的签名逻辑本身只有十几行 HMAC，自己实现比多背一个依赖更可控。

同时兼容历史库里的裸 SHA-256 密码（``utils.encrypt_password`` 的产物）：
校验通过后由调用方就地升级为 PBKDF2，不需要用户改密码。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, Optional

from .paths import app_dir

# ============================================================
#  密码哈希
# ============================================================
_ALGO = "pbkdf2_sha256"
_ITERATIONS = 260_000          # OWASP 2023 对 PBKDF2-HMAC-SHA256 的推荐下限
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """生成 ``pbkdf2_sha256$迭代次数$盐$摘要`` 格式的密码串（自带盐，可安全落库）。"""
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def _legacy_sha256(password: str) -> str:
    """历史实现：无盐单轮 SHA-256。仅用于兼容旧库，不再用于新密码。"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, stored: str) -> bool:
    """校验密码。同时支持新格式（PBKDF2）与历史裸 SHA-256。"""
    if not stored:
        return False
    if stored.startswith(_ALGO + "$"):
        try:
            _, iterations, salt_hex, hash_hex = stored.split("$")
            dk = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(dk.hex(), hash_hex)
    # 旧格式兜底：等长比较，避免时序侧信道
    return hmac.compare_digest(_legacy_sha256(password), stored)


def needs_rehash(stored: str) -> bool:
    """判断存量密码串是否需要升级为 PBKDF2（登录成功后顺带迁移）。"""
    return not (stored or "").startswith(_ALGO + "$")


# ============================================================
#  签名密钥（进程级单例）
# ============================================================
_KEY_FILE = os.path.join(app_dir(), "data", ".secret_key")
_secret_cache: Optional[bytes] = None


def get_secret_key() -> bytes:
    """获取 JWT 签名密钥。

    优先级：环境变量 ``APP_SECRET_KEY`` > ``data/.secret_key`` 文件 > 随机生成并落盘。
    落盘而非每次随机，是为了让服务重启后已签发的 token 仍然有效。
    """
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache

    env = (os.environ.get("APP_SECRET_KEY") or "").strip()
    if env:
        _secret_cache = env.encode("utf-8")
        return _secret_cache

    os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as fh:
            data = fh.read().strip()
        if data:
            _secret_cache = data
            return _secret_cache

    key = secrets.token_bytes(48)
    with open(_KEY_FILE, "wb") as fh:
        fh.write(key)
    try:
        os.chmod(_KEY_FILE, 0o600)      # Windows 上为部分生效，失败不阻断
    except OSError:
        pass
    _secret_cache = key
    return key


# ============================================================
#  访问令牌（HS256 JWT）
# ============================================================
TOKEN_TTL_SECONDS = int(os.environ.get("APP_TOKEN_TTL", "43200"))   # 默认 12 小时


class TokenError(Exception):
    """令牌非法 / 过期 / 签名不匹配。"""


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def create_access_token(subject: str, uid: int, role: str, ttl: Optional[int] = None) -> str:
    """签发访问令牌。payload 只放最小必要信息，角色以数据库为准（token 仅作入口凭证）。"""
    issued = int(time.time())
    payload = {
        "sub": subject,
        "uid": uid,
        "role": role,
        "iat": issued,
        "exp": issued + (ttl if ttl is not None else TOKEN_TTL_SECONDS),
    }
    header_seg = _b64u_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":"), sort_keys=True).encode())
    payload_seg = _b64u_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    signature = hmac.new(get_secret_key(), signing_input, hashlib.sha256).digest()
    return f"{header_seg}.{payload_seg}.{_b64u_encode(signature)}"


def decode_access_token(token: str) -> Dict[str, Any]:
    """校验并解析访问令牌，失败统一抛 :class:`TokenError`。"""
    if not token or token.count(".") != 2:
        raise TokenError("令牌格式非法")
    header_seg, payload_seg, sig_seg = token.split(".")
    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    expected = hmac.new(get_secret_key(), signing_input, hashlib.sha256).digest()
    try:
        provided = _b64u_decode(sig_seg)
    except (ValueError, TypeError):
        raise TokenError("令牌签名非法") from None
    # 先验签再解析载荷，避免解析未受信数据
    if not hmac.compare_digest(expected, provided):
        raise TokenError("令牌签名校验失败")
    try:
        payload = json.loads(_b64u_decode(payload_seg))
    except (ValueError, TypeError):
        raise TokenError("令牌载荷解析失败") from None
    if int(payload.get("exp", 0)) < int(time.time()):
        raise TokenError("登录已过期，请重新登录")
    return payload
