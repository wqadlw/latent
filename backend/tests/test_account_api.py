"""账号 / 平台 / 人设 的 API 回归测试。

只覆盖一条路径：**不选人设（甚至不选平台）也能建账号**。

背景（D5 拆分前端时发现的真缺陷）：
`Account.persona_id` 的列默认值曾是 `default=0`，而 `app/database.py` 开着
`PRAGMA foreign_keys=ON`，`persona` 表里根本没有 id=0。SQLAlchemy 会把
「显式传 None」当成「用默认值」，于是插入 `persona_id=0` →
`FOREIGN KEY constraint failed` → **HTTP 500**。

前端 `Platform.vue` 的 `accountForm` 初始 `persona_id: null`，且那个人设下拉是
`clearable` —— 所以「新建账号但不选人设」是极易触发的常规操作，而不是边角情况。
本机开发库里 `account` 表是空的（该功能从未成功过），而 `tests/` 里 `persona_id`
出现 **0 次** —— 零覆盖正是它长期没被发现的原因。本文件补上这条覆盖。
"""
from app.database import Base


def _industry_id(client, auth_headers) -> int:
    resp = client.get("/api/industry", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert items, "测试库应至少有一个默认行业空间（见 app/main.py 的启动种子）"
    return items[0]["id"]


def test_create_account_without_persona(client, auth_headers):
    """核心回归：不选人设 → 必须成功，且 persona_id 落库为 null（而不是 0）。"""
    industry_id = _industry_id(client, auth_headers)
    resp = client.post("/api/account", headers=auth_headers, json={
        "industry_id": industry_id,
        "account_name": "不选人设的账号",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["persona_id"] is None, f"persona_id 应为 null，实际 {data['persona_id']!r}"
    client.delete(f"/api/account/{data['id']}", headers=auth_headers)


def test_create_account_without_platform_or_persona(client, auth_headers):
    """最精简的创建：平台与人设都不给，两个外键都应为 null。"""
    industry_id = _industry_id(client, auth_headers)
    resp = client.post("/api/account", headers=auth_headers, json={
        "industry_id": industry_id,
        "account_name": "既无平台也无人设",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["platform_id"] is None, f"platform_id 应为 null，实际 {data['platform_id']!r}"
    assert data["persona_id"] is None, f"persona_id 应为 null，实际 {data['persona_id']!r}"
    client.delete(f"/api/account/{data['id']}", headers=auth_headers)


def test_create_account_with_persona_still_works(client, auth_headers):
    """正常路径（选了人设）不能被修坏，且外键确实指向那一行。"""
    industry_id = _industry_id(client, auth_headers)

    per = client.post("/api/persona", headers=auth_headers, json={
        "industry_id": industry_id, "name": "回归测试人设",
    })
    assert per.status_code == 200, per.text
    persona_id = per.json()["data"]["id"]

    acc = client.post("/api/account", headers=auth_headers, json={
        "industry_id": industry_id, "account_name": "选了人设的账号", "persona_id": persona_id,
    })
    assert acc.status_code == 200, acc.text
    data = acc.json()["data"]
    assert data["persona_id"] == persona_id

    client.delete(f"/api/account/{data['id']}", headers=auth_headers)
    client.delete(f"/api/persona/{persona_id}", headers=auth_headers)


def test_no_foreign_key_column_has_scalar_default():
    """结构守卫：外键列的 Python 侧默认值不得是标量（如 0），只能是 None 或不设。

    这条守卫比单个用例更有价值 —— 它能拦住**同一类**缺陷在别的表上重演。
    允许 callable 默认值（如 `default=now`），只禁止 `default=0` 这类字面量。
    """
    offenders = []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if not col.foreign_keys:
                continue
            default = col.default
            if default is not None and not default.is_callable:
                offenders.append(f"{table.name}.{col.name} = {default.arg!r}")
    assert not offenders, (
        "外键列不应有标量默认值（PRAGMA foreign_keys=ON 时，"
        "`default=0` 会让「不传」变成「插 0」而触发外键失败）：" + "；".join(offenders)
    )
