"""
安全核心单元测试：密码哈希与 JWT。

不依赖数据库与网络，纯函数级验证。重点覆盖历史兼容路径 ——
老库里存的是无盐 SHA-256，升级到 PBKDF2 后必须仍能登录，
否则所有存量用户会被锁在门外。
"""
import hashlib
import time

import pytest
from app.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)


# ============================================================
#  密码哈希
# ============================================================
def test_hash_password_is_salted():
    """同一密码两次哈希必须不同（否则等于没加盐，彩虹表可破）。"""
    a = hash_password("admin123")
    b = hash_password("admin123")
    assert a != b
    assert a.startswith("pbkdf2_sha256$")


def test_verify_password_roundtrip():
    stored = hash_password("S3cret-Pass!")
    assert verify_password("S3cret-Pass!", stored) is True
    assert verify_password("wrong", stored) is False


def test_verify_rejects_empty_stored():
    assert verify_password("anything", "") is False


def test_verify_accepts_legacy_sha256():
    """v2 老库的密码格式（无盐 SHA-256）必须仍可校验通过。"""
    legacy = hashlib.sha256("admin123".encode("utf-8")).hexdigest()
    assert verify_password("admin123", legacy) is True
    assert verify_password("bad", legacy) is False


def test_needs_rehash_flags_legacy_only():
    legacy = hashlib.sha256("admin123".encode("utf-8")).hexdigest()
    assert needs_rehash(legacy) is True
    assert needs_rehash(hash_password("admin123")) is False


def test_verify_survives_malformed_stored():
    """损坏的密码串不应抛异常（否则一个坏行会让整个登录接口 500）。"""
    assert verify_password("x", "pbkdf2_sha256$notanumber$zz$yy") is False
    assert verify_password("x", "pbkdf2_sha256$onlyonepart") is False


# ============================================================
#  访问令牌
# ============================================================
def test_token_roundtrip():
    token = create_access_token("admin", 1, "admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "admin"
    assert payload["uid"] == 1
    assert payload["role"] == "admin"


def test_token_rejects_tampered_payload():
    """改掉 payload 里的 uid 后签名必须对不上 —— 这是 JWT 的安全根基。"""
    token = create_access_token("admin", 1, "admin")
    header, payload, signature = token.split(".")
    forged = f"{header}.{payload[:-2]}AA.{signature}"
    with pytest.raises(TokenError):
        decode_access_token(forged)


def test_token_rejects_wrong_signature():
    token = create_access_token("admin", 1, "admin")
    header, payload, _ = token.split(".")
    with pytest.raises(TokenError):
        decode_access_token(f"{header}.{payload}.AAAA")


def test_token_rejects_malformed():
    with pytest.raises(TokenError):
        decode_access_token("not-a-jwt")
    with pytest.raises(TokenError):
        decode_access_token("")


def test_token_expires():
    token = create_access_token("admin", 1, "admin", ttl=-1)
    time.sleep(0.01)
    with pytest.raises(TokenError):
        decode_access_token(token)
