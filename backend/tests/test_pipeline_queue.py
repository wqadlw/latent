# -*- coding: utf-8 -*-
"""生产流水线智能化（阶段 C）测试：可编排规格 + 断点续跑 + 有界并发队列 + 批量生产。

守护的核心不变量
----------------
1. **坏规格不能炸运行** —— 规格是用户可编辑、可被手工改库的 JSON 文本，
   解析失败必须退回默认全开，而不是抛异常让一条已排队的任务永远卡住；
2. **续跑只跳过连续前缀** —— 第③步做完了但第②步没有，不能越过②直接续③；
3. **「状态 done」不等于「产物可用」** —— 只认步骤行状态会让续跑跳到第⑦步，
   然后拿着空终稿去评审。产物为空就必须重跑；
4. **①连接不阻断续跑** —— 它没有产物、每次必须重连引擎；若把它当「未完成」
   会让后面的产物复用全部失效；
5. **编排器不抛异常 ≠ 作业成功** —— 失败是写进 ``run.status`` 后正常返回的，
   队列必须回查运行终态，否则会把失败记成 done；
6. **同一运行同时只有一个活跃作业** —— 否则连点两次「开始」就跑两遍、烧两份 token；
7. **并发上限真的生效** —— 这是整个队列存在的理由；
8. **进程中断的作业会被放回队列** —— 否则那条运行再也不会被推进，
   而队列平白少一个并发额度；
9. **批量去重** —— 重复提交的代价是真金白银（每条 6~10 次 LLM 调用）。
"""
import json
import threading
import time

import pytest
from app.services import batch as batch_svc
from app.services import pipeline as pipeline_svc
from app.services import task_queue

INDUSTRY_ID = 881001
OTHER_INDUSTRY_ID = 881002


def _db():
    from app.database import SessionLocal

    return SessionLocal()


@pytest.fixture(scope="module", autouse=True)
def _industry(client):
    """本模块专用的行业空间 + 全量清理，避免污染共享测试库。

    依赖 ``client`` 是必须的：建表/迁移发生在 app 的 lifespan 里，
    没有它这个 fixture 会先于建表执行，直接撞上「no such table: industry」。
    """
    from app.models import Industry

    with _db() as db:
        for iid, name in ((INDUSTRY_ID, "流水线测试行业"), (OTHER_INDUSTRY_ID, "流水线测试行业B")):
            if not db.query(Industry).filter(Industry.id == iid).first():
                db.add(Industry(id=iid, name=name))
        db.commit()
    yield


@pytest.fixture(autouse=True)
def _clean_queue(_industry):
    """每个用例开始前清空本模块行业的运行与作业。

    队列用例天然共享一张表：上一个用例留下的排队作业会被 ``claim_next`` 领走，
    「未到期的作业不该被领取」这类断言就会因为别人的作业而失败。
    与其在每条断言里加过滤条件，不如让每个用例从干净状态开始。
    """
    from app.models import BrowserStudioStep, PipelineJob, ProductionTask

    with _db() as db:
        run_ids = [
            r[0] for r in db.query(ProductionTask.id)
            .filter(ProductionTask.industry_id.in_((INDUSTRY_ID, OTHER_INDUSTRY_ID))).all()
        ]
        db.query(PipelineJob).filter(
            PipelineJob.industry_id.in_((INDUSTRY_ID, OTHER_INDUSTRY_ID))
        ).delete(synchronize_session=False)
        if run_ids:
            db.query(BrowserStudioStep).filter(
                BrowserStudioStep.run_id.in_(run_ids)
            ).delete(synchronize_session=False)
        db.query(ProductionTask).filter(
            ProductionTask.industry_id.in_((INDUSTRY_ID, OTHER_INDUSTRY_ID))
        ).delete(synchronize_session=False)
        db.commit()
    yield


