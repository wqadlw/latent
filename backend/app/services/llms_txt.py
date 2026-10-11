"""
AI 抓取入口文件生成器：``llms.txt`` / ``sitemap.xml`` / ``robots.txt``

为什么需要它
------------
我们**已经在产出官网 MDX 内容**（``production_task.output_format = 'mdx'``），
但这些内容从来没有以「AI 友好的索引」形式暴露出去。AI 爬虫即使来了，
也只能自己一页页猜着爬。

``llms.txt`` 是 llmstxt.org 提出的约定：在站点根目录放一份 Markdown 索引，
告诉大模型「本站有哪些值得读的内容、分别在哪里」。它不替代 sitemap，
而是给模型一个**低成本、高信噪比**的入口，显著提高内容被正确引用（而非被忽略）的概率。

三个文件的分工
--------------
- ``llms.txt``     —— 给生成式引擎看的内容索引（人也能读）
- ``sitemap.xml``  —— 给传统搜索引擎 + 支持 sitemap 的 AI 爬虫看的全量 URL 清单
- ``robots.txt``   —— 显式放行主流 AI 爬虫并声明 sitemap 位置（GEO 场景下「欢迎抓取」是默认立场）

数据来源（三路合并，按 URL 去重）
--------------------------------
1. ``ProductionTask``  —— 官网/自建站的 MDX 产出（自有阵地，GEO 权重最高）
2. ``PublishJob``      —— 已发布成功、拿到结果 URL 的平台文章
3. ``ContentAsset``    —— 内容资产库里标记为已发布且有 URL 的条目
"""
from __future__ import annotations

from typing import Dict, List, Optional
from xml.sax.saxutils import escape

from ..brand_config import BRAND_NAME, OFFICIAL_SITE_URL
from ..services.crawler_classifier import ai_bot_names, search_bot_names


def _normalize_site(url: str) -> str:
    """站点根地址归一化：补协议、去尾部斜杠。"""
    u = (url or "").strip()
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u.rstrip("/")


def _join(site: str, path: str) -> str:
    """拼接站点根与路径，避免出现双斜杠。"""
    if not path:
        return site
    if path.startswith(("http://", "https://")):
        return path
    return f"{site}/{path.lstrip('/')}"


def _mdx_url(task, site: str) -> str:
    """由生产任务推导官网 URL。

    优先用任务上已记录的 ``publish_url``；否则由 ``mdx_filename`` 去掉扩展名后拼到站点根。
    Astro 的 content collection 通常按文件名生成 slug，这是最贴近实际的推导方式。
    """
    if (task.publish_url or "").strip():
        return task.publish_url.strip()
    filename = (task.mdx_filename or "").strip()
    if not filename:
        return ""
    slug = filename.rsplit(".", 1)[0]
    return _join(site, slug)


def collect_entries(db, site_url: Optional[str] = None) -> List[Dict[str, str]]:
    """汇总所有可被 AI 抓取的内容条目。

    返回 ``[{title, url, section, description, lastmod, source}]``，按 URL 去重（先到先得，
    自有站点条目优先，因为它们排在最前面被收集）。
    """
    from ..models import ContentAsset, ProductionTask, PublishJob

    site = _normalize_site(site_url or OFFICIAL_SITE_URL)
    entries: List[Dict[str, str]] = []
    seen = set()

    def _push(title: str, url: str, section: str, description: str = "", lastmod: str = "", source: str = "") -> None:
        title = (title or "").strip()
        url = (url or "").strip()
        if not url or url in seen:
            return
        seen.add(url)
        entries.append({
            "title": title or url,
            "url": url,
            "section": section or "内容",
            "description": (description or "").strip(),
            "lastmod": (lastmod or "")[:10],
            "source": source,
        })

    # 1) 官网/自建站 MDX 产出（自有阵地，放在最前面）
    tasks = db.query(ProductionTask).filter(
        ProductionTask.is_deleted == 0,
        ProductionTask.output_format == "mdx",
        ProductionTask.mdx_filename != "",
    ).order_by(ProductionTask.update_time.desc()).all()
    for t in tasks:
        url = _mdx_url(t, site)
        _push(
            title=t.final_title or t.title,
            url=url,
            section="官网 · 行业资讯",
            lastmod=t.update_time.strftime("%Y-%m-%d") if t.update_time else "",
            source="production_task",
        )

    # 2) 已发布成功的平台文章
    jobs = db.query(PublishJob).filter(
        PublishJob.is_deleted == 0,
        PublishJob.status == "published",
        PublishJob.result_url != "",
    ).order_by(PublishJob.update_time.desc()).all()
    for j in jobs:
        _push(
            title=j.title,
            url=j.result_url,
            section=f"外部平台 · {j.platform or '未知平台'}",
            lastmod=j.update_time.strftime("%Y-%m-%d") if j.update_time else "",
            source="publish_job",
        )

    # 3) 内容资产库
    assets = db.query(ContentAsset).filter(
        ContentAsset.is_deleted == 0,
        ContentAsset.publish_status == "published",
        ContentAsset.publish_url != "",
    ).order_by(ContentAsset.update_time.desc()).all()
    for a in assets:
        _push(
            title=a.title,
            url=a.publish_url,
            section="内容资产",
            lastmod=a.publish_time.strftime("%Y-%m-%d") if a.publish_time else "",
            source="content_asset",
        )

    return entries


