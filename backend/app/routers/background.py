"""背景库路由

功能：
- 把一个行业的「品牌资产 + 知识库」整理成一份可一键复制、投喂给任意 AI 的背景资料。
- 硬性背景(hard_background)由系统结合当前知识库内容生成、用户可编辑；其余知识点/品牌可按需增删。
- 支持「有选择地复制背景」：品牌资产可整体开关，知识点可按条目勾选排除。
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import BackgroundLibrary, BrandAsset, KnowledgeCategory, KnowledgeItem, Industry

router = APIRouter(prefix="/api/background-library", tags=["背景库"])


# ========== 请求体 ==========
class BackgroundIn(BaseModel):
    industry_id: int
    hard_background: str = ""
    include_brand: int = 1
    excluded_item_ids: List[int] = []


# ========== 工具：生成硬性背景 ==========
def _default_brand(db: Session, industry_id: int):
    brand = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id,
        BrandAsset.is_default == 1,
        BrandAsset.is_deleted == 0,
    ).first()
    if not brand:
        brand = db.query(BrandAsset).filter(
            BrandAsset.industry_id == industry_id,
            BrandAsset.is_deleted == 0,
        ).first()
    return brand


def _build_hard_background(industry_id: int, db: Session) -> str:
    """结合当前品牌资产 + 知识库内容，生成一份可编辑的硬性背景叙述。"""
    industry = db.query(Industry).filter(Industry.id == industry_id).first()
    industry_name = industry.name if industry else ""
    brand = _default_brand(db, industry_id)

    brand_name = brand.brand_name if brand else ""
    slogan = brand.slogan if brand else ""
    website = brand.official_website if brand else ""
    story = brand.brand_story if brand else ""
    core = brand.core_products if brand else ""
    selling = brand.unique_selling_points if brand else ""

    # 知识点（已发布），按重要度+排序
    items = db.query(KnowledgeItem).filter(
        KnowledgeItem.industry_id == industry_id,
        KnowledgeItem.is_deleted == 0,
        KnowledgeItem.status == "published",
    ).order_by(
        (KnowledgeItem.importance == "high").desc(),
        KnowledgeItem.sort.asc(),
        KnowledgeItem.id.desc(),
    ).all()
    high_items = [it for it in items if it.importance == "high"]
    normal_items = [it for it in items if it.importance != "high"]

    # 分类骨架
    categories = db.query(KnowledgeCategory).filter(
        KnowledgeCategory.industry_id == industry_id,
        KnowledgeCategory.is_deleted == 0,
    ).order_by(KnowledgeCategory.sort.asc()).all()
    cat_lines = []
    cat_item_map = {}
    for c in categories:
        cat_items = [it for it in items if it.category_id == c.id]
        cat_item_map[c.id] = cat_items
        if cat_items:
            samples = "、".join(it.title for it in cat_items[:2])
            cat_lines.append(f"- {c.name}：{len(cat_items)} 条（如：{samples}）")
    if not cat_lines:
        cat_lines.append("- （暂无分类，请先在「知识点管理」中录入行业知识）")

    # 关键论据（高重要性，最多 18 条）
    claim_lines = []
    for it in high_items[:18]:
        summ = (it.summary or it.content or "").strip()
        if len(summ) > 160:
            summ = summ[:160] + "…"
        claim_lines.append(f"### {it.title}\n{summ}")

    L = []
    L.append("# 硬性背景（公司 / 品牌核心素材，供 AI 创作前通读）\n")
    L.append(f"> 本资料由系统结合「{industry_name or '当前行业'}」的知识库与品牌资产自动整理，可自由编辑。\n")
    L.append("## 一、公司与品牌定位")
    L.append(f"- 公司：{brand_name or '（待补充）'}")
    if slogan:
        L.append(f"- 定位语：{slogan}")
    if website:
        L.append(f"- 官网：{website}")
    if story:
        L.append(f"- 品牌故事：{story}")
    L.append("")
    L.append("## 二、核心产品与技术优势")
    L.append(f"- 核心产品：{core or '（待补充）'}")
    L.append(f"- 独特卖点：{selling or '（待补充）'}")
    L.append("")
    L.append("## 三、行业知识骨架（来自知识库分类）")
    L.append("完整条目见下方「知识库要点」，可按需勾选投喂：")
    L.extend(cat_lines)
    L.append("")
    L.append("## 四、关键论据（高重要性知识点）")
    if claim_lines:
        L.extend(claim_lines)
    else:
        L.append("- （暂无高重要性知识点，建议在知识库中标记关键论据）")
    L.append("")
    L.append("## 五、给 AI 的创作指引")
    L.append(
        "你现在是该公司的外部内容顾问。以上为本公司的真实背景资料，请据此创作，"
        "确保公司名、产品名、数据口径与上文一致；引用具体论据时优先使用「知识库要点」中的条目；"
        "不得编造未提及的资质、客户案例或数据。面向不同平台时，按平台语境调整语气，但事实底线不变。"
    )
    return "\n".join(L)


def _serialize_brand(brand) -> Optional[dict]:
    if not brand:
        return None
    return {
        "id": brand.id,
        "brand_name": brand.brand_name,
        "official_website": brand.official_website,
        "slogan": brand.slogan,
        "core_products": brand.core_products,
        "unique_selling_points": brand.unique_selling_points,
        "target_keywords": brand.target_keywords,
        "brand_story": brand.brand_story,
    }


# ========== 读取 ==========
@router.get("")
def get_background(industry_id: int, db: Session = Depends(get_db)):
    """获取背景库：返回硬性背景（空则自动生成默认）、品牌资产、分类+知识点（带 excluded 标记）。"""
    prof = db.query(BackgroundLibrary).filter(BackgroundLibrary.industry_id == industry_id).first()
    has_saved = prof is not None and (prof.hard_background or "").strip() != ""
    hard = prof.hard_background if (prof and prof.hard_background) else _build_hard_background(industry_id, db)
    include_brand = prof.include_brand if prof else 1
    excluded = []
    if prof and prof.excluded_item_ids:
        try:
            excluded = json.loads(prof.excluded_item_ids) or []
        except Exception:
            excluded = []
    excluded_set = set(excluded)

    brand = _default_brand(db, industry_id)

    categories = db.query(KnowledgeCategory).filter(
        KnowledgeCategory.industry_id == industry_id,
        KnowledgeCategory.is_deleted == 0,
    ).order_by(KnowledgeCategory.sort.asc()).all()
    items = db.query(KnowledgeItem).filter(
        KnowledgeItem.industry_id == industry_id,
        KnowledgeItem.is_deleted == 0,
        KnowledgeItem.status == "published",
    ).order_by(KnowledgeItem.sort.asc(), KnowledgeItem.id.desc()).all()

    cat_list = []
    for c in categories:
        c_items = [it for it in items if it.category_id == c.id]
        cat_list.append({
            "id": c.id,
            "name": c.name,
            "color": c.color,
            "items": [
                {
                    "id": it.id,
                    "title": it.title,
                    "summary": it.summary,
                    "content": it.content,
                    "importance": it.importance,
                    "source": it.source,
                    "excluded": it.id in excluded_set,
                }
                for it in c_items
            ],
        })
    # 未分类
    uncategorized = [it for it in items if it.category_id is None or it.category_id == 0]
    if uncategorized:
        cat_list.append({
            "id": 0,
            "name": "未分类",
            "color": "#94a3b8",
            "items": [
                {
                    "id": it.id,
                    "title": it.title,
                    "summary": it.summary,
                    "content": it.content,
                    "importance": it.importance,
                    "source": it.source,
                    "excluded": it.id in excluded_set,
                }
                for it in uncategorized
            ],
        })

    return {
        "code": 0,
        "data": {
            "industry_id": industry_id,
            "hard_background": hard,
            "has_saved": has_saved,
            "include_brand": include_brand,
            "excluded_item_ids": excluded,
            "brand": _serialize_brand(brand),
            "categories": cat_list,
        },
    }


# ========== 生成硬性背景（不落库） ==========
@router.post("/generate")
def generate_hard_background(payload: dict, db: Session = Depends(get_db)):
    industry_id = payload.get("industry_id")
    if not industry_id:
        raise HTTPException(400, "industry_id 必填")
    text = _build_hard_background(industry_id, db)
    return {"code": 0, "data": {"hard_background": text}}


# ========== 保存 ==========
@router.put("")
def save_background(payload: BackgroundIn, db: Session = Depends(get_db)):
    prof = db.query(BackgroundLibrary).filter(BackgroundLibrary.industry_id == payload.industry_id).first()
    excluded_json = json.dumps(payload.excluded_item_ids or [], ensure_ascii=False)
    if not prof:
        prof = BackgroundLibrary(industry_id=payload.industry_id)
        db.add(prof)
    prof.hard_background = payload.hard_background
    prof.include_brand = payload.include_brand
    prof.excluded_item_ids = excluded_json
    db.commit()
    db.refresh(prof)
    return {
        "code": 0,
        "msg": "已保存",
        "data": {
            "industry_id": prof.industry_id,
            "hard_background": prof.hard_background,
            "has_saved": bool((prof.hard_background or "").strip()),
            "include_brand": prof.include_brand,
            "excluded_item_ids": payload.excluded_item_ids or [],
        },
    }
