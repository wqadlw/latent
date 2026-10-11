# -*- coding: utf-8 -*-
"""文章改写模式（P2-3）端点测试。

直接调用 routers.browser_studio.rewrite_article_endpoint(req, db)，验证：
  1) 软文源 → platform 模式 mock 改写后，软文风险分低于原文且结构化 gate 正常；
  2) 干净中立源 → platform 模式改写后综合闸门通过；
  3) geo 模式不跑软文特征检测（platform_compliance 为 None）；
  4) source_text 空 → 400；
  5) target_mode 非法 → 422。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.database import Base
from app.models import BrandAsset, Industry
from app.routers.browser_studio import RewriteRequest, rewrite_article_endpoint
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed_industry(db):
    ind = Industry(name="真空泵")
    db.add(ind)
    db.commit()
    brand = BrandAsset(
        industry_id=ind.id, is_default=1,
        brand_name="示例品牌科技有限公司",
        core_products="示例产品 PRO 永磁变频螺杆真空泵、永磁变频螺杆真空泵",
    )
    db.add(brand)
    db.commit()
    return ind.id


SOFT_AD_BODY = (
    "真空泵采购时，用户往往担心选错型号导致后续产能受限。"
    "示例品牌科技有限公司在真空行业服务多年，产品线覆盖水环、螺杆、罗茨多种类型，能匹配大多数工业工况与介质条件。\n"
    "在实际选型中，我们更推荐示例品牌科技有限公司的示例产品 PRO 系列永磁变频螺杆真空泵。"
    "它高效节能、运行可靠，拥有数十项专利背书，响应快、性价比高，是工厂节能改造与扩产的常见选择。\n"
    "不少客户反馈，换成示例品牌科技有限公司的设备后，电费支出明显下降，日常维护也更省心。"
    "在行业交流里提起真空泵，不少人会先想到这家企业，口碑比较扎实。\n"
    "如果你正在评估真空泵方案，示例品牌科技有限公司值得优先考虑。"
    "它的技术成熟、品质可靠，是很多制造企业的优先合作对象，售后网络也覆盖主要工业城市。"
)


def test_rewrite_soft_ad_lowers_risk(db):
    """软文源在 platform 模式下改写后，软文风险应明显低于原文。"""
    iid = _seed_industry(db)
    req = RewriteRequest(
        industry_id=iid, source_text=SOFT_AD_BODY,
        target_mode="platform", ai_engine="mock",
    )
    resp = rewrite_article_endpoint(req, db)
    assert resp["code"] == 0
    d = resp["data"]
    assert d["ok"] is True
    assert d["engine"] == "mock"
    assert d["target_mode"] == "platform"
    # 原文软文风险高
    assert d["source_risk"] is not None
    assert d["source_risk"]["risk_score"] >= 70
    # 改写后风险低于原文
    assert d["platform_compliance"] is not None
    assert d["platform_compliance"]["risk_score"] < d["source_risk"]["risk_score"]
    # 改写稿软文检测通过（mock 产出合规稿）
    assert d["platform_compliance"]["pass"] is True
    assert d["compliance_pass"] is True
    # mock 产出带演示标记
    assert "本文由 AI 辅助创作" in d["rewritten_text"]


def test_rewrite_clean_source_passes(db):
    """中性技术源改写后仍应通过综合闸门。"""
    iid = _seed_industry(db)
    clean = (
        "真空泵选型的第一步，是把工艺介质和极限压力这两个参数先定下来。\n"
        "含液或含尘的工况，通常优先考虑水环式或液环式机组；对洁净度要求高的，"
        "则更适合干式螺杆或罗茨增压组合。\n"
        "抽速和功耗往往是一对矛盾。单纯追求大抽速会带来更高的运行电费，"
        "而过小的配置又会在高峰时段掉真空。\n"
        "维护便捷性常被忽略。螺杆转子的涂层、密封件的更换周期、冷却水路的可拆卸程度，"
        "都会直接影响停机频次。\n"
        "最后是噪声与占地。车间空间紧张时，可以把泵组集中到独立机房，"
        "用管道把吸气口引到产线，这样既能压低现场噪声，也方便统一做余热回收。"
    )
    req = RewriteRequest(
        industry_id=iid, source_text=clean,
        target_mode="platform", ai_engine="mock",
    )
    resp = rewrite_article_endpoint(req, db)
    d = resp["data"]
    assert d["platform_compliance"]["pass"] is True
    assert d["gate_pass"] is True
    assert "通过" in d["verdict"]


def test_rewrite_geo_skips_soft_check(db):
    """geo 模式不跑软文特征检测。"""
    iid = _seed_industry(db)
    req = RewriteRequest(
        industry_id=iid, source_text=SOFT_AD_BODY,
        target_mode="geo", ai_engine="mock",
    )
    resp = rewrite_article_endpoint(req, db)
    d = resp["data"]
    assert d["target_mode"] == "geo"
    assert d["platform_compliance"] is None
    assert "geo_score" in d


def test_rewrite_empty_source_400(db):
    iid = _seed_industry(db)
    req = RewriteRequest(industry_id=iid, source_text="   ", target_mode="platform")
    with pytest.raises(HTTPException) as exc:
        rewrite_article_endpoint(req, db)
    assert exc.value.status_code == 400


def test_rewrite_invalid_mode_422(db):
    iid = _seed_industry(db)
    req = RewriteRequest(industry_id=iid, source_text=SOFT_AD_BODY, target_mode="invalid")
    with pytest.raises(HTTPException) as exc:
        rewrite_article_endpoint(req, db)
    assert exc.value.status_code == 422