def _mk_run(db, subject="测试选题", platform="sohu", industry_id=INDUSTRY_ID,
            status="created", spec=None, batch_id="", **kw):
    from app.models import ProductionTask

    run = ProductionTask(
        mode="auto", industry_id=industry_id, name=f"{subject}｜{platform}",
        title=subject, subject=subject, platform=platform, status=status,
        pipeline_spec=spec if isinstance(spec, str) else (pipeline_svc.dump_spec(spec) if spec else ""),
        batch_id=batch_id, **kw,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _mk_steps(db, run_id, statuses):
    """按 {step_key: status} 建步骤行（顺序即 STEP_ORDER）。"""
    from app.models import BrowserStudioStep

    rows = []
    for no, key in enumerate(pipeline_svc.STEP_ORDER, start=1):
        row = BrowserStudioStep(
            run_id=run_id, step_no=no, step_key=key, title=key,
            status=statuses.get(key, "pending"),
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


def _fill_artifacts(db, run, upto="geo"):
    """把 run 的各产物列填上，模拟「已经跑到第 N 步」。"""
    idx = pipeline_svc.STEP_ORDER.index(upto)
    values = {
        "clarified_brief": "创作简报正文",
        "outline_content": "大纲正文",
        "draft_content": "初稿正文",
        "rewrite_content": "精修稿正文",
        "final_content": "终稿正文",
        "final_title": "终稿标题",
    }
    for key in pipeline_svc.STEP_ORDER[: idx + 1]:
        field = pipeline_svc._ARTIFACT_FIELD.get(key)
        if field in values:
            setattr(run, field, values[field])
    if "review" in pipeline_svc.STEP_ORDER[: idx + 1]:
        run.review_result = json.dumps({"gate_pass": True, "geo_score": 82, "issues": []},
                                       ensure_ascii=False)
    if "revise" in pipeline_svc.STEP_ORDER[: idx + 1]:
        run.revise_rounds = "[]"
    run.geo_score = 82
    db.commit()
    return run


# ============================================================
#  C1：编排规格
# ============================================================
def test_default_spec_enables_every_step():
    spec = pipeline_svc.default_spec()
    assert spec["steps"] == pipeline_svc.STEP_ORDER
    assert spec["max_revise_rounds"] == pipeline_svc.DEFAULT_MAX_REVISE_ROUNDS


def test_spec_tolerates_garbage_input():
    """坏规格必须退回默认，绝不抛异常 —— 否则一条已排队的任务会永远卡住。"""
    for bad in ("{not json", "[]", "123", object(), {"steps": "nope"}):
        spec, _notes = pipeline_svc.validate_spec(bad)
        assert spec["steps"] == pipeline_svc.STEP_ORDER


def test_spec_readds_required_steps_and_reports_it():
    spec, notes = pipeline_svc.validate_spec({"steps": ["outline", "draft"]})
    # geo / review / confirm / connect 都是必开，必须被补回来
    for key in ("connect", "outline", "draft", "geo", "review", "confirm"):
        assert key in spec["steps"]
    assert any("补回必开步骤" in n for n in notes)


def test_spec_keeps_order_and_drops_unknown_steps():
    spec, notes = pipeline_svc.validate_spec(
        {"steps": ["geo", "bogus", "outline", "draft", "review", "confirm"]}
    )
    assert spec["steps"] == ["connect", "outline", "draft", "geo", "review", "confirm"]
    assert any("bogus" in n for n in notes)


def test_spec_clamps_revise_rounds():
    spec, _ = pipeline_svc.validate_spec({"max_revise_rounds": 99})
    assert spec["max_revise_rounds"] == pipeline_svc.MAX_REVISE_ROUNDS_CAP
    spec, _ = pipeline_svc.validate_spec({"max_revise_rounds": -3})
    assert spec["max_revise_rounds"] == 0
    spec, notes = pipeline_svc.validate_spec({"max_revise_rounds": "abc"})
    assert spec["max_revise_rounds"] == pipeline_svc.DEFAULT_MAX_REVISE_ROUNDS
    assert notes


def test_describe_steps_marks_optional_and_artifact():
    steps = pipeline_svc.describe_steps()
    by_key = {s["key"]: s for s in steps}
    assert [s["key"] for s in steps] == pipeline_svc.STEP_ORDER
    assert by_key["depolish"]["optional"] is True
    assert by_key["geo"]["optional"] is False
    assert by_key["outline"]["artifact_field"] == "outline_content"
    assert by_key["connect"]["artifact_field"] == ""


# ============================================================
#  C1：断点续跑
# ============================================================
def test_plan_skips_completed_prefix():
    with _db() as db:
        run = _mk_run(db, subject="续跑-前缀")
        _mk_steps(db, run.id, dict.fromkeys(pipeline_svc.STEP_ORDER[:6], "done"))
        _fill_artifacts(db, run, upto="geo")
        plan = pipeline_svc.plan(db, run)
    assert plan["done"] == ["clarify", "outline", "draft", "depolish", "geo"]
    assert plan["next_key"] == "review"
    assert plan["can_resume"] is True


def test_connect_never_blocks_the_reusable_prefix():
    """①连接每次都必须重连引擎，但它不能阻断后面产物的复用。"""
    with _db() as db:
        run = _mk_run(db, subject="续跑-连接不阻断")
        _mk_steps(db, run.id, dict.fromkeys(pipeline_svc.STEP_ORDER[:6], "done"))
        _fill_artifacts(db, run, upto="geo")
        plan = pipeline_svc.plan(db, run)
    assert "connect" not in plan["done"]           # 不计入复用
    assert plan["starts_at"] == "connect"          # 但它仍是第一个被执行的
    assert plan["next_key"] == "review"            # 用户看到的「从哪继续」
    assert plan["done_count"] == 5


def test_plan_stops_at_gap_even_if_later_steps_are_done():
    """只跳过连续前缀：第③步完成了但第②步没有，就不能越过②续③。"""
    with _db() as db:
        run = _mk_run(db, subject="续跑-断点")
        _mk_steps(db, run.id, {"clarify": "done", "outline": "pending", "draft": "done"})
        run.clarified_brief = "简报"
        run.draft_content = "初稿"
        db.commit()
        plan = pipeline_svc.plan(db, run)
    assert plan["done"] == ["clarify"]
    assert plan["next_key"] == "outline"


def test_done_status_without_artifact_is_not_reusable():
    """状态是 done 但产物为空 → 必须重跑。

    防的是「上次写库失败 / 产物被人工清空」：只认状态会让续跑直接跳到第⑦步，
    然后拿着空终稿去评审。
    """
    with _db() as db:
        run = _mk_run(db, subject="续跑-空产物")
        _mk_steps(db, run.id, {"clarify": "done", "outline": "done"})
        run.clarified_brief = "简报"      # 只有①b 的产物在
        run.outline_content = ""          # ② 的状态是 done，但产物丢了
        db.commit()
        plan = pipeline_svc.plan(db, run)
    assert plan["done"] == ["clarify"]
    assert plan["next_key"] == "outline"


def test_plan_from_step_forces_redo():
    """逃生口：产物虽然写过了但结果不满意 → 从指定步骤强制重做。"""
    with _db() as db:
        run = _mk_run(db, subject="续跑-强制重做")
        _mk_steps(db, run.id, dict.fromkeys(pipeline_svc.STEP_ORDER[:6], "done"))
        _fill_artifacts(db, run, upto="geo")
        plan = pipeline_svc.plan(db, run, from_step="draft")
    assert plan["done"] == ["clarify", "outline"]
    assert plan["next_key"] == "draft"


def test_plan_respects_disabled_steps():
    with _db() as db:
        spec, _ = pipeline_svc.validate_spec(
            {"steps": ["connect", "outline", "draft", "geo", "review", "confirm"]}
        )
        run = _mk_run(db, subject="续跑-裁剪", spec=spec)
        plan = pipeline_svc.plan(db, run)
    assert plan["disabled"] == ["clarify", "depolish", "revise"]
    assert "clarify" not in plan["enabled"]
    assert plan["next_key"] == "outline"


def test_hydrate_reads_artifacts_and_review_issues():
    with _db() as db:
        run = _mk_run(db, subject="续跑-装载")
        _fill_artifacts(db, run, upto="geo")
        run.review_result = json.dumps({"gate_pass": False, "issues": ["缺数据", "标题空泛"]},
                                       ensure_ascii=False)
        run.revise_rounds = json.dumps([{"round": 1}], ensure_ascii=False)
        db.commit()
        h = pipeline_svc.hydrate(run)
    assert h["outline"] == "大纲正文"
    assert h["final_content"] == "终稿正文"
    assert h["issues"] == ["缺数据", "标题空泛"]
    assert len(h["rounds"]) == 1


def test_reset_from_clears_only_the_tail_and_keeps_artifacts():
    with _db() as db:
        run = _mk_run(db, subject="续跑-重置")
        _mk_steps(db, run.id, dict.fromkeys(pipeline_svc.STEP_ORDER[:6], "done"))
        _fill_artifacts(db, run, upto="geo")
        outcome = pipeline_svc.reset_from(db, run, "draft")
        rows = {r.step_key: r.status for r in
                db.query(__import__("app.models", fromlist=["BrowserStudioStep"]).BrowserStudioStep)
                .filter_by(run_id=run.id).all()}
        db.refresh(run)
    assert "draft" in outcome["cleared"] and "geo" in outcome["cleared"]
    assert "clarify" in outcome["kept"]
    assert rows["outline"] == "done" and rows["draft"] == "pending"
    # 产物列不动 —— 这正是「重试不重烧 token」的落点
    assert run.final_content == "终稿正文"


# ============================================================
#  C1：引擎代理（裁剪 / 回放）
# ============================================================
class _RecordingEngine:
    """假引擎：记录被调用的方法，可配置为「一被调用就报错」。"""

    engine_kind = "fake"

    def __init__(self, explode=False):
        self.calls = []
        self.explode = explode

    def _maybe(self, name, ret):
        self.calls.append(name)
        if self.explode:
            raise AssertionError(f"不该调用引擎的 {name}（应当回放或透传）")
        return ret

    def clarify(self, briefing, ctx):
        return self._maybe("clarify", "新简报")

    def gen_outline(self, briefing, clarified, ctx):
        return "", self._maybe("gen_outline", "新大纲")

    def gen_draft(self, outline_text, ctx):
        return "", self._maybe("gen_draft", "新初稿")

    def depolish(self, draft_text, ctx):
        return "", self._maybe("depolish", "新精修稿")

    def geo_strengthen(self, polished_text, ctx):
        return ("新标题", self._maybe("geo_strengthen", "新终稿"))

    def direct_revision(self, text, issues, round_no=1):
        return self._maybe("direct_revision", "新指令")


def test_replay_engine_replays_without_touching_inner():
    inner = _RecordingEngine(explode=True)
    notes = []
    engine = pipeline_svc.ReplayEngine(
        inner,
        hydrated={"clarified": "旧简报", "outline": "旧大纲", "draft": "旧初稿",
                  "polished": "旧精修", "final_title": "旧标题", "final_content": "旧终稿"},
        replay={"clarify", "outline", "draft", "depolish", "geo"},
        enabled=set(pipeline_svc.STEP_ORDER),
        note=notes.append,
    )
    assert engine.clarify("b", {}) == "旧简报"
    assert engine.gen_outline("b", "", {})[1] == "旧大纲"
    assert engine.gen_draft("o", {})[1] == "旧初稿"
    assert engine.depolish("d", {})[1] == "旧精修"
    assert engine.geo_strengthen("p", {}) == ("旧标题", "旧终稿")
    assert inner.calls == []
    assert len(notes) == 5      # 每次回放都要留痕，否则审计看不出是复用还是新生成


def test_replay_engine_passthrough_when_step_disabled():
    inner = _RecordingEngine(explode=True)
    enabled = set(pipeline_svc.STEP_ORDER) - {"depolish", "clarify"}
    engine = pipeline_svc.ReplayEngine(inner, hydrated={}, replay=set(), enabled=enabled)
    assert engine.clarify("b", {}) == ""
    assert engine.depolish("初稿原文", {})[1] == "初稿原文"    # 透传上一步产物
    assert inner.calls == []


def test_replay_engine_blocks_revision_when_disabled():
    inner = _RecordingEngine(explode=True)
    engine = pipeline_svc.ReplayEngine(
        inner, hydrated={"rounds": [{"round": 1}]},
        replay=set(), enabled=set(pipeline_svc.STEP_ORDER) - {"revise"},
    )
    # 空指令 → 编排器的整改循环天然 break，不需要新增控制流
    assert engine.direct_revision("终稿", ["问题"], 1) == ""
    assert inner.calls == []


def test_replay_engine_delegates_unknown_attributes():
    inner = _RecordingEngine()
    inner.last_call = {"role": "writing", "latency_ms": 12}
    engine = pipeline_svc.ReplayEngine(inner, hydrated={}, replay=set(),
                                       enabled=set(pipeline_svc.STEP_ORDER))
    assert engine.engine_kind == "fake"
    assert engine.last_call["latency_ms"] == 12


# ============================================================
#  C2：队列
# ============================================================
def test_enqueue_is_idempotent_per_run():
    """同一运行同时只能有一个活跃作业，否则连点两次就跑两遍。"""
    with _db() as db:
        run = _mk_run(db, subject="队列-幂等")
        first = task_queue.enqueue(db, INDUSTRY_ID, run.id)
        second = task_queue.enqueue(db, INDUSTRY_ID, run.id)
    assert first["created"] is True
    assert second["created"] is False
    assert second["job_id"] == first["job_id"]


def test_reenqueue_reuses_the_same_job_row():
    """重投必须复用同一行作业。

    否则「批次进度」会把 3 条运行算成 5 条 —— 运营看到的总数是错的。
    尝试次数本来就记在 attempts 上，不需要靠多行表达。
    """
    from app.models import PipelineJob

    with _db() as db:
        run = _mk_run(db, subject="队列-复用行")
        first = task_queue.enqueue(db, INDUSTRY_ID, run.id)["job_id"]
        job = db.query(PipelineJob).filter(PipelineJob.id == first).first()
        job.status = "failed"
        job.attempts = 2
        job.error = "上游 429"
        db.commit()
        again = task_queue.enqueue(db, INDUSTRY_ID, run.id, priority=2)
        rows = db.query(PipelineJob).filter(PipelineJob.run_id == run.id).all()
        db.refresh(job)
        state = (job.status, job.attempts, job.error, job.priority)
    assert again["job_id"] == first
    assert again["created"] is True
    assert again["reused_row"] is True
    assert len(rows) == 1                      # 没有多出一行
    assert state == ("queued", 0, "", 2)


def test_batch_progress_total_is_run_count_not_attempt_count():
    """批次进度必须按运行数计，重投不改变总数。"""
    with _db() as db:
        created = batch_svc.create(db, {
            "industry_id": INDUSTRY_ID,
            "subjects": ["进度稳定性A", "进度稳定性B"],
            "platforms": ["sohu"],
            "skip_duplicates": False,
        })
        bid = created["batch_id"]
        assert task_queue.batch_progress(db, bid)["total"] == 2
        # 整批重投一次
        batch_svc.enqueue_batch(db, bid)
        # 再重投一次
        batch_svc.enqueue_batch(db, bid)
        after = task_queue.batch_progress(db, bid)
    assert after["total"] == 2, "重投不应产生新的作业行"


def test_claim_next_prefers_priority_then_fifo():
    with _db() as db:
        low = _mk_run(db, subject="队列-低优先")
        high = _mk_run(db, subject="队列-高优先")
        low_id, high_id = low.id, high.id
        low_job = task_queue.enqueue(db, INDUSTRY_ID, low_id, priority=9)["job_id"]
        high_job = task_queue.enqueue(db, INDUSTRY_ID, high_id, priority=1)["job_id"]
        first = task_queue.claim_next(db)
        second = task_queue.claim_next(db)
        third = task_queue.claim_next(db)
    # 高优先级（数值小）先被领取，与投递顺序无关
    assert first == high_job
    assert second == low_job
    assert third is None


def test_claim_next_skips_jobs_that_are_not_due_yet():
    from datetime import timedelta

    from app.models import PipelineJob

    with _db() as db:
        run = _mk_run(db, subject="队列-未到期")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id)
        job = db.query(PipelineJob).filter(PipelineJob.id == res["job_id"]).first()
        job.available_at = job.available_at + timedelta(seconds=600)   # 退避中
        db.commit()
        claimed = task_queue.claim_next(db)
    assert claimed is None


def test_cancel_queued_job_is_immediate():
    with _db() as db:
        run = _mk_run(db, subject="队列-取消排队")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id)
        out = task_queue.cancel(db, res["job_id"])
        stats = task_queue.queue_stats(db)
    assert out["ok"] and out["immediate"] is True
    assert stats["counts"]["cancelled"] >= 1


