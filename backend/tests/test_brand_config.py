"""
品牌配置单一事实来源（app/brand_config.py）守护测试。

背景：品牌名 / 官网 / 地域原先硬编码散落在 prompt_engine / doubao_studio /
orchestrator / models 等多处，导致「开源版」与「客户定制版」必须维护两份代码，
且极易漏改（历史上就曾漏掉过注释里的真实联系方式）。

现统一收敛到 app/brand_config.py（读 brand.config.json 或环境变量），本测试守护：

  1. 默认值齐备、别名回退逻辑正确；
  2. 关键模板在注入配置值后，**渲染占位符仍完整保留** —— 这是最核心的不变量：
     f-string 注入品牌值时若忘记转义 ``{}``，占位符会被误求值，渲染引擎随即失效；
  3. 地域变量已纳入渲染白名单，可被正常渲染；
  4. 业务源码中不再残留品牌 / 地域字面量。
"""
import inspect

import app.brand_config as brand_config
import app.constants as constants
from app.services import prompt_engine


def test_defaults_present():
    """不配置任何东西时，必须有一套可用的通用默认值（开源开箱即用）。"""
    assert brand_config.BRAND_NAME
    assert brand_config.BRAND_FULL_NAME
    assert brand_config.BRAND_PRODUCT
    assert brand_config.OFFICIAL_SITE_URL.startswith("http")
    assert brand_config.REGION
    assert brand_config.REGION_CITY


def test_aliases_fallback_and_dedup():
    """未显式配置别名时，回退为「品牌名 + 产品线名」，非空且去重。"""
    assert brand_config.BRAND_ALIASES
    assert len(brand_config.BRAND_ALIASES) == len(set(brand_config.BRAND_ALIASES))


def test_mdx_prompt_injects_brand_but_keeps_placeholders():
    """核心不变量：品牌值被注入为字面量，而 {xxx} 渲染占位符必须原样保留。

    若占位符被 f-string 误求值（漏写双花括号），渲染引擎将无法替换，
    提示词会丢失品牌 / 官网 / 知识库等上下文，且不会有任何报错 —— 静默失效。
    """
    tpl = prompt_engine.OFFICIAL_MDX_PROMPT
    # 品牌值已注入
    assert brand_config.BRAND_FULL_NAME in tpl
    # 渲染占位符仍完整保留
    for key in (
        "{official_site_url}", "{brand_name}", "{core_products}",
        "{selling_points}", "{subject}", "{knowledge_content}",
    ):
        assert key in tpl, f"渲染占位符被破坏：{key}"


def test_region_variables_renderable():
    """brand_region / brand_region_city 必须同时在白名单与渲染上下文中可用。"""
    for key in ("brand_region", "brand_region_city"):
        assert key in constants.SUPPORTED_RENDER_VARIABLES

    out = prompt_engine.render_prompt(
        "地域：{brand_region} / {brand_region_city}",
        {
            "brand_region": brand_config.REGION,
            "brand_region_city": brand_config.REGION_CITY,
        },
    )
    assert brand_config.REGION in out
    assert brand_config.REGION_CITY in out
    assert "{brand_region}" not in out


def test_official_site_url_matches_config():
    """官网常量必须与品牌配置同源，不得各自硬编码。"""
    assert prompt_engine.OFFICIAL_SITE_URL == brand_config.OFFICIAL_SITE_URL


def test_as_dict_exposes_all_fields():
    d = brand_config.as_dict()
    for key in (
        "brand_name", "brand_full_name", "brand_product",
        "official_site_url", "region", "region_city", "brand_aliases",
    ):
        assert key in d


def test_no_hardcoded_brand_in_services():
    """业务源码不得再硬编码品牌 / 地域 / 官网字面量（应全部走配置）。"""
    from app.services import doubao_studio, orchestrator

    for mod in (prompt_engine, doubao_studio, orchestrator):
        src = inspect.getsource(mod)
        for literal in ("示例品牌", "示例产品", "华东", "www.example.com"):
            assert literal not in src, f"{mod.__name__} 仍硬编码「{literal}」"
