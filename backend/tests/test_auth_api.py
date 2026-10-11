"""
鉴权体系集成测试。

这是 v3 最重要的一条防线：v2 的 20 个业务路由**完全没有鉴权**，
任何能访问 8765 端口的人都能读写全部数据（含明文 API Key）。
本测试守护「未登录一律 401」这一不变量，防止未来新增路由时漏挂守卫。
"""
import pytest

# 抽几个有代表性的业务路由：CRUD 型、配置型、重操作型
PROTECTED_ENDPOINTS = [
    ("GET", "/api/industry?industry_id=1"),
    ("GET", "/api/platform?industry_id=1"),
    ("GET", "/api/knowledge/category?industry_id=1"),
    ("GET", "/api/prompt-library?industry_id=1"),
    ("GET", "/api/production?industry_id=1"),
    ("GET", "/api/llm/configs?industry_id=1"),
    ("GET", "/api/geo-monitor?industry_id=1"),
    ("GET", "/api/publish-job?industry_id=1"),
    ("GET", "/api/platform-credential?industry_id=1"),
    ("GET", "/api/rule?industry_id=1"),
]


# ============================================================
#  公开端点
# ============================================================
def test_meta_is_public(client):
    resp = client.get("/api/meta")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["version"]


# ============================================================
#  未登录拦截
# ============================================================
@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_protected_endpoints_require_auth(client, method, path):
    resp = client.request(method, path)
    assert resp.status_code == 401, f"{method} {path} 未拦截未登录请求"


def test_garbage_token_rejected(client):
    resp = client.get("/api/industry", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_forged_token_rejected(client):
    """自己拼一个 header.payload 但没有正确签名的令牌，必须被拒。"""
    import base64
    import json

    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": "admin", "uid": 1, "role": "admin", "exp": 9999999999}).encode()
    ).rstrip(b"=").decode()
    resp = client.get("/api/industry", headers={"Authorization": f"Bearer {header}.{payload}.forged"})
    assert resp.status_code == 401


# ============================================================
#  登录
# ============================================================
def test_login_success(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["token"]
    assert data["user"]["username"] == "admin"
    assert "password" not in data["user"], "响应中绝不能带出密码字段"


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "definitely-wrong"})
    assert resp.status_code == 401


def test_login_unknown_user_same_message_as_wrong_password(client):
    """不区分「用户不存在」与「密码错误」，避免账号枚举。"""
    a = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-1"})
    b = client.post("/api/auth/login", json={"username": "no-such-user-xyz", "password": "wrong-1"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_me_returns_current_user(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "admin"


def test_authorized_request_passes(client, auth_headers):
    resp = client.get("/api/industry", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


# ============================================================
#  用户管理（管理员）
# ============================================================
def test_user_crud_and_password_change(client, auth_headers):
    username = "pytest_editor"

    created = client.post(
        "/api/auth/users",
        headers=auth_headers,
        json={"username": username, "password": "init-pass-123", "role": "editor"},
    )
    assert created.status_code == 200, created.text
    uid = created.json()["data"]["id"]

    try:
        # 新用户可以登录
        login = client.post("/api/auth/login", json={"username": username, "password": "init-pass-123"})
        assert login.status_code == 200
        user_headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}

        # 改密后旧密码失效、新密码生效
        changed = client.post(
            "/api/auth/change-password",
            headers=user_headers,
            json={"old_password": "init-pass-123", "new_password": "brand-new-pass-456"},
        )
        assert changed.status_code == 200
        assert client.post(
            "/api/auth/login", json={"username": username, "password": "init-pass-123"}
        ).status_code == 401
        assert client.post(
            "/api/auth/login", json={"username": username, "password": "brand-new-pass-456"}
        ).status_code == 200

        # editor 无权管理用户
        forbidden = client.get("/api/auth/users", headers=user_headers)
        assert forbidden.status_code == 403

        # 弱密码被拒（schema 层 min_length=8）
        weak = client.post(
            "/api/auth/users",
            headers=auth_headers,
            json={"username": "weak_pwd_user", "password": "123", "role": "editor"},
        )
        assert weak.status_code == 422
    finally:
        client.delete(f"/api/auth/users/{uid}", headers=auth_headers)


def test_cannot_delete_self(client, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers).json()["data"]
    resp = client.delete(f"/api/auth/users/{me['id']}", headers=auth_headers)
    assert resp.status_code == 400


def test_cannot_delete_last_admin(client, auth_headers):
    """系统必须保留至少一个启用的管理员，否则会被彻底锁死。"""
    me = client.get("/api/auth/me", headers=auth_headers).json()["data"]
    resp = client.put(
        f"/api/auth/users/{me['id']}", headers=auth_headers, json={"role": "editor"}
    )
    assert resp.status_code == 400


def test_duplicate_username_rejected(client, auth_headers):
    resp = client.post(
        "/api/auth/users",
        headers=auth_headers,
        json={"username": "admin", "password": "another-pass-123", "role": "editor"},
    )
    assert resp.status_code == 400


def test_operation_logs_recorded(client, auth_headers):
    resp = client.get("/api/auth/operation-logs", headers=auth_headers, params={"module": "auth"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] > 0
    assert any(item["action"] == "login_success" for item in data["items"])


# ============================================================
#  结构性守卫（防止未来新增路由漏挂鉴权）
# ============================================================
def test_every_business_router_is_guarded():
    """新增路由模块时必须同时加进 ``_PROTECTED_ROUTERS``，否则整模块裸奔。

    这是本次改动最容易退化的一点：v2 的问题就是「没有任何守卫」，
    而靠人工记住 20 个模块显然不可靠 —— 交给测试来记。
    """
    import pkgutil

    import app.main as main_module
    import app.routers as routers_pkg

    # _PROTECTED_ROUTERS 里存的是模块对象，用模块名比对（对象身份可能因导入路径不同而不同）
    guarded = {getattr(r, "__name__", "").rsplit(".", 1)[-1] for r in main_module._PROTECTED_ROUTERS}
    # 仅这两个模块允许公开：
    #   auth —— 否则无法登录
    #   site —— /llms.txt /sitemap.xml /robots.txt 必须对匿名 AI 爬虫可达
    public_modules = {"auth", "site"}

    unguarded = []
    for mod_info in pkgutil.iter_modules(routers_pkg.__path__):
        name = mod_info.name
        if name.startswith("_") or name in public_modules:
            continue
        module = __import__(f"app.routers.{name}", fromlist=["router"])
        if getattr(module, "router", None) is None:
            continue
        if name not in guarded:
            unguarded.append(name)

    assert not unguarded, (
        f"以下路由模块未挂登录守卫，会被任何人匿名访问：{unguarded}。"
        f"请把它们加入 app/main.py 的 _PROTECTED_ROUTERS。"
    )


def test_openapi_schema_generates(client):
    """OpenAPI 生成必须成功 —— 否则 /docs 页面会 500。

    回归背景：routers/publish.py 的 CapturePaste 用了 `Any` 却未导入，
    配合 `from __future__ import annotations` 被静默推迟，直到 pydantic 2.14
    才在生成 schema 时炸出来。这条用例把「打开文档页」纳入自动化保护。
    """
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["version"]
    assert len(schema["paths"]) > 100