def build_llms_txt(db, site_url: Optional[str] = None, title: Optional[str] = None,
                   description: Optional[str] = None, max_per_section: int = 200) -> str:
    """生成 ``llms.txt`` 内容（Markdown）。"""
    site = _normalize_site(site_url or OFFICIAL_SITE_URL)
    entries = collect_entries(db, site)

    lines: List[str] = []
    lines.append(f"# {title or BRAND_NAME}")
    lines.append("")
    lines.append(
        f"> {description or (BRAND_NAME + ' 的行业内容索引，覆盖产品选型、应用案例与行业资讯，供生成式引擎检索与引用。')}"
    )
    lines.append("")
    lines.append(
        "本文件用于向大语言模型说明本站内容结构。"
        "如需完整 URL 清单请访问 /sitemap.xml。"
    )
    lines.append("")

    if not entries:
        lines.append("## 内容")
        lines.append("")
        lines.append("- 暂无已发布内容。")
        lines.append("")
        return "\n".join(lines)

    # 按 section 分组，保持首次出现顺序
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for e in entries:
        grouped.setdefault(e["section"], []).append(e)

    for section, items in grouped.items():
        lines.append(f"## {section}")
        lines.append("")
        for e in items[:max_per_section]:
            desc = f": {e['description']}" if e["description"] else ""
            lines.append(f"- [{e['title']}]({e['url']}){desc}")
        lines.append("")

    lines.append("## 关于本站")
    lines.append("")
    lines.append(f"- 官网：{site}")
    lines.append("- 内容主题：真空设备选型、行业应用案例、技术科普与行业资讯")
    lines.append("")
    return "\n".join(lines)


def build_sitemap_xml(db, site_url: Optional[str] = None) -> str:
    """生成 ``sitemap.xml``（标准 sitemaps.org 协议）。"""
    site = _normalize_site(site_url or OFFICIAL_SITE_URL)
    entries = collect_entries(db, site)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    # 站点根
    parts.append("  <url>")
    parts.append(f"    <loc>{escape(site)}</loc>")
    parts.append("    <changefreq>daily</changefreq>")
    parts.append("    <priority>1.0</priority>")
    parts.append("  </url>")

    for e in entries:
        parts.append("  <url>")
        parts.append(f"    <loc>{escape(e['url'])}</loc>")
        if e["lastmod"]:
            parts.append(f"    <lastmod>{escape(e['lastmod'])}</lastmod>")
        parts.append("    <changefreq>weekly</changefreq>")
        parts.append("    <priority>0.8</priority>")
        parts.append("  </url>")

    parts.append("</urlset>")
    parts.append("")
    return "\n".join(parts)


def build_robots_txt(site_url: Optional[str] = None, allow_ai: bool = True) -> str:
    """生成 ``robots.txt``。

    GEO 场景下的默认立场是**欢迎 AI 抓取**——内容不被抓就谈不上被引用。
    ``allow_ai=False`` 时改为显式禁止（适用于内容不希望被用于模型训练的场景）。
    """
    site = _normalize_site(site_url or OFFICIAL_SITE_URL)

    lines: List[str] = ["User-agent: *", "Allow: /", ""]

    if allow_ai:
        lines.append("# 生成式引擎抓取器：GEO 场景下显式放行")
        for name in ai_bot_names():
            lines.append(f"User-agent: {name}")
        lines.append("Allow: /")
    else:
        lines.append("# 生成式引擎抓取器：显式禁止")
        for name in ai_bot_names():
            lines.append(f"User-agent: {name}")
        lines.append("Disallow: /")

    lines.append("")
    lines.append("# 传统搜索引擎抓取器：始终放行")
    for name in search_bot_names():
        lines.append(f"User-agent: {name}")
    lines.append("Allow: /")

    lines.append("")
    if site:
        lines.append(f"Sitemap: {site}/sitemap.xml")
        lines.append(f"# LLM 内容索引: {site}/llms.txt")
    lines.append("")
    return "\n".join(lines)


def build_all(db, site_url: Optional[str] = None) -> Dict[str, str]:
    """一次性生成三个文件，返回 ``{"llms_txt": ..., "sitemap_xml": ..., "robots_txt": ...}``。"""
    site = _normalize_site(site_url or OFFICIAL_SITE_URL)
    return {
        "llms_txt": build_llms_txt(db, site),
        "sitemap_xml": build_sitemap_xml(db, site),
        "robots_txt": build_robots_txt(site),
    }
