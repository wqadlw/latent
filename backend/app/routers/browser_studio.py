# -*- coding: utf-8 -*-
"""
浏览器工作室路由（BrowserStudio）

端点：
  POST   /api/browser-studio                  创建运行（选定全量上下文）
  GET    /api/browser-studio                  运行列表（按行业）
  GET    /api/browser-studio/{id}             运行详情（含 5 步状态）
  POST   /api/browser-studio/{id}/start       启动流水线
  POST   /api/browser-studio/{id}/retry       重试（重跑豆包阶段 + 后续步骤）
  POST   /api/browser-studio/{id}/retry-publish  仅重试搜狐号发布
  DELETE /api/browser-studio/{id}             删除（软删）
  POST   /api/browser-studio/doubao-credential     上传豆包登录态 cookie（platform='doubao'）
  GET    /api/browser-studio/doubao-credential     列出豆包凭证（按行业）
  POST   /api/browser-studio/rewrite               文章改写模式（P2-3）：贴被判软文→按目标模式改写

设计：豆包作为创作引擎经浏览器自动化驱动；搜狐号复用既有 PlaywrightAdapter 与审核闸门。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BrowserStudioRun, BrowserStudioStep, PlatformCredential, ProductionTask


def _parse_json(text: str) -> Any:
    """把存为文本的 JSON 字段（如 compliance_result）安全解析为对象；失败返回 {}。"""
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {}
from ..services.publisher import _normalize_pasted_cookies
from ..services.doubao_studio import (
    start_run, retry_run, retry_publish, confirm_run, publish_run,
    format_briefing, build_studio_context, get_auto_run,
    SYSTEM_PROMPT, DEEPSEEK_MASTER_PROMPT, resolve_engine_kind, STAGE_PROMPTS,
    PLANNER_SYSTEM, get_studio_prompts, resolve_run_publish_mode, resolve_run_output_format, PLATFORM_PUBLISH_MODE,
)


router = APIRouter(prefix="/api/browser-studio", tags=["browser-studio"])


# ============================================================
#  Schemas
# ============================================================
class RunCreate(BaseModel):
    industry_id: int
    name: str = ""
    subject: str = ""                 # 目标需求
    platform: str = "sohu"            # 发布平台 code
    account_id: int = 0
    persona_id: int = 0
    brand_asset_id: int = 0
    target_persona_id: int = 0
    intent_question_id: int = 0
    target_persona_ids: List[int] = []   # 多选目标客户画像（逗号存库）
    intent_question_ids: List[int] = []  # 多选意图问题（逗号存库）
    keyword_ids: List[int] = []
    knowledge_item_ids: List[int] = []
    rule_ids: List[int] = []
    doubao_credential_id: int = 0     # 豆包 cookie 凭证
    sohu_credential_id: int = 0       # 搜狐号 cookie 凭证（占位，发布时取行业生效的 sohu 凭证）
    ai_engine: str = "deepseek"       # 创作引擎：deepseek(LLM API) / doubao(浏览器自动化) / mock(模拟演示)
    llm_config_id: int = 0            # 指定 DeepSeek 等 LLM 配置（0=按行业默认自动解析）
    mock_doubao: bool = False         # 兼容旧字段：true 等价于 ai_engine='mock'
    auto_publish: bool = False        # 生成后自动批准并发布
    publish_mode: str = ""            # 发布模式：geo=强品牌/GEO；platform=平台合规；green=绿色吸粉（空=按平台自动推导）
    output_format: str = ""           # 产出形态：markdown=常规文章；mdx=官网/Astro 站（空=按平台自动推导）


class DoubaoCredPaste(BaseModel):
    industry_id: int
    credential_id: Optional[int] = None
    cookies: Any                      # Cookie-Editor 导出数组 / JSON 字符串


# ============================================================
#  序列化
# ============================================================
def _run_to_payload(run: BrowserStudioRun) -> dict:
    return {
        "id": run.id,
        "industry_id": run.industry_id,
        "name": run.name,
        "status": run.status,
        "subject": run.subject,
        "platform": run.platform,
        "account_id": run.account_id,
        "persona_id": run.persona_id,
        "brand_asset_id": run.brand_asset_id,
        "target_persona_id": run.target_persona_id,
        "intent_question_id": run.intent_question_id,
        "target_persona_ids": [int(x) for x in (getattr(run, "target_persona_ids", "") or "").split(",") if x.strip()],
        "intent_question_ids": [int(x) for x in (getattr(run, "intent_question_ids", "") or "").split(",") if x.strip()],
        "keyword_ids": [int(x) for x in (run.keyword_ids or "").split(",") if x.strip()],
        "knowledge_item_ids": [int(x) for x in (run.knowledge_item_ids or "").split(",") if x.strip()],
        "rule_ids": [int(x) for x in (run.rule_ids or "").split(",") if x.strip()],
        "doubao_credential_id": run.doubao_credential_id,
        "sohu_credential_id": run.sohu_credential_id,
        "ai_engine": run.ai_engine or ("mock" if run.mock_doubao else "deepseek"),
        "llm_config_id": run.llm_config_id,
        "mock_doubao": bool(run.mock_doubao),
        "auto_publish": bool(run.auto_publish),
        "publish_mode": run.publish_mode or "geo",
        "output_format": getattr(run, "output_format", "") or "markdown",
        # —— 9 步中间产物（每轮 AI 返回原文，前端逐段回看）——
        "outline_content": run.outline_content or "",
        "draft_content": run.draft_content or "",
        "rewrite_content": run.rewrite_content or "",
        "geo_content": run.geo_content or "",
        # —— 评审与确认 ——
        "review_result": _parse_json(run.review_result),
        "revise_rounds": _parse_json(run.revise_rounds),
        "geo_score": run.geo_score or 0,
        "confirmed": bool(run.confirmed),
        "compliance_result": _parse_json(run.compliance_result),
        # —— 双智能体专属产物 ——
        "clarified_brief": run.clarified_brief or "",
        "editor_review": run.editor_review or "",
        "final_title": run.final_title,
        "final_content": run.final_content,
        "mdx_filename": getattr(run, "mdx_filename", "") or "",
        "mdx_images": _parse_json(getattr(run, "mdx_images", "") or ""),
        "content_asset_id": run.content_asset_id,
        "sohu_job_id": run.sohu_job_id,
        "error": run.error,
        "log": run.log,
        "create_time": run.create_time.isoformat() if run.create_time else "",
        "update_time": run.update_time.isoformat() if run.update_time else "",
    }


def _step_to_payload(s: BrowserStudioStep) -> dict:
    return {
        "id": s.id,
        "run_id": s.run_id,
        "step_no": s.step_no,
        "step_key": s.step_key,
        "agent": s.agent or "",
        "title": s.title,
        "status": s.status,
        "attempts": s.attempts,
        "last_error": s.last_error,
        "started_at": s.started_at.isoformat() if s.started_at else "",
        "finished_at": s.finished_at.isoformat() if s.finished_at else "",
        "result_json": s.result_json,
        "log": s.log,
        # —— 步骤透明化（步骤日志面板用）——
        "request_payload": getattr(s, "request_payload", "") or "",
        "expected_fields": _parse_json(getattr(s, "expected_fields", "") or ""),
        "response_latency_ms": getattr(s, "response_latency_ms", 0) or 0,
        "api_role": getattr(s, "api_role", "") or "",
        "api_config_id": getattr(s, "api_config_id", 0) or 0,
        "api_model": getattr(s, "api_model", "") or "",
        "extracted_result": getattr(s, "extracted_result", "") or "",
        "next_action": getattr(s, "next_action", "") or "",
    }


# ============================================================
#  运行 CRUD + 编排
# ============================================================
@router.post("")
def create_run(payload: RunCreate, db: Session = Depends(get_db)):
    if not payload.industry_id:
        raise HTTPException(400, "industry_id 不能为空")
    name = payload.name or f"浏览器工作室-{payload.platform}-{__import__('datetime').datetime.now():%m%d%H%M}"
    run = ProductionTask(
        mode="auto", legacy_run_id=0, legacy_status="",  # P2 并表：自动流统一写 production_task
        industry_id=payload.industry_id,
        name=name,
        status="created",
        subject=payload.subject,
        platform=payload.platform or "sohu",
        account_id=payload.account_id,
        persona_id=payload.persona_id,
        brand_asset_id=payload.brand_asset_id,
        target_persona_id=payload.target_persona_id,
        intent_question_id=payload.intent_question_id,
        target_persona_ids=",".join(str(i) for i in payload.target_persona_ids),
        intent_question_ids=",".join(str(i) for i in payload.intent_question_ids),
        keyword_ids=",".join(str(i) for i in payload.keyword_ids),
        knowledge_item_ids=",".join(str(i) for i in payload.knowledge_item_ids),
        rule_ids=",".join(str(i) for i in payload.rule_ids),
        doubao_credential_id=payload.doubao_credential_id,
        sohu_credential_id=payload.sohu_credential_id,
        ai_engine=(payload.ai_engine or "deepseek").strip().lower()
        if payload.ai_engine else ("mock" if payload.mock_doubao else "deepseek"),
        mock_doubao=1 if (payload.mock_doubao or (payload.ai_engine or "").lower() == "mock") else 0,
        llm_config_id=payload.llm_config_id or 0,
        auto_publish=1 if payload.auto_publish else 0,
        # 发布模式：显式指定优先；否则按平台推导（内容平台→platform，其它→geo）
        publish_mode=(payload.publish_mode if payload.publish_mode in ("geo", "platform", "green")
                      else PLATFORM_PUBLISH_MODE.get(payload.platform or "sohu", "geo")),
        # 产出形态：显式指定优先；否则官网/自建站→mdx，其它→markdown
        output_format=(payload.output_format if payload.output_format in ("markdown", "mdx")
                       else ("mdx" if payload.platform in ("official", "selfsite") else "markdown")),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"code": 0, "data": _run_to_payload(run)}


def _list_legacy_runs(db: Session, industry_id: int = 0):
    """读取 P2 并表 cutover 前尚未迁移的 browser_studio_run 历史运行。

    cutover 后 browser_studio_run 改名归档为 _archive_browser_studio_run，查询会抛错，
    此时安全返回空（历史运行已并入 production_task(mode='auto')，不会丢失也不重复）。
    """
    try:
        q = db.query(BrowserStudioRun).filter(BrowserStudioRun.is_deleted == 0)
        if industry_id:
            q = q.filter(BrowserStudioRun.industry_id == industry_id)
        return q.order_by(BrowserStudioRun.id.desc()).all()
    except Exception:
        return []


@router.get("")
def list_runs(industry_id: int = 0, db: Session = Depends(get_db)):
    # 新运行 + P2 并表后迁移的历史运行（统一任务表 production_task.mode='auto'）
    q = db.query(ProductionTask).filter(ProductionTask.mode == "auto", ProductionTask.is_deleted == 0)
    if industry_id:
        q = q.filter(ProductionTask.industry_id == industry_id)
    runs = q.order_by(ProductionTask.id.desc()).all()
    # 并表 cutover 前尚未迁移的历史运行（browser_studio_run 表仍存在时）
    runs.extend(_list_legacy_runs(db, industry_id))
    # 按 id 倒序整体排序（production_task 新 id 与 legacy 旧 id 跨表混合展示）
    runs.sort(key=lambda r: r.id, reverse=True)
    return {"code": 0, "data": [_run_to_payload(r) for r in runs]}


# ============================================================
#  豆包凭证（platform='doubao'，复用 PlatformCredential）
#  注意：必须在 /{run_id} 之前注册，否则会被 int 路径参数拦截（422）。
# ============================================================
@router.get("/doubao-credential")
def list_doubao_credential(industry_id: int = 0, db: Session = Depends(get_db)):
    items = db.query(PlatformCredential).filter(
        PlatformCredential.industry_id == industry_id,
        PlatformCredential.platform == "doubao",
        PlatformCredential.is_deleted == 0,
    ).order_by(PlatformCredential.id.desc()).all()
    return {"code": 0, "data": [
        {
            "id": c.id, "platform": c.platform, "cred_type": c.cred_type,
            "status": c.status, "needs_relogin": c.needs_relogin,
            "note": c.note, "last_error": c.last_error,
            "update_time": c.update_time.isoformat() if c.update_time else "",
        } for c in items
    ]}


@router.post("/doubao-credential")
def paste_doubao_credential(payload: DoubaoCredPaste, db: Session = Depends(get_db)):
    raw = payload.cookies
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raise HTTPException(400, "cookie 文本不是合法 JSON，请用 Cookie-Editor 的「导出」结果直接粘贴")
    if not isinstance(raw, list) or not raw:
        raise HTTPException(400, "cookie 应为非空数组，请用 Cookie-Editor 的「导出」结果直接粘贴")
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
        cred = PlatformCredential(industry_id=payload.industry_id, platform="doubao", cred_type="cookie", status=1)
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
        "data": {"ok": True, "credential_id": cred.id, "platform": "doubao", "cookie_count": len(cookies)},
    }


@router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    steps = db.query(BrowserStudioStep).filter(
        BrowserStudioStep.run_id == run_id
    ).order_by(BrowserStudioStep.step_no).all()
    data = _run_to_payload(run)
    data["steps"] = [_step_to_payload(s) for s in steps]
    # 派发给 AI 的完整背景（8 大类整合）与总指令，便于前端展示/回看
    kind = resolve_engine_kind(run)
    ctx = None
    try:
        ctx = build_studio_context(db, run)
        data["briefing"] = format_briefing(ctx, run)
    except Exception:
        data["briefing"] = ""
    # 双模式：按发布模式解析对应提示词（geo=强品牌/GEO；platform=平台合规；green=绿色吸粉）
    _mode = resolve_run_publish_mode(run, db)
    _out = resolve_run_output_format(run, db)
    _sp = get_studio_prompts(_mode)
    data["publish_mode"] = _mode
    data["output_format"] = _out
    data["official_site_url"] = ctx.get("official_site_url", "") if ctx else ""
    data["publish_prompt"] = ctx.get("publish_prompt", "") if ctx else ""
    data["system_prompt"] = _sp["SYSTEM_PROMPT"] if kind in ("doubao", "mock") else _sp["DEEPSEEK_MASTER_PROMPT"]
    # 主编（规划师）系统提示词：面向用户展示「双智能体」中规划角色的定位
    data["planner_system"] = _sp["PLANNER_SYSTEM"]
    # 派发给 AI 的各阶段指令（选题大纲/初稿/去AI味/GEO强化/整改），便于前端展示「总指令」
    data["stage_prompts"] = _sp["STAGE_PROMPTS"]
    return {"code": 0, "data": data}


@router.get("/{run_id}/step-logs")
def step_logs(run_id: int, db: Session = Depends(get_db)):
    """步骤透明日志：每行含 序号 | 阶段 | 发送内容摘要 | 等待API响应字段 | 响应耗时 | 提取结果 | 下一步动作，
    并附完整发送内容（request_payload）供复制复现。"""
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    steps = db.query(BrowserStudioStep).filter(
        BrowserStudioStep.run_id == run_id
    ).order_by(BrowserStudioStep.step_no).all()
    rows = []
    for idx, s in enumerate(steps, start=1):
        payload = getattr(s, "request_payload", "") or ""
        rows.append({
            "index": idx,
            "step_no": s.step_no,
            "step_key": s.step_key,
            "title": s.title,
            "agent": s.agent or "",
            "status": s.status,
            "send_summary": (payload[:160] + ("…" if len(payload) > 160 else "")) if payload else "（无 API 调用 / 系统步骤）",
            "expected_fields": _parse_json(getattr(s, "expected_fields", "") or ""),
            "response_latency_ms": getattr(s, "response_latency_ms", 0) or 0,
            "api_role": getattr(s, "api_role", "") or "",
            "api_model": getattr(s, "api_model", "") or "",
            "extracted_result": getattr(s, "extracted_result", "") or "",
            "next_action": getattr(s, "next_action", "") or "",
            "request_payload": payload,
            "started_at": s.started_at.isoformat() if s.started_at else "",
            "finished_at": s.finished_at.isoformat() if s.finished_at else "",
        })
    return {"code": 0, "data": {"run_id": run_id, "status": run.status, "rows": rows}}


def _extract_step_message(s) -> str:
    """从一步的 result_json / request_payload / extracted_result 稳健提取可读发言文本，用于对话回放。"""
    raw = getattr(s, "result_json", "") or ""
    if raw:
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(obj, dict):
                # 已知语义字段优先（主编指令/评语、写手正文）
                for key in ("editor_review", "directives", "planner_directives", "clarified",
                            "outline", "draft", "geo", "content", "text", "after", "brief"):
                    if obj.get(key):
                        val = obj[key]
                        if isinstance(val, str):
                            return val.strip()[:3000]
                        if isinstance(val, (dict, list)):
                            return json.dumps(val, ensure_ascii=False)[:3000]
                parts = [str(v).strip() for v in obj.values() if isinstance(v, str) and v.strip()]
                if parts:
                    return "\n".join(parts)[:3000]
        except Exception:
            if isinstance(raw, str) and raw.strip():
                return raw.strip()[:3000]
    payload = getattr(s, "request_payload", "") or ""
    if payload and payload.strip():
        return payload.strip()[-1500:]
    return (getattr(s, "extracted_result", "") or "").strip()[:1500]


@router.get("/{run_id}/conversation")
def run_conversation(run_id: int, db: Session = Depends(get_db)):
    """创作过程可视化（P2-2）：结构化展示「主编指令↔写手改写」多轮对话，便于调优提示词。

    聚合 run.revise_rounds（主编↔写手整改多轮对话，每轮含 主编指令/写手改写前后/主编评语/GEO评分）
    与各步 agent（planner=主编 / writer=写手）发言，前端以对话气泡回放，可复制复现。
    """
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    if getattr(run, "is_deleted", 0):
        raise HTTPException(404, "运行已删除")
    revise_rounds = _parse_json(getattr(run, "revise_rounds", "") or "[]") or []
    if not isinstance(revise_rounds, list):
        revise_rounds = []
    steps = db.query(BrowserStudioStep).filter(
        BrowserStudioStep.run_id == run_id
    ).order_by(BrowserStudioStep.step_no).all()
    planner_messages = []
    writer_messages = []
    # run 级主编内容（真实数据常把正文存这里，step.result_json 多仅留元数据）
    cb = (getattr(run, "clarified_brief", "") or "").strip()
    if cb:
        planner_messages.append({"index": 0, "step_no": 2, "step_key": "clarified_brief",
                                  "title": "主编·创作简报", "agent": "planner", "status": "done",
                                  "text": cb[:3000], "latency_ms": 0, "api_role": ""})
    er = (getattr(run, "editor_review", "") or "").strip()
    if er:
        planner_messages.append({"index": 0, "step_no": 7, "step_key": "editor_review",
                                  "title": "主编·评审评语", "agent": "planner", "status": "done",
                                  "text": er[:3000], "latency_ms": 0, "api_role": ""})
    # run 级写手终稿
    fc = (getattr(run, "final_content", "") or "").strip()
    if fc:
        writer_messages.append({"index": 0, "step_no": 9, "step_key": "final",
                                 "title": "写手·终稿", "agent": "writer", "status": "done",
                                 "text": fc[:3000], "latency_ms": 0, "api_role": ""})
    for idx, s in enumerate(steps, start=1):
        agent = (getattr(s, "agent", "") or "").lower()
        # dual 步骤（主编指令↔写手改写）正文已在 revise_rounds 卡片结构化展示，避免气泡空白/重复
        if agent == "dual":
            continue
        entry = {
            "index": idx,
            "step_no": s.step_no,
            "step_key": s.step_key,
            "title": s.title,
            "agent": s.agent,
            "status": s.status,
            "text": _extract_step_message(s),
            "latency_ms": getattr(s, "response_latency_ms", 0) or 0,
            "api_role": getattr(s, "api_role", ""),
        }
        if agent == "planner":
            planner_messages.append(entry)
        elif agent == "writer":
            writer_messages.append(entry)
    # 按创作顺序（step_no）稳定排序
    planner_messages.sort(key=lambda m: m["step_no"])
    writer_messages.sort(key=lambda m: m["step_no"])
    has_data = bool(revise_rounds) or bool(planner_messages) or bool(writer_messages)
    return {"code": 0, "data": {
        "run_id": run.id,
        "mode": resolve_run_publish_mode(run, db),
        "has_data": has_data,
        "revise_rounds": revise_rounds,
        "planner_messages": planner_messages,
        "writer_messages": writer_messages,
    }}


@router.get("/{run_id}/precheck")
def precheck_run(run_id: int, db: Session = Depends(get_db)):
    """发布前软文预检（P2-1 / C 项补全）：对 run 终稿在当前发布模式下跑综合质量闸门，
    返回结构化预检结果（合规 / 软文风险 / GEO）。非硬阻断，仅暴露数据供前端强制确认弹窗。

    用途：用户在 confirm/publish 前先调此端点，提前知道「这篇文章在目标平台是否会被判软文广告」，
    把「发布后才发现被判软文」的痛点前移到创作确认环节，避免无效发布。
    """
    from ..services.orchestrator import run_quality_gate
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    if getattr(run, "is_deleted", 0):
        raise HTTPException(404, "运行已删除")
    text = (getattr(run, "final_content", "") or "").strip()
    title = (getattr(run, "final_title", "") or "").strip()
    mode = resolve_run_publish_mode(run, db)
    out = resolve_run_output_format(run, db)
    if not text:
        return {"code": 0, "data": {
            "run_id": run.id, "mode": mode, "output_format": out,
            "has_content": False, "gate_pass": False, "compliance_pass": False,
            "geo_score": 0, "geo_pass": False, "platform_compliance": None,
            "issues": ["尚未生成终稿，无法预检，请先完成创作流程（①连接 → ⑥GEO终稿）。"],
            "verdict": "待生成终稿",
        }}
    try:
        ctx = build_studio_context(db, run)
    except Exception as e:  # noqa: BLE001
        # 上下文缺失不阻断预检，仅给品牌名兜底，让合规/软文检测仍可用
        ctx = {"brand_name": (getattr(run, "brand_asset_id", 0) and "")}
        ctx["brand_name"] = ""  # build_studio_context 失败时不注入真实品牌红线字段
    gate = run_quality_gate(text, ctx, mode=mode, output_format=out, title=title)
    pc = gate.get("platform_compliance")
    geo = gate.get("geo") or {}
    data = {
        "run_id": run.id,
        "mode": mode,
        "output_format": out,
        "has_content": True,
        "gate_pass": bool(gate.get("gate_pass")),
        "compliance_pass": bool(gate.get("compliance_pass")),
        "geo_score": int(gate.get("geo_score") or 0),
        "geo_pass": bool(geo.get("gate_pass")),
        "platform_compliance": (
            {
                "pass": bool(pc.get("pass")),
                "risk_score": pc.get("risk_score"),
                "risk_level": pc.get("risk_level"),
                "brand_in_title": pc.get("brand_in_title"),
                "brand_count": pc.get("brand_count"),
                "brand_exposure": pc.get("brand_exposure"),
                "soft_issues": pc.get("soft_issues"),
                "issues": pc.get("issues"),
            } if pc else None
        ),
        "issues": gate.get("issues"),
        "verdict": _precheck_verdict(gate, mode),
    }
    return {"code": 0, "data": data}


class RewriteRequest(BaseModel):
    industry_id: int
    source_text: str
    target_mode: str = "platform"          # geo | platform | green
    brand_asset_id: Optional[int] = None
    ai_engine: str = "deepseek"            # deepseek | mock
    platform: Optional[str] = None
    output_format: str = "markdown"        # markdown | mdx


@router.post("/rewrite")
def rewrite_article_endpoint(req: RewriteRequest, db: Session = Depends(get_db)):
    """文章改写模式（P2-3）：把用户贴来的「被判软文 / 低质」文章，按目标发布模式改写。

    直接复用 提示词三模式策略 + 三 API 调度(writing) + 综合质量闸门。
    返回：改写稿 + 原文软文风险(source_risk) + 改写稿综合闸门(gate)，供前端「风险从 X 降到 Y」展示。
    无可用 LLM 时自动回退 Mock（与浏览器工作室一致），非硬阻断。
    """
    source = (req.source_text or "").strip()
    if not source:
        raise HTTPException(400, "待改写原文不能为空")
    mode = (req.target_mode or "platform").lower()
    if mode not in ("geo", "platform", "green"):
        raise HTTPException(422, "target_mode 仅支持 geo / platform / green")
    from ..services.article_rewrite import rewrite_article
    try:
        result = rewrite_article(
            db,
            industry_id=req.industry_id,
            source_text=source,
            target_mode=mode,
            brand_asset_id=req.brand_asset_id,
            ai_engine=req.ai_engine,
            platform=req.platform,
            output_format=req.output_format,
        )
    except Exception as e:  # noqa: BLE001
        return {"code": 1, "data": {"ok": False, "error": f"改写失败：{e}"}, "error": str(e)}
    gate = result.get("gate") or {}
    pc = gate.get("platform_compliance")
    data = {
        "ok": bool(result.get("ok")),
        "target_mode": result.get("target_mode"),
        "output_format": result.get("output_format"),
        "engine": result.get("engine"),
        "rewritten_text": result.get("rewritten_text"),
        "source_risk": result.get("source_risk"),
        "gate_pass": bool(gate.get("gate_pass")),
        "compliance_pass": bool(gate.get("compliance_pass")),
        "geo_score": int(gate.get("geo_score") or 0),
        "platform_compliance": (
            {
                "pass": bool(pc.get("pass")) if pc else None,
                "risk_score": pc.get("risk_score") if pc else None,
                "risk_level": pc.get("risk_level") if pc else None,
                "brand_count": pc.get("brand_count") if pc else None,
                "brand_exposure": pc.get("brand_exposure") if pc else None,
                "soft_issues": pc.get("soft_issues") if pc else None,
                "issues": pc.get("issues") if pc else None,
            } if pc else None
        ),
        "issues": gate.get("issues"),
        "verdict": _precheck_verdict(gate, result.get("target_mode") or mode),
    }
    return {"code": 0, "data": data}


def _precheck_verdict(gate: Dict[str, Any], mode: str) -> str:
    """把综合闸门结果转成一句中文判定，前端弹窗可直接展示。

    platform / green 模式下 compliance_pass 已把「基础合规自检 + 软文特征检测」合并，
    这里拆开分别判断，便于给出精准结论（尤其是用户最痛的「被判软文广告」场景）。
    """
    compliance = gate.get("compliance") or {}
    basic_pass = bool((compliance.get("compliance") or {}).get("pass"))
    anti_ai_pass = bool((compliance.get("anti_ai") or {}).get("pass"))
    pc = gate.get("platform_compliance")
    if gate.get("gate_pass"):
        if mode in ("platform", "green") and pc and (pc.get("risk_score") or 0) >= 40:
            return "整体可过审，但软文特征偏明显（风险分偏高），建议再洗稿降风险后发布。"
        if mode == "geo" and not gate.get("geo_pass"):
            return "合规通过，但 GEO 评分偏低，被 AI 检索推荐的概率下降。"
        return "通过综合预检，可以确认 / 发布。"
    # —— 未过闸门：优先区分「基础合规」与「软文特征」两类原因 ——
    if not basic_pass or not anti_ai_pass:
        return "未通过平台基础合规自检（违禁词 / 硬广 / 联系方式 / AI味 等问题），发布大概率被拒，请先整改。"
    if mode in ("platform", "green") and pc and not pc.get("pass"):
        if (pc.get("risk_score") or 0) >= 70:
            return "软文特征风险高（平台判广告软文概率大），强烈建议改用 geo 模式或重洗稿降风险后再发布。"
        return "未通过发布闸门：存在软文营销特征，请查看下方明细并洗稿降风险后再发布。"
    return "未通过发布闸门（GEO 评分不足或合规未过），请查看下方明细。"


@router.post("/{run_id}/start")
def start_run_endpoint(run_id: int, db: Session = Depends(get_db)):
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    if run.status == "running":
        return {"code": 0, "data": {"ok": False, "msg": "已在运行中"}}
    # 选了「豆包」却没有登录态凭证：自动回退模拟演示，避免硬性阻断用户
    if (run.ai_engine or "").lower() == "doubao" and not run.doubao_credential_id:
        run.mock_doubao = 1
        run.log = (run.log + "\n[提示] 选择了「豆包」但未配置登录态 cookie，已自动回退「模拟演示」模式。"
                   "如需真实浏览器自动化，请在发布中心上传 platform='doubao' 的 cookie 凭证，"
                   "并在新建运行时选择该凭证。").strip()
        db.commit()
    # DeepSeek 未配置 API 的情况在编排线程内自动回退模拟演示，这里无需特殊处理
    start_run(run_id)
    return {"code": 0, "data": {"ok": True, "msg": "已启动"}}


@router.post("/{run_id}/retry")
def retry_run_endpoint(run_id: int, db: Session = Depends(get_db)):
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    retry_run(run_id)
    return {"code": 0, "data": {"ok": True, "msg": "已重新启动（重跑豆包阶段）"}}


@router.post("/{run_id}/retry-publish")
def retry_publish_endpoint(run_id: int, db: Session = Depends(get_db)):
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    result = retry_publish(run_id)
    return {"code": 0, "data": result}


@router.post("/{run_id}/confirm")
def confirm_run_endpoint(run_id: int, db: Session = Depends(get_db)):
    """步骤⑧：人工满意确认 → 加入内容中心。"""
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    result = confirm_run(run_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "确认失败"))
    return {"code": 0, "data": result}


@router.post("/{run_id}/publish")
def publish_run_endpoint(run_id: int, db: Session = Depends(get_db)):
    """步骤⑨：发布到目标平台（创建发布任务 + 审核闸门）。"""
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    result = publish_run(run_id)
    if not result.get("ok") and not result.get("intercepted"):
        raise HTTPException(400, result.get("error", "发布失败"))
    return {"code": 0, "data": result}


@router.delete("/{run_id}")
def delete_run(run_id: int, db: Session = Depends(get_db)):
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    run.is_deleted = 1
    db.query(BrowserStudioStep).filter(BrowserStudioStep.run_id == run_id).update({"run_id": run_id})
    # 步骤随运行软删，置 is_deleted 逻辑放到步骤上无意义，这里直接保留步骤以便回溯；
    # 运行级软删即可，步骤通过 run 关联隐藏。
    db.commit()
    return {"code": 0, "msg": "已删除"}
