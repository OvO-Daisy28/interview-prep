"""Repository abstraction (design §8 flexibility layer 3, persistence side).

The orchestrator talks to this interface only; the concrete store is
swappable. M1 ships ``InMemoryRepository`` (no DB) so the full orchestration
logic is testable without PostgreSQL. A ``PostgresRepository`` later replaces
only this module — state machine, mapping, adapter, and API stay put.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class JobRecord:
    id: int
    kb_id: str
    options: dict[str, Any]
    status: str = "pending"
    priority: int = 0
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    tasks: list["TaskRecord"] = field(default_factory=list)


@dataclass
class TaskRecord:
    id: int
    job_id: int
    doc_name: str
    doc_path_or_url: str
    status: str = "pending"
    priority: int = 0
    retry_count: int = 0
    current_step: str | None = None
    ragflow_doc_id: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    steps: list["StepRecord"] = field(default_factory=list)


@dataclass
class StepRecord:
    id: int
    task_id: int
    step_name: str
    status: str = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: int = 0
    duration_ms: int | None = None
    ragflow_progress: float | None = None
    ragflow_progress_msg: str | None = None
    retry_count: int = 0
    error: str | None = None
    created_at: datetime = field(default_factory=_now)


class IngestRepository:
    """Abstract persistence interface. Implementations: in-memory, Postgres."""

    def create_job(self, kb_id: str, options: dict, priority: int = 0) -> JobRecord: ...
    def get_job(self, job_id: int) -> JobRecord | None: ...
    def create_task(self, job_id: int, doc_name: str, path: str,
                    priority: int = 0) -> TaskRecord: ...
    def get_task(self, task_id: int) -> TaskRecord | None: ...
    def update_task(self, task_id: int, **fields: Any) -> TaskRecord: ...
    def ensure_step(self, task_id: int, step_name: str) -> StepRecord: ...
    def update_step(self, step_id: int, **fields: Any) -> StepRecord: ...
    def list_tasks_by_status(self, status: str) -> list[TaskRecord]: ...


class InMemoryRepository(IngestRepository):
    """Thread-safe in-memory store for M1 testing (no external DB)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[int, JobRecord] = {}
        self._tasks: dict[int, TaskRecord] = {}
        self._steps: dict[int, StepRecord] = {}
        self._next_job = 1
        self._next_task = 1
        self._next_step = 1

    def create_job(self, kb_id, options, priority=0):
        with self._lock:
            jid = self._next_job
            self._next_job += 1
            job = JobRecord(id=jid, kb_id=kb_id, options=options, priority=priority)
            self._jobs[jid] = job
            return job

    def get_job(self, job_id):
        """Return a snapshot copy with live task/step snapshots attached."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            snap = replace(job)
            snap.tasks = []
            for t in self._tasks.values():
                if t.job_id != job_id:
                    continue
                tsnap = replace(t)
                tsnap.steps = [replace(s) for s in self._steps.values()
                               if s.task_id == t.id]
                snap.tasks.append(tsnap)
            snap.tasks.sort(key=lambda t: t.id)
            return snap

    def create_task(self, job_id, doc_name, path, priority=0):
        with self._lock:
            tid = self._next_task
            self._next_task += 1
            task = TaskRecord(id=tid, job_id=job_id, doc_name=doc_name,
                              doc_path_or_url=path, priority=priority)
            self._tasks[tid] = task
            return task

    def get_task(self, task_id):
        """Return a snapshot copy — concurrent batch runs must not share state."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            snap = replace(task)
            snap.steps = [replace(s) for s in self._steps.values()
                          if s.task_id == task_id]
            return snap

    def update_task(self, task_id, **fields):
        with self._lock:
            task = self._tasks[task_id]
            for k, v in fields.items():
                setattr(task, k, v)
            task.updated_at = _now()
            return task

    def ensure_step(self, task_id, step_name):
        with self._lock:
            for s in self._steps.values():
                if s.task_id == task_id and s.step_name == step_name:
                    return s
            sid = self._next_step
            self._next_step += 1
            step = StepRecord(id=sid, task_id=task_id, step_name=step_name)
            self._steps[sid] = step
            return step

    def update_step(self, step_id, **fields):
        with self._lock:
            step = self._steps[step_id]
            for k, v in fields.items():
                setattr(step, k, v)
            return step

    def list_tasks_by_status(self, status):
        with self._lock:
            return [t for t in self._tasks.values() if t.status == status]
