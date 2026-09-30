"""Orchestrator — wires state machine + mapping + adapter + repo (design §5,§12).

Drives one task through upload → parse → (graph_build), polling RAGFlow
progress and projecting it onto the 5 PM sub-steps with timestamps.
Synchronous in M1 (blocking run_task); the REST layer wraps it in a
background worker later. Pause is graceful by default (§5.3): the poll loop
checks task status and exits at a boundary; force pause/cancel call
adapter.stop_parse().
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ingest.repository import IngestRepository
from ingest.state import TaskStatus, TransitionAction as A, transition, InvalidTransition
from ingest.step_mapping import (
    MARKER_ONLY_STAGES,
    PARSE_STAGES,
    GRAPH_STAGES,
    StepStatus,
    parse_progress,
    project_to_pm_steps,
    normalize_run,
)
from ingest.pipeline import IngestPipeline


class Orchestrator:
    def __init__(self, repo: IngestRepository, adapter: IngestPipeline):
        """``adapter`` is any backend satisfying the IngestPipeline protocol:
        the self-run pipeline (方案 B) or the RAGFlow HTTP adapter."""
        self.repo = repo
        self.adapter = adapter

    # ---- job/task creation ----

    def create_job(
        self, kb_id: str, files: list[dict[str, str]],
        options: dict | None = None, priority: int = 0,
    ) -> int:
        job = self.repo.create_job(kb_id, options or {}, priority)
        for f in files:
            self.repo.create_task(job.id, f["name"], f["path_or_url"], priority)
        return job.id

    def get_job(self, job_id: int) -> dict | None:
        job = self.repo.get_job(job_id)
        if not job:
            return None
        return {
            "job_id": job.id, "kb_id": job.kb_id, "status": job.status,
            "options": job.options, "created_at": _iso(job.created_at),
            "tasks": [self._task_view(t) for t in job.tasks],
        }

    def _task_view(self, t) -> dict:
        """Task view: real stages (truth) + PM 5-step projection (presentation).

        ``stages`` is what actually happened in RAGFlow; ``pm_steps`` is the
        prototype-facing projection (design §8 layer 2). The PM's 5th step
        (LLM抽取 / 参数提取) reports not_applicable — that capability belongs
        to the 内容解析子系统, not this interface.
        """
        return {
            "task_id": t.id, "doc_name": t.doc_name, "status": t.status,
            "priority": t.priority, "retry_count": t.retry_count,
            "current_step": t.current_step, "error": t.error,
            "ragflow_doc_id": t.ragflow_doc_id,
            "stages": [self._step_view(s) for s in t.steps],
            "pm_steps": self._pm_steps_view(t),
        }

    def _pm_steps_view(self, t) -> list[dict]:
        """Project persisted stages onto the PM prototype's 5 steps."""
        from ingest.step_mapping import ParseSnapshot, StageState

        def _snap(names):
            states = [
                StageState(s.step_name, StepStatus(s.status), s.progress or 0,
                           s.duration_ms, s.ragflow_progress_msg or "")
                for s in t.steps if s.step_name in names
            ]
            return ParseSnapshot(run="", progress=0, active_stage=None, stages=states)

        parse_snap = _snap(set(PARSE_STAGES))
        graph_states = _snap(set(GRAPH_STAGES))
        graph_snap = graph_states if graph_states.stages else None
        projected = project_to_pm_steps(parse_snap, graph_snap)
        return [
            {"step": p.name, "status": p.status.value, "progress": p.progress,
             "duration_ms": p.duration_ms, "note": p.detail}
            for p in projected
        ]

    def _step_view(self, s) -> dict:
        return {
            "step_name": s.step_name, "status": s.status,
            "started_at": _iso(s.started_at), "finished_at": _iso(s.finished_at),
            "progress": s.progress, "duration_ms": s.duration_ms,
            "error": s.error,
        }

    # ---- run one task end-to-end ----

    def run_task(self, task_id: int, *, poll_interval: float = 1.0,
                 max_polls: int = 10000) -> None:
        task = self.repo.get_task(task_id)
        status = TaskStatus(task.status)
        if status is TaskStatus.PENDING:
            status = transition(status, A.START)
            self.repo.update_task(task_id, status=status.value)
        if status is not TaskStatus.RUNNING:
            return  # paused / cancelled / etc — do not run

        job = self.repo.get_job(task.job_id)
        kb = job.kb_id
        opts = job.options
        try:
            doc_id = self._ensure_uploaded(task, kb)
            self._run_parse(task_id, kb, doc_id, opts, poll_interval, max_polls)
            # check pause requested mid-flight
            if self._is_paused(task_id):
                return
            if opts.get("build_graph"):
                self._run_graph_build(task_id, kb, task.retry_count, poll_interval, max_polls)
            self._set_status(task_id, A.SUCCEED)
        except _TaskPaused:
            return  # already marked paused
        except Exception as exc:
            # A backend that runs the work in-process (the self-run pipeline)
            # aborts by raising when it notices the pause flag. That surfaces
            # here as an ordinary exception, but the task is already `paused`
            # and paused->fail is not a legal move — so check before failing.
            if self._is_paused(task_id):
                return
            self.repo.update_task(task_id, error=str(exc))
            self._set_status(task_id, A.FAIL)
            raise

    def _ensure_uploaded(self, task, kb: str) -> str:
        if task.ragflow_doc_id:
            return task.ragflow_doc_id
        docs = self.adapter.upload_documents(kb, [task.doc_path_or_url])
        if not docs:
            raise RuntimeError("upload returned no documents")
        doc_id = docs[0]["id"]
        self.repo.update_task(task.id, ragflow_doc_id=doc_id)
        return doc_id

    def _run_parse(self, task_id, kb, doc_id, opts, poll_interval, max_polls):
        """Drive parsing, recording stage timings.

        Two backends, two shapes (see ingest/pipeline.py):
          * self-run  — pushes real stage boundaries through ``on_stage``, so
            timings are recorded, not inferred, and ``start_parse`` returns
            only once the document is fully ingested.
          * RAGFlow   — returns immediately; stages are inferred by polling
            ``progress_msg`` (the guessing we are moving away from).
        The poll loop below serves both: a self-run document is simply already
        terminal on the first poll.
        """
        for name in PARSE_STAGES:
            self.repo.ensure_step(task_id, name)

        def on_stage(stage_name, status, pct, duration_ms, detail):
            if self._is_paused(task_id):
                raise _TaskPaused()
            rec = self.repo.ensure_step(task_id, stage_name)
            updates: dict[str, Any] = {"progress": pct, "status": status}
            if duration_ms is not None:
                updates["duration_ms"] = duration_ms
            if detail:
                updates["ragflow_progress_msg"] = detail
            if status == "running" and not rec.started_at:
                updates["started_at"] = datetime.now(timezone.utc)
            if status in ("done", "failed"):
                updates["finished_at"] = datetime.now(timezone.utc)
            self.repo.update_step(rec.id, **updates)
            self.repo.update_task(task_id, current_step=stage_name)

        pushed = False
        try:
            def tracking_on_stage(*a):
                nonlocal pushed
                pushed = True
                on_stage(*a)
            self.adapter.start_parse(kb, [doc_id], on_stage=tracking_on_stage)
        except TypeError:
            # backend predates the on_stage protocol (RAGFlow HTTP adapter)
            self.adapter.start_parse(kb, [doc_id])

        for _ in range(max_polls):
            if self._is_paused(task_id):
                raise _TaskPaused()
            st = self.adapter.get_document_status(kb, doc_id)
            run_norm = normalize_run(st.get("run", "UNSTART"))
            # Only infer stages from text when the backend did not push them.
            if not pushed:
                self._apply_stages(task_id, st, stages=PARSE_STAGES)
            if run_norm == "DONE":
                if pushed:
                    self._finish_pushed_stages(task_id)
                return
            if run_norm == "FAIL":
                raise RuntimeError(f"parse failed: {st.get('progress_msg', '')}")
            if run_norm == "CANCEL":
                raise _TaskPaused()
            time.sleep(poll_interval)
        raise RuntimeError("parse exceeded max_polls")

    def _finish_pushed_stages(self, task_id) -> None:
        """Mark any stage the backend skipped as done, so timelines are complete."""
        task = self.repo.get_task(task_id)
        for s in task.steps:
            if s.step_name in PARSE_STAGES and s.status not in ("done", "failed"):
                self.repo.update_step(
                    s.id, status="done", progress=100,
                    finished_at=s.finished_at or datetime.now(timezone.utc))

    def _run_graph_build(self, task_id, kb, retry_count, poll_interval, max_polls):
        step = self.repo.ensure_step(task_id, "graph_build")
        self.repo.update_step(step.id, status="running", started_at=datetime.now(timezone.utc))
        self.repo.update_task(task_id, current_step="graph_build")
        for name in GRAPH_STAGES:
            self.repo.ensure_step(task_id, name)
        # decision 3: retry must DELETE /graph first to avoid 'already merged'
        if retry_count > 0:
            self.adapter.delete_graph(kb)
        self.adapter.start_graph_build(kb)
        for _ in range(max_polls):
            if self._is_paused(task_id):
                raise _TaskPaused()
            gp = self.adapter.get_graph_build_progress(kb)
            prog = gp.get("progress", 0) or 0
            # project graph progress onto the GraphRAG sub-stages too
            self._apply_stages(
                task_id,
                {"run": "DONE" if prog >= 1.0 else "RUNNING",
                 "progress": prog,
                 "progress_msg": gp.get("progress_msg", "")},
                stages=GRAPH_STAGES,
            )
            self.repo.update_step(step.id, ragflow_progress=prog,
                                   ragflow_progress_msg=gp.get("progress_msg", ""),
                                   progress=int(prog * 100))
            if prog >= 1.0:
                self.repo.update_step(step.id, status="done", progress=100,
                                      finished_at=datetime.now(timezone.utc))
                return
            time.sleep(poll_interval)
        raise RuntimeError("graph_build exceeded max_polls")

    def _apply_stages(self, task_id, st, *, stages=PARSE_STAGES):
        """Project one RAGFlow poll onto real stages and persist timestamps.

        Durations come from RAGFlow's own "(114.90s)" markers when present
        (server-side truth, excludes poll latency); we fall back to wall-clock
        between our own started_at/finished_at only when RAGFlow reports none.
        """
        snap = parse_progress(
            st.get("run", "UNSTART"), st.get("progress", 0),
            st.get("progress_msg", ""), stages=stages,
        )
        if snap.active_stage:
            self.repo.update_task(task_id, current_step=snap.active_stage)
        for mapped in snap.stages:
            rec = self.repo.ensure_step(task_id, mapped.name)
            updates: dict[str, Any] = {
                "progress": mapped.progress,
                "ragflow_progress_msg": mapped.detail or rec.ragflow_progress_msg,
            }
            if mapped.duration_ms is not None:
                updates["duration_ms"] = mapped.duration_ms  # RAGFlow's own timing
            if mapped.status.value != rec.status:
                updates["status"] = mapped.status.value
                if mapped.status is StepStatus.RUNNING and not rec.started_at:
                    updates["started_at"] = datetime.now(timezone.utc)
                if mapped.status in (StepStatus.DONE, StepStatus.FAILED):
                    finished = datetime.now(timezone.utc)
                    updates["finished_at"] = finished
                    # Wall-clock fallback only for real work stages: for pure
                    # markers (e.g. "received") it would just measure our own
                    # polling interval, which is meaningless.
                    if (mapped.duration_ms is None and rec.started_at
                            and mapped.name not in MARKER_ONLY_STAGES):
                        updates["duration_ms"] = int(
                            (finished - rec.started_at).total_seconds() * 1000)
            self.repo.update_step(rec.id, **updates)

    # ---- control: pause / resume / cancel / retry ----

    def pause(self, task_id: int, *, force: bool = False) -> None:
        """Graceful by default (§5.3): mark paused, poll loop exits at boundary.
        force=True also calls DELETE /chunks to stop the in-flight RAGFlow task."""
        task = self.repo.get_task(task_id)
        new = transition(TaskStatus(task.status), A.PAUSE)
        self.repo.update_task(task_id, status=new.value)
        if force and task.ragflow_doc_id:
            job = self.repo.get_job(task.job_id)
            self.adapter.stop_parse(job.kb_id, [task.ragflow_doc_id])

    def resume(self, task_id: int) -> None:
        """Return a paused task to running, clearing any backend abort flag.

        A force-pause told the backend to stop (``stop_parse``), which on the
        self-run pipeline sets a per-document abort flag. Resuming has to
        clear it, or the next run aborts immediately and the task looks stuck.
        """
        task = self.repo.get_task(task_id)
        new = transition(TaskStatus(task.status), A.RESUME)
        self.repo.update_task(task_id, status=new.value)
        clear = getattr(self.adapter, "clear_stop", None)
        if clear and task.ragflow_doc_id:
            job = self.repo.get_job(task.job_id)
            clear(job.kb_id, [task.ragflow_doc_id])

    def cancel(self, task_id: int) -> None:
        task = self.repo.get_task(task_id)
        new = transition(TaskStatus(task.status), A.CANCEL)
        self.repo.update_task(task_id, status=new.value)
        if task.ragflow_doc_id:
            job = self.repo.get_job(task.job_id)
            try:
                self.adapter.stop_parse(job.kb_id, [task.ragflow_doc_id])
            except Exception:
                pass  # best-effort; already cancelled in our state
        if task.current_step == "graph_build":
            try:
                self.adapter.delete_graph(job.kb_id)
            except Exception:
                pass

    def retry(self, task_id: int) -> None:
        task = self.repo.get_task(task_id)
        new = transition(TaskStatus(task.status), A.RETRY)
        # graph_build step retry_count++ signals run_task to DELETE /graph first
        gs = next((s for s in task.steps if s.step_name == "graph_build"), None)
        if gs:
            self.repo.update_step(gs.id, retry_count=gs.retry_count + 1)
        self.repo.update_task(task_id, status=new.value,
                              retry_count=task.retry_count + 1,
                              current_step=None, error=None)

    # ---- helpers ----

    def _is_paused(self, task_id: int) -> bool:
        t = self.repo.get_task(task_id)
        return TaskStatus(t.status) is TaskStatus.PAUSED

    def _set_status(self, task_id: int, action: A) -> None:
        task = self.repo.get_task(task_id)
        new = transition(TaskStatus(task.status), action)
        self.repo.update_task(task_id, status=new.value)


class _TaskPaused(Exception):
    """Internal signal: poll loop detected task was paused mid-flight."""


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
