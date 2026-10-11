"""
以编程方式驱动 Alembic —— 让应用启动时自动把 schema 升到最新版本。

三种启动场景
------------
1. **全新库**（无任何业务表）→ ``upgrade head``，由基线迁移建全部表。
2. **v2 老库**（有业务表但没有 ``alembic_version``）→ ``stamp 0001_baseline``，
   只打**基线**版本标记、不重放建表，随后继续 ``upgrade head`` 把增量迁移跑完。
   老库的 schema 早已由 v2 的 ``init_db()`` 手写迁移补齐，重放基线会撞上已存在的表/索引。
3. **v3 库**（已有 ``alembic_version``）→ ``upgrade head``，执行增量迁移。

⚠️ 历史缺陷：早期实现是 ``stamp head``，把老库直接标记为**最新**版本，
导致后续新增的增量迁移在老库上**永远不会执行**（表永远建不出来）。
现改为 stamp 到基线再 upgrade，才是正确的升级语义。

这样升级路径对使用者是透明的：老用户把 v3 代码覆盖上去直接启动即可。
"""
from __future__ import annotations

import os

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from .database import DB_PATH, engine
from .paths import resource_dir


def _alembic_root() -> str:
    """alembic.ini 与 alembic/ 所在目录。源码模式=backend/，打包模式=资源目录。"""
    return resource_dir()


def _build_config() -> Config:
    root = _alembic_root()
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic").replace("\\", "/"))
    cfg.set_main_option(
        "sqlalchemy.url",
        "sqlite:///" + DB_PATH.replace("\\", "/").replace("%", "%%"),
    )
    return cfg


def current_revision() -> str | None:
    """当前库所处的迁移版本；未纳管（无 alembic_version 表）时返回 None。"""
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _has_business_tables() -> bool:
    """库中是否已存在业务表（用于区分「全新库」与「v2 老库」）。"""
    names = set(inspect(engine).get_table_names())
    return bool(names - {"alembic_version"})


# v3 引入 Alembic 时的基线版本。老库只应被标记到此版本，
# 之后由 ``upgrade head`` 补齐增量迁移 —— 不能直接 stamp 到 head。
BASELINE_REVISION = "0001_baseline"


def upgrade_to_head() -> None:
    """把 schema 升级到最新版本（幂等）。"""
    revision = current_revision()
    cfg = _build_config()

    if revision is None and _has_business_tables():
        command.stamp(cfg, BASELINE_REVISION)
        print(f"[迁移] 检测到 v2 老库，已标记为基线 {BASELINE_REVISION}（不重放建表），继续执行增量迁移")

    command.upgrade(cfg, "head")
    new_revision = current_revision()
    if new_revision:
        print(f"[迁移] 数据库 schema 已就绪（版本 {new_revision}）")
