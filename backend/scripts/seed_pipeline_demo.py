# -*- coding: utf-8 -*-
"""生产流水线（阶段 C）本地验收演示数据（幂等）。

造一个「看起来像真在用」的批次：3 个选题 × 2 个平台 = 6 条运行，
并把队列态刻意摊开到各种状态上 —— 排队中 / 退避重试 / 执行中 / 已完成 / 失败，
这样「执行队列」「批次进度」「断点续跑」三块一眼就能看到东西。

用法：
    cd backend
    venv/Scripts/python.exe scripts/seed_pipeline_demo.py [industry_id]

重复执行安全：已存在演示批次时直接跳过。
"""
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, now  # noqa: E402
from app.models import BrowserStudioStep, Industry, PipelineJob, ProductionTask  # noqa: E402
from app.services import batch as batch_svc  # noqa: E402
from app.services import pipeline as pipeline_svc  # noqa: E402

PREFIX = "【演示】"
SUBJECTS = [
    f"{PREFIX}真空泵选型要注意什么",
    f"{PREFIX}食品厂为什么需要无油真空泵",
    f"{PREFIX}真空泵保养周期怎么定",
]
PLATFORMS = ["sohu", "zhihu"]


def _ensure_steps(db, run, statuses):
    """按编排规格建步骤行并设置状态（模拟「已经跑到第 N 步」）。"""
    spec = pipeline_svc.spec_of(run)
    for no, key in enumerate(spec["steps"], start=1):
        db.add(BrowserStudioStep(
            run_id=run.id, step_no=no, step_key=key, title=key,
            status=statuses.get(key, "pending"),
        ))
    db.commit()


