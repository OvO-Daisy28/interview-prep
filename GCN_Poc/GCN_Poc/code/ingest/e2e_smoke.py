"""M1 end-to-end smoke against real RAGFlow (design §11 M1, §9 待验证1).

Runs ONE document through the real orchestrator: upload -> parse -> (graph?).
Records every progress_msg sample seen during polling, then prints the 5-step
projection so the mapping keywords (step_mapping.STEP_KEYWORDS) can be
calibrated against real 131 vocabulary.

Non-destructive: uploads a new document + parses it. Does NOT delete graphs,
restart workers, or touch existing PTR data. Uses PTR_普通RAG KB by default
(light, no graph build unless --build-graph).

Usage (key injected from your shell, never written into code):
  export RAGFLOW_API_KEY=...
  uv run --project code python code/ingest/e2e_smoke.py --file <path>

Or with the in-session ! prefix:
  ! RAGFLOW_API_KEY=... uv run --project "D:/lxt/learn/Best_Practices/GCN_Poc/code" python "D:/lxt/learn/Best_Practices/GCN_Poc/code/ingest/e2e_smoke.py" --file <path>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# allow running as script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest.orchestrator import Orchestrator  # noqa: E402
from ingest.pipeline_adapter import ChunksPipelineAdapter  # noqa: E402
from ingest.repository import InMemoryRepository  # noqa: E402

# POC-proven KB ids (operations.md §2.1)
KB_NORMAL = "4ec640408cc711f19f3f45f212d2b89e"
KB_GRAPH = "4ec8cbda8cc711f19f3f45f212d2b89e"


class _RecordingAdapter(ChunksPipelineAdapter):
    """Wraps the real adapter; records every progress_msg sample for calibration."""

    def __init__(self):
        self.samples: list[dict] = []

    def get_document_status(self, kb_id, doc_id):
        st = super().get_document_status(kb_id, doc_id)
        self.samples.append(dict(st))
        return st

    def get_graph_build_progress(self, kb_id):
        gp = super().get_graph_build_progress(kb_id)
        self.samples.append({"_phase": "graph", **gp})
        return gp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="document path to upload")
    ap.add_argument("--kb-id", default=KB_NORMAL,
                    help=f"dataset id (default PTR_普通RAG {KB_NORMAL})")
    ap.add_argument("--build-graph", action="store_true",
                    help="also run GraphRAG build (heavy, ~20min, uses KB_GRAPH)")
    ap.add_argument("--poll-interval", type=float, default=2.0)
    args = ap.parse_args()

    fpath = Path(args.file)
    if not fpath.exists():
        print(f"file not found: {fpath}", file=sys.stderr)
        return 2

    repo = InMemoryRepository()
    adapter = _RecordingAdapter()
    orch = Orchestrator(repo, adapter)

    kb = KB_GRAPH if args.build_graph else args.kb_id
    options = {"build_graph": args.build_graph}

    print(f"[e2e] kb={kb} file={fpath.name} build_graph={args.build_graph}")
    jid = orch.create_job(kb, [{"name": fpath.name, "path_or_url": str(fpath)}],
                          options=options)
    tid = repo.get_job(jid).tasks[0].id
    print(f"[e2e] job={jid} task={tid} starting run_task...")

    t0 = time.time()
    try:
        orch.run_task(tid, poll_interval=args.poll_interval, max_polls=600)
    except Exception as exc:
        print(f"[e2e] FAILED after {time.time()-t0:.1f}s: {exc}", file=sys.stderr)
        _dump(adapter, repo, jid, ok=False)
        return 1

    elapsed = time.time() - t0
    job = orch.get_job(jid)
    task = job["tasks"][0]
    print(f"[e2e] done in {elapsed:.1f}s, task status={task['status']}")
    _dump(adapter, repo, jid, ok=True)
    return 0


def _dump(adapter, repo, jid, *, ok):
    print("\n=== progress_msg samples (for step_mapping calibration) ===")
    for i, s in enumerate(adapter.samples):
        msg = s.get("progress_msg", s.get("_phase", ""))
        print(f"  [{i:02d}] run={s.get('run','?')} prog={s.get('progress','?')} msg={msg!r}")
    job = repo.get_job(jid)
    print("\n=== 5-step projection ===")
    for t in job.tasks:
        print(f"task {t.id} {t.doc_name} status={t.status}")
        for s in t.steps:
            print(f"  {s.step_name:12s} status={s.status:8s} prog={s.progress:3d}"
                  f" dur={s.duration_ms}")
    out = {"ok": ok, "samples": adapter.samples,
           "tasks": [{"name": t.doc_name, "status": t.status,
                      "steps": [{"name": s.step_name, "status": s.status,
                                 "progress": s.progress, "duration_ms": s.duration_ms}
                                for s in t.steps]} for t in job.tasks]}
    d = Path(__file__).resolve().parents[2] / "test" / "results" / "e2e"
    d.mkdir(parents=True, exist_ok=True)
    fp = d / f"m1_smoke_{int(time.time())}.json"
    fp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] {fp}")


if __name__ == "__main__":
    raise SystemExit(main())
