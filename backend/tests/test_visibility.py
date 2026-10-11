"""AI 可见性采集（B2）测试。

守护的核心不变量
----------------
1. **手工通道与自动通道共用同一套解析** —— 否则会出现「同一个回答，
   手工导入判正面、自动采集判中性」这种自相矛盾；
2. **``brand_visible`` 是 OR 语义** —— 回答没点名品牌、但把自有站作为前 3 信源引用，
   同样算可见（而且往往更有价值）。这条写错，整个可见性指标就失去意义；
3. **信源按域名去重且 rank 按出现顺序** —— 不去重会把「信源偏好榜」彻底扭曲；
4. **并发只做网络调用、落库串行** —— SQLite 写锁容不下多线程同时写；
5. **自动采集的回复不能被人工粘贴覆盖** —— 每条自动探测对应独立的 run，
   一旦被覆盖，历史探测数据就没了。
"""
import pytest
from app.services import circuit_breaker
from app.services.visibility import collector, metrics, normalizer

INDUSTRY_ID = 1

MOCK_ANSWER = (
    "关于「真空泵怎么选型」，主流判断依据包括极限真空度、抽速与长期运行稳定性。\n\n"
    "推荐方案：优先考虑有公开实测数据的厂商。\n\n"
    "来源：\n"
    "[1] 行业选型指南 - https://www.example.com/guide/selection\n"
    "[2] 第三方检测机构 - https://www.testlab.cn/reports/vacuum\n"
    "[3] 行业资讯 - https://news.example.org/articles/vacuum-trend\n"
)


@pytest.fixture(scope="module", autouse=True)
def _clean_breaker():
    """熔断器是进程级单例，跨模块污染会让「该失败的没失败、该成功的被短路」。"""
    circuit_breaker.reset_all()
    yield
    circuit_breaker.reset_all()


# ============================================================
#  一、指标解析：手工流 / 自动流共用同一实现
# ============================================================
def test_parse_ai_reply_is_shared_single_source():
    """``geo_monitor`` 里用的解析函数必须就是 ``visibility.metrics`` 里那一个。

    这条断言防的是「有人图省事在路由里又抄一份解析」——
    那样两条通道的口径会悄悄分叉，而且不会有任何测试失败。
    """
    from app.routers import geo_monitor

    assert geo_monitor._parse_ai_reply is metrics.parse_ai_reply


def test_parse_ai_reply_detects_positive_mention():
    data = metrics.parse_ai_reply("我们推荐示例品牌的真空泵，实测效率提升30%。", "示例品牌")
    assert data["mentioned"] == 1
    assert data["mention_count"] >= 1
    assert data["sentiment"] == "positive"
    assert data["recommended"] == 1
    assert data["valuable_positive"] == 1, "正面 + 带数据证据 = 有价值的正面"
    assert "示例品牌" in data["snippet"]


def test_parse_ai_reply_negation_flips_to_negative():
    """「不推荐」必须判为负向 —— 否定前缀处理是这块最容易漏的细节。"""
    data = metrics.parse_ai_reply("不建议选择示例品牌，故障率偏高。", "示例品牌")
    assert data["mentioned"] == 1
    assert data["sentiment"] == "negative"
    assert data["recommended"] == 0


def test_parse_ai_reply_without_mention_is_neutral():
    data = metrics.parse_ai_reply("真空泵选型需关注极限真空度。", "示例品牌")
    assert data["mentioned"] == 0
    assert data["mention_count"] == 0
    assert data["sentiment"] == "neutral"
    assert data["valuable_positive"] == 0


# ============================================================
#  二、信源抽取与归一化
# ============================================================
def test_normalize_host_strips_www_and_port():
    assert normalizer.normalize_host("https://www.Example.com:8443/a/b") == "example.com"
    assert normalizer.normalize_host("www.testlab.cn/reports") == "testlab.cn"
    assert normalizer.normalize_host("") == ""


def test_extract_sources_from_markdown_links():
    text = "参考 [行业白皮书](https://www.zhihu.com/question/123) 与 [检测报告](https://testlab.cn/r/1)。"
    sources = normalizer.extract_sources(text)
    domains = [s["domain"] for s in sources]
    assert domains == ["zhihu.com", "testlab.cn"]
    assert sources[0]["title"] == "行业白皮书", "Markdown 链接的标题必须被保留"
    assert sources[0]["source_type"] == "markdown_link"


