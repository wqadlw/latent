"""AI 可见性分析（B3）测试：6 KPI / 趋势 / 信源偏好榜 / 竞品对比。

守护的核心不变量
----------------
1. **KPI 分母只算「成功的探测」** —— 把超时、熔断、限流算成「品牌不可见」，
   会把上游故障误读成品牌表现变差，这是最容易犯且最难发现的错；
2. **每天每关键词采样上限** —— 不采样的话，某天多跑几次就能把趋势线整个拉歪；
3. **信源偏好榜按「被引用的探测条数」计数，不按信源行数** ——
   一篇啰嗦回答把一个域名写 5 次，不代表它比另一个域名重要 5 倍；
4. **选题建议排除自有域名** —— 自有站不需要「对标」，需要的是保持更新；
5. **同名竞品合并而非重复入库** —— 否则看板上同一家竞品拆成两行，数字各占一半。
"""
import types

import pytest
from app.services.visibility import analytics, competitor

INDUSTRY_ID = 1


def _db():
    from app.database import SessionLocal

    return SessionLocal()


def _fake_run(status="completed", analysis=None, keyword="真空泵怎么选型",
              create_time=None, run_id=0, answer_text="", industry_id=INDUSTRY_ID):
    """构造一个只带分析层所需字段的假 Run（不必真的落库）。"""
    import json
    from datetime import datetime

    return types.SimpleNamespace(
        id=run_id,
        industry_id=industry_id,
        keyword=keyword,
        status=status,
        analysis_json=json.dumps(analysis or {}, ensure_ascii=False),
        answer_text=answer_text,
        create_time=create_time or datetime.now(),
    )


def _analysis(visible=True, top1=True, top3=True, sentiment="positive",
              score=1.0, sources=3):
    return {
        "brand_visible": visible, "top1": top1, "top3": top3,
        "sentiment": sentiment, "sentiment_score": score, "source_count": sources,
    }


# ============================================================
#  一、6 个 KPI
# ============================================================
def test_compute_kpis_on_empty_input_is_all_zero():
    kpis = analytics.compute_kpis([])
    assert kpis["sample_size"] == 0
    for key in ("brand_visibility", "top1_rate", "top3_rate",
                "positive_rate", "negative_rate", "sentiment_score"):
        assert kpis[key] == 0.0, f"{key} 在无数据时必须是 0，不能是 None"


def test_compute_kpis_denominator_excludes_failed_runs():
    """失败的探测不能进分母 —— 否则上游故障会被读成品牌表现变差。

    3 条成功（全部可见）+ 7 条失败，可见率必须是 100%，不是 30%。
    """
    runs = [_fake_run(analysis=_analysis()) for _ in range(3)]
    runs += [_fake_run(status="failed", analysis={}) for _ in range(7)]
    kpis = analytics.compute_kpis(runs)
    assert kpis["sample_size"] == 3
    assert kpis["brand_visibility"] == 1.0


def test_compute_kpis_ignores_runs_without_analysis():
    runs = [
        _fake_run(analysis=_analysis(visible=False, top1=False, top3=False)),
        _fake_run(status="completed", analysis={}),  # 有状态但没分析结果
    ]
    kpis = analytics.compute_kpis(runs)
    assert kpis["sample_size"] == 1
    assert kpis["brand_visibility"] == 0.0


def test_compute_kpis_rates_are_fractions_not_percentages():
    """比率统一是 0~1 浮点 —— 服务层不带单位，前端自行乘 100。"""
    runs = [
        _fake_run(analysis=_analysis()),
        _fake_run(analysis=_analysis(visible=False, top1=False, top3=False,
                                     sentiment="negative", score=-1.0)),
    ]
    kpis = analytics.compute_kpis(runs)
    assert kpis["brand_visibility"] == 0.5
    assert kpis["top1_rate"] == 0.5
    assert kpis["positive_rate"] == 0.5
    assert kpis["negative_rate"] == 0.5
    assert kpis["sentiment_score"] == 0.0, "1.0 与 -1.0 的均值应为 0"


def test_compute_kpis_counts_sources():
    runs = [_fake_run(analysis=_analysis(sources=4)),
            _fake_run(analysis=_analysis(sources=2))]
    assert analytics.compute_kpis(runs)["source_total"] == 6


