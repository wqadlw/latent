"""闭环看板演示数据种子（仅用于本地验收，可重复执行）。"""
import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    CrawlerHit,
    GeoVisibilityRun,
    GeoVisibilitySource,
    ProductionTask,
)

INDUSTRY_ID = 1
BASE = "https://demo.zhaozhenkong.com"
# 发布 URL 的路径必须与站点访问日志里的路径一致 —— 归因是按「归一化路径」
# 精确匹配的，多一段少一段都会让收录统计静默归零。
PREFIX = f"{BASE}/case"

# (路径尾段, 标题, AI 抓取次数, 搜索引擎抓取次数, 引用名次列表)
PLAN = [
    ("vacuum-pump-selection", "真空泵选型避坑指南：极限真空度与抽速怎么权衡", 7, 3, [1, 2]),
    ("roots-pump-maintenance", "罗茨泵日常维护与常见故障排查", 4, 2, [3]),
    ("vacuum-system-energy", "真空系统节能改造的 5 个实测数据", 5, 1, [5]),
    ("oil-free-vs-oil", "无油真空泵与有油泵的成本对比", 2, 4, []),
    ("vacuum-gauge-calib", "真空计校准周期与送检流程", 0, 3, []),
    ("chamber-leak-detect", "真空腔体检漏的 6 种方法", 0, 0, []),
]

BOTS = [
    ("ai_bot", "GPTBot"), ("ai_bot", "Bytespider"), ("ai_bot", "PerplexityBot"),
    ("ai_bot", "ClaudeBot"), ("ai_bot", "DeepSeek"), ("ai_bot", "Google-Extended"),
]

KEYWORDS = ["真空泵怎么选型", "罗茨泵维护要点", "真空系统怎么节能"]


def main() -> None:
    with SessionLocal() as db:
        # 清掉上一次的演示数据，保证可重复执行
        paths = [f"/case/{slug}" for slug, *_ in PLAN]
        db.query(CrawlerHit).filter(CrawlerHit.path.in_(paths)).delete(
            synchronize_session=False)
        old = db.query(ProductionTask).filter(
            ProductionTask.publish_url.like(f"{PREFIX}%")).all()
        for t in old:
            db.query(ProductionTask).filter(ProductionTask.id == t.id).delete()
        runs = db.query(GeoVisibilityRun).filter(
            GeoVisibilityRun.keyword.in_(KEYWORDS)).all()
        for r in runs:
            db.query(GeoVisibilitySource).filter(
                GeoVisibilitySource.run_id == r.id).delete()
            db.query(GeoVisibilityRun).filter(GeoVisibilityRun.id == r.id).delete()
        db.commit()

        # 已发布内容
        for i, (slug, title, _ai, _se, _cites) in enumerate(PLAN):
            db.add(ProductionTask(
                industry_id=INDUSTRY_ID,
                title=title, final_title=title,
                publish_url=f"{PREFIX}/{slug}",
                status="done", platform_snapshot="搜狐号" if i % 2 == 0 else "知乎",
                update_time=datetime.now() - timedelta(days=20 - i * 3),
            ))
        db.commit()

        # 抓取记录：按计划造出 ai_bot / search_bot 的差异
        now = datetime.now()
        for i, (slug, _t, ai_n, se_n, _c) in enumerate(PLAN):
            path = f"/case/{slug}"
            for k in range(ai_n):
                bot_class, bot_name = BOTS[(i + k) % len(BOTS)]
                db.add(CrawlerHit(
                    hit_time=now - timedelta(days=15 - i, hours=k),
                    path=path, matched_url=path,
                    bot_class=bot_class, bot_name=bot_name,
                    method="GET", status_code=200, ip_hash=f"demo{i}{k}"[:16].ljust(16, "0"),
                ))
            for k in range(se_n):
                db.add(CrawlerHit(
                    hit_time=now - timedelta(days=14 - i, hours=k + 5),
                    path=path, matched_url=path,
                    bot_class="search_bot", bot_name="Baiduspider",
                    method="GET", status_code=200, ip_hash=f"srch{i}{k}"[:16].ljust(16, "0"),
                ))
        db.commit()

        # AI 引用记录：让前 3 篇各自在某个问题下被引用
        for i, (slug, title, _ai, _se, cites) in enumerate(PLAN):
            if not cites:
                continue
            run = GeoVisibilityRun(
                industry_id=INDUSTRY_ID,
                uuid=f"loopdemo{i}"[:40],
                keyword=KEYWORDS[i % len(KEYWORDS)],
                status="completed", provider_key="mock", model_id="mock-visibility-v1",
                create_time=now - timedelta(days=10 - i),
            )
            db.add(run)
            db.flush()
            for rank in cites:
                db.add(GeoVisibilitySource(
                    run_id=run.id, source_type="bare_url",
                    title=title, url=f"{PREFIX}/{slug}",
                    domain="demo.zhaozhenkong.com", site_name="demo.zhaozhenkong.com",
                    rank=rank, rank_score=round(1 / rank, 4),
                    authority_level="low", is_owned=1,
                    snippet=f"围绕「{KEYWORDS[i % len(KEYWORDS)]}」的实测数据与选型结论",
                ))
            # 再补一个第三方信源，让信源偏好榜与对标选题有内容
            db.add(GeoVisibilitySource(
                run_id=run.id, source_type="domain_mention",
                title="行业选型白皮书", url="https://www.zhihu.com/question/10086",
                domain="zhihu.com", site_name="zhihu.com",
                rank=4, rank_score=0.22, authority_level="medium", is_owned=0,
            ))
        db.commit()

    print("演示数据已就绪")
    for _slug, title, ai_n, se_n, cites in PLAN:
        print(f"  {title[:24]:26} AI抓取={ai_n} 搜索引擎={se_n} 引用名次={cites or '无'}")


if __name__ == "__main__":
    main()
