"""M2 batch verification on real infrastructure (方案 B).

Runs the actual orchestrator + SelfRunPipeline against 131's MinIO/ES/MySQL
and the shared embedding service — no fakes. Answers the questions unit tests
cannot: real throughput, where the time goes, whether concurrency helps, and
whether failure isolation holds when the failure is a real one.

Must run INSIDE the RAGFlow container (the embedding service and datastores
are on the internal network).

Usage:
    docker exec docker-ragflow-cpu-1 bash -c \\
      "cd /ragflow && PYTHONPATH=/ragflow python /ragflow/ingest/m2_batch_run.py \\
       --docs 10 --concurrency 3"
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
from ingest.repository import InMemoryRepository  # noqa: E402
from ingest.scheduler import Scheduler  # noqa: E402
from ingest.selfrun_pipeline import SelfRunPipeline  # noqa: E402

KB_NORMAL = "4ec640408cc711f19f3f45f212d2b89e"
TENANT = "56f78bf26ac611f187cd7db89d62ca74"

SAMPLE = """PTR冷却泵设备技术文档 第{n}份

一、设备概述
PTR冷却泵是核电站余热排出系统的关键设备，用于停堆后导出堆芯余热。
本文档为批量导入验证第 {n} 份，由 GCN 自研摄入服务处理。

二、主要技术参数
额定流量：640 立方米每小时
额定扬程：36 米
转速：1480 转每分钟
电机功率：90 千瓦
入口压力：0.35 兆帕（表压）

三、常见故障与处理
故障现象：泵体振动超标
可能原因：叶轮不平衡、轴承磨损、联轴器对中不良
处理措施：停机检查叶轮动平衡，更换磨损轴承，重新对中联轴器

故障现象：轴封泄漏量增大
可能原因：机械密封面磨损、O型圈老化
处理措施：更换机械密封组件，检查轴套配合面

四、维护要求
每运行 2000 小时检查一次轴承润滑状态。
每年进行一次解体检修，更换密封圈。
备件清单：机械密封、轴承、O型圈、联轴器弹性块。
"""


def make_docs(count: int, out_dir: Path, bad_index: int | None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        p = out_dir / f"m2_doc_{i:02d}.txt"
        if bad_index is not None and i == bad_index:
            # a real failure: unsupported type, rejected by our parser
            p = out_dir / f"m2_doc_{i:02d}.pdf"
            p.write_bytes(b"%PDF-1.4 not really a pdf")
        else:
            p.write_text(SAMPLE.format(n=i), encoding="utf-8")
        paths.append(p)
    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=10)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--kb-id", default=KB_NORMAL)
    ap.add_argument("--tenant-id", default=TENANT)
    ap.add_argument("--inject-failure", action="store_true",
                    help="make one document fail, to verify isolation")
    ap.add_argument("--out", default="/tmp/m2_result.json")
    args = ap.parse_args()

    bad = (args.docs // 2) if args.inject_failure else None
    files = make_docs(args.docs, Path("/tmp/m2_docs"), bad)

    repo = InMemoryRepository()
    pipeline = SelfRunPipeline(tenant_id=args.tenant_id)
    orch = Orchestrator(repo, pipeline)
    sched = Scheduler(repo, orch, max_concurrent=args.concurrency)

    print(f"[m2] docs={args.docs} concurrency={args.concurrency} "
          f"kb={args.kb_id} inject_failure={args.inject_failure}")

    # Pay the ~30s cold start here instead of inside document #0, where it
    # showed up as an index p90 of ~28s against a p50 of 8.5s.
    warm = pipeline.warm_up(kb_id=args.kb_id)
    if warm:
        print(f"[m2] warm-up: settings={warm.get('settings_ms', 0):.0f}ms "
              f"mysql={warm.get('mysql_ms', 0):.0f}ms "
              f"docstore={warm.get('docstore_ms', 0):.0f}ms")

    job_id = orch.create_job(
        args.kb_id,
        [{"name": f.name, "path_or_url": str(f)} for f in files],
        options={"build_graph": False},
    )

    t0 = time.time()
    result = sched.run_batch(poll_interval=0.2, max_polls=600)
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

    print(f"\n[m2] wall clock      : {wall:.1f}s")
    print(f"[m2] succeeded       : {len(result.succeeded)}")
    print(f"[m2] failed          : {len(result.failed)}")
    print(f"[m2] peak concurrency: {sched.peak_in_flight}")
    if result.succeeded:
        print(f"[m2] throughput      : {len(result.succeeded)/wall:.2f} docs/s "
              f"({wall/len(result.succeeded):.1f}s per doc)")

    print("\n[m2] stage timings (ms, across succeeded docs)")
    print(f"  {'stage':10s} {'n':>3s} {'p50':>8s} {'p90':>8s} {'max':>8s} {'total':>9s}")
    for name in ("parse", "chunk", "embed", "index"):
        vals = sorted(per_stage.get(name, []))
        if not vals:
            print(f"  {name:10s}   0        -        -        -         -")
            continue
        p50 = statistics.median(vals)
        p90 = vals[min(len(vals) - 1, int(len(vals) * 0.9))]
        print(f"  {name:10s} {len(vals):3d} {p50:8.0f} {p90:8.0f} "
              f"{max(vals):8d} {sum(vals):9d}")

    total_ms = sum(sum(v) for v in per_stage.values())
    if total_ms:
        print("\n[m2] where time goes (share of summed stage time)")
        for name in ("parse", "chunk", "embed", "index"):
            share = sum(per_stage.get(name, [])) / total_ms * 100
            print(f"  {name:10s} {share:5.1f}%")

    if result.failed:
        print("\n[m2] failures (isolation check)")
        for t in tasks:
            if t["status"] == "failed":
                print(f"  {t['doc_name']}: {str(t['error'])[:90]}")

    payload = {
        "docs": args.docs, "concurrency": args.concurrency,
        "wall_seconds": round(wall, 2),
        "succeeded": len(result.succeeded), "failed": len(result.failed),
        "peak_in_flight": sched.peak_in_flight,
        "stage_ms": {k: sorted(v) for k, v in per_stage.items()},
        "tasks": [{"name": t["doc_name"], "status": t["status"],
                   "stages": {s["step_name"]: s["duration_ms"] for s in t["stages"]},
                   "error": t["error"]} for t in tasks],
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"\n[m2] saved -> {args.out}")
    return 0 if not result.failed or args.inject_failure else 1


if __name__ == "__main__":
    raise SystemExit(main())
