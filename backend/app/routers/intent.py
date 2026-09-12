"""GEO 作战 - 目标画像与意图问题库（模块①）

目标：把"目标客户会向 AI 问什么"结构化下来，作为后续软文选题与 GEO 评分的基础。
- TargetPersona：目标客户画像（工厂老板 / 技术人员 / 采购人员…）
- IntentQuestion：目标客户会问 AI 的问题 + 期望 AI 推荐我们的角度

注意：Persona 已被"写作人设"占用，目标客户画像必须用 TargetPersona 避免冲突。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import json
from ..database import get_db
from ..models import TargetPersona, IntentQuestion, Industry, BrandAsset
from ..utils import to_dict

router = APIRouter(prefix="/api", tags=["GEO-画像与意图问题库"])

ROLE_TYPES = ("decision_maker", "technical", "procurement", "other")
INTENT_CATEGORIES = ("selection", "cost", "integration", "risk", "compliance", "other")
COVERAGE_STATUS = ("covered", "gap")
SOURCES = ("manual", "interview", "support", "search", "competitor")


# ============================================================
#  目标画像 TargetPersona
# ============================================================
class TargetPersonaIn(BaseModel):
    industry_id: int
    name: str
    role_type: str = "other"        # decision_maker/technical/procurement/other
    description: str = ""
    pain_points: str = ""           # 换行分隔
    cares_about: str = ""           # 换行分隔
    decision_weight: int = 2        # 1-3
    icon: str = "User"
    color: str = "#6366f1"
    sort: int = 0


@router.get("/target-persona")
def list_target_personas(industry_id: int, db: Session = Depends(get_db)):
    rows = db.query(TargetPersona).filter(
        TargetPersona.industry_id == industry_id,
        TargetPersona.is_deleted == 0,
    ).order_by(TargetPersona.sort.asc(), TargetPersona.id.asc()).all()
    result = []
    for p in rows:
        d = to_dict(p)
        cnt = db.query(IntentQuestion).filter(
            IntentQuestion.persona_id == p.id,
            IntentQuestion.is_deleted == 0,
        ).count()
        d["question_count"] = cnt
        result.append(d)
    return {"code": 0, "data": result}


@router.post("/target-persona")
def create_target_persona(payload: TargetPersonaIn, db: Session = Depends(get_db)):
    if payload.role_type not in ROLE_TYPES:
        payload.role_type = "other"
    if payload.decision_weight not in (1, 2, 3):
        payload.decision_weight = 2
    it = TargetPersona(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "画像已创建"}


@router.put("/target-persona/{item_id}")
def update_target_persona(item_id: int, payload: TargetPersonaIn, db: Session = Depends(get_db)):
    it = db.query(TargetPersona).filter(TargetPersona.id == item_id).first()
    if not it:
        raise HTTPException(404, "画像不存在")
    data = payload.dict()
    if data.get("role_type") not in ROLE_TYPES:
        data["role_type"] = "other"
    if data.get("decision_weight") not in (1, 2, 3):
        data["decision_weight"] = 2
    for k, v in data.items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "画像已更新"}


@router.delete("/target-persona/{item_id}")
def delete_target_persona(item_id: int, db: Session = Depends(get_db)):
    it = db.query(TargetPersona).filter(TargetPersona.id == item_id).first()
    if not it:
        raise HTTPException(404, "画像不存在")
    # 该画像下的问题改为"未关联画像"，避免悬空外键
    db.query(IntentQuestion).filter(IntentQuestion.persona_id == item_id).update({"persona_id": 0})
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "画像已删除"}


@router.post("/target-persona/sort")
def sort_target_personas(items: List[dict], db: Session = Depends(get_db)):
    for i, it in enumerate(items):
        db.query(TargetPersona).filter(TargetPersona.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "画像顺序已更新"}


# 默认画像种子（真空领域：真空设备/真空泵/真空镀膜/真空炉等目标客户）
# 站在真实购买决策链视角：决策层 / 技术层 / 采购层 / 运维 / 研发 / 质量，
# 痛点与关注点尽量具体到一线可感知的场景，而非泛泛而谈。
DEFAULT_PERSONAS = [
    {
        "name": "真空产线厂长", "role_type": "decision_maker", "decision_weight": 3,
        "icon": "OfficeBuilding", "color": "#6366f1",
        "description": "负责真空产线日常运营与生产指标的一线决策者，背 KPI（良率、产能、停机时长），对设备稳定性与回本周期最敏感。",
        "pain_points": "真空度波动直接导致整批产品良率不达标，返工亏钱\n系统能耗占车间电费大头，月底电费单看了头疼\n半夜突发停机，整线停摆，产损加加班抢修双重压力\n看不懂分子泵/罗茨泵参数表，被供应商牵着鼻子走\n招不到懂真空的运维，设备一坏就只能干等厂家",
        "cares_about": "投资回报与回本周期（多久能把设备钱赚回来）\n单位产品能耗与综合运维成本\n平均无故障时间（MTBF）与停机率\n同行业、同工艺的真空应用成功案例",
    },
    {
        "name": "真空工艺工程师", "role_type": "technical", "decision_weight": 2,
        "icon": "Cpu", "color": "#0ea5e9",
        "description": "负责真空工艺调试与设备选型的技术骨干，天天和极限真空度、漏率、抽速打交道，要算清工艺窗口。",
        "pain_points": "新工艺要求极限真空度，现有系统死活达不到\n漏率超标查一周查不出漏点，产线干等\n分子泵/罗茨泵/干泵到底怎么搭配，算不准抽速\n腔体、法兰、PLC 通讯协议对不上，集成拖进度\n工艺放大时本底真空变差，残余气体影响镀膜/焊接质量",
        "cares_about": "极限真空度与抽速等硬指标是否留足余量\n漏率检测方法与可接受的泄漏率标准\n泵组搭配口径、接口与通讯兼容性\n技术文档完整度、现场支持响应速度",
    },
    {
        "name": "真空设备采购", "role_type": "procurement", "decision_weight": 2,
        "icon": "ShoppingCart", "color": "#f59e0b",
        "description": "负责真空设备比价、招标、合同与交付的商务角色，要在预算、交期、质保之间找平衡，向上汇报风险。",
        "pain_points": "不同厂家参数口径不一，用同一张表根本比不了价\n报价水分大，主机/泵组/安装/备件拆得不清不楚\n交付和安装周期一拖再拖，影响产线投产节点\n质保和备件条款模糊，出事互相踢皮球\n领导只问价格和交期，不懂技术差异怎么控风险",
        "cares_about": "透明、可横向比价的报价结构\n明确的交付里程碑与安装调试周期\n质保年限、备件库存与 SLA 响应时效\n真空行业资质、业绩与可查证案例",
    },
    {
        "name": "真空技术研发总监", "role_type": "technical", "decision_weight": 3,
        "icon": "MagicStick", "color": "#8b5cf6",
        "description": "负责新产品导入与工艺路线的研发负责人，关注前沿真空方案能否支撑下一代产品，对技术先进性与可量产性双重把关。",
        "pain_points": "新产品要求更高本底真空，现有平台 hold 不住\n新工艺（如新型镀膜/烧结）找不到成熟真空方案\n进口设备交期长、被卡脖子，国产替代心里没底\n研发样机到量产，真空系统一致性上不去\n技术路线选型错，前期投入全打水漂",
        "cares_about": "方案的技术先进性与工艺窗口余量\n国产替代的可行性与可靠性证据\n从样机到量产的一致性与放大能力\n厂家联合开发能力与专利/标准参与情况",
    },
    {
        "name": "设备运维主管", "role_type": "other", "decision_weight": 2,
        "icon": "Tools", "color": "#10b981",
        "description": "负责真空设备日常点检、保养与故障抢修的运维负责人，最怕半夜被叫起来，也最清楚哪家售后真靠谱。",
        "pain_points": "设备一坏就停产，抢修全靠厂家远程，等不起\n备件库里没有关键件，进口货一订一个月\n日常保养没标准 SOP，全凭老师傅经验\n故障代码看不懂，排查靠猜\n厂家培训走过场，手下人还是不会修",
        "cares_about": "平均修复时间（MTTR）与现场响应速度\n常用备件供应与本地库存\n设备可维护性与保养 SOP 是否清晰\n厂家培训与远程诊断能力",
    },
    {
        "name": "工厂总经理 / 投资负责人", "role_type": "decision_maker", "decision_weight": 3,
        "icon": "Trophy", "color": "#ef4444",
        "description": "对整条产线资本开支拍板的人，关注总拥有成本（TCO）、战略契合与投产节奏，不被单一技术指标带节奏。",
        "pain_points": "设备报价只是冰山一角，后续能耗/备件/人工才是大头\n回本测算供应商给得太乐观，落地根本达不到\n多条产线要同步投，资金排期和投产节奏难协调\n选了便宜但不稳的方案，良率损失远超省下的钱\n老板只问什么时候能投产赚钱，技术细节难量化汇报",
        "cares_about": "总拥有成本（TCO）与真实回本周期\n产能爬坡节奏与投产节点\n方案的战略契合度与扩展性\n风险可控性（交期/良率/售后兜底）",
    },
    {
        "name": "质量 / 良率负责人", "role_type": "other", "decision_weight": 2,
        "icon": "Stamp", "color": "#0ea5e9",
        "description": "对产品良率与污染控制负责的质量角色，真空系统的洁净度与稳定性直接关系到客诉和报废。",
        "pain_points": "真空腔体残留气体导致镀膜/焊接出现针孔、气泡\n颗粒污染超标，客户验厂一票否决\n真空波动与批次良率波动强相关，难溯源\n新风系统/手套箱与真空系统耦合，污染链查不清\n客诉来了要出 8D，根因分析卡在真空环节",
        "cares_about": "本底真空与残余气体成分控制\n颗粒/污染控制与洁净度指标\n工艺稳定性与批次一致性\n污染溯源手段与质量体系对接",
    },
]


@router.post("/target-persona/seed/{industry_id}")
def seed_target_personas(industry_id: int, db: Session = Depends(get_db)):
    """为指定行业预置/刷新默认目标画像（按 industry_id+name upsert，不丢用户自建数据）。

    画像内容随行业不同：命中真空相关行业用真空领域预设，其余用通用 B2B 预设。
    """
    ind = db.query(Industry).filter(Industry.id == industry_id).first()
    personas, _ = resolve_industry_preset(ind.name if ind else "")
    created = updated = 0
    for i, p in enumerate(personas):
        exist = db.query(TargetPersona).filter(
            TargetPersona.industry_id == industry_id,
            TargetPersona.name == p["name"],
            TargetPersona.is_deleted == 0,
        ).first()
        if exist:
            for k, v in p.items():
                setattr(exist, k, v)
            exist.sort = i
            updated += 1
        else:
            db.add(TargetPersona(industry_id=industry_id, sort=i, **p))
            created += 1
    db.commit()
    return {"code": 0, "msg": f"已预置 {created} 个、刷新 {updated} 个默认画像", "data": {"created": created, "updated": updated}}


# ============================================================
#  意图问题 IntentQuestion
# ============================================================
class IntentQuestionIn(BaseModel):
    industry_id: int
    persona_id: int = 0
    question: str
    intent_category: str = "other"       # selection/cost/integration/risk/compliance/other
    expected_recommendation: str = ""
    priority: int = 2                    # 1-3
    coverage_status: str = "gap"         # covered/gap
    source: str = "manual"               # manual/interview/support/search/competitor
    sort: int = 0


@router.get("/intent-question")
def list_intent_questions(
    industry_id: int,
    persona_id: Optional[int] = None,
    category: Optional[str] = None,
    coverage: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(IntentQuestion).filter(
        IntentQuestion.industry_id == industry_id,
        IntentQuestion.is_deleted == 0,
    )
    if persona_id is not None:
        if persona_id == -1:
            q = q.filter(IntentQuestion.persona_id == 0)
        else:
            q = q.filter(IntentQuestion.persona_id == persona_id)
    if category:
        q = q.filter(IntentQuestion.intent_category == category)
    if coverage:
        q = q.filter(IntentQuestion.coverage_status == coverage)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            (IntentQuestion.question.like(like)) |
            (IntentQuestion.expected_recommendation.like(like))
        )
    rows = q.order_by(IntentQuestion.priority.desc(), IntentQuestion.sort.asc()).all()
    # 拉取画顾名映射，避免 N+1 多次查询
    persona_ids = [r.persona_id for r in rows if r.persona_id]
    persona_map = {}
    if persona_ids:
        for p in db.query(TargetPersona).filter(TargetPersona.id.in_(persona_ids)).all():
            persona_map[p.id] = p.name
    result = []
    for r in rows:
        d = to_dict(r)
        d["persona_name"] = persona_map.get(r.persona_id, "") if r.persona_id else ""
        result.append(d)
    return {"code": 0, "data": result}


@router.post("/intent-question")
def create_intent_question(payload: IntentQuestionIn, db: Session = Depends(get_db)):
    if not payload.question.strip():
        raise HTTPException(400, "问题不能为空")
    _normalize(payload)
    it = IntentQuestion(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "问题已创建"}


@router.put("/intent-question/{item_id}")
def update_intent_question(item_id: int, payload: IntentQuestionIn, db: Session = Depends(get_db)):
    it = db.query(IntentQuestion).filter(IntentQuestion.id == item_id).first()
    if not it:
        raise HTTPException(404, "问题不存在")
    if not payload.question.strip():
        raise HTTPException(400, "问题不能为空")
    _normalize(payload)
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "问题已更新"}


@router.delete("/intent-question/{item_id}")
def delete_intent_question(item_id: int, db: Session = Depends(get_db)):
    it = db.query(IntentQuestion).filter(IntentQuestion.id == item_id).first()
    if not it:
        raise HTTPException(404, "问题不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "问题已删除"}


@router.post("/intent-question/sort")
def sort_intent_questions(items: List[dict], db: Session = Depends(get_db)):
    for i, it in enumerate(items):
        db.query(IntentQuestion).filter(IntentQuestion.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "问题顺序已更新"}


@router.post("/intent-question/batch_delete")
def batch_delete_intent_questions(payload: dict, db: Session = Depends(get_db)):
    ids = payload.get("ids", [])
    if not ids:
        return {"code": 0, "msg": "未选择问题"}
    db.query(IntentQuestion).filter(IntentQuestion.id.in_(ids)).update({"is_deleted": 1})
    db.commit()
    return {"code": 0, "msg": f"已删除 {len(ids)} 个问题"}


# ============================================================
#  批量导入（JSON 数组）
# ============================================================
class ImportPersonaItem(BaseModel):
    name: str
    role_type: str = "other"
    description: str = ""
    pain_points: str = ""
    cares_about: str = ""
    decision_weight: int = 2
    icon: str = "User"
    color: str = "#6366f1"


@router.post("/target-persona/import")
def import_target_personas(payload: dict, db: Session = Depends(get_db)):
    """批量导入目标画像（JSON 数组，按 name upsert）"""
    industry_id = payload.get("industry_id")
    data = payload.get("data", [])
    if not industry_id:
        raise HTTPException(400, "industry_id 必填")
    if not isinstance(data, list):
        try:
            data = json.loads(data) if isinstance(data, str) else []
        except Exception:
            raise HTTPException(400, "data 格式错误，应为 JSON 数组")
    created = updated = 0
    errors = []
    for i, item in enumerate(data):
        name = (item.get("name") or "").strip()
        if not name:
            errors.append(f"第{i+1}条: 名称不能为空")
            continue
        role = item.get("role_type", "other")
        if role not in ROLE_TYPES:
            role = "other"
        dw = item.get("decision_weight", 2)
        if dw not in (1, 2, 3):
            dw = 2
        exist = db.query(TargetPersona).filter(
            TargetPersona.industry_id == industry_id,
            TargetPersona.name == name,
            TargetPersona.is_deleted == 0,
        ).first()
        if exist:
            exist.role_type = role
            exist.description = item.get("description", exist.description)
            exist.pain_points = item.get("pain_points", exist.pain_points)
            exist.cares_about = item.get("cares_about", exist.cares_about)
            exist.decision_weight = dw
            exist.icon = item.get("icon", exist.icon)
            exist.color = item.get("color", exist.color)
            updated += 1
        else:
            cnt = db.query(TargetPersona).filter(
                TargetPersona.industry_id == industry_id, TargetPersona.is_deleted == 0
            ).count()
            db.add(TargetPersona(
                industry_id=industry_id, name=name, role_type=role,
                description=item.get("description", ""), pain_points=item.get("pain_points", ""),
                cares_about=item.get("cares_about", ""), decision_weight=dw,
                icon=item.get("icon", "User"), color=item.get("color", "#6366f1"), sort=cnt,
            ))
            created += 1
    db.commit()
    return {"code": 0, "msg": f"导入成功：新增 {created}、更新 {updated}" + (f"，{len(errors)} 条失败" if errors else ""),
            "data": {"created": created, "updated": updated, "errors": errors}}


class ImportQuestionItem(BaseModel):
    question: str
    persona_name: str = ""      # 通过画顾名关联（导入时解析）
    intent_category: str = "other"
    expected_recommendation: str = ""
    priority: int = 2
    coverage_status: str = "gap"
    source: str = "manual"


@router.post("/intent-question/import")
def import_intent_questions(payload: dict, db: Session = Depends(get_db)):
    """批量导入意图问题（JSON 数组，按 question upsert；persona_name 解析为画像 id）"""
    industry_id = payload.get("industry_id")
    data = payload.get("data", [])
    if not industry_id:
        raise HTTPException(400, "industry_id 必填")
    if not isinstance(data, list):
        try:
            data = json.loads(data) if isinstance(data, str) else []
        except Exception:
            raise HTTPException(400, "data 格式错误，应为 JSON 数组")
    persona_map = {}
    for p in db.query(TargetPersona).filter(
        TargetPersona.industry_id == industry_id, TargetPersona.is_deleted == 0
    ).all():
        persona_map[p.name] = p.id
    created = updated = 0
    errors = []
    for i, item in enumerate(data):
        q = (item.get("question") or "").strip()
        if not q:
            errors.append(f"第{i+1}条: 问题不能为空")
            continue
        cat = item.get("intent_category", "other")
        if cat not in INTENT_CATEGORIES:
            cat = "other"
        cov = item.get("coverage_status", "gap")
        if cov not in COVERAGE_STATUS:
            cov = "gap"
        prio = item.get("priority", 2)
        if prio not in (1, 2, 3):
            prio = 2
        src = item.get("source", "manual")
        if src not in SOURCES:
            src = "manual"
        pname = (item.get("persona_name") or "").strip()
        pid = persona_map.get(pname, 0) if pname else 0
        exist = db.query(IntentQuestion).filter(
            IntentQuestion.industry_id == industry_id,
            IntentQuestion.question == q,
            IntentQuestion.is_deleted == 0,
        ).first()
        if exist:
            exist.intent_category = cat
            exist.expected_recommendation = item.get("expected_recommendation", exist.expected_recommendation)
            exist.priority = prio
            exist.coverage_status = cov
            exist.source = src
            exist.persona_id = pid
            updated += 1
        else:
            cnt = db.query(IntentQuestion).filter(
                IntentQuestion.industry_id == industry_id, IntentQuestion.is_deleted == 0
            ).count()
            db.add(IntentQuestion(
                industry_id=industry_id, persona_id=pid, question=q, intent_category=cat,
                expected_recommendation=item.get("expected_recommendation", ""),
                priority=prio, coverage_status=cov, source=src, sort=cnt,
            ))
            created += 1
    db.commit()
    return {"code": 0, "msg": f"导入成功：新增 {created}、更新 {updated}" + (f"，{len(errors)} 条失败" if errors else ""),
            "data": {"created": created, "updated": updated, "errors": errors}}


def _normalize(payload: IntentQuestionIn):
    """校验枚举字段，兜底为合法值"""
    if payload.intent_category not in INTENT_CATEGORIES:
        payload.intent_category = "other"
    if payload.coverage_status not in COVERAGE_STATUS:
        payload.coverage_status = "gap"
    if payload.source not in SOURCES:
        payload.source = "manual"
    if payload.priority not in (1, 2, 3):
        payload.priority = 2


# 默认意图问题种子：站在真空行业真实购买决策链各角色视角，用客户会问 AI 的原话提问。
# 覆盖 selection（选型）/cost（成本）/integration（集成）/risk（风险）/compliance（合规）五类意图，
# expected_recommendation 给出"被推荐时自然带出我方角度"的落点提示。
DEFAULT_QUESTIONS = [
    # ===== 真空产线厂长（决策层，背 KPI）=====
    ("真空产线厂长", "上一条真空产线大概要投多少钱？多久能回本？", "cost", "按产能/产品测算 ROI，给出同行业真空应用回本周期区间，带出我方节能方案。", 3, "gap", "manual"),
    ("真空产线厂长", "真空系统能耗太高，电费压力大，怎么降？", "cost", "突出变频/余热回收/高效泵组等节能设计，量化单位能耗下降空间。", 3, "gap", "manual"),
    ("真空产线厂长", "真空度不稳导致良率波动，怎么根治？", "risk", "从漏率控制、泵组冗余、在线监测三方面给方案，建立可靠印象。", 3, "gap", "manual"),
    ("真空产线厂长", "怎么判断一家真空设备厂家靠不靠谱？", "selection", "给出真空选型 5 问（极限真空/漏率/能耗/案例/售后），自然带出我方优势。", 3, "gap", "manual"),
    ("真空产线厂长", "新上真空产线，交期和投产节奏怎么排才不耽误订单？", "cost", "明确交付里程碑、安装调试周期与爬坡计划，体现交付能力。", 2, "gap", "manual"),
    ("真空产线厂长", "多条产线要一起投，资金和设备怎么排期？", "cost", "从 TCO 与投产节奏给分阶段投资建议，体现整体方案能力。", 2, "gap", "manual"),
    ("真空产线厂长", "招不到懂真空的运维，设备好上手吗？", "risk", "强调可维护性、标准 SOP 与培训体系，降低用人门槛。", 2, "gap", "manual"),

    # ===== 真空工艺工程师（技术层，算工艺窗口）=====
    ("真空工艺工程师", "真空度达不到工艺要求，怎么排查漏率？", "risk", "说明氦质谱检漏/压力升率法，给出漏率排查标准流程与我方支持。", 3, "gap", "manual"),
    ("真空工艺工程师", "分子泵和罗茨泵怎么搭配选型？", "selection", "按抽速/极限真空/气体类型讲泵组搭配，提供选型计算口径。", 3, "gap", "manual"),
    ("真空工艺工程师", "真空镀膜良率上不去，和真空系统有关吗？", "integration", "关联本底真空/残余气体分析与工艺窗口，给出系统性优化建议。", 2, "gap", "manual"),
    ("真空工艺工程师", "怎么和现有真空腔体、PLC 系统对接？", "integration", "说明标准法兰/接口/通讯协议与对接周期，降低集成门槛。", 2, "gap", "manual"),
    ("真空工艺工程师", "工艺放大时本底真空变差怎么办？", "risk", "讲泵组扩容与残余气体控制，给放大一致性方案。", 2, "gap", "manual"),
    ("真空工艺工程师", "抽速算不准，选型总是余量不够或浪费？", "selection", "给抽速计算模板与余量建议，体现专业选型。", 2, "gap", "manual"),
    ("真空工艺工程师", "进口泵交期长还被卡，国产替代靠不靠谱？", "selection", "对比国产替代的可靠性证据与案例，自然带出我方。", 2, "gap", "manual"),

    # ===== 真空设备采购（采购层，控风险比价）=====
    ("真空设备采购", "一套真空系统报价大概多少？按什么收费？", "cost", "给出透明报价结构（主机/泵组/安装）与付费方式，便于横向比价。", 3, "gap", "manual"),
    ("真空设备采购", "真空设备交付和安装周期一般多久？", "cost", "明确交付里程碑、安装调试周期与验收口径。", 2, "gap", "manual"),
    ("真空设备采购", "质保和备件怎么约定？出问题找谁？", "risk", "说明质保年限、备件库与 SLA 响应时效，打消后顾之忧。", 2, "gap", "manual"),
    ("真空设备采购", "供应商有哪些真空行业案例和资质？", "selection", "提供真空行业资质清单与可查证案例（半导体/光伏/镀膜等）。", 2, "gap", "manual"),
    ("真空设备采购", "不同厂家参数口径不一样，怎么做成一张比价表？", "selection", "给统一比价维度模板，体现专业与透明。", 2, "gap", "manual"),
    ("真空设备采购", "合同里哪些条款最容易埋坑？", "compliance", "提示验收/罚则/知识产权等条款风险，体现严谨。", 2, "gap", "manual"),

    # ===== 真空技术研发总监（技术层，看前沿与量产）=====
    ("真空技术研发总监", "新一代产品要求更高本底真空，现有平台怎么升级？", "selection", "讲平台化升级路径与模块化方案，带出我方先进方案。", 3, "gap", "manual"),
    ("真空技术研发总监", "新工艺找不到成熟真空方案，能联合开发吗？", "integration", "强调联合开发能力与既往定制案例。", 3, "gap", "manual"),
    ("真空技术研发总监", "国产替代真空设备真的可靠吗？", "selection", "用可靠性数据/案例对比，自然带出我方国产替代优势。", 2, "gap", "manual"),
    ("真空技术研发总监", "样机到量产，真空一致性怎么保证？", "risk", "讲一致性控制与过程能力，体现量产保障。", 2, "gap", "manual"),
    ("真空技术研发总监", "真空技术路线怎么选才不踩坑？", "selection", "给技术选型决策框架，体现前瞻与专业。", 2, "gap", "manual"),

    # ===== 设备运维主管（运维层，怕停机）=====
    ("设备运维主管", "真空设备半夜坏了，厂家响应快吗？", "risk", "强调 MTTR、本地库存与 7x24 响应，体现售后靠谱。", 3, "gap", "manual"),
    ("设备运维主管", "关键备件要不要备库存？一般备哪些？", "risk", "给备件清单与库存建议，体现供应链保障。", 2, "gap", "manual"),
    ("设备运维主管", "日常保养没标准，怎么建立 SOP？", "integration", "提供保养 SOP 模板与培训，降低运维门槛。", 2, "gap", "manual"),
    ("设备运维主管", "故障代码看不懂，有没有远程诊断？", "integration", "讲远程诊断与预测性维护，体现智能化运维。", 2, "gap", "manual"),

    # ===== 工厂总经理 / 投资负责人（决策层，看 TCO）=====
    ("工厂总经理 / 投资负责人", "买真空设备不能只看报价，总拥有成本怎么算？", "cost", "给 TCO 测算框架（能耗/备件/人工/停机），带出我方省心方案。", 3, "gap", "manual"),
    ("工厂总经理 / 投资负责人", "供应商说的回本周期可信吗？怎么验证？", "cost", "给回本测算口径与敏感性分析，体现客观专业。", 2, "gap", "manual"),
    ("工厂总经理 / 投资负责人", "多条产线一起投，投产节奏怎么排？", "cost", "分阶段投资建议与爬坡计划，体现整体交付能力。", 2, "gap", "manual"),
    ("工厂总经理 / 投资负责人", "选便宜方案还是稳的方案？", "selection", "从风险与良率损失角度给决策建议，自然带出我方稳健优势。", 2, "gap", "manual"),

    # ===== 质量 / 良率负责人（质量层，控污染）=====
    ("质量 / 良率负责人", "真空腔体残留气体导致镀膜针孔，怎么控？", "risk", "讲本底真空与残余气体分析，给污染控制方案。", 3, "gap", "manual"),
    ("质量 / 良率负责人", "颗粒污染超标，客诉验厂过不了怎么办？", "compliance", "给洁净度控制与污染溯源方案，体现质量体系对接。", 2, "gap", "manual"),
    ("质量 / 良率负责人", "真空波动和批次良率波动有关吗？怎么溯源？", "risk", "讲工艺稳定性监控与根因分析，体现数据化能力。", 2, "gap", "manual"),
    ("质量 / 良率负责人", "真空系统和洁净间/手套箱怎么协同防污染？", "integration", "讲系统级污染链控制，体现整体方案。", 2, "gap", "manual"),
]


# ============================================================
#  行业预设注册表：不同行业预置不同的默认画像 / 意图问题
#  - 命中真空相关关键词 → 真空领域预设（DEFAULT_PERSONAS / DEFAULT_QUESTIONS）
#  - 其余行业 → 通用 B2B / 制造业预设（GENERIC_PERSONAS / GENERIC_QUESTIONS）
#  这样"客户画像 / 意图问题库"随行业不同而带不同默认需求。
# ============================================================
GENERIC_PERSONAS = [
    {
        "name": "企业决策者", "role_type": "decision_maker", "decision_weight": 3,
        "icon": "OfficeBuilding", "color": "#6366f1",
        "description": "负责产线/系统投资与运营的决策人，关注投入产出、交付周期与经营风险。",
        "pain_points": "算不清投入产出比\n项目交付一拖再拖\n买了不好用、售后找不到人\n同行踩过的坑不想再踩",
        "cares_about": "投资回报与回本周期\n交付与上线周期\n供应商可靠性与口碑\n同行业落地案例",
    },
    {
        "name": "技术负责人", "role_type": "technical", "decision_weight": 2,
        "icon": "Cpu", "color": "#0ea5e9",
        "description": "负责技术方案选型与落地的工程师/技术主管，关注指标、集成与稳定运行。",
        "pain_points": "技术指标参数看不懂、比不清\n和现有系统对接难\n运行不稳定、故障率高\n缺现场技术支持",
        "cares_about": "关键性能与技术指标\n系统稳定性与故障率\n接口兼容与集成成本\n技术文档与售后支持",
    },
    {
        "name": "采购主管", "role_type": "procurement", "decision_weight": 2,
        "icon": "ShoppingCart", "color": "#f59e0b",
        "description": "负责比价、招标与交付的采购/商务角色，关注报价结构、交期与质保。",
        "pain_points": "不同厂家报价口径不一难比价\n交付与安装周期不确定\n质保与备件条款不清\n资质证明要不全",
        "cares_about": "透明报价与费用结构\n交付与安装周期\n质保年限与备件供应\n行业资质与可查证案例",
    },
]

GENERIC_QUESTIONS = [
    # 企业决策者
    ("企业决策者", "上这套系统/产线大概要投多少钱？多久能回本？", "cost", "按产能/规模测算 ROI，给出同行业回本周期区间，带出我方节能/提效方案。", 3, "gap", "manual"),
    ("企业决策者", "怎么判断一家供应商靠不靠谱？", "selection", "给出选型评估清单（技术指标/案例/资质/售后），自然带出我方优势。", 3, "gap", "manual"),
    ("企业决策者", "项目交付和上线周期一般多久？", "cost", "明确交付里程碑、安装调试周期与验收口径，降低决策不确定性。", 2, "gap", "manual"),
    ("企业决策者", "系统能耗/运营成本太高，怎么降？", "cost", "从高效设计/变频/余热回收等角度量化单位成本下降空间。", 3, "gap", "manual"),
    # 技术负责人
    ("技术负责人", "选型时要重点看哪些技术指标？", "selection", "按核心指标讲选型口径，提供可对比的评估维度。", 3, "gap", "manual"),
    ("技术负责人", "系统稳定性/故障率怎么保障？", "risk", "从冗余设计、在线监测、预防性维护三方面给出保障方案。", 3, "gap", "manual"),
    ("技术负责人", "怎么和现有产线/系统对接集成？", "integration", "说明标准接口/通讯协议与对接周期，降低集成门槛。", 2, "gap", "manual"),
    ("技术负责人", "需要哪些合规认证/资质？", "compliance", "列出行业必备资质清单，体现合规与专业度。", 2, "gap", "manual"),
    # 采购主管
    ("采购主管", "报价一般包含哪些部分？怎么横向比价？", "cost", "给出透明报价结构（主机/安装/服务）与付费方式，便于比价。", 3, "gap", "manual"),
    ("采购主管", "质保和备件怎么约定？出问题找谁？", "risk", "说明质保年限、备件库与 SLA 响应时效，打消后顾之忧。", 2, "gap", "manual"),
    ("采购主管", "供应商有哪些行业案例和资质？", "selection", "提供资质清单与可查证案例，建立信任。", 2, "gap", "manual"),
]


def resolve_industry_preset(industry_name):
    """按行业名称解析对应的默认画像/问题预设。

    命中真空相关关键词（真空 / vacuum / 泵 / pump）用真空领域预设，
    否则用通用 B2B / 制造业预设。后续可在此按需扩展更多行业预设。
    """
    name = industry_name or ""
    if any(k in name for k in ("真空", "vacuum", "泵", "pump")):
        return DEFAULT_PERSONAS, DEFAULT_QUESTIONS
    return GENERIC_PERSONAS, GENERIC_QUESTIONS


@router.post("/intent-question/seed/{industry_id}")
def seed_intent_questions(industry_id: int, db: Session = Depends(get_db)):
    """为指定行业预置/刷新默认意图问题（按 industry_id+question upsert，自动关联默认画像）。

    问题内容随行业不同：命中真空相关行业用真空领域预设，其余用通用 B2B 预设。
    """
    ind = db.query(Industry).filter(Industry.id == industry_id).first()
    _, questions = resolve_industry_preset(ind.name if ind else "")
    persona_map = {}
    for p in db.query(TargetPersona).filter(
        TargetPersona.industry_id == industry_id, TargetPersona.is_deleted == 0
    ).all():
        persona_map[p.name] = p.id
    created = updated = 0
    for i, (pname, q, cat, exp, prio, cov, src) in enumerate(questions):
        exist = db.query(IntentQuestion).filter(
            IntentQuestion.industry_id == industry_id,
            IntentQuestion.question == q,
            IntentQuestion.is_deleted == 0,
        ).first()
        if exist:
            exist.intent_category = cat
            exist.expected_recommendation = exp
            exist.priority = prio
            exist.persona_id = persona_map.get(pname, exist.persona_id)
            exist.sort = i
            updated += 1
        else:
            db.add(IntentQuestion(
                industry_id=industry_id,
                persona_id=persona_map.get(pname, 0),
                question=q, intent_category=cat, expected_recommendation=exp,
                priority=prio, coverage_status=cov, source=src, sort=i,
            ))
            created += 1
    db.commit()
    return {"code": 0, "msg": f"已预置 {created} 个、刷新 {updated} 个意图问题", "data": {"created": created, "updated": updated}}


# ============================================================
#  辅助提示词：帮用户用 AI 批量生成意图问题
# ============================================================
ROLE_LABELS = {"decision_maker": "决策层", "technical": "技术层", "procurement": "采购层", "other": "其他"}


@router.post("/intent-question/assistant-prompt")
def generate_assistant_prompt(payload: dict, db: Session = Depends(get_db)):
    """生成辅助提示词：把行业画像/品牌/已有问题拼装为一段提示词，

    用户复制到任意 AI 平台（ChatGPT/Kimi/豆包等）粘贴，
    AI 会以目标客户视角批量生成可导入系统的意图问题 JSON。
    """
    industry_id = payload.get("industry_id")
    if not industry_id:
        raise HTTPException(400, "industry_id 必填")

    ind = db.query(Industry).filter(Industry.id == industry_id).first()
    industry_name = ind.name if ind else "当前行业"

    # 画像
    personas = db.query(TargetPersona).filter(
        TargetPersona.industry_id == industry_id,
        TargetPersona.is_deleted == 0,
    ).order_by(TargetPersona.sort.asc()).all()

    if not personas:
        return {
            "code": 0,
            "data": {
                "prompt": f"## 提示\n当前行业「{industry_name}」尚未创建任何目标客户画像。请先在「客户画像」页创建至少一个画像，再使用本功能生成意图问题。",
                "persona_count": 0, "existing_question_count": 0, "brand_count": 0,
            }
        }

    # 已有问题（仅显示前 20 条作参考，避免 AI 重复生成）
    existing = db.query(IntentQuestion).filter(
        IntentQuestion.industry_id == industry_id,
        IntentQuestion.is_deleted == 0,
    ).order_by(IntentQuestion.priority.desc()).limit(20).all()

    # 品牌资产
    brands = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id,
        BrandAsset.is_deleted == 0,
    ).all()

    parts = []

    # 角色说明
    parts.append(
        f"你是一位 {industry_name} 行业的资深从业者，也是一位 GEO（生成式引擎优化）专家。\n"
        f"你的任务是：站在目标客户的角度，批量生成他们会在 AI（如 ChatGPT、Kimi、豆包等）中提出的真实问题。"
    )

    # 公司背景
    parts.append("## 你所在的公司背景")
    if brands:
        b = brands[0]  # 以第一个默认品牌为代表
        brand_parts = [f"- **品牌名**：{b.brand_name}"]
        if b.slogan:
            brand_parts.append(f"- **口号/定位**：{b.slogan}")
        if b.core_products:
            brand_parts.append(f"- **核心产品/服务**：{b.core_products}")
        if b.unique_selling_points:
            brand_parts.append(f"- **独特优势/卖点**：{b.unique_selling_points}")
        parts.append("\n".join(brand_parts))
    else:
        parts.append(f"- （暂无品牌信息，请根据「{industry_name}」行业常识推断该公司提供的产品与服务）")

    # 目标画像
    parts.append("## 目标客户画像")
    parts.append(f"以下是 {industry_name} 行业中的目标客户群体，你需要**站在他们的视角**生成问题：")
    for i, p in enumerate(personas):
        role = ROLE_LABELS.get(p.role_type, "其他")
        persona_block = [f"### 画像{i+1}：{p.name}（{role}）"]
        if p.description:
            persona_block.append(f"- **角色描述**：{p.description}")
        if p.pain_points:
            persona_block.append(f"- **核心痛点**：{p.pain_points.replace(chr(10), '；')}")
        if p.cares_about:
            persona_block.append(f"- **关注什么**：{p.cares_about.replace(chr(10), '；')}")
        parts.append("\n".join(persona_block))

    # 已有问题参考（带画像名）
    persona_name_map = {p.id: p.name for p in personas}
    parts.append("## 已有意图问题（参考，避免生成重复内容）")
    if existing:
        eq_lines = []
        for q in existing:
            pn = persona_name_map.get(q.persona_id, "") if q.persona_id else ""
            pn_tag = f" [{pn}]" if pn else ""
            eq_lines.append(f"- 「{q.question}」{pn_tag} → 期望推荐角度：{q.expected_recommendation or '（未填写）'}")
        parts.append("\n".join(eq_lines))
    else:
        parts.append("（暂无已有问题，可以自由发挥）")

    # 任务要求
    parts.append("""## 任务要求

