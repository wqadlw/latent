# -*- coding: utf-8 -*-
"""
生产队列（有界并发执行池）

为什么要有它
------------
阶段 C 之前，「跑一篇」= 点一次按钮 → 起一个裸线程 → 听天由命：
  - **没有上限**：连点 20 次就同时开 20 条流水线，把 LLM 的 QPS 限额和浏览器资源一起打爆；
  - **没有排队**：点完就开跑，先来后到全靠手速；
  - **没有重试**：一次网络抖动就让整条运行停在 failed，得人工点重试；
  - **重启即丢失**：进程一崩，卡在运行中的运行再也不会被推进，而队列里也看不到它们。

本模块把「排队 → 领取 → 执行 → 判结果 → 退避重试」这一整套做成一张表
（``pipeline_job``）+ 一个调度线程 + 一个有界线程池。

并发为什么默认只给 2
--------------------
创作引擎要么是按 token 计费的 LLM API（有 QPS 与并发限额），要么是浏览器自动化
（一个 Chrome 实例吃掉几百 MB）。这两者都不是「开越多越快」的负载，
默认 2 是「吞吐够用且不会把上游打爆」的保守值，可用 ``PIPELINE_CONCURRENCY`` 调。

取消的语义（刻意保守）
----------------------
LLM 调用与浏览器步骤都是**原子**的，中途杀掉既省不下钱、还会留下半截产物。
所以取消的语义是「**尽快不再执行**」：
  - 排队中的作业 → 立刻置为已取消，不再领取；
  - 运行中的作业 → 让它跑完这一次，跑完后按已取消收尾（不进入重试）。
批量场景下这个语义已经够用：真正要止损的是「后面那 17 条还没开跑的」。

与断点续跑的关系
----------------
作业重试**不清空**运行的中间产物。配合 ``services.pipeline`` 的已完成前缀计算，
一次失败重试只会补上没做完的那一段，而不是从①重新烧一遍 token。
"""
from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import or_

from ..database import SessionLocal, now
from ..models import PipelineJob, ProductionTask
from .doubao_studio import get_auto_run, orchestrate_run

# ============================================================
#  可调参数（全部可用环境变量覆盖）
# ============================================================
#: 同时执行的作业数上限。
DEFAULT_CONCURRENCY = 2
#: 调度线程的轮询间隔（秒）。空队列时的检查成本约等于一条索引查询，1 秒足够灵敏。
DEFAULT_POLL_SECONDS = 1.0
#: 单条作业的最大尝试次数（含首次）。
DEFAULT_MAX_ATTEMPTS = 2
#: 退避基数（秒），第 n 次失败后等待 ``BASE * 2**(n-1)``，上限 5 分钟。
BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 300

#: 运行终态里算「本次作业成功」的那些。
#: ``await_confirm`` 是正常成功终点（内容就绪、等人点确认），
#: 对队列而言这一步的活已经干完了，不能算失败。
_TERMINAL_OK = ("await_confirm", "confirmed", "succeeded", "published")


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name) or default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.environ.get(name) or default))
    except (TypeError, ValueError):
        return default


def backoff_seconds(attempts: int) -> int:
    """第 ``attempts`` 次尝试失败后的等待秒数（指数退避，带上限）。"""
    n = max(1, int(attempts or 1))
    return min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** (n - 1)))


def worker_enabled() -> bool:
    """队列调度线程是否随服务启动。测试里默认关掉，见 tests/conftest.py。"""
    return (os.environ.get("APP_PIPELINE_WORKER") or "1").strip() not in ("0", "false", "False")


