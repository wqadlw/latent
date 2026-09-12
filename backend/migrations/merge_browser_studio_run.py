#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P2 数据并表迁移脚本（幂等 / 自动备份 / 默认 dry-run）

目标：把 browser_studio_run（自动流）的历史数据并入 production_task（统一任务模型），
      并打通 browser_studio_step / llm_call_log 的外键指向，使两套生产路径共用一张任务表。

设计要点：
- 默认 dry-run：仅打印将要做什么、影响多少行；不写库。加 --apply 才真正执行。
- 自动备份：任何写操作前，先把整个 database.db 复制为 database.db.bak.<时间戳>（完美回滚点）。
- 幂等：production_task 已有 legacy_run_id 的行（说明曾经迁过）直接跳过；新增列已存在则跳过 ALTER。
- foreign_keys=OFF 仅用于 DDL 重建阶段，执行完恢复；运行期 DB 仍保持外键开启。

列对齐策略（关键，降低代码重构风险）：
  production_task 直接补齐 BrowserStudioRun 的「同名列」（name/platform/log/error 等，
  与现有 title/platform_id 不冲突），因此代码侧只需把 BrowserStudioRun 类替换为
  ProductionTask 类（纯类型替换），引擎逻辑无需逐处改属性名。

⚠️ 重要前置依赖（本脚本不负责，需在「同一版本」内由代码重构完成）：
   doubao_studio.py / routers/browser_studio.py / models.py / main.py 启动迁移 仍引用
   browser_studio_run。本脚本会把 browser_studio_run 改名归档为 _archive_browser_studio_run，
   因此「执行本脚本」必须与「代码侧改为读写 ProductionTask(mode='auto')」同时发布，
   否则应用会启动失败。代码重构（Phase 2b）完成前，请勿 --apply。

用法：
  python migrations/merge_browser_studio_run.py            # dry-run（安全预览）
  python migrations/merge_browser_studio_run.py --apply    # 真正执行（先自动备份）
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

# ---- 路径解析：脚本位于 <backend>/migrations/，DB 在 <backend>/data/database.db ----
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(HERE)
DEFAULT_DB = os.path.join(BACKEND_DIR, "data", "database.db")

# production_task 需要新增的列（name, type）。
# 注意：与现有 production_task 列不冲突 —— 现有是 title/platform_id，这里补 name/platform；
#        现有无 log/error，这里补；其余为自动流专属字段。
NEW_COLUMNS = [
    ("name", "TEXT DEFAULT ''"),                        # 运行名称（与 manual 的 title 并存）
    ("subject", "TEXT DEFAULT ''"),                     # 目标需求
    ("platform", "VARCHAR(32) DEFAULT 'sohu'"),         # 发布平台 code（与 manual 的 platform_id 并存）
    ("publish_mode", "VARCHAR(16) DEFAULT 'geo'"),      # geo / platform / green
    ("output_format", "VARCHAR(16) DEFAULT 'markdown'"),# markdown / mdx
    ("brand_asset_id", "INTEGER DEFAULT 0"),
    ("target_persona_ids", "TEXT DEFAULT ''"),
    ("intent_question_ids", "TEXT DEFAULT ''"),         # 多选意图问题 id 列表（逗号）
    ("doubao_credential_id", "INTEGER DEFAULT 0"),
    ("sohu_credential_id", "INTEGER DEFAULT 0"),
    ("ai_engine", "VARCHAR(32) DEFAULT 'deepseek'"),
    ("llm_config_id", "INTEGER DEFAULT 0"),
    ("mock_doubao", "INTEGER DEFAULT 0"),
    ("compliance_result", "TEXT DEFAULT ''"),
    ("auto_publish", "INTEGER DEFAULT 0"),
    ("geo_content", "TEXT DEFAULT ''"),
    ("review_result", "TEXT DEFAULT ''"),
    ("revise_rounds", "TEXT DEFAULT ''"),
    ("clarified_brief", "TEXT DEFAULT ''"),
    ("editor_review", "TEXT DEFAULT ''"),
    ("confirmed", "INTEGER DEFAULT 0"),
    ("mdx_filename", "TEXT DEFAULT ''"),
    ("mdx_images", "TEXT DEFAULT ''"),
    ("content_asset_id", "INTEGER DEFAULT 0"),
    ("sohu_job_id", "INTEGER DEFAULT 0"),
    ("error", "TEXT DEFAULT ''"),
    ("log", "TEXT DEFAULT ''"),
    # —— 并表簿记字段 ——
    ("mode", "VARCHAR(16) DEFAULT 'manual'"),           # manual / auto
    ("legacy_run_id", "INTEGER DEFAULT 0"),             # 原 browser_studio_run.id；manual 行=0
    ("legacy_status", "VARCHAR(32) DEFAULT ''"),        # 原 browser_studio_run.status（审计保留）
]

# browser_studio_run 中「已存在于 production_task」的共享列（直接复制值，不加新列）
SHARED_FIELDS = [
    "industry_id", "status", "account_id", "persona_id", "target_persona_id",
    "intent_question_id", "keyword_ids", "knowledge_item_ids", "rule_ids",
    "outline_content", "draft_content", "rewrite_content",
    "geo_score", "final_title", "final_content",
    "create_time", "update_time", "is_deleted",
]

