# -*- coding: utf-8 -*-
"""
平台发布器（PlatformPublisher）

职责：把"已通过审核的最终稿"真正发到目标平台。
设计：适配器可插拔，当前落地两条路线——
  1) Playwright 兜底适配器（zhihu / sohu / wangyi）：无官方 Open API 的平台用浏览器自动化。
  2) Mock 适配器：模拟发布，返回假 URL，用于在不装浏览器/无凭证时验证整条流水线。

官方 Open API 适配器（微信/小红书/百家号/头条）因当前无资质暂缓，抽象层已预留（adapter_type='api'）。

⚠️ ToS / 合规风险提示（务必知悉）：
  各平台服务条款普遍禁止自动化批量发布营销内容，存在限流 / 封号风险；
  且低质自动内容可能对 GEO 反噬（被降权、被当噪声）。
  本模块仅供"用户在本机对自己的账号、知情授权后"使用，绝不自动破解 2FA；
  登录态由用户手动登录后导出 cookie 上传。发布节奏请拟人化、错峰，保留人工审核闸门。

实现约定：
  - 仅用标准库 + 可选 playwright（懒加载 import，未安装时优雅降级，不崩溃）。
  - publish() 返回 PublishResult，绝不抛未捕获异常给调用方；失败信息进 result.error + log。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ============================================================
#  浏览器探测（优先用 Playwright 官方 channel 复用本机已装的
#  Microsoft Edge / Google Chrome，避免从 Playwright CDN 下载 chromium
#  —— 很多内网/沙箱拉不下来；channel 方式由 Playwright 官方维护，
#  CDP 兼容性最稳，优于手动指定 executable_path）
# ============================================================
def _local_app_paths(*parts: str) -> List[str]:
    """用户级安装路径（%LOCALAPPDATA%\\...），跨机器可移植。

    Edge / Chrome 的用户级安装位于 %LOCALAPPDATA%，不能硬编码用户名。
    """
    local = os.environ.get("LOCALAPPDATA")
    return [os.path.join(local, *parts)] if local else []


def _resolve_chromium_executable() -> Optional[str]:
    """按优先级返回可用的 Chromium 内核浏览器路径，找不到返回 None。

    优先级：
      1) 环境变量 PROMPT_MATRIX_CHROME_PATH（用户强制指定）
      2) 本机已装的 Microsoft Edge / Google Chrome（Chromium 内核，Playwright 可驱动）
    注意：不主动使用 Playwright 自带的 chromium（需 CDN 下载，本环境常被拦）。
    """
    forced = os.environ.get("PROMPT_MATRIX_CHROME_PATH")
    if forced and os.path.isfile(forced):
        return forced
    candidates = [
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        *_local_app_paths("Microsoft", "Edge", "Application", "msedge.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        *_local_app_paths("Google", "Chrome", "Application", "chrome.exe"),
        r"C:\Program Files\Chromium\Application\chrome.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


# channel 名 → 探测该浏览器是否安装（仅当存在时才用 channel，避免 Playwright 报错）
_CHANNEL_EXE_CANDIDATES: Dict[str, List[str]] = {
    "msedge": [
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        *_local_app_paths("Microsoft", "Edge", "Application", "msedge.exe"),
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        *_local_app_paths("Google", "Chrome", "Application", "chrome.exe"),
    ],
}


def _detect_channel() -> Optional[str]:
    """探测本机已安装的、Playwright 支持的 channel（msedge 优先，其次 chrome）。"""
    for ch, paths in _CHANNEL_EXE_CANDIDATES.items():
        if any(os.path.isfile(p) for p in paths):
            return ch
    return None


def _browser_launch_kwargs(headless: bool = True) -> Dict[str, Any]:
    """返回 Playwright launch 参数：优先官方 channel（最稳），否则回退 executable_path。

    用 channel 时由 Playwright 官方维护 CDP 兼容，比手写 executable_path 更可靠；
    都不可用时退化为空（依赖 Playwright 自带 chromium，可能需先下载）。
    """
    ch = _detect_channel()
    if ch:
        return {"headless": headless, "channel": ch}
    exe = _resolve_chromium_executable()
    if exe:
        return {"headless": headless, "executable_path": exe}
    return {"headless": headless}


# ============================================================
#  发布结果
# ============================================================
@dataclass
class PublishResult:
    status: str = "failed"          # published | failed
    url: str = ""                   # 发布成功后的文章 URL
    raw: Dict[str, Any] = field(default_factory=dict)
    log: str = ""                   # 步骤日志（含截图路径/耗时）
    needs_relogin: bool = False     # True 表示登录态失效，需人工续期


# ============================================================
#  平台目录（前端 /api/platforms 使用）
#  每个平台声明可用适配器类型与发布页，selector 仅作参考，需按平台实际 DOM 校验。
# ============================================================
PLATFORM_CATALOG: List[Dict[str, Any]] = [
    {
        "platform": "zhihu",
        "name": "知乎",
        "adapter_type": "playwright",
        "note": "专业问答/长文，AI 收录极高；需 cookie 登录态。",
        "publish_url": "https://www.zhihu.com/write",
    },
    {
        "platform": "sohu",
        "name": "搜狐号",
        "adapter_type": "playwright",
        "note": "自媒体发布；需 cookie 登录态。",
        "publish_url": "https://mp.sohu.com/mpfe/v3/article/write",
    },
    {
        "platform": "wangyi",
        "name": "网易号",
        "adapter_type": "playwright",
        "note": "自媒体发布；需 cookie 登录态。",
        "publish_url": "https://mp.163.com/media/article/write/",
    },
    {
        "platform": "wechat",
        "name": "微信公众号",
        "adapter_type": "api",
        "note": "官方 Open API（需认证服务号 appid/appsecret），当前无资质暂缓。",
        "publish_url": "",
    },
    {
        "platform": "xiaohongshu",
        "name": "小红书",
        "adapter_type": "api",
        "note": "官方开放平台专业号（需资质），当前暂缓。",
        "publish_url": "",
    },
    {
        "platform": "baijiahao",
        "name": "百家号",
        "adapter_type": "api",
        "note": "百度百家号开放平台（需资质），当前暂缓。",
        "publish_url": "",
    },
    {
        "platform": "toutiao",
        "name": "头条/抖音",
        "adapter_type": "api",
        "note": "头条开放平台（需资质），当前暂缓。",
        "publish_url": "",
    },
]

# Playwright 各平台的发布页填写选择器（参考值，需按实际 DOM 校验后微调）
PLAYWRIGHT_SELECTORS: Dict[str, Dict[str, Any]] = {
    "zhihu": {
        "publish_url": "https://www.zhihu.com/write",
        "title": {"selector": "textarea[placeholder*='标题'], .WriteTitle-title", "mode": "fill"},
        "content": {"selector": ".RichText-editor, .DraftEditor-editorContainer", "mode": "html"},
        "submit": {"selector": "button:has-text('发布')", "mode": "click"},
        "success_url_contains": "zhuanlan.zhihu.com/p/",
    },
    "sohu": {
        "publish_url": "https://mp.sohu.com/mpfe/v3/article/write",
        "title": {"selector": "input[placeholder*='标题'], .article-title input", "mode": "fill"},
        "content": {"selector": ".editor-body, [contenteditable='true']", "mode": "html"},
        "submit": {"selector": "button:has-text('发布')", "mode": "click"},
        "success_url_contains": "www.sohu.com/a/",
    },
    "wangyi": {
        "publish_url": "https://mp.163.com/media/article/write/",
        "title": {"selector": "input[placeholder*='标题'], .article-title input", "mode": "fill"},
        "content": {"selector": ".edui-body, [contenteditable='true']", "mode": "html"},
        "submit": {"selector": "button:has-text('发布')", "mode": "click"},
        "success_url_contains": "www.163.com/",
    },
}

# 各平台登录页（交互式 Cookie 捕获：弹真实浏览器让用户登录）
LOGIN_URLS: Dict[str, str] = {
    "zhihu": "https://www.zhihu.com/login",
    "sohu": "https://mp.sohu.com/mpfe/v3/login",
    "wangyi": "https://mp.163.com/login",
}

# 登录态多信号识别（比单一 cookie 名更稳）：任一信号命中即认为"已登录"。
#   cookies   —— 登录后可能出现的会话 cookie 名（取并集，命中任意一个即可）
#   url_has   —— 登录后页面 URL 应包含的特征串（如控制台域名）
#   not_url   —— 若 URL 含这些串（login/signin）则视为未登录
# 设计依据：单点 cookie 名常因平台改版而失效，多信号 OR 大幅提升自动捕获触发率。
LOGIN_CHECK: Dict[str, Dict[str, Any]] = {
    "zhihu": {
        "cookies": ["z_c0", "d_c0", "KLBRSID"],
        "url_has": ["zhihu.com"],
        "not_url": ["/login", "/signin", "sign_in"],
    },
    "sohu": {
        "cookies": ["passport_session", "sohu_session", "PASSPORT_SESSION", "sess_publish"],
        "url_has": ["mp.sohu.com", "sohu.com"],
        "not_url": ["/login", "/signin"],
    },
    "wangyi": {
        "cookies": ["NTES_SESS", "NTES_PASSPORT", "P_INFO"],
        "url_has": ["mp.163.com", "163.com"],
        "not_url": ["/login", "/signin"],
    },
}

# 各平台 cookie 归属域名（用于捕获时按域名过滤，去掉无关站点 cookie，减小体积也更干净）
PLATFORM_DOMAINS: Dict[str, List[str]] = {
    "zhihu": [".zhihu.com", "zhihu.com"],
    "sohu": [".sohu.com", "sohu.com", ".mp.sohu.com"],
    "wangyi": [".163.com", "163.com", ".mp.163.com"],
}


# ============================================================
#  适配器抽象
# ============================================================
class PlatformAdapter(ABC):
    platform: str = ""
    adapter_type: str = "playwright"

    @abstractmethod
    def publish(
        self,
        title: str,
        content: str,
        cover: Optional[str],
        cred_json: str,
        log: List[str],
    ) -> PublishResult:
        """执行一次发布。cred_json 为凭证原文（cookie JSON 数组 或 {username,password}）。
        log 为可变列表，适配器 Append 步骤日志。"""
        raise NotImplementedError


class MockAdapter(PlatformAdapter):
    """模拟发布：不触达任何平台，返回假 URL。用于验证 create→review→run→回写 全链路。"""
    adapter_type = "mock"

    def __init__(self, platform: str):
        self.platform = platform

    def publish(self, title, content, cover, cred_json, log):
        log.append(f"[mock] 模拟发布到 {self.platform}：标题《{title[:20]}…》")
        time.sleep(0.3)  # 模拟网络耗时
        slug = str(int(time.time()))[-8:]
        url = f"https://mock.publish.local/{self.platform}/article/{slug}"
        log.append(f"[mock] 发布成功（模拟），URL={url}")
        return PublishResult(status="published", url=url, raw={"mock": True}, log="\n".join(log))


class PlaywrightAdapter(PlatformAdapter):
    """Playwright 浏览器自动化发布。懒加载 playwright，未安装时优雅降级。"""
    adapter_type = "playwright"

    def __init__(self, platform: str):
        self.platform = platform
        self.cfg = PLAYWRIGHT_SELECTORS.get(platform, {})

    def _parse_credential(self, cred_json: str) -> Dict[str, Any]:
        """解析凭证原文，返回 {mode, ...}。

        - storage_state：捕获时存的完整登录态（cookies+localStorage），最可靠
        - cookies：纯 cookie 数组（旧格式或手动粘贴）
        - none：无法解析
        """
        try:
            data = json.loads(cred_json or "[]")
        except Exception:
            return {"mode": "none"}
        if isinstance(data, list):
            return {"mode": "cookies", "cookies": data}
        if isinstance(data, dict):
            # storage_state 形态：含 cookies 键（Playwright 标准结构）
            if "cookies" in data:
                return {"mode": "storage_state", "state": data}
            if "username" in data or "password" in data:
                return {"mode": "password", "data": data}
        return {"mode": "none"}

    def _load_cookies(self, cred_json: str) -> List[Dict[str, Any]]:
        parsed = self._parse_credential(cred_json)
        if parsed["mode"] in ("cookies",):
            return parsed.get("cookies", []) or []
        if parsed["mode"] == "storage_state":
            return (parsed.get("state", {}) or {}).get("cookies", []) or []
        return []

    def publish(self, title, content, cover, cred_json, log):
        parsed = self._parse_credential(cred_json)
        if parsed["mode"] == "none":
            log.append(f"[playwright] {self.platform} 无有效凭证，标记需重新登录")
            return PublishResult(
                status="failed", needs_relogin=True,
                error="未配置有效 cookie 凭证。请在本机手动登录后导出 cookie 上传，或用「手动粘贴 Cookie」导入。",
                log="\n".join(log),
            )

        # 懒加载 playwright，避免未安装时 import 失败拖垮整个后端
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as e:
            log.append(f"[playwright] 未安装 playwright：{e}")
            return PublishResult(
                status="failed",
                error="服务端未安装 playwright，且未检测到本机 Edge/Chrome。可二选一：① 安装本机 Microsoft Edge 或 Google Chrome（推荐，自动复用）；② pip install playwright && playwright install chromium",
                log="\n".join(log),
            )

        publish_url = self.cfg.get("publish_url") or self._catalog_url()
        if not publish_url:
            return PublishResult(status="failed", error=f"{self.platform} 未配置发布页地址", log="\n".join(log))

        screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "publish")
        os.makedirs(screenshot_dir, exist_ok=True)
        shot = os.path.join(screenshot_dir, f"{self.platform}_{int(time.time())}.png")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(**_browser_launch_kwargs(True))
                # 优先用完整 storage_state（cookies + localStorage）恢复登录态，比纯 add_cookies 更稳
                if parsed["mode"] == "storage_state":
                    context = browser.new_context(storage_state=parsed.get("state", {}))
                    log.append(f"[playwright] 使用 storage_state 恢复登录态（{len(parsed.get('state', {}).get('cookies', []))} cookies）")
                else:
                    cookies = parsed.get("cookies", []) or []
                    context = browser.new_context()
                    if cookies:
                        context.add_cookies(cookies)
                    log.append(f"[playwright] 使用 {len(cookies)} 条 cookie 恢复登录态")
                page = context.new_page()
                log.append(f"[playwright] 打开发布页 {publish_url}")
                page.goto(publish_url, wait_until="domcontentloaded", timeout=30000)

                # 检测登录态：若被重定向到登录页，说明 cookie 失效
                if "login" in page.url or "signin" in page.url:
                    page.screenshot(path=shot)
                    browser.close()
                    log.append(f"[playwright] 检测到未登录（{page.url}），截图 {shot}")
                    return PublishResult(
                        status="failed", needs_relogin=True,
                        error="cookie 登录态已失效，请重新登录导出 cookie。",
                        log="\n".join(log),
                    )

                # 填标题
                t = self.cfg.get("title", {})
                page.fill(t["selector"], title, timeout=15000)
                log.append(f"[playwright] 已填标题")

                # 填正文（HTML 走 contenteditable，fill 走 textarea/input）
                c = self.cfg.get("content", {})
                if c.get("mode") == "html":
                    page.evaluate(
                        "(sel, html) => { document.querySelector(sel).innerHTML = html; }",
                        c["selector"], content,
                    )
                else:
                    page.fill(c["selector"], content, timeout=15000)
                log.append(f"[playwright] 已填正文（{len(content)} 字符）")

                # 封面（可选）：若提供且平台支持，上传；此处仅占位，按平台实现
                if cover:
                    log.append("[playwright] 封面图已提供，但当前通用适配器未实现封面上传（按平台定制）")

                # 提交
                s = self.cfg.get("submit", {})
                page.click(s["selector"], timeout=15000)
                log.append("[playwright] 已点击发布，等待结果…")

                # 等待 URL 变化或成功标识
                success_contains = self.cfg.get("success_url_contains", "")
                try:
                    page.wait_for_url(f"**/{success_contains}**" if success_contains else "**", timeout=20000)
                except Exception:
                    pass
                time.sleep(2)
                url = page.url
                page.screenshot(path=shot)
                browser.close()

                if success_contains and success_contains not in url:
                    log.append(f"[playwright] 发布后 URL 未命中成功特征（{url}），截图 {shot}")
                    return PublishResult(
                        status="failed", error=f"发布后未跳转到文章页（当前 {url}），请检查提交是否成功。",
                        log="\n".join(log),
                    )
                log.append(f"[playwright] 发布成功，URL={url}，截图 {shot}")
                return PublishResult(status="published", url=url, raw={"final_url": url}, log="\n".join(log))
        except Exception as e:  # noqa: BLE001
            try:
                page.screenshot(path=shot)  # type: ignore
            except Exception:
                pass
            log.append(f"[playwright] 异常：{e}，截图 {shot}")
            return PublishResult(status="failed", error=f"发布过程异常：{e}", log="\n".join(log))

    def _catalog_url(self) -> str:
        for item in PLATFORM_CATALOG:
            if item["platform"] == self.platform:
                return item.get("publish_url", "")
        return ""


class ApiAdapterPlaceholder(PlatformAdapter):
    """官方 Open API 适配器占位（微信/小红书/百家号/头条）。当前无资质，待实现。"""
    adapter_type = "api"

    def __init__(self, platform: str):
        self.platform = platform

    def publish(self, title, content, cover, cred_json, log):
        log.append(f"[api] {self.platform} 官方 Open API 适配器尚未实现")
        return PublishResult(
            status="failed",
            error=f"{self.platform} 官方 Open API 发布需要平台认证资质（appid/appsecret 等），当前未配置，暂缓实现。",
            log="\n".join(log),
        )


# ============================================================
#  交互式 Cookie 捕获（"浏览器登录获取 Cookie"）
#  设计：弹出一个真实（有头）浏览器，用户在弹窗里像平时一样扫码/输密码登录；
#  登录成功后自动把当前上下文的 cookie 抓回，写入 PlatformCredential。
#  - 绝不自动破解 2FA：所有登录动作由用户在弹出的浏览器内亲自完成。
#  - 自动检测：轮询登录态 cookie，出现即自动捕获并关闭；
#    也支持用户点"已完成登录，捕获 Cookie"手动触发。
#  - 未安装 playwright 时优雅降级（status=failed + 安装提示），不崩。
#  线程模型：capture 在独立守护线程跑 Playwright 事件循环，主线程通过 Event 信号交互。
# ============================================================
def _filter_storage_state(state: Dict[str, Any], platform: str) -> Dict[str, Any]:
    """按平台域名过滤 storage_state（cookies + localStorage origins），去掉无关站点数据。"""
    domains = PLATFORM_DOMAINS.get(platform, [])
    cookies = state.get("cookies", []) or []
    origins = state.get("origins", []) or []
    if domains:
        cookies = [c for c in cookies if any(d in (c.get("domain") or "") for d in domains)]
        origins = [o for o in origins if any(d in (o.get("origin") or "") for d in domains)]
    return {"cookies": cookies, "origins": origins}


def _normalize_pasted_cookies(raw: Any) -> List[Dict[str, Any]]:
    """把 Cookie-Editor / Netscape 风格的导出归一化为 Playwright cookie 列表。

    支持字段：name, value, domain, path, expirationDate/expires, httpOnly, secure, sameSite。
    sameSite 取值（no_restriction/unspecified/lax/strict）映射为 Playwright 要求的
    Lax/Strict/None（大小写敏感，错值会被 Playwright 拒绝）。
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for c in raw:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        value = c.get("value")
        if name is None or value is None:
            continue
        cookie: Dict[str, Any] = {"name": str(name), "value": str(value)}
        domain = c.get("domain")
        if domain:
            cookie["domain"] = domain
        cookie["path"] = c.get("path") or "/"
        for exp_key in ("expirationDate", "expires"):
            if exp_key in c and c.get(exp_key) not in (None, "", 0):
                try:
                    cookie["expires"] = int(float(c[exp_key]))
                    break
                except (TypeError, ValueError):
                    pass
        cookie["httpOnly"] = bool(c.get("httpOnly", False))
        cookie["secure"] = bool(c.get("secure", False))
        ss = str(c.get("sameSite", "") or "").lower()
        if ss in ("lax", "strict", "none"):
            cookie["sameSite"] = ss.capitalize()
        out.append(cookie)
    return out