def test_extract_sources_from_bare_url_and_bare_domain():
    text = "详见 https://testlab.cn/reports/vacuum ，另可参考 zhihu.com 上的讨论。"
    sources = normalizer.extract_sources(text)
    domains = {s["domain"] for s in sources}
    assert "testlab.cn" in domains
    assert "zhihu.com" in domains, "裸域名（无协议）也要能识别"


def test_extract_sources_dedupes_by_domain_keeping_first():
    """同一域名被引用多次只保留首次 —— 重复计数会严重扭曲信源偏好榜。"""
    text = (
        "第一处 https://testlab.cn/a\n"
        "第二处 https://testlab.cn/b\n"
        "第三处 https://testlab.cn/c\n"
    )
    sources = normalizer.extract_sources(text)
    assert len(sources) == 1
    assert sources[0]["rank"] == 1


def test_extract_sources_rank_follows_appearance_order():
    sources = normalizer.extract_sources(MOCK_ANSWER)
    assert [s["rank"] for s in sources] == list(range(1, len(sources) + 1))
    assert sources[0]["domain"] == "example.com", "rank 必须等于出现顺序"


def test_authority_level_classification():
    assert normalizer.authority_level("gov.cn") == "high"
    assert normalizer.authority_level("www.miit.gov.cn") == "high"
    assert normalizer.authority_level("zhihu.com") == "medium"
    assert normalizer.authority_level("some-random-blog.xyz") == "low"


def test_owned_source_detection_and_score_boost():
    sources = normalizer.extract_sources(MOCK_ANSWER, owned_hosts=["example.com"])
    owned = [s for s in sources if s["is_owned"]]
    assert len(owned) == 1
    assert owned[0]["domain"] == "example.com"
    # 自有站点在同等位次下得分更高（鼓励自有内容被引用）
    plain = normalizer.extract_sources(
        "https://example.com/a https://other.com/b", owned_hosts=[]
    )
    boosted = normalizer.extract_sources(
        "https://example.com/a https://other.com/b", owned_hosts=["example.com"]
    )
    assert boosted[0]["rank_score"] > plain[0]["rank_score"]


def test_extract_sources_parses_source_lines():
    text = "正文内容。\n来源：《真空技术手册》、中国真空学会"
    sources = normalizer.extract_sources(text)
    titles = [s["title"] for s in sources]
    assert "真空技术手册" in titles, "书名号必须被剥掉"
    assert "中国真空学会" in titles


# ============================================================
#  三、brand_visible 的 OR 语义（本模块最核心的一条）
# ============================================================
def test_brand_visible_when_answer_mentions_brand():
    sources = []
    result = normalizer.analyze_answer(
        "我们推荐示例品牌的真空泵。", sources, brand_aliases=["示例品牌"], owned_hosts=[]
    )
    assert result["answer_mentions_brand"] is True
    assert result["brand_visible"] is True


def test_brand_visible_when_owned_source_in_top3_without_mention():
    """AI 没点名你，但把自有站作为前 3 信源引用了 —— 同样算可见。

    这正是 GEO 与「品牌词监控」的分水岭：被引用往往比被点名更有价值，
    说明你的内容被 AI 当成了判断依据。
    """
    sources = normalizer.extract_sources(MOCK_ANSWER, owned_hosts=["example.com"])
    result = normalizer.analyze_answer(
        MOCK_ANSWER, sources, brand_aliases=["完全不相关的品牌"], owned_hosts=["example.com"]
    )
    assert result["answer_mentions_brand"] is False
    assert result["top1"] is True
    assert result["top3"] is True
    assert result["brand_visible"] is True, "自有信源进前 3 必须判为可见"


def test_not_visible_when_neither_mention_nor_owned_source():
    text = "真空泵选型看极限真空度。\n来源：https://testlab.cn/a"
    sources = normalizer.extract_sources(text, owned_hosts=["example.com"])
    result = normalizer.analyze_answer(
        text, sources, brand_aliases=["示例品牌"], owned_hosts=["example.com"]
    )
    assert result["answer_mentions_brand"] is False
    assert result["brand_visible"] is False
    assert result["best_brand_rank"] is None


def test_owned_source_at_rank4_is_not_top3():
    """第 4 名不再是 top3 —— 边界不能含糊，否则「前 3 引用」这个指标就没法解释。"""
    text = (
        "https://a1.com/x https://a2.com/x https://a3.com/x "
        "https://www.example.com/x"
    )
    sources = normalizer.extract_sources(text, owned_hosts=["example.com"])
    result = normalizer.analyze_answer(
        text, sources, brand_aliases=["示例品牌"], owned_hosts=["example.com"]
    )
    assert result["best_brand_rank"] == 4
    assert result["top3"] is False
    assert result["brand_visible"] is False


