"""B3：竞品检测表

Revision ID: 0005_geo_competitor
Revises: 0004_geo_visibility
Create Date: 2026-10-10

背景
----
「AI 在同一批关键词上还推荐了谁」是与可见性同等重要的信息：
只知道自己被提没被提，不足以指导内容策略；知道竞品在哪些问题上压过自己，
才能定位要补的内容缺口。

幂等性说明：同 0002 —— 全新库在 baseline 阶段已建表，此处存在即跳过。
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0005_geo_competitor"
down_revision = "0004_geo_visibility"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    from app.models import GeoVisibilityCompetitor, GeoVisibilityCompetitorDetection

    for model in (GeoVisibilityCompetitor, GeoVisibilityCompetitorDetection):
        if not _has_table(model.__tablename__):
            model.__table__.create(op.get_bind())


def downgrade() -> None:
    for table in ("geo_visibility_competitor_detection", "geo_visibility_competitor"):
        if _has_table(table):
            op.drop_table(table)