def test_kpi_cards_are_display_ready():
    cards = analytics.kpi_cards(analytics.compute_kpis([_fake_run(analysis=_analysis())]))
    by_key = {c["key"]: c for c in cards}
    assert len(cards) == 6
    assert by_key["brand_visibility"]["display"] == "100.0%"
    # 情感分是 -1~1 的分数，不能显示成百分比
    assert by_key["sentiment_score"]["display"] == "+1.00"
    assert "%" not in by_key["sentiment_score"]["unit"]
    assert all(c["hint"] for c in cards), "每张卡片都应带解释，避免看板变成猜谜"


# ============================================================
#  二、采样
# ============================================================
def test_sample_runs_limits_per_keyword_per_day():
    """同一关键词同一天最多留 DAILY_SAMPLE_TARGET 条。"""
    runs = [_fake_run(run_id=i) for i in range(1, 21)]
    sampled = analytics.sample_runs(runs)
    assert len(sampled) == analytics.DAILY_SAMPLE_TARGET == 5
    assert [r.id for r in sampled] == [1, 2, 3, 4, 5], "应取最早的一批，保证可复现"


def test_sample_runs_keeps_different_keywords_separate():
    runs = (
        [_fake_run(run_id=i, keyword="问题A") for i in range(1, 9)]
        + [_fake_run(run_id=100 + i, keyword="问题B") for i in range(1, 4)]
    )
    sampled = analytics.sample_runs(runs)
    assert len(sampled) == 5 + 3, "不同关键词各占各的配额，不互相挤占"


def test_sample_target_is_configurable():
    runs = [_fake_run(run_id=i) for i in range(1, 11)]
    assert len(analytics.sample_runs(runs, target=2)) == 2


# ============================================================
#  三、趋势
# ============================================================
def test_daily_trend_fills_missing_days_with_zero(client):
    """缺数据的日子必须补 0 而不是跳过 —— 跳过会把「没探测」画成「表现很好」。

    用不可能存在的关键词过滤，避免其它用例当天写入的探测混进来（否则这条断言
    会变成「取决于测试执行顺序」的脆弱断言）。
    """
    trend = analytics.daily_trend(_db(), INDUSTRY_ID, days=7, keyword="__不存在的关键词__")
    assert len(trend) == 7
    assert all("date" in p and "brand_visibility" in p for p in trend)
    assert [p["date"] for p in trend] == sorted(p["date"] for p in trend), "必须按日期升序"
    assert all(p["runs"] == 0 for p in trend)


def test_daily_trend_reflects_todays_runs(client):
    with _db() as db:
        from app.services.visibility import collector

        collector.collect_one(
            db, industry_id=INDUSTRY_ID, keyword="趋势用例问题",
            provider_type="mock", owned_hosts=["example.com"],
            brand_aliases=["示例品牌"], use_circuit_breaker=False,
        )
    trend = analytics.daily_trend(_db(), INDUSTRY_ID, days=3, keyword="趋势用例问题")
    assert trend[-1]["runs"] == 1
    assert trend[-1]["sample_size"] == 1
    assert trend[-1]["brand_visibility"] == 1.0


# ============================================================
#  四、信源偏好榜
# ============================================================
def test_source_preferences_counts_distinct_runs_not_rows(client):
    """同一域名在一篇回答里出现 3 次，只能算 1 条被引用。

    这是「信源偏好榜」能不能信的关键：按行数算的话，
    一篇啰嗦的回答就能把一个域名顶到榜首。
    """
    from app.models import GeoVisibilityRun, GeoVisibilitySource

    with _db() as db:
        run = GeoVisibilityRun(industry_id=INDUSTRY_ID, uuid="pref-test-1",
                               keyword="信源偏好用例", status="completed")
        db.add(run)
        db.flush()
        for i in range(3):
            db.add(GeoVisibilitySource(
                run_id=run.id, domain="chatty.com", rank=i + 1, title=f"t{i}",
                authority_level="low", is_owned=0,
            ))
        db.add(GeoVisibilitySource(
            run_id=run.id, domain="once.com", rank=4, title="t4",
            authority_level="medium", is_owned=0,
        ))
        db.commit()

        board = analytics.source_preferences(db, INDUSTRY_ID, days=30,
                                             keyword="信源偏好用例")
    by_domain = {s["domain"]: s for s in board}
    assert by_domain["chatty.com"]["cited_runs"] == 1
    assert by_domain["chatty.com"]["citation_rows"] == 3
    # 两者被引用的探测条数相同 → 更靠前的 avg_rank 胜出
    assert board[0]["domain"] == "chatty.com"


