"""质检闸门集成测试。

守护的核心不变量
----------------
1. 三态决策只可能是 ``passed`` / ``needs_review`` / ``blocked``；
2. **合规问题必须走硬阻塞**，不能被「扣点分算了」稀释成软问题；
3. 无依据的数字断言必须被识别出来（这是旧版质检完全缺失的能力）；
4. 有知识库依据的断言必须能匹配上，否则闸门会变成「一律不通过」的噪声源。
"""
import pytest
from app.services import quality_evidence

INDUSTRY_ID = 1


@pytest.fixture(scope="module", autouse=True)
def _fresh_evidence_index():
    """每个模块开始前清一次证据索引缓存，避免跨测试污染。"""
    quality_evidence.clear_index_cache()
    yield
    quality_evidence.clear_index_cache()


def _check(client, headers, content, **extra):
    payload = {"content": content, "industry_id": INDUSTRY_ID, **extra}
    resp = client.post("/api/quality/check", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ============================================================
#  鉴权
# ============================================================
def test_quality_endpoints_require_auth(client):
    assert client.post("/api/quality/check", json={"content": "x"}).status_code == 401
    assert client.get("/api/quality/checks?industry_id=1").status_code == 401
    assert client.get("/api/quality/stats?industry_id=1").status_code == 401
    assert client.get("/api/quality/health").status_code == 401


def test_check_rejects_empty_content(client, auth_headers):
    resp = client.post("/api/quality/check", headers=auth_headers, json={"content": "   "})
    assert resp.status_code == 400


# ============================================================
#  三态决策
# ============================================================
def test_decision_is_always_one_of_three(client, auth_headers):
    for text in [
        "真空泵是一种常见的工业设备，用于抽取密闭空间内的气体。",
        "我们的产品效率提升30%，已服务500家客户。",
        "最好的产品，行业第一，唯一选择，国家级认证。",
    ]:
        data = _check(client, auth_headers, text)
        assert data["decision"] in ("passed", "needs_review", "blocked")


def test_blocked_by_banned_words(client, auth_headers):
    """3 个广告法违禁词超过 compliance_level=2 的容忍上限（2 个）→ 硬阻塞。"""
    data = _check(client, auth_headers, "这是最好的产品，行业第一，唯一的选择。")
    assert data["decision"] == "blocked"
    codes = {b["code"] for b in data["hard_blockers"]}
    assert "banned_words" in codes
    assert data["score"] < 100


def test_blocked_by_offsite_contact(client, auth_headers):
    """站外引流是零容忍项：出现即硬阻塞，与分数无关。"""
    data = _check(client, auth_headers, "详情请访问官网 www.example.com 或加微信咨询。")
    assert data["decision"] == "blocked"
    codes = {b["code"] for b in data["hard_blockers"]}
    assert "offsite_contact" in codes


def test_hard_blockers_are_not_diluted_into_soft_issues(client, auth_headers):
    """合规问题必须出现在 hard_blockers 里，不能只落到 soft_issues。

    这是本次改造最核心的设计点：把一票否决项和扣分项混在一个列表里，
    是旧版质检最根本的缺陷。
    """
    data = _check(client, auth_headers, "最好的产品，行业第一，唯一选择。")
    assert data["hard_blockers"]
    blocker_codes = {b["code"] for b in data["hard_blockers"]}
    soft_codes = {i["code"] for i in data["soft_issues"]}
    assert "banned_words" in blocker_codes
    assert "banned_words" not in soft_codes


def test_low_score_forces_blocked(client, auth_headers):
    """分数低于人工放行底线 → blocked，即使没有合规硬阻塞。"""
    data = _check(client, auth_headers, "短。")
    assert data["decision"] == "blocked"
    assert data["score"] < data["thresholds"]["manual_floor"]


# ============================================================
#  断言证据核对
# ============================================================
def test_unverified_claims_are_reported(client, auth_headers):
    """没有知识库依据的数字断言必须被标出来 —— 这是旧版完全没有的能力。"""
    data = _check(client, auth_headers, "本产品效率提升300%，能耗降低80%，服务客户超过50000家。")
    assert data["claim_summary"]["total"] >= 2
    assert data["unverified_claims"], "无依据断言未被识别"
    assert data["evidence_coverage"] < 1.0
    notes = " ".join(c.get("note") or "" for c in data["unverified_claims"])
    assert notes, "未通过断言必须给出原因说明"


def test_absolute_claim_always_unverified(client, auth_headers):
    """绝对化表述无法用证据支撑，必须恒为 unverified。"""
    data = _check(client, auth_headers, "我们是行业内首屈一指的供应商。")
    absolutes = [c for c in data["unverified_claims"] if c["type"] == "absolute"]
    assert absolutes
    assert "广告法" in (absolutes[0].get("note") or "")


def test_verified_claim_with_knowledge_evidence(client, auth_headers):
    """知识库里能对上数字的断言必须被判为已证实。

    如果这条挂了，说明闸门退化成「一律不通过」，运营会直接无视它。
    """
    item = client.post("/api/knowledge/item", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID,
        "title": "真空泵能效实测报告",
        "summary": "第三方实测数据显示，我司真空泵相比传统机型效率提升30%，已服务客户超过500家。",
        "content": "第三方检测机构实测：真空泵效率提升30%，服务客户超过500家，覆盖全国20个省份。",
        "source": "第三方检测报告 2026-Q3",
    })
    assert item.status_code == 200, item.text
    item_id = item.json()["data"]["id"]
    quality_evidence.clear_index_cache()

    try:
        data = _check(client, auth_headers, "我们的真空泵效率提升30%，已服务500家客户。")
        assert data["evidence_stats"]["verified"] >= 1, "有依据的断言未被匹配上"
        assert data["verified_claims"], "verified_claims 为空"
        assert data["evidence_coverage"] > 0
    finally:
        client.delete(f"/api/knowledge/item/{item_id}", headers=auth_headers)
        quality_evidence.clear_index_cache()


