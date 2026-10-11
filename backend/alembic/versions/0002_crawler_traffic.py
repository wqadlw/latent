"""B5：爬虫流量日志表 ``crawler_hit``

Revision ID: 0002_crawler_traffic
Revises: 0001_baseline
Create Date: 2026-10-10

背景
----
GEO 闭环的「发布 → 收录」之间此前完全没有数据：系统只知道「发布成功」，
不知道 AI 有没有来抓。本迁移建立爬虫抓取日志表，配合
``app/services/crawler_classifier.py`` 与 ``app/middleware/traffic_log.py``，
首次让「被 AI 收录」这件事可被客观观测。

幂等性说明
----------
``0001_baseline`` 从**当前** ``Base.metadata`` 建表，因此全新库在 baseline 阶段
其实已经包含本表。本迁移对全新库是 no-op，对存量库才真正建表。
两种路径都必须成功，所以这里做「存在即跳过」判定。
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0002_crawler_traffic"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    from app.models import CrawlerHit

    if not _has_table(CrawlerHit.__tablename__):
        CrawlerHit.__table__.create(op.get_bind())


def downgrade() -> None:
    if _has_table("crawler_hit"):
        op.drop_table("crawler_hit")
