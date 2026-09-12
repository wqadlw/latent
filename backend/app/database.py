"""
数据库连接与会话管理
SQLite 单文件存储，零安装零服务
"""
import os
import shutil
from datetime import datetime
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from .paths import app_dir, resource_dir, _is_frozen

# 可写数据目录：源码模式=backend/data；打包 exe 模式=exe 同级 data（持久化，不随临时目录丢失）
BASE_DIR = app_dir()
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "database.db")

# ---- 种子数据库还原：首次运行时从 exe 内提取 ----
if _is_frozen() and not os.path.exists(DB_PATH):
    seed = os.path.join(resource_dir(), "seed_data", "database.db")
    if os.path.exists(seed):
        print(f"[数据] 首次启动，正在还原种子数据库 → {DB_PATH}")
        shutil.copy2(seed, DB_PATH)
        print("[数据] 种子数据库还原完成")
    else:
        print("[数据] 未找到种子数据库，将创建空数据库")

DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _fk_pragma_on_connect(dbapi_con, con_record):
    cursor = dbapi_con.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def now():
    return datetime.now()