def test_wrong_number_is_not_verified(client, auth_headers):
    """知识库里有相近表述但**关键数字对不上**时，不能算已证实。

    这是证据核对最容易被做错的一点：只做词面相似度会把「效率提升300%」
    匹配到写着「效率提升30%」的资料上，闸门反而变成了错误的背书。
    """
    item = client.post("/api/knowledge/item", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID,
        "title": "能效说明",
        "summary": "实测效率提升30%。",
        "content": "实测效率提升30%。",
    })
    item_id = item.json()["data"]["id"]
    quality_evidence.clear_index_cache()

    try:
        data = _check(client, auth_headers, "我们的真空泵效率提升300%。")
        quantified = [c for c in data["unverified_claims"] if c["type"] == "quantified"]
        assert quantified, "数字对不上的断言不应被判为已证实"
    finally:
        client.delete(f"/api/knowledge/item/{item_id}", headers=auth_headers)
        quality_evidence.clear_index_cache()


def test_too_many_unverified_claims_blocks(client, auth_headers):
    """无依据断言达到阈值 → 硬阻塞（虚假宣传风险）。"""
    content = (
        "效率提升300%，能耗降低80%，服务客户超过50000家，"
        "覆盖全国300个城市，返修率仅0.01%，累计交付12000台设备。"
    )
    data = _check(client, auth_headers, content, thresholds={"unverified_block": 3})
    codes = {b["code"] for b in data["hard_blockers"]}
    assert "too_many_unverified_claims" in codes
    assert data["decision"] == "blocked"


def test_unverified_block_threshold_is_configurable(client, auth_headers):
    """把阈值抬高后，同样内容不应再被无依据断言拦截。"""
    content = "效率提升300%，能耗降低80%，服务客户超过50000家。"
    data = _check(client, auth_headers, content, thresholds={"unverified_block": 99})
    codes = {b["code"] for b in data["hard_blockers"]}
    assert "too_many_unverified_claims" not in codes


# ============================================================
#  抽样兜底
# ============================================================
def test_long_content_uses_sampling_scope(client, auth_headers):
    long_text = "真空泵选型需要考虑流量与极限真空度。" * 1500  # 约 27k 字
    data = _check(client, auth_headers, long_text)
    assert data["inspection_scope"] == "fallback_sampled"
    assert "抽样" in data["scope_label"]


def test_sampled_result_never_auto_passes(client, auth_headers):
    """抽样质检默认不自动放行 —— 抽样结论的可信度不足以支撑无人复核发布。"""
    long_text = "真空泵选型需要考虑流量与极限真空度。" * 1500
    data = _check(client, auth_headers, long_text, thresholds={"sampled_auto_release": False})
    assert data["decision"] != "passed"


def test_short_content_uses_full_scope(client, auth_headers):
    data = _check(client, auth_headers, "真空泵是一种常见的工业设备。")
    assert data["inspection_scope"] == "full"


# ============================================================
#  落库 / 查询 / 统计
# ============================================================
def test_persist_and_query_flow(client, auth_headers):
    data = _check(
        client, auth_headers,
        "我们的真空泵效率提升30%，已服务500家客户，选型需关注极限真空度。",
        persist=True, title="质检落库用例",
    )
    check_id = data.get("check_id")
    assert check_id, "persist=true 时必须落库并返回 check_id"

    listing = client.get("/api/quality/checks", headers=auth_headers,
                         params={"industry_id": INDUSTRY_ID, "days": 3650}).json()["data"]
    assert listing["total"] >= 1
    assert any(i["id"] == check_id for i in listing["items"])
    # 列表页只回摘要，不传三路原始 JSON
    assert "rule_result_json" not in listing["items"][0]
    assert "unverified_claim_count" in listing["items"][0]

    detail = client.get(f"/api/quality/check/{check_id}", headers=auth_headers).json()["data"]
    assert detail["decision"] == data["decision"]
    assert isinstance(detail["hard_blockers"], list)
    assert isinstance(detail["thresholds"], dict)

    assert client.delete(f"/api/quality/check/{check_id}", headers=auth_headers).status_code == 200
    assert client.get(f"/api/quality/check/{check_id}", headers=auth_headers).status_code == 404


