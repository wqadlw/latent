"""
爬虫流量日志中间件（纯 ASGI，不依赖 BaseHTTPMiddleware）

作用
----
把每一次**非人类**请求落到 ``crawler_hit`` 表，让「AI 到底有没有来抓我们」这件事
从「不可观测」变成「可查询」。这是 GEO 归因闭环（发布 → 收录 → 排名 → 回流选题）
里「收录」环节唯一的一手证据。

为什么用纯 ASGI 而不是 ``BaseHTTPMiddleware``
--------------------------------------------
- 不包裹响应体，对静态文件 / 流式响应零干扰；
- 少一层 anyio 任务组，开销更低；
- 只在 ``http.response.start`` 上取一次状态码，逻辑简单可控。

落库时机
--------
在 ``await self.app(...)`` **返回之后**（即响应已完整发给客户端）才写库，
因此不会增加客户端感知到的延迟。写库走线程池，不阻塞事件循环。

开关
----
- ``APP_TRAFFIC_LOG=0``       —— 整体关闭（默认开启）
- ``APP_TRAFFIC_LOG_ALL=1``   —— 连真人访问也记录（默认只记爬虫，避免表体积失控）
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, Optional

from starlette.concurrency import run_in_threadpool

from ..services.crawler_classifier import HUMAN, identify

# 不记录这些前缀：静态资源、接口文档、前端产物，对 GEO 归因没有意义
_SKIP_PREFIXES = (
    "/assets/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/api/",
)

# 单个 UA / 路径的落库长度上限，防止超长 UA 撑爆表
_MAX_UA_LEN = 512
_MAX_PATH_LEN = 512


def _truthy(name: str, default: str = "0") -> bool:
    return (os.environ.get(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


def _hash_ip(ip: str) -> str:
    """IP 只存哈希前 16 位：足以区分同源/异源，又不落明文，规避个人信息合规风险。"""
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8", "ignore")).hexdigest()[:16]


def _client_ip(scope: Dict[str, Any]) -> str:
    """取客户端 IP。优先 X-Forwarded-For 首段（反代场景），回退到 socket peer。"""
    for raw_name, raw_value in scope.get("headers") or []:
        if raw_name == b"x-forwarded-for":
            try:
                return raw_value.decode("latin-1").split(",")[0].strip()
            except Exception:  # noqa: BLE001
                break
    client = scope.get("client")
    if isinstance(client, (tuple, list)) and client:
        return str(client[0] or "")
    return ""


def _header(scope: Dict[str, Any], name: bytes) -> str:
    for raw_name, raw_value in scope.get("headers") or []:
        if raw_name == name:
            try:
                return raw_value.decode("latin-1")
            except Exception:  # noqa: BLE001
                return ""
    return ""


def _should_skip(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _SKIP_PREFIXES)


def _record(info: Dict[str, Any]) -> None:
    """把一条命中写入 ``crawler_hit``。

    任何异常都吞掉 —— 日志写入失败绝不能影响业务请求。
    """
    try:
        from ..database import SessionLocal
        from ..models import CrawlerHit

        with SessionLocal() as db:
            db.add(CrawlerHit(**info))
            db.commit()
    except Exception:  # noqa: BLE001
        pass


class TrafficLogMiddleware:
    """记录爬虫抓取行为的 ASGI 中间件。"""

    def __init__(self, app, enabled: Optional[bool] = None, log_all: Optional[bool] = None):
        self.app = app
        self.enabled = _truthy("APP_TRAFFIC_LOG", "1") if enabled is None else enabled
        self.log_all = _truthy("APP_TRAFFIC_LOG_ALL", "0") if log_all is None else log_all

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if _should_skip(path):
            await self.app(scope, receive, send)
            return

        # CORS 预检不是内容抓取，跳过
        if (scope.get("method") or "").upper() == "OPTIONS":
            await self.app(scope, receive, send)
            return

        ua = _header(scope, b"user-agent")
        verdict = identify(ua)
        bot_class = verdict["bot_class"]

        # 真人流量默认不落库
        if bot_class == HUMAN and not self.log_all:
            await self.app(scope, receive, send)
            return

        status_holder = {"status": 0}

        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                status_holder["status"] = int(message.get("status") or 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            info = {
                "path": path[:_MAX_PATH_LEN],
                "query": (scope.get("query_string") or b"").decode("latin-1")[:512],
                "user_agent": ua[:_MAX_UA_LEN],
                "bot_class": bot_class,
                "bot_name": verdict["bot_name"],
                "method": (scope.get("method") or "GET")[:8],
                "status_code": status_holder["status"],
                "referer": _header(scope, b"referer")[:512],
                "ip_hash": _hash_ip(_client_ip(scope)),
            }
            await run_in_threadpool(_record, info)


def install_traffic_log(app) -> None:
    """把中间件挂到 FastAPI 应用上。

    单独抽成函数是为了让 ``main.py`` 的装配代码保持一行，也便于测试里按需绕过。
    """
    app.add_middleware(TrafficLogMiddleware)