def test_cancel_running_job_is_deferred_not_instant():
    """运行中的作业不能被瞬间杀掉：LLM 调用与浏览器步骤都是原子的。"""
    from app.models import PipelineJob

    with _db() as db:
        run = _mk_run(db, subject="队列-取消运行中")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id)
        job = db.query(PipelineJob).filter(PipelineJob.id == res["job_id"]).first()
        job.status = "running"
        db.commit()
        out = task_queue.cancel(db, res["job_id"])
        db.refresh(job)
        still_running = job.status
        flag = job.cancel_requested
    assert out["ok"] and out["immediate"] is False
    assert still_running == "running"
    assert flag == 1


def test_cancel_finished_job_is_rejected():
    from app.models import PipelineJob

    with _db() as db:
        run = _mk_run(db, subject="队列-取消已完成")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id)
        job = db.query(PipelineJob).filter(PipelineJob.id == res["job_id"]).first()
        job.status = "done"
        db.commit()
        out = task_queue.cancel(db, res["job_id"])
    assert out["ok"] is False


def test_retry_resets_attempts_and_clears_error():
    from app.models import PipelineJob

    with _db() as db:
        run = _mk_run(db, subject="队列-重试")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id)
        job = db.query(PipelineJob).filter(PipelineJob.id == res["job_id"]).first()
        job.status = "failed"
        job.attempts = 2
        job.error = "上游 429"
        job.cancel_requested = 1
        db.commit()
        out = task_queue.retry(db, res["job_id"])
        db.refresh(job)
        after = (job.status, job.attempts, job.error, job.cancel_requested)
    assert out["ok"] is True
    # 手动重试必须重新给足次数，否则重试一次仍会立刻彻底失败
    assert after == ("queued", 0, "", 0)


