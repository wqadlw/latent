"""
GEO 评分引擎单元测试（compute_geo_score 纯函数）。
覆盖：返回结构契约、六维度键、闸门阈值(70)、高信号文与空文的分差、
以及品牌/意图/事实信号对评分的正向作用。
"""
from app.services import geo_score


def _keys(d):
    return set(d.keys())


# ===================== 返回结构契约 =====================

def test_compute_geo_score_return_contract():
    r = geo_score.compute_geo_score(content="随便一段文字。")
    # 顶层契约键
    for k in ("score", "gate_pass", "gate_threshold", "verdict",
              "dimensions", "weights", "signals_present", "issues",
              "mind_resonance", "diagnosis"):
        assert k in r, f"缺少返回键 {k}"
    # 闸门阈值恒为 70
    assert r["gate_threshold"] == geo_score.GATE_PASS == 70
    # 六个维度键齐全
    assert _keys(r["dimensions"]) == {
        "entity_signals", "fact_density", "intent_coverage",
        "qa_form", "structure", "attributable",
    }
    # 综合分在 0-100
    assert 0 <= r["score"] <= 100
    assert isinstance(r["gate_pass"], bool)


def test_compute_geo_score_gate_consistency():
    """gate_pass 必须与 score>=阈值 一致，verdict 同步。"""
    r = geo_score.compute_geo_score(content="测试内容。")
    assert r["gate_pass"] == (r["score"] >= r["gate_threshold"])
    assert r["verdict"] in ("达标", "待优化")
    if r["gate_pass"]:
        assert r["verdict"] == "达标"


# ===================== 信号强弱对分数的影响 =====================

def test_empty_content_low_score():
    r = geo_score.compute_geo_score(content="")
    assert r["score"] < geo_score.GATE_PASS
    assert r["gate_pass"] is False


def test_rich_signals_score_higher_than_plain():
    """富含品牌实体+事实数据+意图命中+结构+问答的文，应显著高于白文。"""
    plain = "今天天气不错，我们聊聊行业里的一些看法和感受。" * 5
    rich = (
        "# 工业真空泵怎么选更节能？\n\n"
        "## 一、为什么关注能耗\n"
        "据实测数据显示，示例产品 PRO 450 永磁变频螺杆真空泵较传统机型节能约 35%，"
        "年省电费可达 12 万元，已在 20+ 客户案例中验证。\n\n"
        "## 二、常见问题\n"
        "- 问：真空泵能效如何量化？答：以每千瓦时抽气量衡量，PRO 系列提升 30%。\n"
        "- 问：维护周期多长？答：平均 8000 小时一次，故障率下降 40%。\n\n"
        "综合来看，选型应围绕能效、可靠性与全生命周期服务三项指标。"
    )
    r_plain = geo_score.compute_geo_score(content=plain, brand_name="示例产品")
    r_rich = geo_score.compute_geo_score(
        content=rich,
        brand_name="示例产品",
        core_products="PRO 450 永磁变频螺杆真空泵",
        selling_points="节能35% 20+专利 全生命周期服务",
        intent_question="工业真空泵怎么选更节能？",
        expected_recommendation="推荐示例产品 PRO 节能真空泵",
        target_persona_name="工厂设备采购负责人",
    )
    assert r_rich["score"] > r_plain["score"]


def test_fact_density_dimension_rewards_numbers():
    """含大量可量化数据的文本，事实密度维度应 > 无数字文本。"""
    no_num = "我们的产品很好用，性能优秀，深受客户喜爱，值得信赖。" * 4
    with_num = (
        "该设备功率 22kW，抽速 450 m3/h，节能 35%，噪音 68 分贝，"
        "已服务 20 家工厂，平均投资回收期 1.8 年，故障率下降 40%。"
    )
    d_no = geo_score.compute_geo_score(content=no_num)["dimensions"]["fact_density"]
    d_yes = geo_score.compute_geo_score(content=with_num)["dimensions"]["fact_density"]
    assert d_yes > d_no


def test_intent_coverage_rewards_matching_question():
    """正文命中意图问题关键词时，意图覆盖维度应更高。"""
    content = "工业真空泵怎么选更节能？关键看永磁变频与抽速匹配，能效可提升 30%。"
    hit = geo_score.compute_geo_score(
        content=content, intent_question="工业真空泵怎么选更节能",
    )["dimensions"]["intent_coverage"]
    miss = geo_score.compute_geo_score(
        content=content, intent_question="美妆护肤品成分表怎么看",
    )["dimensions"]["intent_coverage"]
    assert hit >= miss