def test_source_preferences_marks_owned_and_gives_action(client):
    with _db() as db:
        from app.services.visibility import collector

        collector.collect_one(
            db, industry_id=INDUSTRY_ID, keyword="信源行动用例",
            provider_type="mock", owned_hosts=["example.com"],
            brand_aliases=["示例品牌"], use_circuit_breaker=False,
        )
        board = analytics.source_preferences(db, INDUSTRY_ID, days=30,
                                             keyword="信源行动用例")
    owned = [s for s in board if s["is_owned"]]
    assert len(owned) == 1
    assert owned[0]["domain"] == "example.com"
    assert "自有站点" in owned[0]["action"]
    assert all(s["share"] > 0 for s in board)
    assert board[0]["share"] == 1.0


def test_source_preferences_respects_limit(client):
    board = analytics.source_preferences(_db(), INDUSTRY_ID, days=30, limit=2)
    assert len(board) <= 2


# ============================================================
#  五、选题回流
# ============================================================
def test_topic_suggestions_exclude_owned_domains(client):
    """自有域名不该出现在「去对标谁」的建议里。"""
    with _db() as db:
        from app.services.visibility import collector

        collector.collect_one(
            db, industry_id=INDUSTRY_ID, keyword="选题回流用例",
            provider_type="mock", owned_hosts=["example.com"],
            brand_aliases=["示例品牌"], use_circuit_breaker=False,
        )
        topics = analytics.topic_suggestions(_db(), INDUSTRY_ID, days=30,
                                             keyword="选题回流用例")
    domains = {t["source_domain"] for t in topics}
    assert "example.com" not in domains, "自有站点不应出现在对标选题里"
    assert domains, "非自有信源应生成对标选题"
    for t in topics:
        assert t["priority"] in ("高", "中", "低")
        assert t["suggested_title"], "每条建议都必须给出可直接用的标题"
        assert t["reason"]


def test_term_cloud_returns_frequency_pairs(client):
    with _db() as db:
        from app.services.visibility import collector

        collector.collect_one(
            db, industry_id=INDUSTRY_ID, keyword="词云用例",
            provider_type="mock", owned_hosts=["example.com"],
            brand_aliases=["示例品牌"], use_circuit_breaker=False,
        )
        cloud = analytics.term_cloud(_db(), INDUSTRY_ID, days=30, keyword="词云用例")
    assert cloud
    assert all({"term", "count"} <= set(item) for item in cloud)
    counts = [c["count"] for c in cloud]
    assert counts == sorted(counts, reverse=True), "词云必须按频次降序"


# ============================================================
#  六、竞品检测
# ============================================================
def test_detect_in_text_orders_by_first_appearance():
    competitors = [
        types.SimpleNamespace(id=1, name="乙公司", aliases_json="[]", is_self=0),
        types.SimpleNamespace(id=2, name="甲公司", aliases_json="[]", is_self=0),
    ]
    text = "行业里甲公司口碑较好，乙公司次之。"
    found = competitor.detect_in_text(text, competitors)
    assert [f["name"] for f in found] == ["甲公司", "乙公司"], "先提到的排在前面"
    assert [f["rank"] for f in found] == [1, 2]
    assert all(f["mention_count"] == 1 for f in found)


def test_detect_in_text_matches_aliases():
    row = types.SimpleNamespace(
        id=1, name="某某真空科技", aliases_json='["某某", "MW"]', is_self=0
    )
    found = competitor.detect_in_text("推荐 MW 的方案，某某真空科技也不错。", [row])
    assert len(found) == 1
    assert found[0]["mention_count"] == 2, "别名与全称命中应合并计数"


def test_detect_in_text_ignores_single_char_names():
    row = types.SimpleNamespace(id=1, name="A", aliases_json="[]", is_self=0)
    assert competitor.detect_in_text("A 公司很不错", [row]) == [], "单字名误命中率太高"


def test_detect_in_text_marks_self_baseline():
    row = types.SimpleNamespace(id=9, name="示例品牌", aliases_json="[]", is_self=1)
    found = competitor.detect_in_text("示例品牌值得推荐。", [row])
    assert found[0]["is_self"] == 1
    assert found[0]["sentiment"] == "positive"


