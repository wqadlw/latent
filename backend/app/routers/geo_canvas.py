"""GEO 定位画布（三环定位法可视化）

把分散在「客户画像 / 意图问题库 / 品牌资产库」三处的数据，按文章提出的
"三环定位法"——细分人群 × 特定问题 × 独特优势——交叉聚合，帮助快速找到
"哪类客户、问什么问题时、AI 应该推荐我们"的精准定位点。

这是展示层聚合，不新增数据表；所有数据来自已有三张表。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models import TargetPersona, IntentQuestion, BrandAsset
from ..utils import to_dict

router = APIRouter(prefix="/api/geo-canvas", tags=["GEO-定位画布"])


def _split_lines(s: str) -> List[str]:
    if not s:
        return []
    return [x.strip() for x in str(s).split("\n") if x.strip()]


@router.get("")
def geo_canvas(industry_id: int, db: Session = Depends(get_db)):
    """聚合 GEO 定位所需的画像 / 意图问题 / 品牌资产，并给出交叉洞察。"""
    personas = db.query(TargetPersona).filter(
        TargetPersona.industry_id == industry_id,
        TargetPersona.is_deleted == 0,
    ).order_by(TargetPersona.sort.asc(), TargetPersona.id.asc()).all()

    questions = db.query(IntentQuestion).filter(
        IntentQuestion.industry_id == industry_id,
        IntentQuestion.is_deleted == 0,
    ).order_by(IntentQuestion.priority.desc(), IntentQuestion.id.asc()).all()

    brands = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id,
        BrandAsset.is_deleted == 0,
    ).order_by(BrandAsset.is_default.desc(), BrandAsset.sort.asc(), BrandAsset.id.asc()).all()

    # 画像 → 意图问题 分组
    personas_out = []
    for p in personas:
        d = to_dict(p)
        d["pain_points"] = _split_lines(p.pain_points)
        d["cares_about"] = _split_lines(p.cares_about)
        d["questions"] = []
        personas_out.append(d)
    persona_map = {p["id"]: p for p in personas_out}

    orphan_questions = []
    for q in questions:
        qd = to_dict(q)
        pid = q.persona_id
        if pid and pid in persona_map:
            persona_map[pid]["questions"].append(qd)
        else:
            orphan_questions.append(qd)

    # 品牌资产（去重长度）
    brands_out = []
    for b in brands:
        d = to_dict(b)
        d["core_products_list"] = _split_lines(b.core_products)
        d["usp_list"] = _split_lines(b.unique_selling_points)
        d["target_keywords_list"] = _split_lines(b.target_keywords)
        brands_out.append(d)

    # 交叉洞察
    personas_with_q = sum(1 for p in personas_out if p["questions"])
    covered = sum(1 for q in questions if q.coverage_status == "covered")
    gap_q = [q for q in questions if q.coverage_status == "gap"]
    persona_without_q = [p for p in personas_out if not p["questions"]]

    insights = {
        "persona_count": len(personas_out),
        "question_count": len(questions),
        "brand_count": len(brands_out),
        "personas_with_question": personas_with_q,
        "personas_without_question": [p["name"] for p in persona_without_q],
        "covered_count": covered,
        "gap_count": len(gap_q),
        "orphan_question_count": len(orphan_questions),
        "has_brand": any((b.brand_name or "").strip() for b in brands),
    }

    # 给前端生成"定位点"建议：画像 × 高优先级问题，且标注是否已覆盖、品牌是否就绪
    positioning_points = []
    for p in personas_out:
        for q in p["questions"]:
            positioning_points.append({
                "persona_id": p["id"],
                "persona_name": p["name"],
                "persona_role": p["role_type"],
                "question_id": q["id"],
                "question": q["question"],
                "intent_category": q["intent_category"],
                "expected_recommendation": q["expected_recommendation"],
                "priority": q["priority"],
                "coverage_status": q["coverage_status"],
                "brand_ready": insights["has_brand"],
            })
    # 未关联画像的问题也作为孤立定位点
    for q in orphan_questions:
        positioning_points.append({
            "persona_id": 0,
            "persona_name": "未关联画像",
            "persona_role": "other",
            "question_id": q["id"],
            "question": q["question"],
            "intent_category": q["intent_category"],
            "expected_recommendation": q["expected_recommendation"],
            "priority": q["priority"],
            "coverage_status": q["coverage_status"],
            "brand_ready": insights["has_brand"],
        })

    return {"code": 0, "data": {
        "personas": personas_out,
        "brands": brands_out,
        "orphan_questions": orphan_questions,
        "positioning_points": positioning_points,
        "insights": insights,
    }}
