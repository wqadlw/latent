"""
通用工具函数
"""
import hashlib
import json
import re
from datetime import date, datetime


def to_dict(obj) -> dict:
    """SQLAlchemy 对象转字典"""
    if obj is None:
        return {}
    result = {}
    for c in obj.__table__.columns:
        val = getattr(obj, c.name)
        if isinstance(val, datetime):
            val = val.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(val, date):
            val = val.strftime("%Y-%m-%d")
        result[c.name] = val
    return result


def parse_datetime(value):
    """把字符串/日期/日期时间统一转成 datetime 对象，无法解析时返回 None。

    支持：
      - datetime / date 对象（date 会补零为 00:00:00）
      - 'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DD HH:MM' / 'YYYY-MM-DD' / ISO 格式
      - 时间戳（int/float，秒或毫秒）
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)):
        # 兼容毫秒时间戳
        if value > 1e12:
            value = value / 1000
        try:
            return datetime.fromtimestamp(value)
        except (OSError, ValueError, OverflowError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # 常见格式依次尝试
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        # 最后尝试 fromisoformat（Python 3.7+）
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def parse_date(value):
    """把字符串/日期/日期时间统一转成 date 对象，无法解析时返回 None。"""
    dt = parse_datetime(value)
    if dt is None:
        return None
    return dt.date()


def parse_json(s, default=None):
    if default is None:
        default = []
    if not s:
        return default
    if isinstance(s, (list, dict)):
        return s
    try:
        return json.loads(s)
    except Exception:
        return default


def parse_ids(s) -> list:
    if not s or s == "all":
        return []
    return [int(x) for x in str(s).split(",") if x.strip().isdigit()]


def encrypt_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()


def verify_password(pwd: str, hashed: str) -> bool:
    return encrypt_password(pwd) == hashed


def safe_format(template: str, context: dict) -> str:
    """安全的字符串格式化，缺失的占位符保留原样。

    与旧版 ``str.format_map`` 相比，改用正则逐占位符替换，避免两类崩溃：
    1. 模板中出现字面花括号（如示例 JSON、代码块、``{要点}``）时，
       ``format_map`` 会抛 ``ValueError: unexpected '}'``；
    2. 格式说明符写法不规范时抛 ``KeyError``。
    现在只对合法的 ``{key}`` 占位符做替换，其余内容（含字面花括号）原样保留，
    缺失的占位符保留为 ``{key}``，与 ``unresolved_variables`` 语义一致。
    """
    if not template:
        return ""
    pattern = r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})"

    def _repl(m):
        key = m.group(1)
        val = context.get(key, "{" + key + "}")
        return "" if val is None else str(val)

    return re.sub(pattern, _repl, template)