# ============================================================
#  七、竞品库
# ============================================================
def test_upsert_competitor_merges_duplicate_names(client):
    """同名重复录入必须合并 —— 否则看板上同一家竞品拆成两行，数字各占一半。"""
    with _db() as db:
        a = competitor.upsert_competitor(db, INDUSTRY_ID, "重复测试公司", aliases=["重测"])
        b = competitor.upsert_competitor(db, INDUSTRY_ID, "重复测试公司", note="第二次")
        assert a.id == b.id, "同名应更新而不是新增"
        rows = [c for c in competitor.list_competitors(db, INDUSTRY_ID)
                if c.name == "重复测试公司"]
        assert len(rows) == 1
        assert rows[0].note == "第二次"
        competitor.delete_competitor(db, a.id)


def test_upsert_competitor_rejects_empty_name(client):
    with _db() as db:
        with pytest.raises(ValueError):
            competitor.upsert_competitor(db, INDUSTRY_ID, "   ")


def test_delete_competitor_is_soft(client):
    """软删除：历史检测结果仍要能追溯到它，硬删会让过去的对比数据变成孤儿。"""
    with _db() as db:
        row = competitor.upsert_competitor(db, INDUSTRY_ID, "软删测试公司")
        assert competitor.delete_competitor(db, row.id) is True
        assert all(c.id != row.id for c in competitor.list_competitors(db, INDUSTRY_ID))
        assert any(c.id == row.id for c in competitor.list_competitors(db, INDUSTRY_ID,
                                                                      include_deleted=True))
        assert competitor.delete_competitor(db, 99999999) is False


def test_seed_self_brand_is_idempotent(client):
    with _db() as db:
        first = competitor.seed_self_brand(db, INDUSTRY_ID)
        second = competitor.seed_self_brand(db, INDUSTRY_ID)
        assert first.id == second.id
        assert second.is_self == 1
        assert competitor.competitor_to_dict(second)["aliases"], "别名应被写入"


def test_save_detections_replaces_previous(client):
    """重跑检测不能累积出重复行。"""
    from app.models import GeoVisibilityCompetitorDetection, GeoVisibilityRun

    with _db() as db:
        run = GeoVisibilityRun(industry_id=INDUSTRY_ID, uuid="det-replace-1",
                               keyword="检测覆盖用例", status="completed")
        db.add(run)
        db.commit()

        competitor.save_detections(db, run.id, [{"name": "旧公司", "rank": 1, "mentioned": 1}])
        competitor.save_detections(db, run.id, [{"name": "新公司", "rank": 1, "mentioned": 1}])
        rows = db.query(GeoVisibilityCompetitorDetection).filter(
            GeoVisibilityCompetitorDetection.run_id == run.id
        ).all()
        assert len(rows) == 1
        assert rows[0].name == "新公司"


def test_gap_analysis_without_baseline():
    result = competitor.gap_analysis([{"name": "某公司", "is_self": 0, "mention_rate": 0.5}])
    assert result["has_baseline"] is False


def test_gap_analysis_reports_who_is_ahead():
    rows = [
        {"name": "本品牌", "is_self": 1, "mention_rate": 0.2},
        {"name": "强竞品", "is_self": 0, "mention_rate": 0.8},
        {"name": "弱竞品", "is_self": 0, "mention_rate": 0.1},
    ]
    gap = competitor.gap_analysis(rows)
    assert gap["has_baseline"] is True
    assert gap["self_mention_rate"] == 0.2
    assert [b["name"] for b in gap["behind"]] == ["强竞品"]
    assert gap["behind"][0]["gap"] == 0.6
    assert [a["name"] for a in gap["ahead"]] == ["弱竞品"]


# ============================================================
#  八、API
# ============================================================
def test_analytics_endpoints_require_auth(client):
    for path in (
        "/api/visibility/overview?industry_id=1",
        "/api/visibility/kpis?industry_id=1",
        "/api/visibility/trend?industry_id=1",
        "/api/visibility/source-preferences?industry_id=1",
        "/api/visibility/term-cloud?industry_id=1",
        "/api/visibility/topic-suggestions?industry_id=1",
        "/api/visibility/competitors?industry_id=1",
        "/api/visibility/competitors/board?industry_id=1",
    ):
        assert client.get(path).status_code == 401, path


