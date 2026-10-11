# -*- coding: utf-8 -*-
"""
批量生产（Batch）

解决的问题
----------
「这个月要在这个行业铺 20 篇内容，覆盖 5 个选题 × 4 个平台」——
在阶段 C 之前，这意味着手工新建 20 次运行、点 20 次开始，而且它们会同时开跑。

本模块只做一件事：**把一份「选题 × 平台」规格展开成 N 条运行 + N 条排队作业**，
共享一个 ``batch_id`` 便于看批次进度。执行、并发、重试全交给 ``services.task_queue``。

刻意的边界：批量生产**不**批量过审
----------------------------------
很容易顺手加一个「全部自动确认并入内容中心」，但那等于让 AI 生成的品牌内容
无人过审直接进库。企业内容流水线的底线是**必须有人看过**，所以批次跑到
「等待确认」就停下，由人来批量确认。这里不提供绕过它的开关。

去重（默认开启）
----------------
同行业 + 同平台 + 同选题 已存在一条未失败/未取消的运行 → 视为重复并跳过。
理由是重复提交的代价是**真金白银**（每条运行 6~10 次 LLM 调用），
而运营在页面上多贴一次同一段选题的概率并不低。想强制重跑可显式关掉去重。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models import Industry, ProductionTask
from . import pipeline as pipeline_svc
from . import task_queue
from .doubao_studio import PLATFORM_PUBLISH_MODE

#: 单批上限。定这个数不是为了性能，而是防止「一次提交 500 条」把队列、
#: LLM 配额和磁盘日志一起拖垮 —— 那种量级本来就该分几天做。
MAX_BATCH = 60

#: 选题长度上限（与运行名展示宽度对齐）。
MAX_SUBJECT_LEN = 200

#: 视为「已经做过、不必重复」的运行终态之外的集合 —— 换句话说，
#: 失败和取消的运行不算重复，允许重投。
_DEAD_STATUS = ("failed", "cancelled")


def _clean_subjects(raw: Any) -> List[str]:
    """清洗选题列表：去空白、去空行、去重（保序）、截断超长。"""
    if isinstance(raw, str):
        items = raw.replace("\r", "\n").split("\n")
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = []
    out: List[str] = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        if len(text) > MAX_SUBJECT_LEN:
            text = text[:MAX_SUBJECT_LEN]
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _clean_platforms(raw: Any) -> List[str]:
    if isinstance(raw, str):
        items = [p.strip() for p in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        items = [str(p or "").strip() for p in raw]
    else:
        items = []
    out: List[str] = []
    for code in items:
        if code and code not in out:
            out.append(code)
    return out or ["sohu"]


def _ids_csv(raw: Any) -> str:
    """把 id 列表 / 逗号串规整成逗号分隔字符串（与 create_run 的存储口径一致）。"""
    if raw in (None, ""):
        return ""
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        parts = [str(p).strip() for p in raw]
    else:
        return ""
    return ",".join(p for p in parts if p)


def _find_duplicate(db: Any, industry_id: int, platform: str, subject: str) -> Optional[ProductionTask]:
    return (
        db.query(ProductionTask)
        .filter(
            ProductionTask.industry_id == int(industry_id),
            ProductionTask.mode == "auto",
            ProductionTask.is_deleted == 0,
            ProductionTask.platform == platform,
            ProductionTask.subject == subject,
            ProductionTask.status.notin_(_DEAD_STATUS),
        )
        .order_by(ProductionTask.id.desc())
        .first()
    )


def expand(db: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """把规格展开成清单（**不落库**）。

    预览与创建共用这一份展开逻辑，避免「预览说 12 条、实际创建 9 条」这种
    最伤信任的不一致。
    """
    industry_id = int(payload.get("industry_id") or 0)
    subjects = _clean_subjects(payload.get("subjects") or payload.get("subject") or "")
    platforms = _clean_platforms(payload.get("platforms") or payload.get("platform"))
    skip_duplicates = payload.get("skip_duplicates")
    if skip_duplicates is None:
        skip_duplicates = True
    else:
        skip_duplicates = bool(skip_duplicates)

    industry = None
    if industry_id:
        industry = db.query(Industry).filter(Industry.id == industry_id).first()

    items: List[Dict[str, Any]] = []
    truncated = False
    for subject in subjects:
        for platform in platforms:
            if len(items) >= MAX_BATCH:
                truncated = True
                break
            dup = _find_duplicate(db, industry_id, platform, subject) if (skip_duplicates and industry_id) else None
            items.append({
                "subject": subject,
                "platform": platform,
                "publish_mode": PLATFORM_PUBLISH_MODE.get(platform, "geo"),
                "output_format": "mdx" if platform in ("official", "selfsite") else "markdown",
                "duplicate": dup is not None,
                "duplicate_run_id": dup.id if dup is not None else 0,
                "duplicate_reason": (f"同行业同平台已存在同选题运行 #{dup.id}（{dup.status}）"
                                     if dup is not None else ""),
            })
        if truncated:
            break

    will_create = [i for i in items if not i["duplicate"]]
    will_skip = [i for i in items if i["duplicate"]]
    problems: List[str] = []
    if not industry_id:
        problems.append("缺少 industry_id")
    elif industry is None:
        problems.append(f"行业 #{industry_id} 不存在")
    if not subjects:
        problems.append("选题为空：请至少填写一行选题")
    if truncated:
        problems.append(f"选题×平台 超过单批上限 {MAX_BATCH}，仅取前 {MAX_BATCH} 条")

    return {
        "industry_id": industry_id,
        "industry_name": industry.name if industry is not None else "",
        "platforms": platforms,
        "subjects": subjects,
        "items": items,
        "will_create": len(will_create),
        "will_skip": len(will_skip),
        "limit": MAX_BATCH,
        "truncated": truncated,
        "skip_duplicates": skip_duplicates,
        "problems": problems,
        "ok": not problems or (len(problems) == 1 and truncated),
    }


def create(db: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """按展开结果创建运行并入队。返回批次号与逐条结果。"""
    plan = expand(db, payload)
    if not plan["ok"]:
        return {"ok": False, "error": "；".join(plan["problems"]), "plan": plan}

    industry_id = plan["industry_id"]
    spec_raw = payload.get("pipeline_spec")
    spec = pipeline_svc.parse_spec(spec_raw) if spec_raw not in (None, "") else pipeline_svc.default_spec()
    spec_json = pipeline_svc.dump_spec(spec)
    priority = int(payload.get("priority") or 5)
    max_attempts = int(payload.get("max_attempts") or task_queue.DEFAULT_MAX_ATTEMPTS)
    batch_id = f"B{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"

    ai_engine = str(payload.get("ai_engine") or "deepseek").strip().lower() or "deepseek"
    mock = 1 if (ai_engine == "mock" or payload.get("mock_doubao")) else 0

    created: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for item in plan["items"]:
        if item["duplicate"]:
            skipped.append({**item, "reason": item["duplicate_reason"]})
            continue
        subject = item["subject"]
        platform = item["platform"]
        run = ProductionTask(
            mode="auto",
            industry_id=industry_id,
            name=f"{subject[:30]}｜{platform}",
            title=subject,
            status="created",
            subject=subject,
            platform=platform,
            account_id=int(payload.get("account_id") or 0),
            persona_id=int(payload.get("persona_id") or 0),
            brand_asset_id=int(payload.get("brand_asset_id") or 0),
            target_persona_id=int(payload.get("target_persona_id") or 0),
            intent_question_id=int(payload.get("intent_question_id") or 0),
            target_persona_ids=_ids_csv(payload.get("target_persona_ids")),
            intent_question_ids=_ids_csv(payload.get("intent_question_ids")),
            keyword_ids=_ids_csv(payload.get("keyword_ids")),
            knowledge_item_ids=_ids_csv(payload.get("knowledge_item_ids")),
            rule_ids=_ids_csv(payload.get("rule_ids")),
            ai_engine=ai_engine,
            mock_doubao=mock,
            llm_config_id=int(payload.get("llm_config_id") or 0),
            auto_publish=1 if payload.get("auto_publish") else 0,
            publish_mode=item["publish_mode"],
            output_format=item["output_format"],
            batch_id=batch_id,
            pipeline_spec=spec_json,
            log=f"[批次] 由批量生产创建（批次 {batch_id}）",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        queued = task_queue.enqueue(
            db, industry_id, run.id, batch_id=batch_id,
            priority=priority, max_attempts=max_attempts,
        )
        created.append({
            "run_id": run.id,
            "job_id": queued["job_id"],
            "subject": subject,
            "platform": platform,
            "name": run.name,
        })

    return {
        "ok": True,
        "batch_id": batch_id,
        "created": created,
        "created_count": len(created),
        "skipped": skipped,
        "skipped_count": len(skipped),
        "spec": spec,
        "plan": plan,
    }


def list_batches(db: Any, industry_id: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
    """按批次聚合出进度概览（最近有活动的批次在前）。

    只查一次库：先把该行业下的运行按 id 升序扫一遍，逐批次记下「最早的一条」
    （取创建时间）与「最晚的 id」（取排序），再按后者倒序取前 N 个批次。
    逐批次再查一次库的写法在批次多时会变成 N+1，这里刻意避开。
    """
    limit = max(1, min(200, int(limit or 20)))
    q = db.query(ProductionTask).filter(
        ProductionTask.is_deleted == 0, ProductionTask.batch_id != ""
    )
    if industry_id:
        q = q.filter(ProductionTask.industry_id == int(industry_id))
    rows = q.order_by(ProductionTask.id.asc()).limit(4000).all()

    agg: Dict[str, Dict[str, Any]] = {}
    for run in rows:
        node = agg.setdefault(run.batch_id, {"first": run, "last_id": run.id})
        node["last_id"] = max(node["last_id"], run.id)
    ordered = sorted(agg.items(), key=lambda kv: kv[1]["last_id"], reverse=True)[:limit]

    out: List[Dict[str, Any]] = []
    for bid, node in ordered:
        progress = task_queue.batch_progress(db, bid)
        run = node["first"]
        out.append({
            "batch_id": bid,
            "industry_id": run.industry_id,
            "total": progress["total"],
            "counts": progress["counts"],
            "finished": progress["finished"],
            "progress": progress["progress"],
            "create_time": run.create_time.strftime("%Y-%m-%d %H:%M:%S") if run.create_time else "",
        })
    return out


def enqueue_batch(db: Any, batch_id: str, priority: int = 5) -> Dict[str, Any]:
    """把一个批次里所有未完成/未排队的运行重新投递。

    用途：批次跑完后发现有几条失败，改好提示词再整批重投；
    已完成的运行会被 ``enqueue`` 的幂等规则挡掉，不会重复执行。
    """
    runs = (
        db.query(ProductionTask)
        .filter(ProductionTask.is_deleted == 0, ProductionTask.batch_id == batch_id)
        .order_by(ProductionTask.id.asc())
        .all()
    )
    if not runs:
        return {"ok": False, "error": f"批次 {batch_id} 下没有运行"}
    queued, existed, done = [], [], []
    for run in runs:
        if run.status in ("await_confirm", "confirmed", "succeeded", "published"):
            done.append(run.id)
            continue
        res = task_queue.enqueue(db, run.industry_id, run.id, batch_id=batch_id, priority=priority)
        (queued if res["created"] else existed).append(res["job_id"])
    return {
        "ok": True,
        "batch_id": batch_id,
        "queued": queued,
        "already_active": existed,
        "skipped_finished": done,
        "msg": f"重新投递 {len(queued)} 条（已在队列 {len(existed)} 条，已完成跳过 {len(done)} 条）",
    }


def batch_summary(db: Any, batch_id: str) -> Dict[str, Any]:
    progress = task_queue.batch_progress(db, batch_id)
    runs = (
        db.query(ProductionTask)
        .filter(ProductionTask.is_deleted == 0, ProductionTask.batch_id == batch_id)
        .order_by(ProductionTask.id.asc())
        .all()
    )
    progress["runs"] = [
        {
            "id": r.id,
            "name": r.name or r.title or "",
            "subject": r.subject or "",
            "platform": r.platform or "",
            "status": r.status or "",
            "geo_score": int(r.geo_score or 0),
            "error": r.error or "",
            "publish_url": r.publish_url or "",
            "update_time": r.update_time.strftime("%Y-%m-%d %H:%M:%S") if r.update_time else "",
        }
        for r in runs
    ]
    progress["create_time"] = (
        runs[0].create_time.strftime("%Y-%m-%d %H:%M:%S") if runs and runs[0].create_time else ""
    )
    return progress


def resolve_batch_industry(db: Any, batch_id: str) -> int:
    row = (
        db.query(ProductionTask.industry_id)
        .filter(ProductionTask.is_deleted == 0, ProductionTask.batch_id == batch_id)
        .first()
    )
    return int(row[0]) if row and row[0] else 0
