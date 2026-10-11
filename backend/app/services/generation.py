# -*- coding: utf-8 -*-
"""软文生成核心服务（与生产路由共享，供「一键生成并发布」编排复用）。

把单步生成逻辑（渲染提示词 → 调用行业生效 LLM → 返回文本）抽成纯函数，
避免 production 路由与 publish 编排各写一份。

设计要点：
  - 与手动模式并存：本服务只产出文本，由调用方决定写回哪些字段；
  - 未配置 LLM 时返回 need_config=True（连同渲染后的提示词），绝不阻断；
  - geo 步自动解析 4 段结构（优化后标题/正文/GEO评分/优化建议）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..models import LlmConfig, ProductionTask, PromptLibraryItem
from .llm import LLMError, get_provider
from .prompt_engine import build_render_context, render_prompt, unresolved_variables

# step → 提示词类目
_CATEGORY_BY_STEP = {
    "outline": "outline",
    "draft": "draft",
    "rewrite": "rewrite",
    "geo": "geo",
}

# step → 任务上保存的对应提示词字段（geo 步历史沿用 safety_prompt_id）
_STEP_PROMPT_FIELD = {
    "outline": "outline_prompt_id",
    "draft": "draft_prompt_id",
    "rewrite": "rewrite_prompt_id",
    "geo": "safety_prompt_id",
}


def _parse_geo_finalize(text: str) -> dict:
    """解析第9步 geo 提示词交给 AI 后返回的结构化结果。

    预期四个段落（顺序不限，标题严格匹配以便系统解析回填）：
      ## 优化后标题
      ## 优化后正文
      ## GEO 评分（0-100）
      ## 优化建议
    """
    result = {"title": "", "body": "", "score": None, "suggestions": ""}
    if not text:
        return result
    lines = text.split("\n")
    markers = []
    for i, line in enumerate(lines):
        s = line.strip()
        if re.match(r"^#+\s*优化后标题\s*$", s):
            markers.append(("title", i))
        elif re.match(r"^#+\s*优化后正文\s*$", s):
            markers.append(("body", i))
        elif re.match(r"^#+\s*GEO\s*评分", s, re.I):
            markers.append(("score", i))
        elif re.match(r"^#+\s*优化建议\s*$", s):
            markers.append(("suggestions", i))
    for idx, (kind, lineno) in enumerate(markers):
        start = lineno + 1
        end = markers[idx + 1][1] if idx + 1 < len(markers) else len(lines)
        chunk = "\n".join(lines[start:end]).strip()
        if kind == "title":
            result["title"] = chunk
        elif kind == "body":
            result["body"] = chunk
        elif kind == "suggestions":
            result["suggestions"] = chunk
        elif kind == "score":
            m = re.search(r"(\d{1,3})", chunk)
            if m:
                result["score"] = int(m.group(1))
    return result


def _resolve_llm_config(db: Session, task: ProductionTask, config_id: Optional[int]):
    """解析生效 LLM 配置：优先 config_id → 行业默认(is_default) → 首个启用(status=1)。"""
    c = None
    try:
        if config_id:
            c = db.query(LlmConfig).filter(
                LlmConfig.id == config_id,
                LlmConfig.industry_id == task.industry_id,
                LlmConfig.is_deleted == 0,
            ).first()
        if not c:
            c = db.query(LlmConfig).filter(
                LlmConfig.industry_id == task.industry_id,
                LlmConfig.is_deleted == 0,
                LlmConfig.is_default == 1,
            ).first()
        if not c:
            c = db.query(LlmConfig).filter(
                LlmConfig.industry_id == task.industry_id,
                LlmConfig.is_deleted == 0,
                LlmConfig.status == 1,
            ).first()
        # 兜底：行业内无配置时，退回任意「默认/启用」配置（避免已配置 DeepSeek 却因行业隔离误报未配置）
        if not c:
            c = db.query(LlmConfig).filter(
                LlmConfig.is_deleted == 0, LlmConfig.is_default == 1
            ).first()
        if not c:
            c = db.query(LlmConfig).filter(
                LlmConfig.is_deleted == 0, LlmConfig.status == 1
            ).first()
    except Exception:  # noqa: BLE001
        c = None
    return c


def generate_step_text(
    db: Session,
    task: ProductionTask,
    step: str,
    prompt_id: Optional[int] = None,
    config_id: Optional[int] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    custom_vars: Optional[Dict[str, Any]] = None,
    run_id: Optional[int] = None,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    """渲染某步提示词并调用 LLM，返回统一结构。

    返回字段：
      ok          是否成功生成文本
      need_config 是否因未配置 LLM 而中断（此时 rendered 仍返回，方便手动模式）
      rendered    渲染后的提示词
      unresolved  未解析变量名列表
      prompt_name / prompt_id / category
      text        LLM 生成文本（失败/未配置时为 ""）
      parsed      geo 步的 4 段解析结果，其它步为 None
      error       失败原因
    """
    category = _CATEGORY_BY_STEP.get(step)
    if not category:
        return {
            "ok": False, "need_config": False,
            "rendered": "", "unresolved": [], "prompt_name": "", "category": "",
            "text": "", "parsed": None, "prompt_id": 0,
            "error": f"不支持的 step：{step}（支持 outline/draft/rewrite/geo）",
        }

    # 选定提示词：优先 prompt_id，否则取任务已存的同类目提示词
    p = None
    if prompt_id:
        p = db.query(PromptLibraryItem).filter(
            PromptLibraryItem.id == prompt_id, PromptLibraryItem.is_deleted == 0
        ).first()
    if not p:
        field = _STEP_PROMPT_FIELD.get(step)
        pid = getattr(task, field, 0) if field else 0
        if pid:
            p = db.query(PromptLibraryItem).filter(
                PromptLibraryItem.id == pid, PromptLibraryItem.is_deleted == 0
            ).first()
    if not p:
        return {
            "ok": False, "need_config": False,
            "rendered": "", "unresolved": [], "prompt_name": "", "category": category,
            "text": "", "parsed": None, "prompt_id": 0,
            "error": f"未选择「{category}」类提示词，无法生成。请先指定对应提示词。",
        }

    context = build_render_context(db, task, task.industry_id)
    if custom_vars:
        context.update(custom_vars)
    rendered = render_prompt(p.content, context)
    unresolved = unresolved_variables(p.content, context)

    c = _resolve_llm_config(db, task, config_id)
    if not c or not c.api_key:
        return {
            "ok": False, "need_config": True,
            "rendered": rendered, "unresolved": unresolved,
            "prompt_name": p.name, "category": category, "text": "",
            "parsed": None, "prompt_id": p.id,
            "error": "未配置 LLM（如 DeepSeek）API Key。请先在「设置 → LLM 配置」填写，"
                     "或继续使用手动模式：复制上方渲染后的提示词给 AI → 把结果粘贴回系统。",
        }

    kwargs: Dict[str, Any] = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    # 浏览器工作室运行内调用：走「三 API 调度器」（按角色路由 + 负载均衡 + 故障切换 + 调用日志）
    if run_id is not None:
        from .llm_scheduler import scheduler_generate
        try:
            text, meta = scheduler_generate(
                db, role or "writing", rendered, run_id=run_id, step_key=step,
                temperature=float(c.temperature) if c.temperature not in (None, "") else 0.7,
                max_tokens=c.max_tokens, timeout=c.timeout,
            )
        except LLMError as e:
            return {
                "ok": False, "need_config": False,
                "rendered": rendered, "unresolved": unresolved,
                "prompt_name": p.name, "category": category, "text": "",
                "parsed": None, "prompt_id": p.id,
                "call_meta": None, "error": str(e),
            }
        parsed = _parse_geo_finalize(text) if step == "geo" else None
        return {
            "ok": True, "need_config": False,
            "rendered": rendered, "unresolved": unresolved,
            "prompt_name": p.name, "category": category, "text": text,
            "parsed": parsed, "prompt_id": p.id,
            "config_name": meta.get("model"), "provider": meta.get("provider"),
            "model": meta.get("model"),
            "call_meta": meta,
        }

    try:
        text = get_provider({
            "provider": c.provider, "api_key": c.api_key, "base_url": c.base_url,
            "model": c.model,
            "temperature": float(c.temperature) if c.temperature not in (None, "") else 0.7,
            "max_tokens": c.max_tokens, "timeout": c.timeout,
        }).generate(rendered, **kwargs)
    except LLMError as e:
        return {
            "ok": False, "need_config": False,
            "rendered": rendered, "unresolved": unresolved,
            "prompt_name": p.name, "category": category, "text": "",
            "parsed": None, "prompt_id": p.id, "error": str(e),
        }

    parsed = _parse_geo_finalize(text) if step == "geo" else None
    return {
        "ok": True, "need_config": False,
        "rendered": rendered, "unresolved": unresolved,
        "prompt_name": p.name, "category": category, "text": text,
        "parsed": parsed, "prompt_id": p.id,
        "config_name": c.name, "provider": c.provider, "model": c.model,
    }


def assign_default_prompts(db: Session, task: ProductionTask) -> None:
    """为任务补齐缺失的默认提示词（按行业 + 类目），仅覆盖仍为 0 的字段。"""
    fields = {
        "outline": "outline_prompt_id",
        "draft": "draft_prompt_id",
        "rewrite": "rewrite_prompt_id",
        "geo": "safety_prompt_id",
    }
    changed = False
    for cat, field in fields.items():
        if getattr(task, field, 0):
            continue  # 已指定，不覆盖
        p = db.query(PromptLibraryItem).filter(
            PromptLibraryItem.industry_id == task.industry_id,
            PromptLibraryItem.category == cat,
            PromptLibraryItem.is_deleted == 0,
            PromptLibraryItem.is_default == 1,
        ).first()
        if not p:
            p = db.query(PromptLibraryItem).filter(
                PromptLibraryItem.industry_id == task.industry_id,
                PromptLibraryItem.category == cat,
                PromptLibraryItem.is_deleted == 0,
            ).first()
        if not p:
            p = db.query(PromptLibraryItem).filter(
                PromptLibraryItem.category == cat,
                PromptLibraryItem.is_deleted == 0,
            ).first()
        if p:
            setattr(task, field, p.id)
            changed = True
    if changed:
        db.commit()
