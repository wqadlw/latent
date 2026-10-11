"""
数据级迁移（非 schema 变更）：把存量数据刷成 v3 期望的格式。

与 Alembic 的分工：
- Alembic 管 **schema**（建表 / 加列 / 改类型），见 ``alembic/versions/``
- 本模块管 **存量数据**（把已有行刷成新格式）

放在这里而不是写进 Alembic migration，是因为其中一部分依赖运行时资源
（密钥文件、模型层常量），而 migration 应保持可重放且与环境解耦。
本模块所有函数都**幂等**，重复执行无副作用。

这些逻辑原本散落在 ``main.py::init_db()`` 里，和 schema 迁移混在一起，
既看不出哪些是建表、哪些是刷数据，也无法单独测试。现在归拢到这里。
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .crypto import encrypt_secret, is_encrypted


# ============================================================
#  敏感字段加密
# ============================================================
def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"), {"n": name}
    ).fetchone()
    return row is not None


def _encrypt_column(engine: Engine, table: str, column: str) -> int:
    """把 ``table.column`` 中所有非空且未加密的值就地加密，返回转换行数。

    直接走裸 SQL 读写 —— 若经 ORM 读取，``EncryptedText`` 会把明文原样返回，
    再写回时又被加密，虽然结果正确，但无法区分「本次是否真的发生了转换」，
    也就给不出准确的迁移计数。
    """
    converted = 0
    with engine.begin() as conn:
        if not _table_exists(conn, table):
            return 0
        rows = conn.execute(text(f"SELECT id, {column} FROM {table}")).fetchall()
        for row_id, value in rows:
            if not value or is_encrypted(value):
                continue
            conn.execute(
                text(f"UPDATE {table} SET {column} = :v WHERE id = :i"),
                {"v": encrypt_secret(value), "i": row_id},
            )
            converted += 1
    return converted


def encrypt_legacy_secrets(engine: Engine) -> None:
    """把 LLM 密钥与平台凭据的存量明文转为密文。"""
    try:
        n_key = _encrypt_column(engine, "llm_config", "api_key")
        n_cred = _encrypt_column(engine, "platform_credential", "cred_json")
        if n_key or n_cred:
            print(f"[数据迁移] 已加密存量敏感字段：LLM 密钥 {n_key} 条、平台凭据 {n_cred} 条")
    except Exception as exc:  # noqa: BLE001 — 迁移失败不应阻断启动
        print(f"[数据迁移] 敏感字段加密迁移跳过: {exc}")


# ============================================================
#  历史业务数据归一
# ============================================================
def merge_safety_prompts(engine: Engine) -> None:
    """原「安全筛选(safety)」与「GEO 软文(geo)」两类提示词已合并为「安全 · GEO 筛选(geo)」。

    把历史 safety 类目提示词改归到 geo，避免类目消失后变成孤儿数据。
    """
    try:
        with engine.begin() as conn:
            if not _table_exists(conn, "prompt_library_item"):
                return
            result = conn.execute(
                text("UPDATE prompt_library_item SET category='geo' WHERE category='safety'")
            )
            if result.rowcount:
                print(f"[数据迁移] 已将 {result.rowcount} 条 safety 提示词并入 geo 类")
    except Exception as exc:  # noqa: BLE001
        print(f"[数据迁移] safety→geo 合并跳过: {exc}")


def inject_geo_signal_block(engine: Engine) -> None:
    """为现存「默认」outline/draft/rewrite 提示词补上【目标客户需求 / GEO 信号】块。

    使第 4 步「目标客户需求」在已有行业的软文生产中也真实生效。
    幂等判据：模板里已含 ``{geo_signals}`` 则跳过。
    """
    geo_block = "\n【目标客户需求 / GEO 信号（若第4步已设定则必用）】\n{geo_signals}\n"
    try:
        from .database import SessionLocal
        from .models import PromptLibraryItem

        changed = 0
        with SessionLocal() as session:
            items = (
                session.query(PromptLibraryItem)
                .filter(
                    PromptLibraryItem.category.in_(["outline", "draft", "rewrite"]),
                    PromptLibraryItem.is_deleted == 0,
                )
                .all()
            )
            for item in items:
                if not item.content or "{geo_signals}" in item.content:
                    continue
                if not (item.name or "").startswith("默认"):
                    continue
                item.content = item.content.rstrip() + geo_block
                changed += 1
            if changed:
                session.commit()
        if changed:
            print(f"[数据迁移] 已为 {changed} 条默认提示词追加 GEO 需求块")
    except Exception as exc:  # noqa: BLE001
        print(f"[数据迁移] 默认提示词 GEO 块追加跳过: {exc}")


def drop_orphan_tables(engine: Engine) -> None:
    """清理被 prompt_library 取代的旧版孤儿表。"""
    try:
        with engine.begin() as conn:
            for table in ("prompt_template", "prompt_generate_log"):
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
    except Exception as exc:  # noqa: BLE001
        print(f"[数据迁移] 孤儿表清理跳过: {exc}")


def run_data_migrations(engine: Engine) -> None:
    """启动时统一入口。顺序：先归一业务数据，再做加密（加密放最后，避免影响前面按原文判断的逻辑）。"""
    merge_safety_prompts(engine)
    inject_geo_signal_block(engine)
    drop_orphan_tables(engine)
    encrypt_legacy_secrets(engine)
