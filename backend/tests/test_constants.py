"""
常量单一事实来源（app/constants.py）守护测试。

背景：原先 BUILTIN_VARIABLES 在 services/prompt_engine.py（set，渲染 is_builtin 白名单）
与 routers/prompt_library.py（list[dict]，前端变量面板）两处定义，注释要求「保持一致」
但无强制约束，历史上曾因不一致导致默认模板占位符渲染残留（A2 缺陷）。
现已收敛到 app/constants.py 单一来源，本测试守护「面板键 ⊆ 渲染白名单」不变量，
防止未来任一处漂移重新引入残留占位符风险。
"""
import app.constants as constants
import app.services.prompt_engine as prompt_engine
import app.routers.prompt_library as prompt_library
from app.models import PLATFORM_PRESETS


def test_canonical_definitions_present():
    assert isinstance(constants.BUILTIN_VARIABLES, list)
    assert isinstance(constants.SUPPORTED_RENDER_VARIABLES, set)
    assert len(constants.BUILTIN_VARIABLES) > 0
    assert len(constants.SUPPORTED_RENDER_VARIABLES) > 0


def test_re_exports_resolve():
    # prompt_engine 通过 re-export 暴露渲染白名单集合（原名 BUILTIN_VARIABLES 保持兼容）
    assert isinstance(prompt_engine.BUILTIN_VARIABLES, set)
    assert prompt_engine.BUILTIN_VARIABLES == constants.SUPPORTED_RENDER_VARIABLES
    # prompt_library 通过 re-export 暴露面板列表
    assert isinstance(prompt_library.BUILTIN_VARIABLES, list)
    assert prompt_library.BUILTIN_VARIABLES == constants.BUILTIN_VARIABLES


def test_panel_keys_subset_of_render_whitelist():
    """核心不变量：前端面板展示的每一个变量都必须在渲染引擎白名单内，
    否则该变量在渲染时原样残留（历史 A2 缺陷）。"""
    panel_keys = {v["key"] for v in constants.BUILTIN_VARIABLES}
    render_keys = constants.SUPPORTED_RENDER_VARIABLES
    orphans = panel_keys - render_keys
    assert not orphans, f"面板存在渲染引擎不支持的变量键（会残留占位符）: {sorted(orphans)}"


def test_panel_keys_unique():
    keys = [v["key"] for v in constants.BUILTIN_VARIABLES]
    assert len(keys) == len(set(keys)), "BUILTIN_VARIABLES 存在重复 key"


def test_platform_presets_single_source():
    """PLATFORM_PRESETS 本就是单一来源（仅定义于 models.py），此处仅做健全性断言。"""
    assert isinstance(PLATFORM_PRESETS, list) and len(PLATFORM_PRESETS) > 0
    names = [p["name"] for p in PLATFORM_PRESETS]
    assert len(names) == len(set(names)), "PLATFORM_PRESETS 存在重复平台名"
