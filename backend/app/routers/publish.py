# -*- coding: utf-8 -*-
"""
发布自动化路由

端点：
  GET  /api/platforms                      可用平台 + adapter_type + 是否配置凭证 + 状态
  GET  /api/platform-credential            凭证列表（按行业）
  POST /api/platform-credential            新增凭证
  PUT  /api/platform-credential/{id}       更新凭证
  DELETE /api/platform-credential/{id}     删除凭证（软删）
  GET  /api/publish-job                    发布任务列表（按行业/任务过滤）
  POST /api/publish-job                    创建发布任务（默认进 pending_review 审核闸门）
  POST /api/publish-job/{id}/approve       审核批准
  POST /api/publish-job/{id}/reject        审核打回
  POST /api/publish-job/{id}/run           实际发布（仅 approved 可执行）

审核闸门：当前策略为"每次发布均需人工批准"（run 前状态须为 approved），
避免无脑群发对 GEO 反噬。配置/调度（错峰、重试、告警）留作后续增强。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ProductionTask, PlatformCredential, PublishJob
from ..services.publisher import publisher as _publisher
from ..services.publisher import PlaywrightCookieCapture
from ..services.generation import generate_step_text, assign_default_prompts
from ..routers.production import apply_geo_finalize


router = APIRouter(prefix="/api", tags=["publish"])


# ============================================================
#  Schemas
# ============================================================
class CredentialIn(BaseModel):
    industry_id: int
    platform: str
    cred_type: str = "cookie"        # cookie | password
    cred_json: str = ""              # cookie JSON 数组 或 {username,password}
    note: str = ""


class CredentialUpdate(BaseModel):
    platform: Optional[str] = None
    cred_type: Optional[str] = None
    cred_json: Optional[str] = None
    note: Optional[str] = None
    status: Optional[int] = None


class JobCreate(BaseModel):
    industry_id: int
    task_id: int = 0
    platform: str
    adapter_type: str = "playwright"   # playwright | mock
    title: str = ""
    content: str = ""
    cover: str = ""
    scheduled_at: str = ""             # YYYY-MM-DD HH:MM:SS


class JobReject(BaseModel):
    reason: str = ""


# ============================================================
#  平台目录
# ============================================================
@router.get("/platforms")
def list_platforms(industry_id: int = 0, db: Session = Depends(get_db)):
    platforms = _publisher.list_platforms()
    cred_map = {}
    for c in db.query(PlatformCredential).filter(
        PlatformCredential.industry_id == industry_id,
        PlatformCredential.is_deleted == 0,
        PlatformCredential.status == 1,
    ).all():
        cred_map[c.platform] = {
            "configured": True,
            "needs_relogin": bool(c.needs_relogin),
            "last_error": c.last_error,
        }
    for p in platforms:
        info = cred_map.get(p["platform"])
        p["credential_configured"] = bool(info)
        p["needs_relogin"] = bool(info and info["needs_relogin"]) if info else False
        p["last_error"] = (info or {}).get("last_error", "")
    return {"code": 0, "data": platforms}


# ============================================================
#  凭证 CRUD
# ============================================================
def _cred_to_payload(c: PlatformCredential) -> dict:
    return {
        "id": c.id,
        "industry_id": c.industry_id,
        "platform": c.platform,
        "cred_type": c.cred_type,
        "cred_json": c.cred_json,
        "status": c.status,
        "needs_relogin": c.needs_relogin,
        "note": c.note,
        "last_error": c.last_error,
        "update_time": c.update_time.isoformat() if c.update_time else "",
    }


@router.get("/platform-credential")
def list_credentials(industry_id: int = 0, db: Session = Depends(get_db)):
    items = db.query(PlatformCredential).filter(
        PlatformCredential.industry_id == industry_id,
        PlatformCredential.is_deleted == 0,
    ).order_by(PlatformCredential.id.desc()).all()
    return {"code": 0, "data": [_cred_to_payload(c) for c in items]}


@router.post("/platform-credential")
def create_credential(payload: CredentialIn, db: Session = Depends(get_db)):
    if not payload.platform:
        raise HTTPException(400, "platform 不能为空")
    c = PlatformCredential(
        industry_id=payload.industry_id,
        platform=payload.platform,
        cred_type=payload.cred_type,
        cred_json=payload.cred_json,
        note=payload.note,
        status=1,
        needs_relogin=0,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"code": 0, "data": _cred_to_payload(c)}


@router.put("/platform-credential/{cid}")
def update_credential(cid: int, payload: CredentialUpdate, db: Session = Depends(get_db)):
    c = db.query(PlatformCredential).filter(
        PlatformCredential.id == cid, PlatformCredential.is_deleted == 0
    ).first()
    if not c:
        raise HTTPException(404, "凭证不存在")
    for f in ("platform", "cred_type", "cred_json", "note", "status"):
        v = getattr(payload, f, None)
        if v is not None:
            setattr(c, f, v)
    c.needs_relogin = 0  # 重新录入视为续期
    c.last_error = ""
    db.commit()
    return {"code": 0, "data": _cred_to_payload(c)}


@router.delete("/platform-credential/{cid}")
def delete_credential(cid: int, db: Session = Depends(get_db)):
    c = db.query(PlatformCredential).filter(
        PlatformCredential.id == cid, PlatformCredential.is_deleted == 0
    ).first()
    if not c:
        raise HTTPException(404, "凭证不存在")
    c.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


# ============================================================
#  交互式 Cookie 捕获（浏览器登录获取 Cookie）
#  流程：capture-start 弹真实浏览器 → 用户登录 → 自动/手动捕获 → capture-finish 存回凭证。
# ============================================================
_capture_sessions: Dict[str, "PlaywrightCookieCapture"] = {}
_capture_lock = threading.Lock()


class CaptureStart(BaseModel):
    industry_id: int
    platform: str
    credential_id: Optional[int] = None   # 不传则捕获后新建凭证


@router.post("/platform-credential/capture-start")
def capture_start(payload: CaptureStart, db: Session = Depends(get_db)):
    valid = {p["platform"] for p in _publisher.list_platforms()}
    if payload.platform not in valid:
        raise HTTPException(400, f"未知平台 {payload.platform}")
    cap = PlaywrightCookieCapture(payload.platform, headless=False, auto_detect=True)
    cap.intent = {
        "industry_id": payload.industry_id,
        "platform": payload.platform,
        "credential_id": payload.credential_id,
    }
    cap.start()
    with _capture_lock:
        _capture_sessions[cap.session_id] = cap
    return {"code": 0, "data": {"session_id": cap.session_id, "status": cap.status}}


@router.get("/platform-credential/capture-status")
def capture_status(session_id: str):
    cap = _capture_sessions.get(session_id)
    if not cap:
        raise HTTPException(404, "捕获会话不存在或已结束")
    return {
        "code": 0,
        "data": {
            "session_id": session_id,
            "status": cap.status,
            "error": cap.error,
            "cookie_count": len(cap.cookies),
        },
    }


@router.post("/platform-credential/capture-finish")
def capture_finish(session_id: str, db: Session = Depends(get_db)):
    cap = _capture_sessions.get(session_id)
    if not cap:
        raise HTTPException(404, "捕获会话不存在或已结束")
    status, storage_state, error = cap.finish(timeout=30)
    with _capture_lock:
        _capture_sessions.pop(session_id, None)
    cookies = (storage_state or {}).get("cookies", [])
    if status != "captured" or not cookies:
        return {"code": 0, "data": {"ok": False, "status": status, "error": error}}
    cred_json = json.dumps(storage_state, ensure_ascii=False)
    intent = cap.intent
    cred = None
    if intent.get("credential_id"):
        cred = db.query(PlatformCredential).filter(
            PlatformCredential.id == intent["credential_id"],
            PlatformCredential.is_deleted == 0,
        ).first()
    if not cred:
        cred = PlatformCredential(
            industry_id=intent["industry_id"],
            platform=intent["platform"],
            cred_type="cookie",
            status=1,
        )
        db.add(cred)
    cred.cred_json = cred_json
    cred.cred_type = "cookie"
    cred.needs_relogin = 0
    cred.last_error = ""
    cred.status = 1
    db.commit()
    db.refresh(cred)
    return {
        "code": 0,
        "data": {
            "ok": True,
            "credential_id": cred.id,
            "platform": cred.platform,
            "cookie_count": len(cookies),
        },
    }


class CapturePaste(BaseModel):
    industry_id: int
    platform: str
    credential_id: Optional[int] = None
    cookies: Any  # 浏览器插件（Cookie-Editor 等）导出的 cookie 数组 / 或 JSON 字符串


@router.post("/platform-credential/capture-paste")
def capture_paste(payload: CapturePaste, db: Session = Depends(get_db)):
    """手动粘贴兜底：用户从已登录浏览器用 Cookie-Editor 等插件导出 cookie，
    粘贴进来即可，无需弹窗登录。归一化为 storage_state 后写入凭证。最可靠的录入方式。"""
    valid = {p["platform"] for p in _publisher.list_platforms()}
    if payload.platform not in valid:
        raise HTTPException(400, f"未知平台 {payload.platform}")
    raw = payload.cookies
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raise HTTPException(400, "cookie 文本不是合法 JSON，请用 Cookie-Editor 的「导出」结果直接粘贴")
    if not isinstance(raw, list) or not raw:
        raise HTTPException(400, "cookie 应为非空数组，请用 Cookie-Editor 的「导出」结果直接粘贴")
    from ..services.publisher import _normalize_pasted_cookies
    cookies = _normalize_pasted_cookies(raw)
    if not cookies:
        raise HTTPException(400, "未解析到任何有效 cookie（需含 name 与 value 字段）")
    storage_state = {"cookies": cookies, "origins": []}
    cred_json = json.dumps(storage_state, ensure_ascii=False)
    cred = None
    if payload.credential_id:
        cred = db.query(PlatformCredential).filter(
            PlatformCredential.id == payload.credential_id,
            PlatformCredential.is_deleted == 0,
        ).first()
    if not cred:
        cred = PlatformCredential(
            industry_id=payload.industry_id,
            platform=payload.platform,
            cred_type="cookie",
            status=1,
        )
        db.add(cred)
    cred.cred_json = cred_json
    cred.cred_type = "cookie"
    cred.needs_relogin = 0
    cred.last_error = ""
    cred.status = 1
    db.commit()
    db.refresh(cred)
    return {
        "code": 0,
        "data": {
            "ok": True,
            "credential_id": cred.id,
            "platform": cred.platform,
            "cookie_count": len(cookies),
        },
    }


@router.post("/platform-credential/capture-cancel")
def capture_cancel(session_id: str):
    cap = _capture_sessions.get(session_id)
    if cap:
        cap.cancel()
        with _capture_lock:
            _capture_sessions.pop(session_id, None)
    return {"code": 0, "msg": "已取消"}


# ============================================================
#  发布任务
# ============================================================
def _job_to_payload(j: PublishJob, task_title: str = "") -> dict:
    return {
        "id": j.id,
        "industry_id": j.industry_id,
        "task_id": j.task_id,
        "task_title": task_title,
        "title": j.title,
        "content": j.content,
        "cover": j.cover,
        "platform": j.platform,
        "adapter_type": j.adapter_type,
        "status": j.status,
        "reject_reason": j.reject_reason,
        "scheduled_at": j.scheduled_at,
        "result_url": j.result_url,
        "error": j.error,
        "log": j.log,
        "finished_at": j.finished_at.isoformat() if j.finished_at else "",
        "create_time": j.create_time.isoformat() if j.create_time else "",
    }


@router.get("/publish-job")
def list_jobs(industry_id: int = 0, task_id: int = 0, db: Session = Depends(get_db)):
    q = db.query(PublishJob).filter(
        PublishJob.industry_id == industry_id, PublishJob.is_deleted == 0
    )
    if task_id:
        q = q.filter(PublishJob.task_id == task_id)
    jobs = q.order_by(PublishJob.id.desc()).all()
    task_titles = {}
    for t in db.query(ProductionTask).filter(ProductionTask.id.in_([j.task_id for j in jobs if j.task_id])).all():
        task_titles[t.id] = t.title
    return {"code": 0, "data": [_job_to_payload(j, task_titles.get(j.task_id, "")) for j in jobs]}


@router.post("/publish-job")
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    title, content = payload.title, payload.content
    # 未显式给标题/正文时，从生产任务 final_title/final_content 取（即第9步 GEO 终稿）
    if (not title or not content) and payload.task_id:
        t = db.query(ProductionTask).filter(ProductionTask.id == payload.task_id).first()
        if t:
            title = title or t.final_title or t.title
            content = content or t.final_content
    if not title or not content:
        raise HTTPException(400, "缺少标题或正文（请先在对应生产任务完成第9步 GEO 终稿）")
    if payload.adapter_type not in ("playwright", "mock"):
        raise HTTPException(400, "adapter_type 仅支持 playwright / mock")
    # 审核闸门：新任务默认进 pending_review，需人工批准后再 run
    job = PublishJob(
        industry_id=payload.industry_id,
        task_id=payload.task_id,
        title=title,
        content=content,
        cover=payload.cover,
        platform=payload.platform,
        adapter_type=payload.adapter_type,
        status="pending_review",
        scheduled_at=payload.scheduled_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    t = db.query(ProductionTask).filter(ProductionTask.id == payload.task_id).first()
    return {"code": 0, "data": _job_to_payload(job, t.title if t else "")}


@router.post("/publish-job/{jid}/approve")
def approve_job(jid: int, db: Session = Depends(get_db)):
    j = db.query(PublishJob).filter(PublishJob.id == jid, PublishJob.is_deleted == 0).first()
    if not j:
        raise HTTPException(404, "发布任务不存在")
    if j.status in ("published", "publishing"):
        raise HTTPException(400, f"当前状态 {j.status}，不可重复批准")
    j.status = "approved"
    db.commit()
    return {"code": 0, "data": _job_to_payload(j)}


@router.post("/publish-job/{jid}/reject")
def reject_job(jid: int, payload: JobReject, db: Session = Depends(get_db)):
    j = db.query(PublishJob).filter(PublishJob.id == jid, PublishJob.is_deleted == 0).first()
    if not j:
        raise HTTPException(404, "发布任务不存在")
    j.status = "rejected"
    j.reject_reason = payload.reason
    db.commit()
    return {"code": 0, "data": _job_to_payload(j)}


def _run_publish(db: Session, j: PublishJob) -> dict:
    """实际执行发布（被 run 端点与一键发布编排复用）。

    前置：调用方需保证 j.status == "approved"（审核闸门）。
    返回统一结果 dict：{ok, status, url, error, log, job}
    """
    # 取凭证（仅 playwright 需要）
    cred_json = ""
    cred = None
    if j.adapter_type == "playwright":
        cred = db.query(PlatformCredential).filter(
            PlatformCredential.industry_id == j.industry_id,
            PlatformCredential.platform == j.platform,
            PlatformCredential.status == 1,
            PlatformCredential.is_deleted == 0,
        ).first()
        if not cred:
            return {
                "ok": False, "status": "failed",
                "url": "", "error": f"平台 {j.platform} 未配置凭证（cookie）。请先在发布中心上传登录态 cookie。",
                "log": "", "job": _job_to_payload(j),
            }
        cred_json = cred.cred_json

    j.status = "publishing"
    db.commit()

    result = _publisher.publish(
        platform=j.platform,
        adapter_type=j.adapter_type,
        title=j.title,
        content=j.content,
        cover=j.cover or None,
        cred_json=cred_json,
    )

    j.log = result.log
    if result.status == "published":
        j.status = "published"
        j.result_url = result.url
        j.finished_at = datetime.now()
        j.error = ""
        # 回写生产任务
        t = db.query(ProductionTask).filter(ProductionTask.id == j.task_id).first()
        if t:
            t.publish_url = result.url
            t.published_status = "published"
            t.last_publish_job_id = j.id
        # 凭证续期成功
        if cred:
            cred.needs_relogin = 0
            cred.last_error = ""
    else:
        j.status = "failed"
        j.error = result.error
        j.finished_at = datetime.now()
        if cred:
            cred.last_error = result.error
            if result.needs_relogin:
                cred.needs_relogin = 1
    db.commit()

    return {
        "ok": result.status == "published",
        "status": j.status,
        "url": j.result_url,
        "error": j.error,
        "log": j.log,
        "job": _job_to_payload(j),
    }


@router.post("/publish-job/{jid}/run")
def run_job(jid: int, db: Session = Depends(get_db)):
    j = db.query(PublishJob).filter(PublishJob.id == jid, PublishJob.is_deleted == 0).first()
    if not j:
        raise HTTPException(404, "发布任务不存在")
    # 审核闸门：必须 approved 才能执行（每次发布均人工确认，防无脑群发）
    if j.status != "approved":
        return {
            "code": 0,
            "data": {
                "ok": False,
                "status": j.status,
                "error": f"发布任务状态为「{j.status}」，需先审核批准（approved）才能执行。",
            },
        }
    data = _run_publish(db, j)
    return {"code": 0, "data": data}


# ============================================================
#  一键生成并发布编排
# ============================================================
class OneClickIn(BaseModel):
    industry_id: int
    platform: str                       # 目标平台 code（sohu/zhihu/wangyi/toutiao/...）
    task_id: int = 0                    # 已有生产任务（复用其成品/配置）；为 0 时按 topic 新建
    topic: str = ""                     # 新主题（task_id=0 时使用）
    keyword_ids: List[int] = []         # 关键词（仅新建任务生效）
    knowledge_item_ids: List[int] = []
    rule_ids: List[int] = []
    config_id: Optional[int] = None     # 指定 LLM 配置；缺省按行业默认/首个启用
    adapter_type: str = "playwright"    # playwright | mock
    auto_publish: bool = False          # True 时生成后自动批准并发布（绕过人工审核闸门，需自担群发风险）
    cover: str = ""


@router.post("/publish/one-click")
def one_click_publish(payload: OneClickIn, db: Session = Depends(get_db)):
    """一键生成并发布：用 DeepSeek(行业 LLM) + 提示词库 + 软文生产步骤，
    直接产出完整最终文章并（可选）推送到平台。

    流程：解析/新建生产任务 → 按行业补齐默认提示词 → 依次跑
    outline/draft/rewrite/geo（每步调用 LLM）→ 第9步 GEO 终检写回
    final_title/final_content → 创建发布任务（默认进审核闸门 pending_review）；
    若 auto_publish=True 且凭证就绪，则自动批准并执行发布。

    未配置 LLM 时返回 need_config=True（连同渲染提示词），绝不阻断。
    """
    industry_id = payload.industry_id
    platform = (payload.platform or "").strip()
    if not platform:
        raise HTTPException(400, "platform 不能为空")

    # 1) 解析 / 新建生产任务
    task = None
    if payload.task_id:
        task = db.query(ProductionTask).filter(
            ProductionTask.id == payload.task_id, ProductionTask.is_deleted == 0
        ).first()
        if not task:
            raise HTTPException(404, f"生产任务 {payload.task_id} 不存在")

    if task is None:
        title = (payload.topic or "").strip() or f"一键发布-{platform}-{datetime.now():%m%d%H%M}"
        task = ProductionTask(
            industry_id=industry_id,
            title=title,
            keyword_ids=",".join(str(i) for i in payload.keyword_ids),
            knowledge_item_ids=",".join(str(i) for i in payload.knowledge_item_ids),
            rule_ids=",".join(str(i) for i in payload.rule_ids),
            status="draft",
            current_step=1,
            # platform_id 不强制绑定（按平台 code 走发布，渲染上下文按任务既有平台特性）
        )
        db.add(task)
        db.commit()
        db.refresh(task)

    # 2) 补齐默认提示词（按行业 + 类目）
    assign_default_prompts(db, task)

    # 3) 依次跑 4 个生产步骤（DeepSeek + 提示词 + 生产步骤）
    trace: dict = {}
    steps = [
        ("outline", "outline_content", "outline_prompt_id"),
        ("draft", "draft_content", "draft_prompt_id"),
        ("rewrite", "rewrite_content", "rewrite_prompt_id"),
        ("geo", None, "safety_prompt_id"),
    ]
    for step, content_field, prompt_field in steps:
        r = generate_step_text(db, task, step, config_id=payload.config_id)
        if r.get("need_config"):
            return {
                "code": 0,
                "data": {
                    "ok": False, "need_config": True, "failed_step": step,
                    "task_id": task.id, "rendered": r.get("rendered", ""),
                    "error": r.get("error", "未配置 LLM"),
                },
            }
        if not r.get("ok"):
            return {
                "code": 0,
                "data": {
                    "ok": False, "need_config": False, "failed_step": step,
                    "task_id": task.id,
                    "error": r.get("error", "生成失败"),
                },
            }
        if step == "geo":
            geo = apply_geo_finalize(db, task, r["text"])
            trace[step] = {
                "ok": True, "prompt_name": r["prompt_name"],
                "geo_score": geo["geo_score"], "parsed_ok": geo["parsed_ok"],
            }
        else:
            setattr(task, content_field, r["text"])
            setattr(task, prompt_field, r["prompt_id"])
            db.commit()
            trace[step] = {"ok": True, "prompt_name": r["prompt_name"], "len": len(r["text"])}

    # 4) 创建发布任务（默认进审核闸门）
    adapter = payload.adapter_type if payload.adapter_type in ("playwright", "mock") else "playwright"
    job = PublishJob(
        industry_id=industry_id,
        task_id=task.id,
        title=task.final_title or task.title,
        content=task.final_content or "",
        cover=payload.cover or None,
        platform=platform,
        adapter_type=adapter,
        status="pending_review",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # 5) 可选：自动批准并发布（绕过人工审核闸门）
    auto_result = None
    if payload.auto_publish:
        job.status = "approved"
        db.commit()
        auto_result = _run_publish(db, job)

    return {
        "code": 0,
        "data": {
            "ok": True,
            "need_config": False,
            "task_id": task.id,
            "job_id": job.id,
            "final_title": task.final_title,
            "final_content_len": len(task.final_content or ""),
            "trace": trace,
            "auto_published": bool(payload.auto_publish),
            "auto_result": auto_result,
            "job": _job_to_payload(job),
        },
        "msg": "已生成最终文章" + ("并发布" if payload.auto_publish else "，请在任务列表批准并执行发布"),
    }
