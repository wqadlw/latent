"""断言抽取器单元测试。

这是质检闸门「可信度」维度的输入端：抽不出断言，后面的证据核对就无从谈起。
重点守护：
1. 真断言能抽出、类型正确；
2. **结构性表述不被误抽**（「3 步」「5 个要点」不是事实主张）；
3. 抽取片段是**可读的小句**，而不是前后各截 N 字的半截话；
4. 抽样区间互不重叠且覆盖全文。
"""
from app.services.claim_extractor import (
    ABSOLUTE,
    CERTIFICATION,
    COMPARISON,
    QUANTIFIED,
    claim_summary,
    extract_claims,
    extract_terms,
    sample_ranges,
    split_sentences,
)


# ============================================================
#  句子切分
# ============================================================
def test_split_sentences():
    sents = split_sentences("第一句。第二句！第三句？")
    assert sents == ["第一句。", "第二句！", "第三句？"]


def test_split_sentences_skips_blank():
    assert split_sentences("\n\n  \n") == []


# ============================================================
#  断言抽取
# ============================================================
def test_extract_quantified_claim():
    claims = extract_claims("我们的真空泵效率提升30%。")
    types = {c["type"] for c in claims}
    assert QUANTIFIED in types
    quantified = [c for c in claims if c["type"] == QUANTIFIED]
    assert any("30%" in c["text"] for c in quantified)


def test_claim_snippet_is_readable_clause():
    """片段必须是完整小句，不能是「…提升30%，已服务5」这种半截话。"""
    claims = extract_claims("我们的真空泵效率提升30%，已服务500家客户，通过ISO9001认证。")
    texts = [c["text"] for c in claims if c["type"] == QUANTIFIED]
    # 片段按标点切到小句边界：含主语但不跨逗号
    assert "效率提升30%" in texts[0]
    assert texts[1] == "已服务500家客户"
    assert all("，" not in t for t in texts), "片段不应跨越逗号"


def test_extract_certification_claim():
    claims = extract_claims("公司已通过ISO9001认证，并获得3项发明专利。")
    certs = [c for c in claims if c["type"] == CERTIFICATION]
    assert certs
    assert any("ISO9001" in c["text"] for c in certs)


def test_extract_absolute_claim():
    claims = extract_claims("我们是行业第一，产品绝对可靠。")
    absolutes = [c for c in claims if c["type"] == ABSOLUTE]
    texts = " ".join(c["text"] for c in absolutes)
    assert "行业第一" in texts
    assert "绝对" in texts


def test_extract_comparison_claim():
    claims = extract_claims("相比传统机型，能耗降低40%。")
    assert any(c["type"] == COMPARISON for c in claims)


# ============================================================
#  误抽防护
# ============================================================
def test_structural_numbers_are_not_claims():
    """「3 步」「5 个要点」「2 类」是结构表述，不是事实主张。

    若把它们也当断言，几乎每篇文章都会挂一堆无意义告警，
    最终导致告警被运营无视 —— 比不告警更糟。
    """
    text = "本文分 3 步教你选型。下面列出 5 个要点。产品分为 2 类。"
    claims = extract_claims(text)
    assert [c for c in claims if c["type"] == QUANTIFIED] == []


def test_year_is_not_quantified_claim():
    assert [c for c in extract_claims("2026 年行业规模持续增长。") if c["type"] == QUANTIFIED] == []


def test_large_weak_unit_count_is_a_claim():
    """「服务 500 家客户」是事实主张，不能被当成结构表述放过。"""
    claims = extract_claims("我们已服务500家客户。")
    assert any(c["type"] == QUANTIFIED and "500" in c["text"] for c in claims)


def test_no_claims_on_plain_text():
    assert extract_claims("真空泵是一种常见的工业设备，用于抽取密闭空间内的气体。") == []


def test_inline_source_flag():
    with_source = extract_claims("据第三方检测报告显示，效率提升30%。")
    without = extract_claims("效率提升30%。")
    assert any(c["has_inline_source"] for c in with_source)
    assert not any(c["has_inline_source"] for c in without)


def test_claim_summary_counts():
    summary = claim_summary(extract_claims("效率提升30%，已通过ISO9001认证，是行业第一。"))
    assert summary["total"] >= 3
    assert summary[QUANTIFIED] >= 1
    assert summary[CERTIFICATION] >= 1
    assert summary[ABSOLUTE] >= 1


# ============================================================
#  关键词抽取
# ============================================================
def test_extract_terms_keeps_numbers_and_models():
    terms = extract_terms("效率提升30%，型号 VQP-200 适用")
    assert "30" in terms
    assert "vqp-200" in terms


def test_extract_terms_chinese_bigrams():
    terms = extract_terms("真空泵选型")
    assert "真空" in terms and "空泵" in terms


def test_extract_terms_drops_stopword_bigrams():
    """纯虚词组成的 2-gram 没有区分度，必须丢掉，否则证据匹配形同虚设。"""
    terms = extract_terms("的了和与")
    assert terms == []


# ============================================================
#  抽样兜底
# ============================================================
def test_sample_ranges_short_text_not_sampled():
    result = sample_ranges("短文", max_characters=6000, max_ranges=12)
    assert result["sampled"] is False
    assert result["text"] == "短文"


def test_sample_ranges_long_text_is_sampled():
    text = "".join(str(i % 10) for i in range(25000))
    result = sample_ranges(text, max_characters=6000, max_ranges=12)
    assert result["sampled"] is True
    assert len(result["ranges"]) == 12


def test_sample_ranges_are_non_overlapping_and_cover_tail():
    """区间必须互不重叠，且覆盖到全文尾部 —— 只抽开头会让质检失去代表性。"""
    text = "x" * 30000
    result = sample_ranges(text, max_characters=6000, max_ranges=12)
    ranges = result["ranges"]
    for (_s1, e1), (s2, _e2) in zip(ranges, ranges[1:]):
        assert e1 <= s2, "区间出现重叠"
    assert ranges[-1][1] > len(text) * 0.8, "抽样未覆盖到全文后段"


def test_sample_ranges_respects_single_range():
    text = "y" * 30000
    result = sample_ranges(text, max_characters=6000, max_ranges=1)
    assert len(result["ranges"]) == 1
