"""
FastAPI 主程序入口
多行业提示词矩阵管理系统 - 后端服务
"""
import os
import sys
import webbrowser
import threading
import time
import sqlite3
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.schema import CreateTable

from .database import Base, engine, SessionLocal, DB_PATH
from .models import SysUser, Industry, OperationLog, TargetPersona, IntentQuestion, PromptLibraryItem, GeoMonitor, GeoMonitorReply, LlmConfig, PlatformCredential, PublishJob, BrowserStudioRun, BrowserStudioStep, AutomationPrompt, LlmCallLog, PublishStrategy
from .utils import encrypt_password
from .routers import (
    industry, platform, knowledge, rule, keyword, content, effect,
    prompt_library, production, brand_asset, platform_preset, search, intent, geo_monitor, geo_canvas,
    llm, publish, browser_studio, automation_prompts, background,
)


def _safe_create_all():
    """create_all 安全封装：兼容 P2 并表 cutover 后的状态。

    cutover 后 browser_studio_run 已改名归档为 _archive_browser_studio_run，
    其索引名 ix_browser_studio_run_industry_id 仍挂在归档表上。若 create_all 尝试重建
    browser_studio_run 表（及该索引）→ 报 "index already exists" 致启动失败。

    做法：显式传入 tables 列表，排除 BrowserStudioRun.__table__，使 create_all 永不重建该表
    （模型查询仍走 BrowserStudioRun.__table__，get_auto_run 的 fallback 在表不存在时捕获返回 None）。
    这是最稳妥的方式——不依赖 DB 内省、不临时注销 metadata，避免"失败 create_all 反复重建空表"的死循环。
    """
    from .models import BrowserStudioRun
    _tables = [t for t in Base.metadata.tables.values() if t is not BrowserStudioRun.__table__]
    Base.metadata.create_all(bind=engine, tables=_tables)


