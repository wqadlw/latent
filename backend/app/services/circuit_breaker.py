"""
熔断器（Circuit Breaker）

为什么质检链路需要它
--------------------
质检闸门在「本地证据不足」时可以调用 AI 做补充裁决。一旦上游模型服务
持续报错（限流 / 超时 / 欠费），每次质检都要白等一个超时周期，
批量质检时会把整个生产队列拖死 —— **故障从上游传染到本地**。

熔断器的作用就是在检测到上游持续失败后，**主动短路**一段时间，
让质检降级为「纯本地判定 + 标记待人工复核」，而不是继续排队等超时。

打开条件（与 GEOFlow 的 ``ai_quality_circuit_*`` 配置对齐）
----------------------------------------------------------
- 连续失败 ``consecutive_failures`` 次（默认 5），**或**
- 最近 ``sample_size`` 次调用（默认 10）的失败率 >= ``failure_percent``（默认 50%）

打开后保持 ``open_seconds`` 秒（默认 60）不发起调用；
到期后进入**半开**状态，放行一次试探：
- 成功 → 关闭（恢复）
- 失败 → 重新打开

所有状态都在进程内存中，单机部署下足够；多进程部署时每个 worker 各自熔断，
行为仍然安全（最坏情况是每个 worker 各试探一次）。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Optional

# 熔断状态
CLOSED = "closed"       # 正常放行
OPEN = "open"           # 短路，不放行
HALF_OPEN = "half_open"  # 放行一次试探

_STATE_LABELS = {
    CLOSED: "正常",
    OPEN: "已熔断",
    HALF_OPEN: "半开试探",
}


class CircuitBreaker:
    """单实例熔断器（线程安全）。"""

    def __init__(self, name: str = "default", consecutive_failures: int = 5,
                 sample_size: int = 10, failure_percent: float = 50.0,
                 open_seconds: float = 60.0):
        self.name = name
        self.consecutive_failures = max(1, int(consecutive_failures))
        self.sample_size = max(2, int(sample_size))
        self.failure_percent = max(1.0, min(100.0, float(failure_percent)))
        self.open_seconds = max(0.001, float(open_seconds))

        self._lock = threading.Lock()
        self._outcomes: Deque[bool] = deque(maxlen=self.sample_size)
        self._consecutive = 0
        self._state = CLOSED
        self._opened_at = 0.0
        self._trial_in_flight = False

    # ---- 状态查询 ----
    def _refresh(self, now: float) -> None:
        """根据打开时长决定是否转入半开。调用方必须已持锁。"""
        if self._state == OPEN and now - self._opened_at >= self.open_seconds:
            self._state = HALF_OPEN
            self._trial_in_flight = False

    def allow(self) -> bool:
        """当前是否允许发起调用。"""
        with self._lock:
            self._refresh(time.time())
            if self._state == CLOSED:
                return True
            if self._state == HALF_OPEN:
                if self._trial_in_flight:
                    # 半开状态下只放行一个试探请求，其余继续短路
                    return False
                self._trial_in_flight = True
                return True
            return False

    # ---- 结果上报 ----
    def record_success(self) -> None:
        with self._lock:
            self._consecutive = 0
            self._outcomes.append(True)
            self._trial_in_flight = False
            self._state = CLOSED
            self._opened_at = 0.0

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive += 1
            self._outcomes.append(False)
            self._trial_in_flight = False
            if self._should_open():
                self._state = OPEN
                self._opened_at = time.time()

    def _should_open(self) -> bool:
        if self._consecutive >= self.consecutive_failures:
            return True
        if len(self._outcomes) >= self.sample_size:
            failures = sum(1 for ok in self._outcomes if not ok)
            rate = failures * 100.0 / len(self._outcomes)
            return rate >= self.failure_percent
        return False

    # ---- 运维接口 ----
    def reset(self) -> None:
        """人工复位（上游恢复后手动关闭熔断）。"""
        with self._lock:
            self._outcomes.clear()
            self._consecutive = 0
            self._state = CLOSED
            self._opened_at = 0.0
            self._trial_in_flight = False

    def state(self) -> Dict[str, object]:
        with self._lock:
            now = time.time()
            self._refresh(now)
            failures = sum(1 for ok in self._outcomes if not ok)
            total = len(self._outcomes)
            return {
                "name": self.name,
                "state": self._state,
                "label": _STATE_LABELS.get(self._state, self._state),
                "consecutive_failures": self._consecutive,
                "sample_total": total,
                "sample_failures": failures,
                "failure_percent": round(failures * 100.0 / total, 1) if total else 0.0,
                "open_remaining_seconds": (
                    max(0.0, round(self.open_seconds - (now - self._opened_at), 1))
                    if self._state == OPEN else 0.0
                ),
                "thresholds": {
                    "consecutive_failures": self.consecutive_failures,
                    "sample_size": self.sample_size,
                    "failure_percent": self.failure_percent,
                    "open_seconds": self.open_seconds,
                },
            }


# ============================================================
#  全局注册表：按名字复用同一个熔断器
# ============================================================
_REGISTRY_LOCK = threading.Lock()
_REGISTRY: Dict[str, CircuitBreaker] = {}

# 各业务链路的默认阈值（与 GEOFlow 的 ai_quality_circuit_* 对齐）
DEFAULT_PROFILES: Dict[str, Dict[str, float]] = {
    "ai_quality": {
        "consecutive_failures": 5,
        "sample_size": 10,
        "failure_percent": 50,
        "open_seconds": 60,
    },
    "ai_visibility": {
        "consecutive_failures": 3,
        "sample_size": 10,
        "failure_percent": 60,
        "open_seconds": 45,
    },
}


def get_breaker(name: str, **overrides) -> CircuitBreaker:
    """按名字取熔断器（不存在则按 profile 创建）。"""
    with _REGISTRY_LOCK:
        breaker = _REGISTRY.get(name)
        if breaker is None:
            params = dict(DEFAULT_PROFILES.get(name) or {})
            params.update(overrides)
            breaker = CircuitBreaker(name=name, **params)  # type: ignore[arg-type]
            _REGISTRY[name] = breaker
        return breaker


def all_states() -> Dict[str, Dict[str, object]]:
    """导出全部熔断器状态（供运维看板）。"""
    with _REGISTRY_LOCK:
        breakers = list(_REGISTRY.items())
    return {name: b.state() for name, b in breakers}


def reset_all() -> None:
    """复位全部熔断器。"""
    with _REGISTRY_LOCK:
        breakers = list(_REGISTRY.values())
    for b in breakers:
        b.reset()


def is_open(name: str) -> bool:
    """便捷判定：某条链路当前是否被熔断。"""
    with _REGISTRY_LOCK:
        breaker: Optional[CircuitBreaker] = _REGISTRY.get(name)
    return bool(breaker and breaker.state()["state"] == OPEN)
