"""
AI 爬虫 / 搜索引擎爬虫分类器（纯正则 + 子串匹配，零依赖）

设计目标
--------
回答一个此前系统完全无法回答的问题：**「我们发的文章，到底有没有被 AI 爬？」**

GEO 的最后一环是「发布 → 收录 → 排名 → 回流选题」。其中「收录」的**唯一客观证据**
就是服务器侧看到 AI 爬虫来抓过我们的页面。在此之前系统只有「发布成功」这一状态，
发布之后完全是个黑盒。

分类维度（五类）
----------------
- ``ai_bot``     —— 生成式引擎的抓取器（GPTBot / ClaudeBot / Bytespider / PerplexityBot …）
                   这些才是 GEO 真正关心的：它们决定内容能否进入 AI 的知识与检索层。
- ``search_bot`` —— 传统搜索引擎抓取器（Googlebot / Baiduspider / Bingbot …）
                   影响的是经典 SEO 收录，与 GEO 相关但不等价。
- ``other_bot``  —— 监控 / 采集 / 脚本类（UptimeRobot / SemrushBot / python-requests …）
                   既非 AI 也非搜索，单独归类避免污染前两类统计。
- ``human``      —— 真实浏览器 UA。
- ``unknown``    —— 空 UA 或无法判定。

匹配策略
--------
先按 **AI → 搜索 → 其他 → 人类** 的顺序匹配，且用「子串包含」而非「正则整串匹配」。
原因：真实 UA 形如 ``Mozilla/5.0 (compatible; Googlebot/2.1; +http://...)``，
既含 ``Mozilla`` 又含 ``Googlebot``；若先判人类就会把搜索引擎爬虫误判成真人。
顺序 + 子串是这里唯一稳妥的做法。

签名表按「**先具体后宽泛**」排列（``chatgpt-user`` 必须排在 ``chatgpt`` 之前），
首个命中的签名即为判定结果。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# —— 分类枚举（对外暴露的稳定取值，前端/统计按这些值分组）——
AI_BOT = "ai_bot"
SEARCH_BOT = "search_bot"
OTHER_BOT = "other_bot"
HUMAN = "human"
UNKNOWN = "unknown"

ALL_CLASSES = (AI_BOT, SEARCH_BOT, OTHER_BOT, HUMAN, UNKNOWN)

# 分类的中文展示名（前端直接渲染，避免各处重复维护映射）
CLASS_LABELS = {
    AI_BOT: "AI 爬虫",
    SEARCH_BOT: "搜索引擎爬虫",
    OTHER_BOT: "其他爬虫",
    HUMAN: "真实用户",
    UNKNOWN: "未知",
}


# ============================================================
#  AI 爬虫签名表（(展示名, 匹配子串)）
#  顺序敏感：更具体的签名必须排在更宽泛的签名之前。
# ============================================================
_AI_BOT_SIGNATURES: List[Tuple[str, str]] = [
    # —— OpenAI ——
    ("GPTBot", "gptbot"),
    ("ChatGPT-User", "chatgpt-user"),
    ("OAI-SearchBot", "oai-searchbot"),
    ("ChatGPT", "chatgpt"),
    ("OpenAI", "openai"),
    # —— Anthropic ——
    ("ClaudeBot", "claudebot"),
    ("Claude-SearchBot", "claude-searchbot"),
    ("Claude-User", "claude-user"),
    ("Claude-Web", "claude-web"),
    ("Anthropic", "anthropic"),
    # —— Perplexity ——
    ("PerplexityBot", "perplexitybot"),
    ("Perplexity-User", "perplexity-user"),
    ("Perplexity", "perplexity"),
    # —— 国内生成式引擎 ——
    # 字节跳动（豆包 / 即梦）抓取器，国内 AI 收录最主要的来源之一
    ("Bytespider", "bytespider"),
    ("Doubao", "doubao"),
    ("DeepSeek", "deepseek"),
    ("Kimi", "kimi"),
    ("Moonshot", "moonshot"),
    ("Qwen", "qwen"),
    ("Tongyi", "tongyi"),
    ("Yuanbao", "yuanbao"),          # 腾讯元宝
    ("BaiduAI", "baidubot"),         # 百度文心抓取器（区别于 Baiduspider 搜索抓取）
    ("AliGenie", "aligenie"),
    ("ZhipuAI", "zhipu"),
    # —— 其他国际 AI 抓取器 ——
    ("CCBot", "ccbot"),              # Common Crawl，大量模型训练语料的上游
    ("Google-Extended", "google-extended"),
    ("Applebot-Extended", "applebot-extended"),
    ("Meta-ExternalAgent", "meta-externalagent"),
    ("Cohere-AI", "cohere-ai"),
    ("YouBot", "youbot"),            # You.com
    ("Amazonbot", "amazonbot"),
    ("Diffbot", "diffbot"),
    ("Omgili", "omgili"),
    ("Timpibot", "timpibot"),
    ("Webz.io", "webzio"),
    ("ImagesiftBot", "imagesiftbot"),
    ("PanguBot", "pangubot"),        # 华为盘古
    ("PetalBot-AI", "petalbot-ai"),
    ("AI2Bot", "ai2bot"),            # Allen Institute
    ("FriendlyCrawler", "friendlycrawler"),
    ("ICC-Crawler", "icc-crawler"),
]

# ============================================================
#  搜索引擎爬虫签名表
# ============================================================
_SEARCH_BOT_SIGNATURES: List[Tuple[str, str]] = [
    ("Googlebot", "googlebot"),
    ("Google-InspectionTool", "google-inspectiontool"),
    ("GoogleOther", "googleother"),
    ("Storebot-Google", "storebot-google"),
    ("Bingbot", "bingbot"),
    ("AdIdxBot", "adidxbot"),
    ("BingPreview", "bingpreview"),
    ("Baiduspider", "baiduspider"),
    ("Sogou", "sogou"),
    ("360Spider", "360spider"),
    ("YisouSpider", "yisouspider"),      # 神马/UC 搜索
    ("ShenmaSpider", "shenmaspider"),
    ("YandexBot", "yandexbot"),
    ("DuckDuckBot", "duckduckbot"),
    ("DuckDuckGo", "duckduckgo"),
    ("Slurp", "slurp"),                  # Yahoo
    ("Exabot", "exabot"),
    ("PetalBot", "petalbot"),            # 华为搜索
    ("Applebot", "applebot"),
    ("NaverBot", "naver"),
    ("Daumoa", "daumoa"),
    ("Qwantify", "qwantify"),
    ("SeznamBot", "seznam"),
    ("Teoma", "teoma"),
    ("Gigabot", "gigabot"),
]

# ============================================================
#  其他爬虫 / 脚本签名表（SEO 工具、监控、归档、SDK、无头浏览器）
#
#  归类原则：``search_bot`` 只放**真正构建搜索引擎索引**的爬虫；
#  SEO 商业工具（Semrush / Ahrefs / MJ12 …）虽然也是「爬虫」，
#  但它们不服务于任何用户可查询的搜索引擎，归入 ``other_bot`` 更准确 ——
#  否则「搜索引擎爬虫」这个标签会误导运营判断。
# ============================================================
_OTHER_BOT_SIGNATURES: List[Tuple[str, str]] = [
    # SEO / 外链分析工具
    ("AhrefsBot", "ahrefsbot"),
    ("SemrushBot", "semrushbot"),
    ("MJ12bot", "mj12bot"),
    ("DotBot", "dotbot"),
    ("BLEXBot", "blexbot"),
    ("BacklinkCrawler", "backlinkcrawler"),
    ("MegaIndex", "megaindex"),
    ("Screaming Frog", "screaming frog"),
    # 网页归档
    ("ia_archiver", "ia_archiver"),      # Alexa / Wayback Machine
    # 监控服务
    ("UptimeRobot", "uptimerobot"),
    ("Pingdom", "pingdom"),
    ("StatusCake", "statuscake"),
    ("Site24x7", "site24x7"),
    ("BetterUptime", "betteruptime"),
    ("NewRelic", "newrelic"),
    ("Datadog", "datadog"),
    ("Zabbix", "zabbix"),
    ("Nagios", "nagios"),
    # HTTP 客户端 / 脚本
    ("python-requests", "python-requests"),
    ("python-urllib", "python-urllib"),
    ("aiohttp", "aiohttp"),
    ("httpx", "httpx"),
    ("Go-http-client", "go-http-client"),
    ("Java", "java/"),
    ("OkHttp", "okhttp"),
    ("Apache-HttpClient", "apache-httpclient"),
    ("axios", "axios"),
    ("node-fetch", "node-fetch"),
    ("undici", "undici"),
    ("curl", "curl/"),
    ("Wget", "wget/"),
    ("libwww-perl", "libwww-perl"),
    ("Scrapy", "scrapy"),
    ("HttpClient", "httpclient"),
    ("RestSharp", "restsharp"),
    ("PostmanRuntime", "postmanruntime"),
    ("Insomnia", "insomnia"),
    # 无头浏览器 / 自动化
    ("HeadlessChrome", "headlesschrome"),
    ("PhantomJS", "phantomjs"),
    ("Selenium", "selenium"),
    ("Puppeteer", "puppeteer"),
    ("Playwright", "playwright"),
    ("Electron", "electron"),
    # 安全扫描（不含 UA 的恶意扫描通常 UA 为空或伪造，能识别多少算多少）
    ("Nmap", "nmap"),
    ("Nikto", "nikto"),
    ("sqlmap", "sqlmap"),
    ("masscan", "masscan"),
    ("zgrab", "zgrab"),
    ("Censys", "censys"),
    ("Shodan", "shodan"),
    ("Netcraft", "netcraft"),
]

# 真人浏览器特征：命中任一即认为是浏览器；但必须放在爬虫判定之后使用
_HUMAN_BROWSER_MARKERS = (
    "mozilla/",
    "applewebkit",
    "chrome/",
    "safari/",
    "firefox/",
    "edg/",
    "edgios/",
    "opr/",
    "msie ",
    "trident/",
    "gecko/",
    "micromessenger",   # 微信内置浏览器
    "qqbrowser",
    "ucbrowser",
    "quark",
    "baiduboxapp",
)


def _match(user_agent: str, signatures: List[Tuple[str, str]]) -> Optional[str]:
    """在 UA 中按顺序查找首个命中的签名，返回展示名。"""
    for name, needle in signatures:
        if needle in user_agent:
            return name
    return None


def identify(user_agent: Optional[str]) -> Dict[str, str]:
    """识别 UA，返回 ``{"bot_class": ..., "bot_name": ..., "label": ...}``。

    ``bot_name`` 在未识别到具体爬虫时为空串；``human`` 类返回 ``"Browser"``，
    ``unknown`` 类返回空串。调用方不需要自己维护展示名映射。
    """
    ua = (user_agent or "").strip()
    if not ua:
        return {"bot_class": UNKNOWN, "bot_name": "", "label": CLASS_LABELS[UNKNOWN]}

    lowered = ua.lower()

    name = _match(lowered, _AI_BOT_SIGNATURES)
    if name:
        return {"bot_class": AI_BOT, "bot_name": name, "label": CLASS_LABELS[AI_BOT]}

    name = _match(lowered, _SEARCH_BOT_SIGNATURES)
    if name:
        return {"bot_class": SEARCH_BOT, "bot_name": name, "label": CLASS_LABELS[SEARCH_BOT]}

    name = _match(lowered, _OTHER_BOT_SIGNATURES)
    if name:
        return {"bot_class": OTHER_BOT, "bot_name": name, "label": CLASS_LABELS[OTHER_BOT]}

    if any(marker in lowered for marker in _HUMAN_BROWSER_MARKERS):
        return {"bot_class": HUMAN, "bot_name": "Browser", "label": CLASS_LABELS[HUMAN]}

    return {"bot_class": UNKNOWN, "bot_name": "", "label": CLASS_LABELS[UNKNOWN]}


def classify(user_agent: Optional[str]) -> str:
    """只取分类结果（``ai_bot`` / ``search_bot`` / ``other_bot`` / ``human`` / ``unknown``）。"""
    return identify(user_agent)["bot_class"]


def is_ai_bot(user_agent: Optional[str]) -> bool:
    """是否为生成式引擎抓取器。"""
    return classify(user_agent) == AI_BOT


def is_crawler(user_agent: Optional[str]) -> bool:
    """是否为任何非人类爬虫（含 AI / 搜索 / 其他）。"""
    return classify(user_agent) in (AI_BOT, SEARCH_BOT, OTHER_BOT)


def ai_bot_names() -> List[str]:
    """AI 爬虫展示名清单（供前端展示「我们关注哪些 AI 抓取器」）。"""
    return [name for name, _ in _AI_BOT_SIGNATURES]


def search_bot_names() -> List[str]:
    """搜索引擎爬虫展示名清单。"""
    return [name for name, _ in _SEARCH_BOT_SIGNATURES]