def init_db():
    _safe_create_all()

    # ===== 轻量级迁移：为已有表添加新列（SQLite ALTER TABLE） =====
    from sqlalchemy import text
    with engine.connect() as conn:
        # 检查 production_task 表是否有 knowledge_item_ids 列
        try:
            cols = conn.execute(text("PRAGMA table_info(production_task)")).fetchall()
            col_names = [c[1] for c in cols]
            if "knowledge_item_ids" not in col_names:
                conn.execute(text("ALTER TABLE production_task ADD COLUMN knowledge_item_ids TEXT DEFAULT ''"))
                conn.commit()
            # v4 新增：第8步配图方案
            if "illustration_plan" not in col_names:
                conn.execute(text("ALTER TABLE production_task ADD COLUMN illustration_plan TEXT DEFAULT ''"))
                conn.commit()
            # 内容运营日历：计划发布日期 YYYY-MM-DD
            if "plan_date" not in col_names:
                conn.execute(text("ALTER TABLE production_task ADD COLUMN plan_date TEXT DEFAULT ''"))
                conn.commit()
            # 第9步「安全发布 & GEO 筛选」产出的最终标题（与 final_content 配对，可直接复制发布到平台）
            if "final_title" not in col_names:
                conn.execute(text("ALTER TABLE production_task ADD COLUMN final_title TEXT DEFAULT ''"))
                conn.commit()
            # 发布自动化：末次发布状态 + 关联最近一次 publish_job
            if "published_status" not in col_names:
                conn.execute(text("ALTER TABLE production_task ADD COLUMN published_status TEXT DEFAULT ''"))
                conn.commit()
            if "last_publish_job_id" not in col_names:
                conn.execute(text("ALTER TABLE production_task ADD COLUMN last_publish_job_id INTEGER DEFAULT 0"))
                conn.commit()
            # GEO 作战：绑定目标画像与意图问题（生成"带信号的 GEO 软文"的锚点）
            # create_all 不会为已存在的表添加新列，这里一次性补齐
            _GEO_COLS = {
                "target_persona_id": "INTEGER DEFAULT 0",
                "target_persona_snapshot": "TEXT DEFAULT ''",
                "intent_question_id": "INTEGER DEFAULT 0",
                "intent_question_snapshot": "TEXT DEFAULT ''",
                "geo_score": "INTEGER DEFAULT 0",
                "target_needs": "TEXT DEFAULT ''",
            }
            for _cname, _ctype in _GEO_COLS.items():
                if _cname not in col_names:
                    conn.execute(text(f"ALTER TABLE production_task ADD COLUMN {_cname} {_ctype}"))
                    conn.commit()
        except Exception:
            pass  # 表不存在时跳过，create_all 会创建

    # P2 并表：为 production_task 补齐浏览器工作室（自动流）所需字段，使自动流直接写统一任务表。
    # 列定义与 migrations/merge_browser_studio_run.py 的 NEW_COLUMNS 保持一致（含 mode/legacy_run_id/legacy_status 簿记字段）。
    try:
        with engine.connect() as conn:
            pt_cols2 = conn.execute(text("PRAGMA table_info(production_task)")).fetchall()
            pt_names2 = [c[1] for c in pt_cols2]
            _P2_COLS = [
                ("name", "TEXT DEFAULT ''"),
                ("subject", "TEXT DEFAULT ''"),
                ("platform", "VARCHAR(32) DEFAULT 'sohu'"),
                ("publish_mode", "VARCHAR(16) DEFAULT 'geo'"),
                ("output_format", "VARCHAR(16) DEFAULT 'markdown'"),
                ("brand_asset_id", "INTEGER DEFAULT 0"),
                ("target_persona_ids", "TEXT DEFAULT ''"),
                ("intent_question_ids", "TEXT DEFAULT ''"),
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
                ("mode", "VARCHAR(16) DEFAULT 'manual'"),
                ("legacy_run_id", "INTEGER DEFAULT 0"),
                ("legacy_status", "VARCHAR(32) DEFAULT ''"),
            ]
            for _cname, _ctype in _P2_COLS:
                if _cname not in pt_names2:
                    conn.execute(text(f"ALTER TABLE production_task ADD COLUMN {_cname} {_ctype}"))
                    conn.commit()
        print("[迁移] P2 已为 production_task 补齐自动流并表字段")
    except Exception as e:
        print(f"[迁移] P2 production_task 并表字段迁移跳过: {e}")

    # P2：脱除 browser_studio_step.run_id 对 browser_studio_run 的旧外键（统一任务表后 run_id 指向 production_task.id）。
    # SQLite 不支持 ALTER DROP CONSTRAINT，故以「改名旧表 → 按模型重建正确 schema（保留主键自增/索引）
    # → 复制数据 → 删旧表」实现。注意：绝不能用 CREATE TABLE ... AS SELECT，那会丢掉主键自增，
    # 导致后续新步骤插入报 "NULL identity key"。
    # 关键：必须用「原生 sqlite3 连接」执行重建。SQLAlchemy 连接的 autobegin 事务会让
    # ALTER...RENAME 与后续 INSERT...SELECT 处于同一快照，导致 SELECT 读到空表、数据丢失。
    # 重建条件（幂等）：① run_id 仍指向 browser_studio_run 旧外键；② id 不是主键（曾被误建）。
    try:
        import sqlite3 as _sqlite3
        _raw = _sqlite3.connect(DB_PATH)
        try:
            _raw.execute("PRAGMA foreign_keys=OFF")
            _tbl = _raw.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='browser_studio_step'"
            ).fetchone()
            if _tbl:
                _fks = _raw.execute("PRAGMA foreign_key_list(browser_studio_step)").fetchall()
                _info = _raw.execute("PRAGMA table_info(browser_studio_step)").fetchall()
                _id_pk = any(r[1] == "id" and r[5] == 1 for r in _info)
                if any(fk[2] == "browser_studio_run" for fk in _fks) or (not _id_pk):
                    _raw.execute("DROP TABLE IF EXISTS browser_studio_step_old")
                    _raw.execute("ALTER TABLE browser_studio_step RENAME TO browser_studio_step_old")
                    _raw.execute(str(CreateTable(BrowserStudioStep.__table__)))
                    _cols = ", ".join(BrowserStudioStep.__table__.columns.keys())
                    _raw.execute(
                        f"INSERT INTO browser_studio_step ({_cols}) SELECT {_cols} FROM browser_studio_step_old"
                    )
                    _raw.execute("DROP TABLE browser_studio_step_old")
                    _raw.commit()
                    print("[迁移] P2 已修复 browser_studio_step（脱除旧外键 / 恢复主键自增）")
            _raw.execute("PRAGMA foreign_keys=ON")
        finally:
            _raw.close()
    except Exception as e:
        print(f"[迁移] P2 browser_studio_step 修复跳过: {e}")


    # ===== 关键词分组：为已有 keyword 表添加 group_id 列 =====
    try:
        with engine.connect() as conn:
            kcols = conn.execute(text("PRAGMA table_info(keyword)")).fetchall()
            kcol_names = [c[1] for c in kcols]
            if "group_id" not in kcol_names:
                conn.execute(text("ALTER TABLE keyword ADD COLUMN group_id INTEGER"))
                conn.commit()
    except Exception:
        pass

    # GEO 监测：为已有 geo_monitor_reply 表补齐 recommended 列（AI 是否明确推荐该品牌）
    try:
        with engine.connect() as conn:
            gcols = conn.execute(text("PRAGMA table_info(geo_monitor_reply)")).fetchall()
            gcol_names = [c[1] for c in gcols]
            if "recommended" not in gcol_names:
                conn.execute(text("ALTER TABLE geo_monitor_reply ADD COLUMN recommended INTEGER DEFAULT 0"))
                conn.commit()
    except Exception:
        pass

    # 平台特性/规则：为已有 platform 表添加 characteristics / rules 列，并按预设回填（仅当为空）
    try:
        with engine.connect() as conn:
            pcols = conn.execute(text("PRAGMA table_info(platform)")).fetchall()
            pcol_names = [c[1] for c in pcols]
            for _cname, _ctype in (("characteristics", "TEXT DEFAULT ''"), ("rules", "TEXT DEFAULT ''")):
                if _cname not in pcol_names:
                    conn.execute(text(f"ALTER TABLE platform ADD COLUMN {_cname} {_ctype}"))
                    conn.commit()
        # 回填：按名称匹配预设，填入特性/规则（不覆盖用户已填内容）
        from .models import Platform as _Platform, PLATFORM_PRESETS as _PRESETS
        _by_name = {p["name"]: p for p in _PRESETS}
        with SessionLocal() as s:
            for r in s.query(_Platform).filter(_Platform.is_deleted == 0).all():
                preset = _by_name.get(r.name)
                if not preset:
                    continue
                changed = False
                if (not r.characteristics) and preset.get("characteristics"):
                    r.characteristics = preset["characteristics"]; changed = True
                if (not r.rules) and preset.get("rules"):
                    r.rules = preset["rules"]; changed = True
                if changed:
                    s.commit()
        print("[迁移] 已为 platform 表补齐 characteristics/rules 列并按预设回填")
    except Exception as e:
        print(f"[迁移] platform characteristics/rules 迁移跳过: {e}")

    # 双模式发布：为 platform 表补齐 publish_mode 列，并把 7 大内容平台预设回填为 platform（平台合规模式）
    try:
        with engine.connect() as conn:
            pcols = conn.execute(text("PRAGMA table_info(platform)")).fetchall()
            pcol_names = [c[1] for c in pcols]
            if "publish_mode" not in pcol_names:
                conn.execute(text("ALTER TABLE platform ADD COLUMN publish_mode TEXT DEFAULT 'geo'"))
                conn.commit()
        # 内容平台（搜狐号/百家号/网易号/今日头条号/知乎号/微信公众号/小红书号）统一设为平台合规模式
        from .models import Platform as _Platform, PLATFORM_PRESETS as _PRESETS
        _content_names = {p["name"] for p in _PRESETS}
        with SessionLocal() as s:
            _updated = 0
            for r in s.query(_Platform).filter(_Platform.is_deleted == 0).all():
                if r.name in _content_names and (not r.publish_mode or r.publish_mode == "geo"):
                    r.publish_mode = "platform"
                    _updated += 1
            if _updated:
                s.commit()
                print(f"[迁移] 已为 {_updated} 个内容平台设置 publish_mode=platform")
    except Exception as e:
        print(f"[迁移] platform publish_mode 迁移跳过: {e}")

    # 三模式 + 官网 MDX：为 platform 表补齐 output_format / site_url / publish_prompt 列，
    # 并确保每个行业都存在「官网/自建站」平台（output_format=mdx，publish_prompt=官网 MDX 模板）。
    try:
        with engine.connect() as conn:
            pcols = conn.execute(text("PRAGMA table_info(platform)")).fetchall()
            pcol_names = [c[1] for c in pcols]
            for _cname, _ctype in (
                ("output_format", "TEXT DEFAULT 'markdown'"),
                ("site_url", "TEXT DEFAULT ''"),
                ("publish_prompt", "TEXT DEFAULT ''"),
            ):
                if _cname not in pcol_names:
                    conn.execute(text(f"ALTER TABLE platform ADD COLUMN {_cname} {_ctype}"))
                    conn.commit()
        from .models import Platform as _Platform, PLATFORM_PRESETS as _PRESETS
        from .services.prompt_engine import OFFICIAL_MDX_PROMPT, OFFICIAL_SITE_URL
        _official_preset = next((p for p in _PRESETS if p["name"] == "官网/自建站"), None)
        _content_names = {p["name"] for p in _PRESETS if p["name"] != "官网/自建站"}
        with SessionLocal() as s:
            # 已存在的内容平台统一 output_format=markdown
            for r in s.query(_Platform).filter(_Platform.is_deleted == 0).all():
                if r.name in _content_names and (not r.output_format or r.output_format == ""):
                    r.output_format = "markdown"
            # 确保每个有平台的行业都存在「官网/自建站」平台
            if _official_preset:
                _inds = s.query(_Platform.industry_id).filter(_Platform.is_deleted == 0).distinct().all()
                for (_ind,) in _inds:
                    _exists = s.query(_Platform).filter(
                        _Platform.industry_id == _ind,
                        _Platform.name == _official_preset["name"],
                        _Platform.is_deleted == 0,
                    ).first()
                    if not _exists:
                        s.add(_Platform(
                            industry_id=_ind,
                            name=_official_preset["name"],
                            word_count_min=_official_preset["word_count_min"],
                            word_count_max=_official_preset["word_count_max"],
                            compliance_level=_official_preset["compliance_level"],
                            config=_official_preset["config"],
                            characteristics=_official_preset.get("characteristics", ""),
                            rules=_official_preset.get("rules", ""),
                            publish_mode=_official_preset.get("publish_mode", "geo"),
                            output_format=_official_preset.get("output_format", "mdx"),
                            site_url=_official_preset.get("site_url", ""),
                            publish_prompt=OFFICIAL_MDX_PROMPT,
                            sort=8,
                        ))
                s.commit()
            # 回填已存在官网平台的 publish_prompt / output_format / site_url
            for r in s.query(_Platform).filter(_Platform.is_deleted == 0).all():
                if r.name == "官网/自建站":
                    if not r.publish_prompt:
                        r.publish_prompt = OFFICIAL_MDX_PROMPT
                    if not r.output_format or r.output_format == "":
                        r.output_format = "mdx"
                    if not r.site_url:
                        r.site_url = (_official_preset or {}).get("site_url", OFFICIAL_SITE_URL)
            s.commit()
            print("[迁移] 已补齐 platform.output_format/site_url/publish_prompt 并确保官网/自建站平台存在")
    except Exception as e:
        print(f"[迁移] platform output_format/site_url/publish_prompt 迁移跳过: {e}")

    # 浏览器工作室：为已有 browser_studio_run 表补齐 ai_engine 列（创作引擎：deepseek/doubao/mock）
    try:
        with engine.connect() as conn:
            bsr_cols = conn.execute(text("PRAGMA table_info(browser_studio_run)")).fetchall()
            bsr_names = [c[1] for c in bsr_cols]
            if not bsr_names:
                # P2 并表 cutover 后 browser_studio_run 已改名归档为 _archive_browser_studio_run，无需再补齐列
                print("[迁移] browser_studio_run 表不存在（已归档），跳过其补齐列迁移")
            else:
                if "ai_engine" not in bsr_names:
                    conn.execute(text("ALTER TABLE browser_studio_run ADD COLUMN ai_engine TEXT DEFAULT 'deepseek'"))
                    conn.commit()
                    # 兼容旧数据：mock_doubao=1 的运行标记为 mock
                    conn.execute(text("UPDATE browser_studio_run SET ai_engine='mock' WHERE mock_doubao=1 AND (ai_engine IS NULL OR ai_engine='')"))
                    conn.commit()
                    print("[迁移] 已为 browser_studio_run 表补齐 ai_engine 列")
                if "llm_config_id" not in bsr_names:
                    conn.execute(text("ALTER TABLE browser_studio_run ADD COLUMN llm_config_id INTEGER DEFAULT 0"))
                    conn.commit()
                    print("[迁移] 已为 browser_studio_run 表补齐 llm_config_id 列")
                if "compliance_result" not in bsr_names:
                    conn.execute(text("ALTER TABLE browser_studio_run ADD COLUMN compliance_result TEXT DEFAULT ''"))
                    conn.commit()
                    print("[迁移] 已为 browser_studio_run 表补齐 compliance_result 列")
                if "publish_mode" not in bsr_names:
                    conn.execute(text("ALTER TABLE browser_studio_run ADD COLUMN publish_mode TEXT DEFAULT 'geo'"))
                    conn.commit()
                    # 兼容旧数据：内容平台（搜狐/知乎/网易/头条/微信/小红书/百家）的运行标记为 platform
                    conn.execute(text(
                        "UPDATE browser_studio_run SET publish_mode='platform' "
                        "WHERE platform IN ('sohu','zhihu','wangyi','toutiao','wechat','xiaohongshu','baijiahao') "
                        "AND (publish_mode IS NULL OR publish_mode='')"
                    ))
                    conn.commit()
                    print("[迁移] 已为 browser_studio_run 表补齐 publish_mode 列（内容平台回填 platform）")
                for _col, _typ in [
                    ("outline_content", "TEXT DEFAULT ''"),
                    ("draft_content", "TEXT DEFAULT ''"),
                    ("rewrite_content", "TEXT DEFAULT ''"),
                    ("geo_content", "TEXT DEFAULT ''"),
                    ("review_result", "TEXT DEFAULT ''"),
                    ("revise_rounds", "TEXT DEFAULT ''"),
                    ("geo_score", "INTEGER DEFAULT 0"),
                    ("confirmed", "INTEGER DEFAULT 0"),
                    ("output_format", "TEXT DEFAULT 'markdown'"),
                    ("mdx_filename", "TEXT DEFAULT ''"),
                    ("mdx_images", "TEXT DEFAULT ''"),
                ]:
                    if _col not in bsr_names:
                        conn.execute(text(f"ALTER TABLE browser_studio_run ADD COLUMN {_col} {_typ}"))
                        conn.commit()
                        print(f"[迁移] 已为 browser_studio_run 表补齐 {_col} 列")
    except Exception as e:
        print(f"[迁移] browser_studio_run ai_engine 迁移跳过: {e}")

    # 自动化提示词表（automation_prompt）：页面可编辑，覆盖默认提示词常量。
    try:
        AutomationPrompt.__table__.create(bind=engine, checkfirst=True)
        with SessionLocal() as s:
            from .services.automation_prompts import seed_automation_prompts
            seed_automation_prompts(s)
        print("[初始化] 已确保 automation_prompt 表存在并完成默认种子")
    except Exception as e:
        print(f"[初始化] automation_prompt 种子跳过: {e}")

    # 三 API 调度：LlmConfig 增加 role 列（research/writing/review/general）
    try:
        with engine.connect() as conn:
            lc_cols = conn.execute(text("PRAGMA table_info(llm_config)")).fetchall()
            lc_names = [c[1] for c in lc_cols]
            if "role" not in lc_names:
                conn.execute(text("ALTER TABLE llm_config ADD COLUMN role TEXT DEFAULT 'general'"))
                conn.commit()
                print("[迁移] 已为 llm_config 表补齐 role 列（三 API 角色路由）")
    except Exception as e:
        print(f"[迁移] llm_config.role 迁移跳过: {e}")

    # 步骤透明化：BrowserStudioStep 增加发送内容/耗时/提取结果/下一步等列
    try:
        with engine.connect() as conn:
            bs_cols = conn.execute(text("PRAGMA table_info(browser_studio_step)")).fetchall()
            bs_names = [c[1] for c in bs_cols]
            for _col, _typ in [
                ("request_payload", "TEXT DEFAULT ''"),
                ("expected_fields", "TEXT DEFAULT ''"),
                ("response_latency_ms", "INTEGER DEFAULT 0"),
                ("api_role", "TEXT DEFAULT ''"),
                ("api_config_id", "INTEGER DEFAULT 0"),
                ("api_model", "TEXT DEFAULT ''"),
                ("extracted_result", "TEXT DEFAULT ''"),
                ("next_action", "TEXT DEFAULT ''"),
            ]:
                if _col not in bs_names:
                    conn.execute(text(f"ALTER TABLE browser_studio_step ADD COLUMN {_col} {_typ}"))
                    conn.commit()
        print("[迁移] 已为 browser_studio_step 表补齐步骤透明化列")
    except Exception as e:
        print(f"[迁移] browser_studio_step 透明化列迁移跳过: {e}")

    # LLM 调用日志表 + 平台合规策略表
    try:
        LlmCallLog.__table__.create(bind=engine, checkfirst=True)
        PublishStrategy.__table__.create(bind=engine, checkfirst=True)
        print("[初始化] 已确保 llm_call_log / publish_strategy 表存在")
    except Exception as e:
        print(f"[初始化] llm_call_log / publish_strategy 建表跳过: {e}")

    # 平台合规策略种子（按平台 publish_mode 播种默认策略）
    try:
        with SessionLocal() as s:
            from .services.publish_strategy import seed_publish_strategies
            n = seed_publish_strategies(s)
        print(f"[初始化] 平台合规策略种子完成（新增 {n} 条）")
    except Exception as e:
        print(f"[初始化] 平台合规策略种子跳过: {e}")

    # 清理旧版孤儿表（prompt_template / prompt_generate_log 已被 prompt_library 取代）
    try:
        with engine.connect() as conn:
            for tbl in ("prompt_template", "prompt_generate_log"):
                conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
            conn.commit()
    except Exception:
        pass

    # GEO 模块①迁移：intent_question 早期版本给 persona_id 加了外键约束，
    # 但"未关联画像"用 persona_id=0 表示，会触发 FOREIGN KEY 约束失败。
    # 这里一次性把该表重建为"无外键"版本（列结构不变，保留已有数据）。
    try:
        with engine.connect() as conn:
            fk = conn.execute(text("PRAGMA foreign_key_list(intent_question)")).fetchall()
            if fk:
                conn.execute(text("ALTER TABLE intent_question RENAME TO _intent_question_old"))
                conn.commit()
                # 重命名表会保留旧索引名，先删掉避免 create_all 重建时命名冲突
                conn.execute(text("DROP INDEX IF EXISTS ix_intent_question_industry_id"))
                conn.commit()
                _safe_create_all()  # 用当前（无外键）模型重建表（已兼容 P2 归档态）
                cols = [c.name for c in Base.metadata.tables["intent_question"].columns]
                conn.execute(text(
                    f"INSERT INTO intent_question ({', '.join(cols)}) "
                    f"SELECT {', '.join(cols)} FROM _intent_question_old"
                ))
                conn.execute(text("DROP TABLE _intent_question_old"))
                conn.commit()
                print("[迁移] 已重建 intent_question（移除 persona_id 外键约束）")
    except Exception as e:
        print(f"[迁移] intent_question 重建跳过: {e}")

    # GEO 合并迁移：原「安全筛选(safety)」与「GEO 软文(geo)」两类提示词合并为
    # 「安全 · GEO 筛选(geo)」。将历史 safety 类目提示词改归到 geo，避免类目消失后变成孤儿。
    try:
        with engine.connect() as conn:
            conn.execute(text("UPDATE prompt_library_item SET category='geo' WHERE category='safety'"))
            conn.commit()
            print("[迁移] 已将 safety 类提示词并入 geo 类（安全 · GEO 筛选）")
    except Exception as e:
        print(f"[迁移] safety→geo 合并跳过: {e}")

    # GEO 需求注入迁移：对现存「默认」outline/draft/rewrite 提示词，
    # 若尚未引用 {geo_signals}，幂等追加上【目标客户需求 / GEO 信号】块，
    # 使第4步"目标客户需求"在已有行业的软文生产中也真实发挥作用。
    try:
        _geo_block = (
            "\n【目标客户需求 / GEO 信号（若第4步已设定则必用）】\n{geo_signals}\n"
        )
        with SessionLocal() as s:
            items = s.query(PromptLibraryItem).filter(
                PromptLibraryItem.category.in_(["outline", "draft", "rewrite"]),
                PromptLibraryItem.is_deleted == 0,
            ).all()
            for it in items:
                if not it.content or "{geo_signals}" in it.content:
                    continue
                if not (it.name or "").startswith("默认"):
                    continue
                it.content = it.content.rstrip() + _geo_block
            s.commit()
        print("[迁移] 已为现存默认 outline/draft/rewrite 提示词追加 GEO 需求块")
    except Exception as e:
        print(f"[迁移] 默认提示词 GEO 块追加跳过: {e}")

    db = SessionLocal()
    try:
        admin = db.query(SysUser).filter(SysUser.username == "admin").first()
        if not admin:
            admin = SysUser(
                username="admin",
                password=encrypt_password("admin123"),
                role="admin",
                industry_perms="all",
                status=1,
            )
            db.add(admin)
            db.commit()
            print("[初始化] 已创建默认管理员: admin / admin123")

        # 创建默认行业
        ind = db.query(Industry).filter(Industry.is_deleted == 0).first()
        if not ind:
            ind = Industry(name="默认行业", description="系统默认创建的行业空间", sort=0)
            db.add(ind)
            db.commit()
            print("[初始化] 已创建默认行业空间")

        # GEO 模块①：为默认（首个）行业预置默认目标画像 + 意图问题。
        # 画像与问题各自独立判空播种（幂等），避免一方已存在导致另一方不被播种。
        try:
            tp_count = db.query(TargetPersona).filter(
                TargetPersona.industry_id == ind.id, TargetPersona.is_deleted == 0
            ).count()
            if tp_count == 0:
                intent.seed_target_personas(ind.id, db)
                db.commit()
            iq_count = db.query(IntentQuestion).filter(
                IntentQuestion.industry_id == ind.id, IntentQuestion.is_deleted == 0
            ).count()
            if iq_count == 0:
                intent.seed_intent_questions(ind.id, db)
                db.commit()
            if tp_count == 0 or iq_count == 0:
                print("[初始化] 已预置 GEO 默认画像与意图问题")
        except Exception as e:
            db.rollback()
            print(f"[初始化] GEO 预置跳过: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="多行业提示词矩阵管理系统",
    description="面向多行业、多平台、多账号矩阵的纯提示词编排与全流程管控工具",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS 来源：生产部署可设 BACKEND_CORS_ORIGINS=https://a,https://b 显式收紧；
# 未设置则回退通配（本地前后端同进程单体部署场景）。
_cors_origins = [o.strip() for o in os.environ.get("BACKEND_CORS_ORIGINS", "").split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    # 系统无 Cookie/Session 鉴权，凭据类 CORS 与 wildcard origin 互斥（浏览器会拒绝），故关闭 credentials。
    # 前后端同进程同端口（FastAPI 托管 static），仅开发态 vite dev 跨端口需要跨域，关闭 credentials 即可满足。
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
for r in [
    industry, platform, knowledge, rule, keyword, content, effect,
    prompt_library, production, brand_asset, platform_preset, search, intent, geo_monitor, geo_canvas,
    llm, publish, browser_studio, automation_prompts, background,
]:
    app.include_router(r.router)


# 静态文件 & SPA 回退
# 源码模式=backend/static；打包 exe 模式=PyInstaller 解压目录下的 static
from .paths import resource_dir
STATIC_DIR = os.path.join(resource_dir(), "static")
if os.path.isdir(STATIC_DIR) and os.path.exists(os.path.join(STATIC_DIR, "index.html")):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/")
    def root():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"code": 404, "msg": "Not Found"}, status_code=404)
        candidate = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
else:
    @app.get("/")
    def root():
        return {"msg": "前端未构建，请先执行 npm run build", "docs": "/docs"}

    @app.get("/{full_path:path}")
    def spa_fallback_missing(full_path: str):
        # 前端未构建时，深链接也返回提示而非 404 JSON，避免刷新直接报错
        if full_path.startswith("api/"):
            return JSONResponse({"code": 404, "msg": "Not Found"}, status_code=404)
        return JSONResponse(
            {"msg": "前端未构建，请先执行 npm run build", "docs": "/docs"},
            status_code=200,
        )


def open_browser(url: str, delay: float = 1.5):
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    import uvicorn
    host = "127.0.0.1"
    port = 8765
    url = f"http://{host}:{port}"
    print("=" * 60)
    print("  多行业提示词矩阵管理系统 v2.0.0")
    print("=" * 60)
    print(f"  服务地址: {url}")
    print(f"  API文档:  {url}/docs")
    print(f"  默认账号: admin / admin123")
    print("=" * 60)
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