def main() -> None:
    industry_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    with SessionLocal() as db:
        if not industry_id:
            ind = db.query(Industry).filter(Industry.is_deleted == 0).order_by(Industry.id).first()
            if ind is None:
                print("没有可用行业，请先启动一次服务以完成初始化")
                return
            industry_id = ind.id

        existing = db.query(ProductionTask).filter(
            ProductionTask.is_deleted == 0,
            ProductionTask.subject.like(PREFIX + "%"),
        ).first()
        if existing is not None:
            print(f"演示批次已存在（运行 #{existing.id}，批次 {existing.batch_id or '—'}），跳过")
            return

        result = batch_svc.create(db, {
            "industry_id": industry_id,
            "subjects": SUBJECTS,
            "platforms": PLATFORMS,
            "skip_duplicates": False,
            "priority": 5,
            "max_attempts": 2,
            "ai_engine": "mock",
            "pipeline_spec": {"steps": pipeline_svc.STEP_ORDER, "max_revise_rounds": 2},
        })
        if not result.get("ok"):
            print("创建演示批次失败：", result.get("error"))
            return
        batch_id = result["batch_id"]

        runs = (
            db.query(ProductionTask)
            .filter(ProductionTask.batch_id == batch_id)
            .order_by(ProductionTask.id.asc())
            .all()
        )
        jobs = {
            j.run_id: j
            for j in db.query(PipelineJob).filter(PipelineJob.batch_id == batch_id).all()
        }

        # —— 运行①：已跑完，等待人工确认（GEO 分数不错）——
        _finish_ok(db, runs[0], jobs[runs[0].id], score=86, steps_upto="confirm",
                   publish_url="https://demo.zhaozhenkong.com/case/vacuum-pump-selection")

        # —— 运行②：已跑完，GEO 分数偏低 ——
        _finish_ok(db, runs[1], jobs[runs[1].id], score=64, steps_upto="confirm")

        # —— 运行③：失败（两次尝试用尽），停在终稿抽取 ——
        r3 = runs[2]
        r3.status = "failed"
        r3.error = "步骤⑤失败：未抽取到终稿（AI 未遵守输出契约）"
        r3.outline_content = "一、为什么选型容易踩坑\n二、三个必须确认的参数\n三、常见误区"
        r3.draft_content = "（初稿正文，约 1200 字）"
        _ensure_steps(db, r3, {
            "connect": "done", "clarify": "done", "outline": "done",
            "draft": "done", "depolish": "done", "geo": "failed",
        })
        j3 = jobs[r3.id]
        j3.status = "failed"
        j3.attempts = 2
        j3.max_attempts = 2
        j3.error = r3.error
        j3.finished_at = now()
        db.commit()

        # —— 运行④：正在执行（已跑完①②③④，断点在第⑤步）——
        r4 = runs[3]
        r4.status = "running"
        r4.clarified_brief = "选题角：从食品厂卫生要求切入；目标读者：设备采购负责人"
        r4.outline_content = "一、食品厂的卫生红线\n二、有油泵的污染风险\n三、无油泵的选型要点"
        r4.draft_content = "（初稿正文，约 1400 字）"
        r4.rewrite_content = "（去 AI 味后的精修稿，约 1450 字）"
        _ensure_steps(db, r4, {
            "connect": "done", "clarify": "done", "outline": "done",
            "draft": "done", "depolish": "done", "geo": "running",
        })
        j4 = jobs[r4.id]
        j4.status = "running"
        j4.attempts = 1
        j4.worker = "dispatcher-demo"
        j4.started_at = now() - timedelta(minutes=3)
        db.commit()

        # —— 运行⑤：第一次失败，正在退避等待（这一条最能说明「自动重试」）——
        r5 = runs[4]
        r5.status = "created"
        r5.error = "DeepSeek 请求超时"
        _ensure_steps(db, r5, {"connect": "done", "clarify": "done"})
        r5.clarified_brief = "选题角：保养周期的判断依据；目标读者：设备主管"
        j5 = jobs[r5.id]
        j5.status = "queued"
        j5.attempts = 1
        j5.available_at = now() + timedelta(seconds=45)
        j5.error = "DeepSeek 请求超时（第 1 次失败，稍后自动重试）"
        db.commit()

        # —— 运行⑥：普通排队中（全新，无任何产物）——
        # 刻意把 available_at 推后：调度线程在跑，不定个到期时间的话它会在
        # 一两秒内把这条领走，演示数据就看不到「排队中」这个状态了。
        j6 = jobs[runs[5].id]
        j6.status = "queued"
        j6.attempts = 0
        j6.available_at = now() + timedelta(seconds=120)
        db.commit()

        counts = {}
        for j in db.query(PipelineJob).filter(PipelineJob.batch_id == batch_id).all():
            counts[j.status] = counts.get(j.status, 0) + 1
        print(f"演示批次已创建：{batch_id}（行业 {industry_id}）")
        print("  运行数 6｜队列态：", json.dumps(counts, ensure_ascii=False))
        print("  运行①/② 已完成（等待确认，GEO 86 / 64）")
        print("  运行③ 失败（2/2 次用尽，停在步骤⑤）")
        print("  运行④ 执行中（①②③④ 产物就绪，断点在第⑤步）")
        print("  运行⑤ 退避中（第 1 次失败，45 秒后自动重试）")
        print("  运行⑥ 排队中（全新）")


def _finish_ok(db, run, job, score, steps_upto, publish_url=""):
    """把一条运行标成「已跑到确认闸门」。"""
    run.status = "await_confirm"
    run.error = ""
    run.geo_score = score
    run.clarified_brief = "选题角与目标读者已明确"
    run.outline_content = "一、行业现状\n二、核心参数\n三、选型建议\n四、常见问题"
    run.draft_content = "（初稿正文，约 1500 字）"
    run.rewrite_content = "（去 AI 味后的精修稿，约 1520 字）"
    run.final_title = (run.subject or "").replace(PREFIX, "")
    run.final_content = "（终稿正文，约 1600 字，含规格表与实测数据）"
    run.review_result = json.dumps(
        {"gate_pass": True, "geo_score": score, "issues": []}, ensure_ascii=False)
    run.revise_rounds = json.dumps(
        [{"round": 1, "geo_score": score, "gate_pass": True}], ensure_ascii=False)
    if publish_url:
        run.publish_url = publish_url
    _ensure_steps(db, run, dict.fromkeys(pipeline_svc.STEP_ORDER, "done"))
    job.status = "done"
    job.attempts = 1
    job.error = ""
    job.started_at = now() - timedelta(minutes=20)
    job.finished_at = now() - timedelta(minutes=12)
    db.commit()


if __name__ == "__main__":
    main()
