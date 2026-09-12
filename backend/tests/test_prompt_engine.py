"""
提示词渲染引擎单元测试
覆盖：
  - extract_variables（占位符提取、去重、转义、内置判定）
  - render_prompt（别名键渲染、缺失键保留原样）
  - BUILTIN_VARIABLES / VARIABLE_DESCRIPTIONS（别名完整性）
  - build_render_context（A2 修复回归：alias 键 word_min/word_max/brand_selling_points/... 必须被填充）
  - 端到端：默认风格模板渲染后不应残留 {word_min}/{brand_selling_points} 等占位符
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Industry, Platform, BrandAsset, ProductionTask
from app.services import prompt_engine


@pytest.fixture
def db():
    """隔离的内存 SQLite 会话，使用与线上相同的 ORM 元数据。"""
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


# ===================== 纯函数：extract_variables =====================

def test_extract_variables_basic():
    tmpl = "针对 {word_min} 到 {word_max} 字，卖点 {brand_selling_points}，重复 {word_min}。"
    vars_ = prompt_engine.extract_variables(tmpl)
    keys = [v["key"] for v in vars_]
    assert keys == ["word_min", "word_max", "brand_selling_points"]
    # 去重
    assert keys.count("word_min") == 1
    # 内置判定
    assert all(v["is_builtin"] for v in vars_)


def test_extract_variables_escaped_braces_excluded():
    tmpl = "转义示例 {{not_var}} 与真实 {platform_name} 占位符。"
    keys = [v["key"] for v in prompt_engine.extract_variables(tmpl)]
    assert "not_var" not in keys
    assert "platform_name" in keys


def test_extract_variables_empty():
    assert prompt_engine.extract_variables("") == []
    assert prompt_engine.extract_variables("无变量纯文本") == []


def test_extract_variables_custom_var_marked_non_builtin():
    vars_ = prompt_engine.extract_variables("自定义变量 {my_custom_var}")
    assert len(vars_) == 1
    assert vars_[0]["key"] == "my_custom_var"
    assert vars_[0]["is_builtin"] is False
    assert vars_[0]["desc"] == "自定义变量"


# ===================== 纯函数：render_prompt =====================

def test_render_prompt_renders_alias_keys():
    template = (
        "请为 {platform_name} 写一篇 {word_min}-{word_max} 字的文章，"
        "突出 {brand_selling_points}，官网 {brand_official_url}。"
    )
    ctx = {
        "platform_name": "小红书",
        "word_min": 300,
        "word_max": 1000,
        "brand_selling_points": "天然成分",
        "brand_official_url": "https://x.com",
    }
    out = prompt_engine.render_prompt(template, ctx)
    assert "{word_min}" not in out
    assert "{word_max}" not in out
    assert "300-1000" in out
    assert "天然成分" in out
    assert "https://x.com" in out


def test_render_prompt_keeps_missing_placeholder():
    out = prompt_engine.render_prompt(
        "正文：{draft_content}，附言：{unknown_var}",
        {"draft_content": "你好"},
    )
    assert out == "正文：你好，附言：{unknown_var}"


# ===================== 常量完整性 =====================

def test_builtin_variables_contains_aliases():
    for key in (
        "word_min", "word_max",
        "brand_selling_points", "brand_official_url",
        "brand_official_website", "platform_tone",
    ):
        assert key in prompt_engine.BUILTIN_VARIABLES, f"{key} 应在 BUILTIN_VARIABLES"
        assert key in prompt_engine.VARIABLE_DESCRIPTIONS, f"{key} 应在 VARIABLE_DESCRIPTIONS"


# ===================== build_render_context：A2 别名键回归 =====================

def test_build_render_context_alias_keys(db):
    ind = Industry(name="美妆", description="美妆行业")
    db.add(ind); db.flush()
    plat = Platform(
        industry_id=ind.id, name="小红书",
        word_count_min=300, word_count_max=1000, compliance_level=3,
    )
    db.add(plat); db.flush()
    brand = BrandAsset(
        industry_id=ind.id, brand_name="润X", official_website="https://x.com",
        is_default=1, unique_selling_points="天然成分",
    )
    db.add(brand); db.flush()
    task = ProductionTask(industry_id=ind.id, platform_id=plat.id)
    db.add(task); db.flush()

    ctx = prompt_engine.build_render_context(db, task, ind.id)

    # 规范名
    assert ctx["platform_word_min"] == 300
    assert ctx["platform_word_max"] == 1000
    assert ctx["selling_points"] == "天然成分"
    # 防泄露设计：官网/联系方式绝不注入创作上下文，恒为空串（见 build_render_context 注释）
    assert ctx["official_website"] == ""
    # 别名键（A2 修复核心）
    assert ctx["word_min"] == 300
    assert ctx["word_max"] == 1000
    assert ctx["brand_selling_points"] == "天然成分"
    # 官网别名同样恒为空（源自 official_website）
    assert ctx["brand_official_url"] == ""
    assert ctx["brand_official_website"] == ""


def test_render_default_style_template_no_leftover(db):
    """端到端回归：默认初稿模板使用的别名占位符必须被真实值替换。"""
    ind = Industry(name="美妆"); db.add(ind); db.flush()
    plat = Platform(
        industry_id=ind.id, name="小红书",
        word_count_min=300, word_count_max=1000, compliance_level=3,
    )
    db.add(plat); db.flush()
    brand = BrandAsset(
        industry_id=ind.id, brand_name="润X", official_website="https://x.com",
        is_default=1, unique_selling_points="天然成分",
    )
    db.add(brand); db.flush()
    task = ProductionTask(industry_id=ind.id, platform_id=plat.id)
    db.add(task); db.flush()

    ctx = prompt_engine.build_render_context(db, task, ind.id)
    template = (
        "请为 {platform_name} 撰写一篇 {word_min}-{word_max} 字的软文，"
        "核心卖点为 {brand_selling_points}，官网见 {brand_official_url}。"
    )
    out = prompt_engine.render_prompt(template, ctx)

    assert "{word_min}" not in out
    assert "{word_max}" not in out
    assert "{brand_selling_points}" not in out
    assert "{brand_official_url}" not in out
    assert "300-1000" in out
    assert "天然成分" in out
    # 防泄露设计：官网占位符被替换为空串，真实官网绝不出现在渲染结果中
    assert "https://x.com" not in out