def test_overview_endpoint_shape(client, auth_headers):
    data = client.get("/api/visibility/overview", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID, "days": 7}).json()["data"]
    assert len(data["kpi_cards"]) == 6
    assert len(data["trend"]) == 7
    assert isinstance(data["source_preferences"], list)
    assert isinstance(data["term_cloud"], list)
    assert isinstance(data["topic_suggestions"], list)
    assert isinstance(data["competitor_board"], list)
    assert "has_baseline" in data["gap_analysis"]
    assert data["window_days"] == 7
    assert data["sample_target"] == analytics.DAILY_SAMPLE_TARGET


def test_kpis_endpoint(client, auth_headers):
    data = client.get("/api/visibility/kpis", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID}).json()["data"]
    assert set(data["kpis"]) >= {
        "brand_visibility", "top1_rate", "top3_rate",
        "positive_rate", "negative_rate", "sentiment_score", "sample_size",
    }
    assert len(data["kpi_cards"]) == 6


def test_source_preferences_endpoint_respects_limit(client, auth_headers):
    rows = client.get("/api/visibility/source-preferences", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID, "limit": 1}).json()["data"]
    assert len(rows) <= 1


def test_compare_endpoint_requires_keywords(client, auth_headers):
    assert client.get("/api/visibility/compare", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID}).status_code == 400

    rows = client.get("/api/visibility/compare", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID,
                              "keywords": "真空泵怎么选型,另一个问题"}).json()["data"]
    assert [r["keyword"] for r in rows] == ["真空泵怎么选型", "另一个问题"] or \
        {r["keyword"] for r in rows} == {"真空泵怎么选型", "另一个问题"}
    assert all("brand_visibility" in r for r in rows)


def test_competitor_crud_flow(client, auth_headers):
    created = client.post("/api/visibility/competitors", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID, "name": "API竞品公司",
        "aliases": ["API竞品"], "note": "用例",
    })
    assert created.status_code == 200, created.text
    comp_id = created.json()["data"]["id"]

    listing = client.get("/api/visibility/competitors", headers=auth_headers,
                         params={"industry_id": INDUSTRY_ID}).json()["data"]
    assert any(c["id"] == comp_id for c in listing)
    assert any("API竞品" in c["aliases"] for c in listing if c["id"] == comp_id)

    assert client.post("/api/visibility/competitors", headers=auth_headers,
                       json={"industry_id": INDUSTRY_ID, "name": "  "}).status_code == 400

    assert client.delete(f"/api/visibility/competitors/{comp_id}",
                         headers=auth_headers).status_code == 200
    assert client.delete(f"/api/visibility/competitors/{comp_id}",
                         headers=auth_headers).status_code == 404


def test_seed_competitors_endpoint(client, auth_headers):
    data = client.post("/api/visibility/competitors/seed", headers=auth_headers,
                       params={"industry_id": INDUSTRY_ID}).json()["data"]
    assert data["is_self"] == 1
    # 幂等：再调一次不应产生第二行
    again = client.post("/api/visibility/competitors/seed", headers=auth_headers,
                        params={"industry_id": INDUSTRY_ID}).json()["data"]
    assert again["id"] == data["id"]


def test_competitor_detect_endpoint(client, auth_headers):
    created = client.post("/api/visibility/collect", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID, "keyword": "竞品检测用例",
        "provider_type": "mock", "auto_sync_reply": False,
    }).json()["data"]
    run_id = created["id"]

    assert client.post("/api/visibility/competitors/detect/999999",
                       headers=auth_headers).status_code == 404

    resp = client.post(f"/api/visibility/competitors/detect/{run_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json()["data"], list)

    client.delete(f"/api/visibility/run/{run_id}", headers=auth_headers)


def test_competitor_board_endpoint(client, auth_headers):
    data = client.get("/api/visibility/competitors/board", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID, "days": 30}).json()["data"]
    assert isinstance(data["board"], list)
    assert "has_baseline" in data["gap"]
    # 有基线时必须排第一行
    if data["board"] and data["gap"]["has_baseline"]:
        assert data["board"][0]["is_self"] == 1, "本品牌基线必须排在第一行"
