"""B1：质检闸门表 ``quality_check``

Revision ID: 0003_quality_gate
Revises: 0002_crawler_traffic
Create Date: 2026-10-10

背景
----
此前内容质检只有「过 / 不过」二值判定（``services/rule_checker.py``），
与 GEO 评分（``services/geo_score.py``）各判各的、互不裁决。
本表用于承载统一闸门的三态决策结果：
``passed``（自动放行）/ ``needs_review``（人工复核）/ ``blocked``（拦截），
并把「硬阻塞项」「软扣分项」「无证据断言」分离落库，便于事后复盘与阈值调优。

幂等性说明：同 0002 —— 全新库在 baseline 阶段已建表，此处存在即跳过。
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0003_quality_gate"
down_revision = "0002_crawler_traffic"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    from app.models import QualityCheck

    if not _has_table(QualityCheck.__tablename__):
        QualityCheck.__table__.create(op.get_bind())


def downgrade() -> None:
    if _has_table("quality_check"):
        op.drop_table("quality_check")
