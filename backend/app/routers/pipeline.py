# -*- coding: utf-8 -*-
"""生产流水线路由（阶段 C）

对外暴露四组能力：
  1. **编排规格**：读/写某条运行「启用哪些步骤、最多整改几轮」；
  2. **断点续跑**：从第一个未完成的步骤继续，而不是从①重跑；
  3. **队列运维**：总览、取消、重试、批量重试失败；
  4. **批量生产**：预览 → 创建 → 看批次进度 → 整批重投。

设计约定
--------
- 所有写操作都返回**规整后的结果**（例如 PUT 规格会回显被修正之处），
  而不是只回一个 ok —— 前端才有机会把「你填的值被改成了什么」如实告诉用户。
- 队列状态是**运行态镜像**：``production_task.status`` 描述内容走到哪，
  ``pipeline_job.status`` 描述调度到哪，两者会同时为真却不同（见 models.PipelineJob 注释）。
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PipelineJob, ProductionTask
from ..services import batch as batch_svc
from ..services import pipeline as pipeline_svc
from ..services import task_queue
from ..services.doubao_studio import get_auto_run

router = APIRouter(prefix="/api/pipeline", tags=["生产流水线"])


# ============================================================
#  请求体
# ============================================================
class SpecIn(BaseModel):
    run_id: int
    steps: Optional[List[str]] = None
    max_revise_rounds: Optional[int] = None


class ResumeIn(BaseModel):
    from_step: str = ""      # 留空=自动从断点续跑；填了=从该步强制重做
    priority: int = 3        # 人工触发的续跑给较高优先级（数值越小越先执行）


class JobActionIn(BaseModel):
    priority: int = 5


class BatchIn(BaseModel):
    industry_id: int
    subjects: Any = ""
    platforms: Any = None
    platform: str = ""
    skip_duplicates: bool = True
    priority: int = 5
    max_attempts: int = 0
    pipeline_spec: Any = None
    # —— 与单条运行一致的模板字段 ——
    persona_id: int = 0
    account_id: int = 0
    brand_asset_id: int = 0
    target_persona_id: int = 0
    intent_question_id: int = 0
    target_persona_ids: Any = ""
    intent_question_ids: Any = ""
    keyword_ids: Any = ""
    knowledge_item_ids: Any = ""
    rule_ids: Any = ""
    ai_engine: str = "deepseek"
    mock_doubao: int = 0
    llm_config_id: int = 0
    auto_publish: int = 0


def _payload_dict(payload: BaseModel) -> Dict[str, Any]:
    return payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()


# ============================================================
#  1) 编排规格
# ============================================================
@router.get("/steps")
def list_steps(engine_kind: str = "deepseek"):
    """步骤注册表：顺序、是否可关、产物落点、依赖说明。前端编排器据此渲染。"""
    return {
        "code": 0,
        "data": {
            "steps": pipeline_svc.describe_steps(engine_kind),
            "optional": sorted(pipeline_svc.OPTIONAL_STEPS),
            "default_spec": pipeline_svc.default_spec(),
            "max_revise_rounds_cap": pipeline_svc.MAX_REVISE_ROUNDS_CAP,
        },
    }


@router.get("/spec")
def get_spec(run_id: int, db: Session = Depends(get_db)):
    """读一条运行的编排规格 + 断点续跑计划（一次给全，前端不必再算）。"""
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    return {"code": 0, "data": {"run_id": run_id, "plan": pipeline_svc.plan(db, run)}}


@router.put("/spec")
def put_spec(payload: SpecIn, db: Session = Depends(get_db)):
    """写入编排规格。返回规整后的规格与**被修正之处**，便于前端如实回显。"""
    run = get_auto_run(db, payload.run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    if run.status == "running":
        raise HTTPException(400, "运行中，暂不能修改编排规格")
    spec, notes = pipeline_svc.validate_spec({
        "steps": payload.steps if payload.steps is not None else pipeline_svc.default_spec()["steps"],
        "max_revise_rounds": (payload.max_revise_rounds
                              if payload.max_revise_rounds is not None
                              else pipeline_svc.DEFAULT_MAX_REVISE_ROUNDS),
    })
    run.pipeline_spec = pipeline_svc.dump_spec(spec)
    db.commit()
    return {
        "code": 0,
        "data": {"run_id": run.id, "spec": spec, "notes": notes,
                 "plan": pipeline_svc.plan(db, run, spec)},
    }


# ============================================================
#  2) 断点续跑
# ============================================================
@router.post("/run/{run_id}/resume")
def resume_run(run_id: int, payload: Optional[ResumeIn] = None, db: Session = Depends(get_db)):
    """从断点续跑：重置第一个未完成步骤及其之后，然后入队。

    ``from_step`` 是逃生口 —— 产物虽然写过了但结果不满意时，用它强制从某步重做。
    """
    payload = payload or ResumeIn()
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    if run.status == "running":
        raise HTTPException(400, "运行中，无需续跑")

    from_step = (payload.from_step or "").strip() or None
    if from_step and from_step not in pipeline_svc.STEP_ORDER:
        raise HTTPException(400, f"未知步骤：{from_step}")
    spec = pipeline_svc.spec_of(run)
    if from_step and from_step not in spec["steps"]:
        raise HTTPException(400, f"步骤「{from_step}」已被当前编排规格关闭，无法从它续跑")

    plan = pipeline_svc.plan(db, run, spec, from_step=from_step)
    start_at = from_step or plan["next_key"]
    reset: Dict[str, Any] = {"from_step": "", "cleared": [], "kept": list(spec["steps"])}
    if start_at:
        reset = pipeline_svc.reset_from(db, run, start_at)
    run.status = "created"
    run.error = ""
    db.commit()

    queued = task_queue.enqueue(
        db, run.industry_id, run.id, batch_id=run.batch_id or "",
        priority=int(payload.priority or 3),
    )
    return {
        "code": 0,
        "data": {
            "run_id": run.id,
            "resumed_from": start_at or "",
            "reused": reset["kept"],
            "reset": reset["cleared"],
            "job": queued,
            "plan": plan,
        },
        "msg": (f"已从「{start_at}」续跑（复用 {len(reset['kept'])} 步产物）"
                if start_at else "所有步骤产物均可用，已重新投递"),
    }


@router.post("/run/{run_id}/enqueue")
def enqueue_run(run_id: int, payload: Optional[JobActionIn] = None, db: Session = Depends(get_db)):
    """只入队、不重置任何步骤（适合「上次是服务中断，产物都还在」）。"""
    payload = payload or JobActionIn()
    run = get_auto_run(db, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    res = task_queue.enqueue(db, run.industry_id, run.id, batch_id=run.batch_id or "",
                             priority=int(payload.priority or 5))
    return {"code": 0, "data": res,
            "msg": "已入队" if res["created"] else "该运行已在队列中，未重复投递"}


# ============================================================
#  3) 队列运维
# ============================================================
@router.get("/queue/stats")
def queue_stats(db: Session = Depends(get_db)):
    return {"code": 0, "data": task_queue.queue_stats(db)}


@router.get("/queue")
def list_queue(
    industry_id: int = 0,
    status: str = "",
    batch_id: str = "",
    limit: int = 50,
    db: Session = Depends(get_db),
):
    if status and status not in task_queue._STATUS_LABEL:
        raise HTTPException(400, f"未知状态：{status}")
    return {"code": 0, "data": {
        "jobs": task_queue.list_jobs(db, industry_id, status, batch_id, limit),
        "stats": task_queue.queue_stats(db),
    }}


@router.post("/queue/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    res = task_queue.cancel(db, job_id)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "取消失败"))
    return {"code": 0, "data": res}


@router.post("/queue/{job_id}/retry")
def retry_job(job_id: int, db: Session = Depends(get_db)):
    res = task_queue.retry(db, job_id)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "重试失败"))
    return {"code": 0, "data": res}


@router.post("/queue/retry-failed")
def retry_failed(industry_id: int = 0, batch_id: str = "", db: Session = Depends(get_db)):
    """批量重试：把失败/已取消的作业一次性重新排队。

    单条重试要来回点十几次，而失败往往是成批的（比如上游 API 限流），
    所以这个端点是批量场景下的主力操作。
    """
    q = db.query(PipelineJob).filter(
        PipelineJob.is_deleted == 0,
        PipelineJob.status.in_(("failed", "cancelled")),
    )
    if industry_id:
        q = q.filter(PipelineJob.industry_id == int(industry_id))
    if batch_id:
        q = q.filter(PipelineJob.batch_id == batch_id)
    jobs = q.order_by(PipelineJob.id.asc()).limit(200).all()
    ok: List[int] = []
    for job in jobs:
        if task_queue.retry(db, job.id).get("ok"):
            ok.append(job.id)
    return {"code": 0, "data": {"retried": ok, "count": len(ok)},
            "msg": f"已重新排队 {len(ok)} 条"}


@router.post("/queue/reap")
def reap_orphans(db: Session = Depends(get_db)):
    """手动回收「上次进程留下的运行中作业」。

    服务正常启动时会自动做一次；这里保留手动入口，便于排查
    「明明没有运行中的任务，并发额度却被占满」这类问题。
    """
    n = task_queue.reap_orphans(db)
    return {"code": 0, "data": {"reaped": n}, "msg": f"已回收 {n} 条中断作业（将断点续跑）"}


# ============================================================
#  4) 批量生产
# ============================================================
@router.post("/batch/preview")
def preview_batch(payload: BatchIn, db: Session = Depends(get_db)):
    """展开预览（不落库）：将创建多少条、跳过多少条、为什么跳过。"""
    return {"code": 0, "data": batch_svc.expand(db, _payload_dict(payload))}


@router.post("/batch")
def create_batch(payload: BatchIn, db: Session = Depends(get_db)):
    """创建批次：N 条运行 + N 条排队作业，共享一个 batch_id。"""
    result = batch_svc.create(db, _payload_dict(payload))
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "批量创建失败"))
    return {"code": 0, "data": result,
            "msg": f"已创建 {result['created_count']} 条并入队"
                   + (f"，跳过重复 {result['skipped_count']} 条" if result["skipped_count"] else "")}


@router.get("/batches")
def list_batches(industry_id: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return {"code": 0, "data": batch_svc.list_batches(db, industry_id, limit)}


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: str, db: Session = Depends(get_db)):
    data = batch_svc.batch_summary(db, batch_id)
    if not data["total"]:
        raise HTTPException(404, "批次不存在或没有作业")
    return {"code": 0, "data": data}


@router.post("/batches/{batch_id}/requeue")
def requeue_batch(batch_id: str, payload: Optional[JobActionIn] = None,
                  db: Session = Depends(get_db)):
    """整批重投：已完成的运行会被幂等规则挡掉，不会重复烧 token。"""
    payload = payload or JobActionIn()
    res = batch_svc.enqueue_batch(db, batch_id, priority=int(payload.priority or 5))
    if not res.get("ok"):
        raise HTTPException(404, res.get("error", "批次不存在"))
    return {"code": 0, "data": res, "msg": res["msg"]}


# ============================================================
#  5) 运行维度的队列视图（给运行列表加「队列态」列用）
# ============================================================
@router.get("/run/{run_id}/queue")
def run_queue_state(run_id: int, db: Session = Depends(get_db)):
    run = db.query(ProductionTask).filter(ProductionTask.id == run_id).first()
    if not run:
        raise HTTPException(404, "运行不存在")
    jobs = (
        db.query(PipelineJob)
        .filter(PipelineJob.is_deleted == 0, PipelineJob.run_id == run_id)
        .order_by(PipelineJob.id.desc())
        .limit(5)
        .all()
    )
    return {"code": 0, "data": {
        "run_id": run_id,
        "run_status": run.status or "",
        "jobs": [
            {
                "id": j.id,
                "status": j.status,
                "status_label": task_queue._STATUS_LABEL.get(j.status, j.status),
                "attempts": j.attempts,
                "error": j.error or "",
                "create_time": j.create_time.strftime("%Y-%m-%d %H:%M:%S") if j.create_time else "",
            }
            for j in jobs
        ],
        "plan": pipeline_svc.plan(db, run),
    }}
