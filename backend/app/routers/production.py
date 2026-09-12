"""标准软文生产工作空间路由（8 步流程）

8 步流程：
  1. 选择行业
  2. 选择平台
  3. 选择人设账号
  4. 选择关键词 + 大纲提示词 → 生成大纲
  5. 选择初稿提示词 + 大纲 → 生成第一版初稿
  6. 选择洗稿提示词 + 初稿 → 生成第二版去 AI 味精修稿
  7. 选择安全筛选提示词 + 精修稿 → 生成最终文章 + 发布
  8. 文章配图：提示词驱动（与步骤 4-7 同款）
     - 从提示词库选择「配图类(illustration)」提示词，按封面 + 各章节逐张渲染文生图提示词（AI 生图）
     - 同时给出配图建议（AI 生图 vs 网络搜图）及对应产物：AI→文生图提示词，网络→图片关键字

系统边界：不调用任何 AI 接口，仅负责编排提示词与回填人工产出。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import json
import re

from ..database import get_db, now
from ..models import (
    ProductionTask, PromptLibraryItem, Industry, Platform, Account, Persona,
    Keyword, KeywordGroup, KnowledgeItem, KnowledgeCategory, ContentAsset, BrandAsset, RuleLibrary,
    ContentVersion, TargetPersona, IntentQuestion, LlmConfig,
)
from ..utils import to_dict, parse_json, parse_ids, parse_datetime
from ..services.prompt_engine import build_render_context, render_prompt, unresolved_variables
from ..services.geo_score import compute_geo_score, build_geo_audit_prompt, parse_geo_audit_result
from ..services.llm import get_provider, LLMError
from ..services.generation import (
    generate_step_text, _parse_geo_finalize, _CATEGORY_BY_STEP,
    _STEP_PROMPT_FIELD, assign_default_prompts,
)
from ..services.orchestrator import run_quality_gate

router = APIRouter(prefix="/api/production", tags=["软文生产工作空间"])

# update_task 中禁止前端覆盖的字段（避免把字符串时间写回 DateTime 列）
_PROTECTED_FIELDS = {"id", "create_time", "update_time", "is_deleted"}


class TaskIn(BaseModel):
    industry_id: int
    title: str = ""
    platform_id: Optional[int] = None
    account_id: Optional[int] = None
    persona_id: Optional[int] = None
    keyword_ids: str = ""
    knowledge_item_ids: str = ""
    rule_ids: str = ""
    # GEO 作战：目标画像与意图问题（生成"带信号的 GEO 软文"的锚点）
    target_persona_id: Optional[int] = 0
    intent_question_id: Optional[int] = 0
    geo_score: int = 0
    outline_prompt_id: Optional[int] = None
    draft_prompt_id: Optional[int] = None
    rewrite_prompt_id: Optional[int] = None
    safety_prompt_id: Optional[int] = None
    outline_content: str = ""
    draft_content: str = ""
    rewrite_content: str = ""
    final_content: str = ""
    safety_report: str = ""
    publish_url: str = ""
    current_step: int = 1
    status: str = "draft"


class RenderIn(BaseModel):
    task_id: int
    prompt_id: int
    category: str  # outline / draft / rewrite / safety
    keyword_ids: List[int] = []
    knowledge_item_ids: List[int] = []
    rule_ids: List[int] = []  # v5 新增：选定的规则库规则 id（覆盖任务已存值，便于未保存即预览）
    custom_vars: dict = {}  # v4 新增：自定义变量覆盖


@router.get("")
def list_tasks(industry_id: int, db: Session = Depends(get_db)):
    items = db.query(ProductionTask).filter(
        ProductionTask.industry_id == industry_id,
        ProductionTask.is_deleted == 0
    ).order_by(ProductionTask.id.desc()).all()
    return {"code": 0, "data": [to_dict(i) for i in items]}


@router.post("")
def create_task(payload: TaskIn, db: Session = Depends(get_db)):
    it = ProductionTask(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


# 内容字段 -> 版本步骤（保存内容变化时自动记录历史版本）
_CONTENT_STEP_MAP = {
    "outline_content": "outline",
    "draft_content": "draft",
    "rewrite_content": "rewrite",
    "safety_report": "safety",
    "final_content": "final",
}


def _save_version(db, task, step, content, payload):
    """记录一条内容版本，附带当时的规则/知识点/关键词/提示词配置快照"""
    snapshot = {
        "rule_ids": payload.get("rule_ids", task.rule_ids),
        "knowledge_item_ids": payload.get("knowledge_item_ids", task.knowledge_item_ids),
        "keyword_ids": payload.get("keyword_ids", task.keyword_ids),
    }
    prompt_field = {
        "outline": "outline_prompt_id", "draft": "draft_prompt_id",
        "rewrite": "rewrite_prompt_id", "safety": "safety_prompt_id",
    }.get(step)
    if prompt_field:
        snapshot["prompt_id"] = payload.get(prompt_field, getattr(task, prompt_field, 0))
    last = (
        db.query(ContentVersion)
        .filter(ContentVersion.task_id == task.id, ContentVersion.step == step)
        .order_by(ContentVersion.version_no.desc())
        .first()
    )
    version_no = (last.version_no + 1) if last else 1
    db.add(ContentVersion(
        task_id=task.id, step=step, content=content,
        config_snapshot=json.dumps(snapshot, ensure_ascii=False),
        version_no=version_no,
    ))


@router.put("/{task_id}")
def update_task(task_id: int, payload: dict, db: Session = Depends(get_db)):
    it = db.query(ProductionTask).filter(ProductionTask.id == task_id).first()
    if not it:
        raise HTTPException(404, "任务不存在")
    for k, v in payload.items():
        # 跳过受保护字段，避免前端把字符串时间写回 DateTime 列
        if k in _PROTECTED_FIELDS:
            continue
        if hasattr(it, k):
            # 内容字段变化 -> 自动存版本
            if k in _CONTENT_STEP_MAP and v not in (None, "") and v != getattr(it, k):
                _save_version(db, it, _CONTENT_STEP_MAP[k], v, payload)
            setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    it = db.query(ProductionTask).filter(ProductionTask.id == task_id).first()
    if not it:
        raise HTTPException(404, "任务不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


# ========== 版本 / 历史管理 ==========
@router.get("/{task_id}/versions")
def list_versions(task_id: int, step: str = "", db: Session = Depends(get_db)):
    """列出某任务的内容版本历史，可按步骤筛选"""
    q = db.query(ContentVersion).filter(ContentVersion.task_id == task_id)
    if step:
        q = q.filter(ContentVersion.step == step)
    items = q.order_by(ContentVersion.step, ContentVersion.version_no.desc()).all()
    return {"code": 0, "data": [{
        "id": v.id, "step": v.step, "version_no": v.version_no,
        "content": v.content, "config_snapshot": v.config_snapshot,
        "create_time": v.create_time.isoformat() if v.create_time else "",
    } for v in items]}


@router.post("/{task_id}/versions/{vid}/restore")
def restore_version(task_id: int, vid: int, db: Session = Depends(get_db)):
    """回滚到指定版本（把版本内容写回任务对应字段）"""
    v = db.query(ContentVersion).filter(ContentVersion.id == vid, ContentVersion.task_id == task_id).first()
    if not v:
        raise HTTPException(404, "版本不存在")
    it = db.query(ProductionTask).filter(ProductionTask.id == task_id).first()
    if not it:
        raise HTTPException(404, "任务不存在")
    field = {
        "outline": "outline_content", "draft": "draft_content",
        "rewrite": "rewrite_content", "safety": "safety_report", "final": "final_content",
    }.get(v.step)
    if field:
        setattr(it, field, v.content)
    db.commit()
    return {"code": 0, "msg": "已回滚到该版本"}


@router.post("/render")
def render_prompt_api(payload: RenderIn, db: Session = Depends(get_db)):
    """渲染提示词：把模板里的占位符替换成真实上下文"""
    t = db.query(ProductionTask).filter(ProductionTask.id == payload.task_id).first()
    if not t:
        raise HTTPException(404, "任务不存在")
    p = db.query(PromptLibraryItem).filter(PromptLibraryItem.id == payload.prompt_id).first()
    if not p:
        raise HTTPException(404, "提示词不存在")

    if payload.keyword_ids:
        t.keyword_ids = ",".join(str(i) for i in payload.keyword_ids)
    if payload.knowledge_item_ids:
        t.knowledge_item_ids = ",".join(str(i) for i in payload.knowledge_item_ids)
    if payload.rule_ids:
        t.rule_ids = ",".join(str(i) for i in payload.rule_ids)
    db.commit()

    context = build_render_context(db, t, t.industry_id)
    # v4 新增：合并自定义变量（覆盖同名内置变量）
    if payload.custom_vars:
        context.update(payload.custom_vars)
    rendered = render_prompt(p.content, context)
    # 安全网：检测模板中使用了但上下文未提供的变量（会原样保留为 {xxx}）
    unresolved = unresolved_variables(p.content, context)
    # v4 新增：使用次数自增
    p.usage_count = (p.usage_count or 0) + 1
    p.last_used_time = now()
    db.commit()
    return {"code": 0, "data": {"rendered": rendered, "unresolved": unresolved}, "msg": "渲染成功"}


# ========== 一键生成（调用已配置 LLM；未配置时引导手动模式） ==========
class GenerateIn(BaseModel):
    step: str  # outline / draft / rewrite / geo
    prompt_id: Optional[int] = None
    keyword_ids: List[int] = []
    knowledge_item_ids: List[int] = []
    rule_ids: List[int] = []
    custom_vars: dict = {}
    config_id: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@router.post("/{task_id}/generate")
def generate_step(task_id: int, payload: GenerateIn, db: Session = Depends(get_db)):
    """一键生成：渲染该步提示词 → 调用行业生效的 LLM → 返回原文。

    与手动模式并存：本端点只产出文本，由前端展示并让用户确认后写回对应字段
    （geo 步走 /geo-finalize 解析 4 段结构）。未配置 LLM 时返回引导提示，
    提示词与渲染结果仍一并返回，方便用户直接走手动复制模式。
    """
    t = db.query(ProductionTask).filter(ProductionTask.id == task_id).first()
    if not t:
        raise HTTPException(404, "任务不存在")

    # 临时应用本轮选词/选知识点/选规则（与 render 接口一致）
    if payload.keyword_ids:
        t.keyword_ids = ",".join(str(i) for i in payload.keyword_ids)
    if payload.knowledge_item_ids:
        t.knowledge_item_ids = ",".join(str(i) for i in payload.knowledge_item_ids)
    if payload.rule_ids:
        t.rule_ids = ",".join(str(i) for i in payload.rule_ids)
    db.commit()

    r = generate_step_text(
        db, t, payload.step,
        prompt_id=payload.prompt_id,
        config_id=payload.config_id,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        custom_vars=payload.custom_vars or None,
    )

    if r.get("need_config"):
        return {
            "code": 0,
            "data": {
                "ok": False, "need_config": True,
                "rendered": r.get("rendered", ""), "unresolved": r.get("unresolved", []),
                "prompt_name": r.get("prompt_name", ""), "category": r.get("category", ""),
                "text": "", "error": r.get("error", ""),
            },
        }
    if not r.get("ok"):
        return {
            "code": 0,
            "data": {
                "ok": False, "need_config": False,
                "rendered": r.get("rendered", ""), "unresolved": r.get("unresolved", []),
                "prompt_name": r.get("prompt_name", ""), "category": r.get("category", ""),
                "text": "", "error": r.get("error", "生成失败"),
            },
        }
    return {
        "code": 0,
        "data": {
            "ok": True,
            "need_config": False,
            "rendered": r["rendered"],
            "unresolved": r["unresolved"],
            "prompt_name": r["prompt_name"],
            "category": r["category"],
            "text": r["text"],
            "parsed": r["parsed"],
            "config_name": r.get("config_name", ""),
            "provider": r.get("provider", ""),
            "model": r.get("model", ""),
        },
    }


# ========== GEO 评分闸门（本地启发式，不调用 AI） ==========
class GeoScoreIn(BaseModel):
    content: str = ""
    intent_question: str = ""
    expected_recommendation: str = ""
    target_persona_name: str = ""
    brand_name: str = ""
    official_website: str = ""
    contact: str = ""
    core_products: str = ""
    selling_points: str = ""


@router.post("/geo-score")
def geo_score_standalone(payload: GeoScoreIn, db: Session = Depends(get_db)):
    """独立 GEO 评分（本地启发式兜底）：传入文章正文 + 品牌/意图信号，返回 0-100 评分与明细。"""
    result = compute_geo_score(
        content=payload.content,
        brand_name=payload.brand_name,
        official_website=payload.official_website,
        contact=payload.contact,
        intent_question=payload.intent_question,
        expected_recommendation=payload.expected_recommendation,
        target_persona_name=payload.target_persona_name,
        core_products=payload.core_products,
        selling_points=payload.selling_points,
    )
    result["intent_question"] = payload.intent_question or ""
    result["expected_recommendation"] = payload.expected_recommendation or ""
    return {"code": 0, "data": result}


def _assemble_geo_inputs(t, db):
    """装配 GEO 审计/评分所需的全部上下文：正文 + 默认品牌信号 + 绑定意图问题。"""
    content = t.final_content or t.rewrite_content or t.draft_content or ""
    brand = db.query(BrandAsset).filter(
        BrandAsset.industry_id == t.industry_id,
        BrandAsset.is_default == 1, BrandAsset.is_deleted == 0,
    ).first() or db.query(BrandAsset).filter(
        BrandAsset.industry_id == t.industry_id, BrandAsset.is_deleted == 0,
    ).first()
    brand_name = brand.brand_name if brand else ""
    official_website = brand.official_website if brand else ""
    contact = " ".join(x for x in [brand.contact_phone if brand else "", brand.contact_wechat if brand else "", brand.contact_email if brand else ""] if x)
    core_products = brand.core_products if brand else ""
    selling_points = brand.unique_selling_points if brand else ""
    intent_question = ""
    expected_recommendation = ""
    target_persona_name = ""
    if t.intent_question_id:
        iq = db.query(IntentQuestion).filter(IntentQuestion.id == t.intent_question_id).first()
        if iq:
            intent_question = iq.question or ""
            expected_recommendation = iq.expected_recommendation or ""
            if iq.persona_id:
                tp = db.query(TargetPersona).filter(TargetPersona.id == iq.persona_id).first()
                target_persona_name = tp.name if tp else ""
    return dict(
        content=content, brand_name=brand_name, official_website=official_website,
        contact=contact, core_products=core_products, selling_points=selling_points,
        intent_question=intent_question, expected_recommendation=expected_recommendation,
        target_persona_name=target_persona_name,
    )


def _resolve_task_publish_mode(t: ProductionTask, db: Session) -> tuple:
    """解析手动流任务的发布模式/产出形态：查绑定平台的 publish_mode/output_format，
    与自动流（doubao_studio.resolve_run_*）默认对齐——缺省 geo / markdown。
    返回 (mode, output_format)。
    """
    mode, out = "geo", "markdown"
    if t.platform_id:
        pf = db.query(Platform).filter(Platform.id == t.platform_id).first()
        if pf:
            _pm = (getattr(pf, "publish_mode", "") or "").strip()
            if _pm in ("geo", "platform", "green"):
                mode = _pm
            _out = (getattr(pf, "output_format", "") or "").strip()
            if _out in ("markdown", "mdx"):
                out = _out
    return mode, out


def run_manual_quality_gate(db: Session, t: ProductionTask, text: str, title: str = "") -> dict:
    """手动流综合质量闸门：复用 orchestrator.run_quality_gate（与自动流同一真源）。

    手动流此前只调 GEO 评分、缺平台合规硬闸门；此处补齐「违禁词/硬广/联系方式 + AI味
    + 软文特征(platform/green)」检测。采用「surface 不硬阻断」策略——把结论回传/落库供
    用户判断，不改变现有发布行为（与自动流「未过审也可自担风险手动确认」一致）。
    """
    mode, out = _resolve_task_publish_mode(t, db)
    inp = _assemble_geo_inputs(t, db)
    ctx = {
        "brand_name": inp.get("brand_name", ""),
        "official_website": inp.get("official_website", ""),
        # _assemble_geo_inputs 用 contact（合并微信/电话/邮箱），闸门读 contact_phone → 映射
        "contact_phone": inp.get("contact", ""),
        "core_products": inp.get("core_products", ""),
        "selling_points": inp.get("selling_points", ""),
        "intent_question": inp.get("intent_question", ""),
        "expected_recommendation": inp.get("expected_recommendation", ""),
        "target_persona_name": inp.get("target_persona_name", ""),
    }
    gate = run_quality_gate(text, ctx, mode=mode, output_format=out, title=title)
    gate["mode"] = mode
    gate["output_format"] = out
    return gate


def _merge_safety_report(ai_suggestions: str, gate: dict) -> str:
    """把 AI 优化建议 + 合规闸门结论合并为安全筛选报告（非破坏式，清晰分节）。"""
    parts = []
    _pass = bool(gate.get("gate_pass"))
    _head = "【平台合规闸门】" + ("✅ 通过" if _pass else "⚠️ 未通过（发布前建议整改）")
    parts.append(f"{_head}（模式：{gate.get('mode', 'geo')}）")
    issues = gate.get("issues") or []
    if issues:
        parts.append("待整改问题：")
        parts.extend(f"  · {i}" for i in issues[:20])
    else:
        parts.append("未检出平台合规/软文特征风险项。")
    body = "\n".join(parts)
    if ai_suggestions:
        return f"{ai_suggestions}\n\n{'-' * 24}\n{body}"
    return body


def apply_geo_finalize(db: Session, t: ProductionTask, ai_result: str) -> dict:
    """第9步终检写回（供端点与一键发布编排共用）。

    解析 AI 返回的「安全·GEO 终稿」4 段结构，评分（优先 AI，缺失用本地启发式兜底）
    并写回 final_title / final_content / geo_score / safety_report，返回结果 dict。
    """
    parsed = _parse_geo_finalize(ai_result)

    final_title = (parsed["title"] or "").strip() or (t.title or f"任务#{t.id}")
    final_body = (parsed["body"] or "").strip() or (t.final_content or t.rewrite_content or t.draft_content or "")

    # 评分：优先用 AI 给的 GEO 评分；缺失则用本地启发式对「最终正文」兜底计算
    inp = _assemble_geo_inputs(t, db)
    inp["content"] = final_body or inp["content"]
    local_score = compute_geo_score(**inp)["score"]
    ai_score = parsed["score"]
    score = ai_score if ai_score is not None else local_score

    # 优化建议 → 安全筛选报告
    suggestions = (parsed["suggestions"] or "").strip()

    # 平台合规硬闸门（手动流补齐：与自动流共用 orchestrator.run_quality_gate）
    gate = run_manual_quality_gate(db, t, final_body, final_title)
    safety_report = _merge_safety_report(suggestions, gate)

    t.final_title = final_title
    t.final_content = final_body
    t.geo_score = int(score)
    t.safety_report = safety_report
    db.commit()

    return {
        "final_title": final_title,
        "final_content": final_body,
        "geo_score": int(score),
        "safety_report": safety_report,
        "ai_score": ai_score,
        "local_score": local_score,
        "parsed_ok": bool(parsed["title"] and parsed["body"]),
        "quality_gate": {
            "gate_pass": bool(gate.get("gate_pass")),
            "compliance_pass": bool(gate.get("compliance_pass")),
            "geo_score": int(gate.get("geo_score") or 0),
            "mode": gate.get("mode", "geo"),
            "issues": gate.get("issues") or [],
        },
    }


@router.post("/{task_id}/geo-audit-prompt")
def geo_audit_prompt(task_id: int, db: Session = Depends(get_db)):
    """生成交给外部 AI 执行的 GEO 审计提示词（本系统不调用大模型）。"""
    t = db.query(ProductionTask).filter(ProductionTask.id == task_id).first()
    if not t:
        raise HTTPException(404, "任务不存在")
    inp = _assemble_geo_inputs(t, db)
    prompt = build_geo_audit_prompt(**inp)
    return {
        "code": 0,
        "data": {
            "prompt": prompt,
            "intent_question": inp["intent_question"],
            "expected_recommendation": inp["expected_recommendation"],
            "has_content": bool(inp["content"]),
        },
    }


class GeoAuditImportIn(BaseModel):
    ai_result: str = ""


class GeoFinalizeIn(BaseModel):
    ai_result: str = ""  # 第9步 geo 提示词交给 AI 后，AI 返回的结构化结果（含 优化后标题/正文/评分/建议）


@router.post("/{task_id}/geo-audit-import")
def geo_audit_import(task_id: int, payload: GeoAuditImportIn, db: Session = Depends(get_db)):
    """导入外部 AI 返回的 GEO 审计 JSON，解析归一化后写回任务分数。"""
    t = db.query(ProductionTask).filter(ProductionTask.id == task_id).first()
    if not t:
        raise HTTPException(404, "任务不存在")
    inp = _assemble_geo_inputs(t, db)
    try:
        result = parse_geo_audit_result(
            payload.ai_result,
            inp["intent_question"],
            inp["expected_recommendation"],
            content=inp.get("content", ""),
            target_persona_name=inp.get("target_persona_name", ""),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    t.geo_score = int(result["score"])
    db.commit()
    result["task_id"] = task_id
    result["brand_name"] = inp["brand_name"]
    return {"code": 0, "data": result, "msg": f"AI 评分 {result['score']} / 100"}


@router.post("/{task_id}/geo-score")
def geo_score_task(task_id: int, db: Session = Depends(get_db)):
    """对生产任务做 GEO 评分（本地启发式兜底），基于最终文章 + 绑定品牌/意图，分数写回任务。"""
    t = db.query(ProductionTask).filter(ProductionTask.id == task_id).first()
    if not t:
        raise HTTPException(404, "任务不存在")
    inp = _assemble_geo_inputs(t, db)
    result = compute_geo_score(**inp)
    t.geo_score = int(result["score"])
    db.commit()
    result["task_id"] = task_id
    result["brand_name"] = inp["brand_name"]
    result["intent_question"] = inp["intent_question"]
    result["expected_recommendation"] = inp["expected_recommendation"]
    return {"code": 0, "data": result, "msg": f"GEO 评分 {result['score']} / 100"}


@router.post("/{task_id}/geo-finalize")
def geo_finalize(task_id: int, payload: GeoFinalizeIn, db: Session = Depends(get_db)):
    """第9步终检合并端点：解析 AI 返回的「安全·GEO 终稿」结构化结果，
    评分（优先用 AI 给的分，缺失则用本地启发式兜底）并直接写回
    final_title / final_content / geo_score / safety_report，产出可直接发布的最终形态。

    合并了原「GEO 筛选闸门（评分）」+「安全·GEO 筛选提示词（改写）」两步为一个闭环。
    """
    t = db.query(ProductionTask).filter(ProductionTask.id == task_id).first()
    if not t:
        raise HTTPException(404, "任务不存在")
    data = apply_geo_finalize(db, t, payload.ai_result)
    return {
        "code": 0,
        "data": data,
        "msg": f"终检完成，GEO 评分 {data['geo_score']} / 100，已生成可发布标题与正文",
    }


@router.post("/{task_id}/publish")
def publish_task(task_id: int, payload: dict, db: Session = Depends(get_db)):
    """发布任务：标记为已完成，并把最终文章入库到内容资产库"""
    t = db.query(ProductionTask).filter(ProductionTask.id == task_id).first()
    if not t:
        raise HTTPException(404, "任务不存在")
    t.status = "done"
    t.publish_url = payload.get("publish_url", "")
    # 发布后推进到第 10 步（文章配图），让用户继续补充配图
    t.current_step = 10
    db.commit()

    # 入库到内容资产
    _final_title = t.final_title or t.title or f"任务#{t.id}"
    if t.final_content:
        existing = db.query(ContentAsset).filter(
            ContentAsset.industry_id == t.industry_id,
            ContentAsset.title == _final_title,
            ContentAsset.is_deleted == 0
        ).first()
        if not existing:
            ca = ContentAsset(
                industry_id=t.industry_id,
                platform_id=t.platform_id,
                account_id=t.account_id,
                title=_final_title,
                content=t.final_content,
                review_status="pass",
                publish_status="published",
                publish_url=payload.get("publish_url", ""),
                publish_time=datetime.now(),
            )
            db.add(ca)
            db.commit()

    return {"code": 0, "msg": "发布成功"}


# ========== 第8步 文章配图：提示词驱动 + AI/网络双方案 ==========
# 与步骤 4-7 同款模式：用户从提示词库选择「配图类(illustration)」提示词（或用内置默认），
# 系统将提示词按「封面 + 各章节」逐张渲染，产出可直接粘贴到即梦/通义万相/Midjourney 的文生图提示词；
# 同时给出「配图建议」（AI 生图 vs 网络搜图）及对应产物：AI→文生图提示词，网络→图片关键字。
# 系统不调用任何图像/AI 接口，仅编排提示词与回填人工产出。
# 平台 → 封面/内文 比例与尺寸（封面与内文插图可不同，更贴合各平台真实配图规范）
_PLATFORM_ASPECT = {
    "小红书": {"cover": ("3:4", "1080x1440"), "inline": ("1:1", "1080x1080")},
    "抖音": {"cover": ("9:16", "1080x1920"), "inline": ("9:16", "1080x1920")},
    "视频号": {"cover": ("9:16", "1080x1920"), "inline": ("9:16", "1080x1920")},
    "微博": {"cover": ("1:1", "1080x1080"), "inline": ("4:3", "1280x960")},
    "公众号": {"cover": ("16:9", "1280x720"), "inline": ("1:1", "1080x1080")},
    "微信": {"cover": ("16:9", "1280x720"), "inline": ("1:1", "1080x1080")},
    "知乎": {"cover": ("16:9", "1280x720"), "inline": ("4:3", "1280x960")},
    "头条": {"cover": ("16:9", "1280x720"), "inline": ("1:1", "1080x1080")},
    "百家号": {"cover": ("16:9", "1280x720"), "inline": ("1:1", "1080x1080")},
    "网易号": {"cover": ("16:9", "1280x720"), "inline": ("1:1", "1080x1080")},
    "搜狐号": {"cover": ("16:9", "1280x720"), "inline": ("1:1", "1080x1080")},
}
_DEFAULT_COVER = ("16:9", "1280x720")
_DEFAULT_INLINE = ("1:1", "1080x1080")

# 风格预设
STYLE_PRESETS = {
    "photo": "写实商业摄影（自然光、电影感构图、高质感、8k）",
    "fresh": "清新生活插画（明亮治愈、扁平微质感）",
    "guofeng": "国风插画（水墨与传统元素）",
    "flat": "极简扁平插画（色块几何、现代感）",
    "3d": "3D 渲染（C4D 风格、柔和材质）",
}
_PLATFORM_STYLE = {
    "小红书": "fresh", "抖音": "photo", "视频号": "photo", "微博": "photo",
    "公众号": "photo", "微信": "photo", "知乎": "photo", "头条": "photo",
    "百家号": "photo", "网易号": "photo", "搜狐号": "photo",
}
_NEGATIVE = "文字水印、Logo 水印、低清模糊、肢体变形、多余手指、刺眼高对比、硬广海报感、拥挤杂乱"

# 按风格细化反向词（不同风格的失败模式不同）
_NEGATIVE_BY_STYLE = {
    "photo": "文字水印、Logo 水印、低清模糊、肢体变形、多余手指、刺眼高对比、硬广海报感、拥挤杂乱",
    "fresh": "暗沉色调、文字水印、低清模糊、杂乱背景、生硬边缘、过度饱和、廉价感",
    "guofeng": "现代元素、西式建筑、文字水印、低清、高饱和刺眼、塑料感、违章比例",
    "flat": "写实照片感、脏渐变、文字水印、低清、过重阴影、立体透视畸变",
    "3d": "低模破面、文字水印、低清、塑料感过强、锯齿、穿模",
}

# 内置默认配图提示词（用户未在库中选择时兜底；同时作为库里默认模板种子）
_DEFAULT_ILLU_PROMPT = """你是一位资深视觉策划 / AI 绘画提示词工程师。请为发布在{platform_name}的一篇图文生成一张配图。

