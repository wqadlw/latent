"""手动流（ProductionTask）综合质量闸门测试。

覆盖 P1 收敛后补齐的缺口：手动流此前只调 GEO 评分、缺平台合规硬闸门，
现改为复用 orchestrator.run_quality_gate（与自动流同一真源）。
"""
import pytest
from app.database import Base
from app.models import BrandAsset, Industry, Platform, ProductionTask
from app.routers.production import (
    _merge_safety_report,
    _resolve_task_publish_mode,
    apply_geo_finalize,
    run_manual_quality_gate,
)
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


def _seed(db, publish_mode="geo", output_format="markdown"):
    ind = Industry(name="真空泵")
    db.add(ind)
    db.commit()
    plat = Platform(industry_id=ind.id, name="搜狐号",
                    publish_mode=publish_mode, output_format=output_format)
    db.add(plat)
    brand = BrandAsset(industry_id=ind.id, is_default=1,
                       brand_name="示例品牌科技有限公司",
                       core_products="示例产品 PRO 永磁变频螺杆真空泵")
    db.add(brand)
    db.commit()
    task = ProductionTask(industry_id=ind.id, platform_id=plat.id, title="测试稿")
    db.add(task)
    db.commit()
    return ind, plat, task


# ---------- _resolve_task_publish_mode ----------

def test_resolve_publish_mode_from_platform(db):
    _, _, task = _seed(db, publish_mode="platform", output_format="markdown")
    mode, out = _resolve_task_publish_mode(task, db)
    assert mode == "platform"
    assert out == "markdown"


def test_resolve_publish_mode_official_mdx(db):
    _, _, task = _seed(db, publish_mode="geo", output_format="mdx")
    mode, out = _resolve_task_publish_mode(task, db)
    assert out == "mdx"


def test_resolve_publish_mode_default_when_no_platform(db):
    ind = Industry(name="x")
    db.add(ind)
    db.commit()
    task = ProductionTask(industry_id=ind.id)
    db.add(task)
    db.commit()
    mode, out = _resolve_task_publish_mode(task, db)
    assert (mode, out) == ("geo", "markdown")


# ---------- run_manual_quality_gate ----------

def test_manual_gate_returns_gate_contract(db):
    _, _, task = _seed(db)
    gate = run_manual_quality_gate(db, task, "这是一篇关于工业真空泵选型的正文。" * 30, "选型指南")
    # 契约键齐全（与自动流 run_quality_gate 一致）
    for k in ("compliance_pass", "geo_score", "gate_pass", "issues", "mode", "output_format"):
        assert k in gate
    assert gate["mode"] == "geo"


def test_manual_gate_catches_forbidden_words(db):
    """含硬广/极限词的文本，平台合规硬闸门应判不通过。"""
    _, _, task = _seed(db, publish_mode="platform")
    bad = "本产品效果绝对第一，全球唯一，100%无故障，立即拨打电话 13800000000 抢购！" * 10
    gate = run_manual_quality_gate(db, task, bad, "促销")
    assert gate["compliance_pass"] is False
    assert gate["gate_pass"] is False
    assert any("平台合规" in i for i in gate["issues"])


# ---------- _merge_safety_report ----------

def test_merge_safety_report_pass():
    gate = {"gate_pass": True, "mode": "geo", "issues": []}
    out = _merge_safety_report("AI建议：加个小标题", gate)
    assert "AI建议：加个小标题" in out
    assert "✅ 通过" in out
    assert "未检出" in out


def test_merge_safety_report_fail_lists_issues():
    gate = {"gate_pass": False, "mode": "platform",
            "issues": ["[平台合规·A级] 命中极限词：唯一"]}
    out = _merge_safety_report("", gate)
    assert "⚠️ 未通过" in out
    assert "唯一" in out


# ---------- apply_geo_finalize 集成 ----------

def test_apply_geo_finalize_wires_gate(db):
    """终检写回后：safety_report 含闸门结论、返回体含 quality_gate。"""
    _, _, task = _seed(db)
    task.rewrite_content = "这是一篇关于工业真空泵节能选型的深度正文内容。" * 30
    db.commit()
    ai_result = "标题：真空泵节能选型指南\n正文：这是一篇关于工业真空泵节能选型的深度正文内容。" * 1
    data = apply_geo_finalize(db, task, ai_result)
    assert "quality_gate" in data
    assert "gate_pass" in data["quality_gate"]
    assert "平台合规闸门" in (task.safety_report or "")