def test_retry_rejects_active_job():
    with _db() as db:
        run = _mk_run(db, subject="队列-重试活跃")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id)
        out = task_queue.retry(db, res["job_id"])
    assert out["ok"] is False


def test_reap_orphans_requeues_interrupted_jobs():
    """进程中断留下的 running 作业必须回到队列，否则那条运行再也不会被推进。"""
    from app.models import PipelineJob

    with _db() as db:
        run = _mk_run(db, subject="队列-孤儿回收")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id)
        job = db.query(PipelineJob).filter(PipelineJob.id == res["job_id"]).first()
        job.status = "running"
        job.worker = "dead-process"
        db.commit()
        n = task_queue.reap_orphans(db)
        db.refresh(job)
        after = (job.status, job.worker)
        assert "断点续跑" in job.error
    assert n >= 1
    assert after == ("queued", "")


def test_backoff_grows_and_is_capped():
    values = [task_queue.backoff_seconds(n) for n in range(1, 8)]
    assert values == sorted(values)
    assert values[-1] == task_queue.BACKOFF_CAP_SECONDS
    assert task_queue.backoff_seconds(1) == task_queue.BACKOFF_BASE_SECONDS


def test_execute_job_marks_failed_when_run_did_not_succeed(monkeypatch):
    """编排器正常返回 ≠ 作业成功：失败是写进 run.status 的，队列必须回查终态。"""
    from app.models import PipelineJob, ProductionTask

    def fake_orchestrate(run_id):
        with _db() as db:
            run = db.query(ProductionTask).filter(ProductionTask.id == run_id).first()
            run.status = "failed"
            run.error = "步骤⑤失败：未抽取到终稿"
            db.commit()

    monkeypatch.setattr(task_queue, "orchestrate_run", fake_orchestrate)
    with _db() as db:
        run = _mk_run(db, subject="队列-失败判定")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id, max_attempts=1)
    outcome = task_queue.execute_job(res["job_id"])
    with _db() as db:
        job = db.query(PipelineJob).filter(PipelineJob.id == res["job_id"]).first()
        final = (job.status, job.error, job.finished_at is not None)
    assert outcome == "failed"
    assert final[0] == "failed"
    assert "未抽取到终稿" in final[1]
    assert final[2] is True


def test_execute_job_requeues_with_backoff_on_first_failure(monkeypatch):
    from app.models import PipelineJob, ProductionTask

    def fake_orchestrate(run_id):
        with _db() as db:
            run = db.query(ProductionTask).filter(ProductionTask.id == run_id).first()
            run.status = "failed"
            run.error = "网络抖动"
            db.commit()

    monkeypatch.setattr(task_queue, "orchestrate_run", fake_orchestrate)
    with _db() as db:
        run = _mk_run(db, subject="队列-退避重试")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id, max_attempts=2)
    outcome = task_queue.execute_job(res["job_id"])
    with _db() as db:
        job = db.query(PipelineJob).filter(PipelineJob.id == res["job_id"]).first()
        state = (job.status, job.attempts, job.available_at is not None)
    assert outcome == "retry_queued"
    assert state[0] == "queued" and state[1] == 1 and state[2] is True


