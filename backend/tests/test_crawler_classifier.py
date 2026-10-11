"""爬虫分类器单元测试。

这是 GEO 收录观测的判定内核：分类错了，后面所有统计都是错的。
重点守护三件事：
1. 三类爬虫各归其位，不互相串；
2. **含 Mozilla 前缀的真实爬虫 UA 不被误判成真人**（最容易踩的坑）；
3. 更具体的签名优先于更宽泛的签名（``chatgpt-user`` 不能落进 ``chatgpt``）。
"""
import pytest
from app.services.crawler_classifier import (
    AI_BOT,
    HUMAN,
    OTHER_BOT,
    SEARCH_BOT,
    UNKNOWN,
    ai_bot_names,
    classify,
    identify,
    is_ai_bot,
    is_crawler,
)


# ============================================================
#  AI 爬虫
# ============================================================
@pytest.mark.parametrize("ua,expected_name", [
    ("Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)", "GPTBot"),
    ("Mozilla/5.0 (compatible; ChatGPT-User/1.0; +https://openai.com/bot)", "ChatGPT-User"),
    ("Mozilla/5.0 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)", "OAI-SearchBot"),
    ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "ClaudeBot"),
    ("Mozilla/5.0 (compatible; Claude-SearchBot/1.0)", "Claude-SearchBot"),
    ("Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)", "PerplexityBot"),
    ("Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)", "Bytespider"),
    ("Mozilla/5.0 (compatible; CCBot/2.0; +https://commoncrawl.org/faq/)", "CCBot"),
    ("Mozilla/5.0 (compatible; Google-Extended/1.0)", "Google-Extended"),
    ("Mozilla/5.0 (compatible; Applebot-Extended/0.1)", "Applebot-Extended"),
    ("meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)", "Meta-ExternalAgent"),
    ("Mozilla/5.0 (compatible; YouBot/1.0)", "YouBot"),
    ("DeepSeek-Crawler/1.0", "DeepSeek"),
])
def test_ai_bots_classified(ua, expected_name):
    verdict = identify(ua)
    assert verdict["bot_class"] == AI_BOT, f"{ua} 应判为 AI 爬虫，实际 {verdict}"
    assert verdict["bot_name"] == expected_name


def test_ai_bot_helpers():
    assert is_ai_bot("GPTBot/1.0") is True
    assert is_ai_bot("Mozilla/5.0 (Windows NT 10.0) Chrome/120.0") is False
    assert is_crawler("GPTBot/1.0") is True
    assert is_crawler("Mozilla/5.0 (Windows NT 10.0) Chrome/120.0") is False


# ============================================================
#  搜索引擎爬虫
# ============================================================
@pytest.mark.parametrize("ua,expected_name", [
    ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "Googlebot"),
    ("Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)", "Bingbot"),
    ("Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)", "Baiduspider"),
    ("Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)", "YandexBot"),
    ("Sogou web spider/4.0(+http://www.sogou.com/docs/help/webmasters.htm#07)", "Sogou"),
    ("Mozilla/5.0 (compatible; 360Spider)", "360Spider"),
])
def test_search_bots_classified(ua, expected_name):
    verdict = identify(ua)
    assert verdict["bot_class"] == SEARCH_BOT
    assert verdict["bot_name"] == expected_name


def test_search_bot_is_not_ai_bot():
    """搜索引擎爬虫不能被算进 AI 收录统计 —— 两者的业务含义完全不同。"""
    assert classify("Mozilla/5.0 (compatible; Googlebot/2.1)") == SEARCH_BOT
    assert is_ai_bot("Mozilla/5.0 (compatible; Googlebot/2.1)") is False


# ============================================================
#  其他爬虫 / 脚本
# ============================================================
@pytest.mark.parametrize("ua", [
    "python-requests/2.31.0",
    "curl/8.4.0",
    "Go-http-client/1.1",
    "Mozilla/5.0 (compatible; UptimeRobot/2.0)",
    "Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/120.0.0.0",
    # SEO 商业工具：不服务于任何用户可查询的搜索引擎，归入 other_bot
    "Mozilla/5.0 (compatible; SemrushBot/7~bl)",
    "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)",
    "Mozilla/5.0 (compatible; DotBot/1.2; +https://opensiteexplorer.org/dotbot)",
])
def test_other_bots_classified(ua):
    assert classify(ua) == OTHER_BOT


# ============================================================
#  真人 / 未知
# ============================================================
@pytest.mark.parametrize("ua", [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) MicroMessenger/8.0.44",
])
def test_human_browsers_classified(ua):
    assert classify(ua) == HUMAN


@pytest.mark.parametrize("ua", [None, "", "   ", "some-random-client"])
def test_unknown_classified(ua):
    assert classify(ua) == UNKNOWN


# ============================================================
#  签名优先级
# ============================================================
def test_specific_signature_wins_over_generic():
    """``chatgpt-user`` 必须排在 ``chatgpt`` 之前，否则前者永远匹配不到。"""
    assert identify("Mozilla/5.0 (compatible; ChatGPT-User/1.0)")["bot_name"] == "ChatGPT-User"
    assert identify("Mozilla/5.0 (compatible; ChatGPT/1.0)")["bot_name"] == "ChatGPT"


def test_mozilla_prefix_does_not_override_crawler_detection():
    """真实爬虫 UA 普遍带 ``Mozilla/5.0`` 前缀，绝不能因此被判成真人。

    这是分类器最关键的一条不变量：判定顺序必须是
    AI → 搜索 → 其他 → 真人，而不是先看有没有 Mozilla。
    """
    for ua in [
        "Mozilla/5.0 (compatible; GPTBot/1.0)",
        "Mozilla/5.0 (compatible; Googlebot/2.1)",
        "Mozilla/5.0 (compatible; SemrushBot/7~bl)",
    ]:
        assert classify(ua) != HUMAN, f"{ua} 被误判为真人"


def test_ai_bot_list_is_not_empty():
    names = ai_bot_names()
    assert len(names) >= 20
    # 去重（签名表手工维护，容易重复）
    assert len(names) == len(set(names))
