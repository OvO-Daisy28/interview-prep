"""AB 对比实验 — 统一批量跑测脚本。

同一批文档，--backend ragflow（方案A，RAGFlow 原生 task_executor 解析）或
--backend selfrun（方案B，mentor 自建 parse/chunk/embed/index 流水线），走相同
Orchestrator + InMemoryRepository + Scheduler，输出统一格式 JSON 供 ab_report.py
对比。两方案唯一差异是 pipeline 实现，编排/调度/计时口径完全一致。

方案A: ChunksPipelineAdapter — start_parse 异步入队 RAGFlow POST /chunks，
  task_executor 消费 Redis Stream 干活（embed_limiter 默认1=串行），run_task
  轮询 GET /documents 直到 run=DONE/FAIL。progress 是单浮点，阶段靠 progress_msg
  文本推断。RecordingAdapter 额外记录 progress_msg 样本用于报告展示。
方案B: SelfRunPipeline — start_parse 同步跑 _ingest_one 四阶段，每阶段 time.time()
  精确计时，on_stage 回调写 InMemoryRepository.step.duration_ms。

两方案都逐文档处理（Orchestrator._ensure_uploaded 每次传1份），Scheduler 并发 N。
embedding 最终都走同一 bge-base 服务（192.168.80.1:18001）。

Must run INSIDE the RAGFlow container（方案B 需 192.168.80.1 embedding + MinIO/ES
内网；方案A 调 RAGFlow API 但文件须容器内可读）。

Usage:
    docker exec docker-ragflow-cpu-1 bash -c \\
      "cd /ragflow && PYTHONPATH=/ragflow python /ragflow/ingest/ab_batch.py \\
       --backend ragflow --kb-id <KB_ID> \\
       --docs-json /tmp/ab_doc_list.json --docs-dir /ragflow/ingest/_abtest_docs \\
       --concurrency 3 --label round1-default --out /tmp/ab_ragflow_r1.json"
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

# allow running as script inside container
sys.path.insert(0, "/ragflow")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest.orchestrator import Orchestrator  # noqa: E402
from ingest.pipeline_adapter import ChunksPipelineAdapter  # noqa: E402
from ingest.repository import InMemoryRepository  # noqa: E402
from ingest.scheduler import Scheduler  # noqa: E402
from ingest.selfrun_pipeline import SelfRunPipeline  # noqa: E402

TENANT = "56f78bf26ac611f187cd7db89d62ca74"

# 100 份方案A embedding 串行（embed_limiter=1），单份~8s，最后一份等~800s；
# poll_interval=2s, max_polls=2000 → 4000s 上限，足够。
POLL_INTERVAL = 2.0
MAX_POLLS = 2000


class RecordingAdapter(ChunksPipelineAdapter):
    """方案A 适配器 + progress_msg 样本采集（用于报告展示进度可见性差异）。"""

    def __init__(self) -> None:
        super().__init__()
        self.samples: list[dict] = []  # 每次 get_document_status 记一条

    def get_document_status(self, kb_id: str, doc_id: str) -> dict:
        st = super().get_document_status(kb_id, doc_id)
        # 只在 progress 或 run 变化时记录，避免 JSON 爆炸
        self.samples.append({
            "doc_id": doc_id, "t": round(time.time(), 2),
            "run": st.get("run"), "progress": st.get("progress"),
            "progress_msg": (st.get("progress_msg", "") or "")[:500],
            "chunk_count": st.get("chunk_count", 0),
        })
        return st


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["ragflow", "selfrun"], required=True)
    ap.add_argument("--kb-id", required=True)
    ap.add_argument("--docs-json", required=True, help="清单 JSON 路径（容器内）")
    ap.add_argument("--docs-dir", required=True, help="文档目录（容器内）")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--tenant-id", default=TENANT)
    ap.add_argument("--label", default="", help="轮次标签，如 round1-default")
    ap.add_argument("--out", default="/tmp/ab_result.json")
    args = ap.parse_args()

    docs_data = json.loads(Path(args.docs_json).read_text(encoding="utf-8"))
    file_list = docs_data["docs"]
    files = [str(Path(args.docs_dir) / d["name"]) for d in file_list]
    # 校验文件存在
    missing = [f for f in files if not Path(f).exists()]
    if missing:
        print(f"[ab] {len(missing)} files missing, e.g. {missing[:3]}", file=sys.stderr)
        return 2

    repo = InMemoryRepository()
    if args.backend == "ragflow":
        pipeline = RecordingAdapter()
    else:
        pipeline = SelfRunPipeline(tenant_id=args.tenant_id)
    orch = Orchestrator(repo, pipeline)
    sched = Scheduler(repo, orch, max_concurrent=args.concurrency)

    print(f"[ab] backend={args.backend} kb={args.kb_id} docs={len(files)} "
          f"concurrency={args.concurrency} label={args.label or '(none)'}")

    # warm up（仅方案B有；方案A 无需预热，RAGFlow 自己管）
    if hasattr(pipeline, "warm_up"):
        t_warm = time.time()
        warm = pipeline.warm_up(kb_id=args.kb_id)
        if warm:
            print(f"[ab] warm-up {time.time()-t_warm:.1f}s: {warm}")

    job_id = orch.create_job(
        args.kb_id,
        [{"name": Path(f).name, "path_or_url": f} for f in files],
        options={"build_graph": False},
    )

    t0 = time.time()
    result = sched.run_batch(poll_interval=POLL_INTERVAL, max_polls=MAX_POLLS)
    wall = time.time() - t0

    job = orch.get_job(job_id)
    tasks = job["tasks"]

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

    print(f"\n[ab] === {args.backend} {args.label} ===")
    print(f"[ab] wall clock      : {wall:.1f}s")
    print(f"[ab] succeeded/failed/skipped : {succeeded}/{failed}/{skipped}")
    print(f"[ab] peak concurrency: {sched.peak_in_flight}")
    if succeeded and wall > 0:
        print(f"[ab] throughput      : {succeeded/wall:.3f} docs/s "
              f"({wall/succeeded:.1f}s per doc)")

    if per_stage:
        print(f"\n[ab] stage timings (ms, across succeeded docs)")
        print(f"  {'stage':12s} {'n':>3s} {'p50':>8s} {'p90':>8s} {'max':>8s} {'total':>9s}")
        for name in ("parse", "chunk", "embed", "index"):
            vals = sorted(per_stage.get(name, []))
            if not vals:
                print(f"  {name:12s}   0        -        -        -         -")
                continue
            p50 = statistics.median(vals)
            p90 = vals[min(len(vals) - 1, int(len(vals) * 0.9))]
            print(f"  {name:12s} {len(vals):3d} {p50:8.0f} {p90:8.0f} "
                  f"{max(vals):8d} {sum(vals):9d}")

        total_ms = sum(sum(v) for v in per_stage.values())
        if total_ms:
            print("\n[ab] where time goes (share of summed stage time)")
            for name in ("parse", "chunk", "embed", "index"):
                share = sum(per_stage.get(name, [])) / total_ms * 100
                print(f"  {name:12s} {share:5.1f}%")

    if failed:
        print("\n[ab] failures (isolation check)")
        for t in tasks:
            if t["status"] == "failed":
                print(f"  {t['doc_name']}: {str(t['error'])[:100]}")

    # 方案A: progress_msg 样本统计
    progress_samples = []
    if isinstance(pipeline, RecordingAdapter):
        progress_samples = pipeline.samples
        print(f"\n[ab] progress_msg samples collected: {len(progress_samples)}")

    payload = {
        "backend": args.backend,
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
        "progress_samples": progress_samples,  # 方案A only，方案B 为空
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[ab] saved -> {out_path}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