class PlaywrightCookieCapture:
    def __init__(self, platform: str, headless: bool = False, auto_detect: bool = True,
                 auto_timeout: int = 180):
        self.platform = platform
        self.headless = headless
        self.auto_detect = auto_detect
        self.auto_timeout = auto_timeout
        self.session_id = uuid.uuid4().hex
        self.status = "starting"          # starting | waiting_login | captured | failed | cancelled
        self.error = ""
        self.cookies: List[Dict[str, Any]] = []
        # 完整登录态（Playwright storage_state：cookies + localStorage），比纯 cookie 更完整可靠
        self.storage_state: Dict[str, Any] = {"cookies": [], "origins": []}
        self.intent: Dict[str, Any] = {}   # {industry_id, platform, credential_id?}
        self._login_event = threading.Event()    # 主线程 -> 捕获线程：请捕获 cookie
        self._captured_event = threading.Event()  # 捕获线程 -> 主线程：cookie 已就绪
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._browser = None
        self._context = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _is_logged_in(self, page) -> bool:
        """多信号判定：命中任一登录态 cookie，或 URL 已离开登录页并进入平台域名。"""
        cfg = LOGIN_CHECK.get(self.platform, {})
        cookie_names = set(cfg.get("cookies", []))
        not_url = set(cfg.get("not_url", []))
        url_has = cfg.get("url_has", [])
        try:
            names = {c.get("name") for c in self._context.cookies()}
            if cookie_names & names:
                return True
        except Exception:
            pass
        try:
            url = page.url or ""
            if url and not any(s in url for s in not_url):
                if not url_has or any(h in url for h in url_has):
                    return True
        except Exception:
            pass
        return False

    def _do_capture(self) -> None:
        try:
            raw = self._context.storage_state() if self._context else {"cookies": [], "origins": []}
            self.storage_state = _filter_storage_state(raw, self.platform)
            self.cookies = self.storage_state.get("cookies", [])
            self.status = "captured"
        except Exception as e:  # noqa: BLE001
            self.status = "failed"
            self.error = f"捕获登录态失败：{e}"
        finally:
            self._captured_event.set()

    def _run(self) -> None:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as e:  # noqa: BLE001
            self.status = "failed"
            self.error = ("服务端未安装 playwright，且未检测到本机 Edge/Chrome。可二选一：\n"
                          "① 安装本机 Microsoft Edge 或 Google Chrome（推荐，自动复用）；\n"
                          "② pip install playwright && playwright install chromium")
            self._captured_event.set()
            return
        try:
            with sync_playwright() as p:
                launch_kwargs = _browser_launch_kwargs(self.headless)
                self._browser = p.chromium.launch(**launch_kwargs)
                self._context = self._browser.new_context()
                page = self._context.new_page()
                login_url = LOGIN_URLS.get(self.platform, "https://www.zhihu.com/login")
                page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                self.status = "waiting_login"
                log("cookie-capture", f"[{self.platform}] 已打开登录页 {login_url}，等待用户登录")

                # 自动检测：登录态信号出现即自动捕获
                if self.auto_detect:
                    deadline = time.time() + self.auto_timeout
                    while time.time() < deadline:
                        if self._stop_event.is_set():
                            self.status = "cancelled"
                            self._captured_event.set()
                            return
                        if self._login_event.is_set():
                            break
                        if self._is_logged_in(page):
                            log("cookie-capture", f"[{self.platform}] 检测到已登录，自动捕获登录态")
                            self._do_capture()
                            return
                        time.sleep(2)

                # 等待用户手动点"完成登录，捕获 Cookie"或取消
                while not self._stop_event.is_set() and not self._login_event.is_set():
                    time.sleep(0.5)
                if self._stop_event.is_set():
                    self.status = "cancelled"
                    self._captured_event.set()
                    return
                self._do_capture()
        except Exception as e:  # noqa: BLE001
            self.status = "failed"
            self.error = f"捕获过程异常：{e}"
            self._captured_event.set()
        finally:
            try:
                if self._browser:
                    self._browser.close()
            except Exception:
                pass

    def finish(self, timeout: int = 30):
        """主线程调用：请求捕获并等待结果。返回 (status, storage_state, error)。"""
        self._login_event.set()
        self._captured_event.wait(timeout=timeout)
        return self.status, self.storage_state, self.error

    def cancel(self) -> None:
        self._stop_event.set()


