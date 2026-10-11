# -*- coding: utf-8 -*-
"""
自动化提示词路由（Automation Studio）

端点：
  GET    /api/automation-prompts               列表（按 category 可选过滤）
  GET    /api/automation-prompts/steps          工作流步骤定义（前端可视化用）
  PUT    /api/automation-prompts/{key}          更新某提示词内容
  POST   /api/automation-prompts/{key}/reset    重置为出厂默认
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import automation_prompts as svc
from ..services.llm_scheduler import get_scheduler_status
from ..services.orchestrator import ROLE_BY_STEP, STEP_PROMPT_KEYS, get_step_defs
from ..services.publish_strategy import (
    get_publish_strategies,
    update_publish_strategy,
)

router = APIRouter(prefix="/api/automation-prompts", tags=["automation-prompts"])


class UpdateReq(BaseModel):
    content: str


class StrategyUpdateReq(BaseModel):
    title_min_len: Optional[int] = None
    title_max_len: Optional[int] = None
    min_words: Optional[int] = None
    max_words: Optional[int] = None
    structure_rules: Optional[str] = None
    paragraph_rules: Optional[str] = None
    banned_words_rule: Optional[str] = None
    soft_ad_rule: Optional[str] = None
    publish_mode_type: Optional[str] = None
    geo_keyword_density: Optional[str] = None
    geo_structured_summary: Optional[int] = None
    geo_title_info: Optional[int] = None
    geo_notes: Optional[str] = None
    notes: Optional[str] = None


@router.get("")
def list_prompts(category: Optional[str] = None, db: Session = Depends(get_db)):
    rows = svc.get_automation_prompts(db, category)
    return {"code": 0, "data": rows}


@router.get("/steps")
def workflow_steps():
    """返回自动化工作流 10 步定义（含角色），供前端可视化。"""
    engine_kind = "deepseek"
    steps = get_step_defs(engine_kind)
    out = []
    for no, key, title, agent in steps:
        out.append({"step_no": no, "step_key": key, "title": title, "agent": agent})
    return {"code": 0, "data": out}


@router.get("/meta")
def workflow_meta():
    """步骤→提示词 key 与 步骤→API角色 的单一真源，供前端（Manual.vue 操作手册）委托，
    消除前后端双份映射漂移：前端不再硬编码 STEP_PROMPT_KEYS / ROLE_BY_STEP，
    改为挂载时从本端点取，后端改了映射前端自动跟随。"""
    return {"code": 0, "data": {
        "step_prompt_keys": STEP_PROMPT_KEYS,
        "role_by_step": ROLE_BY_STEP,
    }}


# 发布模式元信息（前端预览背景内容时切换）
PUBLISH_MODES = [
    {"value": "geo", "label": "强品牌 / GEO 模式", "desc": "品牌突出，被 AI 推荐引用"},
    {"value": "platform", "label": "平台合规模式", "desc": "中性有价值，规避软文广告判定"},
    {"value": "green", "label": "绿色吸粉模式", "desc": "纯涨粉，品牌顺带一提"},
    {"value": "official", "label": "官网 / 自建站", "desc": "产出可复制 MDX 代码"},
]


@router.get("/context")
def automation_context(mode: str = "geo", db: Session = Depends(get_db)):
    """返回某发布模式下会被注入提示词的背景内容（品牌策略 / 模式目标 / 专家团队 / 官网地址），供页面展示与预览。"""
    from ..services.prompt_engine import OFFICIAL_SITE_URL
    ctx = svc.get_resolved_context(db, mode)
    ctx["modes"] = PUBLISH_MODES
    ctx["official_site_url"] = OFFICIAL_SITE_URL
    return {"code": 0, "data": ctx}


@router.put("/{key}")
def update_prompt(key: str, payload: UpdateReq, db: Session = Depends(get_db)):
    ok = svc.update_automation_prompt(db, key, payload.content)
    if not ok:
        raise HTTPException(404, f"提示词不存在：{key}")
    return {"code": 0, "msg": "已保存", "key": key}


@router.post("/{key}/reset")
def reset_prompt(key: str, db: Session = Depends(get_db)):
    ok = svc.reset_automation_prompt(db, key)
    if not ok:
        raise HTTPException(404, f"提示词不存在：{key}")
    return {"code": 0, "msg": "已重置为默认", "key": key}


@router.get("/scheduler-status")
def scheduler_status(db: Session = Depends(get_db)):
    """三 API 调度状态：三角色 → 配置分配 / 最近耗时 / 故障切换，供「三 API 调度」状态卡。"""
    return {"code": 0, "data": get_scheduler_status(db)}


@router.get("/publish-strategies")
def publish_strategies(db: Session = Depends(get_db)):
    """各平台合规发布策略（格式/禁区/发布模式/AI 抓取优化）。"""
    return {"code": 0, "data": get_publish_strategies(db)}


@router.put("/publish-strategies/{sid}")
def update_strategy(sid: int, payload: StrategyUpdateReq, db: Session = Depends(get_db)):
    """更新某平台合规发布策略。"""
    res = update_publish_strategy(db, sid, payload.dict(exclude_unset=True))
    if not res.get("ok"):
        raise HTTPException(404, res.get("error", "更新失败"))
    return {"code": 0, "msg": "已保存", "id": sid}
