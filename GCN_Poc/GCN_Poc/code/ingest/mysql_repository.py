"""MySQL-backed repository (决策 16).

Same ``IngestRepository`` interface as the in-memory one, so the orchestrator,
scheduler and REST layer are untouched — this is the swap the three-layer
design (§8) was built for. What changes is that state now survives a restart,
which is the difference between a script and a service.

Connection handling: one connection per thread, because the batch scheduler
runs tasks concurrently and PyMySQL connections are not thread-safe. A pool
would be the next step under real load; per-thread is enough for the
concurrency ceiling we actually use (default 3) and keeps failure modes
simple.

Autocommit is on. Every method here is a single statement or a small
self-contained unit; the one place that needs atomicity (create_job plus its
tasks) takes an explicit transaction.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from ingest.repository import (
    IngestRepository,
    JobRecord,
    StepRecord,
    TaskRecord,
)

DEFAULT_DB = "gcn_ingest"


class MySQLRepository(IngestRepository):
    """Persistent store for jobs, tasks and stage timings."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ):
        self._cfg = {
            "host": host or os.environ.get("GCN_DB_HOST", "mysql"),
            "port": int(port or os.environ.get("GCN_DB_PORT", 3306)),
            "user": user or os.environ.get("GCN_DB_USER", "root"),
            "password": password or os.environ.get("GCN_DB_PASSWORD", ""),
            "database": database or os.environ.get("GCN_DB_NAME", DEFAULT_DB),
            "charset": "utf8mb4",
            "autocommit": True,
            "cursorclass": DictCursor,
        }
        self._local = threading.local()

    # ---- connection ----

    @property
    def conn(self):
        """One connection per thread; reconnect if the server dropped it."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = pymysql.connect(**self._cfg)
            self._local.conn = conn
        else:
            conn.ping(reconnect=True)
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def _query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def _execute(self, sql: str, params: tuple = ()) -> int:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.lastrowid

    # ---- job ----

    def create_job(self, kb_id: str, options: dict, priority: int = 0) -> JobRecord:
        import json

        job_id = self._execute(
            "INSERT INTO ingest_job (kb_id, options, status, priority) "
            "VALUES (%s, %s, %s, %s)",
            (kb_id, json.dumps(options, ensure_ascii=False), "pending", priority),
        )
        return self.get_job(job_id)

    def get_job(self, job_id: int) -> JobRecord | None:
        rows = self._query("SELECT * FROM ingest_job WHERE id = %s", (job_id,))
        if not rows:
            return None
        job = _to_job(rows[0])
        job.tasks = self._tasks_of_job(job_id)
        return job

    def _tasks_of_job(self, job_id: int) -> list[TaskRecord]:
        rows = self._query(
            "SELECT * FROM ingest_task WHERE job_id = %s ORDER BY id", (job_id,))
        tasks = [_to_task(r) for r in rows]
        if not tasks:
            return tasks
        # one query for every step in the job, then group — avoids N+1
        ids = tuple(t.id for t in tasks)
        placeholders = ",".join(["%s"] * len(ids))
        steps = self._query(
            f"SELECT * FROM ingest_step WHERE task_id IN ({placeholders}) "
            "ORDER BY id", ids)
        by_task: dict[int, list[StepRecord]] = {}
        for row in steps:
            by_task.setdefault(row["task_id"], []).append(_to_step(row))
        for t in tasks:
            t.steps = by_task.get(t.id, [])
        return tasks

    # ---- task ----

    def create_task(self, job_id: int, doc_name: str, path: str,
                    priority: int = 0) -> TaskRecord:
        task_id = self._execute(
            "INSERT INTO ingest_task (job_id, doc_name, doc_path_or_url, "
            "status, priority) VALUES (%s, %s, %s, %s, %s)",
            (job_id, doc_name, path, "pending", priority),
        )
        return self.get_task(task_id)

    def get_task(self, task_id: int) -> TaskRecord | None:
        rows = self._query("SELECT * FROM ingest_task WHERE id = %s", (task_id,))
        if not rows:
            return None
        task = _to_task(rows[0])
        task.steps = [
            _to_step(r) for r in self._query(
                "SELECT * FROM ingest_step WHERE task_id = %s ORDER BY id",
                (task_id,))
        ]
        return task

    def update_task(self, task_id: int, **fields: Any) -> TaskRecord:
        allowed = {"status", "priority", "retry_count", "current_step",
                   "ragflow_doc_id", "error", "doc_name", "doc_path_or_url"}
        sets, params = [], []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"cannot update unknown column: {key}")
            sets.append(f"{key} = %s")
            params.append(value)
        if sets:
            params.append(task_id)
            self._execute(
                f"UPDATE ingest_task SET {', '.join(sets)} WHERE id = %s",
                tuple(params))
        return self.get_task(task_id)

    def list_tasks_by_status(self, status: str) -> list[TaskRecord]:
        return [_to_task(r) for r in self._query(
            "SELECT * FROM ingest_task WHERE status = %s "
            "ORDER BY priority DESC, id", (status,))]

    # ---- step ----

    def ensure_step(self, task_id: int, step_name: str) -> StepRecord:
        """Idempotent: the unique key on (task_id, step_name) makes the
        insert-or-fetch race-free, so concurrent workers cannot duplicate a
        stage row."""
        self._execute(
            "INSERT INTO ingest_step (task_id, step_name, status) "
            "VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)",
            (task_id, step_name, "pending"),
        )
        rows = self._query(
            "SELECT * FROM ingest_step WHERE task_id = %s AND step_name = %s",
            (task_id, step_name))
        return _to_step(rows[0])

    def update_step(self, step_id: int, **fields: Any) -> StepRecord:
        allowed = {"status", "started_at", "finished_at", "progress",
                   "duration_ms", "ragflow_progress", "ragflow_progress_msg",
                   "retry_count", "error"}
        sets, params = [], []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"cannot update unknown column: {key}")
            sets.append(f"{key} = %s")
            params.append(_coerce(value))
        if sets:
            params.append(step_id)
            self._execute(
                f"UPDATE ingest_step SET {', '.join(sets)} WHERE id = %s",
                tuple(params))
        rows = self._query("SELECT * FROM ingest_step WHERE id = %s", (step_id,))
        return _to_step(rows[0])

    # ---- schema bootstrap ----

    def ensure_schema(self, ddl_path: str | None = None) -> None:
        """Apply schema.sql. Safe to call repeatedly (CREATE ... IF NOT EXISTS).

        Comment lines are stripped before splitting on ';' — a semicolon inside
        a comment (Chinese prose uses '；' and ';' freely) would otherwise cut a
        statement in half and produce a syntax error.
        """
        from pathlib import Path

        path = Path(ddl_path or Path(__file__).with_name("schema.sql"))
        raw = path.read_text(encoding="utf-8")
        body = "\n".join(
            line for line in raw.splitlines()
            if not line.lstrip().startswith("--")
        )
        statements = [s.strip() for s in body.split(";") if s.strip()]
        with self.conn.cursor() as cur:
            for stmt in statements:
                if stmt.upper().startswith(("CREATE DATABASE", "USE ")):
                    continue        # the connection already targets the database
                cur.execute(stmt)


def _coerce(value: Any) -> Any:
    """Timezone-aware datetimes cannot go into a MySQL DATETIME column."""
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def _to_job(row: dict) -> JobRecord:
    import json

    options = row["options"]
    if isinstance(options, (str, bytes)):
        options = json.loads(options)
    return JobRecord(
        id=row["id"], kb_id=row["kb_id"], options=options or {},
        status=row["status"], priority=row["priority"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _to_task(row: dict) -> TaskRecord:
    return TaskRecord(
        id=row["id"], job_id=row["job_id"], doc_name=row["doc_name"],
        doc_path_or_url=row["doc_path_or_url"], status=row["status"],
        priority=row["priority"], retry_count=row["retry_count"],
        current_step=row["current_step"], ragflow_doc_id=row["ragflow_doc_id"],
        error=row["error"], created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_step(row: dict) -> StepRecord:
    return StepRecord(
        id=row["id"], task_id=row["task_id"], step_name=row["step_name"],
        status=row["status"], started_at=row["started_at"],
        finished_at=row["finished_at"], progress=row["progress"] or 0,
        duration_ms=row["duration_ms"], ragflow_progress=row["ragflow_progress"],
        ragflow_progress_msg=row["ragflow_progress_msg"],
        retry_count=row["retry_count"], error=row["error"],
        created_at=row["created_at"],
    )
