"""效果数据统计路由"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Account, ContentAsset, EffectRecord, Keyword, Platform
from ..utils import parse_date, to_dict

router = APIRouter(prefix="/api/effect", tags=["效果统计"])


class EffectIn(BaseModel):
    # model_type 字段以 model_ 开头，会触发 Pydantic v2 的 protected_namespaces 警告，显式关闭
    model_config = ConfigDict(protected_namespaces=())
    industry_id: int
    keyword_id: Optional[int] = None
    model_type: str = ""
    has_brand: int = 0
    has_website: int = 0
    has_contact: int = 0
    rank: int = 0
    record_date: str
    remark: str = ""


@router.get("")
def list_effects(industry_id: int, keyword_id: Optional[int] = None,
                 model_type: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(EffectRecord).filter(EffectRecord.industry_id == industry_id)
    if keyword_id:
        q = q.filter(EffectRecord.keyword_id == keyword_id)
    if model_type:
        q = q.filter(EffectRecord.model_type == model_type)
    items = q.order_by(EffectRecord.id.desc()).all()
    result = []
    for it in items:
        d = to_dict(it)
        kw = db.query(Keyword).filter(Keyword.id == it.keyword_id).first()
        d["keyword_word"] = kw.word if kw else ""
        result.append(d)
    return {"code": 0, "data": result}


@router.post("")
def create_effect(payload: EffectIn, db: Session = Depends(get_db)):
    data = payload.dict()
    # record_date 列是 Date，必须把字符串转成 date 对象
    data["record_date"] = parse_date(data.get("record_date"))
    it = EffectRecord(**data)
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "录入成功"}


@router.delete("/{item_id}")
def delete_effect(item_id: int, db: Session = Depends(get_db)):
    it = db.query(EffectRecord).filter(EffectRecord.id == item_id).first()
    if not it:
        raise HTTPException(404, "记录不存在")
    db.delete(it)
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.get("/dashboard")
def dashboard(industry_id: int, db: Session = Depends(get_db)):
    total_content = db.query(ContentAsset).filter(
        ContentAsset.industry_id == industry_id,
        ContentAsset.is_deleted == 0
    ).count()
    pass_content = db.query(ContentAsset).filter(
        ContentAsset.industry_id == industry_id,
        ContentAsset.is_deleted == 0,
        ContentAsset.review_status == "pass"
    ).count()
    pass_rate = round(pass_content / max(total_content, 1) * 100, 1)

    total_effect = db.query(EffectRecord).filter(
        EffectRecord.industry_id == industry_id
    ).count()
    brand_count = db.query(EffectRecord).filter(
        EffectRecord.industry_id == industry_id,
        EffectRecord.has_brand == 1
    ).count()
    website_count = db.query(EffectRecord).filter(
        EffectRecord.industry_id == industry_id,
        EffectRecord.has_website == 1
    ).count()
    contact_count = db.query(EffectRecord).filter(
        EffectRecord.industry_id == industry_id,
        EffectRecord.has_contact == 1
    ).count()
    brand_rate = round(brand_count / max(total_effect, 1) * 100, 1)
    website_rate = round(website_count / max(total_effect, 1) * 100, 1)
    contact_rate = round(contact_count / max(total_effect, 1) * 100, 1)

    platforms = db.query(Platform).filter(
        Platform.industry_id == industry_id, Platform.is_deleted == 0
    ).all()
    platform_stats = []
    for p in platforms:
        cnt = db.query(ContentAsset).filter(
            ContentAsset.industry_id == industry_id,
            ContentAsset.platform_id == p.id,
            ContentAsset.is_deleted == 0
        ).count()
        platform_stats.append({"name": p.name, "count": cnt})
    platform_stats.sort(key=lambda x: -x["count"])

    accounts = db.query(Account).filter(
        Account.industry_id == industry_id, Account.is_deleted == 0
    ).all()
    account_stats = []
    for a in accounts:
        cnt = db.query(ContentAsset).filter(
            ContentAsset.industry_id == industry_id,
            ContentAsset.account_id == a.id,
            ContentAsset.is_deleted == 0
        ).count()
        p = db.query(Platform).filter(Platform.id == a.platform_id).first()
        account_stats.append({
            "id": a.id, "name": a.account_name,
            "platform": p.name if p else "", "count": cnt
        })
    account_stats.sort(key=lambda x: -x["count"])

    return {
        "code": 0,
        "data": {
            "total_content": total_content,
            "pass_content": pass_content,
            "pass_rate": pass_rate,
            "total_effect": total_effect,
            "brand_rate": brand_rate,
            "website_rate": website_rate,
            "contact_rate": contact_rate,
            "platform_stats": platform_stats,
            "account_stats": account_stats[:10],
        }
    }
