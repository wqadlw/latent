"""C2：生产队列表 ``pipeline_job`` + 可编排规格字段

Revision ID: 0006_pipeline_queue
Revises: 0005_geo_competitor
Create Date: 2026-10-11

背景
----
阶段 C 之前，一次「浏览器工作室自动流」运行是**同步、无队列、不可裁剪**的：
  - 步骤顺序写死在 ``doubao_studio.orchestrate_run`` 里，无法只跑其中一段；
  - 失败后 ``retry_run`` 把全部步骤重置为 pending，从步骤①重新烧一遍 token；
  - 想批量做 10 篇，只能手工点 10 次。

本次迁移为三件事落库：
  1. ``production_task.pipeline_spec`` —— 该运行的编排规格（启用哪些步骤 / 最大整改轮数）。
     存 JSON 文本而不是拆列，是因为规格字段后续还会增删，拆列会让每次加一个开关都要迁移。
  2. ``production_task.batch_id`` —— 批量生产批次号，用于把「一次提交产生的 N 条运行」
     聚合成一个可看进度的批次。
  3. ``pipeline_job`` 表 —— 队列的持久化载体（排队中 / 运行中 / 已结束 / 失败 / 已取消，
     含优先级、尝试次数、退避时间、取消请求标记）。

幂等性说明：同 0002 —— 全新库在 baseline 阶段已按当前模型建表建列，
此处「存在即跳过」，因此可安全地对老库增量执行。
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0006_pipeline_queue"
down_revision = "0005_geo_competitor"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    from app.models import PipelineJob

    if not _has_table(PipelineJob.__tablename__):
        PipelineJob.__table__.create(op.get_bind())

    # 老库补列：production_task 上新增的两个编排字段
    for col, ddl in (
        ("pipeline_spec", "TEXT DEFAULT ''"),
        ("batch_id", "VARCHAR(64) DEFAULT ''"),
    ):
        if not _has_column("production_task", col):
            op.execute(f"ALTER TABLE production_task ADD COLUMN {col} {ddl}")

    # 批次号要按批次聚合查进度，必须带索引；IF NOT EXISTS 保证重复执行安全
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_production_task_batch_id ON production_task (batch_id)"
    )


def downgrade() -> None:
    if _has_table("pipeline_job"):
        op.drop_table("pipeline_job")
    if _has_column("production_task", "batch_id"):
        op.execute("DROP INDEX IF EXISTS ix_production_task_batch_id")
        op.execute("ALTER TABLE production_task DROP COLUMN batch_id")
    if _has_column("production_task", "pipeline_spec"):
        op.execute("ALTER TABLE production_task DROP COLUMN pipeline_spec")
