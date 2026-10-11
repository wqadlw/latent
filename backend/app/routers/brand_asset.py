"""品牌资产库路由"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BrandAsset
from ..utils import to_dict

router = APIRouter(prefix="/api/brand-asset", tags=["品牌资产库"])


class BrandIn(BaseModel):
    industry_id: int
    brand_name: str
    official_website: str = ""
    contact_phone: str = ""
    contact_wechat: str = ""
    contact_email: str = ""
    slogan: str = ""
    core_products: str = ""
    unique_selling_points: str = ""
    target_keywords: str = ""
    brand_story: str = ""
    is_default: int = 0
    sort: int = 0


@router.get("")
def list_assets(industry_id: int, db: Session = Depends(get_db)):
    items = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id,
        BrandAsset.is_deleted == 0,
    ).order_by(BrandAsset.is_default.desc(), BrandAsset.sort.asc()).all()
    return {"code": 0, "data": [to_dict(i) for i in items]}


@router.post("")
def create_asset(payload: BrandIn, db: Session = Depends(get_db)):
    it = BrandAsset(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/{item_id}")
def update_asset(item_id: int, payload: BrandIn, db: Session = Depends(get_db)):
    it = db.query(BrandAsset).filter(BrandAsset.id == item_id).first()
    if not it:
        raise HTTPException(404, "品牌资产不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/{item_id}")
def delete_asset(item_id: int, db: Session = Depends(get_db)):
    it = db.query(BrandAsset).filter(BrandAsset.id == item_id).first()
    if not it:
        raise HTTPException(404, "品牌资产不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "删除成功"}


@router.post("/{item_id}/default")
def set_default(item_id: int, db: Session = Depends(get_db)):
    item = db.query(BrandAsset).filter(BrandAsset.id == item_id, BrandAsset.is_deleted == 0).first()
    if not item:
        raise HTTPException(status_code=404, detail="品牌资产不存在")
    db.query(BrandAsset).filter(
        BrandAsset.industry_id == item.industry_id,
        BrandAsset.id != item_id,
    ).update({BrandAsset.is_default: 0})
    item.is_default = 1
    db.commit()
    return {"code": 0, "msg": "已设为默认品牌"}


@router.get("/default/{industry_id}")
def get_default(industry_id: int, db: Session = Depends(get_db)):
    item = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id,
        BrandAsset.is_default == 1,
        BrandAsset.is_deleted == 0,
    ).first()
    if not item:
        item = db.query(BrandAsset).filter(
            BrandAsset.industry_id == industry_id,
            BrandAsset.is_deleted == 0,
        ).order_by(BrandAsset.id.asc()).first()
    return {"code": 0, "data": to_dict(item) if item else None}
