"""Batch scheduler — priority selection + bounded concurrency (design §5.5, §6).

M1 was serial (one task at a time). M2 adds bounded concurrent execution with
per-task failure isolation, which is what makes batch import usable.

Why bounded, and why small by default:
RAGFlow runs a single ``task_executor`` worker by default (operations.md 坑#1;
GraphRAG needs a separate ``-t graphrag`` worker). Firing N uploads at once
does not make RAGFlow parse them N times faster — it just piles messages into
the Redis stream. Worse, 131 has been OOM-killed before under load
(decision 10). So the orchestration layer throttles submission instead of
letting the queue explode; ``max_concurrent`` is a knob to be calibrated by
the 1/10/100 ladder benchmark (decision 8/10), not a guess to trust blindly.

Failure isolation (PM prototype §72 "单份失败不影响批量"): each task runs in
its own thread with its own try/except. One document failing marks only that
task ``failed``; siblings keep running and the batch continues.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from ingest.orchestrator import Orchestrator
from ingest.repository import IngestRepository

logger = logging.getLogger(__name__)

# Conservative default: RAGFlow's single worker is the real bottleneck, so a
# high number buys nothing but queue depth. Calibrate with the ladder test.
DEFAULT_MAX_CONCURRENT = 3


@dataclass
class BatchResult:
    """Outcome of one batch run — per-task, never aggregated into a single flag."""

    succeeded: list[int]
    failed: list[int]
    skipped: list[int]      # not runnable (paused/cancelled/terminal)

    @property
    def total(self) -> int:
        return len(self.succeeded) + len(self.failed) + len(self.skipped)


class Scheduler:
    def __init__(
        self,
        repo: IngestRepository,
        orchestrator: Orchestrator,
        *,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ):
        self.repo = repo
        self.orchestrator = orchestrator
        self.max_concurrent = max(1, int(max_concurrent))
        self._peak_lock = threading.Lock()
        self._in_flight = 0
        self.peak_in_flight = 0   # observed concurrency, asserted by tests

    # ---- selection ----

    def pick_next_task(self) -> int | None:
        """Highest priority first; FIFO (lower id) breaks ties."""
        tasks = self.repo.list_tasks_by_status("pending")
        if not tasks:
            return None
        return max(tasks, key=lambda t: (t.priority, -t.id)).id

    def pending_in_priority_order(self, limit: int | None = None) -> list[int]:
        """All pending task ids, highest priority first, FIFO within a priority."""
        tasks = self.repo.list_tasks_by_status("pending")
        ordered = sorted(tasks, key=lambda t: (-t.priority, t.id))
        ids = [t.id for t in ordered]
        return ids[:limit] if limit else ids

    # ---- execution ----

    def run_pending_once(self) -> bool:
        """Serial: run a single pending task (kept for M1 compatibility)."""
        tid = self.pick_next_task()
        if tid is None:
            return False
        self._run_one(tid)
        return True

    def run_batch(
        self,
        *,
        limit: int | None = None,
        poll_interval: float = 1.0,
        max_polls: int = 10000,
    ) -> BatchResult:
        """Run pending tasks concurrently, bounded by ``max_concurrent``.

        Each task is isolated: an exception in one never propagates to the
        others, and the batch always returns a per-task breakdown rather than
        a single pass/fail flag.
        """
        task_ids = self.pending_in_priority_order(limit)
        result = BatchResult(succeeded=[], failed=[], skipped=[])
        if not task_ids:
            return result

        self.peak_in_flight = 0
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as pool:
            futures = {
                pool.submit(
                    self._run_one, tid,
                    poll_interval=poll_interval, max_polls=max_polls,
                ): tid
                for tid in task_ids
            }
            for fut in as_completed(futures):
                tid = futures[fut]
                try:
                    fut.result()
                except Exception as exc:   # isolation boundary
                    logger.warning("task %s failed: %s", tid, exc)
                task = self.repo.get_task(tid)
                status = task.status if task else "unknown"
                if status == "succeeded":
                    result.succeeded.append(tid)
                elif status == "failed":
                    result.failed.append(tid)
                else:
                    result.skipped.append(tid)
        return result

    def _run_one(self, task_id: int, *, poll_interval: float = 1.0,
                 max_polls: int = 10000) -> None:
        """Run one task, tracking observed concurrency for assertions."""
        with self._peak_lock:
            self._in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self._in_flight)
        try:
            self.orchestrator.run_task(
                task_id, poll_interval=poll_interval, max_polls=max_polls)
        finally:
            with self._peak_lock:
                self._in_flight -= 1

    # ---- batch status aggregation ----

    def job_stats(self, job_id: int) -> dict[str, int]:
        """Per-status counts for one job (feeds GET /ingest/jobs/{id})."""
        job = self.repo.get_job(job_id)
        stats = {s: 0 for s in
                 ("pending", "running", "succeeded", "failed", "cancelled", "paused")}
        if not job:
            return stats
        for t in job.tasks:
            stats[t.status] = stats.get(t.status, 0) + 1
        return stats
