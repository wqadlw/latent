"""AI 抓取入口 + 收录观测 API 测试。

守护两条关键不变量：
1. ``/llms.txt`` ``/sitemap.xml`` ``/robots.txt`` **必须匿名可访问** ——
   爬虫不带令牌，一旦被挂上守卫，整个 GEO 抓取入口就废了；
2. 访问日志导入 → 分类 → 归因这条链路端到端可用。
"""


SAMPLE_NGINX_LOG = """127.0.0.1 - - [10/Oct/2026:20:57:06 +0800] "GET /case/vacuum-pump HTTP/1.1" 200 1234 "-" "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)"
10.0.0.2 - - [10/Oct/2026:20:58:00 +0800] "GET /case/vacuum-pump HTTP/1.1" 200 1234 "-" "Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)"
10.0.0.3 - - [10/Oct/2026:20:59:00 +0800] "GET /products/root-pump HTTP/1.1" 200 900 "-" "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
10.0.0.4 - - [10/Oct/2026:21:00:00 +0800] "GET /case/vacuum-pump HTTP/1.1" 200 1234 "-" "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
this line is garbage and must be skipped
"""


# ============================================================
#  公开端点：AI 抓取入口
# ============================================================
def test_llms_txt_is_public(client):
    resp = client.get("/llms.txt")
    assert resp.status_code == 200, "llms.txt 必须匿名可访问"
    assert "text/plain" in resp.headers["content-type"]
    assert resp.text.startswith("#")


def test_sitemap_xml_is_public_and_wellformed(client):
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200, "sitemap.xml 必须匿名可访问"
    assert "xml" in resp.headers["content-type"]
    assert resp.text.startswith("<?xml")
    assert "<urlset" in resp.text and "</urlset>" in resp.text


def test_robots_txt_is_public_and_allows_ai_bots(client):
    resp = client.get("/robots.txt")
    assert resp.status_code == 200, "robots.txt 必须匿名可访问"
    # GEO 场景的默认立场是欢迎 AI 抓取
    assert "User-agent: GPTBot" in resp.text
    assert "User-agent: Bytespider" in resp.text
    assert "Sitemap:" in resp.text


def test_robots_can_deny_ai_bots(client):
    resp = client.get("/robots.txt", params={"allow_ai": "false"})
    assert resp.status_code == 200
    assert "User-agent: GPTBot" in resp.text
    assert "Disallow: /" in resp.text


def test_site_index_accepts_site_override(client):
    resp = client.get("/sitemap.xml", params={"site": "example.org"})
    assert resp.status_code == 200
    assert "https://example.org" in resp.text


# ============================================================
#  受保护端点：收录观测
# ============================================================
def test_crawler_endpoints_require_auth(client):
    for path in ("/api/crawler/bots", "/api/crawler/stats", "/api/crawler/hit", "/api/site/index"):
        resp = client.get(path)
        assert resp.status_code == 401, f"{path} 未拦截未登录请求"


def test_crawler_bots_lists_tracked_agents(client, auth_headers):
    resp = client.get("/api/crawler/bots", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "GPTBot" in data["ai_bots"]
    assert "Googlebot" in data["search_bots"]
    assert any(c["value"] == "ai_bot" for c in data["classes"])


def test_import_access_log_end_to_end(client, auth_headers):
    """粘贴 Nginx 日志 → 解析 → 分类 → 入库，真人被过滤、脏行被跳过。"""
    resp = client.post(
        "/api/crawler/import-log",
        headers=auth_headers,
        json={"text": SAMPLE_NGINX_LOG},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["parsed"] == 4, "4 行有效日志（第 5 行是脏数据）"
    assert data["unparsable_lines"] == 1
    assert data["skipped_human"] == 1, "Chrome 真人访问必须被过滤"
    assert data["imported"] == 3

    stats = client.get("/api/crawler/stats", headers=auth_headers, params={"days": 3650}).json()["data"]
    assert stats["total_hits"] >= 3
    assert stats["ai_bot_hits"] >= 2, "GPTBot + Bytespider"
    assert stats["search_bot_hits"] >= 1, "Googlebot"

    bots = {b["bot_name"] for b in stats["by_bot"]}
    assert {"GPTBot", "Bytespider", "Googlebot"} <= bots


def test_import_is_idempotent_by_dedupe(client, auth_headers):
    """重复粘贴同一份日志不应让统计翻倍 —— 这是运营最可能踩的坑。"""
    before = client.get("/api/crawler/stats", headers=auth_headers, params={"days": 3650}).json()["data"]
    resp = client.post(
        "/api/crawler/import-log",
        headers=auth_headers,
        json={"text": SAMPLE_NGINX_LOG, "dedupe": True},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["imported"] == 0
    assert resp.json()["data"]["duplicated"] == 3

    after = client.get("/api/crawler/stats", headers=auth_headers, params={"days": 3650}).json()["data"]
    assert after["total_hits"] == before["total_hits"]


def test_import_rejects_empty_and_garbage(client, auth_headers):
    assert client.post("/api/crawler/import-log", headers=auth_headers, json={"text": ""}).status_code == 400
    assert client.post(
        "/api/crawler/import-log", headers=auth_headers, json={"text": "not a log line at all"}
    ).status_code == 400


def test_hit_listing_and_filtering(client, auth_headers):
    resp = client.get("/api/crawler/hit", headers=auth_headers,
                      params={"days": 3650, "bot_class": "ai_bot"})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert items, "应有 AI 爬虫记录"
    assert all(i["bot_class"] == "ai_bot" for i in items)

    filtered = client.get("/api/crawler/hit", headers=auth_headers,
                          params={"days": 3650, "keyword": "root-pump"}).json()["data"]["items"]
    assert all("root-pump" in i["path"] for i in filtered)


def test_site_index_preview(client, auth_headers):
    resp = client.get("/api/site/index", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["llms_txt"].startswith("#")
    assert data["sitemap_xml"].startswith("<?xml")
    assert "User-agent" in data["robots_txt"]
    assert "entry_count" in data


def test_trend_endpoint(client, auth_headers):
    resp = client.get("/api/crawler/trend", headers=auth_headers, params={"days": 3650})
    assert resp.status_code == 200
    trend = resp.json()["data"]
    assert isinstance(trend, list)
    if trend:
        assert {"date", "ai_bot"} <= set(trend[0].keys())


# ============================================================
#  中间件：本机流量也要能被记录
# ============================================================
def test_middleware_records_bot_traffic(client, auth_headers):
    """用爬虫 UA 访问一个内容路径，应被中间件记录；真人 UA 不应被记录。"""
    client.get("/some-content-page", headers={"User-Agent": "Mozilla/5.0 (compatible; PerplexityBot/1.0)"})
    client.get("/another-page", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0.0.0"})

    items = client.get("/api/crawler/hit", headers=auth_headers,
                       params={"days": 1, "bot_name": "PerplexityBot"}).json()["data"]["items"]
    assert items, "PerplexityBot 的访问应被记录"

    human = client.get("/api/crawler/hit", headers=auth_headers,
                       params={"days": 1, "keyword": "another-page"}).json()["data"]["items"]
    assert not human, "真人访问默认不应落库"


def test_middleware_skips_api_and_assets(client, auth_headers):
    """接口与静态资源不应污染抓取统计。"""
    client.get("/api/meta", headers={"User-Agent": "Mozilla/5.0 (compatible; GPTBot/1.0)"})
    items = client.get("/api/crawler/hit", headers=auth_headers,
                       params={"days": 1, "keyword": "/api/meta"}).json()["data"]["items"]
    assert not items
