# -*- coding: utf-8 -*-
"""创作过程可视化端点（P2-2）测试。

直接调用 routers.browser_studio.run_conversation(run_id, db)，验证：
  1) 聚合 run.revise_rounds（主编↔写手整改多轮对话）正确解析；
  2) 各步按 agent 分组（主编 planner / 写手 writer）发言正确提取；
  3) 运行不存在返回 404；
  4) revise_rounds 非法 JSON 容错为 [] 不崩；
  5) 无任何步骤与整改记录时 has_data=False。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.database import Base
from app.models import BrandAsset, BrowserStudioStep, Industry, ProductionTask
from app.routers.browser_studio import run_conversation
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


def _seed_run(db, revise_rounds=None, steps=None):
    ind = Industry(name="真空泵")
    db.add(ind)
    db.commit()
    brand = BrandAsset(
        industry_id=ind.id, is_default=1,
        brand_name="示例品牌科技有限公司",
        core_products="示例产品 PRO 永磁变频螺杆真空泵",
    )
    db.add(brand)
    db.commit()
    run = ProductionTask(
        mode="auto", industry_id=ind.id, platform="sohu",
        publish_mode="platform", output_format="markdown",
        brand_asset_id=brand.id, status="review",
        revise_rounds=(revise_rounds if revise_rounds is not None else ""),
    )
    db.add(run)
    db.commit()
    if steps:
        for st in steps:
            s = BrowserStudioStep(
                run_id=run.id, step_no=st["step_no"], step_key=st["step_key"],
                agent=st["agent"], title=st.get("title", st["step_key"]),
                status="done", result_json=st.get("result_json", ""),
                request_payload=st.get("request_payload", ""),
                extracted_result=st.get("extracted_result", ""),
            )
            db.add(s)
        db.commit()
    return run


GOOD_ROUNDS = '[{"round":1,"planner_directives":"本轮请补充数据来源并弱化品牌口吻","editor_review":"改写后数据更扎实，达标","before":"旧稿……","after":"新稿……","geo_score":78,"gate_pass":true}]'

SAMPLE_STEPS = [
    {"step_no": 2, "step_key": "clarify", "agent": "planner",
     "title": "主编·明晰选题", "result_json": '{"clarified":"面向工厂设备主管的真空泵选型简报"}'},
    {"step_no": 3, "step_key": "outline", "agent": "planner",
     "title": "主编·拟定大纲", "result_json": '{"outline":"1.工况 2.选型 3.节能 4.案例"}'},
    {"step_no": 4, "step_key": "draft", "agent": "writer",
     "title": "写手·初稿", "result_json": '{"draft":"真空泵选型初稿正文……"}'},
    {"step_no": 6, "step_key": "geo", "agent": "writer",
     "title": "写手·GEO终稿", "result_json": '{"geo":"真空泵选型GEO终稿正文……"}'},
    {"step_no": 7, "step_key": "review", "agent": "planner",
     "title": "主编·评审", "result_json": '{"editor_review":"结构清晰，建议补案例"}'},
    {"step_no": 8, "step_key": "revise", "agent": "planner",
     "title": "主编·整改指令", "result_json": '{"planner_directives":"补充两个客户案例","after":"整改后终稿……"}'},
]


def test_conversation_aggregates_rounds_and_agents(db):
    run = _seed_run(db, revise_rounds=GOOD_ROUNDS, steps=SAMPLE_STEPS)
    resp = run_conversation(run.id, db)
    d = resp["data"]
    assert d["has_data"] is True
    assert len(d["revise_rounds"]) == 1
    assert d["revise_rounds"][0]["round"] == 1
    assert d["revise_rounds"][0]["gate_pass"] is True
    # 主编步骤：clarify/outline/review/revise（4），写手步骤：draft/geo（2）
    planner = d["planner_messages"]
    writer = d["writer_messages"]
    assert [m["step_key"] for m in planner] == ["clarify", "outline", "review", "revise"]
    assert [m["step_key"] for m in writer] == ["draft", "geo"]
    # 文本提取正确（命中 result_json 已知语义字段）
    clarify = next(m for m in planner if m["step_key"] == "clarify")
    assert "真空泵选型简报" in clarify["text"]
    geo = next(m for m in writer if m["step_key"] == "geo")
    assert "GEO终稿正文" in geo["text"]


def test_conversation_404(db):
    with pytest.raises(HTTPException) as exc:
        run_conversation(99999, db)
    assert exc.value.status_code == 404


def test_conversation_malformed_rounds_tolerated(db):
    # revise_rounds 非法 JSON → 容错为 []，不抛异常
    run = _seed_run(db, revise_rounds="{不是合法json", steps=SAMPLE_STEPS[:2])
    resp = run_conversation(run.id, db)
    d = resp["data"]
    assert d["revise_rounds"] == []
    assert d["has_data"] is True  # 仍有 steps 发言


def test_conversation_no_data(db):
    run = _seed_run(db, revise_rounds="", steps=None)
    resp = run_conversation(run.id, db)
    assert resp["data"]["has_data"] is False
    assert resp["data"]["planner_messages"] == []
    assert resp["data"]["writer_messages"] == []
