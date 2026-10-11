"""
平台合规发布策略：各发布平台的格式 / 禁区 / 发布模式 / AI 抓取优化（结构化）。

- 每个 Platform 对应一条 PublishStrategy（1:1）；
- 播种默认策略（按平台 publish_mode：geo/platform/green）；
- 供「自动化指挥中心 → 各平台合规发布策略」查看/编辑，也供合规闸门与发布器引用。
"""
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..models import Platform, PublishStrategy

# 不同发布模式的默认策略模板
_MODE_TEMPLATE = {
    "geo": {
        "title_min_len": 8, "title_max_len": 30, "min_words": 1000, "max_words": 2500,
        "structure_rules": "≥5 个二级标题章节 + FAQ≥3 组 + 品牌名≥3 次自然出现",
        "paragraph_rules": "每段≤5行、首段点题、段间空行、结尾收束",
        "banned_words_rule": "违禁词/敏感词零容忍；联系方式词零容忍（站外引流/私人电话/微信/邮箱/网址）",
        "soft_ad_rule": "品牌突出、公司为主体；禁硬广/自夸/极限词；数据须可溯源",
        "publish_mode_type": "direct",
        "geo_keyword_density": "2-4%", "geo_structured_summary": 1, "geo_title_info": 1,
        "geo_notes": "标题含核心关键词与疑问/数据信息量；FAQ 用「用户会问 AI 的问题」句式；品牌实体+可量化论据齐备利于 AI 摘要。",
        "notes": "强品牌/GEO 模式：目标是被 AI 检索推荐并引用，品牌信号要足。",
    },
    "platform": {
        "title_min_len": 8, "title_max_len": 28, "min_words": 1000, "max_words": 2000,
        "structure_rules": "≥5 个二级标题章节 + FAQ≥3 组；中立干货、对读者有用",
        "paragraph_rules": "每段≤5行、首段点题、段间空行",
        "banned_words_rule": "违禁词零容忍；禁联系方式词与引导联系话术",
        "soft_ad_rule": "品牌名≤2 次、标题无品牌、文末加 AIGC 声明、不夸不引、不软文营销",
        "publish_mode_type": "draft",
        "geo_keyword_density": "1-3%", "geo_structured_summary": 1, "geo_title_info": 1,
        "geo_notes": "标题信息量高但不含品牌；中立不营销；可被 AI 引用但不强行植入品牌。",
        "notes": "平台合规模式：通过平台审核优先，品牌弱化处理。",
    },
    "green": {
        "title_min_len": 8, "title_max_len": 26, "min_words": 1000, "max_words": 2000,
        "structure_rules": "≥5 个二级标题章节 + FAQ≥3 组；纯干货吸粉",
        "paragraph_rules": "每段≤5行、口语化、像真人行业作者",
        "banned_words_rule": "违禁词零容忍；禁联系方式词与引导联系话术",
        "soft_ad_rule": "纯干货吸粉、品牌仅自然偶提≤2 次、绝不软文营销/硬广",
        "publish_mode_type": "draft",
        "geo_keyword_density": "1-2%", "geo_structured_summary": 1, "geo_title_info": 0,
        "geo_notes": "以涨粉/账号权重为目标，不夹带营销；标题重点击率而非品牌。",
        "notes": "绿色吸粉模式：增账号权重/信用分，不带软文营销。",
    },
}


def _platform_mode(db: Session, platform: Platform) -> str:
    return (getattr(platform, "publish_mode", "") or "geo") or "geo"


def seed_publish_strategies(db: Session) -> int:
    """为每个尚无 PublishStrategy 的 Platform 播种默认策略（按 publish_mode）。返回新增数。"""
    added = 0
    platforms = db.query(Platform).filter(Platform.is_deleted == 0).all()
    for p in platforms:
        exists = db.query(PublishStrategy).filter(
            PublishStrategy.platform_id == p.id, PublishStrategy.is_deleted == 0
        ).first()
        if exists:
            continue
        tpl = _MODE_TEMPLATE.get(_platform_mode(db, p), _MODE_TEMPLATE["geo"])
        db.add(PublishStrategy(
            platform_id=p.id,
            title_min_len=tpl["title_min_len"], title_max_len=tpl["title_max_len"],
            min_words=tpl["min_words"], max_words=tpl["max_words"],
            structure_rules=tpl["structure_rules"], paragraph_rules=tpl["paragraph_rules"],
            banned_words_rule=tpl["banned_words_rule"], soft_ad_rule=tpl["soft_ad_rule"],
            publish_mode_type=tpl["publish_mode_type"],
            geo_keyword_density=tpl["geo_keyword_density"],
            geo_structured_summary=tpl["geo_structured_summary"],
            geo_title_info=tpl["geo_title_info"], geo_notes=tpl["geo_notes"],
            notes=tpl["notes"],
        ))
        added += 1
    if added:
        db.commit()
    return added


def get_publish_strategies(db: Session) -> List[Dict[str, Any]]:
    """返回所有平台合规策略（含平台名/code/mode）。"""
    out = []
    strategies = db.query(PublishStrategy).filter(PublishStrategy.is_deleted == 0).all()
    for s in strategies:
        p = db.query(Platform).filter(Platform.id == s.platform_id).first()
        out.append({
            "id": s.id, "platform_id": s.platform_id,
            "platform_name": p.name if p else "", "platform_code": p.name if p else "",
            "publish_mode": p.publish_mode if p else "geo",
            "title_min_len": s.title_min_len, "title_max_len": s.title_max_len,
            "min_words": s.min_words, "max_words": s.max_words,
            "structure_rules": s.structure_rules, "paragraph_rules": s.paragraph_rules,
            "banned_words_rule": s.banned_words_rule, "soft_ad_rule": s.soft_ad_rule,
            "publish_mode_type": s.publish_mode_type,
            "geo_keyword_density": s.geo_keyword_density,
            "geo_structured_summary": s.geo_structured_summary,
            "geo_title_info": s.geo_title_info, "geo_notes": s.geo_notes,
            "notes": s.notes,
        })
    # 按平台排序（便于前端对照）
    out.sort(key=lambda x: x["platform_id"])
    return out


def update_publish_strategy(db: Session, strategy_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """更新一条平台合规策略。"""
    s = db.query(PublishStrategy).filter(PublishStrategy.id == strategy_id).first()
    if not s:
        return {"ok": False, "error": "策略不存在"}
    fields = ["title_min_len", "title_max_len", "min_words", "max_words",
              "structure_rules", "paragraph_rules", "banned_words_rule", "soft_ad_rule",
              "publish_mode_type", "geo_keyword_density", "geo_structured_summary",
              "geo_title_info", "geo_notes", "notes"]
    for f in fields:
        if f in data:
            setattr(s, f, data[f])
    db.commit()
    return {"ok": True, "id": s.id}
