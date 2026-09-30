"""Ingest task state machine (design §5.2, §5.3).

Task-level state for the batch ingestion orchestration layer. RAGFlow kernel
is never touched (decision 8); this machine lives in our PostgreSQL and is
driven by polling RAGFlow progress.

Status alignment with RAGFlow document ``run`` (design §3.1, api_reference
line 1791-1798):

   编排层 status   RAGFlow run       PM 原型口径
    ------------   ---------------   -----------
    pending        UNSTART(0)        排队
    running        RUNNING(1)        进行中
    succeeded      DONE(3)           完成
    failed         FAIL(4)           失败
    cancelled      CANCEL(2)         停止
    paused         (编排层独有)       (软/硬暂停可恢复)

Pause semantics (design §5.3, industry graceful default + force):
  * pause (default, graceful): do NOT call DELETE /chunks; let the in-flight
    RAGFlow task finish at a boundary, then stop submitting further steps.
  * pause (force=true): hard stop via DELETE /chunks; resume re-runs.
  Both map to ``paused`` (recoverable). The soft/force difference is a side
  effect handled in the pipeline adapter layer (§8), NOT a state transition:
  the state machine only distinguishes recoverable (paused) from terminal
  (cancelled). ``cancel`` is terminal and not recoverable.
"""

from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    """Ingest task status. Values double as the wire format for the API."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"

    @property
    def is_terminal(self) -> bool:
        return self in (TaskStatus.SUCCEEDED, TaskStatus.CANCELLED)


class TransitionAction(str, Enum):
    """Actions that move a task between statuses."""

    START = "start"
    SUCCEED = "succeed"
    FAIL = "fail"
    PAUSE = "pause"  # soft (graceful) or force; both -> paused (§5.3)
    RESUME = "resume"
    RETRY = "retry"
    CANCEL = "cancel"  # terminal, not recoverable


class InvalidTransition(RuntimeError):
    """Raised when an action is not allowed from the current status."""


# (current_status, action) -> next_status.
# Derived from design §5.2 state machine diagram.
_TRANSITIONS: dict[tuple[TaskStatus, TransitionAction], TaskStatus] = {
    (TaskStatus.PENDING, TransitionAction.START): TaskStatus.RUNNING,
    (TaskStatus.PENDING, TransitionAction.CANCEL): TaskStatus.CANCELLED,
    (TaskStatus.RUNNING, TransitionAction.SUCCEED): TaskStatus.SUCCEEDED,
    (TaskStatus.RUNNING, TransitionAction.FAIL): TaskStatus.FAILED,
    (TaskStatus.RUNNING, TransitionAction.PAUSE): TaskStatus.PAUSED,
    (TaskStatus.RUNNING, TransitionAction.CANCEL): TaskStatus.CANCELLED,
    (TaskStatus.FAILED, TransitionAction.RETRY): TaskStatus.PENDING,
    (TaskStatus.FAILED, TransitionAction.CANCEL): TaskStatus.CANCELLED,
    (TaskStatus.PAUSED, TransitionAction.RESUME): TaskStatus.RUNNING,
    (TaskStatus.PAUSED, TransitionAction.CANCEL): TaskStatus.CANCELLED,
}


def can_transition(current: TaskStatus, action: TransitionAction) -> bool:
    """Return True if ``action`` is a legal move from ``current``."""
    if current.is_terminal:
        return False
    return (current, action) in _TRANSITIONS


def transition(current: TaskStatus, action: TransitionAction) -> TaskStatus:
    """Apply ``action`` to ``current``; return the next status.

    Raises ``InvalidTransition`` for terminal sources or illegal (status,
    action) pairs. Terminal statuses (succeeded, cancelled) reject all
    actions; a recoverable pause goes through ``paused`` + ``resume``.
    """
    if current.is_terminal:
        raise InvalidTransition(
            f"{current.value} is terminal; no action allowed (got {action.value})"
        )
    key = (current, action)
    if key not in _TRANSITIONS:
        raise InvalidTransition(
            f"{action.value} not allowed from {current.value}"
        )
    return _TRANSITIONS[key]
