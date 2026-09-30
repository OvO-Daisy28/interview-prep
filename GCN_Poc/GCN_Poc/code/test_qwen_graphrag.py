#!/usr/bin/env python3
"""在 4090 RAGFlow 上用 Qwen3.8-27B 跑 PTR 文档的 GraphRAG，分 3 轮拆分各环节。

控制单一变量：只有模型不同（vs 131 基线 ds-v4flash，method=general）。
三轮：
  轮1: resolution=false, community=false → 看原始抽取的节点/边
  轮2: resolution=true,  community=false → 看消歧后
  轮3: resolution=true,  community=true  → 全流程 + 社区报告

每轮：删图→配→触发→轮询→导出。社区报告通过 retrieval(use_kg=true) 间接导出。
"""
from __future__ import annotations

import json
import os
import sys
import time
import pathlib

from ragflow_client import (
    BASE,
    create_dataset,
    upload_document,
    list_documents,
    get_dataset,
    update_graphrag_config,
    trigger_parse,
    get_doc_status,
    trigger_graphrag,
    get_graphrag_progress,
    get_graph,
    delete_graph,
    create_chat,
    ask_detail,
    request_payload,
)

QWEN_LLM_ID = "Qwen3.8-27B@qwen38-local@OpenAI-API-Compatible"
EMBEDDING_MODEL = "bge-base@bge-base@OpenAI-API-Compatible"
PTR_DOCX = r"f:\byh\GCN_Poc\GCN_Poc\doc\客户\测试文档\PTR冷却泵设备运行与维修手册.docx"

# 核电域 entity_types（对齐 131 基线，非默认 5 种）
ENTITY_TYPES = ["设备", "部件", "参数", "故障现象", "故障原因", "处理措施", "备件", "操作步骤", "标准"]

# 三轮配置
ROUNDS = [
    {"name": "round1_extract_only", "resolution": False, "community": False},
    {"name": "round2_with_resolution", "resolution": True, "community": False},
    {"name": "round3_full", "resolution": True, "community": True},
]

# 固定问题集（PTR 手册相关）
QUESTIONS = [
    "PTR冷却泵有哪些主要部件？",
    "设备安装有哪些步骤？",
    "大修必须进行哪些检查？",
    "润滑油的更换周期是什么？",
    "总结这份手册的核心内容。",
]

OUTDIR = pathlib.Path(r"f:\byh\graphrag_test\test\results\qwen3.8-27b_4090")
OUTDIR.mkdir(parents=True, exist_ok=True)


def wait_parse(kb_id: str, doc_id: str, max_wait: int = 600):
    """轮询文档解析直到完成。"""
    print(f"  [parse] 等待解析（最长 {max_wait}s）...", end="", flush=True)
    started = time.monotonic()
    last = None
    while time.monotonic() - started < max_wait:
        st = get_doc_status(kb_id, doc_id)
        run = st.get("run")
        chunks = st.get("chunk_count", 0)
        if (run, chunks) != last:
            print(f" run={run} chunks={chunks}", end="", flush=True)
            last = (run, chunks)
        if run == "DONE" and chunks > 0:
            print(f"\n  [parse] 完成: {chunks} chunks")
            return st
        time.sleep(5)
    raise TimeoutError(f"解析超时: {st}")


def wait_graphrag(kb_id: str, max_wait: int = 7200):
    """轮询 GraphRAG 进度直到完成。"""
    print(f"  [graphrag] 等待建图（最长 {max_wait}s）...", flush=True)
    started = time.monotonic()
    last = -1
    progress_msgs = []
    while time.monotonic() - started < max_wait:
        prog = get_graphrag_progress(kb_id)
        value = prog["progress"]
        msg = prog["progress_msg"]
        if value != last:
            elapsed = int(time.monotonic() - started)
            print(f"  [{elapsed}s] progress={value:.2f}")
            for line in msg.splitlines()[-3:]:
                if line.strip():
                    print(f"    {line}")
            progress_msgs.append(f"=== [{elapsed}s] progress={value:.2f} ===\n{msg}")
            last = value
        if value < 0:
            print(f"  [graphrag] 失败! progress={value}")
            return prog, progress_msgs, False
        if value >= 1:
            print(f"  [graphrag] 完成! progress={value}")
            return prog, progress_msgs, True
        time.sleep(10)
    raise TimeoutError(f"GraphRAG 超时: progress={value}")


def export_graph(kb_id: str):
    """导出图谱（节点/边）。"""
    return get_graph(kb_id)


def retrieval_kg(kb_id: str, question: str):
    """用 retrieval API + use_kg=true 间接导出 KG 相关内容（含社区报告）。"""
    data = request_payload(
        "POST",
        "/api/v1/retrieval",
        json={
            "question": question,
            "dataset_ids": [kb_id],
            "page": 1,
            "page_size": 30,
            "use_kg": True,
        },
        timeout=180,
    ).get("data", {})
    return data


