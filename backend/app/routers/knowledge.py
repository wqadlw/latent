"""知识库管理路由 - v4 增强版

新增功能：
- 分类支持图标/颜色/描述
- 知识点支持摘要/来源/重要性/状态/查看次数
- 统计接口（按分类、按重要性、按状态分组）
- 导出接口（JSON/CSV）
- 详情接口（含查看次数自增）
- 分组列表接口（按分类分组，供生产第4步使用）
- 批量导入支持新字段
"""
import csv
import io
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import KnowledgeCategory, KnowledgeItem
from ..utils import to_dict

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])


# ========== 分类 ==========
class CategoryIn(BaseModel):
    industry_id: int
    name: str
    icon: str = "Folder"
    color: str = "#6366f1"
    description: str = ""
    sort: int = 0


@router.get("/category")
def list_categories(industry_id: int, db: Session = Depends(get_db)):
    items = db.query(KnowledgeCategory).filter(
        KnowledgeCategory.industry_id == industry_id,
        KnowledgeCategory.is_deleted == 0
    ).order_by(KnowledgeCategory.sort.asc()).all()
    result = []
    for c in items:
        d = to_dict(c)
        d["item_count"] = db.query(KnowledgeItem).filter(
            KnowledgeItem.category_id == c.id,
            KnowledgeItem.is_deleted == 0
        ).count()
        result.append(d)
    return {"code": 0, "data": result}


@router.post("/category")
def create_category(payload: CategoryIn, db: Session = Depends(get_db)):
    it = KnowledgeCategory(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/category/{item_id}")
def update_category(item_id: int, payload: CategoryIn, db: Session = Depends(get_db)):
    it = db.query(KnowledgeCategory).filter(KnowledgeCategory.id == item_id).first()
    if not it:
        raise HTTPException(404, "分类不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/category/{item_id}")
def delete_category(item_id: int, db: Session = Depends(get_db)):
    it = db.query(KnowledgeCategory).filter(KnowledgeCategory.id == item_id).first()
    if not it:
        raise HTTPException(404, "分类不存在")
    it.is_deleted = 1
    # 将该分类下的知识点 category_id 置空（归为「未分类」）；不可置 0，否则违反外键约束
    db.query(KnowledgeItem).filter(KnowledgeItem.category_id == item_id).update({"category_id": None})
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.post("/category/sort")
def sort_categories(items: List[dict], db: Session = Depends(get_db)):
    for i, it in enumerate(items):
        db.query(KnowledgeCategory).filter(KnowledgeCategory.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "排序已更新"}


# ========== 知识点 ==========
class ItemIn(BaseModel):
    industry_id: int
    category_id: Optional[int] = None
    title: str
    summary: str = ""
    content: str = ""
    tags: str = ""
    source: str = ""
    importance: str = "normal"  # high/normal/low
    status: str = "published"  # draft/published
    sort: int = 0


@router.get("/item")
def list_items(industry_id: int, category_id: Optional[int] = None,
               keyword: Optional[str] = None, importance: Optional[str] = None,
               status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(KnowledgeItem).filter(
        KnowledgeItem.industry_id == industry_id,
        KnowledgeItem.is_deleted == 0
    )
    if category_id:
        q = q.filter(KnowledgeItem.category_id == category_id)
    if importance:
        q = q.filter(KnowledgeItem.importance == importance)
    if status:
        q = q.filter(KnowledgeItem.status == status)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            (KnowledgeItem.title.like(like)) |
            (KnowledgeItem.content.like(like)) |
            (KnowledgeItem.tags.like(like)) |
            (KnowledgeItem.summary.like(like))
        )
    items = q.order_by(KnowledgeItem.sort.asc(), KnowledgeItem.id.desc()).all()
    result = []
    for it in items:
        d = to_dict(it)
        c = db.query(KnowledgeCategory).filter(KnowledgeCategory.id == it.category_id).first()
        d["category_name"] = c.name if c else "未分类"
        d["category_color"] = c.color if c else "#94a3b8"
        result.append(d)
    return {"code": 0, "data": result}


@router.get("/item/grouped")
def list_items_grouped(industry_id: int, keyword: Optional[str] = None, db: Session = Depends(get_db)):
    """按分类分组返回知识点列表，方便在生产第4步按分类浏览选择"""
    q = db.query(KnowledgeItem).filter(
        KnowledgeItem.industry_id == industry_id,
        KnowledgeItem.is_deleted == 0,
        KnowledgeItem.status == "published",
    )
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            (KnowledgeItem.title.like(like)) |
            (KnowledgeItem.content.like(like)) |
            (KnowledgeItem.tags.like(like)) |
            (KnowledgeItem.summary.like(like))
        )
    items = q.order_by(KnowledgeItem.sort.asc(), KnowledgeItem.id.desc()).all()

    # 查所有分类
    categories = db.query(KnowledgeCategory).filter(
        KnowledgeCategory.industry_id == industry_id,
        KnowledgeCategory.is_deleted == 0
    ).order_by(KnowledgeCategory.sort.asc()).all()

    # 按分类分组
    groups = []
    for c in categories:
        group_items = [it for it in items if it.category_id == c.id]
        groups.append({
            "category_id": c.id,
            "category_name": c.name,
            "category_color": c.color,
            "category_icon": c.icon,
            "items": [to_dict(it) for it in group_items],
        })
    # 未分类
    uncategorized = [it for it in items if it.category_id == 0 or it.category_id is None]
    if uncategorized:
        groups.append({
            "category_id": 0,
            "category_name": "未分类",
            "category_color": "#94a3b8",
            "category_icon": "Folder",
            "items": [to_dict(it) for it in uncategorized],
        })

    return {"code": 0, "data": groups}


