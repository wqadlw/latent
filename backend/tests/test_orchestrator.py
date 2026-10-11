# -*- coding: utf-8 -*-
"""orchestrator.py 单测：步骤注册表 + 综合质量闸门组合逻辑。

用 mock 锁定 run_full_check / compute_geo_score / check_platform_compliance 的返回，
只验证「综合闸门如何按发布模式组合」这一编排逻辑（即原 _run_review 的收敛点），
不依赖规则引擎内部评分，保证稳定可重复。
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.routers.automation_prompts import workflow_meta  # noqa: E402
from app.services.llm_scheduler import ROLE_BY_STEP as SCHEDULER_ROLE_BY_STEP  # noqa: E402
from app.services.orchestrator import (  # noqa: E402
    ROLE_BY_STEP,
    STEP_PROMPT_KEYS,
    get_step_defs,
    run_quality_gate,
)


# ---- 1) 步骤注册表 ----------------------------------------------------------
def test_get_step_defs_shape():
    steps = get_step_defs("deepseek")
    assert isinstance(steps, list)
    assert len(steps) == 10
    for s in steps:
        assert isinstance(s, tuple) and len(s) == 4
        no, key, title, agent = s
        assert isinstance(no, int) and isinstance(key, str)
        assert agent in ("planner", "writer", "system", "dual")


def test_get_step_defs_keys_ordered():
    steps = get_step_defs("deepseek")
    keys = [k for _, k, _, _ in steps]
    assert keys == [
        "connect", "clarify", "outline", "draft", "depolish",
        "geo", "review", "revise", "confirm", "publish",
    ]


def test_get_step_defs_engine_label_differs():
    deep = get_step_defs("deepseek")
    mock = get_step_defs("mock")
    assert deep[0][2] != mock[0][2]           # connect 标题带引擎名
    assert deep[1][2] != mock[1][2]           # clarify 标题也带引擎名（deepseek=创作简报 / mock=模拟豆包）
    assert deep[0][0] == mock[0][0] == 1      # step_no 一致


def test_step_prompt_keys_and_roles():
    assert STEP_PROMPT_KEYS["clarify"] == "PLANNER_CLARIFY_PROMPT"
    assert STEP_PROMPT_KEYS["outline"] == "PLANNER_OUTLINE_PROMPT"
    assert STEP_PROMPT_KEYS["draft"] == "STAGE_draft"
    assert STEP_PROMPT_KEYS["depolish"] == "STAGE_depolish"
    assert STEP_PROMPT_KEYS["geo"] == "STAGE_geo"
    assert STEP_PROMPT_KEYS["review"] == "PLANNER_REVIEW_PROMPT"
    assert STEP_PROMPT_KEYS["revise"] == "PLANNER_DIRECTIVE_PROMPT"
    assert ROLE_BY_STEP["clarify"] == "research"
    assert ROLE_BY_STEP["draft"] == "writing"
    assert ROLE_BY_STEP["review"] == "review"
    assert ROLE_BY_STEP["confirm"] == "human"
    assert ROLE_BY_STEP["publish"] == "system"


def test_role_by_step_superset_of_scheduler():
    """orchestrator.ROLE_BY_STEP 必须以真实调度源（llm_scheduler）为基底，
    覆盖其全部步骤且角色一致——否则后端会出现两份角色映射漂移。"""
    for k, v in SCHEDULER_ROLE_BY_STEP.items():
        assert k in ROLE_BY_STEP, f"orchestrator.ROLE_BY_STEP 缺失调度步骤 {k}"
        assert ROLE_BY_STEP[k] == v, f"步骤 {k} 角色不一致：{ROLE_BY_STEP[k]} != {v}"


def test_workflow_meta_endpoint_shape():
    """/meta 端点返回前端委托所需的单一真源；无 DB 依赖，可直调。"""
    r = workflow_meta()
    assert r["code"] == 0
    d = r["data"]
    assert d["step_prompt_keys"]["draft"] == "STAGE_draft"
    assert d["step_prompt_keys"]["clarify"] == "PLANNER_CLARIFY_PROMPT"
    assert d["role_by_step"]["draft"] == "writing"
    assert d["role_by_step"]["clarify"] == "research"
    # 显示用角色（无 AI 调用步骤）也须暴露给前端
    assert d["role_by_step"]["confirm"] == "human"
    assert d["role_by_step"]["publish"] == "system"


# ---- 2) 综合闸门组合逻辑（mock 锁定规则引擎） ---------------------------------
def _patch_gate(compliance_pass, geo_pass, platform_pass=None):
    """构造三层规则引擎的 mock 返回值。

    注意：run_quality_gate 内的 _compliance_gate 会用 compliance["pass"] / anti_ai["pass"]
    重新计算 overall_pass，所以「合规是否通过」由这两项的 pass 决定，而非外层 overall_pass。
    """
    comp = {"pass": bool(compliance_pass), "issues": ["合规建议A"]}
    anti = {"pass": bool(compliance_pass), "issues": []}
    full = {
        "compliance": comp, "anti_ai": anti, "ai_seo": {"pass": True},
        "format": {"pass": True},
        "overall_pass": bool(compliance_pass),
        "issues": [] if compliance_pass else ["硬广命中"],
    }
    geo = {
        "score": 80 if geo_pass else 40,
        "gate_pass": bool(geo_pass),
        "issues": [] if geo_pass else ["GEO 信号不足"],
        "dimensions": {}, "signals_present": [], "mind_resonance": {}, "diagnosis": {},
    }
    plat = {"pass": bool(platform_pass), "issues": [] if platform_pass else ["软文特征命中"]}
    return full, geo, plat


def test_gate_geo_mode_double_gate_pass():
    full, geo, plat = _patch_gate(True, True)
    with patch("app.services.orchestrator.run_full_check", return_value=full), \
         patch("app.services.orchestrator.compute_geo_score", return_value=geo):
        r = run_quality_gate("正文", {}, mode="geo", output_format="markdown", title="标题")
    assert r["compliance_pass"] is True
    assert r["geo_score"] == 80
    assert r["gate_pass"] is True


def test_gate_geo_mode_geo_fail_blocks():
    full, geo, plat = _patch_gate(True, False)
    with patch("app.services.orchestrator.run_full_check", return_value=full), \
         patch("app.services.orchestrator.compute_geo_score", return_value=geo):
        r = run_quality_gate("正文", {}, mode="geo", output_format="markdown", title="标题")
    assert r["compliance_pass"] is True
    assert r["gate_pass"] is False          # geo 模式双闸门：GEO 不达标即拦截


def test_gate_geo_mode_compliance_fail_blocks():
    full, geo, plat = _patch_gate(False, True)
    with patch("app.services.orchestrator.run_full_check", return_value=full), \
         patch("app.services.orchestrator.compute_geo_score", return_value=geo):
        r = run_quality_gate("正文", {}, mode="geo", output_format="markdown", title="标题")
    assert r["gate_pass"] is False


def test_gate_platform_mode_only_compliance():
    # platform 模式：合规过但 GEO 不过 → 仍放行（GEO 只作建议）
    full, geo, plat = _patch_gate(True, False, platform_pass=True)
    with patch("app.services.orchestrator.run_full_check", return_value=full), \
         patch("app.services.orchestrator.compute_geo_score", return_value=geo), \
         patch("app.services.orchestrator.check_platform_compliance", return_value=plat):
        r = run_quality_gate("正文", {}, mode="platform", output_format="markdown", title="标题")
    assert r["platform_compliance"]["pass"] is True
    assert r["gate_pass"] is True


def test_gate_platform_mode_softad_blocks():
    # platform 模式：软文特征命中 → 闸门拦截（即便基础合规通过）
    full, geo, plat = _patch_gate(True, True, platform_pass=False)
    with patch("app.services.orchestrator.run_full_check", return_value=full), \
         patch("app.services.orchestrator.compute_geo_score", return_value=geo), \
         patch("app.services.orchestrator.check_platform_compliance", return_value=plat):
        r = run_quality_gate("正文", {}, mode="platform", output_format="markdown", title="标题")
    assert r["gate_pass"] is False


def test_gate_official_mdx_ignores_geo_and_softad():
    # 官网 mdx 模式：只认基础合规闸门，GEO 与软文自检均不阻塞
    full, geo, plat = _patch_gate(True, False, platform_pass=False)
    with patch("app.services.orchestrator.run_full_check", return_value=full), \
         patch("app.services.orchestrator.compute_geo_score", return_value=geo), \
         patch("app.services.orchestrator.check_platform_compliance", return_value=plat):
        r = run_quality_gate("正文", {}, mode="geo", output_format="mdx", title="标题")
    assert r["gate_pass"] is True           # mdx → 仅基础合规（已通过）


def test_gate_issues_merge_with_prefix():
    full, geo, plat = _patch_gate(True, False, platform_pass=False)
    with patch("app.services.orchestrator.run_full_check", return_value=full), \
         patch("app.services.orchestrator.compute_geo_score", return_value=geo), \
         patch("app.services.orchestrator.check_platform_compliance", return_value=plat):
        r = run_quality_gate("正文", {}, mode="platform", output_format="markdown", title="标题")
    assert any(i.startswith("[平台合规·A级]") for i in r["issues"])
    assert any(i.startswith("[GEO优化·B级]") for i in r["issues"])
