"""内容审核与资产管理路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import ContentAsset, Topic, Platform, Account, Keyword, KnowledgeItem
from ..utils import to_dict, parse_ids, parse_datetime
from ..services.rule_checker import run_full_check

router = APIRouter(prefix="/api/content", tags=["内容审核/资产"])


class ContentIn(BaseModel):
    industry_id: int
    topic_id: Optional[int] = None
    prompt_log_id: Optional[int] = None
    platform_id: Optional[int] = None
    account_id: Optional[int] = None
    title: str = ""
    content: str = ""
    tags: str = ""


class ReviewIn(BaseModel):
    review_status: str  # pass / reject
    reject_reason: str = ""


class PublishIn(BaseModel):
    publish_status: str  # published / offline
    publish_url: str = ""
    publish_time: Optional[str] = None


@router.get("")
def list_contents(industry_id: int, review_status: Optional[str] = None,
                  publish_status: Optional[str] = None, platform_id: Optional[int] = None,
                  keyword: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(ContentAsset).filter(
        ContentAsset.industry_id == industry_id,
        ContentAsset.is_deleted == 0
    )
    if review_status:
        q = q.filter(ContentAsset.review_status == review_status)
    if publish_status:
        q = q.filter(ContentAsset.publish_status == publish_status)
    if platform_id:
        q = q.filter(ContentAsset.platform_id == platform_id)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(ContentAsset.title.like(like) | ContentAsset.content.like(like))
    items = q.order_by(ContentAsset.id.desc()).all()
    return {"code": 0, "data": [to_dict(i) for i in items]}


@router.post("")
def create_content(payload: ContentIn, db: Session = Depends(get_db)):
    it = ContentAsset(**payload.dict(), review_status="pending", publish_status="pending")
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/{item_id}")
def update_content(item_id: int, payload: ContentIn, db: Session = Depends(get_db)):
    it = db.query(ContentAsset).filter(ContentAsset.id == item_id).first()
    if not it:
        raise HTTPException(404, "内容不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/{item_id}")
def delete_content(item_id: int, db: Session = Depends(get_db)):
    it = db.query(ContentAsset).filter(ContentAsset.id == item_id).first()
    if not it:
        raise HTTPException(404, "内容不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.get("/{item_id}/check")
def check_content(item_id: int, db: Session = Depends(get_db)):
    """本地初检：合规/AI SEO/去AI味/格式"""
    it = db.query(ContentAsset).filter(ContentAsset.id == item_id).first()
    if not it:
        raise HTTPException(404, "内容不存在")
    platform = db.query(Platform).filter(Platform.id == it.platform_id).first() if it.platform_id else None
    keywords = []
    if it.topic_id:
        topic = db.query(Topic).filter(Topic.id == it.topic_id).first()
        if topic and topic.keyword_id_list:
            kw_ids = parse_ids(topic.keyword_id_list)
            keywords = [k.word for k in db.query(Keyword).filter(Keyword.id.in_(kw_ids)).all()]
    # 注意：run_full_check 的签名为 (text, keywords, brand_info, word_min, word_max, platform_compliance_level)
    # 早期代码误传了 brand_name/website/contact 三个不存在的关键字，导致接口 500。
    # ContentAsset 本身不带品牌字段，brand_info 传 None 即可（规则校验会跳过品牌实体检查）。
    result = run_full_check(
        text=it.content or "",
        keywords=keywords,
        brand_info=None,
        word_min=platform.word_count_min if platform else 800,
        word_max=platform.word_count_max if platform else 1500,
        platform_compliance_level=platform.compliance_level if platform else 2,
    )
    return {"code": 0, "data": result}


@router.post("/{item_id}/review")
def review_content(item_id: int, payload: ReviewIn, db: Session = Depends(get_db)):
    it = db.query(ContentAsset).filter(ContentAsset.id == item_id).first()
    if not it:
        raise HTTPException(404, "内容不存在")
    it.review_status = payload.review_status
    it.reject_reason = payload.reject_reason
    db.commit()
    return {"code": 0, "msg": "审核状态已更新"}


@router.post("/{item_id}/publish")
def publish_content(item_id: int, payload: PublishIn, db: Session = Depends(get_db)):
    it = db.query(ContentAsset).filter(ContentAsset.id == item_id).first()
    if not it:
        raise HTTPException(404, "内容不存在")
    it.publish_status = payload.publish_status
    it.publish_url = payload.publish_url
    if payload.publish_time:
        # publish_time 列是 DateTime，必须转成 datetime 对象
        dt = parse_datetime(payload.publish_time)
        if dt is None:
            raise HTTPException(400, "发布时间格式不正确，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")
        it.publish_time = dt
    db.commit()
    return {"code": 0, "msg": "发布状态已更新"}


@router.get("/similarity")
def check_similarity(item_id: int, db: Session = Depends(get_db)):
    """本地相似度检测：基于关键词重合度"""
    it = db.query(ContentAsset).filter(ContentAsset.id == item_id).first()
    if not it:
        raise HTTPException(404, "内容不存在")
    def tokenize(text):
        text = text or ""
        return set(text[i:i+2] for i in range(len(text)-1))

    target_tokens = tokenize(it.content)
    same_platform = db.query(ContentAsset).filter(
        ContentAsset.platform_id == it.platform_id,
        ContentAsset.id != item_id,
        ContentAsset.is_deleted == 0
    ).all()
    result = []
    for s in same_platform:
        s_tokens = tokenize(s.content)
        if not s_tokens:
            continue
        overlap = len(target_tokens & s_tokens) / max(len(target_tokens | s_tokens), 1)
        if overlap > 0.3:
            result.append({
                "id": s.id,
                "title": s.title,
                "similarity": round(overlap * 100, 1)
            })
    result.sort(key=lambda x: -x["similarity"])
    return {"code": 0, "data": result[:10]}