@router.get("/item/search")
def search_items(industry_id: int, keyword: str, limit: int = 20, db: Session = Depends(get_db)):
    """快速搜索知识点（标题+内容+标签+摘要）"""
    like = f"%{keyword}%"
    items = db.query(KnowledgeItem).filter(
        KnowledgeItem.industry_id == industry_id,
        KnowledgeItem.is_deleted == 0,
        (KnowledgeItem.title.like(like)) |
        (KnowledgeItem.content.like(like)) |
        (KnowledgeItem.tags.like(like)) |
        (KnowledgeItem.summary.like(like)),
    ).order_by(KnowledgeItem.sort.asc()).limit(limit).all()
    result = []
    for it in items:
        d = to_dict(it)
        c = db.query(KnowledgeCategory).filter(KnowledgeCategory.id == it.category_id).first()
        d["category_name"] = c.name if c else "未分类"
        d["category_color"] = c.color if c else "#94a3b8"
        result.append(d)
    return {"code": 0, "data": result}


@router.get("/item/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)):
    """获取知识点详情（同时自增查看次数）"""
    it = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if not it:
        raise HTTPException(404, "知识点不存在")
    it.view_count = (it.view_count or 0) + 1
    db.commit()
    d = to_dict(it)
    c = db.query(KnowledgeCategory).filter(KnowledgeCategory.id == it.category_id).first()
    d["category_name"] = c.name if c else "未分类"
    d["category_color"] = c.color if c else "#94a3b8"
    return {"code": 0, "data": d}


@router.post("/item")
def create_item(payload: ItemIn, db: Session = Depends(get_db)):
    it = KnowledgeItem(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/item/{item_id}")
def update_item(item_id: int, payload: ItemIn, db: Session = Depends(get_db)):
    it = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if not it:
        raise HTTPException(404, "知识点不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/item/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    it = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if not it:
        raise HTTPException(404, "知识点不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.post("/item/batch_move")
def batch_move_items(payload: dict, db: Session = Depends(get_db)):
    ids = payload.get("ids", [])
    category_id = payload.get("category_id")
    db.query(KnowledgeItem).filter(KnowledgeItem.id.in_(ids)).update({"category_id": category_id})
    db.commit()
    return {"code": 0, "msg": f"已移动 {len(ids)} 条"}


@router.post("/item/batch_delete")
def batch_delete_items(payload: dict, db: Session = Depends(get_db)):
    ids = payload.get("ids", [])
    db.query(KnowledgeItem).filter(KnowledgeItem.id.in_(ids)).update({"is_deleted": 1})
    db.commit()
    return {"code": 0, "msg": f"已删除 {len(ids)} 条"}


@router.post("/item/batch_status")
def batch_update_status(payload: dict, db: Session = Depends(get_db)):
    """批量更新状态/重要性"""
    ids = payload.get("ids", [])
    field = payload.get("field")  # status / importance
    value = payload.get("value")
    if field not in ("status", "importance"):
        raise HTTPException(400, "field 只能是 status 或 importance")
    db.query(KnowledgeItem).filter(KnowledgeItem.id.in_(ids)).update({field: value})
    db.commit()
    return {"code": 0, "msg": f"已更新 {len(ids)} 条"}


@router.post("/item/sort")
def sort_items(items: List[dict], db: Session = Depends(get_db)):
    for i, it in enumerate(items):
        db.query(KnowledgeItem).filter(KnowledgeItem.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "排序已更新"}


# ========== 批量导入 ==========
@router.post("/item/batch")
def batch_import_items(payload: dict, db: Session = Depends(get_db)):
    """批量导入知识点

    支持两种格式:
    1. text 模式: 每行一个知识点，格式 "标题:内容" 或 "标题|内容"
    2. json 模式: [{"title": "xxx", "content": "xxx", "tags": "xxx", "summary": "xxx", "source": "xxx", "importance": "normal"}, ...]
    """
    industry_id = payload.get("industry_id")
    category_id = payload.get("category_id")
    mode = payload.get("mode", "text")  # text / json
    data = payload.get("data", "")

    if not industry_id:
        raise HTTPException(400, "industry_id 必填")

    created = 0
    errors = []

    if mode == "json":
        # JSON 数组模式
        items_data = data if isinstance(data, list) else []
        for i, item in enumerate(items_data):
            title = (item.get("title") or "").strip()
            content = (item.get("content") or "").strip()
            tags = (item.get("tags") or "").strip()
            summary = (item.get("summary") or "").strip()
            source = (item.get("source") or "").strip()
            importance = (item.get("importance") or "normal").strip()
            if not title:
                errors.append(f"第{i+1}条: 标题为空")
                continue
            it = KnowledgeItem(
                industry_id=industry_id,
                category_id=category_id,
                title=title,
                content=content,
                tags=tags,
                summary=summary,
                source=source,
                importance=importance,
                sort=i,
            )
            db.add(it)
            created += 1
    else:
        # 文本模式: 每行一个，用 : 或 | 分隔标题和内容
        lines = data.strip().split("\n") if data else []
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            # 支持 "标题:内容" 或 "标题|内容" 或 "标题::内容"
            title = ""
            content = ""
            for sep in ["::", ":", "|", "：", "｜"]:
                if sep in line:
                    parts = line.split(sep, 1)
                    title = parts[0].strip()
                    content = parts[1].strip()
                    break
            if not title:
                title = line
                content = ""
            it = KnowledgeItem(
                industry_id=industry_id,
                category_id=category_id,
                title=title,
                content=content,
                sort=i,
            )
            db.add(it)
            created += 1

    db.commit()
    return {
        "code": 0,
        "msg": f"成功导入 {created} 条知识点" + (f"，{len(errors)} 条失败" if errors else ""),
        "data": {"created": created, "errors": errors},
    }


# ========== 一键灌入可引用论据默认模板 ==========
# GEO 双信任的关键原料库：每条都是 claim + evidence + source 结构（示例占位，请替换为贵司真实数据）
_DEFAULT_KNOWLEDGE_CATEGORY = "GEO 可引用论据（默认）"
_DEFAULT_KNOWLEDGE_ITEMS = [
    {
        "title": "（示例）核心产品关键性能基准",
        "content": "示例条目：请替换为贵司真实数据。例如「[核心产品] 在典型工况下 [关键指标] 可达 [数值+单位]，优于行业平均 [数值]」。",
        "summary": "可量化性能基准，便于 AI 直接引用",
        "tags": "示例,性能,数据,GEO",
        "source": "（请填写：官方案例 / 第三方检测报告 / 客户实证）",
        "importance": "high",
    },
    {
        "title": "（示例）典型客户应用场景与收益",
        "content": "示例条目：描述一个真实但可模糊化的客户场景，如「某 [行业] 客户在 [场景] 中使用 [产品]，将 [指标] 从 X 优化到 Y」。",
        "summary": "客户实证场景，增强可归属证据",
        "tags": "示例,案例,客户,GEO",
        "source": "（请填写：客户授权案例 / 项目复盘）",
        "importance": "high",
    },
    {
        "title": "（示例）行业常见误区与正确做法",
        "content": "示例条目：列出 1-2 个客户常踩的坑，并给出客观正确做法，作为「专家可信」的证据。",
        "summary": "行业误区，建立专家权威",
        "tags": "示例,误区,专业,GEO",
        "source": "（内部经验 / 行业共识）",
        "importance": "normal",
    },
    {
        "title": "（示例）资质 / 标准 / 认证",
        "content": "示例条目：列出贵司相关资质、参与标准、专利等硬信任素材（务必真实可核验）。",
        "summary": "硬信任素材，AI 引用的凭据",
        "tags": "示例,资质,认证,GEO",
        "source": "（请填写：证书编号 / 发证机构）",
        "importance": "high",
    },
    {
        "title": "（示例）售后 / 质保 / 交付承诺",
        "content": "示例条目：用可量化口径写清质保周期、交付周期、响应时效，作为「敢承诺」的信任证据。",
        "summary": "服务承诺，降低决策风险感",
        "tags": "示例,售后,质保,GEO",
        "source": "（内部服务标准）",
        "importance": "normal",
    },
]


@router.post("/seed/{industry_id}")
def seed_default_knowledge(industry_id: int, db: Session = Depends(get_db)):
    """一键灌入「可引用论据库」默认模板：建默认分类并灌入 claim+evidence+source 示例条目（按标题去重）"""
    cat = db.query(KnowledgeCategory).filter(
        KnowledgeCategory.industry_id == industry_id,
        KnowledgeCategory.name == _DEFAULT_KNOWLEDGE_CATEGORY,
        KnowledgeCategory.is_deleted == 0,
    ).first()
    if not cat:
        max_sort = db.query(KnowledgeCategory).filter(
            KnowledgeCategory.industry_id == industry_id,
            KnowledgeCategory.is_deleted == 0,
        ).count()
        cat = KnowledgeCategory(
            industry_id=industry_id,
            name=_DEFAULT_KNOWLEDGE_CATEGORY,
            color="#14b8a6",
            icon="Quote",
            description="GEO 作战默认论据库：claim + evidence + source，供提示词模板引用",
            sort=max_sort,
        )
        db.add(cat)
        db.commit()
        db.refresh(cat)

    created = 0
    for i, item in enumerate(_DEFAULT_KNOWLEDGE_ITEMS):
        title = (item.get("title") or "").strip()
        if not title:
            continue
        existing = db.query(KnowledgeItem).filter(
            KnowledgeItem.industry_id == industry_id,
            KnowledgeItem.category_id == cat.id,
            KnowledgeItem.title == title,
            KnowledgeItem.is_deleted == 0,
        ).first()
        if existing:
            continue
        db.add(KnowledgeItem(
            industry_id=industry_id,
            category_id=cat.id,
            title=title,
            content=item.get("content", ""),
            summary=item.get("summary", ""),
            tags=item.get("tags", ""),
            source=item.get("source", ""),
            importance=item.get("importance", "normal"),
            sort=i,
        ))
        created += 1
    db.commit()
    msg = f"已灌入 {created} 条可引用论据（分类：{_DEFAULT_KNOWLEDGE_CATEGORY}）"
    return {"code": 0, "msg": msg, "data": {"created": created, "category_id": cat.id}}


# ========== 内联创建分类（快速创建） ==========
@router.post("/category/quick")
def quick_create_category(payload: dict, db: Session = Depends(get_db)):
    """快速创建分类，返回新分类ID（用于知识点编辑时内联创建）"""
    industry_id = payload.get("industry_id")
    name = (payload.get("name") or "").strip()
    color = payload.get("color") or "#6366f1"
    icon = payload.get("icon") or "Folder"
    if not industry_id or not name:
        raise HTTPException(400, "industry_id 和 name 必填")
    # 检查重名
    existing = db.query(KnowledgeCategory).filter(
        KnowledgeCategory.industry_id == industry_id,
        KnowledgeCategory.name == name,
        KnowledgeCategory.is_deleted == 0,
    ).first()
    if existing:
        return {"code": 0, "data": to_dict(existing), "msg": "分类已存在"}
    max_sort = db.query(KnowledgeCategory).filter(
        KnowledgeCategory.industry_id == industry_id,
        KnowledgeCategory.is_deleted == 0,
    ).count()
    it = KnowledgeCategory(
        industry_id=industry_id,
        name=name,
        color=color,
        icon=icon,
        sort=max_sort,
    )
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


# ========== v4 新增：统计接口 ==========
@router.get("/stats")
def get_stats(industry_id: int, db: Session = Depends(get_db)):
    """知识库统计：总数、按分类、按重要性、按状态"""
    base_q = db.query(KnowledgeItem).filter(
        KnowledgeItem.industry_id == industry_id,
        KnowledgeItem.is_deleted == 0
    )
    total = base_q.count()

    # 按分类
    categories = db.query(KnowledgeCategory).filter(
        KnowledgeCategory.industry_id == industry_id,
        KnowledgeCategory.is_deleted == 0
    ).order_by(KnowledgeCategory.sort.asc()).all()
    by_category = []
    for c in categories:
        cnt = base_q.filter(KnowledgeItem.category_id == c.id).count()
        by_category.append({"id": c.id, "name": c.name, "color": c.color, "count": cnt})
    uncategorized = base_q.filter(
        (KnowledgeItem.category_id == 0) | (KnowledgeItem.category_id.is_(None))
    ).count()
    by_category.append({"id": 0, "name": "未分类", "color": "#94a3b8", "count": uncategorized})

    # 按重要性
    by_importance = {
        "high": base_q.filter(KnowledgeItem.importance == "high").count(),
        "normal": base_q.filter(KnowledgeItem.importance == "normal").count(),
        "low": base_q.filter(KnowledgeItem.importance == "low").count(),
    }

    # 按状态
    by_status = {
        "published": base_q.filter(KnowledgeItem.status == "published").count(),
        "draft": base_q.filter(KnowledgeItem.status == "draft").count(),
    }

    # 最近添加
    recent = base_q.order_by(KnowledgeItem.id.desc()).limit(5).all()
    recent_list = []
    for it in recent:
        d = {"id": it.id, "title": it.title, "summary": it.summary, "update_time": str(it.update_time) if it.update_time else ""}
        recent_list.append(d)

    return {
        "code": 0,
        "data": {
            "total": total,
            "categories": len(by_category),
            "by_category": by_category,
            "by_importance": by_importance,
            "by_status": by_status,
            "recent": recent_list,
        }
    }


# ========== v4 新增：导出接口 ==========
@router.get("/export")
def export_items(industry_id: int, fmt: str = "json", category_id: Optional[int] = None, db: Session = Depends(get_db)):
    """导出知识点为 JSON 或 CSV"""
    q = db.query(KnowledgeItem).filter(
        KnowledgeItem.industry_id == industry_id,
        KnowledgeItem.is_deleted == 0
    )
    if category_id:
        q = q.filter(KnowledgeItem.category_id == category_id)
    items = q.order_by(KnowledgeItem.sort.asc()).all()

    # 查分类映射
    categories = db.query(KnowledgeCategory).filter(
        KnowledgeCategory.industry_id == industry_id,
        KnowledgeCategory.is_deleted == 0
    ).all()
    cat_map = {c.id: c.name for c in categories}

    if fmt == "csv":
        output = io.StringIO()
        output.write("\ufeff")  # BOM for Excel
        writer = csv.writer(output)
        writer.writerow(["ID", "标题", "摘要", "分类", "内容", "标签", "来源", "重要性", "状态", "创建时间"])
        for it in items:
            writer.writerow([
                it.id, it.title, it.summary or "", cat_map.get(it.category_id, "未分类"),
                it.content or "", it.tags or "", it.source or "",
                it.importance or "normal", it.status or "published",
                str(it.create_time) if it.create_time else ""
            ])
        content = output.getvalue()
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=knowledge_items.csv"}
        )
    else:
        data = []
        for it in items:
            data.append({
                "title": it.title,
                "summary": it.summary or "",
                "content": it.content or "",
                "category": cat_map.get(it.category_id, "未分类"),
                "tags": it.tags or "",
                "source": it.source or "",
                "importance": it.importance or "normal",
                "status": it.status or "published",
            })
        content = json.dumps(data, ensure_ascii=False, indent=2)
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=knowledge_items.json"}
        )
