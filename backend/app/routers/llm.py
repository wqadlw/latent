"""
LLM 设置与生成路由
- 配置 CRUD（行业级隔离、可多套并存、is_default 标记激活项）
- 连通性测试
- 一键生成（调用已配置的供应商；未配置时明确提示走手动模式）

与"手动复制提示词给 AI → 粘贴结果回系统"模式并存：本路由只负责"配置 + 调用"，
绝不强制替代人工审阅。生成的文本由前端展示，用户确认后再写回生产任务字段。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db, now
from ..models import Industry, LlmConfig
from ..services.llm import PROVIDER_CHOICES, LLMError, generate_with_config, get_provider
from ..utils import to_dict

router = APIRouter(prefix="/api/llm", tags=["LLM 设置"])


class LlmConfigIn(BaseModel):
    industry_id: int
    name: str = "默认"
    provider: str = "deepseek"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: str = "0.7"
    max_tokens: int = 2000
    timeout: int = 60
    is_default: int = 0
    status: int = 1
    # 三 API 角色路由：research(选题调研/大纲) / writing(正文撰写/精修/GEO) /
    # review(审核优化/整改) / general(兜底通用)。同一角色可绑定多个配置实现负载均衡。
    role: str = "general"
    sort: int = 0


class LlmConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[str] = None
    max_tokens: Optional[int] = None
    timeout: Optional[int] = None
    is_default: Optional[int] = None
    status: Optional[int] = None
    role: Optional[str] = None
    sort: Optional[int] = None


class GenerateIn(BaseModel):
    industry_id: int
    prompt: str
    config_id: Optional[int] = None   # 不传则使用行业默认配置
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


def _config_to_payload(c: LlmConfig) -> dict:
    """把配置对象转成可注入供应商的字典（仅含调用所需字段）。"""
    return {
        "provider": c.provider,
        "api_key": c.api_key,
        "base_url": c.base_url,
        "model": c.model,
        "temperature": float(c.temperature) if c.temperature not in (None, "") else 0.7,
        "max_tokens": c.max_tokens,
        "timeout": c.timeout,
    }


def _resolve_config(db: Session, industry_id: int, config_id: Optional[int]) -> LlmConfig:
    """解析行业生效的 LLM 配置：优先 config_id，否则取 is_default，否则取首个启用项。"""
    if config_id:
        c = db.query(LlmConfig).filter(
            LlmConfig.id == config_id, LlmConfig.industry_id == industry_id,
            LlmConfig.is_deleted == 0,
        ).first()
        if not c:
            raise HTTPException(404, "指定的 LLM 配置不存在")
        return c
    c = db.query(LlmConfig).filter(
        LlmConfig.industry_id == industry_id, LlmConfig.is_deleted == 0,
        LlmConfig.is_default == 1,
    ).first()
    if not c:
        c = db.query(LlmConfig).filter(
            LlmConfig.industry_id == industry_id, LlmConfig.is_deleted == 0,
            LlmConfig.status == 1,
        ).first()
    if not c:
        raise HTTPException(400, "当前行业未配置 LLM（如 DeepSeek）。请先在「设置 → LLM 配置」中填写 API Key，"
                                   "或继续使用手动模式：复制提示词给 AI（网页/客户端）→ 把结果粘贴回系统。")
    return c


@router.get("/providers")
def list_providers():
    """返回可选供应商清单（含默认 base_url / model），供前端下拉。"""
    return {"code": 0, "data": PROVIDER_CHOICES}


@router.get("/configs")
def list_configs(industry_id: int, db: Session = Depends(get_db)):
    items = db.query(LlmConfig).filter(
        LlmConfig.industry_id == industry_id, LlmConfig.is_deleted == 0
    ).order_by(LlmConfig.is_default.desc(), LlmConfig.sort.asc(), LlmConfig.id.desc()).all()
    return {"code": 0, "data": [to_dict(i) for i in items]}


@router.post("/configs")
def create_config(payload: LlmConfigIn, db: Session = Depends(get_db)):
    ind = db.query(Industry).filter(Industry.id == payload.industry_id, Industry.is_deleted == 0).first()
    if not ind:
        raise HTTPException(404, "行业不存在")
    # 若设为默认，先清掉同行业其它默认项
    if payload.is_default == 1:
        db.query(LlmConfig).filter(
            LlmConfig.industry_id == payload.industry_id, LlmConfig.is_deleted == 0
        ).update({LlmConfig.is_default: 0})
    # 首个配置自动设为默认
    count = db.query(LlmConfig).filter(
        LlmConfig.industry_id == payload.industry_id, LlmConfig.is_deleted == 0
    ).count()
    is_default = 1 if (payload.is_default == 1 or count == 0) else 0
    c = LlmConfig(**{**payload.dict(), "is_default": is_default})
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"code": 0, "data": to_dict(c), "msg": "创建成功"}


@router.put("/configs/{cid}")
def update_config(cid: int, payload: LlmConfigUpdate, db: Session = Depends(get_db)):
    c = db.query(LlmConfig).filter(LlmConfig.id == cid, LlmConfig.is_deleted == 0).first()
    if not c:
        raise HTTPException(404, "配置不存在")
    data = payload.dict(exclude_unset=True)
    if data.get("is_default") == 1:
        db.query(LlmConfig).filter(
            LlmConfig.industry_id == c.industry_id, LlmConfig.is_deleted == 0,
            LlmConfig.id != cid,
        ).update({LlmConfig.is_default: 0})
    for k, v in data.items():
        if v is not None:
            setattr(c, k, v)
    c.update_time = now()
    db.commit()
    return {"code": 0, "data": to_dict(c), "msg": "更新成功"}


@router.delete("/configs/{cid}")
def delete_config(cid: int, db: Session = Depends(get_db)):
    c = db.query(LlmConfig).filter(LlmConfig.id == cid, LlmConfig.is_deleted == 0).first()
    if not c:
        raise HTTPException(404, "配置不存在")
    c.is_deleted = 1
    # 若删除的是默认项，把同行业首个启用项提升为默认
    if c.is_default == 1:
        nxt = db.query(LlmConfig).filter(
            LlmConfig.industry_id == c.industry_id, LlmConfig.is_deleted == 0,
            LlmConfig.status == 1,
        ).first()
        if nxt:
            nxt.is_default = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.post("/configs/{cid}/set-default")
def set_default(cid: int, db: Session = Depends(get_db)):
    c = db.query(LlmConfig).filter(LlmConfig.id == cid, LlmConfig.is_deleted == 0).first()
    if not c:
        raise HTTPException(404, "配置不存在")
    db.query(LlmConfig).filter(
        LlmConfig.industry_id == c.industry_id, LlmConfig.is_deleted == 0,
    ).update({LlmConfig.is_default: 0})
    c.is_default = 1
    db.commit()
    return {"code": 0, "data": to_dict(c), "msg": f"已将「{c.name}」设为默认"}


@router.post("/configs/{cid}/test")
def test_config(cid: int, db: Session = Depends(get_db)):
    """连通性测试：直接用该配置调用一次极短生成。"""
    c = db.query(LlmConfig).filter(LlmConfig.id == cid, LlmConfig.is_deleted == 0).first()
    if not c:
        raise HTTPException(404, "配置不存在")
    if not c.api_key:
        return {"code": 0, "data": {"ok": False, "error": "未填写 api_key"}}
    try:
        provider = get_provider(_config_to_payload(c))
        res = provider.test()
    except LLMError as e:
        return {"code": 0, "data": {"ok": False, "error": str(e)}}
    except Exception as e:  # noqa: BLE001
        return {"code": 0, "data": {"ok": False, "error": str(e)}}
    return {"code": 0, "data": res}


@router.post("/generate")
def generate(payload: GenerateIn, db: Session = Depends(get_db)):
    """一键生成：用行业生效的 LLM 配置直接生成文本。

    失败时若因"未配置"，返回清晰提示引导用户走手动模式。
    """
    if not payload.prompt or not payload.prompt.strip():
        raise HTTPException(400, "prompt 不能为空")
    c = _resolve_config(db, payload.industry_id, payload.config_id)
    if not c.api_key:
        return {
            "code": 0,
            "data": {
                "ok": False,
                "need_config": True,
                "text": "",
                "error": "该 LLM 配置未填写 api_key。请先填写，或使用手动模式：复制提示词给 AI → 粘贴结果回系统。",
            },
        }
    kwargs = {}
    if payload.temperature is not None:
        kwargs["temperature"] = payload.temperature
    if payload.max_tokens is not None:
        kwargs["max_tokens"] = payload.max_tokens
    try:
        text = generate_with_config(_config_to_payload(c), payload.prompt, **kwargs)
    except LLMError as e:
        return {"code": 0, "data": {"ok": False, "need_config": False, "text": "", "error": str(e)}}
    except Exception as e:  # noqa: BLE001
        return {"code": 0, "data": {"ok": False, "need_config": False, "text": "", "error": str(e)}}
    return {
        "code": 0,
        "data": {
            "ok": True,
            "need_config": False,
            "text": text,
            "config_id": c.id,
            "config_name": c.name,
            "provider": c.provider,
            "model": c.model,
        },
    }