def log(tag: str, msg: str) -> None:
    try:
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "capture"),
                    exist_ok=True)
        fp = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "capture", f"{tag}.log")
        with open(fp, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ============================================================
#  发布器注册表
# ============================================================
class PlatformPublisher:
    def __init__(self):
        self._cache: Dict[str, PlatformAdapter] = {}

    def _build(self, platform: str, adapter_type: str) -> PlatformAdapter:
        at = (adapter_type or "playwright").lower()
        if at == "mock":
            return MockAdapter(platform)
        if at == "api":
            return ApiAdapterPlaceholder(platform)
        # 默认 playwright
        return PlaywrightAdapter(platform)

    def get_adapter(self, platform: str, adapter_type: str) -> PlatformAdapter:
        key = f"{platform}:{adapter_type}"
        if key not in self._cache:
            self._cache[key] = self._build(platform, adapter_type)
        return self._cache[key]

    def publish(
        self,
        platform: str,
        adapter_type: str,
        title: str,
        content: str,
        cover: Optional[str] = None,
        cred_json: str = "",
    ) -> PublishResult:
        log: List[str] = []
        adapter = self._build(platform, adapter_type)
        result = adapter.publish(title, content, cover, cred_json, log)
        if not result.log:
            result.log = "\n".join(log)
        return result

    def list_platforms(self) -> List[Dict[str, Any]]:
        return [dict(p) for p in PLATFORM_CATALOG]


# 全局单例
publisher = PlatformPublisher()
