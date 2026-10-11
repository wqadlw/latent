# -*- coding: utf-8 -*-
"""
可编排流水线内核（Pipeline）

为什么要有这一层
----------------
阶段 C 之前，10 步流水线的**顺序、开关、失败恢复**三件事全部写死在
``doubao_studio.orchestrate_run`` 的函数体里，于是：

  - **不能裁剪**：想跳过「去 AI 味精修」省一次调用，只能改代码；
  - **不能续跑**：``retry_run`` 把全部步骤重置为 ``pending``，第⑦步失败也要从①b
    重新烧一遍 token（一次运行 6~10 次 LLM 调用，白烧的钱是实打实的）；
  - **不能批量**：一次只能跑一篇。

本模块把这三件事从「函数体」搬到「数据」：一条运行携带一份 ``pipeline_spec``
（启用哪些步骤、最多整改几轮），执行器据此决定跑什么、跳过什么；
已完成的步骤产物本来就已经落在 ``production_task`` 的各列上，
所以「续跑」= 把已完成前缀读回来、只跑剩下的那一段。

单一真源约定
------------
- **顺序与开关**：本模块 ``STEP_ORDER`` / ``OPTIONAL_STEPS``。
- **步骤标题与角色**：仍在 ``services.orchestrator.get_step_defs``（两路径共享），
  本模块只按 key 取值，不复制一份标题。
- **产物落点**：本模块 ``_ARTIFACT_FIELD`` 声明「哪一步的产物写在哪一列」，
  执行器与续跑判定都读它，避免两处各记一套。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from ..models import BrowserStudioStep

# ============================================================
#  1) 步骤拓扑（顺序 / 是否可关 / 产物落点）
# ============================================================
#: 规范顺序。任何 spec 的步骤序列都必须是它的子序列。
STEP_ORDER: List[str] = [
    "connect", "clarify", "outline", "draft",
    "depolish", "geo", "review", "revise", "confirm",
]

#: 可关闭的步骤。关掉之后的语义是**透传**（产物取上一步），而不是让整条链断掉：
#: 关掉 ``clarify`` 则主编简报为空；关掉 ``depolish`` 则精修稿直接取初稿；
#: 关掉 ``revise`` 则不整改，评审未达标也照常进入确认闸门。
OPTIONAL_STEPS = {"clarify", "depolish", "revise"}

#: 步骤 → 产物所在列。``connect`` / ``confirm`` 不产文本，故不在此表。
_ARTIFACT_FIELD: Dict[str, str] = {
    "clarify": "clarified_brief",
    "outline": "outline_content",
    "draft": "draft_content",
    "depolish": "rewrite_content",
    "geo": "final_content",
    "review": "review_result",
    "revise": "revise_rounds",
}

#: 步骤的「为什么可以关掉」说明，供前端编排器直接展示，避免用户盲关。
STEP_HINT: Dict[str, str] = {
    "connect": "连接创作引擎并准备上下文。断点续跑时总会重新执行——引擎会话无法跨进程复用。",
    "clarify": "主编先写一份创作简报。关掉可省一次调用，但大纲会缺少选题角与目标读者的约束。",
    "outline": "主编拟定大纲。必开——后面所有步骤都依赖它。",
    "draft": "写手基于大纲出初稿。必开。",
    "depolish": "去 AI 味精修。关掉则 GEO 强化直接拿初稿，成稿的机器味会明显偏重。",
    "geo": "GEO 强化 + 平台过审，产出终稿。必开。",
    "review": "主编评审 + 平台合规自检 + GEO 评分（本地启发式，零 AI 调用）。必开。",
    "revise": "未达标时的闭环整改（主编指令 → 写手改写，最多 N 轮）。关掉则不整改，省下最多 3×2 次调用。",
    "confirm": "人工满意确认闸门。必开——企业内容不应无人过审就入库。",
}

#: 未显式声明时的默认规格：全开 + 最多 3 轮整改。
DEFAULT_MAX_REVISE_ROUNDS = 3
MAX_REVISE_ROUNDS_CAP = 5

#: 步骤行被视为「已满足」的状态。``skipped`` 是主动关掉的步骤，
#: 续跑时同样不该重跑，故与 ``done`` 同等对待。
_SATISFIED_STATUS = ("done", "skipped")

#: 不参与「已完成前缀」判定的步骤。``connect`` 没有产物、且每次执行都必须重连引擎，
#: 若把它当作「未完成」就会永远卡在断点①，让后面的产物复用全部失效；
#: 若把它算作「已完成」又会在语义上骗人。所以单独归为「非阻断」：
#: 既不阻断前缀扫描，也不计入复用清单。
_NON_BLOCKING = {"connect"}


def default_spec() -> Dict[str, Any]:
    return {
        "version": 1,
        "steps": list(STEP_ORDER),
        "max_revise_rounds": DEFAULT_MAX_REVISE_ROUNDS,
    }


# ============================================================
#  2) 规格解析（容错优先）
# ============================================================
def validate_spec(raw: Any) -> Tuple[Dict[str, Any], List[str]]:
    """把任意输入规整成合法规格，并返回被修正之处。

    容错优先：**坏规格绝不能导致运行起不来**。数据库里存的是 JSON 文本，
    历史数据、手工改库、前端半截请求都可能给出脏值；此时退回默认全开，
    比抛异常让一条已排队的任务永远卡住要好得多。

    返回 ``(spec, notes)``；``notes`` 为空表示输入完全合法。
    """
    spec = default_spec()
    notes: List[str] = []
    if raw in (None, "", b""):
        return spec, notes

    data = raw
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except Exception:  # noqa: BLE001
            return spec, ["规格不是合法 JSON，已退回默认（全步骤启用）"]
    if not isinstance(data, dict):
        return spec, ["规格不是对象，已退回默认（全步骤启用）"]

    steps = data.get("steps")
    if isinstance(steps, list):
        wanted = {str(s) for s in steps}
        unknown = sorted(wanted - set(STEP_ORDER))
        if unknown:
            notes.append("已忽略未知步骤：" + "、".join(unknown))
        ordered = [k for k in STEP_ORDER if k in wanted]
        missing_required = [k for k in STEP_ORDER if k not in OPTIONAL_STEPS and k not in ordered]
        if missing_required:
            # 缺了必开步骤的规格产不出东西，补回来比让它跑出一个空结果好
            notes.append("已补回必开步骤：" + "、".join(missing_required))
            ordered = [k for k in STEP_ORDER if k in set(ordered) | set(missing_required)]
        spec["steps"] = ordered
    elif steps is not None:
        notes.append("steps 不是数组，已退回全步骤启用")

    raw_rounds = data.get("max_revise_rounds")
    if raw_rounds is not None:
        try:
            rounds = int(raw_rounds)
        except (TypeError, ValueError):
            notes.append("max_revise_rounds 不是整数，已退回默认值")
        else:
            if rounds < 0:
                notes.append("max_revise_rounds 为负，已按 0 处理")
            if rounds > MAX_REVISE_ROUNDS_CAP:
                notes.append(f"max_revise_rounds 超过上限 {MAX_REVISE_ROUNDS_CAP}，已截断")
            spec["max_revise_rounds"] = max(0, min(MAX_REVISE_ROUNDS_CAP, rounds))

    return spec, notes


def parse_spec(raw: Any) -> Dict[str, Any]:
    """容错解析，只取规整后的规格（不需要修正说明时用这个）。"""
    return validate_spec(raw)[0]


def spec_of(run: Any) -> Dict[str, Any]:
    return parse_spec(getattr(run, "pipeline_spec", ""))


def dump_spec(spec: Dict[str, Any]) -> str:
    return json.dumps(spec, ensure_ascii=False)


# ============================================================
#  3) 步骤描述（供前端编排器渲染）
# ============================================================
def describe_steps(engine_kind: str = "deepseek") -> List[Dict[str, Any]]:
    """返回全部步骤的元信息（含标题/角色），顺序即规范顺序。

    标题不在此处再抄一份：统一取自 ``orchestrator.get_step_defs``，
    它同时服务「浏览器工作室」与「生产手动流」两个界面。
    """
    from .orchestrator import get_step_defs

    meta = {key: (title, agent) for _no, key, title, agent in get_step_defs(engine_kind)}
    out: List[Dict[str, Any]] = []
    for no, key in enumerate(STEP_ORDER, start=1):
        title, agent = meta.get(key, (key, "system"))
        out.append({
            "no": no,
            "key": key,
            "title": title,
            "agent": agent,
            "optional": key in OPTIONAL_STEPS,
            "hint": STEP_HINT.get(key, ""),
            "artifact_field": _ARTIFACT_FIELD.get(key, ""),
        })
    return out


# ============================================================
#  4) 续跑判定
# ============================================================
def _step_rows(db: Any, run_id: int) -> Dict[str, BrowserStudioStep]:
    rows = db.query(BrowserStudioStep).filter(BrowserStudioStep.run_id == run_id).all()
    return {r.step_key: r for r in rows}


def _review_passed(run: Any) -> bool:
    try:
        return bool(json.loads(run.review_result or "{}").get("gate_pass"))
    except Exception:  # noqa: BLE001
        return False


def is_satisfied(run: Any, key: str, row: Optional[BrowserStudioStep]) -> bool:
    """某一步的产物是否还在、可以跳过。

    刻意不只看步骤行状态：**状态是 done 但产物为空**同样要重跑。
    这条防的是「上次写库失败 / 产物被人工清空」这类情况 ——
    只认状态会让续跑直接跳到第⑦步，然后拿着空终稿去评审。
    """
    if key == "connect":
        # 引擎连接是进程内资源（浏览器会话 / 客户端），跨进程一定失效，必须重连
        return False
    if key == "confirm":
        return int(getattr(run, "confirmed", 0) or 0) == 1
    if row is None or row.status not in _SATISFIED_STATUS:
        return False
    field = _ARTIFACT_FIELD.get(key)
    if field and not str(getattr(run, field, "") or "").strip():
        return False
    return True


def plan(
    db: Any,
    run: Any,
    spec: Optional[Dict[str, Any]] = None,
    from_step: Optional[str] = None,
) -> Dict[str, Any]:
    """计算这条运行「该从哪一步接着跑」。

    参数
    ----
    from_step : 显式指定从某一步重跑（含该步）。用于「产物虽然写过了，但我不满意，
                请从②重新来」这类诉求。它是唯一的逃生口 ——
                没有它，用户遇到「已满足但结果不对」时只能删掉运行重建。

    返回结构直接喂给前端，所以字段都做了人类可读的取名。

    两个「下一步」的区别
    --------------------
    - ``starts_at``：执行器**第一个会碰到的**步骤（通常就是①连接，因为它必须重连引擎）；
    - ``next_key``：第一个需要**真正重新生成**的步骤，也就是用户理解的「从哪继续」。
    界面上展示 ``next_key``，重试也从 ``next_key`` 起重置 ——
    把①也一起重置会把后面可复用的产物全部丢掉。
    """
    spec = spec or spec_of(run)
    enabled: List[str] = spec["steps"]
    rows = _step_rows(db, run.id)

    # 只跳过**连续前缀**：第③步做完了但第②步没有，就不能越过②直接续③。
    # 显式 from_step 则把该步及其之后全部视为未完成。
    cutoff = enabled.index(from_step) if from_step in enabled else len(enabled)
    done: List[str] = []
    for idx, key in enumerate(enabled):
        if idx >= cutoff:
            break
        if key in _NON_BLOCKING:
            continue
        if is_satisfied(run, key, rows.get(key)):
            done.append(key)
        else:
            break

    done_set = set(done)
    remaining = [k for k in enabled if k not in done_set]
    next_key = next((k for k in remaining if k not in _NON_BLOCKING), None)

    steps_view: List[Dict[str, Any]] = []
    for no, key in enumerate(enabled, start=1):
        row = rows.get(key)
        field = _ARTIFACT_FIELD.get(key, "")
        reused = key in done_set
        steps_view.append({
            "no": no,
            "key": key,
            "title": (row.title if row is not None and row.title else key),
            "agent": (row.agent if row is not None else ""),
            "optional": key in OPTIONAL_STEPS,
            "status": ("reuse" if reused else (row.status if row is not None else "pending")),
            "satisfied": reused,
            "artifact_field": field,
            "artifact_len": len(str(getattr(run, field, "") or "")) if field else 0,
            "attempts": int(getattr(row, "attempts", 0) or 0) if row is not None else 0,
            "last_error": (row.last_error if row is not None else "") or "",
        })

    disabled = [k for k in STEP_ORDER if k not in set(enabled)]
    return {
        "spec": spec,
        "enabled": enabled,
        "disabled": disabled,
        "done": done,
        "remaining": remaining,
        "next_key": next_key,
        "next_no": (enabled.index(next_key) + 1) if next_key else None,
        "starts_at": (enabled[0] if enabled else None),
        "done_count": len(done),
        "total": len(enabled),
        "can_resume": bool(done),
        "review_passed": _review_passed(run),
        "steps": steps_view,
    }


def hydrate(run: Any) -> Dict[str, Any]:
    """从 run 行把已完成步骤的产物读回来，供续跑时直接复用。

    这就是「断点续跑」的全部秘密：产物本来就已经落库了
    （``outline_content`` / ``draft_content`` / … 都是 ``production_task`` 的列），
    续跑不需要另建检查点文件，只需要把它们读回来塞进执行上下文。
    """
    issues: List[str] = []
    try:
        issues = list(json.loads(run.review_result or "{}").get("issues") or [])
    except Exception:  # noqa: BLE001
        issues = []
    rounds: List[Any] = []
    try:
        loaded = json.loads(run.revise_rounds or "[]")
        if isinstance(loaded, list):
            rounds = loaded
    except Exception:  # noqa: BLE001
        rounds = []
    return {
        "clarified": run.clarified_brief or "",
        "outline": run.outline_content or "",
        "draft": run.draft_content or "",
        "polished": run.rewrite_content or "",
        "final_title": run.final_title or "",
        "final_content": run.final_content or "",
        "geo_score": int(run.geo_score or 0),
        "issues": issues,
        "rounds": rounds,
    }


def reset_from(db: Any, run: Any, from_step: Optional[str] = None) -> Dict[str, Any]:
    """把 ``from_step``（含）之后的步骤行重置为 pending，保留之前的产物与日志。

    这是 ``retry`` 的正确语义。历史实现把**所有**步骤重置为 pending，
    于是第⑦步失败也要从①b 重烧一遍 —— 对按 token 计费的引擎来说就是白花钱。
    """
    spec = spec_of(run)
    enabled: List[str] = spec["steps"]
    cutoff = enabled.index(from_step) if from_step in enabled else 0
    target = set(enabled[cutoff:]) if from_step in enabled else set(enabled)

    rows = db.query(BrowserStudioStep).filter(BrowserStudioStep.run_id == run.id).all()
    cleared: List[str] = []
    for row in rows:
        if row.step_key in target:
            row.status = "pending"
            row.last_error = ""
            row.result_json = ""
            row.started_at = None
            row.finished_at = None
            cleared.append(row.step_key)
    db.commit()
    return {
        "from_step": from_step or (enabled[0] if enabled else ""),
        "cleared": cleared,
        "kept": [k for k in enabled if k not in target],
    }


# ============================================================
#  5) 引擎代理：把「裁剪 / 续跑」收敛到一个类
# ============================================================
class ReplayEngine:
    """包住真实创作引擎，决定**这一步到底要不要真的调用模型**。

    为什么用代理而不是在编排器里插 if
    --------------------------------
    直接在 ``orchestrate_run`` 的每个步骤块前面插一句
    ``if key in skip: ... else: ...`` 也能work，但那样「裁剪与续跑」的知识就散在
    8 个步骤块里，每加一个开关都要动一处，迟早漏一处。
    收敛成一个代理后，编排器继续只管「按顺序推进状态」，
    代理只管「这一步该不该真调用」—— 职责单一，且新增步骤时只需在代理里加一个方法。

    三种处置
    --------
    - **replay**：产物已在库里 → 直接回放，零调用（这是断点续跑）；
    - **passthrough**：步骤被规格关掉 → 原样透传上一步产物（如关掉精修则终稿取初稿）；
    - 其余 → 落到下层引擎。

    ``note`` 是可选的回调，用来把「本次没真调用」记进运行日志 ——
    否则审计时只看日志会以为每一步都跑过，看不出是复用还是新生成。
    """

    def __init__(
        self,
        inner: Any,
        hydrated: Optional[Dict[str, Any]] = None,
        replay: Optional[Any] = None,
        enabled: Optional[Any] = None,
        note: Optional[Any] = None,
    ) -> None:
        self._inner = inner
        self._h: Dict[str, Any] = hydrated or {}
        self._replay = set(replay or ())
        self._enabled = set(enabled or ()) or set(STEP_ORDER)
        self._note_fn = note

    # —— 内部 ——
    def _note(self, msg: str) -> None:
        if self._note_fn is not None:
            try:
                self._note_fn(msg)
            except Exception:  # noqa: BLE001
                pass

    def _off(self, key: str) -> bool:
        return key not in self._enabled

    def _done(self, key: str) -> bool:
        return key in self._replay

    # —— 透明委托：未覆写的方法与属性一律透传给下层引擎 ——
    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

    def open(self) -> Any:
        # 引擎连接不可复用（浏览器会话 / 客户端），续跑也必须重新打开
        return self._inner.open()

    def close(self) -> Any:
        return self._inner.close()

    def clarify(self, briefing: str, ctx: Dict[str, Any]) -> str:
        if self._off("clarify"):
            self._note("步骤①b 已按编排规格关闭：跳过创作简报，大纲将不带简报约束")
            return ""
        if self._done("clarify"):
            self._note("步骤①b 断点续跑：复用已有创作简报，未调用引擎")
            return self._h.get("clarified", "")
        return self._inner.clarify(briefing, ctx)

    def gen_outline(self, briefing: str, clarified: str, ctx: Dict[str, Any]) -> Any:
        if self._done("outline"):
            self._note("步骤② 断点续跑：复用已有大纲，未调用引擎")
            return "", self._h.get("outline", "")
        return self._inner.gen_outline(briefing, clarified, ctx)

    def gen_draft(self, outline_text: str, ctx: Dict[str, Any]) -> Any:
        if self._done("draft"):
            self._note("步骤③ 断点续跑：复用已有初稿，未调用引擎")
            return "", self._h.get("draft", "")
        return self._inner.gen_draft(outline_text, ctx)

    def depolish(self, draft_text: str, ctx: Dict[str, Any]) -> Any:
        if self._off("depolish"):
            self._note("步骤④ 已按编排规格关闭：精修稿直接取初稿（透传）")
            return "", draft_text
        if self._done("depolish"):
            self._note("步骤④ 断点续跑：复用已有精修稿，未调用引擎")
            return "", self._h.get("polished", "")
        return self._inner.depolish(draft_text, ctx)

    def geo_strengthen(self, polished_text: str, ctx: Dict[str, Any]) -> Any:
        if self._done("geo"):
            self._note("步骤⑤ 断点续跑：复用已有终稿，未调用引擎")
            return self._h.get("final_title", ""), self._h.get("final_content", "")
        return self._inner.geo_strengthen(polished_text, ctx)

    def direct_revision(self, text: str, issues: List[str], round_no: int = 1) -> str:
        """返回空指令即「本轮不整改」。

        编排器的整改循环对空指令本就是 ``break`` 语义（见 ``orchestrate_run``），
        所以这里不需要新增控制流 —— 复用它天然的终止条件。
        """
        if self._off("revise") or self._done("revise"):
            why = "已按编排规格关闭" if self._off("revise") else "断点续跑复用"
            self._note("步骤⑦ 不再发起整改（%s，已有整改记录 %d 轮）"
                       % (why, len(self._h.get("rounds") or [])))
            return ""
        return self._inner.direct_revision(text, issues, round_no)
