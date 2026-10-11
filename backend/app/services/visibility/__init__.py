"""AI 可见性采集（Visibility Collection）

把「AI 到底怎么回答我的问题、引用了谁」从**人工复制粘贴**升级为**自动并发探测**。

数据模型分两层（对应 GEOFlow 的 ``AiVisibilityRun`` / ``AiVisibilitySource``）：

- ``GeoVisibilityRun``    一次探测（一个问题 × 一个引擎 × 一次调用）
- ``GeoVisibilitySource`` 该次探测里 AI 引用到的信源（N 条）

**为什么必须存信源**：只知道自己被提没被提，不足以指导内容策略。
知道「AI 在回答『真空泵怎么选型』时引用了 A/B/C 三个站点」，
才能回答「内容该铺到哪里」——这是整个 GEO 闭环里最可执行的一条数据。

分层（B2 采集 → B3 分析）：

- ``base`` / ``collector``  采集：怎么拿到回答、怎么落库
- ``metrics`` / ``normalizer``  解析：回答 → 指标 + 信源（手工流与自动流共用）
- ``analytics``  分析：6 KPI + 趋势 + 信源偏好榜 + 选题回流
- ``competitor``  对比：我们 vs 竞品
"""
from .analytics import compute_kpis, daily_trend, overview, source_preferences, topic_suggestions
from .base import BaseVisibilityProvider, SourceData, VisibilityResult, get_provider_cls, list_provider_types
from .collector import collect_multi, collect_one, sync_reply_from_run
from .competitor import board as competitor_board
from .competitor import detect_from_run, detect_in_text
from .metrics import parse_ai_reply
from .normalizer import analyze_answer, extract_sources

__all__ = [
    "BaseVisibilityProvider",
    "SourceData",
    "VisibilityResult",
    "get_provider_cls",
    "list_provider_types",
    "collect_one",
    "collect_multi",
    "sync_reply_from_run",
    "parse_ai_reply",
    "analyze_answer",
    "extract_sources",
    "compute_kpis",
    "daily_trend",
    "overview",
    "source_preferences",
    "topic_suggestions",
    "competitor_board",
    "detect_from_run",
    "detect_in_text",
]