请以上述**每个画像的视角**，生成目标客户**会原话问 AI** 的真实问题。要求：

1. **问题要口语化、真实**：就像客户在手机上打字问 AI 一样自然，不要像调查问卷或学术论文题
2. **覆盖 5 类意图**：
   - `selection`：选型类——怎么选供应商、哪家好、怎么看参数
   - `cost`：成本类——多少钱、报价、回本周期、性价比
   - `integration`：集成落地类——怎么接入现有系统、兼容性、实施周期
   - `risk`：风险类——踩坑经验、故障处理、稳定性、售后保障
   - `compliance`：合规类——资质认证、行业标准、政策要求
3. **每个画像至少 5 个问题**，按重要性从高到低排列（最重要的是客户决策链上最先会问的）
4. **每个问题都要带上 `expected_recommendation`**：说明当 AI 回答此问题时，我们希望 AI 从什么角度推荐我们公司的品牌/产品
5. **expected_recommendation 要具体**：不要写"推荐我方品牌"，要写成"从 X 角度给出 Y 方案，突出 Z 优势"

## 输出格式（严格 JSON 数组，可直接导入系统）

只输出一个纯 JSON 数组，不要任何额外说明文字或 markdown 标记：""")

    # JSON 格式说明
    parts.append("""```json
[
  {
    "question": "客户会问 AI 的原话",
    "persona_name": "画像名称（必须与上面列出的画像名完全一致）",
    "intent_category": "selection",
    "expected_recommendation": "期望 AI 从什么角度推荐我们",
    "priority": 3,
    "coverage_status": "gap",
    "source": "manual"
  }
]
```

