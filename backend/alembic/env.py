"""
Alembic 运行环境。

关键点：**连接串不写在 alembic.ini 里**，而是从 ``app.database.DB_PATH`` 动态注入。
这样「源码模式 backend/data/」与「PyInstaller 打包模式 exe 同级 data/」两套路径
共用同一份迁移配置，不会出现「打包后迁移跑到错误目录」的问题。
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 让 alembic 能 import 到 app 包（本文件位于 backend/alembic/env.py）
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import app.models  # noqa: E402,F401  —— 必须导入以把所有表注册进 Base.metadata
from app.database import DB_PATH, Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Windows 路径需转成正斜杠；configparser 的 % 需转义为 %%
_url = "sqlite:///" + DB_PATH.replace("\\", "/").replace("%", "%%")
config.set_main_option("sqlalchemy.url", _url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连接数据库。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,       # SQLite 不支持 ALTER，需 batch 模式重建表
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直连数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,   # 关键：SQLite 加列/改列走「重建表」策略
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
