"""
敏感字段加密测试。

核心断言是「**落库是密文、读出来是明文**」——
这既验证了 TypeDecorator 的 bind/result 双向转换，也验证了 20 个业务路由
（它们直接读 ``config.api_key``）拿到的仍是可直接使用的明文。
"""
from app.crypto import decrypt_secret, encrypt_secret, is_encrypted
from sqlalchemy import text


# ============================================================
#  纯函数
# ============================================================
def test_encrypt_decrypt_roundtrip():
    plain = "sk-1234567890abcdef"
    cipher = encrypt_secret(plain)
    assert cipher != plain
    assert cipher.startswith("enc:v1:")
    assert decrypt_secret(cipher) == plain


def test_encrypt_is_nondeterministic():
    """Fernet 自带随机 IV，同一明文两次密文必须不同。"""
    assert encrypt_secret("same-value") != encrypt_secret("same-value")


def test_encrypt_is_idempotent_on_ciphertext():
    """已是密文的值再加密不应套娃（启动迁移可能重复执行）。"""
    cipher = encrypt_secret("value")
    assert encrypt_secret(cipher) == cipher


def test_legacy_plaintext_passes_through():
    """历史明文（无前缀）读取时原样返回 —— 保证老库不刷数据也能用。"""
    assert is_encrypted("plain-old-key") is False
    assert decrypt_secret("plain-old-key") == "plain-old-key"


def test_empty_values_untouched():
    assert encrypt_secret("") == ""
    assert decrypt_secret("") == ""
    assert decrypt_secret(None) is None


def test_corrupted_ciphertext_returns_empty_not_crash():
    """密钥换掉后旧密文解不开 —— 应返回空串，而不是让整个列表接口 500。"""
    assert decrypt_secret("enc:v1:this-is-not-valid-fernet") == ""


# ============================================================
#  落库往返（TypeDecorator）
# ============================================================
def test_api_key_encrypted_at_rest_plaintext_in_python(client):
    """LLM 配置的 api_key：数据库里是密文，ORM 对象上是明文。"""
    from app.database import SessionLocal, engine
    from app.models import Industry, LlmConfig

    with SessionLocal() as session:
        industry = session.query(Industry).filter(Industry.is_deleted == 0).first()
        assert industry is not None, "夹具应已播种默认行业"

        config = LlmConfig(industry_id=industry.id, name="加密测试", api_key="sk-plain-secret")
        session.add(config)
        session.commit()
        config_id = config.id

    # 裸 SQL 查库：必须是密文
    with engine.connect() as conn:
        raw = conn.execute(
            text("SELECT api_key FROM llm_config WHERE id = :i"), {"i": config_id}
        ).scalar()
    assert raw != "sk-plain-secret"
    assert raw.startswith("enc:v1:")

    # ORM 查询：必须自动解密回明文
    with SessionLocal() as session:
        loaded = session.query(LlmConfig).filter(LlmConfig.id == config_id).first()
        assert loaded.api_key == "sk-plain-secret"
        session.delete(loaded)
        session.commit()
