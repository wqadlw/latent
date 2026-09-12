"""平台、人设、账号管理路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import Platform, Persona, Account
from ..utils import to_dict

router = APIRouter(prefix="/api", tags=["平台/人设/账号"])


# ========== 平台 ==========
class PlatformIn(BaseModel):
    industry_id: int
    name: str
    word_count_min: int = 800
    word_count_max: int = 1500
    compliance_level: int = 2
    config: str = "{}"
    characteristics: str = ""
    rules: str = ""
    sort: int = 0


@router.get("/platform")
def list_platforms(industry_id: int, db: Session = Depends(get_db)):
    items = db.query(Platform).filter(
        Platform.industry_id == industry_id,
        Platform.is_deleted == 0
    ).order_by(Platform.sort.asc()).all()
    return {"code": 0, "data": [to_dict(i) for i in items]}


@router.post("/platform")
def create_platform(payload: PlatformIn, db: Session = Depends(get_db)):
    it = Platform(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/platform/{item_id}")
def update_platform(item_id: int, payload: PlatformIn, db: Session = Depends(get_db)):
    it = db.query(Platform).filter(Platform.id == item_id).first()
    if not it:
        raise HTTPException(404, "平台不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/platform/{item_id}")
def delete_platform(item_id: int, db: Session = Depends(get_db)):
    it = db.query(Platform).filter(Platform.id == item_id).first()
    if not it:
        raise HTTPException(404, "平台不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.post("/platform/sort")
def sort_platforms(items: List[dict], db: Session = Depends(get_db)):
    for i, it in enumerate(items):
        db.query(Platform).filter(Platform.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "排序已更新"}


# ========== 人设 ==========
class PersonaIn(BaseModel):
    industry_id: int
    name: str
    identity: str = ""
    tone_style: str = ""
    contact_rule: str = ""
    sort: int = 0


@router.get("/persona")
def list_personas(industry_id: int, db: Session = Depends(get_db)):
    items = db.query(Persona).filter(
        Persona.industry_id == industry_id,
        Persona.is_deleted == 0
    ).order_by(Persona.sort.asc()).all()
    return {"code": 0, "data": [to_dict(i) for i in items]}


@router.post("/persona")
def create_persona(payload: PersonaIn, db: Session = Depends(get_db)):
    it = Persona(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/persona/{item_id}")
def update_persona(item_id: int, payload: PersonaIn, db: Session = Depends(get_db)):
    it = db.query(Persona).filter(Persona.id == item_id).first()
    if not it:
        raise HTTPException(404, "人设不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/persona/{item_id}")
def delete_persona(item_id: int, db: Session = Depends(get_db)):
    it = db.query(Persona).filter(Persona.id == item_id).first()
    if not it:
        raise HTTPException(404, "人设不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


# ========== 账号 ==========
class AccountIn(BaseModel):
    industry_id: int
    platform_id: Optional[int] = None
    persona_id: Optional[int] = None
    account_name: str
    content_track: str = ""
    status: int = 1
    sort: int = 0


@router.get("/account")
def list_accounts(industry_id: int, platform_id: Optional[int] = None,
                  db: Session = Depends(get_db)):
    q = db.query(Account).filter(
        Account.industry_id == industry_id,
        Account.is_deleted == 0
    )
    if platform_id:
        q = q.filter(Account.platform_id == platform_id)
    items = q.order_by(Account.sort.asc()).all()
    result = []
    for a in items:
        d = to_dict(a)
        p = db.query(Platform).filter(Platform.id == a.platform_id).first()
        d["platform_name"] = p.name if p else ""
        result.append(d)
    return {"code": 0, "data": result}


@router.post("/account")
def create_account(payload: AccountIn, db: Session = Depends(get_db)):
    it = Account(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/account/{item_id}")
def update_account(item_id: int, payload: AccountIn, db: Session = Depends(get_db)):
    it = db.query(Account).filter(Account.id == item_id).first()
    if not it:
        raise HTTPException(404, "账号不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/account/{item_id}")
def delete_account(item_id: int, db: Session = Depends(get_db)):
    it = db.query(Account).filter(Account.id == item_id).first()
    if not it:
        raise HTTPException(404, "账号不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.patch("/account/{item_id}/status")
def toggle_account_status(item_id: int, status: int = 1, db: Session = Depends(get_db)):
    it = db.query(Account).filter(Account.id == item_id).first()
    if not it:
        raise HTTPException(404, "账号不存在")
    it.status = status
    db.commit()
    return {"code": 0, "msg": "状态已更新"}


@router.post("/account/sort")
def sort_accounts(items: List[dict], db: Session = Depends(get_db)):
    for i, it in enumerate(items):
        db.query(Account).filter(Account.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "排序已更新"}