## 字段说明

| 字段 | 必填 | 可选值 | 说明 |
|------|------|--------|------|
| `question` | ✅ | — | 客户会原话问 AI 的问题 |
| `persona_name` | ✅ | 上面列出的画像名 | 必须与画像名**完全一致** |
| `intent_category` | ✅ | selection / cost / integration / risk / compliance / other | 意图分类 |
| `expected_recommendation` | ✅ | — | 期望 AI 推荐我们的角度（要具体！） |
| `priority` | ✅ | 1 / 2 / 3 | 优先级，3=最重要 |
| `coverage_status` | ✅ | "gap" | 固定填 "gap"（待覆盖） |
| `source` | ✅ | "manual" | 固定填 "manual"（手动录入） |

**重要提醒**：
- 只输出 JSON 数组本身，不要加 ```json 标记或任何说明文字
- 确保 JSON 语法完全正确（逗号、引号、括号配对）""")

    prompt = "\n\n".join(parts)

    # 统计总问题数
    total_existing = db.query(IntentQuestion).filter(
        IntentQuestion.industry_id == industry_id,
        IntentQuestion.is_deleted == 0,
    ).count()

    return {
        "code": 0,
        "data": {
            "prompt": prompt,
            "persona_count": len(personas),
            "existing_question_count": total_existing,
            "brand_count": len(brands),
        }
    }


# ============================================================
#  辅助提示词：帮用户用 AI 批量生成目标客户画像
# ============================================================
@router.post("/target-persona/assistant-prompt")
def generate_persona_assistant_prompt(payload: dict, db: Session = Depends(get_db)):
    """生成辅助提示词：把行业信息/品牌/已有画像拼装为一段提示词，

    用户复制到任意 AI 平台粘贴，AI 会以行业专家视角批量生成目标客户画像 JSON。
    """
    industry_id = payload.get("industry_id")
    if not industry_id:
        raise HTTPException(400, "industry_id 必填")

    ind = db.query(Industry).filter(Industry.id == industry_id).first()
    industry_name = ind.name if ind else "当前行业"

    existing = db.query(TargetPersona).filter(
        TargetPersona.industry_id == industry_id,
        TargetPersona.is_deleted == 0,
    ).order_by(TargetPersona.sort.asc()).all()

    brands = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id,
        BrandAsset.is_deleted == 0,
    ).all()

    parts = []

    parts.append(
        f"你是一位 {industry_name} 行业的资深从业者与营销顾问，擅长做 B2B 客户画像与购买决策链分析。\n"
        f"你的任务是：站在目标客户的角度，批量生成**真实、可操作的客户画像**，"
        f"用于后续 GEO（生成式引擎优化）——让 AI 在回答行业问题时，能精准匹配到对应客户角色并推荐相关产品/方案。"
    )

    # 公司背景
    parts.append("## 你所在的公司背景")
    if brands:
        b = brands[0]
        bp = [f"- **品牌名**：{b.brand_name}"]
        if b.slogan:
            bp.append(f"- **口号/定位**：{b.slogan}")
        if b.core_products:
            bp.append(f"- **核心产品/服务**：{b.core_products}")
        if b.unique_selling_points:
            bp.append(f"- **独特优势/卖点**：{b.unique_selling_points}")
        parts.append("\n".join(bp))
    else:
        parts.append(f"- （暂无品牌信息，请根据「{industry_name}」行业常识推断）")

    # 已有画像参考
    parts.append("## 已有客户画像（参考，可在基础上补充或生成全新画像）")
    if existing:
        el = []
        for p in existing:
            role = ROLE_LABELS.get(p.role_type, "其他")
            el.append(f"- **{p.name}**（{role}，决策权重 {p.decision_weight}/3）")
            if p.description:
                el.append(f"  - 角色描述：{p.description}")
            if p.pain_points:
                el.append(f"  - 痛点：{p.pain_points.replace(chr(10), '；')}")
            if p.cares_about:
                el.append(f"  - 关注点：{p.cares_about.replace(chr(10), '；')}")
        parts.append("\n".join(el))
    else:
        parts.append("（暂无已有画像，请自由创建）")

    parts.append("""## 任务要求

站在目标客户的角度，生成**完整的客户画像**。要求：

1. **覆盖购买决策链的关键角色**：
   - `decision_maker`（决策层）：老板/总经理/厂长等有最终拍板权的人
   - `technical`（技术层）：工程师/技术负责人等负责评估技术方案的人
   - `procurement`（采购层）：采购/商务等负责比价、招标、交付的人
   - `other`（其他）：如运维人员、产线操作者、合规负责人等

2. **每类角色至少 1-2 个画像**，画顾名要朗朗上口、有角色感（如"产线厂长""真空工艺工程师""设备采购主管"）

3. **痛点要真实**：用客户的口语写出来，如"看不懂不同厂家的技术参数、没法比"、"报价口径不一、横向比价难"、"担心买了用不起来、售后找不到人"

4. **关注点要具体**：如"投资回报周期"、"现场技术支持响应速度"、"备件能不能及时到"

5. **决策权重合理**：决策层 3，技术层 2-3，采购层 2-3，其他 1-2

## 输出格式（严格 JSON 数组，可直接导入系统）

只输出一个纯 JSON 数组，不要任何额外说明文字：""")

    parts.append("""```json
