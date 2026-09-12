"""
本地规则校验引擎单元测试
覆盖四个纯函数检查 + run_full_check 聚合，并包含 A1 修复回归
（run_full_check 接受 brand_info 并用于品牌实体检测）。
"""
from app.services import rule_checker


# ===================== 合规检测 =====================

def test_check_compliance_banned_word():
    r = rule_checker.check_compliance("这是顶级产品，全国第一。", platform_compliance_level=2)
    assert r["banned_count"] > 0
    assert not r["banned_pass"]
    assert not r["pass"]


def test_check_compliance_level1_strict():
    # 合规等级 1：不允许任何违禁词（max_banned = 0）
    r = rule_checker.check_compliance("这是最好的。", platform_compliance_level=1)
    assert r["banned_count"] >= 1
    assert not r["banned_pass"]


def test_check_compliance_clean():
    r = rule_checker.check_compliance("这是一篇普通文章，介绍我们的产品特点。", platform_compliance_level=2)
    assert r["banned_count"] == 0
    assert r["banned_pass"]
    assert r["hard_ad_count"] == 0
    assert r["pass"]


def test_check_compliance_hard_ad_ratio():
    text = "立即购买 " * 10
    r = rule_checker.check_compliance(text, platform_compliance_level=2)
    assert r["hard_ad_count"] >= 1
    assert r["hard_ad_ratio"] > 20
    assert not r["hard_ad_pass"]


# ===================== AI SEO 检测 =====================

def test_check_ai_seo_full_coverage():
    r = rule_checker.check_ai_seo("文章提到关键词护肤和补水，结构清晰。", ["护肤", "补水"])
    assert r["coverage_rate"] == 100
    assert r["coverage_pass"]
    assert "护肤" in r["covered_keywords"]
    assert r["missing_keywords"] == []


def test_check_ai_seo_missing_keyword():
    r = rule_checker.check_ai_seo("文章没有相关关键词。", ["护肤"])
    assert r["coverage_rate"] == 0
    assert not r["coverage_pass"]
    assert "护肤" in r["missing_keywords"]


def test_check_ai_seo_no_keywords_is_pass():
    r = rule_checker.check_ai_seo("无任何关键词要求的文章。", [])
    assert r["coverage_rate"] == 100
    assert r["coverage_pass"]


def test_check_ai_seo_brand_entity():
    # 现设计：实体检测仅保留「品牌名」；官网/联系方式因平台普遍禁止站外引流与联系方式，
    # 不再作为实体强制项（见 rule_checker.check_ai_seo 注释）。
    r = rule_checker.check_ai_seo(
        "品牌润X官网https://x.com",
        [],
        {"brand_name": "润X", "official_website": "https://x.com", "contact_phone": "13800000000"},
    )
    items = {i["name"]: i["present"] for i in r["entity_check"]["items"]}
    assert items["品牌名"] is True
    # 官网/联系方式不再纳入实体检测项
    assert "官网" not in items
    assert "联系方式" not in items
    # 仅品牌名且已出现 → 实体检测完整
    assert r["entity_check"]["complete"] is True


# ===================== 去 AI 味检测 =====================

def test_check_anti_ai_cliche():
    r = rule_checker.check_anti_ai("综上所述，众所周知，毋庸置疑，这是一篇套话文章。")
    assert r["cliche_count"] >= 3
    assert not r["pass"]


def test_check_anti_ai_clean():
    r = rule_checker.check_anti_ai(
        "我们实地调研了三十位用户，发现他们更看重成分安全性与日常肤感。"
    )
    assert r["cliche_count"] == 0
    assert r["ai_score"] >= 60
    assert r["pass"]


# ===================== 格式检测 =====================

def test_check_format_word_count_ok():
    text = "段落一内容。\n\n段落二内容。\n\n段落三内容。"
    r = rule_checker.check_format(text, word_min=10, word_max=100)
    assert r["word_count"] == len(text)
    assert r["word_pass"]
    assert r["paragraph_count"] == 3
    assert r["pass"]


def test_check_format_out_of_range():
    r = rule_checker.check_format("短", word_min=100, word_max=200)
    assert not r["word_pass"]
    assert not r["pass"]


# ===================== run_full_check 集成 =====================

def test_run_full_check_integration_fails():
    text = "顶级产品全国第一，立即购买立即购买立即购买。"
    res = rule_checker.run_full_check(
        text, keywords=["护肤"], brand_info={"brand_name": "润X"},
        word_min=10, word_max=100, platform_compliance_level=2,
    )
    assert res["overall_pass"] is False
    assert len(res["issues"]) > 0
    for k in ("compliance", "ai_seo", "anti_ai", "format"):
        assert k in res


def test_run_full_check_brand_info_param_a1_regression():
    """A1 修复回归：run_full_check 接受 brand_info，实体检测应基于它运行。
    现设计：实体检测仅校验品牌名是否出现（官网/联系方式已移除）。"""
    text = "品牌润X在官网https://x.com推广，联系13800000000。"
    res = rule_checker.run_full_check(
        text, keywords=[],
        brand_info={"brand_name": "润X", "official_website": "https://x.com", "contact_phone": "13800000000"},
        word_min=10, word_max=2000,
    )
    ai_seo = res["ai_seo"]
    items = {i["name"]: i["present"] for i in ai_seo["entity_check"]["items"]}
    assert items["品牌名"] is True
    assert "官网" not in items
    assert "联系方式" not in items
    assert ai_seo["entity_check"]["complete"] is True


def test_run_full_check_pass_when_clean():
    text = "我们调研发现用户看重成分安全。\n\n产品采用天然配方，温和不刺激。\n\n适合日常长期使用。"
    res = rule_checker.run_full_check(
        text, keywords=[], brand_info=None,
        word_min=10, word_max=2000, platform_compliance_level=2,
    )
    assert res["overall_pass"] is True
    assert res["issues"] and "通过" in res["issues"][0]
