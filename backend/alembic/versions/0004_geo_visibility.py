"""B2：AI 可见性采集表 + ``geo_monitor_reply`` 桥接字段

Revision ID: 0004_geo_visibility
Revises: 0003_quality_gate
Create Date: 2026-10-10

背景
----
此前 AI 可见性监测完全靠「人工复制 AI 回答 → 粘贴回系统」，且**只存回答文本**，
把最有价值的信息丢掉了：AI 在回答里**引用了哪些信源**。

本迁移建立两层数据模型：
- ``geo_visibility_run``    —— 一次探测（问题 × 引擎 × 一次调用）
- ``geo_visibility_source`` —— 该次探测中被 AI 引用的信源（N 条）

并给 ``geo_monitor_reply`` 增加 ``run_id`` / ``source_channel``，
让手工粘贴通道与自动采集通道的指标能进入同一套统计口径。

幂等性说明
----------
新建表：全新库在 baseline 阶段已建，存在即跳过。
新增列：baseline 用**当前** metadata 建 ``geo_monitor_reply``，因此全新库里
这两列已经存在，必须逐列判定后再 ALTER，否则报「duplicate column name」。
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import Column, Integer, String, inspect

revision = "0004_geo_visibility"
down_revision = "0003_quality_gate"
branch_labels = None
depends_on = None

# 需要补到 geo_monitor_reply 的桥接列（列名 → 列定义）
_BRIDGE_COLUMNS = {
    "run_id": Column("run_id", Integer, nullable=True, server_default="0"),
    "source_channel": Column("source_channel", String(16), nullable=True, server_default="manual"),
}


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _column_names(table: str) -> set:
    insp = inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    from app.models import GeoVisibilityRun, GeoVisibilitySource

    for model in (GeoVisibilityRun, GeoVisibilitySource):
        if not _has_table(model.__tablename__):
            model.__table__.create(op.get_bind())

    # geo_monitor_reply 桥接列：先加列（带 server_default，保证存量行有值）
    existing = _column_names("geo_monitor_reply")
    for name, column in _BRIDGE_COLUMNS.items():
        if name not in existing:
            op.add_column("geo_monitor_reply", column)

    # 桥接列的索引（batch 模式在 SQLite 下安全重建）
    existing_indexes = {i["name"] for i in inspect(op.get_bind()).get_indexes("geo_monitor_reply")}
    if "ix_geo_monitor_reply_run_id" not in existing_indexes and "run_id" in _column_names("geo_monitor_reply"):
        op.create_index("ix_geo_monitor_reply_run_id", "geo_monitor_reply", ["run_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    existing_indexes = {i["name"] for i in insp.get_indexes("geo_monitor_reply")}
    if "ix_geo_monitor_reply_run_id" in existing_indexes:
        op.drop_index("ix_geo_monitor_reply_run_id", table_name="geo_monitor_reply")

    existing = _column_names("geo_monitor_reply")
    for name in _BRIDGE_COLUMNS:
        if name in existing:
            op.drop_column("geo_monitor_reply", name)

    for table in ("geo_visibility_source", "geo_visibility_run"):
        if _has_table(table):
            op.drop_table(table)
