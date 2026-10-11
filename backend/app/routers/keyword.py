"""关键词与选题管理路由"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Account, Keyword, KeywordGroup, Platform, Topic
from ..utils import parse_date, parse_ids, to_dict

router = APIRouter(prefix="/api", tags=["关键词/选题"])


# ========== 关键词分组 ==========
class KeywordGroupIn(BaseModel):
    industry_id: int
    name: str
    color: str = "#6366f1"
    icon: str = "Collection"
    description: str = ""
    sort: int = 0


@router.get("/keyword-group")
def list_keyword_groups(industry_id: int, db: Session = Depends(get_db)):
    groups = db.query(KeywordGroup).filter(
        KeywordGroup.industry_id == industry_id,
        KeywordGroup.is_deleted == 0,
    ).order_by(KeywordGroup.sort.asc(), KeywordGroup.id.asc()).all()
    result = []
    for g in groups:
        d = to_dict(g)
        cnt = db.query(Keyword).filter(
            Keyword.group_id == g.id, Keyword.is_deleted == 0
        ).count()
        d["item_count"] = cnt
        result.append(d)
    return {"code": 0, "data": result}


@router.post("/keyword-group")
def create_keyword_group(payload: KeywordGroupIn, db: Session = Depends(get_db)):
    it = KeywordGroup(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "分组已创建"}


@router.put("/keyword-group/{item_id}")
def update_keyword_group(item_id: int, payload: KeywordGroupIn, db: Session = Depends(get_db)):
    it = db.query(KeywordGroup).filter(KeywordGroup.id == item_id).first()
    if not it:
        raise HTTPException(404, "分组不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "已更新"}


@router.delete("/keyword-group/{item_id}")
def delete_keyword_group(item_id: int, db: Session = Depends(get_db)):
    it = db.query(KeywordGroup).filter(KeywordGroup.id == item_id).first()
    if not it:
        raise HTTPException(404, "分组不存在")
    # 该分组下的关键词改为未分组
    db.query(Keyword).filter(Keyword.group_id == item_id).update({"group_id": None})
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.post("/keyword-group/sort")
def sort_keyword_groups(items: List[dict], db: Session = Depends(get_db)):
    """拖拽自定义排序：传有序的 [{id, sort}] 列表，重排分组顺序"""
    for i, it in enumerate(items):
        db.query(KeywordGroup).filter(KeywordGroup.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "分组排序已更新"}


# ========== 关键词 ==========
class KeywordIn(BaseModel):
    industry_id: int
    word: str
    group_id: Optional[int] = None
    type: str = "long_tail"  # brand/product/long_tail/question
    priority: int = 2
    related_product: str = ""
    tags: str = ""
    sort: int = 0


@router.get("/keyword")
def list_keywords(industry_id: int, type: Optional[str] = None,
                  group_id: Optional[int] = None, keyword: Optional[str] = None,
                  db: Session = Depends(get_db)):
    q = db.query(Keyword).filter(
        Keyword.industry_id == industry_id,
        Keyword.is_deleted == 0
    )
    if type:
        q = q.filter(Keyword.type == type)
    if group_id is not None:
        # group_id = -1 表示「未分组」
        if group_id == -1:
            q = q.filter(Keyword.group_id.is_(None))
        else:
            q = q.filter(Keyword.group_id == group_id)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            (Keyword.word.like(like)) |
            (Keyword.related_product.like(like)) |
            (Keyword.tags.like(like))
        )
    items = q.order_by(Keyword.priority.desc(), Keyword.sort.asc()).all()
    return {"code": 0, "data": [to_dict(i) for i in items]}


@router.post("/keyword")
def create_keyword(payload: KeywordIn, db: Session = Depends(get_db)):
    it = Keyword(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/keyword/{item_id}")
def update_keyword(item_id: int, payload: KeywordIn, db: Session = Depends(get_db)):
    it = db.query(Keyword).filter(Keyword.id == item_id).first()
    if not it:
        raise HTTPException(404, "关键词不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/keyword/{item_id}")
def delete_keyword(item_id: int, db: Session = Depends(get_db)):
    it = db.query(Keyword).filter(Keyword.id == item_id).first()
    if not it:
        raise HTTPException(404, "关键词不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.post("/keyword/sort")
def sort_keywords(items: List[dict], db: Session = Depends(get_db)):
    for i, it in enumerate(items):
        db.query(Keyword).filter(Keyword.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "排序已更新"}


@router.post("/keyword/batch_group")
def batch_update_group(payload: dict, db: Session = Depends(get_db)):
    """批量修改关键词所属分组（group_id 可传 null 表示设为未分组）"""
    ids = payload.get("ids", [])
    group_id = payload.get("group_id")
    if not ids:
        return {"code": 0, "msg": "未选择关键词"}
    db.query(Keyword).filter(Keyword.id.in_(ids)).update({"group_id": group_id})
    db.commit()
    return {"code": 0, "msg": f"已更新 {len(ids)} 个关键词的分组"}


@router.post("/keyword/batch_delete")
def batch_delete_keywords(payload: dict, db: Session = Depends(get_db)):
    """批量软删除关键词"""
    ids = payload.get("ids", [])
    if not ids:
        return {"code": 0, "msg": "未选择关键词"}
    db.query(Keyword).filter(Keyword.id.in_(ids)).update({"is_deleted": 1})
    db.commit()
    return {"code": 0, "msg": f"已删除 {len(ids)} 个关键词"}


# ========== 批量导入关键词 ==========
VALID_TYPES = ("brand", "product", "long_tail", "question")


class KeywordBatchItem(BaseModel):
    word: str
    type: Optional[str] = None
    priority: int = 2
    related_product: str = ""
    tags: str = ""
    group_id: Optional[int] = None      # 本条所属分组（覆盖批量默认 group_id）
    group_name: Optional[str] = None    # 按分组名自动建组并归入（与 group_id 二选一）


class KeywordBatchIn(BaseModel):
    industry_id: int
    default_type: str = "long_tail"
    group_id: Optional[int] = None      # 批量默认分组（导入到对应分组）
    items: List[KeywordBatchItem]


@router.post("/keyword/batch")
def batch_import_keywords(payload: KeywordBatchIn, db: Session = Depends(get_db)):
    """批量导入关键词，按 (industry_id, word) 去重，已存在则跳过。
    支持把整批或单条导入到指定分组（group_id / 按 group_name 自动建组）。"""
    ind = payload.industry_id
    default_type = payload.default_type if payload.default_type in VALID_TYPES else "long_tail"
    default_group = payload.group_id

    # 解析「按名称自动建组」：累计 name -> group_id
    _name_group_cache = {}
    def _resolve_group(name: Optional[str], item_group_id: Optional[int]):
        gid = item_group_id if item_group_id is not None else default_group
        if gid:
            return gid
        if name:
            if name in _name_group_cache:
                return _name_group_cache[name]
            g = db.query(KeywordGroup).filter(
                KeywordGroup.industry_id == ind, KeywordGroup.name == name,
                KeywordGroup.is_deleted == 0
            ).first()
            if not g:
                g = KeywordGroup(industry_id=ind, name=name, sort=0)
                db.add(g)
                db.flush()
            _name_group_cache[name] = g.id
            return g.id
        return None

    # 预取该行业已有词，便于去重
    existing = {
        w for (w,) in db.query(Keyword.word)
        .filter(Keyword.industry_id == ind, Keyword.is_deleted == 0)
        .all()
    }
    created = 0
    skipped = 0
    errors = []
    seen_in_batch = set()
    for i, it in enumerate(payload.items):
        word = (it.word or "").strip()
        if not word:
            errors.append(f"第{i+1}条: 关键词为空，已跳过")
            continue
        if word in existing or word in seen_in_batch:
            skipped += 1
            seen_in_batch.add(word)
            continue
        ktype = it.type if (it.type and it.type in VALID_TYPES) else default_type
        gid = _resolve_group(it.group_name, it.group_id)
        db.add(Keyword(
            industry_id=ind,
            group_id=gid,
            word=word,
            type=ktype,
            priority=it.priority if it.priority in (1, 2, 3) else 2,
            related_product=it.related_product or "",
            tags=it.tags or "",
            sort=created,
        ))
        existing.add(word)
        seen_in_batch.add(word)
        created += 1
    db.commit()
    msg = f"成功导入 {created} 条"
    if skipped:
        msg += f"，跳过重复 {skipped} 条"
    if errors:
        msg += f"，{len(errors)} 条有误"
    return {"code": 0, "msg": msg, "data": {"created": created, "skipped": skipped, "errors": errors}}


# ========== 选题 ==========
class TopicIn(BaseModel):
    industry_id: int
    platform_id: Optional[int] = None
    account_id: Optional[int] = None
    title: str
    keyword_id_list: str = ""
    plan_date: Optional[str] = None
    status: str = "pending"
    sort: int = 0


@router.get("/topic")
def list_topics(industry_id: int, platform_id: Optional[int] = None,
                account_id: Optional[int] = None, status: Optional[str] = None,
                db: Session = Depends(get_db)):
    q = db.query(Topic).filter(
        Topic.industry_id == industry_id,
        Topic.is_deleted == 0
    )
    if platform_id:
        q = q.filter(Topic.platform_id == platform_id)
    if account_id:
        q = q.filter(Topic.account_id == account_id)
    if status:
        q = q.filter(Topic.status == status)
    items = q.order_by(Topic.sort.asc(), Topic.plan_date.asc()).all()
    result = []
    for t in items:
        d = to_dict(t)
        p = db.query(Platform).filter(Platform.id == t.platform_id).first()
        a = db.query(Account).filter(Account.id == t.account_id).first()
        d["platform_name"] = p.name if p else ""
        d["account_name"] = a.account_name if a else ""
        kw_ids = parse_ids(t.keyword_id_list)
        kws = db.query(Keyword).filter(Keyword.id.in_(kw_ids)).all()
        d["keywords"] = [k.word for k in kws]
        result.append(d)
    return {"code": 0, "data": result}


@router.post("/topic")
def create_topic(payload: TopicIn, db: Session = Depends(get_db)):
    data = payload.dict()
    # plan_date 列是 Date，必须把字符串转成 date 对象
    data["plan_date"] = parse_date(data.get("plan_date"))
    it = Topic(**data)
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/topic/{item_id}")
def update_topic(item_id: int, payload: TopicIn, db: Session = Depends(get_db)):
    it = db.query(Topic).filter(Topic.id == item_id).first()
    if not it:
        raise HTTPException(404, "选题不存在")
    data = payload.dict()
    # plan_date 列是 Date，必须把字符串转成 date 对象
    data["plan_date"] = parse_date(data.get("plan_date"))
    for k, v in data.items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/topic/{item_id}")
def delete_topic(item_id: int, db: Session = Depends(get_db)):
    it = db.query(Topic).filter(Topic.id == item_id).first()
    if not it:
        raise HTTPException(404, "选题不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.get("/topic/matrix")
def topic_matrix(industry_id: int, db: Session = Depends(get_db)):
    platforms = db.query(Platform).filter(
        Platform.industry_id == industry_id, Platform.is_deleted == 0
    ).order_by(Platform.sort.asc()).all()
    matrix = []
    for p in platforms:
        accounts = db.query(Account).filter(
            Account.industry_id == industry_id,
            Account.platform_id == p.id,
            Account.is_deleted == 0
        ).order_by(Account.sort.asc()).all()
        acc_list = []
        for a in accounts:
            topics = db.query(Topic).filter(
                Topic.industry_id == industry_id,
                Topic.account_id == a.id,
                Topic.is_deleted == 0
            ).order_by(Topic.sort.asc(), Topic.plan_date.asc()).all()
            acc_list.append({
                "account": to_dict(a),
                "topics": [to_dict(t) for t in topics]
            })
        matrix.append({
            "platform": to_dict(p),
            "accounts": acc_list
        })
    return {"code": 0, "data": matrix}