def test_analyze_answer_counts_owned_sources():
    sources = normalizer.extract_sources(MOCK_ANSWER, owned_hosts=["example.com"])
    result = normalizer.analyze_answer(
        MOCK_ANSWER, sources, brand_aliases=["示例品牌"], owned_hosts=["example.com"]
    )
    assert result["source_count"] == len(sources)
    assert result["owned_source_count"] == 1


# ============================================================
#  四、信源偏好榜与行动建议
# ============================================================
def test_top_domains_aggregates_across_runs():
    """``top_domains`` 的用途是**跨多次探测**汇总域名份额，所以这里直接喂多条信源。

    单篇回答内的同域名重复已在 ``extract_sources`` 里去重，
    因此这条函数真正发挥作用的地方就是「多篇回答一起看谁被引用得最多」。
    """
    sources = [
        {"domain": "zhihu.com", "rank": 1, "rank_score": 0.88,
         "authority_level": "medium", "is_owned": 0, "title": "a"},
        {"domain": "zhihu.com", "rank": 2, "rank_score": 0.44,
         "authority_level": "medium", "is_owned": 0, "title": "b"},
        {"domain": "testlab.cn", "rank": 1, "rank_score": 0.88,
         "authority_level": "low", "is_owned": 0, "title": "c"},
    ]
    board = normalizer.top_domains(sources)
    assert board[0]["domain"] == "zhihu.com"
    assert board[0]["count"] == 2
    assert board[0]["best_rank"] == 1
    assert board[1]["domain"] == "testlab.cn"


def test_source_action_differs_by_authority():
    high = normalizer.source_action({"authority_level": "high", "is_owned": 0})
    low = normalizer.source_action({"authority_level": "low", "is_owned": 0})
    owned = normalizer.source_action({"authority_level": "low", "is_owned": 1})
    assert "高权威" in high
    assert "长尾" in low
    assert "自有站点" in owned


# ============================================================
#  五、collect_one：单引擎探测落库
# ============================================================
def _db():
    from app.database import SessionLocal

    return SessionLocal()


def test_collect_one_with_mock_provider_persists_run_and_sources(client):
    """mock 通道跑通完整链路：建 Run → 抽信源 → 算指标 → 落库。"""
    with _db() as db:
        data = collector.collect_one(
            db, industry_id=INDUSTRY_ID, keyword="真空泵怎么选型",
            provider_type="mock",
            owned_hosts=["example.com"], brand_aliases=["示例品牌"],
            use_circuit_breaker=False,
        )
        run_id = data["id"]

    assert data["status"] == "completed"
    assert data["error_code"] == ""
    assert len(data["sources"]) == 3
    assert data["analysis"]["brand_visible"] is True
    assert data["top_domains"][0]["domain"] == "example.com"

    with _db() as db:
        from app.models import GeoVisibilityRun

        detail = collector.run_to_dict(
            db.query(GeoVisibilityRun).filter_by(id=run_id).first(),
            include_sources=True,
        )
    assert len(detail["sources"]) == 3
    assert all(s["action"] for s in detail["sources"]), "每条信源都应给出行动建议"


def test_collect_one_rejects_empty_keyword(client):
    with _db() as db:
        with pytest.raises(ValueError):
            collector.collect_one(db, industry_id=INDUSTRY_ID, keyword="   ",
                                  provider_type="mock", use_circuit_breaker=False)


def test_collect_one_records_stable_error_code_when_no_api_key(client):
    """缺密钥时落库的必须是**稳定错误码**，不是自由文本 —— 运维看板要能按类型分组。"""
    with _db() as db:
        data = collector.collect_one(
            db, industry_id=INDUSTRY_ID, keyword="真空泵怎么选型",
            llm_config={"provider": "deepseek", "model": "deepseek-chat"},
            provider_type="llm_chat",
            use_circuit_breaker=False,
        )
    assert data["status"] == "failed"
    assert data["error_code"] == "ai_model_not_configured"
    assert data["sources"] == []


