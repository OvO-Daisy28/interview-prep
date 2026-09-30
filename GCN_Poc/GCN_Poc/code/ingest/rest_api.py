"""REST API — unified orchestration interface (design §7, §8 layer 1).

Named rest_api rather than api on purpose: this package is deployed
next to RAGFlow, whose own top-level package is api. A module named
api.py here shadows it and breaks every import api.db... inside the
worker process ("'api' is not a package").

Exposes job/task/queue verbs only; RAGFlow pipeline type is hidden behind
the adapter (§8 layer 3) and status mapping is configurable (§8 layer 2).
Pipeline type swap (/chunks ↔ /ingest) changes nothing here.

M1 background execution: a daemon thread per trigger runs
scheduler.run_pending_once() (serial). Production should use a bounded
worker pool (M2 concurrency limiting, §6).
"""

from __future__ import annotations

import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ingest.orchestrator import Orchestrator
from ingest.scheduler import Scheduler


class CreateJobRequest(BaseModel):
    kb_id: str
    files: list[dict]
    options: dict = {}
    priority: int = 0


class PatchTaskRequest(BaseModel):
    status: str | None = None
    priority: int | None = None


def create_app(orchestrator: Orchestrator, scheduler: Scheduler) -> FastAPI:
    app = FastAPI(title="GCN Ingest Orchestration")
    app.state.orchestrator = orchestrator
    app.state.scheduler = scheduler

    def _kick_worker() -> None:
        threading.Thread(target=scheduler.run_pending_once, daemon=True).start()

    @app.get("/demo", response_class=HTMLResponse)
    def demo_page():
        """Review console: live endpoints, the decisions behind them, measurements.

        Served from the app itself so a demo needs no second deployment, and so
        what the reviewer clicks is unambiguously the same service.
        """
        from ingest.demo_page import DEMO_HTML

        return HTMLResponse(DEMO_HTML)

    @app.post("/ingest/jobs")
    def create_job(req: CreateJobRequest):
        jid = orchestrator.create_job(req.kb_id, req.files, req.options, req.priority)
        _kick_worker()
        return {"job_id": jid}

    @app.get("/ingest/jobs/{job_id}")
    def get_job(job_id: int):
        job = orchestrator.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.post("/ingest/tasks/{task_id}/pause")
    def pause(task_id: int, force: bool = False):
        orchestrator.pause(task_id, force=force)
        return {"task_id": task_id, "status": "paused", "force": force}

    @app.post("/ingest/tasks/{task_id}/resume")
    def resume(task_id: int):
        orchestrator.resume(task_id)
        _kick_worker()
        return {"task_id": task_id, "status": "running"}

    @app.post("/ingest/tasks/{task_id}/retry")
    def retry(task_id: int):
        orchestrator.retry(task_id)
        _kick_worker()
        return {"task_id": task_id, "status": "pending"}

    @app.post("/ingest/tasks/{task_id}/cancel")
    def cancel(task_id: int):
        orchestrator.cancel(task_id)
        return {"task_id": task_id, "status": "cancelled"}

    @app.patch("/ingest/tasks/{task_id}")
    def patch_task(task_id: int, req: PatchTaskRequest):
        fields: dict = {}
        if req.priority is not None:
            fields["priority"] = req.priority
        if req.status is not None:
            fields["status"] = req.status
        orchestrator.repo.update_task(task_id, **fields)
        return {"task_id": task_id, **fields}

    @app.get("/ingest/queue")
    def queue(kb_id: str | None = None, status: str | None = None):
        statuses = ["pending", "running", "failed", "succeeded", "cancelled", "paused"]
        counts = {s: len(orchestrator.repo.list_tasks_by_status(s)) for s in statuses}
        return {"counts": counts}

    @app.post("/ingest/upload")
    async def upload(kb_id: str = Form(...), files: list[UploadFile] = File(...),
                     priority: int = Form(0), build_graph: bool = Form(False)):
        """Accept real files from a browser and queue them.

        The other entry point, POST /ingest/jobs, takes paths — fine for
        server-side callers whose files already sit on disk, useless for a
        person with a document on their laptop. This one receives the bytes,
        stages them, and creates the same job, so both paths converge on one
        pipeline.
        """
        staged: list[dict[str, str]] = []
        stage_dir = Path(tempfile.gettempdir()) / "gcn_uploads"
        stage_dir.mkdir(parents=True, exist_ok=True)

        for upload_file in files:
            name = Path(upload_file.filename or "unnamed").name   # strip any path
            # 磁盘暂存名只用 uuid（32 字符），不用原文件名——法律文档名常超 255 字节
            # 触发 ENAMETOOLONG（OSError 36）。原文件名存进 name 字段，pipeline 用它做 doc_name。
            target = stage_dir / f"{uuid.uuid4().hex}.docx"
            with target.open("wb") as fh:
                while chunk := await upload_file.read(1024 * 1024):
                    fh.write(chunk)
            staged.append({"name": name, "path_or_url": str(target)})

        if not staged:
            raise HTTPException(status_code=400, detail="no files received")

        job_id = orchestrator.create_job(
            kb_id, staged, {"build_graph": build_graph}, priority)
        _kick_worker()
        return {"job_id": job_id, "accepted": len(staged),
                "files": [f["name"] for f in staged]}

    @app.get("/ingest/datasets")
    def datasets():
        """List the knowledge bases documents can be sent to.

        Exists so a UI can offer names instead of asking someone to paste a
        32-character id. Queries RAGFlow's knowledgebase table directly; if
        that is unavailable the caller still gets a usable (empty) answer
        rather than an error, because picking a target is not worth failing
        the page over.
        """
        try:
            from api.db.services.knowledgebase_service import KnowledgebaseService

            kbs = (KnowledgebaseService.model
                   .select()
                   .order_by(KnowledgebaseService.model.create_time.desc())
                   .limit(60))
            return {"datasets": [
                {"id": kb.id, "name": kb.name,
                 "doc_num": getattr(kb, "doc_num", 0),
                 "chunk_num": getattr(kb, "chunk_num", 0),
                 "parser_id": getattr(kb, "parser_id", "")}
                for kb in kbs
            ]}
        except Exception as exc:
            return {"datasets": [], "note": f"unavailable: {exc}"}

    @app.get("/ingest/schema")
    def schema():
        """Expose how task state is stored, for review and for operators.

        Reviewers ask where the state lives; operators need the column list
        without shelling into the database. Served from the live table
        definitions, so it cannot drift from reality the way a copied diagram
        would.
        """
        repo = orchestrator.repo
        query = getattr(repo, "_query", None)
        if query is None:
            return {"backend": "in-memory",
                    "note": "state is not persisted in this configuration"}

        tables: list[dict] = []
        for table in ("ingest_job", "ingest_task", "ingest_step"):
            try:
                cols = query(
                    "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, "
                    "COLUMN_COMMENT FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
                    "ORDER BY ORDINAL_POSITION", (table,))
                count = query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
            except Exception as exc:
                tables.append({"table": table, "error": str(exc)})
                continue
            tables.append({
                "table": table,
                "rows": count,
                "columns": [
                    {"name": c["COLUMN_NAME"], "type": c["COLUMN_TYPE"],
                     "nullable": c["IS_NULLABLE"] == "YES",
                     "key": c["COLUMN_KEY"], "comment": c["COLUMN_COMMENT"]}
                    for c in cols
                ],
            })
        return {"backend": "MySQL", "database": repo._cfg["database"],
                "tables": tables}

    return app
