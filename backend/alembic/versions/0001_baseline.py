"""baseline：v3.0.0 全量 schema 基线

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-10

说明
----
这是「引入 Alembic 时对既有模型的一次性快照」。此前建表由
``main.py::init_db()`` 的 ``Base.metadata.create_all`` 完成，本迁移把该行为
固化成可版本化的基线，之后所有 schema 变更都以增量迁移的形式追加。

刻意保留原有的一处**例外**：``browser_studio_run`` 表不建。
P2 并表改造后，自动流数据已并入 ``production_task``，原表被改名归档为
``_archive_browser_studio_run``，但其索引名仍挂在归档表上；若再重建该表，
会因索引重名导致启动失败。模型类保留（查询走 fallback），只是不再建表。
"""
from __future__ import annotations

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.database import Base
    from app.models import BrowserStudioRun

    bind = op.get_bind()
    tables = [t for t in Base.metadata.tables.values() if t is not BrowserStudioRun.__table__]
    Base.metadata.create_all(bind=bind, tables=tables)


def downgrade() -> None:
    from app.database import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
