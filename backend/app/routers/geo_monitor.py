"""GEO 监测模块（模块⑥）

闭环最后一环：验证 AI 是否真的推荐我们。
- GeoMonitor：监测任务（目标问题 + 品牌名 + 对标 AI 平台列表）
- GeoMonitorReply：某 AI 平台的答复 + 本地启发式解析出的「AI 认可度 3 指标」

工作流（与系统"提示词编排 + 结果回传"模式一致）：
1. 创建监测任务（设定目标问题 + 品牌名 + 选 AI 平台）
2. 系统生成各平台提问提示词 → 用户复制去 AI 平台粘贴
3. 用户把 AI 答复粘贴回系统 → 本地解析 3 指标
4. 看板汇总：品牌提及率 / 引用长度 / 情感倾向
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BrandAsset, GeoMonitor, GeoMonitorReply, IntentQuestion
from ..utils import to_dict

router = APIRouter(prefix="/api", tags=["GEO-监测"])

# 对标 AI 平台预设
AI_PLATFORMS = [
    {"name": "豆包", "icon": "ChatDotRound", "color": "#4e8ef7"},
    {"name": "文心一言", "icon": "ChatLineRound", "color": "#2932e1"},
    {"name": "DeepSeek", "icon": "MagicStick", "color": "#4f46e5"},
    {"name": "Kimi", "icon": "ChatRound", "color": "#1a1a1a"},
    {"name": "通义千问", "icon": "ChatDotSquare", "color": "#615ced"},
    {"name": "智谱清言", "icon": "ChatLineSquare", "color": "#3777e5"},
    {"name": "ChatGPT", "icon": "ChatDotRound", "color": "#10a37f"},
    {"name": "Perplexity", "icon": "Search", "color": "#20808d"},
]


# ============================================================
#  Pydantic 输入模型
# ============================================================
class GeoMonitorIn(BaseModel):
    industry_id: int
    name: str = ""
    target_query: str = ""          # 向 AI 提的问题
    brand_name: str = ""            # 要监测的品牌名
    platforms: str = "[]"           # JSON 数组：AI 平台名列表
    note: str = ""
    sort: int = 0


class GeoMonitorReplyIn(BaseModel):
    monitor_id: int
    platform: str
    ai_reply: str = ""


# ============================================================
#  平台列表
# ============================================================
@router.get("/geo-monitor/platforms")
def list_ai_platforms():
    return {"code": 0, "data": AI_PLATFORMS}


# ============================================================
#  监测任务 CRUD
# ============================================================
@router.get("/geo-monitor")
def list_monitors(industry_id: int, db: Session = Depends(get_db)):
    rows = db.query(GeoMonitor).filter(
        GeoMonitor.industry_id == industry_id,
        GeoMonitor.is_deleted == 0,
    ).order_by(GeoMonitor.sort.asc(), GeoMonitor.id.desc()).all()
    result = []
    for m in rows:
        d = to_dict(m)
        # 统计回复数与提及率
        replies = db.query(GeoMonitorReply).filter(
            GeoMonitorReply.monitor_id == m.id,
        ).all()
        d["reply_count"] = len(replies)
        d["mentioned_count"] = sum(1 for r in replies if r.mentioned)
        d["mention_rate"] = round(d["mentioned_count"] / len(replies) * 100) if replies else 0
        result.append(d)
    return {"code": 0, "data": result}


@router.post("/geo-monitor")
def create_monitor(payload: GeoMonitorIn, db: Session = Depends(get_db)):
    if not payload.target_query.strip():
        raise HTTPException(400, "目标问题不能为空")
    if not payload.brand_name.strip():
        raise HTTPException(400, "品牌名不能为空")
    it = GeoMonitor(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "监测任务已创建"}


@router.put("/geo-monitor/{item_id}")
def update_monitor(item_id: int, payload: GeoMonitorIn, db: Session = Depends(get_db)):
    it = db.query(GeoMonitor).filter(GeoMonitor.id == item_id).first()
    if not it:
        raise HTTPException(404, "监测任务不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "监测任务已更新"}


@router.delete("/geo-monitor/{item_id}")
def delete_monitor(item_id: int, db: Session = Depends(get_db)):
    it = db.query(GeoMonitor).filter(GeoMonitor.id == item_id).first()
    if not it:
        raise HTTPException(404, "监测任务不存在")
    it.is_deleted = 1
    # 同时清理回复
    db.query(GeoMonitorReply).filter(GeoMonitorReply.monitor_id == item_id).delete()
    db.commit()
    return {"code": 0, "msg": "监测任务已删除"}


@router.post("/geo-monitor/sort")
def sort_monitors(items: List[dict], db: Session = Depends(get_db)):
    for i, it in enumerate(items):
        db.query(GeoMonitor).filter(GeoMonitor.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "顺序已更新"}


# ============================================================
#  一键灌入默认监测模板（数据驱动：品牌资产 × 高优先级意图问题）
# ============================================================
@router.post("/geo-monitor/seed/{industry_id}")
def seed_default_monitors(industry_id: int, db: Session = Depends(get_db)):
    """一键灌入默认监测模板：把"高优先级意图问题 × 品牌资产"组合成监测任务。

    不重复灌入（按 target_query 去重）；依赖品牌资产库已有品牌名与意图问题库已有高优先级问题。
    若两者缺一，返回友好提示而非报错。
    """
    brand = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id, BrandAsset.is_deleted == 0,
        BrandAsset.is_default == 1,
    ).first()
    if not brand:
        brand = db.query(BrandAsset).filter(
            BrandAsset.industry_id == industry_id, BrandAsset.is_deleted == 0,
        ).first()
    if not brand or not (brand.brand_name or "").strip():
        return {"code": 0, "msg": "暂无品牌资产，无法生成监测模板（请先在「品牌资产库」填写品牌名）", "data": {"created": 0}}

    brand_name = brand.brand_name.strip()
    qs = db.query(IntentQuestion).filter(
        IntentQuestion.industry_id == industry_id, IntentQuestion.is_deleted == 0,
        IntentQuestion.priority >= 2,
    ).order_by(IntentQuestion.priority.desc(), IntentQuestion.id.asc()).limit(8).all()
    if not qs:
        return {"code": 0, "msg": "暂无高优先级意图问题，无法生成监测模板（请先在「意图问题库」标注优先级≥2 的问题）", "data": {"created": 0}}

    default_platforms = json.dumps([p["name"] for p in AI_PLATFORMS[:5]])
    created = 0
    for q in qs:
        exist = db.query(GeoMonitor).filter(
            GeoMonitor.industry_id == industry_id, GeoMonitor.is_deleted == 0,
            GeoMonitor.target_query == q.question,
        ).first()
        if exist:
            continue
        db.add(GeoMonitor(
            industry_id=industry_id,
            name=f"监测：{q.question[:24]}",
            target_query=q.question,
            brand_name=brand_name,
            platforms=default_platforms,
            note="一键灌入默认模板",
        ))
        created += 1
    db.commit()
    return {"code": 0, "msg": f"已灌入 {created} 个监测模板（品牌：{brand_name}）", "data": {"created": created}}


# ============================================================
#  生成提问提示词（给用户复制去各 AI 平台粘贴）
# ============================================================
@router.get("/geo-monitor/{monitor_id}/prompt")
def get_monitor_prompt(monitor_id: int, platform: Optional[str] = None, db: Session = Depends(get_db)):
    """生成对标各 AI 平台的提问提示词。

    不调 AI，纯本地拼装。用户复制后去对应 AI 平台粘贴，
    把 AI 的答复粘回系统即可。
    """
    m = db.query(GeoMonitor).filter(GeoMonitor.id == monitor_id).first()
    if not m:
        raise HTTPException(404, "监测任务不存在")
    try:
        platforms = json.loads(m.platforms) if m.platforms else []
    except Exception:
        platforms = []
    if not platforms:
        platforms = [p["name"] for p in AI_PLATFORMS]

    brand = m.brand_name.strip()
    query = m.target_query.strip()

    # 通用提问提示词：让 AI 自然回答目标问题
    # 不直接问品牌名（避免引导），而是问行业问题，看 AI 是否主动提及
    base_prompt = f"""请回答以下问题：