def run_round(kb_id: str, doc_id: str, round_cfg: dict, is_first: bool):
    """跑一轮：配→(删图)→触发→轮询→导出。"""
    name = round_cfg["name"]
    print(f"\n{'=' * 60}")
    print(f"[{name}] resolution={round_cfg['resolution']} community={round_cfg['community']}")
    print("=" * 60)

    # 配 GraphRAG
    effective = update_graphrag_config(
        kb_id,
        method="general",
        entity_types=ENTITY_TYPES,
        resolution=round_cfg["resolution"],
        community=round_cfg["community"],
        batch_chunk_token_size=4096,
    )
    print(f"  config: method={effective.get('method')} resolution={effective.get('resolution')} community={effective.get('community')}")

    # 非首轮先删图
    if not is_first:
        print("  删除上一轮图...")
        delete_graph(kb_id)

    # 触发建图
    print("  触发 GraphRAG...")
    trigger_graphrag(kb_id)
    prog, progress_msgs, ok = wait_graphrag(kb_id, max_wait=7200)

    # 导出
    graph = export_graph(kb_id) if ok else {"nodes": [], "edges": []}
    nodes = len(graph.get("nodes", []))
    edges = len(graph.get("edges", []))
    print(f"  图: {nodes} nodes / {edges} edges")

    round_out = OUTDIR / name
    round_out.mkdir(parents=True, exist_ok=True)
    (round_out / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (round_out / "progress_msg.txt").write_text("\n\n".join(progress_msgs), encoding="utf-8")

    return {"name": name, "nodes": nodes, "edges": edges, "ok": ok, "progress": prog}


def main():
    if not os.environ.get("RAGFLOW_API_KEY"):
        print("需配 RAGFLOW_API_KEY 环境变量")
        return 1

    # 1. 建库
    print("[setup] 建知识库")
    kb = create_dataset(
        f"qwen38_graphrag_{time.strftime('%m%d')}",
        embedding_model=EMBEDDING_MODEL,
    )
    kb_id = kb["id"]
    print(f"  kb_id={kb_id}")

    # 1.5 设 llm_id（PUT，文档未列但现有库有此字段）
    import requests
    r = requests.put(
        f"{BASE}/api/v1/datasets/{kb_id}",
        headers={"Authorization": f"Bearer {os.environ['RAGFLOW_API_KEY']}", "Content-Type": "application/json"},
        json={"llm_id": QWEN_LLM_ID},
        timeout=15,
    )
    d = get_dataset(kb_id)
    print(f"  llm_id={d.get('llm_id')} (PUT status={r.status_code})")

    # 2. 上传 PTR 文档
    print("[setup] 上传 PTR 文档")
    docs = upload_document(kb_id, PTR_DOCX)
    doc_id = docs[0]["id"]
    print(f"  doc_id={doc_id}")

    # 3. 触发解析（只需一次）
    print("[setup] 触发解析")
    trigger_parse(kb_id, doc_id)
    wait_parse(kb_id, doc_id, max_wait=600)

    # 4. 三轮
    results = []
    for i, rcfg in enumerate(ROUNDS):
        r = run_round(kb_id, doc_id, rcfg, is_first=(i == 0))
        results.append(r)

    # 5. 全流程轮跑固定问题集 + retrieval 导出社区报告
    print(f"\n[query] 固定问题集（基于 round3 全流程图）")
    chat_id = create_chat(f"qwen38_q_{time.strftime('%m%d')}", kb_id)
    answers = []
    kg_exports = []
    for qi, q in enumerate(QUESTIONS):
        print(f"  Q{qi+1}: {q}")
        # 问答
        data = ask_detail(chat_id, q, timeout=300)
        ans = data.get("answer", "")
        ref = data.get("reference", [])
        answers.append({"question": q, "answer": ans, "reference": ref})
        print(f"    A: {ans[:120]}...")
        # retrieval 导出 KG 内容
        kg_data = retrieval_kg(kb_id, q)
        chunks = kg_data.get("chunks", [])
        kg_exports.append({"question": q, "num_chunks": len(chunks), "chunks": chunks})
        print(f"    KG retrieval: {len(chunks)} chunks")

    (OUTDIR / "answers.jsonl").write_text(
        "\n".join(json.dumps(a, ensure_ascii=False) for a in answers), encoding="utf-8"
    )
    (OUTDIR / "kg_retrieval.json").write_text(
        json.dumps(kg_exports, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 6. 汇总
    summary = {
        "model": "Qwen3.8-27B int8 (qwen38-local)",
        "method": "general",
        "entity_types": ENTITY_TYPES,
        "kb_id": kb_id,
        "doc_id": doc_id,
        "rounds": results,
        "baseline_131": {"nodes": 256, "edges": 128, "communities": 41, "model": "ds-v4flash"},
    }
    (OUTDIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print("[done] 三轮汇总:")
    for r in results:
        print(f"  {r['name']}: {r['nodes']} nodes / {r['edges']} edges (ok={r['ok']})")
    print(f"  基线(131): 256 nodes / 128 edges / 41 communities")
    print(f"  产物: {OUTDIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