def test_check_task_endpoint(client, auth_headers):
    """对生产任务跑质检：任务不存在时 404，存在时返回决策。"""
    assert client.post("/api/quality/check-task/999999", headers=auth_headers).status_code == 404

    created = client.post("/api/production", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID, "title": "质检任务用例",
    })
    assert created.status_code == 200, created.text
    task_id = created.json()["data"]["id"]

    try:
        resp = client.post(f"/api/quality/check-task/{task_id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["decision"] in ("passed", "needs_review", "blocked")
    finally:
        client.delete(f"/api/production/{task_id}", headers=auth_headers)


def test_stats_endpoint(client, auth_headers):
    _check(client, auth_headers, "最好的产品，行业第一，唯一选择。", persist=True)
    data = client.get("/api/quality/stats", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID, "days": 3650}).json()["data"]
    assert data["total"] >= 1
    assert set(data["decisions"]) == {"passed", "needs_review", "blocked"}
    assert data["block_rate"] >= 0
    assert isinstance(data["top_blockers"], list)
    assert isinstance(data["trend"], list)


# ============================================================
#  阈值 / 熔断器
# ============================================================
def test_thresholds_endpoint(client, auth_headers):
    data = client.get("/api/quality/thresholds", headers=auth_headers).json()["data"]
    assert data["auto_pass"] == 85
    assert data["manual_floor"] == 70
    assert data["unverified_block"] == 3


def test_thresholds_override_per_request(client, auth_headers):
    data = _check(client, auth_headers, "真空泵设备说明。", thresholds={"auto_pass": 10, "manual_floor": 5})
    assert data["thresholds"]["auto_pass"] == 10
    assert data["thresholds"]["manual_floor"] == 5


def test_health_and_reset(client, auth_headers):
    data = client.get("/api/quality/health", headers=auth_headers).json()["data"]
    assert data["breaker"]["state"] in ("closed", "open", "half_open")
    assert "thresholds" in data["breaker"]
    assert client.post("/api/quality/health/reset", headers=auth_headers).status_code == 200
    after = client.get("/api/quality/health", headers=auth_headers).json()["data"]
    assert after["breaker"]["state"] == "closed"


# ============================================================
#  熔断器单元行为
# ============================================================
def test_circuit_breaker_opens_after_consecutive_failures():
    from app.services.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("unit-test", consecutive_failures=3, sample_size=10, open_seconds=60)
    assert cb.allow() is True
    for _ in range(3):
        cb.record_failure()
    assert cb.allow() is False, "连续失败达到阈值后必须短路"
    assert cb.state()["state"] == "open"


def test_circuit_breaker_half_open_then_close():
    from app.services.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("unit-half-open", consecutive_failures=2, sample_size=10, open_seconds=0.01)
    cb.record_failure()
    cb.record_failure()
    assert cb.allow() is False
    import time
    time.sleep(0.05)
    assert cb.allow() is True, "冷却结束后应放行一次试探"
    assert cb.allow() is False, "半开状态只放行一个试探请求"
    cb.record_success()
    assert cb.state()["state"] == "closed"


def test_circuit_breaker_opens_on_failure_rate():
    from app.services.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("unit-rate", consecutive_failures=99, sample_size=4, failure_percent=50, open_seconds=60)
    cb.record_success()
    cb.record_success()
    cb.record_failure()
    cb.record_failure()
    assert cb.allow() is False, "样本失败率达标也应熔断"


# ============================================================
#  编排层集成：手动流 / 自动流共用同一套裁决
# ============================================================
def test_orchestrator_gate_produces_three_state_decision():
    """``orchestrator.run_quality_gate`` 在传入 db 时必须给出三态决策。

    这是「手动流与自动流口径一致」的保证：两条链路都走 ``verdict_from_results``，
    不可能出现「手动流放行、自动流拦截」这种自相矛盾。
    """
    from app.database import SessionLocal
    from app.services.orchestrator import run_quality_gate

    with SessionLocal() as db:
        result = run_quality_gate(
            "我们的真空泵效率提升300%，已服务50000家客户，是行业第一。",
            {"brand_name": "示例品牌", "keywords": "真空泵"},
            mode="geo",
            title="测试标题",
            db=db,
            industry_id=INDUSTRY_ID,
        )

    assert result["decision"] in ("passed", "needs_review", "blocked")
    assert "gate_pass" in result, "旧字段必须保留，不能破坏既有调用方"
    assert result["unverified_claims"], "无依据断言应被带出"
    assert result["hard_blockers"] is not None
    assert any("可信度" in i for i in result["issues"]), "问题清单应带可信度分级前缀"


def test_orchestrator_gate_without_db_still_works():
    """不传 db 时退化为旧行为（不报错、字段齐全），保证向后兼容。"""
    from app.services.orchestrator import run_quality_gate

    result = run_quality_gate("真空泵设备说明。", {}, mode="geo", title="t")
    assert "gate_pass" in result
    assert "issues" in result
    assert "decision" not in result, "无 db 时不应编造三态决策"
