"""
pytest 全局夹具。

**必须在导入 app 之前**设置好环境变量 —— ``app.database`` 在模块导入时就会
按 ``APP_DB_PATH`` 计算数据库路径并建立 engine，晚于导入再改就来不及了。
conftest.py 由 pytest 最先加载，因此这里是唯一可靠的注入点。

隔离策略：
- 数据库 → 临时目录，绝不碰开发库 ``backend/data/database.db``
- JWT 签名密钥 / Fernet 加密密钥 → 固定测试值，保证可重复
"""
import os
import tempfile

import pytest

_TMP_DIR = tempfile.mkdtemp(prefix="acm-test-")

os.environ["APP_DB_PATH"] = os.path.join(_TMP_DIR, "test.db")
os.environ["APP_SECRET_KEY"] = "pytest-fixed-secret-key-do-not-use-in-production"

# 队列调度线程在测试里必须关掉：它会在后台不断领取并执行排队中的作业，
# 于是「投递一条作业」的用例会与它抢同一行，结果随线程时序而变（典型 flaky 来源）。
# 需要验证调度循环本身的用例，自己显式起一个 Dispatcher 并同步驱动它。
os.environ["APP_PIPELINE_WORKER"] = "0"

# Fernet 密钥必须格式合法，用真实实现生成一个
from cryptography.fernet import Fernet  # noqa: E402

os.environ["APP_FERNET_KEY"] = Fernet.generate_key().decode("ascii")


@pytest.fixture(scope="session")
def client():
    """带完整 lifespan（建库 + 迁移 + 种子）的测试客户端，整个会话复用。"""
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def admin_token(client):
    """登录默认管理员，返回可用的访问令牌。"""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
