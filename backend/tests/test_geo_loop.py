"""GEO 归因闭环（B4）测试：发布 → 收录 → 引用 → 排名 → 回流。

守护的核心不变量
----------------
1. **``search_bot`` 不算 AI 收录** —— 把百度/Google 收录混进「AI 收录率」会虚高指标，
   掩盖「AI 根本没来抓」这个真问题，而那才是 GEO 要修的洞；
2. **四阶段严格递进** —— 被引用必然先被抓取，进前 3 必然先被引用，
   任何一步的计数都不允许超过上一步；
3. **关联按归一化路径，不按完整 URL** —— 同一篇文章在不同平台的 URL 不同，
   用完整 URL 关联会得出「全都收录失败」的假结论；
4. **行业隔离** —— 别的行业的抓取与引用不能混进本行业的漏斗；
5. **归因表把问题排在前面** —— 运营打开这张表是为了找问题，不是看已成功的那些。
"""
import pytest
from app.services import geo_loop

INDUSTRY_ID = 1
OTHER_INDUSTRY_ID = 2


def _db():
    from app.database import SessionLocal

    return SessionLocal()


def _mk_task(db, url, title="测试文章", industry_id=INDUSTRY_ID, final_title=""):
    """建一条「已发布」的生产任务。"""
    from app.models import ProductionTask

    t = ProductionTask(
        industry_id=industry_id, title=title, final_title=final_title,
        publish_url=url, status="done", platform_snapshot="搜狐号",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _mk_hit(db, path, bot_class="ai_bot", bot_name="GPTBot", matched_url="",
            hours_ago=1):
    """建一条抓取记录。``hours_ago`` 用来控制先后顺序。"""
    from datetime import datetime, timedelta

    from app.models import CrawlerHit

    h = CrawlerHit(
        hit_time=datetime.now() - timedelta(hours=hours_ago),
        path=path, matched_url=matched_url, bot_class=bot_class, bot_name=bot_name,
        method="GET", status_code=200, ip_hash="a" * 16,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _mk_citation(db, url, rank=1, keyword="真空泵怎么选型", industry_id=INDUSTRY_ID,
                 title="行业指南", domain="zhihu.com", is_owned=1):
    """建一次「AI 引用」：Run + Source。"""
    from app.models import GeoVisibilityRun, GeoVisibilitySource

    run = GeoVisibilityRun(
        industry_id=industry_id, uuid=f"loop-{url}-{rank}-{keyword}"[:40],
        keyword=keyword, status="completed", provider_key="mock",
    )
    db.add(run)
    db.flush()
    s = GeoVisibilitySource(
        run_id=run.id, url=url, rank=rank, title=title, domain=domain,
        authority_level="medium", is_owned=is_owned,
    )
    db.add(s)
    db.commit()
    return run, s


@pytest.fixture(scope="module")
def seeded(client):
    """一个模块级的闭环数据集，覆盖四种状态各一。

    单独造数据而不是复用其它测试的残留 —— 闭环测试对「分母」极敏感，
    任何外部数据混进来都会让断言变成「取决于执行顺序」的脆弱断言。
    """
    from app.models import Industry

    with _db() as db:
        if not db.query(Industry).filter(Industry.id == OTHER_INDUSTRY_ID).first():
            db.add(Industry(id=OTHER_INDUSTRY_ID, name="闭环测试行业B"))
            db.commit()

    created = {}
    with _db() as db:
        # 1) 未被 AI 抓取
        created["not_crawled"] = _mk_task(
            db, "https://demo.loop/case/not-crawled", title="未收录文章",
        ).id
        # 2) 被抓取但未被引用
        created["crawled_only"] = _mk_task(
            db, "https://demo.loop/case/crawled-only", title="已收录未引用",
        ).id
        _mk_hit(db, "/case/crawled-only", matched_url="/case/crawled-only", hours_ago=5)
        # 3) 被引用但排名靠后（第 5）
        created["cited"] = _mk_task(
            db, "https://demo.loop/case/cited-late", title="被引用但靠后",
        ).id
        _mk_hit(db, "/case/cited-late", matched_url="/case/cited-late", hours_ago=4)
        _mk_citation(db, "https://demo.loop/case/cited-late", rank=5)
        # 4) 被引用且进前 3
        created["top3"] = _mk_task(
            db, "https://demo.loop/case/top3", title="进前3的文章",
        ).id
        _mk_hit(db, "/case/top3", matched_url="/case/top3", hours_ago=3)
        _mk_citation(db, "https://demo.loop/case/top3", rank=2)
        _mk_citation(db, "https://demo.loop/case/top3", rank=1, keyword="真空泵哪个牌子好")

        # 只被搜索引擎抓、AI 从没来的那篇（用于验证「不算 AI 收录」）
        created["search_only"] = _mk_task(
            db, "https://demo.loop/case/search-only", title="只被百度抓过",
        ).id
        _mk_hit(db, "/case/search-only", bot_class="search_bot",
                bot_name="Baiduspider", hours_ago=6)

        # 别的行业：整条链路都有，但不应污染行业 1
        created["other_industry"] = _mk_task(
            db, "https://demo.loop/case/other-industry",
            title="别的行业的文章", industry_id=OTHER_INDUSTRY_ID,
        ).id
        _mk_hit(db, "/case/other-industry", matched_url="/case/other-industry", hours_ago=2)
        _mk_citation(db, "https://demo.loop/case/other-industry", rank=1,
                     industry_id=OTHER_INDUSTRY_ID)

    yield created

    with _db() as db:
        from app.models import (
            CrawlerHit,
            GeoVisibilityRun,
            GeoVisibilitySource,
            ProductionTask,
        )

        paths = [
            "/case/not-crawled", "/case/crawled-only", "/case/cited-late",
            "/case/top3", "/case/search-only", "/case/other-industry",
        ]
        db.query(CrawlerHit).filter(CrawlerHit.path.in_(paths)).delete(
            synchronize_session=False)
        run_ids = [r.id for r in db.query(GeoVisibilityRun).filter(
            GeoVisibilityRun.keyword.in_(["真空泵怎么选型", "真空泵哪个牌子好"])
        ).all()]
        if run_ids:
            db.query(GeoVisibilitySource).filter(
                GeoVisibilitySource.run_id.in_(run_ids)).delete(synchronize_session=False)
            db.query(GeoVisibilityRun).filter(
                GeoVisibilityRun.id.in_(run_ids)).delete(synchronize_session=False)
        db.query(ProductionTask).filter(
            ProductionTask.publish_url.like("https://demo.loop/%")
        ).delete(synchronize_session=False)
        db.commit()


# ============================================================
#  一、四阶段漏斗
# ============================================================
def test_funnel_has_four_ordered_stages(seeded):
    with _db() as db:
        funnel = geo_loop.publish_funnel(db, INDUSTRY_ID, days=90)
    keys = [s["key"] for s in funnel["stages"]]
    assert keys == ["published", "crawled", "cited", "top3"]
    assert all(s["label"] for s in funnel["stages"])


def test_funnel_counts_each_stage(seeded):
    """四篇（不含 search-only）各自落在一个阶段上。"""
    with _db() as db:
        counts = geo_loop.publish_funnel(db, INDUSTRY_ID, days=90)["counts"]
    assert counts["published"] == 5, "行业 1 共 5 篇已发布（含只被百度抓的那篇）"
    assert counts["crawled"] == 3, "AI 抓过 3 篇"
    assert counts["cited"] == 2, "被引用 2 篇"
    assert counts["top3"] == 1, "进前 3 只有 1 篇"


def test_funnel_stages_are_monotonically_decreasing(seeded):
    """漏斗必须严格递进 —— 任何一步大于上一步都说明口径写错了。"""
    with _db() as db:
        counts = geo_loop.publish_funnel(db, INDUSTRY_ID, days=90)["counts"]
    assert counts["published"] >= counts["crawled"] >= counts["cited"] >= counts["top3"]


def test_search_bot_does_not_count_as_ai_crawl(seeded):
    """只被 Baiduspider 抓过的内容，不能被算成「AI 已收录」。

    这是本模块最核心的口径：把搜索引擎收录混进 AI 收录率，
    指标会好看，但会掩盖「AI 根本没来抓」这个真正要修的问题。
    """
    with _db() as db:
        funnel = geo_loop.publish_funnel(db, INDUSTRY_ID, days=90)
        rows = geo_loop.attribution_table(db, INDUSTRY_ID, days=90, limit=100)

    assert funnel["search_only_count"] == 1
    row = next(r for r in rows if r["title"] == "只被百度抓过")
    assert row["search_hits"] >= 1
    assert row["ai_hits"] == 0
    assert row["status"] == "not_crawled", "只有搜索引擎抓过仍属「未被 AI 抓取」"


def test_funnel_rates_are_fractions(seeded):
    with _db() as db:
        funnel = geo_loop.publish_funnel(db, INDUSTRY_ID, days=90)
    stages = {s["key"]: s for s in funnel["stages"]}
    assert stages["published"]["rate_of_prev"] == 1.0
    assert stages["crawled"]["rate_of_prev"] == round(3 / 5, 4)
    assert stages["cited"]["rate_of_prev"] == round(2 / 3, 4)
    assert stages["top3"]["rate_of_prev"] == round(1 / 2, 4)
    assert all(0.0 <= s["rate_of_published"] <= 1.0 for s in funnel["stages"])


def test_funnel_isolated_by_industry(seeded):
    """别的行业的已发布内容不能混进本行业的分母。"""
    with _db() as db:
        mine = geo_loop.publish_funnel(db, INDUSTRY_ID, days=90)["counts"]
        other = geo_loop.publish_funnel(db, OTHER_INDUSTRY_ID, days=90)["counts"]
    assert mine["published"] == 5
    assert other["published"] == 1
    assert mine["top3"] == 1, "别的行业那篇 rank=1 不能算进本行业"
    assert other["top3"] == 1


def test_citation_from_other_industry_is_not_counted(seeded):
    """跨行业的引用记录不能污染本行业漏斗（信源表本身不带行业，必须经 Run 过滤）。"""
    with _db() as db:
        rows = geo_loop.attribution_table(db, INDUSTRY_ID, days=90, limit=100)
    other = [r for r in rows if r["title"] == "别的行业的文章"]
    assert other == [], "别的行业的内容根本不该出现在本行业归因表里"


def test_funnel_ignores_unrelated_crawl_paths(seeded):
    """抓取记录里那些对不上任何已发布内容的路径，不能凭空造出「已收录」。"""
    with _db() as db:
        _mk_hit(db, "/random/unrelated/page", bot_class="ai_bot", bot_name="GPTBot")
        counts = geo_loop.publish_funnel(db, INDUSTRY_ID, days=90)["counts"]
    assert counts["crawled"] == 3, "无关路径不应被算进任何内容的收录"


def test_funnel_handles_no_published_content(client):
    with _db() as db:
        funnel = geo_loop.publish_funnel(db, 987654, days=90)
    assert funnel["counts"] == {"published": 0, "crawled": 0, "cited": 0, "top3": 0}
    assert all(s["rate_of_published"] == 0.0 for s in funnel["stages"])


# ============================================================
#  二、逐篇归因表
# ============================================================
def test_attribution_status_labels(seeded):
    with _db() as db:
        rows = geo_loop.attribution_table(db, INDUSTRY_ID, days=90, limit=100)
    by_title = {r["title"]: r for r in rows}
    assert by_title["未收录文章"]["status"] == "not_crawled"
    assert by_title["已收录未引用"]["status"] == "crawled_only"
    assert by_title["被引用但靠后"]["status"] == "cited"
    assert by_title["进前3的文章"]["status"] == "top3"
    assert all(r["status_label"] and r["action"] for r in rows), "每行都要有标签和下一步动作"


def test_attribution_sorts_problems_first(seeded):
    """运营打开这张表是为了找问题，不是看已成功的那些。"""
    with _db() as db:
        rows = geo_loop.attribution_table(db, INDUSTRY_ID, days=90, limit=100)
    order = [r["status"] for r in rows]
    assert order.index("not_crawled") < order.index("crawled_only")
    assert order.index("crawled_only") < order.index("cited")
    assert order.index("cited") < order.index("top3")


def test_attribution_reports_bots_and_rank(seeded):
    with _db() as db:
        rows = geo_loop.attribution_table(db, INDUSTRY_ID, days=90, limit=100)
    top3 = next(r for r in rows if r["title"] == "进前3的文章")
    assert top3["ai_hits"] == 1
    assert "GPTBot" in top3["ai_bots"]
    assert top3["cited_times"] == 2
    assert top3["best_rank"] == 1, "两次引用取最好名次"
    assert top3["first_crawl"], "应记录首次抓取时间"


# ============================================================
#  三、内容旅程钻取
# ============================================================
def test_content_journey_returns_raw_records(seeded):
    """钻取必须能看到原始抓取记录 —— 否则「没被收录」这个结论不可信。"""
    with _db() as db:
        journey = geo_loop.content_journey(
            db, "https://demo.loop/case/top3", industry_id=INDUSTRY_ID)
    assert journey["ai_hits"] == 1
    assert len(journey["crawl_records"]) == 1
    assert journey["crawl_records"][0]["bot_name"] == "GPTBot"
    assert journey["status"] == "top3"
    assert len(journey["citations"]) == 2
    assert journey["best_rank"] == 1
    # 引用要带上「在哪个问题下被引用」——这才是可行动的信息
    keywords = {c["keyword"] for c in journey["citations"]}
    assert "真空泵怎么选型" in keywords


def test_content_journey_matches_by_normalized_path(seeded):
    """带查询串、尾斜杠、大小写差异的 URL 都要能匹配上同一篇内容。

    同一篇文章在不同平台、不同分享渠道下 URL 形态各异，
    按完整 URL 关联会得出「全都收录失败」的假结论。
    """
    with _db() as db:
        for variant in (
            "https://demo.loop/case/top3/",
            "https://demo.loop/case/top3?utm_source=wechat",
            "https://demo.loop/case/top3#section-2",
            "/case/top3",
        ):
            journey = geo_loop.content_journey(db, variant, industry_id=INDUSTRY_ID)
            assert journey["ai_hits"] == 1, f"{variant} 未匹配到同一篇内容"
            assert journey["best_rank"] == 1


def test_content_journey_for_uncrawled_content(seeded):
    with _db() as db:
        journey = geo_loop.content_journey(
            db, "https://demo.loop/case/not-crawled", industry_id=INDUSTRY_ID)
    assert journey["ai_hits"] == 0
    assert journey["crawl_records"] == []
    assert journey["citations"] == []
    assert journey["status"] == "not_crawled"
    assert "sitemap" in journey["action"]


def test_content_journey_separates_search_bot(seeded):
    with _db() as db:
        journey = geo_loop.content_journey(
            db, "https://demo.loop/case/search-only", industry_id=INDUSTRY_ID)
    assert journey["ai_hits"] == 0
    assert journey["search_hits"] == 1
    assert journey["total_hits"] == 1


# ============================================================
#  四、回流选题
# ============================================================
def test_recycle_produces_actionable_kinds(seeded):
    with _db() as db:
        items = geo_loop.recycle_suggestions(db, INDUSTRY_ID, days=90, limit=50)
    kinds = {i["kind"] for i in items}
    assert {"replicate", "push_index", "improve"} <= kinds
    assert all(i["title"] and i["reason"] and i["action"] for i in items)


def test_recycle_marks_verified_pattern_as_replicate(seeded):
    with _db() as db:
        items = geo_loop.recycle_suggestions(db, INDUSTRY_ID, days=90, limit=50)
    repl = [i for i in items if i["kind"] == "replicate"]
    assert repl and repl[0]["priority"] == "高"
    assert "进前3的文章" in repl[0]["title"]


def test_recycle_does_not_duplicate_benchmark_suggestions(seeded):
    """对标第三方信源是 ``analytics.topic_suggestions`` 的职责。

    两处都产出「对标建议」只会让运营收到两份互相矛盾的清单，
    所以这里刻意不产出 ``benchmark`` 类型。
    """
    with _db() as db:
        items = geo_loop.recycle_suggestions(db, INDUSTRY_ID, days=90, limit=50)
    assert all(i["kind"] != "benchmark" for i in items)


def test_recycle_respects_limit(seeded):
    with _db() as db:
        items = geo_loop.recycle_suggestions(db, INDUSTRY_ID, days=90, limit=2)
    assert len(items) <= 2


def test_recycle_sorted_by_priority(seeded):
    """列表标了「越先做越靠前」，就必须真的按优先级排。

    否则会出现「中」排在「高」前面，运营第一反应是这张表坏了、不再相信它。
    """
    with _db() as db:
        items = geo_loop.recycle_suggestions(db, INDUSTRY_ID, days=90, limit=50)
    order = {"高": 0, "中": 1, "低": 2}
    ranks = [order[i["priority"]] for i in items]
    assert ranks == sorted(ranks), f"优先级未排序：{[i['priority'] for i in items]}"


# ============================================================
#  五、闭环健康度
# ============================================================
def test_loop_health_finds_weakest_transition(seeded):
    """行业 1：发布 5 → 收录 3 → 引用 2 → 前 3 1。

    转化率依次为 60% / 66.7% / 50%，最弱是「前 3」，因此瓶颈应指向 expand。
    """
    with _db() as db:
        health = geo_loop.loop_health(db, INDUSTRY_ID, days=90)
    assert health["stage"] == "top3"
    assert health["bottleneck"] == "expand"
    assert health["transition_rate"] == 0.5
    assert health["detail"] and health["next_step"]
    assert "funnel" in health


def test_loop_health_empty_when_nothing_published(client):
    with _db() as db:
        health = geo_loop.loop_health(db, 987654, days=90)
    assert health["stage"] == "empty"
    assert health["funnel"]["counts"]["published"] == 0
    assert "软文生产" in health["detail"]


def test_loop_health_points_to_crawl_when_ai_never_comes(client):
    """已发布但 AI 一次都没来抓 → 瓶颈必须是「收录」，动作指向 sitemap/robots。"""
    from app.models import Industry

    industry_id = 424242
    with _db() as db:
        if not db.query(Industry).filter(Industry.id == industry_id).first():
            db.add(Industry(id=industry_id, name="闭环健康度测试行业"))
            db.commit()
        t = _mk_task(db, "https://demo.loop/case/health-check",
                     title="健康度用例", industry_id=industry_id)
        try:
            health = geo_loop.loop_health(db, industry_id, days=90)
            assert health["stage"] == "crawled"
            assert health["bottleneck"] == "push_index"
            assert "sitemap" in health["detail"]
        finally:
            from app.models import ProductionTask
            db.query(ProductionTask).filter(ProductionTask.id == t.id).delete()
            db.commit()


def test_loop_health_wording_matches_reality_when_partially_crawled(client):
    """收录环节最弱、但已有部分内容被抓取时，结论不能写成「AI 还没来抓」。

    漏斗上明明显示有已收录内容，结论却说「没来抓」，是自相矛盾 ——
    运营一眼就会不信这个诊断，之后连带整块看板都不再信。
    """
    from app.models import CrawlerHit, Industry, ProductionTask

    industry_id = 727272
    with _db() as db:
        if not db.query(Industry).filter(Industry.id == industry_id).first():
            db.add(Industry(id=industry_id, name="措辞一致性测试行业"))
            db.commit()
        made = []
        # 3 篇已发布：2 篇被抓取，其中 2 篇被引用且都进前 3
        # 转化率 66.7% / 100% / 100% → 最弱是「收录」，但 crawled > 0
        for i in range(3):
            made.append(_mk_task(db, f"https://demo.loop/wording/art-{i}",
                                 title=f"措辞用例{i}", industry_id=industry_id).id)
        hits = [_mk_hit(db, f"/wording/art-{i}", matched_url=f"/wording/art-{i}")
                for i in range(2)]
        for i in range(2):
            _mk_citation(db, f"https://demo.loop/wording/art-{i}", rank=1,
                         keyword="措辞用例关键词", industry_id=industry_id)
        try:
            health = geo_loop.loop_health(db, industry_id, days=90)
            assert health["bottleneck"] == "push_index"
            assert health["funnel"]["counts"]["crawled"] == 2, "前提：确实有内容被抓取"
            assert "还没来抓" not in health["detail"], (
                f"漏斗显示已收录 2 篇，结论却说「还没来抓」：{health['detail']}"
            )
            assert "sitemap" in health["detail"]
        finally:
            from app.models import GeoVisibilityRun, GeoVisibilitySource
            db.query(CrawlerHit).filter(
                CrawlerHit.id.in_([h.id for h in hits])).delete(synchronize_session=False)
            runs = db.query(GeoVisibilityRun).filter(
                GeoVisibilityRun.keyword == "措辞用例关键词").all()
            for r in runs:
                db.query(GeoVisibilitySource).filter(
                    GeoVisibilitySource.run_id == r.id).delete(synchronize_session=False)
                db.query(GeoVisibilityRun).filter(
                    GeoVisibilityRun.id == r.id).delete(synchronize_session=False)
            db.query(ProductionTask).filter(
                ProductionTask.id.in_(made)).delete(synchronize_session=False)
            db.commit()


def test_loop_health_detects_path_mismatch(client):
    """抓取路径的末段与已发布内容一致、但整条路径不同 → 必须报「路径不一致」。

    这是最容易把运营带偏的一种情况：看板说「AI 没来抓」，
    于是去折腾 sitemap 和 robots，而真实原因只是发布 URL 多了一段路径。
    两种情况给出的动作完全不同，必须分开诊断。
    """
    from app.models import CrawlerHit, Industry, ProductionTask

    industry_id = 515151
    with _db() as db:
        if not db.query(Industry).filter(Industry.id == industry_id).first():
            db.add(Industry(id=industry_id, name="路径不一致测试行业"))
            db.commit()
        # 发布 URL 是 /blog/post-x，但日志里的路径是 /articles/post-x
        t = _mk_task(db, "https://demo.loop/blog/post-x",
                     title="路径对不上的文章", industry_id=industry_id)
        h = _mk_hit(db, "/articles/post-x", bot_class="ai_bot", bot_name="GPTBot")
        try:
            health = geo_loop.loop_health(db, industry_id, days=90)
            assert health["stage"] == "path_mismatch"
            assert health["bottleneck"] == "path_mismatch"
            assert "路径" in health["detail"]
            # 精确证据：slug 相同（post-x）但整条路径不同
            near = health["funnel"]["near_miss"]
            assert len(near) == 1
            assert near[0]["hit_path"] == "/articles/post-x"
            assert near[0]["published_path"] == "/blog/post-x"
            assert near[0]["ai_hits"] == 1
            assert health["funnel"]["matched_ai_hits"] == 0
        finally:
            db.query(CrawlerHit).filter(CrawlerHit.id == h.id).delete()
            db.query(ProductionTask).filter(ProductionTask.id == t.id).delete()
            db.commit()


def test_funnel_exposes_matched_vs_unmatched_ai_hits(seeded):
    """三类 AI 抓取流量必须分开暴露 —— 只看总数会把路径配置错误藏起来。

    分类：命中本行业 / 命中别的行业空间 / 谁也对不上。
    最后一类才是「路径可能配错了」的信号。
    """
    with _db() as db:
        funnel = geo_loop.publish_funnel(db, INDUSTRY_ID, days=90)
    assert funnel["matched_ai_hits"] >= 3
    assert funnel["ai_crawl_total"] == (
        funnel["matched_ai_hits"]
        + funnel["other_industry_ai_hits"]
        + funnel["unmatched_ai_hits"]
    )


def test_other_industry_traffic_is_not_reported_as_path_mismatch(client):
    """「对不上任何内容的 AI 流量」本身不是路径配错的证据，不能据此报警。

    ``crawler_hit`` 是全站级的（一个站点服务多个行业空间），站点上还天然存在
    产品页、分类页这些从未打算归因的 URL。若按「存在对不上的流量」判定路径配错，
    多行业共用站点时会天天误报，运营很快就不再相信这个提示。
    只有当**末段路径与某篇已发布内容一致、整条路径却不同**时才算配错。
    """
    from app.models import CrawlerHit, Industry, ProductionTask

    industry_id = 616161
    with _db() as db:
        if not db.query(Industry).filter(Industry.id == industry_id).first():
            db.add(Industry(id=industry_id, name="多行业误报测试"))
            db.commit()
        t = _mk_task(db, "https://demo.loop/other/isolated",
                     title="孤立行业的内容", industry_id=industry_id)
        # 一条谁也对不上的 AI 流量（例如产品页 / 别的行业空间），slug 与本行业无关
        h = _mk_hit(db, "/unrelated/belonging-to-nobody", bot_class="ai_bot",
                    bot_name="GPTBot")
        try:
            funnel = geo_loop.publish_funnel(db, industry_id, days=90)
            assert funnel["counts"]["crawled"] == 0
            # 确实存在「谁也对不上」的流量 …
            assert funnel["unmatched_ai_hits"] >= 1
            # … 但没有 slug 碰撞，所以不构成路径配错的证据
            assert funnel["near_miss"] == []

            health = geo_loop.loop_health(db, industry_id, days=90)
            assert health["stage"] != "path_mismatch", (
                "对不上任何内容的流量被误报成路径不一致"
            )
            assert health["stage"] == "crawled"
        finally:
            db.query(CrawlerHit).filter(CrawlerHit.id == h.id).delete()
            db.query(ProductionTask).filter(ProductionTask.id == t.id).delete()
            db.commit()


def test_funnel_near_miss_requires_slug_collision(seeded):
    """slug 不同则不算配错 —— 守住「精确信号」这条线，避免误报回潮。"""
    from app.models import CrawlerHit

    with _db() as db:
        h = _mk_hit(db, "/totally/different-slug", bot_class="ai_bot",
                    bot_name="GPTBot")
        try:
            funnel = geo_loop.publish_funnel(db, INDUSTRY_ID, days=90)
            assert funnel["near_miss"] == [], "slug 不同却被判成路径配错"
        finally:
            db.query(CrawlerHit).filter(CrawlerHit.id == h.id).delete()
            db.commit()


def test_not_crawled_action_mentions_path_check_first(seeded):
    """「未被抓取」的处置建议必须先让人核对路径 —— 先查便宜且最可能的原因。"""
    with _db() as db:
        rows = geo_loop.attribution_table(db, INDUSTRY_ID, days=90, limit=100)
    row = next(r for r in rows if r["status"] == "not_crawled")
    assert "路径" in row["action"]
    assert row["action"].index("路径") < row["action"].index("sitemap")


# ============================================================
#  六、API
# ============================================================
def test_loop_endpoints_require_auth(client):
    for path in (
        "/api/crawler/funnel?industry_id=1",
        "/api/crawler/attribution?industry_id=1",
        "/api/crawler/recycle?industry_id=1",
        "/api/crawler/loop-health?industry_id=1",
        "/api/crawler/loop-overview?industry_id=1",
        "/api/crawler/journey?url=/case/x",
    ):
        assert client.get(path).status_code == 401, path


def test_loop_overview_endpoint_shape(client, auth_headers, seeded):
    data = client.get("/api/crawler/loop-overview", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID, "days": 90}).json()["data"]
    assert data["days"] == 90
    assert [s["key"] for s in data["funnel"]["stages"]] == [
        "published", "crawled", "cited", "top3"]
    assert data["funnel"]["counts"]["published"] == 5
    assert data["health"]["stage"] == "top3"
    assert isinstance(data["attribution"], list)
    assert isinstance(data["recycle"], list)
    # health 里不再重复嵌套 funnel（避免响应体无谓翻倍）
    assert "funnel" not in data["health"]


def test_funnel_and_health_endpoints(client, auth_headers, seeded):
    funnel = client.get("/api/crawler/funnel", headers=auth_headers,
                        params={"industry_id": INDUSTRY_ID, "days": 90}).json()["data"]
    assert funnel["counts"]["crawled"] == 3

    health = client.get("/api/crawler/loop-health", headers=auth_headers,
                        params={"industry_id": INDUSTRY_ID, "days": 90}).json()["data"]
    assert health["stage"] == "top3"


def test_attribution_endpoint_filters_by_status(client, auth_headers, seeded):
    data = client.get("/api/crawler/attribution", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID, "days": 90,
                              "status": "not_crawled"}).json()["data"]
    assert data["total"] >= 1
    assert all(i["status"] == "not_crawled" for i in data["items"])


def test_recycle_endpoint(client, auth_headers, seeded):
    data = client.get("/api/crawler/recycle", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID, "days": 90}).json()["data"]
    assert data["total"] >= 1
    assert all(i["kind"] in ("replicate", "push_index", "improve") for i in data["items"])


def test_journey_endpoint(client, auth_headers, seeded):
    assert client.get("/api/crawler/journey", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID}).status_code == 422, "缺 url 应被 FastAPI 拦下"

    data = client.get("/api/crawler/journey", headers=auth_headers,
                      params={"url": "https://demo.loop/case/top3",
                              "industry_id": INDUSTRY_ID}).json()["data"]
    assert data["status"] == "top3"
    assert len(data["crawl_records"]) == 1
    assert len(data["citations"]) == 2


def test_journey_endpoint_rejects_blank_url(client, auth_headers):
    resp = client.get("/api/crawler/journey", headers=auth_headers,
                      params={"url": "   ", "industry_id": INDUSTRY_ID})
    assert resp.status_code == 400