def test_execute_job_marks_done_on_await_confirm(monkeypatch):
    """``await_confirm`` 是正常成功终点（内容就绪、等人点确认），不能算失败。"""
    from app.models import PipelineJob, ProductionTask

    def fake_orchestrate(run_id):
        with _db() as db:
            run = db.query(ProductionTask).filter(ProductionTask.id == run_id).first()
            run.status = "await_confirm"
            run.error = ""
            db.commit()

    monkeypatch.setattr(task_queue, "orchestrate_run", fake_orchestrate)
    with _db() as db:
        run = _mk_run(db, subject="队列-成功")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id)
    outcome = task_queue.execute_job(res["job_id"])
    with _db() as db:
        job = db.query(PipelineJob).filter(PipelineJob.id == res["job_id"]).first()
        state = (job.status, job.error)
    assert outcome == "done"
    assert state == ("done", "")


def test_execute_job_respects_cancel_requested_before_start(monkeypatch):
    from app.models import PipelineJob

    called = []
    monkeypatch.setattr(task_queue, "orchestrate_run", lambda rid: called.append(rid))
    with _db() as db:
        run = _mk_run(db, subject="队列-开跑前取消")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id)
        job = db.query(PipelineJob).filter(PipelineJob.id == res["job_id"]).first()
        job.cancel_requested = 1
        db.commit()
    outcome = task_queue.execute_job(res["job_id"])
    with _db() as db:
        job = db.query(PipelineJob).filter(PipelineJob.id == res["job_id"]).first()
        status = job.status
    assert outcome == "cancelled"
    assert status == "cancelled"
    assert called == []      # 取消生效后绝不能真的开跑


def test_execute_job_survives_orchestrator_exception(monkeypatch):
    """编排器抛异常也必须被兜住并落到 failed，不能把异常抛回调度线程。"""
    from app.models import PipelineJob

    def boom(run_id):
        raise RuntimeError("浏览器启动失败")

    monkeypatch.setattr(task_queue, "orchestrate_run", boom)
    with _db() as db:
        run = _mk_run(db, subject="队列-异常兜底")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id, max_attempts=1)
    outcome = task_queue.execute_job(res["job_id"])
    with _db() as db:
        job = db.query(PipelineJob).filter(PipelineJob.id == res["job_id"]).first()
        err = job.error
    assert outcome == "failed"
    assert "浏览器启动失败" in err


def test_dispatcher_enforces_concurrency_limit(monkeypatch):
    """并发上限是整个队列存在的理由，必须真的生效。"""
    gate = threading.Event()
    started = []

    def slow_job(job_id, worker=""):
        started.append(job_id)
        gate.wait(timeout=5)
        return "done"

    monkeypatch.setattr(task_queue, "execute_job", slow_job)
    with _db() as db:
        runs = [_mk_run(db, subject=f"队列-并发{i}") for i in range(3)]
        for run in runs:
            task_queue.enqueue(db, INDUSTRY_ID, run.id)

    disp = task_queue.Dispatcher(concurrency=1, poll_seconds=0.05)
    disp.start(reap=False)
    try:
        deadline = time.time() + 3
        while len(started) < 1 and time.time() < deadline:
            time.sleep(0.05)
        assert len(started) == 1, "应当只启动 1 条（并发上限 1）"
        time.sleep(0.3)
        assert len(started) == 1, "并发上限被突破了"

        # 释放闸门后，剩下的作业应当被继续领取（调度线程必须持续工作）
        gate.set()
        deadline = time.time() + 5
        while len(started) < 3 and time.time() < deadline:
            time.sleep(0.1)
        assert len(started) == 3, "闸门释放后应当继续领取后续作业"
    finally:
        gate.set()
        disp.stop(wait=True)


def test_dispatcher_reports_status():
    disp = task_queue.Dispatcher(concurrency=3, poll_seconds=2.0)
    st = disp.status()
    assert st["running"] is False
    assert st["concurrency"] == 3
    assert st["poll_seconds"] == 2.0
    assert st["inflight"] == []


def test_dispatcher_runs_a_real_mock_pipeline_to_completion():
    """端到端：真起一个 Dispatcher，跑一条真实 mock 流水线直到终态。

    这是阶段 C 唯一能证明「整条链真的通」的用例 —— 上面的用例都用假函数
    替换了 ``orchestrate_run``，只验证了状态映射，证明不了队列真的能驱动流水线。
    顺带覆盖断点续跑所需的产物落库（final_content / 步骤行状态）。
    """
    from app.models import BrowserStudioStep, PipelineJob, ProductionTask

    with _db() as db:
        run = _mk_run(db, subject="端到端-mock流水线", platform="sohu")
        run.ai_engine = "mock"
        run.mock_doubao = 1
        run.publish_mode = "platform"
        run.output_format = "markdown"
        # 只跑 1 轮整改，控制用例耗时
        run.pipeline_spec = pipeline_svc.dump_spec(
            {"steps": pipeline_svc.STEP_ORDER, "max_revise_rounds": 1}
        )
        db.commit()
        run_id = run.id
        job_id = task_queue.enqueue(db, INDUSTRY_ID, run_id, max_attempts=1)["job_id"]

    disp = task_queue.Dispatcher(concurrency=1, poll_seconds=0.2)
    disp.start(reap=False)
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            with _db() as db:
                job = db.query(PipelineJob).filter(PipelineJob.id == job_id).first()
                terminal = job.status in ("done", "failed", "cancelled")
            if terminal:
                break
            time.sleep(0.3)
    finally:
        disp.stop(wait=True)

    with _db() as db:
        job = db.query(PipelineJob).filter(PipelineJob.id == job_id).first()
        run = db.query(ProductionTask).filter(ProductionTask.id == run_id).first()
        steps = {
            s.step_key: s.status
            for s in db.query(BrowserStudioStep).filter(BrowserStudioStep.run_id == run_id).all()
        }
        outcome = (job.status, job.error, run.status, run.final_content or "", run.geo_score)

    assert outcome[0] == "done", f"队列未能驱动流水线跑完：{outcome[1]}"
    assert outcome[2] == "await_confirm"
    assert outcome[3].strip(), "终稿为空 —— 产物没有落库，断点续跑就无从复用"
    assert steps.get("geo") == "done"
    assert steps.get("review") == "done"
    assert outcome[4] > 0, "GEO 评分未写入"