{query}

要求：
- 给出详细、专业的回答
- 如果有推荐的品牌或方案，请明确提及
- 说明推荐理由与具体优势
- 如有数据或案例，请一并给出
- 结尾用一句话给出明确的推荐结论（是否推荐某品牌/方案及核心理由）"""

    # 平台专属追加（不同 AI 平台提问风格略有差异）
    platform_suffix = {
        "豆包": "\n\n请给出你认为最值得推荐的 2-3 个品牌或方案，并说明理由。",
        "文心一言": "\n\n请给出你认为最值得推荐的 2-3 个品牌或方案，并说明理由。",
        "DeepSeek": "\n\n请给出你认为最值得推荐的 2-3 个品牌或方案，并说明理由。",
        "Kimi": "\n\n请给出你认为最值得推荐的 2-3 个品牌或方案，并说明理由。",
        "通义千问": "\n\n请给出你认为最值得推荐的 2-3 个品牌或方案，并说明理由。",
        "智谱清言": "\n\n请给出你认为最值得推荐的 2-3 个品牌或方案，并说明理由。",
        "ChatGPT": "\n\nPlease recommend 2-3 brands or solutions you think are most worth considering, with reasons.",
        "Perplexity": "\n\nPlease recommend 2-3 brands or solutions you think are most worth considering, with reasons and sources.",
    }

    if platform and platform in platforms:
        suffix = platform_suffix.get(platform, "")
        prompt = base_prompt + suffix
        return {"code": 0, "data": {
            "platform": platform,
            "prompt": prompt,
            "brand": brand,
            "query": query,
        }}

    # 返回所有平台的提示词
    result = []
    for p in platforms:
        suffix = platform_suffix.get(p, "")
        result.append({
            "platform": p,
            "prompt": base_prompt + suffix,
        })
    return {"code": 0, "data": {
        "prompts": result,
        "brand": brand,
        "query": query,
    }}


# ============================================================
#  回传 AI 答复 + 本地解析 3 指标
# ============================================================
@router.post("/geo-monitor/{monitor_id}/reply")
def import_reply(monitor_id: int, payload: dict, db: Session = Depends(get_db)):
    """回传某 AI 平台的答复，本地解析 AI 认可度 3 指标。

    输入: { platform: "豆包", ai_reply: "AI的回复原文..." }
    输出: 解析后的指标（mentioned / mention_count / citation_length / sentiment / valuable_positive / snippet）
    """
    m = db.query(GeoMonitor).filter(GeoMonitor.id == monitor_id).first()
    if not m:
        raise HTTPException(404, "监测任务不存在")

    platform = (payload.get("platform") or "").strip()
    ai_reply = (payload.get("ai_reply") or "").strip()
    if not platform:
        raise HTTPException(400, "AI 平台不能为空")
    if not ai_reply:
        raise HTTPException(400, "AI 答复内容不能为空")

    brand = m.brand_name.strip()
    metrics = _parse_ai_reply(ai_reply, brand)

    # upsert：同 monitor + platform 只保留最新一条。
    # ⚠️ 只匹配「手工通道」的记录（run_id=0）—— 自动采集产生的回复每条对应一个
    # 独立的 geo_visibility_run，不能被人工粘贴覆盖，否则历史探测数据会被抹掉。
    exist = db.query(GeoMonitorReply).filter(
        GeoMonitorReply.monitor_id == monitor_id,
        GeoMonitorReply.platform == platform,
        GeoMonitorReply.run_id == 0,
    ).first()
    if exist:
        exist.ai_reply = ai_reply
        exist.mentioned = metrics["mentioned"]
        exist.mention_count = metrics["mention_count"]
        exist.citation_length = metrics["citation_length"]
        exist.sentiment = metrics["sentiment"]
        exist.valuable_positive = metrics["valuable_positive"]
        exist.recommended = metrics["recommended"]
        exist.snippet = metrics["snippet"]
        exist.source_channel = "manual"
        db.commit()
        return {"code": 0, "data": to_dict(exist), "msg": f"{platform} 答复已更新"}
    else:
        reply = GeoMonitorReply(
            monitor_id=monitor_id,
            platform=platform,
            ai_reply=ai_reply,
            run_id=0,
            source_channel="manual",
            **metrics,
        )
        db.add(reply)
        db.commit()
        db.refresh(reply)
        return {"code": 0, "data": to_dict(reply), "msg": f"{platform} 答复已保存"}


# ============================================================
#  查看某监测任务的全部回复
# ============================================================
@router.get("/geo-monitor/{monitor_id}/replies")
def list_replies(monitor_id: int, db: Session = Depends(get_db)):
    rows = db.query(GeoMonitorReply).filter(
        GeoMonitorReply.monitor_id == monitor_id,
    ).order_by(GeoMonitorReply.id.asc()).all()
    return {"code": 0, "data": [to_dict(r) for r in rows]}


@router.delete("/geo-monitor/reply/{reply_id}")
def delete_reply(reply_id: int, db: Session = Depends(get_db)):
    r = db.query(GeoMonitorReply).filter(GeoMonitorReply.id == reply_id).first()
    if not r:
        raise HTTPException(404, "回复不存在")
    db.delete(r)
    db.commit()
    return {"code": 0, "msg": "回复已删除"}


# ============================================================
#  看板汇总：某行业的整体 AI 认可度
# ============================================================
@router.get("/geo-monitor/stats")
def monitor_stats(industry_id: int, db: Session = Depends(get_db)):
    """汇总某行业的 GEO 监测数据：
    - 监测任务总数
    - 回复总数
    - 品牌提及率（被提及的回复 / 总回复）
    - 平均引用长度
    - 正面提及占比
    - 各平台提及率明细
    """
    monitors = db.query(GeoMonitor).filter(
        GeoMonitor.industry_id == industry_id,
        GeoMonitor.is_deleted == 0,
    ).all()
    monitor_ids = [m.id for m in monitors]
    if not monitor_ids:
        return {"code": 0, "data": {
            "monitor_count": 0,
            "reply_count": 0,
            "mention_rate": 0,
            "avg_citation_length": 0,
            "positive_rate": 0,
            "platforms": [],
        }}

    replies = db.query(GeoMonitorReply).filter(
        GeoMonitorReply.monitor_id.in_(monitor_ids),
    ).all()

    total = len(replies)
    mentioned = [r for r in replies if r.mentioned]
    positive = [r for r in mentioned if r.sentiment == "positive"]
    recommended = [r for r in mentioned if r.recommended]

    # 各平台明细
    platform_map = {}
    for r in replies:
        if r.platform not in platform_map:
            platform_map[r.platform] = {"total": 0, "mentioned": 0, "positive": 0, "recommended": 0, "avg_citation": 0}
        platform_map[r.platform]["total"] += 1
        if r.mentioned:
            platform_map[r.platform]["mentioned"] += 1
        if r.sentiment == "positive":
            platform_map[r.platform]["positive"] += 1
        if r.recommended:
            platform_map[r.platform]["recommended"] += 1
    platform_list = []
    for pname, stats in platform_map.items():
        platform_list.append({
            "platform": pname,
            "total": stats["total"],
            "mentioned": stats["mentioned"],
            "mention_rate": round(stats["mentioned"] / stats["total"] * 100) if stats["total"] else 0,
            "positive": stats["positive"],
            "recommended": stats["recommended"],
            "avg_citation": round(sum(r.citation_length for r in replies if r.platform == pname) / stats["total"]) if stats["total"] else 0,
        })

    return {"code": 0, "data": {
        "monitor_count": len(monitors),
        "reply_count": total,
        "mention_rate": round(len(mentioned) / total * 100) if total else 0,
        "avg_citation_length": round(sum(r.citation_length for r in mentioned) / len(mentioned)) if mentioned else 0,
        "positive_rate": round(len(positive) / len(mentioned) * 100) if mentioned else 0,
        "recommended_rate": round(len(recommended) / len(mentioned) * 100) if mentioned else 0,
        "platforms": platform_list,
    }}


# ============================================================
#  本地启发式解析
#  v3.1 起已上提到 ``services/visibility/metrics.py`` —— 手工粘贴通道与
#  自动采集通道必须共用同一套解析口径，否则同一篇回答在两条通道下
#  会算出不同的情感/提及判定，看板数据自相矛盾。
# ============================================================
from ..services.visibility.metrics import parse_ai_reply as _parse_ai_reply  # noqa: E402
