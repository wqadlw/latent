"""平台预设路由（含 7 大内容平台 + 官网/自建站）"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PLATFORM_PRESETS, Platform
from ..services.prompt_engine import OFFICIAL_MDX_PROMPT

router = APIRouter(prefix="/api/platform-presets", tags=["平台预设"])


@router.get("")
def list_presets():
    return {"code": 0, "data": PLATFORM_PRESETS}


@router.post("/seed/{industry_id}")
def seed_platforms(industry_id: int, db: Session = Depends(get_db)):
    existing = db.query(Platform).filter(
        Platform.industry_id == industry_id,
        Platform.is_deleted == 0,
    ).count()
    if existing > 0:
        return {"code": 0, "msg": f"该行业已有 {existing} 个平台，跳过灌入", "data": {"created": 0}}

    created = 0
    for idx, preset in enumerate(PLATFORM_PRESETS):
        # 官网/自建站：output_format=mdx，publish_prompt 注入官网 MDX 模板
        _is_official = preset["name"] == "官网/自建站"
        p = Platform(
            industry_id=industry_id,
            name=preset["name"],
            word_count_min=preset["word_count_min"],
            word_count_max=preset["word_count_max"],
            compliance_level=preset["compliance_level"],
            config=preset["config"],
            characteristics=preset.get("characteristics", ""),
            rules=preset.get("rules", ""),
            publish_mode=preset.get("publish_mode", "geo"),
            output_format=preset.get("output_format", "markdown"),
            site_url=preset.get("site_url", ""),
            publish_prompt=OFFICIAL_MDX_PROMPT if _is_official else "",
            sort=idx,
        )
        db.add(p)
        created += 1
    db.commit()
    return {"code": 0, "msg": f"已灌入 {created} 个平台预设", "data": {"created": created}}