def test_resume_reuses_artifacts_after_failure(monkeypatch):
    """续跑必须复用产物：第二次执行时已完成的步骤不能再调用引擎。"""
    from app.models import PipelineJob, ProductionTask

    calls = []

    def fake_orchestrate(run_id):
        """模拟编排器：按 pipeline.plan 的复用清单跳过已完成的步骤。"""
        with _db() as db:
            run = db.query(ProductionTask).filter(ProductionTask.id == run_id).first()
            plan = pipeline_svc.plan(db, run)
            calls.append(list(plan["done"]))
            run.status = "failed"
            run.error = "第 1 次尝试失败"
            db.commit()

    monkeypatch.setattr(task_queue, "orchestrate_run", fake_orchestrate)
    with _db() as db:
        run = _mk_run(db, subject="续跑-复用产物")
        _mk_steps(db, run.id, dict.fromkeys(pipeline_svc.STEP_ORDER[:6], "done"))
        _fill_artifacts(db, run, upto="geo")
        run.status = "failed"
        db.commit()
        job_id = task_queue.enqueue(db, INDUSTRY_ID, run.id, max_attempts=1)["job_id"]

    task_queue.execute_job(job_id)
    with _db() as db:
        job = db.query(PipelineJob).filter(PipelineJob.id == job_id).first()
        status = job.status
    # 第一次执行时，队列看到的复用清单已经是 5 步 —— 说明产物真的被复用了
    assert calls and calls[0] == ["clarify", "outline", "draft", "depolish", "geo"]
    assert status == "failed"


def test_queue_stats_counts_by_status():
    with _db() as db:
        run = _mk_run(db, subject="队列-统计")
        task_queue.enqueue(db, INDUSTRY_ID, run.id)
        stats = task_queue.queue_stats(db)
    assert set(stats["labels"]) == {"queued", "running", "done", "failed", "cancelled"}
    assert stats["counts"]["queued"] >= 1
    assert stats["active"] == stats["counts"]["queued"] + stats["counts"]["running"]


def test_list_jobs_puts_active_first_and_joins_run():
    with _db() as db:
        run = _mk_run(db, subject="队列-列表")
        res = task_queue.enqueue(db, INDUSTRY_ID, run.id)
        jobs = task_queue.list_jobs(db, INDUSTRY_ID, limit=50)
    mine = [j for j in jobs if j["id"] == res["job_id"]]
    assert len(mine) == 1
    assert mine[0]["run_name"].startswith("队列-列表")
    assert mine[0]["run_platform"] == "sohu"
    assert mine[0]["status_label"] == "排队中"


# ============================================================
#  C3：批量生产
# ============================================================
def test_expand_builds_cross_product():
    with _db() as db:
        plan = batch_svc.expand(db, {
            "industry_id": INDUSTRY_ID,
            "subjects": ["选题A", "选题B"],
            "platforms": ["sohu", "zhihu", "official"],
            "skip_duplicates": False,
        })
    assert plan["will_create"] == 6
    assert plan["ok"] is True
    formats = {(i["platform"], i["output_format"]) for i in plan["items"]}
    assert ("official", "mdx") in formats
    assert ("sohu", "markdown") in formats


def test_expand_cleans_subjects_and_platforms():
    with _db() as db:
        plan = batch_svc.expand(db, {
            "industry_id": INDUSTRY_ID,
            "subjects": "  选题A \n\n 选题A\n选题B  \n",
            "platforms": ["sohu", "sohu", ""],
            "skip_duplicates": False,
        })
    assert plan["subjects"] == ["选题A", "选题B"]      # 去空白、去空行、去重
    assert plan["platforms"] == ["sohu"]
    assert plan["will_create"] == 2


def test_expand_defaults_platform_to_sohu():
    with _db() as db:
        plan = batch_svc.expand(db, {"industry_id": INDUSTRY_ID, "subjects": "只有选题"})
    assert plan["platforms"] == ["sohu"]


def test_expand_flags_duplicates_but_not_failed_runs():
    with _db() as db:
        _mk_run(db, subject="重复选题", platform="sohu", status="await_confirm")
        _mk_run(db, subject="失败选题", platform="sohu", status="failed")
        plan = batch_svc.expand(db, {
            "industry_id": INDUSTRY_ID,
            "subjects": ["重复选题", "失败选题", "全新选题"],
            "platforms": ["sohu"],
        })
    by_subject = {i["subject"]: i for i in plan["items"]}
    assert by_subject["重复选题"]["duplicate"] is True
    assert by_subject["重复选题"]["duplicate_run_id"] > 0
    # 失败/取消的运行不算「已经做过」，允许重投
    assert by_subject["失败选题"]["duplicate"] is False
    assert by_subject["全新选题"]["duplicate"] is False
    assert plan["will_skip"] == 1 and plan["will_create"] == 2


def test_expand_can_disable_dedup():
    with _db() as db:
        _mk_run(db, subject="重复选题2", platform="sohu", status="await_confirm")
        plan = batch_svc.expand(db, {
            "industry_id": INDUSTRY_ID, "subjects": ["重复选题2"],
            "platforms": ["sohu"], "skip_duplicates": False,
        })
    assert plan["will_create"] == 1 and plan["will_skip"] == 0


def test_expand_truncates_at_batch_limit():
    with _db() as db:
        plan = batch_svc.expand(db, {
            "industry_id": INDUSTRY_ID,
            "subjects": [f"批量上限选题{i}" for i in range(batch_svc.MAX_BATCH + 10)],
            "platforms": ["sohu"],
            "skip_duplicates": False,
        })
    assert len(plan["items"]) == batch_svc.MAX_BATCH
    assert plan["truncated"] is True
    assert any("上限" in p for p in plan["problems"])


def test_expand_reports_problems_for_empty_subjects():
    with _db() as db:
        plan = batch_svc.expand(db, {"industry_id": INDUSTRY_ID, "subjects": "  \n \n"})
    assert plan["ok"] is False
    assert any("选题为空" in p for p in plan["problems"])


