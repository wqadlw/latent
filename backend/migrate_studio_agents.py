# -*- coding: utf-8 -*-
"""浏览器工作室双智能体字段迁移：为 browser_studio_run / browser_studio_step 追加列（幂等）。"""
import os
import sqlite3

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "database.db")


def col_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    adds = [
        ("browser_studio_run", "clarified_brief", "TEXT DEFAULT ''"),
        ("browser_studio_run", "editor_review", "TEXT DEFAULT ''"),
        ("browser_studio_step", "agent", "TEXT DEFAULT ''"),
    ]
    for table, col, typ in adds:
        if not col_exists(cur, table, col):
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            print(f"  + {table}.{col} 已添加")
        else:
            print(f"  = {table}.{col} 已存在，跳过")
    con.commit()
    con.close()
    print("迁移完成。")


if __name__ == "__main__":
    main()