def test_collect_one_short_circuits_when_breaker_open(client):
    """上游熔断期间直接短路，不白白等一个超时周期。"""
    breaker = circuit_breaker.get_breaker("ai_visibility")
    for _ in range(10):
        breaker.record_failure()
    assert breaker.allow() is False

    try:
        with _db() as db:
            data = collector.collect_one(
                db, industry_id=INDUSTRY_ID, keyword="真空泵怎么选型",
                provider_type="mock", use_circuit_breaker=True,
            )
        assert data["error_code"] == collector.ERR_CIRCUIT_OPEN
        assert data["status"] == "failed"
    finally:
        circuit_breaker.reset_all()


# ============================================================
#  六、collect_multi：并发调用、串行落库
# ============================================================
def test_collect_multi_runs_all_targets(client):
    with _db() as db:
        runs = collector.collect_multi(
            db, industry_id=INDUSTRY_ID, keyword="真空泵怎么选型",
            targets=[
                {"provider_type": "mock", "label": "引擎A"},
                {"provider_type": "mock", "label": "引擎B"},
                {"provider_type": "mock", "label": "引擎C"},
            ],
            max_workers=3,
        )
    assert len(runs) == 3
    assert {r["label"] for r in runs} == {"引擎A", "引擎B", "引擎C"}
    assert all(r["status"] == "completed" for r in runs)
    # 每个引擎各落一条独立 Run（不是覆盖同一条）
    assert len({r["id"] for r in runs}) == 3
    assert all(len(r["sources"]) == 3 for r in runs)


def test_collect_multi_falls_back_to_mock_when_no_config(client):
    """该行业没有可用 LLM 配置时退化为 mock —— 让链路可跑通、看板有数据，而不是直接报错。"""
    with _db() as db:
        runs = collector.collect_multi(
            db, industry_id=INDUSTRY_ID, keyword="无配置行业的问题", targets=None,
        )
    assert len(runs) >= 1
    assert runs[0]["provider_type"] == "mock"


