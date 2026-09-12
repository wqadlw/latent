"""
品牌配置中心（Single Source of Truth）
================================================

目标：让「开源通用版」与「客户定制版」**共用同一份代码** ——
品牌名、产品线名、官网地址、地域等易变信息不再散落硬编码在业务代码里，
而是集中到本模块统一读取。

配置来源（优先级由高到低）：
  1. 环境变量：BRAND_NAME / BRAND_FULL_NAME / BRAND_PRODUCT /
     BRAND_OFFICIAL_SITE_URL / BRAND_REGION / BRAND_REGION_CITY / BRAND_ALIASES
  2. JSON 配置文件 ``brand.config.json``（放在项目根目录或 backend/ 目录均可）
  3. 内置默认值（开源示例值，见下方 DEFAULTS）

客户部署时只需在项目根放一份 ``brand.config.json``（该文件已被 .gitignore
排除，不会进仓库），**无需改动任何源码**；开源用户不配置则直接使用示例默认值。

用法::

    from ..brand_config import BRAND_NAME, OFFICIAL_SITE_URL, REGION

    text = f"品牌（{BRAND_NAME}）仅可自然偶提 ≤ 2 次"

注意：本模块的值在 **模块导入时** 求值一次，因此 ``brand.config.json`` /
环境变量必须在进程启动前就绪。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 开源默认值（示例品牌，通用、无真实客户信息）
DEFAULTS: Dict[str, Any] = {
    "brand_name": "示例品牌",
    "brand_full_name": "示例品牌科技有限公司",
    "brand_product": "示例产品",
    "official_site_url": "https://www.example.com",
    "region": "华东",
    "region_city": "上海",
    "brand_aliases": [],
}

# 字段 → 环境变量名
_ENV_MAP = {
    "brand_name": "BRAND_NAME",
    "brand_full_name": "BRAND_FULL_NAME",
    "brand_product": "BRAND_PRODUCT",
    "official_site_url": "BRAND_OFFICIAL_SITE_URL",
    "region": "BRAND_REGION",
    "region_city": "BRAND_REGION_CITY",
    "brand_aliases": "BRAND_ALIASES",
}

# 配置文件候选路径（项目根 / backend/）
_FILE_NAME = "brand.config.json"


def _candidate_files() -> List[Path]:
    """返回 brand.config.json 的候选路径，按优先级排列。

    backend/app/brand_config.py → parents[1] = backend/，parents[2] = 项目根。
    """
    here = Path(__file__).resolve()
    out: List[Path] = []
    for idx in (2, 1):  # 项目根优先，其次 backend/
        try:
            out.append(here.parents[idx] / _FILE_NAME)
        except IndexError:  # pragma: no cover - 极端目录结构兜底
            continue
    return out


def _load_file() -> Tuple[Dict[str, Any], Optional[str]]:
    """读取第一个存在的 brand.config.json；返回 (数据, 文件路径)。"""
    for f in _candidate_files():
        try:
            if f.is_file():
                with f.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return data, str(f)
        except Exception:
            # 配置损坏不应导致进程起不来，静默回退到默认值
            continue
    return {}, None


def _split_aliases(value: Any) -> List[str]:
    """把别名配置统一成去重后的字符串列表。"""
    if isinstance(value, str):
        items = re.split(r"[，,;；/、|]", value)
    elif isinstance(value, (list, tuple)):
        items = [str(x) for x in value]
    else:
        items = []
    seen = set()
    out: List[str] = []
    for it in items:
        it = (it or "").strip()
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _load() -> Tuple[Dict[str, Any], Optional[str]]:
    cfg: Dict[str, Any] = dict(DEFAULTS)

    file_data, used_file = _load_file()
    for key in DEFAULTS:
        val = file_data.get(key)
        if val not in (None, ""):
            cfg[key] = val

    for key, env in _ENV_MAP.items():
        val = os.environ.get(env)
        if val:
            cfg[key] = val

    # 别名：未配置时回退为「品牌名 + 产品线名」，与历史硬编码行为保持一致
    aliases = _split_aliases(cfg.get("brand_aliases"))
    if not aliases:
        aliases = _split_aliases([cfg["brand_name"], cfg["brand_product"]])
    cfg["brand_aliases"] = aliases

    return cfg, used_file


_CFG, CONFIG_FILE = _load()

# —— 对外常量（各模块直接 import 使用）——
BRAND_NAME: str = str(_CFG["brand_name"])
BRAND_FULL_NAME: str = str(_CFG["brand_full_name"])
BRAND_PRODUCT: str = str(_CFG["brand_product"])
OFFICIAL_SITE_URL: str = str(_CFG["official_site_url"])
REGION: str = str(_CFG["region"])
REGION_CITY: str = str(_CFG["region_city"])
BRAND_ALIASES: List[str] = list(_CFG["brand_aliases"])


def as_dict() -> Dict[str, Any]:
    """导出当前生效的品牌配置（供调试 / 接口展示）。"""
    return {
        "brand_name": BRAND_NAME,
        "brand_full_name": BRAND_FULL_NAME,
        "brand_product": BRAND_PRODUCT,
        "official_site_url": OFFICIAL_SITE_URL,
        "region": REGION,
        "region_city": REGION_CITY,
        "brand_aliases": list(BRAND_ALIASES),
        "config_file": CONFIG_FILE,
    }
