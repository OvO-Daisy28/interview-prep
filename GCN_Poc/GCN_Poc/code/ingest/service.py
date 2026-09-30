"""Service entrypoint: wire the pieces and run as a long-lived process.

Until now everything ran as scripts — state lived in memory and died with the
process. This is the same code assembled as a service: MySQL for state, a
background worker draining the queue, and warm-up paid at boot so the first
document does not absorb ~33s of initialisation (see progress-board.md).

Usage (inside the RAGFlow container, which is where the datastores and the
embedding service are reachable):

    PYTHONPATH=/ragflow python -m ingest.service --host 0.0.0.0 --port 9800

Configuration is environment-first, so the same image runs in any environment:

    GCN_DB_HOST / GCN_DB_PORT / GCN_DB_USER / GCN_DB_PASSWORD / GCN_DB_NAME
    GCN_TENANT_ID          tenant whose ES index we write into
    GCN_MAX_CONCURRENT     worker concurrency (default 3)
    GCN_WARM_KB            optional KB id to warm the connection pools against
    EMBED_BASE_URL / EMBED_MODEL
    MINERU_URL             enables PDF support when set
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
import time

logger = logging.getLogger("ingest.service")


def build_app(*, in_memory: bool = False):
    """Assemble the service. Returns (app, scheduler, stop_worker)."""
    from ingest.orchestrator import Orchestrator
    from ingest.rest_api import create_app
    from ingest.scheduler import Scheduler
    from ingest.selfrun_pipeline import SelfRunPipeline

    tenant_id = os.environ.get("GCN_TENANT_ID", "")
    if not tenant_id:
        raise SystemExit("GCN_TENANT_ID is required")

    if in_memory:
        from ingest.repository import InMemoryRepository
        repo = InMemoryRepository()
        logger.warning("using in-memory store: state will not survive restart")
    else:
        from ingest.mysql_repository import MySQLRepository
        repo = MySQLRepository()
        repo.ensure_schema()
        logger.info("MySQL store ready (%s)", repo._cfg["database"])

    mineru = None
    mineru_url = os.environ.get("MINERU_URL")
    if mineru_url:
        from ingest.mineru_client import MinerUClient
        mineru = MinerUClient(mineru_url)
        logger.info("MinerU enabled at %s (healthy=%s)", mineru_url, mineru.health())
    else:
        logger.info("MinerU not configured: PDF ingestion will fail explicitly")

    pipeline = SelfRunPipeline(
        tenant_id=tenant_id,
        embed_url=os.environ.get("EMBED_BASE_URL")
        or "http://192.168.80.1:18001/v1",
        embed_model=os.environ.get("EMBED_MODEL", "bge-base"),
        mineru=mineru,
    )

    warm_kb = os.environ.get("GCN_WARM_KB")
    try:
        timings = pipeline.warm_up(kb_id=warm_kb)
    except Exception as exc:
        # Warm-up imports RAGFlow's settings module, which only exists inside
        # the RAGFlow container. Failing to pre-warm costs latency on the first
        # document (~33s, see progress-board.md); it must not stop the service
        # from starting, or the process becomes undeployable outside that image.
        logger.warning("warm-up skipped (%s): first document pays the cold start",
                       exc)
        timings = {}
    if timings:
        logger.info(
            "warm-up done: settings=%.0fms mysql=%.0fms docstore=%.0fms",
            timings.get("settings_ms", 0), timings.get("mysql_ms", 0),
            timings.get("docstore_ms", 0))

    orchestrator = Orchestrator(repo, pipeline)
    scheduler = Scheduler(
        repo, orchestrator,
        max_concurrent=int(os.environ.get("GCN_MAX_CONCURRENT", 3)))

    app = create_app(orchestrator, scheduler)
    stop = _start_worker(scheduler)
    return app, scheduler, stop


def _start_worker(scheduler, *, idle_sleep: float = 2.0):
    """Drain pending work in the background.

    A REST call should return as soon as the job is recorded; the actual
    ingestion happens here. Polling (rather than waking on submit) keeps this
    simple and also picks up work left behind by a previous run — which is the
    reason the state moved into MySQL in the first place.
    """
    stopping = threading.Event()

    def loop():
        logger.info("worker started (max_concurrent=%d)", scheduler.max_concurrent)
        while not stopping.is_set():
            try:
                result = scheduler.run_batch(limit=scheduler.max_concurrent)
                if result.total:
                    logger.info("batch: %d succeeded, %d failed, %d skipped",
                                len(result.succeeded), len(result.failed),
                                len(result.skipped))
                else:
                    stopping.wait(idle_sleep)
            except Exception:
                logger.exception("worker iteration failed; continuing")
                stopping.wait(idle_sleep)
        logger.info("worker stopped")

    thread = threading.Thread(target=loop, name="ingest-worker", daemon=True)
    thread.start()

    def stop():
        stopping.set()
        thread.join(timeout=30)

    return stop


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=9800)
    ap.add_argument("--in-memory", action="store_true",
                    help="run without MySQL (state lost on restart)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    app, scheduler, stop_worker = build_app(in_memory=args.in_memory)

    import uvicorn

    config = uvicorn.Config(app, host=args.host, port=args.port,
                            log_level=args.log_level.lower())
    server = uvicorn.Server(config)

    def shutdown(signum, _frame):
        logger.info("signal %s received, shutting down", signum)
        stop_worker()
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, shutdown)
        except ValueError:
            pass        # not on the main thread (e.g. under a test harness)

    logger.info("serving on %s:%d", args.host, args.port)
    started = time.time()
    try:
        server.run()
    finally:
        stop_worker()
        logger.info("stopped after %.0fs", time.time() - started)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