# 图片位置
{image_position}（cover=封面图，section=内文插图）

# 本张图对应内容
章节标题：{section_title}
章节正文：{section_content}

# 品牌与风格
品牌：{brand_name}
画面风格：{style_label}
推荐比例：{aspect_ratio}（{image_size}）

# 创作要求
1. 主体突出、构图有呼吸感、色彩明亮统一，与{platform_name}平台调性一致
2. 呈现自然真实的使用场景而非生硬硬广
3. 可融入关键词意象：{keywords}
4. 不要出现文字、水印、Logo

请直接输出文生图提示词（中文），不要输出思考过程。"""

# 网络搜图推荐平台（标注版权风险）
_NETWORK_PLATFORMS = [
    "Unsplash（免版税，可商用）",
    "Pexels（免版税，可商用）",
    "Pixabay（免版税，可商用）",
    "百度图片（注意：需确认授权/注明出处）",
    "谷歌图片（注意：需确认授权/注明出处）",
]


def _aspect_for(platform_name, kind):
    entry = _PLATFORM_ASPECT.get(platform_name)
    if entry and kind in entry:
        return entry[kind]
    return _DEFAULT_COVER if kind == "cover" else _DEFAULT_INLINE


def _split_sections(content):
    """将最终文章拆分为 [{header, level, body}] 列表（保留标题层级，便于前端图文混排重建）。"""
    if not content or not content.strip():
        return []
    sections = []
    cur_level = 0
    cur_heading = None
    cur_body = []
    for raw in content.split("\n"):
        line = raw.strip()
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            if cur_heading is not None or cur_body:
                sections.append({
                    "header": cur_heading,
                    "level": cur_level,
                    "body": "\n".join(cur_body).strip(),
                })
            cur_level = len(m.group(1))
            cur_heading = m.group(2).strip()
            cur_body = []
        else:
            cur_body.append(raw)
    if cur_heading is not None or cur_body:
        sections.append({
            "header": cur_heading,
            "level": cur_level,
            "body": "\n".join(cur_body).strip(),
        })
    return [s for s in sections if (s["header"] or s["body"])]


def _subject_of(heading, body, keywords):
    if heading:
        subject = heading
    else:
        first = (body or "").replace("\n", " ").strip()
        subject = first[:40] if first else "文章核心内容"
    kw = "、".join(keywords[:3]) if keywords else ""
    return subject, kw


def _build_prompts_en(subject, kw, style_label, platform_name, aspect):
    """英文文生图提示词基底（适用于 Midjourney 等需英文的工具）。"""
    en = (
        f"Illustration for a social media article on {platform_name}. Subject: {subject}. "
        f"Style: {style_label}. Clear focal point, cinematic composition, bright cohesive palette, "
        f"high quality, 8k, natural usage scene." + (f" Motifs: {kw}." if kw else "") + f" --ar {aspect}"
    )
    return en


def _recommend_method(platform_name, final_content):
    """配图建议：根据平台调性 + 文章内容信号（真实场景 / 品牌信息）判断优先 AI 生图还是网络搜图。"""
    visual_platforms = {"小红书", "抖音", "视频号", "微博", "Instagram", "Pinterest"}
    real_photo_kw = ["测评", "实测", "教程", "对比", "数据", "价格", "新闻", "案例", "避坑", "实景", "工厂", "门店", "探店"]
    brand_kw = ["品牌", "官网", "旗舰店", "加盟", "授权"]
    content = (final_content or "")
    content_hint = content[:800]
    wants_real = any(k in content_hint for k in real_photo_kw)
    has_brand = any(k in content_hint for k in brand_kw)
    has_text = bool(content.strip())

    if not has_text:
        return {"method": "ai", "reason": "尚未回填最终文章，默认建议 AI 生图以保证风格统一、规避版权风险；回填后重新生成可校准建议。"}

    if platform_name in visual_platforms:
        if wants_real:
            return {"method": "ai", "reason": f"{platform_name} 以视觉种草为主，本篇含「测评/实测/教程」等真实场景，建议优先 AI 生图统一风格、规避版权；关键内文实拍图可辅以网络免版税素材。"}
        return {"method": "ai", "reason": f"{platform_name} 偏精美视觉，AI 生图能保证封面与插图风格统一、规避扒图侵权风险，建议全程 AI 生图。"}

    # 专业 / 资讯平台
    if wants_real and not has_brand:
        return {"method": "network", "reason": f"{platform_name} 偏专业/资讯，本篇含测评/数据/案例等真实场景，真实照片更可信，建议网络搜图（务必用 Unsplash / Pexels / Pixabay 等免版税图库或注明出处）；纯品牌调性图可用 AI 补充。"}
    if has_brand:
        return {"method": "ai", "reason": f"{platform_name} 本篇含品牌/官网信息，建议 AI 生图以保证品牌视觉一致、规避第三方图片授权风险；个别真实场景图可网络补充。"}
    return {"method": "ai", "reason": f"{platform_name} 常规图文建议 AI 生图统一视觉；若涉及真实人物/场景实拍，可改用网络免版税图库。"}


# 网络搜图关键字的停用词（避免把"的/了/如何"等无意义词当关键字）
_STOP = set("的 了 和 与 及 是 在 我 你 他 她 它 我们 你们 他们 这 那 这个 那个 一个 一种 可以 如何 怎么 什么 为什么 因为 所以 但是 而且 如果 以及 对于 关于 通过 进行 成为".split())


def _extract_search_keywords(heading, body, kws, platform_name, brand_name=""):
    """为网络搜图提取图片关键字（每图 3-6 个短语，去停用词、去重、优先议题词）。"""
    cands = []
    if heading:
        cands.append(heading.strip())
    if body:
        parts = [p.strip() for p in re.split(r"[，。；\.！？\n]", body) if p.strip()]
        for p in parts[:2]:
            if 2 <= len(p) <= 20:
                cands.append(p)
    for k in (kws or [])[:3]:
        cands.append(k)
    if brand_name:
        cands.append(brand_name)
    seen = set()
    out = []
    for x in cands:
        x = x.strip()
        if not x or x in seen or x in _STOP:
            continue
        if len(x) > 20:
            x = x[:20]
        seen.add(x)
        out.append(x)
    out.append(f"{platform_name} 风格配图")
    return out[:6]


class IlluIn(BaseModel):
    task_id: int
    prompt_id: Optional[int] = None  # 配图类提示词 id（来自提示词库 illustration 分类）；None 用内置默认
    method: str = "both"  # ai / network / both
    style: Optional[str] = None  # photo/fresh/guofeng/flat/3d；None 表示按平台自动
    max_inline: int = 6


@router.post("/illustration-plan")
def illustration_plan(payload: IlluIn, db: Session = Depends(get_db)):
    """第8步：生成文章配图方案。
    - AI 生图：按「封面 + 各章节」逐张渲染选中的配图提示词，产出文生图提示词（中文 + 英文基底 + 反向词）
    - 网络搜图：为每张图提取图片关键字与推荐搜图平台
    - 同时返回配图建议（AI 还是网络）
    """
    t = db.query(ProductionTask).filter(ProductionTask.id == payload.task_id).first()
    if not t:
        raise HTTPException(404, "任务不存在")

    platform = db.query(Platform).filter(Platform.id == t.platform_id).first() if t.platform_id else None
    platform_name = platform.name if platform else "自媒体平台"

    brand = db.query(BrandAsset).filter(
        BrandAsset.industry_id == t.industry_id,
        BrandAsset.is_default == 1,
        BrandAsset.is_deleted == 0,
    ).first()
    if not brand:
        brand = db.query(BrandAsset).filter(
            BrandAsset.industry_id == t.industry_id,
            BrandAsset.is_deleted == 0,
        ).first()
    brand_name = brand.brand_name if brand else ""

    kws = []
    if t.keyword_ids:
        ids = [int(i) for i in t.keyword_ids.split(",") if str(i).strip().isdigit()]
        kws = [k.word for k in db.query(Keyword).filter(Keyword.id.in_(ids)).all()]

    style = payload.style or _PLATFORM_STYLE.get(platform_name, "photo")
    style_label = STYLE_PRESETS.get(style, STYLE_PRESETS["photo"])

    # 选中的配图提示词（提示词驱动）
    illu_prompt = None
    if payload.prompt_id:
        illu_prompt = db.query(PromptLibraryItem).filter(
            PromptLibraryItem.id == payload.prompt_id,
            PromptLibraryItem.is_deleted == 0,
        ).first()
    template = illu_prompt.content if illu_prompt else _DEFAULT_ILLU_PROMPT

    # 渲染上下文（全局）
    context = build_render_context(db, t, t.industry_id)
    context["brand_name"] = brand_name
    context["style_label"] = style_label
    context["keywords"] = "、".join(kws)

    method = payload.method or "both"
    cover_aspect, cover_size = _aspect_for(platform_name, "cover")
    inline_aspect, inline_size = _aspect_for(platform_name, "inline")

    sections = _split_sections(t.final_content)
    recommendation = _recommend_method(platform_name, t.final_content)

    plan = []
    neg = _NEGATIVE_BY_STYLE.get(style, _NEGATIVE)
    # 封面图
    cover_subject = t.final_title or t.title or (sections[0]["header"] if sections else "文章主题")
    cover_ctx = dict(context)
    cover_ctx.update({
        "section_title": t.final_title or t.title or cover_subject,
        "section_content": (t.final_content or "")[:300],
        "section_index": 1,
        "image_position": "cover",
        "aspect_ratio": cover_aspect,
        "image_size": cover_size,
    })
    ai_prompt_cover = render_prompt(template, cover_ctx) if method in ("ai", "both") else ""
    kw_cover = _extract_search_keywords(t.final_title or t.title or cover_subject, (t.final_content or "")[:200], kws, platform_name, brand_name)
    plan.append({
        "index": 1,
        "position": "cover",
        "section_anchor": -1,
        "section_title": "封面图",
        "scene_desc": cover_subject,
        "aspect_ratio": cover_aspect,
        "size": cover_size,
        "style": style,
        "style_label": style_label,
        "ai_prompt": ai_prompt_cover,
        "ai_prompt_en": _build_prompts_en(cover_subject, "、".join(kws), style_label, platform_name, cover_aspect) if method in ("ai", "both") else "",
        "negative_prompt": neg if method in ("ai", "both") else "",
        "search_keywords": kw_cover if method in ("network", "both") else [],
        "search_platforms": _NETWORK_PLATFORMS if method in ("network", "both") else [],
        "image_url": "",
    })

    # 内文插图（按章节锚定，section_anchor = 该章节在 sections 中的下标，便于前端图文混排）
    for i, sec in enumerate(sections[: payload.max_inline]):
        h, b = sec["header"], sec["body"]
        subject, _ = _subject_of(h, b, kws)
        sec_ctx = dict(context)
        sec_ctx.update({
            "section_title": h or f"第{i + 1}段",
            "section_content": b[:400],
            "section_index": i + 2,
            "image_position": "section",
            "aspect_ratio": inline_aspect,
            "image_size": inline_size,
        })
        ai_prompt_sec = render_prompt(template, sec_ctx) if method in ("ai", "both") else ""
        kw_sec = _extract_search_keywords(h, b, kws, platform_name, brand_name)
        plan.append({
            "index": i + 2,
            "position": "section",
            "section_anchor": i,
            "section_title": h or f"第{i + 1}段",
            "scene_desc": subject,
            "aspect_ratio": inline_aspect,
            "size": inline_size,
            "style": style,
            "style_label": style_label,
            "ai_prompt": ai_prompt_sec,
            "ai_prompt_en": _build_prompts_en(subject, "、".join(kws), style_label, platform_name, inline_aspect) if method in ("ai", "both") else "",
            "negative_prompt": neg if method in ("ai", "both") else "",
            "search_keywords": kw_sec if method in ("network", "both") else [],
            "search_platforms": _NETWORK_PLATFORMS if method in ("network", "both") else [],
            "image_url": "",
        })

    # 使用次数（提示词驱动统计）
    if illu_prompt:
        illu_prompt.usage_count = (illu_prompt.usage_count or 0) + 1
        illu_prompt.last_used_time = now()
        db.commit()

    # 持久化（整包：meta + recommendation + plan）
    saved = {
        "meta": {
            "prompt_id": payload.prompt_id or 0,
            "method": method,
            "style": style,
            "platform_name": platform_name,
        },
        "recommendation": recommendation,
        "plan": plan,
    }
    t.illustration_plan = json.dumps(saved, ensure_ascii=False)
    db.commit()

    copy_all_ai = _build_copy_all_ai(plan, platform_name)
    copy_all_network = _build_copy_all_network(plan, platform_name)
    return {
        "code": 0,
        "data": {
            "recommendation": recommendation,
            "plan": plan,
            "sections": sections,
            "platform_name": platform_name,
            "brand_name": brand_name,
            "style": style,
            "style_label": style_label,
            "copy_all_ai": copy_all_ai,
            "copy_all_network": copy_all_network,
            "prompt_id": payload.prompt_id or 0,
            "prompt_name": illu_prompt.name if illu_prompt else "内置默认配图提示词",
        },
        "msg": "配图方案已生成",
    }


def _build_copy_all_ai(plan, platform_name):
    lines = [f"# {platform_name} 文章配图 · AI 生图提示词（共 {len(plan)} 张）", ""]
    for it in plan:
        label = "封面图" if it["position"] == "cover" else it["section_title"]
        lines.append(f"## {label}（{it['aspect_ratio']} {it['size']}）")
        lines.append("中文提示词：")
        lines.append(it["ai_prompt"])
        if it.get("ai_prompt_en"):
            lines.append("英文提示词：")
            lines.append(it["ai_prompt_en"])
        lines.append(f"反向词：{it['negative_prompt']}")
        lines.append("")
    return "\n".join(lines)


def _build_copy_all_network(plan, platform_name):
    lines = [f"# {platform_name} 文章配图 · 网络搜图关键字（共 {len(plan)} 张）", ""]
    for it in plan:
        label = "封面图" if it["position"] == "cover" else it["section_title"]
        lines.append(f"## {label}（{it['aspect_ratio']} {it['size']}）")
        lines.append("图片关键字：" + "、".join(it["search_keywords"]))
        lines.append("推荐平台：" + "；".join(it["search_platforms"]))
        lines.append("")
    return "\n".join(lines)


@router.get("/{task_id}/options")
def get_options(task_id: int, db: Session = Depends(get_db)):
    """获取任务的可选项：平台、账号、人设、关键词、提示词"""
    t = db.query(ProductionTask).filter(ProductionTask.id == task_id).first()
    if not t:
        raise HTTPException(404, "任务不存在")

    _opt_platform = db.query(Platform).filter(Platform.id == t.platform_id).first() if t.platform_id else None
    platform_name = _opt_platform.name if _opt_platform else "自媒体平台"

    platforms = db.query(Platform).filter(
        Platform.industry_id == t.industry_id, Platform.is_deleted == 0
    ).order_by(Platform.sort.asc()).all()

    accounts = db.query(Account).filter(
        Account.industry_id == t.industry_id, Account.is_deleted == 0
    )
    # 已选平台时，仅返回该平台下的账号（实现"选平台 → 定人设账号"的绑定）
    if t.platform_id:
        accounts = accounts.filter(Account.platform_id == t.platform_id)
    accounts = accounts.all()

    personas = db.query(Persona).filter(
        Persona.industry_id == t.industry_id, Persona.is_deleted == 0
    ).order_by(Persona.sort.asc()).all()

    keywords = db.query(Keyword).filter(
        Keyword.industry_id == t.industry_id, Keyword.is_deleted == 0
    ).order_by(Keyword.priority.desc(), Keyword.sort.asc()).all()

    # 关键词分组（v6 增强：方便第4步关键词库按组浏览）
    keyword_groups_data = db.query(KeywordGroup).filter(
        KeywordGroup.industry_id == t.industry_id,
        KeywordGroup.is_deleted == 0,
    ).order_by(KeywordGroup.sort.asc(), KeywordGroup.id.asc()).all()
    keyword_groups = []
    for g in keyword_groups_data:
        g_items = [k for k in keywords if k.group_id == g.id]
        keyword_groups.append({
            "group": to_dict(g),
            "items": [to_dict(k) for k in g_items],
            "count": len(g_items),
        })
    uncat_kw = [k for k in keywords if k.group_id is None]
    if uncat_kw:
        keyword_groups.append({
            "group": {"id": 0, "name": "未分组", "icon": "Collection", "color": "#94a3b8"},
            "items": [to_dict(k) for k in uncat_kw],
            "count": len(uncat_kw),
        })

    # 新增：知识库知识点（按分类分组，方便第4步选择）
    knowledge_categories = db.query(KnowledgeCategory).filter(
        KnowledgeCategory.industry_id == t.industry_id,
        KnowledgeCategory.is_deleted == 0,
    ).order_by(KnowledgeCategory.sort.asc()).all()

    knowledge_items = db.query(KnowledgeItem).filter(
        KnowledgeItem.industry_id == t.industry_id,
        KnowledgeItem.is_deleted == 0,
    ).order_by(KnowledgeItem.sort.asc(), KnowledgeItem.id.desc()).all()

    # 按分类分组的知识点（v4 增强：方便第4步按分类浏览选择）
    knowledge_grouped = []
    for cat in knowledge_categories:
        cat_items = [ki for ki in knowledge_items if ki.category_id == cat.id]
        knowledge_grouped.append({
            "category": to_dict(cat),
            "items": [to_dict(ki) for ki in cat_items],
            "count": len(cat_items),
        })
    # 未分类的知识点
    uncategorized = [ki for ki in knowledge_items if ki.category_id == 0 or ki.category_id is None]
    if uncategorized:
        knowledge_grouped.append({
            "category": {"id": 0, "name": "未分类", "icon": "Folder", "color": "#94a3b8"},
            "items": [to_dict(ki) for ki in uncategorized],
            "count": len(uncategorized),
        })

    # v5 新增：规则库（按类型分组，供第3步「规则约束」选择并注入提示词）
    rule_items = db.query(RuleLibrary).filter(
        RuleLibrary.industry_id == t.industry_id,
        RuleLibrary.is_deleted == 0,
        RuleLibrary.status == 1,
    ).order_by(RuleLibrary.sort.asc(), RuleLibrary.id.asc()).all()
    rules_by_type = {}
    for r in rule_items:
        rules_by_type.setdefault(r.rule_type, []).append({
            "id": r.id, "rule_type": r.rule_type, "content": r.content,
        })

    prompts = db.query(PromptLibraryItem).filter(
        PromptLibraryItem.industry_id == t.industry_id,
        PromptLibraryItem.is_deleted == 0,
    ).order_by(PromptLibraryItem.sort.asc()).all()

    # GEO 作战：目标画像 + 意图问题（供第4步"确定目标客户需求"选择）
    target_personas = db.query(TargetPersona).filter(
        TargetPersona.industry_id == t.industry_id,
        TargetPersona.is_deleted == 0,
    ).order_by(TargetPersona.sort.asc()).all()
    intent_questions = db.query(IntentQuestion).filter(
        IntentQuestion.industry_id == t.industry_id,
        IntentQuestion.is_deleted == 0,
    ).order_by(IntentQuestion.priority.desc(), IntentQuestion.sort.asc()).all()
    # 当前任务已选的意图问题完整信息（前端展示期望推荐角度 + 自动打标覆盖状态）
    selected_intent = None
    if t.intent_question_id:
        si = db.query(IntentQuestion).filter(IntentQuestion.id == t.intent_question_id).first()
        if si:
            selected_intent = to_dict(si)
            if si.persona_id:
                tpn = db.query(TargetPersona).filter(TargetPersona.id == si.persona_id).first()
                selected_intent["persona_name"] = tpn.name if tpn else ""

    # 平台→账号人设绑定：供第2步展示每个平台下的账号及其绑定人设
    _persona_map = {p.id: p.name for p in personas}
    _all_accounts = db.query(Account).filter(
        Account.industry_id == t.industry_id, Account.is_deleted == 0
    ).all()
    _accounts_by_platform = {}
    for _a in _all_accounts:
        _accounts_by_platform.setdefault(_a.platform_id, []).append({
            "account_name": _a.account_name,
            "persona_name": _persona_map.get(_a.persona_id, "") if _a.persona_id else "",
        })
    platforms_out = []
    for _p in platforms:
        _pd = to_dict(_p)
        _pd["bound_accounts"] = _accounts_by_platform.get(_p.id, [])
        platforms_out.append(_pd)

    return {
        "code": 0,
        "data": {
            "platforms": platforms_out,
            "accounts": [to_dict(a) for a in accounts],
            "personas": [to_dict(p) for p in personas],
            "keywords": [to_dict(k) for k in keywords],
            "keyword_groups": keyword_groups,
            "knowledge_categories": [to_dict(c) for c in knowledge_categories],
            "knowledge_items": [to_dict(ki) for ki in knowledge_items],
            "knowledge_grouped": knowledge_grouped,
            "prompts": {
                "outline": [to_dict(p) for p in prompts if p.category == "outline"],
                "draft": [to_dict(p) for p in prompts if p.category == "draft"],
                "rewrite": [to_dict(p) for p in prompts if p.category == "rewrite"],
                "safety": [to_dict(p) for p in prompts if p.category == "safety"],
                "illustration": [to_dict(p) for p in prompts if p.category == "illustration"],
                # 安全筛选与 GEO 筛选已合并为同一类目：geo 同时容纳两类提示词（兼容旧数据未迁移的情况）
                "geo": [to_dict(p) for p in prompts if p.category in ("geo", "safety")],
            },
            # 第8步配图建议（进入第8步即可见，无需先生成）
            "recommendation": _recommend_method(platform_name, t.final_content),
            # v5 新增：规则库分组（key: ai_seo / anti_ai / compliance）
            "rules": rules_by_type,
            # GEO 作战
            "target_personas": [to_dict(p) for p in target_personas],
            "intent_questions": [to_dict(q) for q in intent_questions],
            "selected_intent": selected_intent,
            "geo_score": t.geo_score or 0,
        },
    }


# ========== v4 新增：知识点搜索 ==========
@router.get("/{task_id}/knowledge-search")
def search_knowledge(task_id: int, keyword: str = "", category_id: Optional[int] = None,
                     db: Session = Depends(get_db)):
    """在第4步中搜索知识点（支持关键词搜索 + 分类过滤）"""
    t = db.query(ProductionTask).filter(ProductionTask.id == task_id).first()
    if not t:
        raise HTTPException(404, "任务不存在")

    q = db.query(KnowledgeItem).filter(
        KnowledgeItem.industry_id == t.industry_id,
        KnowledgeItem.is_deleted == 0,
    )
    if category_id is not None and category_id > 0:
        q = q.filter(KnowledgeItem.category_id == category_id)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            (KnowledgeItem.title.like(like)) |
            (KnowledgeItem.summary.like(like)) |
            (KnowledgeItem.content.like(like)) |
            (KnowledgeItem.tags.like(like))
        )
    items = q.order_by(KnowledgeItem.sort.asc(), KnowledgeItem.id.desc()).all()
    return {"code": 0, "data": [to_dict(ki) for ki in items]}


# ========== v4 新增：知识点详情（含查看次数自增） ==========
@router.get("/knowledge/{item_id}")
def get_knowledge_detail(item_id: int, db: Session = Depends(get_db)):
    """获取知识点详情（查看次数+1）"""
    it = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if not it:
        raise HTTPException(404, "知识点不存在")
    it.view_count = (it.view_count or 0) + 1
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it)}
