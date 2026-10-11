"""
访问日志解析器（Nginx / Apache Combined Log Format）

用途
----
本系统部署在**自有服务器**上，但真正被 AI 抓取的是**外部站点**（Astro 官网、
各内容平台）。因此仅靠本机中间件拿不到「文章被谁爬了」的全貌。

本模块提供一条与系统既有哲学一致的通道：**用户把站点访问日志粘贴/上传进来，
系统本地解析、分类、归因**——不需要任何外部集成，也不需要站点改造。

支持格式（自动嗅探，逐行容错）
------------------------------
1. Nginx 默认::

       127.0.0.1 - - [10/Oct/2026:20:57:06 +0800] "GET /a/b HTTP/1.1" 200 1234

2. Combined（Apache / Nginx 加 ``$http_referer $http_user_agent``）::

       127.0.0.1 - - [10/Oct/2026:20:57:06 +0800] "GET /a/b HTTP/1.1" 200 1234 "-" "Mozilla/5.0 (compatible; GPTBot/1.0)"

3. 简化行（只有 UA 的导出格式，如部分 CDN 后台）::

       2026-10-10T20:57:06Z GET /a/b GPTBot

解析策略是「逐行尝试多个正则，命中即用，全不中则跳过并计数」——
**绝不因为个别脏行让整次导入失败**。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ---- Combined / Nginx 组合格式 ----
# ip ident authuser [time] "METHOD PATH PROTO" status bytes "referer" "ua"
_COMBINED_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<method>[A-Z]+)\s+(?P<path>\S+?)(?:\s+(?P<proto>[^"]*))?"\s+'
    r'(?P<status>\d{3})\s+(?P<bytes>\S+)'
    r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<ua>[^"]*)")?'
)

# ---- Nginx 默认格式（无 referer/ua）----
_NGINX_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<method>[A-Z]+)\s+(?P<path>\S+?)(?:\s+(?P<proto>[^"]*))?"\s+'
    r'(?P<status>\d{3})\s+(?P<bytes>\S+)'
)

# ---- 简化行：ISO 时间 + METHOD + PATH + UA 尾巴 ----
_SIMPLE_RE = re.compile(
    r'^(?P<time>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})?)\s+'
    r'(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+(?P<ua>.+)$'
)

# Apache/Nginx 时间：10/Oct/2026:20:57:06 +0800
_APACHE_TIME_FMT = "%d/%b/%Y:%H:%M:%S %z"
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_apache_time(value: str) -> Optional[datetime]:
    """解析 ``10/Oct/2026:20:57:06 +0800``；失败返回 None。"""
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw, _APACHE_TIME_FMT)
        # 统一转成 naive 本地时间，避免与 SQLite 存储的 naive datetime 比较时炸掉
        return dt.replace(tzinfo=None)
    except ValueError:
        pass
    # 手工兜底：月份英文缩写不一定是标准三字母
    m = re.match(r"(\d{1,2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})", raw)
    if m:
        day, mon_name, year, hh, mm, ss = m.groups()
        mon = _MONTHS.get(mon_name.lower()[:3])
        if mon:
            try:
                return datetime(int(year), mon, int(day), int(hh), int(mm), int(ss))
            except ValueError:
                return None
    return None


def _parse_iso_time(value: str) -> Optional[datetime]:
    """解析 ISO 风格时间戳；失败返回 None。"""
    raw = (value or "").strip().rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:19] if len(raw) > 19 else raw, fmt)
        except ValueError:
            continue
    return None


def _split_path(raw: str) -> Tuple[str, str]:
    """把 ``/a/b?x=1`` 拆成 ``("/a/b", "x=1")``。"""
    path = raw or ""
    if "?" in path:
        path, query = path.split("?", 1)
        return path, query
    return path, ""


def parse_line(line: str) -> Optional[Dict[str, object]]:
    """解析单行访问日志；无法识别返回 None。

    返回 ``{ip, time, method, path, query, status, referer, user_agent}``。
    """
    raw = (line or "").strip()
    if not raw:
        return None

    for regex, time_kind in ((_COMBINED_RE, "apache"), (_NGINX_RE, "apache"), (_SIMPLE_RE, "iso")):
        m = regex.match(raw)
        if not m:
            continue
        gd = m.groupdict()
        path, query = _split_path(gd.get("path") or "")
        when = _parse_apache_time(gd.get("time") or "") if time_kind == "apache" else _parse_iso_time(gd.get("time") or "")
        try:
            status = int(gd.get("status") or 0)
        except (TypeError, ValueError):
            status = 0
        return {
            "ip": gd.get("ip") or "",
            "time": when,
            "method": (gd.get("method") or "GET").upper(),
            "path": path,
            "query": query,
            "status": status,
            "referer": gd.get("referer") or "",
            "user_agent": (gd.get("ua") or "").strip(),
        }
    return None


def parse_log_text(text: str, limit: int = 20000) -> Tuple[List[Dict[str, object]], int]:
    """批量解析日志文本。

    返回 ``(records, skipped)``。``limit`` 是单次导入的行数上限，
    防止用户误粘超大文件把内存打满。
    """
    records: List[Dict[str, object]] = []
    skipped = 0
    for idx, line in enumerate((text or "").splitlines()):
        if idx >= limit:
            break
        if not line.strip():
            continue
        parsed = parse_line(line)
        if parsed is None:
            skipped += 1
            continue
        records.append(parsed)
    return records, skipped