# ============================================================
#  入队 / 取消 / 重试
# ============================================================
def enqueue(
    db: Any,
    industry_id: int,
    run_id: int,
    batch_id: str = "",
    priority: int = 5,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Dict[str, Any]:
    """把一条运行投进队列。

    两条不变量：

    1. **同一条运行同时只能有一个活跃作业**（排队中或运行中）——
       否则连点两次「开始」就会跑两遍，产出两份内容、烧两份 token。
       此时不报错，而是返回已有作业并标记 ``created=False``。
    2. **同一条运行只保留一行作业** —— 失败/取消后重投时**复用同一行**，
       而不是另开一行。否则「批次进度」会把 3 条运行算成 5 条作业，
       运营看到的总数是错的；尝试次数本来就记在 ``attempts`` 上，不需要靠多行表达。
    """
    job = (
        db.query(PipelineJob)
        .filter(PipelineJob.run_id == int(run_id), PipelineJob.is_deleted == 0)
        .order_by(PipelineJob.id.desc())
        .first()
    )
    if job is not None:
        if job.status in ("queued", "running"):
            return {"job_id": job.id, "created": False, "status": job.status,
                    "reused_row": True}
        job.status = "queued"
        job.batch_id = batch_id or job.batch_id or ""
        job.priority = int(priority or 5)
        job.max_attempts = max(1, int(max_attempts or DEFAULT_MAX_ATTEMPTS))
        job.attempts = 0
        job.cancel_requested = 0
        job.worker = ""
        job.error = ""
        job.available_at = now()
        job.started_at = None
        job.finished_at = None
        db.commit()
        return {"job_id": job.id, "created": True, "status": "queued", "reused_row": True}

    job = PipelineJob(
        industry_id=int(industry_id),
        run_id=int(run_id),
        batch_id=batch_id or "",
        status="queued",
        priority=int(priority or 5),
        attempts=0,
        max_attempts=max(1, int(max_attempts or DEFAULT_MAX_ATTEMPTS)),
        available_at=now(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"job_id": job.id, "created": True, "status": job.status, "reused_row": False}


def cancel(db: Any, job_id: int) -> Dict[str, Any]:
    """请求取消。排队中的立刻生效；运行中的会在本次跑完后按已取消收尾。"""
    job = db.query(PipelineJob).filter(PipelineJob.id == int(job_id)).first()
    if job is None or job.is_deleted:
        return {"ok": False, "error": "作业不存在"}
    if job.status in ("done", "failed", "cancelled"):
        return {"ok": False, "error": f"作业已结束（{job.status}），无需取消"}
    job.cancel_requested = 1
    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = now()
        job.error = "已取消（排队中，未执行）"
        db.commit()
        return {"ok": True, "status": "cancelled", "immediate": True}
    db.commit()
    return {"ok": True, "status": "running", "immediate": False,
            "msg": "运行中的作业会在本次跑完后停止，不会进入重试"}


def retry(db: Any, job_id: int) -> Dict[str, Any]:
    """把失败 / 已取消的作业重新排队。"""
    job = db.query(PipelineJob).filter(PipelineJob.id == int(job_id)).first()
    if job is None or job.is_deleted:
        return {"ok": False, "error": "作业不存在"}
    if job.status in ("queued", "running"):
        return {"ok": False, "error": f"作业{('排队中' if job.status == 'queued' else '运行中')}，无需重试"}
    job.status = "queued"
    job.cancel_requested = 0
    job.available_at = now()
    job.worker = ""
    job.finished_at = None
    # 失败重试要重新给足次数，否则一次手动重试仍然只跑一次就彻底失败
    job.attempts = 0
    job.error = ""
    db.commit()
    return {"ok": True, "status": "queued"}


def reap_orphans(db: Any = None) -> int:
    """把「上一个进程留下的运行中作业」放回队列。

    进程崩溃或被杀时，正在跑的作业会永远停在 ``running``：那条运行再也不会被推进，
    队列还平白少一个并发额度。因为流水线支持断点续跑，重新入队不会从零重跑，
    只会补上没做完的那一段 —— 这正是断点续跑在运维上真正兑现价值的地方。

    **必须在调度线程开始领取之前调用一次**（本模块在 start 时自动调用），
    否则会误伤本进程正在跑的作业。
    """
    own = db is not None
    db = db or SessionLocal()
    try:
        rows = db.query(PipelineJob).filter(
            PipelineJob.is_deleted == 0, PipelineJob.status == "running"
        ).all()
        for job in rows:
            job.status = "queued"
            job.worker = ""
            job.available_at = now()
            job.error = "上次服务中断，已自动重新入队（将从断点续跑）"
        if rows:
            db.commit()
        return len(rows)
    finally:
        if not own:
            db.close()


# ============================================================
#  领取与执行
# ============================================================
def claim_next(db: Any, worker: str = "") -> Optional[int]:
    """领取一条到期的排队作业并原子地置为运行中。

    领取只由**一个**调度线程发起，因此不存在多消费者争抢同一行的经典问题；
    真正的并发发生在 worker 池里 —— 每条运行各自持有自己的 session，互不干扰。
    """
    stamp = now()
    job = (
        db.query(PipelineJob)
        .filter(
            PipelineJob.is_deleted == 0,
            PipelineJob.status == "queued",
            or_(PipelineJob.available_at.is_(None), PipelineJob.available_at <= stamp),
        )
        .order_by(PipelineJob.priority.asc(), PipelineJob.id.asc())
        .first()
    )
    if job is None:
        return None
    job.status = "running"
    job.started_at = stamp
    job.attempts = int(job.attempts or 0) + 1
    job.worker = worker or "dispatcher"
    db.commit()
    return job.id


def _finish(db: Any, job: PipelineJob, status: str, error: str = "") -> None:
    job.status = status
    job.error = error or ""
    job.worker = ""
    job.finished_at = now()
    db.commit()


def execute_job(job_id: int, worker: str = "") -> str:
    """同步执行一条作业，返回终态字符串。

    刻意做成**同步、可单独调用**的函数：调度线程只负责「按并发上限调它」，
    测试则直接调它 —— 不必起线程、不必 sleep 等结果，断言自然稳定。
    本函数自身兜住所有异常（失败信息写进 ``job.error``），不会向外抛。
    """
    db = SessionLocal()
    try:
        job = db.query(PipelineJob).filter(PipelineJob.id == int(job_id)).first()
        if job is None or job.is_deleted:
            return "missing"
        if job.cancel_requested:
            _finish(db, job, "cancelled", "取消请求在开始前生效，本次未执行")
            return "cancelled"
        if job.status != "running":
            job.status = "running"
            job.started_at = now()
            job.attempts = int(job.attempts or 0) + 1
        job.worker = worker or job.worker or "inline"
        db.commit()
        run_id = int(job.run_id)
    finally:
        db.close()

    # 真正执行。orchestrate_run 自带 SessionLocal，绝不与外层共用一个 session。
    crash = ""
    try:
        orchestrate_run(run_id)
    except Exception as exc:  # noqa: BLE001
        crash = f"编排过程抛出异常：{exc}"

    db = SessionLocal()
    try:
        job = db.query(PipelineJob).filter(PipelineJob.id == int(job_id)).first()
        if job is None:
            return "missing"
        run = get_auto_run(db, run_id)
        run_status = (run.status if run is not None else "") or ""
        run_error = (run.error if run is not None else "") or ""

        if job.cancel_requested:
            _finish(db, job, "cancelled", run_error or "运行结束后收到取消请求")
            return "cancelled"

        # orchestrate_run 不抛异常 **不代表成功** —— 它把失败写进 run.status/run.error 后正常返回。
        # 所以必须回查运行终态，否则一条失败的运行会被队列记成 done。
        if crash or run_status not in _TERMINAL_OK:
            reason = crash or run_error or (f"运行停在 {run_status or '未知状态'}，未产出终稿")
            if int(job.attempts or 0) < int(job.max_attempts or 1):
                job.status = "queued"
                job.worker = ""
                job.available_at = now() + timedelta(seconds=backoff_seconds(job.attempts))
                job.error = f"{reason}（第 {job.attempts} 次失败，稍后自动重试）"
                db.commit()
                return "retry_queued"
            _finish(db, job, "failed", reason)
            return "failed"

        _finish(db, job, "done", "")
        return "done"
    finally:
        db.close()


# ============================================================
#  调度线程 + 有界 worker 池
# ============================================================
class Dispatcher:
    """单调度线程 + 有界线程池。

    为什么要分成「调度」与「执行」两层：领取动作必须串行（否则两条线程可能领到同一行），
    而执行必须并发（否则队列等于串行队列）。把两者拆开，各自简单。
    """

    def __init__(self, concurrency: Optional[int] = None, poll_seconds: Optional[float] = None):
        self.concurrency = int(concurrency or _env_int("PIPELINE_CONCURRENCY", DEFAULT_CONCURRENCY))
        self.poll_seconds = float(poll_seconds or _env_float("PIPELINE_POLL_SECONDS", DEFAULT_POLL_SECONDS))
        self.worker_id = f"dispatcher-{os.getpid()}"
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._pool: Optional[ThreadPoolExecutor] = None
        self._inflight: Dict[int, Any] = {}
        self._ticks = 0
        self._started_at: Optional[datetime] = None
        self._last_error = ""

    # —— 生命周期 ——
    def start(self, reap: bool = True) -> bool:
        if self._thread is not None and self._thread.is_alive():
            return False
        if reap:
            try:
                self._last_reaped = reap_orphans()
            except Exception as exc:  # noqa: BLE001
                self._last_reaped = 0
                self._last_error = f"孤儿作业回收失败：{exc}"
        else:
            self._last_reaped = 0
        self._stop.clear()
        self._pool = ThreadPoolExecutor(max_workers=self.concurrency, thread_name_prefix="pipeline")
        self._thread = threading.Thread(target=self._loop, name="pipeline-dispatcher", daemon=True)
        self._thread.start()
        self._started_at = datetime.now()
        return True

    def stop(self, wait: bool = False) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=None if wait else 3)
        if self._pool is not None:
            self._pool.shutdown(wait=wait)
        self._thread = None
        self._pool = None
        with self._lock:
            self._inflight.clear()

    # —— 调度 ——
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001
                # 调度线程绝不能因为一次异常就退出：队列必须比单条作业更耐久
                self._last_error = f"{type(exc).__name__}: {exc}"
            self._stop.wait(self.poll_seconds)

    def _tick(self) -> int:
        """一轮调度：先回收已完成的 future，再按空余额度领取新作业。"""
        self._ticks += 1
        with self._lock:
            for jid, fut in list(self._inflight.items()):
                if fut.done():
                    self._inflight.pop(jid, None)
                    exc = fut.exception()
                    if exc is not None:
                        self._last_error = str(exc)
            free = self.concurrency - len(self._inflight)
        if free <= 0:
            return 0

        claimed: List[int] = []
        db = SessionLocal()
        try:
            for _ in range(free):
                jid = claim_next(db, worker=self.worker_id)
                if jid is None:
                    break
                claimed.append(jid)
        finally:
            db.close()

        with self._lock:
            for jid in claimed:
                if self._pool is None:
                    break
                self._inflight[jid] = self._pool.submit(execute_job, jid, self.worker_id)
        return len(claimed)

    # —— 观测 ——
    def status(self) -> Dict[str, Any]:
        with self._lock:
            inflight = sorted(self._inflight.keys())
        alive = self._thread is not None and self._thread.is_alive()
        return {
            "running": alive,
            "worker_id": self.worker_id,
            "concurrency": self.concurrency,
            "poll_seconds": self.poll_seconds,
            "inflight": inflight,
            "ticks": self._ticks,
            "started_at": self._started_at.strftime("%Y-%m-%d %H:%M:%S") if self._started_at else "",
            "last_error": self._last_error,
            "reaped_on_start": getattr(self, "_last_reaped", 0),
        }


#: 进程内单例。由 ``app.main`` 的 lifespan 启动（测试环境默认关闭，见 conftest）。
dispatcher = Dispatcher()


# ============================================================
#  队列观测（供路由与前端）
# ============================================================
_STATUS_LABEL = {
    "queued": "排队中",
    "running": "执行中",
    "done": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
}


def queue_stats(db: Any) -> Dict[str, Any]:
    rows = db.query(PipelineJob.status, PipelineJob.id).filter(PipelineJob.is_deleted == 0).all()
    counts = dict.fromkeys(_STATUS_LABEL, 0)
    for status, _jid in rows:
        counts[status] = counts.get(status, 0) + 1
    return {
        "counts": counts,
        "labels": _STATUS_LABEL,
        "total": len(rows),
        "active": counts.get("queued", 0) + counts.get("running", 0),
        "dispatcher": dispatcher.status(),
    }


def _job_to_dict(db: Any, job: PipelineJob, run: Optional[ProductionTask] = None) -> Dict[str, Any]:
    if run is None and job.run_id:
        run = db.query(ProductionTask).filter(ProductionTask.id == job.run_id).first()
    return {
        "id": job.id,
        "run_id": job.run_id,
        "batch_id": job.batch_id or "",
        "industry_id": job.industry_id,
        "status": job.status,
        "status_label": _STATUS_LABEL.get(job.status, job.status),
        "priority": job.priority,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "available_at": job.available_at.strftime("%Y-%m-%d %H:%M:%S") if job.available_at else "",
        "worker": job.worker or "",
        "error": job.error or "",
        "cancel_requested": int(job.cancel_requested or 0),
        "started_at": job.started_at.strftime("%Y-%m-%d %H:%M:%S") if job.started_at else "",
        "finished_at": job.finished_at.strftime("%Y-%m-%d %H:%M:%S") if job.finished_at else "",
        "create_time": job.create_time.strftime("%Y-%m-%d %H:%M:%S") if job.create_time else "",
        "run_name": (run.name or run.title or "") if run is not None else "",
        "run_status": (run.status or "") if run is not None else "",
        "run_subject": (run.subject or "") if run is not None else "",
        "run_platform": (run.platform or "") if run is not None else "",
        "run_error": (run.error or "") if run is not None else "",
        "run_geo_score": int(run.geo_score or 0) if run is not None else 0,
    }


def list_jobs(
    db: Any,
    industry_id: int = 0,
    status: str = "",
    batch_id: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    q = db.query(PipelineJob).filter(PipelineJob.is_deleted == 0)
    if industry_id:
        q = q.filter(PipelineJob.industry_id == int(industry_id))
    if status:
        q = q.filter(PipelineJob.status == status)
    if batch_id:
        q = q.filter(PipelineJob.batch_id == batch_id)
    # 活跃的排前面，同组内按 id 倒序（最近投递的先看到）
    order = {"queued": 0, "running": 1, "failed": 2, "cancelled": 3, "done": 4}
    rows = q.order_by(PipelineJob.id.desc()).limit(max(1, min(500, int(limit or 50)))).all()
    rows.sort(key=lambda j: (order.get(j.status, 9), -j.id))
    return [_job_to_dict(db, j) for j in rows]


def batch_progress(db: Any, batch_id: str) -> Dict[str, Any]:
    """一个批次的进度聚合：总数、各状态数、完成率、以及运行名清单。"""
    rows = (
        db.query(PipelineJob)
        .filter(PipelineJob.is_deleted == 0, PipelineJob.batch_id == batch_id)
        .order_by(PipelineJob.id.asc())
        .all()
    )
    counts = dict.fromkeys(_STATUS_LABEL, 0)
    for j in rows:
        counts[j.status] = counts.get(j.status, 0) + 1
    finished = counts["done"] + counts["failed"] + counts["cancelled"]
    return {
        "batch_id": batch_id,
        "total": len(rows),
        "counts": counts,
        "labels": _STATUS_LABEL,
        "finished": finished,
        "progress": round(finished / len(rows), 4) if rows else 0.0,
        "jobs": [_job_to_dict(db, j) for j in rows],
    }
