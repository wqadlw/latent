"""行业空间管理路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import (
    Industry, Platform, Persona, Account, KnowledgeCategory, KnowledgeItem,
    ContentAsset, RuleLibrary, Keyword, Topic,
    PromptLibraryItem, BrandAsset, EffectRecord,
)
from ..utils import to_dict

router = APIRouter(prefix="/api/industry", tags=["行业空间"])


class IndustryIn(BaseModel):
    name: str
    description: str = ""
    status: int = 1
    config: str = "{}"
    sort: int = 0


class IndustryCloneIn(BaseModel):
    new_name: str
    new_description: str = ""


@router.get("")
def list_industries(db: Session = Depends(get_db)):
    items = db.query(Industry).filter(Industry.is_deleted == 0)\
        .order_by(Industry.sort.asc(), Industry.id.asc()).all()
    result = []
    for it in items:
        d = to_dict(it)
        d["account_count"] = db.query(Account).filter(
            Account.industry_id == it.id, Account.is_deleted == 0).count()
        d["platform_count"] = db.query(Platform).filter(
            Platform.industry_id == it.id, Platform.is_deleted == 0).count()
        d["keyword_count"] = db.query(Keyword).filter(
            Keyword.industry_id == it.id, Keyword.is_deleted == 0).count()
        d["content_count"] = db.query(ContentAsset).filter(
            ContentAsset.industry_id == it.id, ContentAsset.is_deleted == 0).count()
        result.append(d)
    return {"code": 0, "data": result}


@router.post("")
def create_industry(payload: IndustryIn, db: Session = Depends(get_db)):
    # 同名（未删除）行业已存在时给出明确提示，避免静默重复创建或唯一约束 500
    exist = db.query(Industry).filter(
        Industry.name == payload.name, Industry.is_deleted == 0
    ).first()
    if exist:
        return {"code": 1, "msg": f"行业「{payload.name}」已存在"}
    it = Industry(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/{item_id}")
def update_industry(item_id: int, payload: IndustryIn, db: Session = Depends(get_db)):
    it = db.query(Industry).filter(Industry.id == item_id).first()
    if not it:
        raise HTTPException(404, "行业不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/{item_id}")
def delete_industry(item_id: int, db: Session = Depends(get_db)):
    it = db.query(Industry).filter(Industry.id == item_id).first()
    if not it:
        raise HTTPException(404, "行业不存在")
    it.is_deleted = 1
    # 级联软删除该行业下的全部子表数据，避免产生孤儿行。
    # 仅对同时具备 industry_id 与 is_deleted 字段的模型执行，
    # 个别早期模型（如 effect_record）未设计 is_deleted 时自动跳过，避免整条删除链路 500。
    child_models = (
        Platform, Persona, Account, KnowledgeCategory, KnowledgeItem,
        RuleLibrary, Keyword, Topic, PromptLibraryItem, BrandAsset,
        ContentAsset, EffectRecord,
    )
    for model in child_models:
        if not (hasattr(model, "industry_id") and hasattr(model, "is_deleted")):
            continue
        db.query(model).filter(
            model.industry_id == item_id, model.is_deleted == 0
        ).update({"is_deleted": 1})
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.post("/{item_id}/clone")
def clone_industry(item_id: int, payload: IndustryCloneIn, db: Session = Depends(get_db)):
    """克隆行业（复制平台、人设、规则、模板等全部配置）"""
    src = db.query(Industry).filter(Industry.id == item_id).first()
    if not src:
        raise HTTPException(404, "源行业不存在")

    new_ind = Industry(
        name=payload.new_name,
        description=payload.new_description,
        status=1, config=src.config, sort=0,
    )
    db.add(new_ind)
    db.flush()

    # 克隆平台
    platforms = db.query(Platform).filter(
        Platform.industry_id == item_id, Platform.is_deleted == 0).all()
    pid_map = {}
    for p in platforms:
        new_p = Platform(
            industry_id=new_ind.id, name=p.name,
            word_count_min=p.word_count_min, word_count_max=p.word_count_max,
            compliance_level=p.compliance_level, config=p.config, sort=p.sort,
        )
        db.add(new_p)
        db.flush()
        pid_map[p.id] = new_p.id

    # 克隆人设
    personas = db.query(Persona).filter(
        Persona.industry_id == item_id, Persona.is_deleted == 0).all()
    for p in personas:
        db.add(Persona(
            industry_id=new_ind.id, name=p.name, identity=p.identity,
            tone_style=p.tone_style, contact_rule=p.contact_rule, sort=p.sort,
        ))

    # 克隆账号
    accounts = db.query(Account).filter(
        Account.industry_id == item_id, Account.is_deleted == 0).all()
    for a in accounts:
        db.add(Account(
            industry_id=new_ind.id, platform_id=pid_map.get(a.platform_id),
            persona_id=a.persona_id, account_name=a.account_name,
            content_track=a.content_track, status=a.status, sort=a.sort,
        ))

    # 克隆知识分类
    cats = db.query(KnowledgeCategory).filter(
        KnowledgeCategory.industry_id == item_id, KnowledgeCategory.is_deleted == 0).all()
    for c in cats:
        db.add(KnowledgeCategory(
            industry_id=new_ind.id, name=c.name, sort=c.sort,
        ))

    # 克隆规则
    rules = db.query(RuleLibrary).filter(
        RuleLibrary.industry_id == item_id, RuleLibrary.is_deleted == 0).all()
    for r in rules:
        new_pids = ",".join(str(pid_map.get(int(x), 0)) for x in r.platform_ids.split(",") if x.strip().isdigit()) if r.platform_ids and r.platform_ids != "all" else "all"
        db.add(RuleLibrary(
            industry_id=new_ind.id, rule_type=r.rule_type, content=r.content,
            platform_ids=new_pids, status=r.status, sort=r.sort,
        ))

    # 克隆关键词
    kws = db.query(Keyword).filter(
        Keyword.industry_id == item_id, Keyword.is_deleted == 0).all()
    for k in kws:
        db.add(Keyword(
            industry_id=new_ind.id, word=k.word, type=k.type,
            priority=k.priority, related_product=k.related_product,
            tags=k.tags, sort=k.sort,
        ))

    # 克隆提示词库
    prompts = db.query(PromptLibraryItem).filter(
        PromptLibraryItem.industry_id == item_id, PromptLibraryItem.is_deleted == 0).all()
    for p in prompts:
        db.add(PromptLibraryItem(
            industry_id=new_ind.id, name=p.name, category=p.category,
            content=p.content, variables=p.variables, description=p.description,
            is_default=p.is_default, sort=p.sort,
        ))

    # 克隆品牌资产
    brands = db.query(BrandAsset).filter(
        BrandAsset.industry_id == item_id, BrandAsset.is_deleted == 0).all()
    for b in brands:
        db.add(BrandAsset(
            industry_id=new_ind.id, brand_name=b.brand_name,
            official_website=b.official_website, contact_phone=b.contact_phone,
            contact_wechat=b.contact_wechat, contact_email=b.contact_email,
            slogan=b.slogan, core_products=b.core_products,
            unique_selling_points=b.unique_selling_points,
            target_keywords=b.target_keywords, brand_story=b.brand_story,
            is_default=b.is_default, sort=b.sort,
        ))

    db.commit()
    return {"code": 0, "msg": f"已克隆为新行业「{payload.new_name}」", "data": {"new_id": new_ind.id}}


@router.post("/sort")
def update_sort(items: List[dict], db: Session = Depends(get_db)):
    for i, it in enumerate(items):
        db.query(Industry).filter(Industry.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "排序已更新"}