# ============================================================
#  七、双通道合流：自动采集 vs 人工粘贴
# ============================================================
def _make_monitor(client, auth_headers, brand="示例品牌", query="真空泵怎么选型"):
    resp = client.post("/api/geo-monitor", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID, "name": "可见性测试任务",
        "target_query": query, "brand_name": brand, "platforms": "[]",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def test_sync_reply_from_run_marks_auto_channel(client, auth_headers):
    monitor_id = _make_monitor(client, auth_headers)
    try:
        with _db() as db:
            runs = collector.collect_multi(
                db, industry_id=INDUSTRY_ID, keyword="真空泵怎么选型",
                targets=[{"provider_type": "mock", "label": "DeepSeek"}],
                monitor_id=monitor_id, auto_sync_reply=True,
            )
        assert len(runs) == 1

        replies = client.get(f"/api/geo-monitor/{monitor_id}/replies",
                             headers=auth_headers).json()["data"]
        auto = [r for r in replies if r.get("source_channel") == "auto"]
        assert len(auto) == 1, "自动采集必须回填到同一张 geo_monitor_reply"
        assert auto[0]["run_id"] == runs[0]["id"], "run_id 必须指向来源探测"
    finally:
        client.delete(f"/api/geo-monitor/{monitor_id}", headers=auth_headers)


def test_manual_paste_does_not_overwrite_auto_replies(client, auth_headers):
    """人工粘贴只更新「手工通道」那条，自动采集的历史探测数据必须原样保留。

    旧实现只按 (monitor_id, platform) 匹配，人工一粘贴就会把自动探测的回复
    整条覆盖掉 —— 数据静默丢失，且没有任何报错。
    """
    monitor_id = _make_monitor(client, auth_headers)
    try:
        with _db() as db:
            runs = collector.collect_multi(
                db, industry_id=INDUSTRY_ID, keyword="真空泵怎么选型",
                targets=[{"provider_type": "mock", "label": "DeepSeek"}],
                monitor_id=monitor_id, auto_sync_reply=True,
            )
        auto_run_id = runs[0]["id"]

        resp = client.post(f"/api/geo-monitor/{monitor_id}/reply", headers=auth_headers,
                           json={"platform": "DeepSeek", "ai_reply": "示例品牌值得推荐，实测数据可靠。"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["source_channel"] == "manual"

        replies = client.get(f"/api/geo-monitor/{monitor_id}/replies",
                             headers=auth_headers).json()["data"]
        auto = [r for r in replies if r.get("run_id") == auto_run_id]
        assert len(auto) == 1, "自动采集的回复被人工粘贴覆盖了"
        assert auto[0]["source_channel"] == "auto"

        # 再粘一次：仍然只更新手工那条，不新增
        client.post(f"/api/geo-monitor/{monitor_id}/reply", headers=auth_headers,
                    json={"platform": "DeepSeek", "ai_reply": "示例品牌依然是首选。"})
        replies = client.get(f"/api/geo-monitor/{monitor_id}/replies",
                             headers=auth_headers).json()["data"]
        manual = [r for r in replies if r.get("source_channel") == "manual"]
        assert len(manual) == 1, "手工通道同平台应保持 upsert 语义"
        assert len([r for r in replies if r.get("run_id") == auto_run_id]) == 1
    finally:
        client.delete(f"/api/geo-monitor/{monitor_id}", headers=auth_headers)


# ============================================================
#  八、API
# ============================================================
def test_visibility_endpoints_require_auth(client):
    assert client.get("/api/visibility/providers").status_code == 401
    assert client.get("/api/visibility/configs?industry_id=1").status_code == 401
    assert client.post("/api/visibility/collect", json={"industry_id": 1}).status_code == 401
    assert client.get("/api/visibility/run?industry_id=1").status_code == 401


def test_providers_endpoint(client, auth_headers):
    data = client.get("/api/visibility/providers", headers=auth_headers).json()["data"]
    values = {p["value"] for p in data["providers"]}
    assert {"llm_chat", "mock", "manual"} <= values
    assert data["breaker"]["state"] in ("closed", "open", "half_open")


def test_collect_endpoint_with_mock_provider(client, auth_headers):
    resp = client.post("/api/visibility/collect", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID, "keyword": "真空泵怎么选型",
        "provider_type": "mock", "auto_sync_reply": False,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "completed"
    assert len(data["sources"]) == 3
    client.delete(f"/api/visibility/run/{data['id']}", headers=auth_headers)


def test_collect_endpoint_requires_keyword_or_monitor(client, auth_headers):
    resp = client.post("/api/visibility/collect", headers=auth_headers,
                       json={"industry_id": INDUSTRY_ID, "provider_type": "mock"})
    assert resp.status_code == 400


def test_collect_multi_endpoint(client, auth_headers):
    resp = client.post("/api/visibility/collect-multi", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID, "keyword": "真空泵怎么选型",
        "targets": [
            {"provider_type": "mock", "label": "引擎A"},
            {"provider_type": "mock", "label": "引擎B"},
        ],
        "max_workers": 2,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 2 and data["succeeded"] == 2
    for r in data["runs"]:
        client.delete(f"/api/visibility/run/{r['id']}", headers=auth_headers)


def test_run_list_detail_delete_flow(client, auth_headers):
    created = client.post("/api/visibility/collect", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID, "keyword": "可见性列表用例",
        "provider_type": "mock", "auto_sync_reply": False,
    }).json()["data"]
    run_id = created["id"]

    listing = client.get("/api/visibility/run", headers=auth_headers,
                         params={"industry_id": INDUSTRY_ID, "days": 3650}).json()["data"]
    assert listing["total"] >= 1
    row = next(i for i in listing["items"] if i["id"] == run_id)
    # 列表页只回摘要，不带回答正文
    assert "answer_text" not in row
    assert row["source_count"] == 3
    assert row["brand_visible"] is not None

    detail = client.get(f"/api/visibility/run/{run_id}", headers=auth_headers).json()["data"]
    assert detail["keyword"] == "可见性列表用例"
    assert detail["answer_text"]
    assert len(detail["sources"]) == 3
    assert detail["top_domains"]

    assert client.delete(f"/api/visibility/run/{run_id}", headers=auth_headers).status_code == 200
    assert client.get(f"/api/visibility/run/{run_id}", headers=auth_headers).status_code == 404


def test_sources_endpoint_requires_run_or_industry(client, auth_headers):
    assert client.get("/api/visibility/sources", headers=auth_headers).status_code == 400

    created = client.post("/api/visibility/collect", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID, "keyword": "信源明细用例",
        "provider_type": "mock", "auto_sync_reply": False,
    }).json()["data"]
    run_id = created["id"]
    try:
        rows = client.get("/api/visibility/sources", headers=auth_headers,
                          params={"run_id": run_id}).json()["data"]
        assert len(rows) == 3
        assert rows[0]["rank"] == 1
        assert all(r["domain"] for r in rows)
    finally:
        client.delete(f"/api/visibility/run/{run_id}", headers=auth_headers)