def test_expand_reports_unknown_industry():
    with _db() as db:
        plan = batch_svc.expand(db, {"industry_id": 99999999, "subjects": "选题"})
    assert plan["ok"] is False
    assert any("不存在" in p for p in plan["problems"])


def test_create_batch_creates_runs_and_jobs_sharing_batch_id():
    from app.models import PipelineJob, ProductionTask

    with _db() as db:
        res = batch_svc.create(db, {
            "industry_id": INDUSTRY_ID,
            "subjects": ["批量创建A", "批量创建B"],
            "platforms": ["sohu", "zhihu"],
            "skip_duplicates": False,
            "priority": 4,
            "pipeline_spec": {"steps": ["connect", "outline", "draft", "geo", "review", "confirm"],
                              "max_revise_rounds": 1},
        })
        assert res["ok"] is True
        runs = db.query(ProductionTask).filter(ProductionTask.batch_id == res["batch_id"]).all()
        jobs = db.query(PipelineJob).filter(PipelineJob.batch_id == res["batch_id"]).all()
    assert res["created_count"] == 4
    assert len(runs) == 4 and len(jobs) == 4
    assert all(r.mode == "auto" for r in runs)
    assert all(j.status == "queued" and j.priority == 4 for j in jobs)
    # 批次规格要落到每条运行上，否则执行时又回到「全步骤默认」
    spec = json.loads(runs[0].pipeline_spec)
    assert spec["max_revise_rounds"] == 1
    assert "clarify" not in spec["steps"]


def test_create_batch_skips_duplicates_and_reports_them():
    with _db() as db:
        _mk_run(db, subject="批次去重选题", platform="sohu", status="await_confirm")
        res = batch_svc.create(db, {
            "industry_id": INDUSTRY_ID,
            "subjects": ["批次去重选题", "批次新选题"],
            "platforms": ["sohu"],
        })
    assert res["ok"] is True
    assert res["created_count"] == 1
    assert res["skipped_count"] == 1
    assert res["skipped"][0]["subject"] == "批次去重选题"
    assert res["skipped"][0]["reason"]


def test_create_batch_rejects_invalid_payload():
    with _db() as db:
        res = batch_svc.create(db, {"industry_id": INDUSTRY_ID, "subjects": ""})
    assert res["ok"] is False
    assert "选题为空" in res["error"]


def test_batch_progress_aggregates():
    with _db() as db:
        created = batch_svc.create(db, {
            "industry_id": INDUSTRY_ID,
            "subjects": ["进度选题A", "进度选题B"],
            "platforms": ["sohu"],
            "skip_duplicates": False,
        })
        bid = created["batch_id"]
        from app.models import PipelineJob

        jobs = db.query(PipelineJob).filter(PipelineJob.batch_id == bid).order_by(
            PipelineJob.id.asc()).all()
        jobs[0].status = "done"
        jobs[1].status = "failed"
        db.commit()
        progress = task_queue.batch_progress(db, bid)
        summary = batch_svc.batch_summary(db, bid)
    assert progress["total"] == 2
    assert progress["counts"]["done"] == 1 and progress["counts"]["failed"] == 1
    assert progress["progress"] == 1.0
    assert len(summary["runs"]) == 2
    assert all("name" in r for r in summary["runs"])


def test_enqueue_batch_requeues_only_unfinished():
    from app.models import PipelineJob, ProductionTask

    with _db() as db:
        created = batch_svc.create(db, {
            "industry_id": INDUSTRY_ID,
            "subjects": ["重投选题A", "重投选题B", "重投选题C"],
            "platforms": ["sohu"],
            "skip_duplicates": False,
        })
        bid = created["batch_id"]
        jobs = db.query(PipelineJob).filter(PipelineJob.batch_id == bid).order_by(
            PipelineJob.id.asc()).all()
        jobs[0].status = "failed"
        jobs[1].status = "failed"
        jobs[2].status = "done"
        for job in jobs:
            db.commit()
            run = db.query(ProductionTask).filter(ProductionTask.id == job.run_id).first()
            run.status = {"failed": "failed", "done": "await_confirm"}[job.status]
        db.commit()
        out = batch_svc.enqueue_batch(db, bid)
        db.refresh(jobs[0])
        after = [j.status for j in db.query(PipelineJob).filter(
            PipelineJob.batch_id == bid).order_by(PipelineJob.id.asc()).all()]
    assert out["ok"] is True
    # 失败的重新排队，已完成的（await_confirm）跳过 —— 不重复烧 token
    assert len(out["queued"]) == 2
    assert len(out["skipped_finished"]) == 1
    assert after == ["queued", "queued", "done"]


def test_list_batches_returns_recent_first():
    with _db() as db:
        first = batch_svc.create(db, {"industry_id": INDUSTRY_ID, "subjects": ["批次序A"],
                                     "platforms": ["sohu"], "skip_duplicates": False})
        second = batch_svc.create(db, {"industry_id": INDUSTRY_ID, "subjects": ["批次序B"],
                                      "platforms": ["sohu"], "skip_duplicates": False})
        listed = batch_svc.list_batches(db, INDUSTRY_ID, limit=5)
    ids = [b["batch_id"] for b in listed]
    assert second["batch_id"] in ids and first["batch_id"] in ids
    assert ids.index(second["batch_id"]) < ids.index(first["batch_id"])


