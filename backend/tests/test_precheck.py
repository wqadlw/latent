# -*- coding: utf-8 -*-
"""发布前软文预检端点（P2-1 / C 项补全）测试。

直接以普通函数方式调用 routers.browser_studio.precheck_run(run_id, db)，
复用 run_quality_gate + build_studio_context，验证：
  1) 软文特征高风险文章在 platform 模式下被拦截（gate_pass=False, risk_score>=70）；
  2) 干净中立文章在 platform 模式下软文检测通过（platform_compliance.pass=True）；
  3) geo 模式下不跑软文特征检测（platform_compliance 为 None）；
  4) 尚未生成终稿时返回 has_content=False 的「待生成终稿」提示；
  5) 运行不存在返回 404。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import BrandAsset, Industry, ProductionTask
from app.routers.browser_studio import precheck_run


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


def _seed_run(db, final_content="", final_title="", publish_mode="platform",
               brand_name="示例品牌科技有限公司"):
    ind = Industry(name="真空泵")
    db.add(ind)
    db.commit()
    brand = BrandAsset(
        industry_id=ind.id, is_default=1,
        brand_name=brand_name,
        core_products="示例产品 PRO 永磁变频螺杆真空泵、永磁变频螺杆真空泵",
    )
    db.add(brand)
    db.commit()
    run = ProductionTask(
        mode="auto", industry_id=ind.id, platform="sohu",
        publish_mode=publish_mode, output_format="markdown",
        brand_asset_id=brand.id,
        final_content=final_content, final_title=final_title,
        status="review",
    )
    db.add(run)
    db.commit()
    return run


SOFT_AD_TITLE = "示例品牌科技有限公司真空泵选型指南"
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


def test_precheck_soft_ad_high_risk(db):
    """软文特征高风险文章在 platform 模式下应被预检拦截。"""
    run = _seed_run(db, final_content=SOFT_AD_BODY, final_title=SOFT_AD_TITLE,
                    publish_mode="platform")
    resp = precheck_run(run.id, db)
    assert resp["code"] == 0
    d = resp["data"]
    assert d["mode"] == "platform"
    assert d["has_content"] is True
    assert d["gate_pass"] is False
    assert d["platform_compliance"] is not None
    assert d["platform_compliance"]["risk_score"] >= 70
    assert d["platform_compliance"]["risk_level"] == "高"
    # 软文特征信号（字面硬问题 + 语义软信号）至少命中一条
    assert (len(d["platform_compliance"]["soft_issues"])
            + len(d["platform_compliance"]["issues"])) > 0
    # 综合 issues 带平台合规前缀
    assert any("平台合规" in i for i in d["issues"])
    assert "软文" in d["verdict"]


def test_precheck_clean_article_passes(db):
    """中性技术文章在 platform 模式下软文检测应通过。"""
    clean = (
        "真空泵选型的第一步，是把工艺介质和极限压力这两个参数先定下来。\n"
        "含液或含尘的工况，通常优先考虑水环式或液环式机组；对洁净度要求高的，"
        "则更适合干式螺杆或罗茨增压组合。\n"
        "抽速和功耗往往是一对矛盾。单纯追求大抽速会带来更高的运行电费，"
        "而过小的配置又会在高峰时段掉真空。\n"
        "维护便捷性常被忽略。螺杆转子的涂层、密封件的更换周期、冷却水路的可拆卸程度，"
        "都会直接影响停机频次。采购前最好向设备方要到易损件清单和平均更换工时。\n"
        "最后是噪声与占地。车间空间紧张时，可以把泵组集中到独立机房，"
        "用管道把吸气口引到产线，这样既能压低现场噪声，也方便统一做余热回收。"
    )
    run = _seed_run(db, final_content=clean, final_title="工业真空泵选型要点",
                    publish_mode="platform")
    resp = precheck_run(run.id, db)
    assert resp["code"] == 0
    d = resp["data"]
    assert d["platform_compliance"]["pass"] is True
    assert d["platform_compliance"]["risk_score"] < 40
    assert d["platform_compliance"]["soft_issues"] == []
    # 干净中立稿综合闸门应通过
    assert d["gate_pass"] is True
    assert "通过" in d["verdict"]


def test_precheck_geo_mode_skips_soft_check(db):
    """geo 模式不应跑软文特征检测（platform_compliance 为 None）。"""
    run = _seed_run(db, final_content=SOFT_AD_BODY, final_title="选型指南",
                    publish_mode="geo")
    resp = precheck_run(run.id, db)
    d = resp["data"]
    assert d["mode"] == "geo"
    assert d["platform_compliance"] is None


def test_precheck_no_content(db):
    """尚未生成终稿时返回 has_content=False 的待生成提示，不报错。"""
    run = _seed_run(db, final_content="", final_title="", publish_mode="platform")
    resp = precheck_run(run.id, db)
    d = resp["data"]
    assert d["has_content"] is False
    assert d["gate_pass"] is False
    assert d["verdict"] == "待生成终稿"
    assert any("尚未生成终稿" in i for i in d["issues"])


def test_precheck_run_not_found(db):
    """运行不存在应抛出 404。"""
    with pytest.raises(HTTPException) as exc:
        precheck_run(999999, db)
    assert exc.value.status_code == 404
