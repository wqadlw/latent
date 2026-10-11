"""站点 AI 抓取入口（公开路由，**不挂登录守卫**）

暴露三个约定文件，供 AI 爬虫 / 搜索引擎直接抓取：

- ``GET /llms.txt``     —— 生成式引擎内容索引（llmstxt.org 约定）
- ``GET /sitemap.xml``  —— 标准站点地图
- ``GET /robots.txt``   —— 显式放行主流 AI 爬虫 + 声明 sitemap 位置

⚠️ 这三个端点**必须是公开的**——爬虫不会带 Authorization 头。
因此本模块**不能**加入 ``main.py`` 的 ``_PROTECTED_ROUTERS``，
否则整个 GEO 抓取入口对外不可达，功能形同虚设。

站点地址解析优先级：``?site=`` 查询参数 > 品牌配置 ``official_site_url``。
查询参数是为了让同一套后端能同时服务「主站 + 多个子站」的索引生成。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import llms_txt

router = APIRouter(tags=["站点·AI 抓取入口"])

_PLAIN = "text/plain; charset=utf-8"
_XML = "application/xml; charset=utf-8"

# 缓存 10 分钟：索引内容变化不频繁，避免爬虫高频抓取时反复查库
_CACHE_HEADERS = {"Cache-Control": "public, max-age=600"}


@router.get("/llms.txt", response_class=PlainTextResponse)
def get_llms_txt(site: Optional[str] = Query(None, description="站点根地址，留空用品牌配置"), db: Session = Depends(get_db)):
    """生成式引擎内容索引。"""
    body = llms_txt.build_llms_txt(db, site)
    return Response(content=body, media_type=_PLAIN, headers=_CACHE_HEADERS)


@router.get("/sitemap.xml")
def get_sitemap_xml(site: Optional[str] = Query(None, description="站点根地址，留空用品牌配置"), db: Session = Depends(get_db)):
    """标准站点地图。"""
    body = llms_txt.build_sitemap_xml(db, site)
    return Response(content=body, media_type=_XML, headers=_CACHE_HEADERS)


@router.get("/robots.txt", response_class=PlainTextResponse)
def get_robots_txt(site: Optional[str] = Query(None, description="站点根地址，留空用品牌配置"),
                   allow_ai: bool = Query(True, description="是否放行 AI 爬虫"), db: Session = Depends(get_db)):
    """robots.txt（默认立场：欢迎 AI 抓取）。"""
    body = llms_txt.build_robots_txt(site, allow_ai=allow_ai)
    return Response(content=body, media_type=_PLAIN, headers=_CACHE_HEADERS)