# browser_studio_run 中「需映射到 production_task 新增列」的列（1:1，同名）
AUTO_FIELDS = [
    "name", "subject", "platform", "publish_mode", "output_format",
    "brand_asset_id", "target_persona_ids", "intent_question_ids", "doubao_credential_id", "sohu_credential_id",
    "ai_engine", "llm_config_id", "mock_doubao", "compliance_result", "auto_publish",
    "geo_content", "review_result", "revise_rounds", "clarified_brief", "editor_review",
    "confirmed", "mdx_filename", "mdx_images", "content_asset_id", "sohu_job_id",
    "error", "log",
]

# browser_studio_step 的正确建表 DDL（含主键自增 + run_id 索引），用于「脱除旧外键」时重建。
# ⚠️ 绝不能用 CREATE TABLE ... AS SELECT：那会丢掉主键自增，导致后续新步骤插入报 "NULL identity key"。
BSS_CREATE_SQL = """CREATE TABLE browser_studio_step (
	id INTEGER NOT NULL,
	run_id INTEGER NOT NULL,
	step_no INTEGER,
	step_key VARCHAR(32),
	agent VARCHAR(16),
	title TEXT,
	status VARCHAR(32),
	attempts INTEGER,
	last_error TEXT,
	started_at DATETIME,
	finished_at DATETIME,
	result_json TEXT,
	log TEXT,
	request_payload TEXT,
	expected_fields TEXT,
	response_latency_ms INTEGER,
	api_role VARCHAR(16),
	api_config_id INTEGER,
	api_model VARCHAR(64),
	extracted_result TEXT,
	next_action TEXT,
	create_time DATETIME,
	update_time DATETIME,
	PRIMARY KEY (id)
)"""
BSS_COLUMNS = (
    "id, run_id, step_no, step_key, agent, title, status, attempts, last_error, started_at, "
    "finished_at, result_json, log, request_payload, expected_fields, response_latency_ms, "
    "api_role, api_config_id, api_model, extracted_result, next_action, create_time, update_time"
)


