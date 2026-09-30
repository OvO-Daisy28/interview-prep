"""Hunt the index-stage p90 tail (p50 8.5s vs p90 28s after the refresh fix).

The earlier profile (index_profile.py) measured MinIO/MySQL/ES one document at
a time and found ES's refresh wait. With that fixed the median dropped to
~8.5s, but p90 stayed near 28s — a spread that big is not the same cost, it is
contention or a retry that only shows up sometimes.

Serial profiling cannot see it: the tail appears under concurrency. So this
script runs the same write path from N threads, times every sub-operation,
and reports per-operation percentiles plus the worst individual samples. It
also runs a serial baseline so contention is separable from raw latency.

Runs INSIDE the RAGFlow container.

Usage:
    docker exec docker-ragflow-cpu-1 bash -c \\
      "cd /ragflow && PYTHONPATH=/ragflow python /ragflow/ingest/tail_probe.py \\
       --docs 12 --concurrency 3"
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, "/ragflow")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest.selfrun_pipeline import EMBED_DIM, build_chunk_docs, make_tokenizer  # noqa: E402

KB = "4ec640408cc711f19f3f45f212d2b89e"
TENANT = "56f78bf26ac611f187cd7db89d62ca74"
TEXT = "PTR冷却泵额定流量640立方米每小时，额定扬程36米，转速1480转每分钟。"

_written: list[str] = []
_lock = threading.Lock()


def one_write(idx: int, n_chunks: int) -> dict:
    """Run the write path once, timing each sub-operation separately."""
    from ingest import selfrun_writer as W

    doc_id = uuid.uuid4().hex
    name = f"tail_{idx:03d}_{doc_id[:6]}.txt"
    blob = (TEXT * 5).encode("utf-8")
    path = Path(f"/tmp/{name}")
    path.write_bytes(blob)

    tokenize, fine = make_tokenizer()
    texts = [f"{TEXT} 第{i}块" for i in range(n_chunks)]
    chunks = build_chunk_docs(texts, [[0.01] * EMBED_DIM] * n_chunks,
                              kb_id=KB, doc_id=doc_id, doc_name=name,
                              tokenize=tokenize, fine_tokenize=fine)

    marks: dict[str, float] = {}
    t = time.time()
    location = W.put_object(KB, name, blob)
    marks["minio"] = (time.time() - t) * 1000

    # split the MySQL side: the document row vs the file/file2document rows,
    # because the latter also does a folder lookup/creation per call
    t = time.time()
    W.insert_document_row(doc_id=doc_id, kb_id=KB, tenant_id=TENANT,
                          name=name, location=location, size=len(blob),
                          chunk_num=len(chunks))
    marks["mysql"] = (time.time() - t) * 1000

    t = time.time()
    W.bulk_index_chunks(chunks, tenant_id=TENANT, kb_id=KB)
    marks["es"] = (time.time() - t) * 1000

    marks["total"] = sum(marks[k] for k in ("minio", "mysql", "es"))
    path.unlink(missing_ok=True)
    with _lock:
        _written.append(doc_id)
    return {"idx": idx, **marks}


def cleanup() -> None:
    from common import settings as s
    from rag.nlp.search import index_name
    from api.db.services.document_service import DocumentService

    for doc_id in _written:
        try:
            s.docStoreConn.delete({"doc_id": doc_id}, index_name(TENANT), KB)
        except Exception:
            pass
        try:
            DocumentService.delete_by_id(doc_id)
        except Exception:
            pass


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


def report(label: str, runs: list[dict]) -> dict:
    print(f"\n[{label}] n={len(runs)}")
    print(f"  {'op':8s} {'p50':>9s} {'p90':>9s} {'max':>9s} {'spread':>8s}")
    summary = {}
    for op in ("minio", "mysql", "es", "total"):
        vals = [r[op] for r in runs]
        p50, p90, mx = statistics.median(vals), pct(vals, 0.9), max(vals)
        summary[op] = {"p50": p50, "p90": p90, "max": mx}
        spread = mx / p50 if p50 else 0
        print(f"  {op:8s} {p50:9.1f} {p90:9.1f} {mx:9.1f} {spread:7.1f}x")

    worst = sorted(runs, key=lambda r: -r["total"])[:3]
    print("  worst samples (ms):")
    for w in worst:
        print(f"    #{w['idx']:3d} total={w['total']:8.1f}  "
              f"minio={w['minio']:7.1f} mysql={w['mysql']:8.1f} es={w['es']:8.1f}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=12)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--chunks", type=int, default=5)
    ap.add_argument("--out", default="/tmp/tail_probe.json")
    args = ap.parse_args()

    from ingest import selfrun_writer as W
    W._settings()   # warm connections; first call must not skew sample 1

    print(f"[tail] docs={args.docs} concurrency={args.concurrency} "
          f"chunks={args.chunks}")

    serial = [one_write(i, args.chunks) for i in range(min(6, args.docs))]
    s_sum = report("serial baseline", serial)

    conc: list[dict] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(one_write, 100 + i, args.chunks)
                   for i in range(args.docs)]
        for f in as_completed(futures):
            conc.append(f.result())
    wall = time.time() - t0
    c_sum = report(f"concurrent x{args.concurrency}", conc)
    print(f"  wall clock: {wall:.1f}s")

    print("\n[tail] contention factor (concurrent p50 / serial p50)")
    for op in ("minio", "mysql", "es", "total"):
        base = s_sum[op]["p50"]
        factor = c_sum[op]["p50"] / base if base else 0
        verdict = "contended" if factor > 1.8 else "flat"
        print(f"  {op:8s} {factor:5.2f}x  {verdict}")

    cleanup()
    Path(args.out).write_text(
        json.dumps({"serial": serial, "concurrent": conc,
                    "serial_summary": s_sum, "concurrent_summary": c_sum,
                    "wall_seconds": round(wall, 2)},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[tail] saved -> {args.out} (cleaned up {len(_written)} docs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
