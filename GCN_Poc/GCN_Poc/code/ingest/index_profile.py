"""Break down the index stage — it is ~75% of ingest time (M2 real data).

M2 told us where time goes at stage granularity: parse/chunk ~0%, embed ~25%,
index ~75%. That is too coarse to act on, because "index" is three different
systems: MinIO (object), MySQL (three rows), Elasticsearch (bulk of chunks).
This script times each one separately, so optimisation targets the real cost
rather than the label.

Also measures how ES write time scales with chunk count, which decides whether
batching or a larger bulk size is worth pursuing.

Runs INSIDE the RAGFlow container.

Usage:
    docker exec docker-ragflow-cpu-1 bash -c \\
      "cd /ragflow && PYTHONPATH=/ragflow python /ragflow/ingest/index_profile.py"
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, "/ragflow")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest.selfrun_pipeline import (  # noqa: E402
    EMBED_DIM, build_chunk_docs, make_tokenizer,
)

KB = "4ec640408cc711f19f3f45f212d2b89e"
TENANT = "56f78bf26ac611f187cd7db89d62ca74"

TEXT = ("PTR冷却泵额定流量640立方米每小时，额定扬程36米，转速1480转每分钟。"
        "故障现象：泵体振动超标。可能原因：叶轮不平衡、轴承磨损。")


def timed(fn, *a, **kw):
    t0 = time.time()
    out = fn(*a, **kw)
    return (time.time() - t0) * 1000, out


def profile_once(n_chunks: int, *, keep: bool) -> dict:
    from ingest import selfrun_writer as W

    doc_id = uuid.uuid4().hex
    name = f"profile_{doc_id[:8]}.txt"
    blob = (TEXT * 3).encode("utf-8")
    path = Path(f"/tmp/{name}")
    path.write_bytes(blob)

    tokenize, fine = make_tokenizer()
    texts = [f"{TEXT} 第{i}块" for i in range(n_chunks)]
    vectors = [[0.01] * EMBED_DIM for _ in texts]
    chunks = build_chunk_docs(texts, vectors, kb_id=KB, doc_id=doc_id,
                              doc_name=name, tokenize=tokenize,
                              fine_tokenize=fine)

    # warm the connections so the first call does not pay setup cost
    W._settings()

    t_minio, location = timed(W.put_object, KB, name, blob)
    t_mysql, _ = timed(W.insert_document_row, doc_id=doc_id, kb_id=KB,
                       tenant_id=TENANT, name=name, location=location,
                       size=len(blob), chunk_num=len(chunks))
    t_es, _ = timed(W.bulk_index_chunks, chunks, tenant_id=TENANT, kb_id=KB)

    if not keep:
        _cleanup(doc_id, KB, TENANT)
    path.unlink(missing_ok=True)

    return {"chunks": n_chunks, "minio_ms": t_minio,
            "mysql_ms": t_mysql, "es_ms": t_es,
            "total_ms": t_minio + t_mysql + t_es}


def _cleanup(doc_id: str, kb_id: str, tenant_id: str) -> None:
    """Remove what this probe wrote, so profiling does not pollute the KB."""
    try:
        from common import settings as s
        from rag.nlp.search import index_name
        s.docStoreConn.delete({"doc_id": doc_id}, index_name(tenant_id), kb_id)
    except Exception as exc:
        print(f"  [cleanup] ES: {exc}", file=sys.stderr)
    try:
        from api.db.services.document_service import DocumentService
        DocumentService.delete_by_id(doc_id)
    except Exception as exc:
        print(f"  [cleanup] MySQL: {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3,
                    help="repeats per size; 131 is noisy, single runs lie")
    ap.add_argument("--sizes", default="1,5,20,50",
                    help="chunk counts to profile")
    ap.add_argument("--keep", action="store_true",
                    help="do not delete what we wrote")
    ap.add_argument("--out", default="/tmp/index_profile.json")
    args = ap.parse_args()

    sizes = [int(x) for x in args.sizes.split(",")]
    print(f"[profile] sizes={sizes} rounds={args.rounds}")

    results: dict[int, list[dict]] = {}
    for n in sizes:
        runs = []
        for r in range(args.rounds):
            res = profile_once(n, keep=args.keep)
            runs.append(res)
            print(f"  n={n:3d} round {r+1}: minio={res['minio_ms']:7.1f}ms "
                  f"mysql={res['mysql_ms']:7.1f}ms es={res['es_ms']:8.1f}ms")
        results[n] = runs

    print("\n[profile] medians by chunk count")
    print(f"  {'chunks':>6s} {'minio':>9s} {'mysql':>9s} {'es':>10s} {'total':>10s} {'es/chunk':>9s}")
    summary = {}
    for n, runs in results.items():
        med = {k: statistics.median([r[k] for r in runs])
               for k in ("minio_ms", "mysql_ms", "es_ms", "total_ms")}
        summary[n] = med
        print(f"  {n:6d} {med['minio_ms']:9.1f} {med['mysql_ms']:9.1f} "
              f"{med['es_ms']:10.1f} {med['total_ms']:10.1f} "
              f"{med['es_ms']/n:9.1f}")

    # what dominates, at the largest size measured
    big = max(sizes)
    med = summary[big]
    print(f"\n[profile] share of index time at {big} chunks")
    for label, key in (("MinIO", "minio_ms"), ("MySQL", "mysql_ms"), ("ES", "es_ms")):
        print(f"  {label:6s} {med[key]/med['total_ms']*100:5.1f}%  ({med[key]:.0f}ms)")

    Path(args.out).write_text(
        json.dumps({"raw": {str(k): v for k, v in results.items()},
                    "median": {str(k): v for k, v in summary.items()}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[profile] saved -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