def _backup(db_path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{db_path}.bak.{ts}"
    shutil.copy2(db_path, bak)
    return bak


def _existing_cols(conn: sqlite3.Connection, table: str) -> set:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _print_phase(title: str):
    print(f"\n=== {title} ===")


def run(db_path: str, apply: bool):
    if not os.path.exists(db_path):
        print(f"[错误] 找不到数据库：{db_path}")
        sys.exit(1)

    if not apply:
        print("[模式] DRY-RUN（不写库，仅预览）")
    else:
        bak = _backup(db_path)
        print(f"[备份] 已备份 → {bak}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")  # DDL 重建阶段临时关闭

    summary = {"new_cols": 0, "migrated": 0, "skipped": 0,
               "steps_redirected": 0, "llm_redirected": 0, "archived": False}

    # ---------- Phase A：production_task 加列（幂等）----------
    _print_phase("Phase A  为 production_task 增加并表字段")
    pt_cols = _existing_cols(conn, "production_task")
    for col, typ in NEW_COLUMNS:
        if col in pt_cols:
            print(f"  · 跳过（已存在）: {col}")
            continue
        ddl = f"ALTER TABLE production_task ADD COLUMN {col} {typ}"
        if apply:
            conn.execute(ddl)
        print(f"  · {'将添加' if not apply else '已添加'}: {col} {typ}")
        summary["new_cols"] += 1

    # ---------- Phase B：迁移 browser_studio_run → production_task（幂等）----------
    _print_phase("Phase B  迁移 browser_studio_run 历史数据 → production_task(mode='auto')")
    runs = conn.execute(
        "SELECT * FROM browser_studio_run WHERE is_deleted=0 ORDER BY id"
    ).fetchall()
    print(f"  · 待处理 browser_studio_run 行数: {len(runs)}")

    insert_cols = SHARED_FIELDS + AUTO_FIELDS + ["mode", "legacy_run_id", "legacy_status"]
    placeholders = ", ".join(["?"] * len(insert_cols))
    col_sql = ", ".join(insert_cols)

    mapping = {}  # old_run_id -> new_task_id
    for r in runs:
        old_id = r["id"]
        existing = None
        if "legacy_run_id" in pt_cols:
            existing = conn.execute(
                "SELECT id FROM production_task WHERE legacy_run_id=?", (old_id,)
            ).fetchone()
        if existing:
            mapping[old_id] = existing["id"]
            summary["skipped"] += 1
            print(f"  · 跳过（已迁移）run={old_id} → task={existing['id']}")
            continue

        vals = [r[f] for f in SHARED_FIELDS] + [r[f] for f in AUTO_FIELDS]
        vals += ["auto", old_id, r["status"] or ""]  # mode / legacy_run_id / legacy_status

        if apply:
            cur = conn.execute(
                f"INSERT INTO production_task ({col_sql}) VALUES ({placeholders})", vals
            )
            mapping[old_id] = cur.lastrowid
        else:
            mapping[old_id] = f"<new#{summary['migrated'] + 1}>"
        summary["migrated"] += 1
        if apply:
            print(f"  · 迁移 run={old_id} → task={mapping[old_id]}")
        else:
            print(f"  · 将迁移 run={old_id} → task={mapping[old_id]}")

    # ---------- Phase C：重定向外键 ----------
    _print_phase("Phase C  重定向 browser_studio_step / llm_call_log 的 run_id → production_task.id")
    steps = conn.execute("SELECT COUNT(*) AS c FROM browser_studio_step").fetchone()["c"]
    print(f"  · browser_studio_step 总行数: {steps}")
    redirected_steps = 0
    for old_id, new_id in mapping.items():
        if apply:
            n = conn.execute(
                "UPDATE browser_studio_step SET run_id=? WHERE run_id=?", (new_id, old_id)
            ).rowcount
        else:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM browser_studio_step WHERE run_id=?", (old_id,)
            ).fetchone()["c"]
        redirected_steps += (n if isinstance(n, int) else 0)
    summary["steps_redirected"] = redirected_steps
    print(f"  · {'已更新' if apply else '将更新'} browser_studio_step.run_id 行数: {redirected_steps}")

    if apply:
        # 重建表脱除旧外键，但必须保留主键自增（绝不能用 CREATE TABLE ... AS SELECT）。
        # 触发条件：① run_id 仍指向 browser_studio_run 旧外键；② id 不是主键（曾被误建）。
        _fks = conn.execute("PRAGMA foreign_key_list(browser_studio_step)").fetchall()
        _info = conn.execute("PRAGMA table_info(browser_studio_step)").fetchall()
        _id_pk = any(r[1] == "id" and r[5] == 1 for r in _info)
        if any(fk[2] == "browser_studio_run" for fk in _fks) or (not _id_pk):
            conn.execute("DROP TABLE IF EXISTS browser_studio_step_old")
            conn.execute("ALTER TABLE browser_studio_step RENAME TO browser_studio_step_old")
            conn.execute(BSS_CREATE_SQL)
            conn.execute(
                f"INSERT INTO browser_studio_step ({BSS_COLUMNS}) SELECT {BSS_COLUMNS} FROM browser_studio_step_old"
            )
            conn.execute("DROP TABLE browser_studio_step_old")
            print("  · 已重建 browser_studio_step（脱除旧外键约束，保留主键自增）")
        else:
            print("  · browser_studio_step 已无旧外键且主键完好，跳过重建")
    else:
        print("  · [dry-run] 将重建 browser_studio_step 以脱除指向 browser_studio_run 的旧外键（保留主键自增）")

    llm_redirected = 0
    for old_id, new_id in mapping.items():
        if apply:
            n = conn.execute(
                "UPDATE llm_call_log SET run_id=? WHERE run_id=?", (new_id, old_id)
            ).rowcount
        else:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM llm_call_log WHERE run_id=?", (old_id,)
            ).fetchone()["c"]
        llm_redirected += (n if isinstance(n, int) else 0)
    summary["llm_redirected"] = llm_redirected
    print(f"  · {'已更新' if apply else '将更新'} llm_call_log.run_id 行数: {llm_redirected}")

    # ---------- Phase D：归档旧表 ----------
    _print_phase("Phase D  归档 browser_studio_run → _archive_browser_studio_run")
    if _existing_cols(conn, "_archive_browser_studio_run"):
        print("  · _archive_browser_studio_run 已存在，跳过改名（保留既有归档）")
        summary["archived"] = True
    else:
        if apply:
            conn.execute("ALTER TABLE browser_studio_run RENAME TO _archive_browser_studio_run")
            print("  · 已改名 browser_studio_run → _archive_browser_studio_run（数据保留，只读归档）")
        else:
            print("  · [dry-run] 将改名 browser_studio_run → _archive_browser_studio_run")
        summary["archived"] = True

    if apply:
        conn.commit()
        print("\n[完成] 已提交并表迁移。")
    else:
        print("\n[预览结束] 未做任何写操作。确认无误后加 --apply 执行（会自动先备份）。")

    conn.execute("PRAGMA foreign_keys=ON")
    conn.close()

    print("\n================ 汇总 ================")
    print(f"  新增列        : {summary['new_cols']}")
    print(f"  迁移行数      : {summary['migrated']}")
    print(f"  跳过(已迁移)  : {summary['skipped']}")
    print(f"  步骤外键重定向: {summary['steps_redirected']}")
    print(f"  调用日志重定向: {summary['llm_redirected']}")
    print(f"  旧表已归档    : {summary['archived']}")


def main():
    ap = argparse.ArgumentParser(description="P2 数据并表迁移（browser_studio_run → production_task）")
    ap.add_argument("--db", default=DEFAULT_DB, help="SQLite 数据库路径（默认 backend/data/database.db）")
    ap.add_argument("--apply", action="store_true", help="真正执行写库；不加则仅 dry-run 预览")
    args = ap.parse_args()
    run(args.db, args.apply)


if __name__ == "__main__":
    main()