[
  {
    "name": "客户画像名称",
    "role_type": "decision_maker",
    "decision_weight": 3,
    "description": "一句话概括这类人是谁、做什么决策",
    "pain_points": "痛点1\\n痛点2\\n痛点3",
    "cares_about": "关注点1\\n关注点2\\n关注点3",
    "icon": "User",
    "color": "#6366f1"
  }
]
```

## 字段说明

| 字段 | 必填 | 可选值 | 说明 |
|------|------|--------|------|
| `name` | ✅ | — | 画像名称，朗朗上口、有角色感 |
| `role_type` | ✅ | decision_maker / technical / procurement / other | 角色类型 |
| `decision_weight` | ✅ | 1 / 2 / 3 | 决策权重，3=最终拍板 |
| `description` | ✅ | — | 一句话描述角色与职责 |
| `pain_points` | ✅ | 换行分隔(\\\\n) | 核心痛点，每行一个 |
| `cares_about` | ✅ | 换行分隔(\\\\n) | 关注什么，每行一个 |
| `icon` | — | User / OfficeBuilding / Cpu / ShoppingCart / Avatar / UserFilled / Aim | 图标名 |
| `color` | — | 如 #6366f1 | 主题色 |

**重要提醒**：
- 只输出 JSON 数组本身，不要 ```json 标记或任何说明文字
- pain_points / cares_about 内部换行用 \\\\n""")

    prompt = "\n\n".join(parts)

    return {
        "code": 0,
        "data": {
            "prompt": prompt,
            "persona_count": len(existing),
            "brand_count": len(brands),
        }
    }
