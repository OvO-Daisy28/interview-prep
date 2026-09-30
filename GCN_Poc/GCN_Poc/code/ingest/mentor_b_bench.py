"""mentor 方案 B 并发压测（基于 m2_batch_run.py 改造）。

读真 .docx 文档清单（不用虚拟文档），用 SelfRunPipeline + Scheduler(max_concurrent=N)
跑方案 B 自建流水线，输出统一 JSON（墙钟/吞吐/每阶段 duration_ms/失败数）。

跟 m2_batch_run.py 的差异：
- 文档来源：真 .docx（读 ab_doc_list.json 清单）而非 make_docs 虚拟 txt
- 输出格式：与 native_upload_test.py 对齐，便于报告生成
- 不 inject failure（真文档已预筛纯净）

Must run INSIDE the RAGFlow container（方案B 需 192.168.80.1 embedding + MinIO/ES）。

Usage:
    docker exec docker-ragflow-cpu-1 python3 /ragflow/ingest/mentor_b_bench.py \
      --kb-id <KB_ID> --docs-dir /ragflow/ingest/_abtest_docs \
      --docs-json /ragflow/ingest/ab_doc_list.json \
      --count 50 --concurrency 3 --label c3 --out /tmp/bench_c3.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, "/ragflow")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest.orchestrator import Orchestrator  # noqa: E402
from ingest.mysql_repository import MySQLRepository  # noqa: E402
from ingest.repository import InMemoryRepository  # noqa: E402
from ingest.scheduler import Scheduler  # noqa: E402
from ingest.selfrun_pipeline import SelfRunPipeline  # noqa: E402

KB_NORMAL = "4ec640408cc711f19f3f45f212d2b89e"
TENANT = "56f78bf26ac611f187cd7db89d62ca74"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb-id", default=KB_NORMAL)
    ap.add_argument("--tenant-id", default=TENANT)
    ap.add_argument("--docs-dir", required=True, help="文档目录（容器内）")
    ap.add_argument("--docs-json", required=True, help="清单 JSON")
    ap.add_argument("--count", type=int, default=50, help="取清单前 N 份")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--label", default="c3", help="档位标签如 c1/c3/c6/10k")
    ap.add_argument("--out", default="/tmp/bench_result.json")
    ap.add_argument("--embed-url", default="http://192.168.80.1:18001/v1",
                    help="embedding 服务地址（4090 GPU 用 http://bge-gpu:18001/v1）")
    ap.add_argument("--persist", action="store_true",
                    help="用 MySQL 持久化（15小时长跑必须开，崩了能恢复）")
    args = ap.parse_args()

    docs_data = json.loads(Path(args.docs_json).read_text(encoding="utf-8"))
    names = [d["name"] for d in docs_data["docs"][:args.count]]
    files = [Path(args.docs_dir) / n for n in names]
    missing = [f for f in files if not f.exists()]
    if missing:
        print(f"[bench] {len(missing)} missing, e.g. {missing[:3]}", file=sys.stderr)
        return 2

    if args.persist:
        repo = MySQLRepository()
        repo.ensure_schema()
        print("[bench] using MySQL persistence (gcn_ingest)")
    else:
        repo = InMemoryRepository()
    pipeline = SelfRunPipeline(tenant_id=args.tenant_id, embed_url=args.embed_url)
    orch = Orchestrator(repo, pipeline)
    sched = Scheduler(repo, orch, max_concurrent=args.concurrency)

    print(f"[bench] {args.label} kb={args.kb_id} docs={len(files)} "
          f"concurrency={args.concurrency} persist={args.persist}", flush=True)

    # warm up（约 18s 冷启动，避免文档 #0 承担）
    t_warm = time.time()
    warm = pipeline.warm_up(kb_id=args.kb_id)
    if warm:
        print(f"[bench] warm-up {time.time()-t_warm:.1f}s: settings={warm.get('settings_ms',0):.0f}ms "
              f"mysql={warm.get('mysql_ms',0):.0f}ms docstore={warm.get('docstore_ms',0):.0f}ms", flush=True)

    job_id = orch.create_job(
        args.kb_id,
        [{"name": f.name, "path_or_url": str(f)} for f in files],
        options={"build_graph": False},
    )

    t0 = time.time()
    # 长跑时定期打印进度（max_polls 调大：1万份约15小时，poll_interval=0.2）
    max_polls = 2000000 if args.count >= 1000 else 10000
    # 长跑用后台 daemon 模式：sched.run_batch 会阻塞，但我们开个进度线程
    import threading
    stop_prog = threading.Event()
    def _progress():
        while not stop_prog.wait(120):  # 每 2 分钟打印一次
            try:
                stats = sched.job_stats(job_id)
                wall_now = time.time() - t0
                print(f"[bench] wall={wall_now:.0f}s pending={stats.get('pending',0)} "
                      f"running={stats.get('running',0)} succeeded={stats.get('succeeded',0)} "
                      f"failed={stats.get('failed',0)}", flush=True)
            except Exception:
                pass
    if args.count >= 1000:
        t = threading.Thread(target=_progress, daemon=True)
        t.start()
    result = sched.run_batch(poll_interval=0.2, max_polls=max_polls)
    stop_prog.set()
    wall = time.time() - t0

    job = orch.get_job(job_id)
    tasks = job["tasks"]

    # per-stage durations across all successful documents
    per_stage: dict[str, list[int]] = {}
    for t in tasks:
        if t["status"] != "succeeded":
            continue
        for s in t["stages"]:
            if s["duration_ms"] is not None:
                per_stage.setdefault(s["step_name"], []).append(s["duration_ms"])

    succeeded = len(result.succeeded)
    failed = len(result.failed)
    skipped = len(result.skipped)

    print(f"\n[bench] === {args.label} RESULT ===")
    print(f"[bench] concurrency     : {args.concurrency}")
    print(f"[bench] wall clock      : {wall:.1f}s")
    print(f"[bench] succeeded/failed/skipped : {succeeded}/{failed}/{skipped}")
    print(f"[bench] peak in flight  : {sched.peak_in_flight}")
    if succeeded and wall > 0:
        print(f"[bench] throughput      : {succeeded/wall:.3f} docs/s "
              f"({wall/succeeded:.1f}s per doc)")

    if per_stage:
        print(f"\n[bench] stage timings (ms)")
        print(f"  {'stage':10s} {'n':>3s} {'avg':>8s} {'p50':>8s} {'p90':>8s} {'max':>8s} {'total':>9s}")
        for name in ("parse", "chunk", "embed", "index"):
            vals = sorted(per_stage.get(name, []))
            if not vals:
                print(f"  {name:10s}   0        -        -        -        -         -")
                continue
            p50 = statistics.median(vals)
            p90 = vals[min(len(vals) - 1, int(len(vals) * 0.9))]
            print(f"  {name:10s} {len(vals):3d} {sum(vals)//len(vals):8d} {p50:8.0f} "
                  f"{p90:8.0f} {max(vals):8d} {sum(vals):9d}")

        total_ms = sum(sum(v) for v in per_stage.values())
        if total_ms:
            print("\n[bench] where time goes (share)")
            for name in ("parse", "chunk", "embed", "index"):
                share = sum(per_stage.get(name, [])) / total_ms * 100
                print(f"  {name:10s} {share:5.1f}%")

    if failed:
        print("\n[bench] failures (isolation check)")
        for t in tasks:
            if t["status"] == "failed":
                print(f"  {t['doc_name']}: {str(t['error'])[:100]}")

    payload = {
        "backend": "mentor-b",
        "label": args.label,
        "kb_id": args.kb_id,
        "docs": len(files),
        "concurrency": args.concurrency,
        "wall_seconds": round(wall, 2),
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "peak_in_flight": sched.peak_in_flight,
        "throughput": round(succeeded / wall, 4) if succeeded and wall else 0,
        "stage_ms": {k: sorted(v) for k, v in per_stage.items()},
        "tasks": [
            {"name": t["doc_name"], "status": t["status"],
             "stages": {s["step_name"]: s["duration_ms"] for s in t["stages"]},
             "error": t["error"]}
            for t in tasks
        ],
        "warmup_seconds": round(time.time() - t_warm, 1) if warm else 0,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[bench] saved -> {out_path}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
