"""RAGFlow 原生批量上传接口测试（方案A 纯原生，不走 mentor 编排）。

直接调 RAGFlow HTTP API：批量上传 → 启动解析 → 轮询进度到完成。
记录墙钟/吞吐/成功失败/progress 浮点序列/progress_msg 文本样本/process_duration。
另支持 --cancel-at N：解析到 N% 时发 DELETE /chunks 取消，测原生可控性。

容器内 API 在 localhost:9380（9388 是宿主映射，容器内不通）。

Usage (容器内):
    docker exec docker-ragflow-cpu-1 python3 /ragflow/ingest/native_upload_test.py \
      --kb-id 2f84a97aab4811f1a5be33e6206585a1 \
      --docs-dir /ragflow/ingest/_abtest_docs \
      --docs-json /ragflow/ingest/ab_doc_list.json \
      --token ragflow-xxx --label round1-default --out /tmp/native_r1.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

API_BASE = os.environ.get("RAGFLOW_BASE_URL", "http://localhost:9380").rstrip("/")
# RAGFlow run 字段是单词字符串，不是数字码（实测 raw_run_dist={'RUNNING':100}）
RUN_UNSTART = "UNSTART"
RUN_RUNNING = "RUNNING"
RUN_CANCEL = "CANCEL"
RUN_DONE = "DONE"
RUN_FAIL = "FAIL"
# 终态：DONE/FAIL/CANCEL；非终态：UNSTART(排队)/RUNNING
TERMINAL = {RUN_DONE, RUN_FAIL, RUN_CANCEL}


class NativeClient:
    def __init__(self, token: str, base: str = API_BASE):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}"})

    def upload(self, kb_id: str, files: list[Path]) -> list[dict]:
        """POST /datasets/{kb}/documents (multipart, 多文件一次上传)。"""
        url = f"{self.base}/api/v1/datasets/{kb_id}/documents"
        multipart = []
        for f in files:
            multipart.append(("file", (f.name, open(f, "rb"), "application/octet-stream")))
        try:
            r = self.s.post(url, files=multipart, timeout=300)
            r.raise_for_status()
            payload = r.json()
        finally:
            for _, (_, fh, _) in multipart:
                fh.close()
        if payload.get("code") != 0:
            raise RuntimeError(f"upload error: {payload}")
        return payload.get("data", [])

    def start_parse(self, kb_id: str, doc_ids: list[str]) -> dict:
        """POST /datasets/{kb}/chunks 启动解析（异步入队）。"""
        r = self.s.post(f"{self.base}/api/v1/datasets/{kb_id}/chunks",
                        json={"document_ids": doc_ids}, timeout=60)
        r.raise_for_status()
        return r.json()

    def stop_parse(self, kb_id: str, doc_ids: list[str]) -> dict:
        """DELETE /datasets/{kb}/chunks 停止解析（原生取消）。"""
        r = self.s.delete(f"{self.base}/api/v1/datasets/{kb_id}/chunks",
                           json={"document_ids": doc_ids}, timeout=60)
        r.raise_for_status()
        return r.json()

    def list_docs(self, kb_id: str, page: int = 1, size: int = 100) -> list[dict]:
        """GET /datasets/{kb}/documents 查所有文档状态（page_size 上限100）。"""
        r = self.s.get(f"{self.base}/api/v1/datasets/{kb_id}/documents",
                       params={"page": page, "page_size": min(size, 100)}, timeout=30)
        r.raise_for_status()
        payload = r.json()
        if payload.get("code") != 0:
            print(f"[native] list_docs error: {payload}", file=sys.stderr)
            return []
        data = payload.get("data") or {}
        return data.get("docs", []) or []

    def list_all_docs(self, kb_id: str) -> list[dict]:
        """分页拉取 KB 全部文档（每页100，循环到取空）。"""
        all_docs = []
        page = 1
        while True:
            batch = self.list_docs(kb_id, page=page, size=100)
            if not batch:
                break
            all_docs.extend(batch)
            if len(batch) < 100:
                break
            page += 1
            if page > 20:  # 安全阀 2000 份
                break
        return all_docs

    def get_doc_fields(self, d: dict) -> dict:
        """从 document dict 提取关注的字段。"""
        return {
            "run": str(d.get("run", "")),
            "progress": d.get("progress", 0),
            "progress_msg": (d.get("progress_msg") or "")[:800],
            "process_duration": d.get("process_duration", 0),
            "chunk_count": d.get("chunk_count", 0),
        }

    def get_doc(self, kb_id: str, doc_id: str) -> dict:
        """GET 单文档状态：run/progress/progress_msg/process_duration/chunk_count。"""
        r = self.s.get(f"{self.base}/api/v1/datasets/{kb_id}/documents",
                       params={"id": doc_id}, timeout=15)
        r.raise_for_status()
        payload = r.json()
        if payload.get("code") != 0:
            print(f"[native] get_doc error: {payload}", file=sys.stderr)
            return {}
        data = payload.get("data") or {}
        docs = data.get("docs", []) or []
        if not docs:
            return {}
        d = docs[0]
        return {
            "run": str(d.get("run", "")),
            "progress": d.get("progress", 0),
            "progress_msg": (d.get("progress_msg") or "")[:800],
            "process_duration": d.get("process_duration", 0),
            "chunk_count": d.get("chunk_count", 0),
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb-id", required=True)
    ap.add_argument("--docs-dir", required=True, help="文档目录")
    ap.add_argument("--docs-json", required=True, help="清单 JSON（取前 N 份文件名）")
    ap.add_argument("--token", default=os.environ.get("RAGFLOW_API_KEY", ""))
    ap.add_argument("--count", type=int, default=100, help="取清单前 N 份")
    ap.add_argument("--label", default="round1-default")
    ap.add_argument("--cancel-at", type=float, default=0,
                    help=">0 时，整体进度到该百分比发 DELETE /chunks 测取消")
    ap.add_argument("--poll-interval", type=float, default=2.0)
    ap.add_argument("--out", default="/tmp/native_result.json")
    args = ap.parse_args()

    if not args.token:
        print("need --token or RAGFLOW_API_KEY env", file=sys.stderr)
        return 2

    docs_data = json.loads(Path(args.docs_json).read_text(encoding="utf-8"))
    names = [d["name"] for d in docs_data["docs"][:args.count]]
    files = [Path(args.docs_dir) / n for n in names]
    missing = [f for f in files if not f.exists()]
    if missing:
        print(f"[native] {len(missing)} missing, e.g. {missing[:3]}", file=sys.stderr)
        return 2

    cli = NativeClient(args.token)

    # 确认空库
    existing = cli.list_docs(args.kb_id)
    if existing:
        print(f"[native] WARN: KB has {len(existing)} existing docs (not empty)")

    print(f"[native] {args.label} kb={args.kb_id} docs={len(files)} cancel_at={args.cancel_at}")

    # --- 1. 批量上传 ---
    t_up0 = time.time()
    uploaded = cli.upload(args.kb_id, files)
    t_upload = time.time() - t_up0
    doc_ids = [d["id"] for d in uploaded]
    print(f"[native] uploaded {len(uploaded)} docs in {t_upload:.1f}s")
    id_to_name = {d["id"]: d.get("name", "?") for d in uploaded}

    # --- 2. 启动解析 ---
    t_parse0 = time.time()
    cli.start_parse(args.kb_id, doc_ids)
    print(f"[native] parse started for {len(doc_ids)} docs")

    # --- 3. 轮询 ---
    samples: list[dict] = []
    cancelled = False
    cancel_observation: dict = {}
    poll_n = 0
    while True:
        t_now = time.time()
        wall = t_now - t_parse0
        poll_n += 1
        # 一次拉取所有文档状态（不再逐个 GET）
        all_docs = cli.list_all_docs(args.kb_id)
        id_to_full = {d.get("id"): d for d in all_docs}
        # 诊断：前几次轮询打印原始 run 值分布
        if poll_n <= 3:
            raw_runs = {}
            for d in all_docs:
                rv = str(d.get("run", ""))
                raw_runs[rv] = raw_runs.get(rv, 0) + 1
            print(f"[native] poll#{poll_n} wall={wall:.1f}s total_docs={len(all_docs)} "
                  f"raw_run_dist={raw_runs}")
        statuses = []
        for did in doc_ids:
            d = id_to_full.get(did, {})
            st = cli.get_doc_fields(d) if d else {
                "run": "", "progress": 0, "progress_msg": "",
                "process_duration": 0, "chunk_count": 0}
            st["doc_id"] = did
            st["name"] = id_to_name.get(did, "?")
            st["wall"] = round(wall, 1)
            statuses.append(st)

        done = sum(1 for s in statuses if s["run"] == RUN_DONE)
        fail = sum(1 for s in statuses if s["run"] == RUN_FAIL)
        cancel = sum(1 for s in statuses if s["run"] == RUN_CANCEL)
        running = sum(1 for s in statuses if s["run"] == RUN_RUNNING)
        unstart = sum(1 for s in statuses if s["run"] == RUN_UNSTART or s["run"] == "")
        # 整体进度（已完成文档数 + 平均未完成进度）
        prog_vals = [s["progress"] for s in statuses if s["run"] == RUN_RUNNING]
        avg_prog = (sum(prog_vals) / len(prog_vals)) if prog_vals else 0
        overall = (done + fail + cancel) / len(doc_ids) * 100
        # 未完成 = 还在排队(UNSTART) 或 正在跑(RUNNING)
        pending = unstart + running

        # 采样：记录这一轮的聚合状态 + 每个运行中文档的 progress_msg
        sample = {
            "wall": round(wall, 1), "done": done, "fail": fail,
            "cancel": cancel, "running": running, "unstart": unstart,
            "avg_running_prog": round(avg_prog, 4),
            "overall_pct": round(overall, 1),
            # 只记运行中文档的 progress_msg（变化的才记）
            "running_msgs": [
                {"doc": s["name"], "run": s["run"], "prog": s["progress"],
                 "dur": s["process_duration"],
                 "msg": s["progress_msg"][-200:] if s["progress_msg"] else ""}
                for s in statuses if s["run"] == RUN_RUNNING
            ][:5],  # 最多 5 份避免膨胀
        }
        samples.append(sample)

        if wall > 5 and poll_n % 5 == 0:
            print(f"[native] wall={wall:.0f}s done={done} fail={fail} "
                  f"cancel={cancel} running={running} unstart={unstart} "
                  f"overall={overall:.0f}%")

        # 取消测试
        if args.cancel_at and not cancelled and overall >= args.cancel_at:
            print(f"[native] === CANCEL TEST at overall={overall:.1f}% "
                  f"(threshold {args.cancel_at}%) ===")
            cli.stop_parse(args.kb_id, doc_ids)
            cancelled = True
            cancel_observation["triggered_at_wall"] = round(wall, 1)
            cancel_observation["triggered_at_overall"] = round(overall, 1)

        # 终止条件：没有排队(UNSTART)也没有运行中(RUNNING)的文档
        if pending == 0:
            print(f"[native] all settled: done={done} fail={fail} cancel={cancel}")
            break
        time.sleep(args.poll_interval)
        # 安全阀
        if wall > 7200:
            print("[native] TIMEOUT 2h", file=sys.stderr)
            break

    wall_total = time.time() - t_parse0
    succeeded = sum(1 for s in statuses if s["run"] == RUN_DONE)
    failed = sum(1 for s in statuses if s["run"] == RUN_FAIL)
    cancelled_n = sum(1 for s in statuses if s["run"] == RUN_CANCEL)

    print(f"\n[native] === {args.label} RESULT ===")
    print(f"[native] upload time : {t_upload:.1f}s ({len(files)} files)")
    print(f"[native] parse wall  : {wall_total:.1f}s")
    print(f"[native] succeeded   : {succeeded}")
    print(f"[native] failed      : {failed}")
    print(f"[native] cancelled   : {cancelled_n}")
    if succeeded:
        print(f"[native] throughput  : {succeeded/wall_total:.3f} docs/s")
    print(f"[native] samples      : {len(samples)} polls")

    # 失败详情
    fail_details = [{"name": s["name"], "run": s["run"],
                     "msg": s["progress_msg"]} for s in statuses if s["run"] == RUN_FAIL]

    # progress_msg 样本（取一份有代表性的运行中文档的完整 msg 序列）
    msg_samples = []
    for s in samples:
        for m in s.get("running_msgs", []):
            if m["msg"]:
                msg_samples.append({"wall": s["wall"], **m})

    if cancelled:
        cancel_observation["final_cancelled"] = cancelled_n
        cancel_observation["final_done"] = succeeded
        cancel_observation["final_failed"] = failed
        # 取消后能否 resume？原生无 resume，重新 start_parse
        cancel_observation["note"] = ("RAGFlow 原生无 pause/resume；DELETE /chunks 后 "
                                      "run=CANCEL，需重新 POST /chunks 才能重跑")

    payload = {
        "backend": "ragflow-native",
        "label": args.label,
        "kb_id": args.kb_id,
        "docs": len(files),
        "upload_seconds": round(t_upload, 2),
        "parse_wall_seconds": round(wall_total, 2),
        "succeeded": succeeded,
        "failed": failed,
        "cancelled": cancelled_n,
        "throughput": round(succeeded / wall_total, 4) if succeeded and wall_total else 0,
        "fail_details": fail_details,
        "progress_samples": samples,
        "msg_samples": msg_samples[:50],
        "cancel_test": cancel_observation if cancelled else None,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[native] saved -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