# ============================================================
#  C4：路由
# ============================================================
def test_api_pipeline_steps(client, auth_headers):
    resp = client.get("/api/pipeline/steps", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert [s["key"] for s in data["steps"]] == pipeline_svc.STEP_ORDER
    assert data["optional"] == ["clarify", "depolish", "revise"]
    assert data["default_spec"]["steps"] == pipeline_svc.STEP_ORDER


def test_api_spec_put_echoes_corrections(client, auth_headers):
    with _db() as db:
        run = _mk_run(db, subject="接口-规格")
        run_id = run.id
    resp = client.put("/api/pipeline/spec", headers=auth_headers, json={
        "run_id": run_id,
        "steps": ["outline", "draft", "bogus"],
        "max_revise_rounds": 99,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "bogus" in " ".join(data["notes"])
    assert data["spec"]["max_revise_rounds"] == pipeline_svc.MAX_REVISE_ROUNDS_CAP
    assert "geo" in data["spec"]["steps"]      # 必开步骤被补回


def test_api_spec_rejects_unknown_run(client, auth_headers):
    resp = client.get("/api/pipeline/spec", headers=auth_headers, params={"run_id": 99999999})
    assert resp.status_code == 404


def test_api_queue_stats_and_list(client, auth_headers):
    with _db() as db:
        run = _mk_run(db, subject="接口-队列")
        task_queue.enqueue(db, INDUSTRY_ID, run.id)
    resp = client.get("/api/pipeline/queue/stats", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["counts"]["queued"] >= 1
    # 调度线程在测试里是关的，状态应如实反映「未启动」
    assert resp.json()["data"]["dispatcher"]["running"] is False

    resp = client.get("/api/pipeline/queue", headers=auth_headers,
                      params={"industry_id": INDUSTRY_ID})
    assert resp.status_code == 200
    assert any("run_name" in j for j in resp.json()["data"]["jobs"])


def test_api_queue_rejects_unknown_status(client, auth_headers):
    resp = client.get("/api/pipeline/queue", headers=auth_headers, params={"status": "bogus"})
    assert resp.status_code == 400


def test_api_cancel_and_retry_job(client, auth_headers):
    with _db() as db:
        run = _mk_run(db, subject="接口-取消重试")
        job_id = task_queue.enqueue(db, INDUSTRY_ID, run.id)["job_id"]
    cancelled = client.post(f"/api/pipeline/queue/{job_id}/cancel", headers=auth_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["immediate"] is True      # 排队中的取消立刻生效

    retried = client.post(f"/api/pipeline/queue/{job_id}/retry", headers=auth_headers)
    assert retried.status_code == 200
    assert retried.json()["data"]["status"] == "queued"

    # 已回到排队中，可以再次取消
    again = client.post(f"/api/pipeline/queue/{job_id}/cancel", headers=auth_headers)
    assert again.status_code == 200
    assert again.json()["data"]["immediate"] is True


def test_api_batch_preview_does_not_persist(client, auth_headers):
    from app.models import ProductionTask

    with _db() as db:
        before = db.query(ProductionTask).count()
    resp = client.post("/api/pipeline/batch/preview", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID,
        "subjects": ["预览选题X", "预览选题Y"],
        "platforms": ["sohu", "zhihu"],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["will_create"] == 4
    with _db() as db:
        after = db.query(ProductionTask).count()
    assert after == before, "预览绝不能落库"


def test_api_batch_create_and_detail(client, auth_headers):
    resp = client.post("/api/pipeline/batch", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID,
        "subjects": ["接口批量A", "接口批量B"],
        "platforms": ["sohu"],
        "priority": 3,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["created_count"] == 2

    detail = client.get(f"/api/pipeline/batches/{data['batch_id']}", headers=auth_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["total"] == 2
    assert len(detail.json()["data"]["runs"]) == 2

    listed = client.get("/api/pipeline/batches", headers=auth_headers,
                        params={"industry_id": INDUSTRY_ID})
    assert data["batch_id"] in [b["batch_id"] for b in listed.json()["data"]]


def test_api_batch_detail_404_for_unknown_batch(client, auth_headers):
    resp = client.get("/api/pipeline/batches/B20990101-zzzzzz", headers=auth_headers)
    assert resp.status_code == 404


def test_api_batch_rejects_empty_subjects(client, auth_headers):
    resp = client.post("/api/pipeline/batch", headers=auth_headers, json={
        "industry_id": INDUSTRY_ID, "subjects": "   ",
    })
    assert resp.status_code == 400


def test_api_resume_reports_reused_and_reset_steps(client, auth_headers):
    with _db() as db:
        run = _mk_run(db, subject="接口-续跑")
        _mk_steps(db, run.id, dict.fromkeys(pipeline_svc.STEP_ORDER[:6], "done"))
        _fill_artifacts(db, run, upto="geo")
        run_id = run.id
    resp = client.post(f"/api/pipeline/run/{run_id}/resume", headers=auth_headers, json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["resumed_from"] == "review"
    assert "geo" in data["reused"]
    assert "review" in data["reset"]
    assert data["job"]["created"] is True


def test_api_resume_rejects_step_disabled_by_spec(client, auth_headers):
    with _db() as db:
        spec, _ = pipeline_svc.validate_spec(
            {"steps": ["connect", "outline", "draft", "geo", "review", "confirm"]}
        )
        run = _mk_run(db, subject="接口-续跑裁剪", spec=spec)
        run_id = run.id
    resp = client.post(f"/api/pipeline/run/{run_id}/resume", headers=auth_headers,
                       json={"from_step": "clarify"})
    assert resp.status_code == 400
    assert "关闭" in resp.json()["detail"]


def test_api_resume_rejects_unknown_step(client, auth_headers):
    with _db() as db:
        run_id = _mk_run(db, subject="接口-续跑未知步").id
    resp = client.post(f"/api/pipeline/run/{run_id}/resume", headers=auth_headers,
                       json={"from_step": "nope"})
    assert resp.status_code == 400


def test_api_run_queue_state_includes_plan(client, auth_headers):
    with _db() as db:
        run = _mk_run(db, subject="接口-运行队列态")
        task_queue.enqueue(db, INDUSTRY_ID, run.id)
        run_id = run.id
    resp = client.get(f"/api/pipeline/run/{run_id}/queue", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["jobs"][0]["status"] == "queued"
    assert "plan" in data
    # 全新运行的「从哪继续」是①b（①连接必然重跑、不算可复用产物），
    # 而执行器第一个碰到的是①连接 —— 两者刻意分开，界面展示前者。
    assert data["plan"]["next_key"] == "clarify"
    assert data["plan"]["starts_at"] == "connect"


def test_api_retry_failed_bulk(client, auth_headers):
    from app.models import PipelineJob

    with _db() as db:
        runs = [_mk_run(db, subject=f"接口-批量重试{i}") for i in range(3)]
        job_ids = [task_queue.enqueue(db, INDUSTRY_ID, r.id)["job_id"] for r in runs]
        for jid in job_ids:
            job = db.query(PipelineJob).filter(PipelineJob.id == jid).first()
            job.status = "failed"
            job.error = "上游限流"
        db.commit()
    resp = client.post("/api/pipeline/queue/retry-failed", headers=auth_headers,
                       params={"industry_id": INDUSTRY_ID})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["count"] >= 3
    with _db() as db:
        states = [db.query(PipelineJob).filter(PipelineJob.id == jid).first().status
                  for jid in job_ids]
    assert states == ["queued"] * 3
