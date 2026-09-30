"""AB 对比实验 — 清空测试 KB 的所有文档。

方案A 文档由 RAGFlow task_executor 写入；方案B 文档由 selfrun_pipeline.write_all
写入 RAGFlow document 表 + ES + MinIO。两者都通过 RAGFlow document API 列出并
删除，跑前后各清一次保证 KB 干净。

Usage (容器内或本地，只要能访问 RAGFlow API + API Key):
    RAGFLOW_API_KEY=... uv run --project code python code/ingest/ab_cleanup_kb.py --kb-id <KB>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ragflow_client  # noqa: E402


def list_docs(kb_id: str) -> list[dict]:
    """列出 KB 所有文档（分页，每页 200）。"""
    docs: list[dict] = []
    page = 1
    while True:
        payload = ragflow_client.request_payload(
            "GET",
            f"/api/v1/datasets/{kb_id}/documents",
            params={"page": page, "page_size": 200, "suffix": ".docx"},
            timeout=30,
        )
        data = payload.get("data", {})
        batch = data.get("docs", [])
        total = data.get("total", 0)
        docs.extend(batch)
        if len(batch) < 200 or len(docs) >= total:
            break
        page += 1
        if page > 500:  # 安全阀
            break
    return docs


def delete_docs(kb_id: str, doc_ids: list[str]) -> None:
    """批量删除文档，每批 100（DELETE /documents，body document_ids）。"""
    for i in range(0, len(doc_ids), 100):
        batch = doc_ids[i:i + 100]
        ragflow_client.request_payload(
            "DELETE",
            f"/api/v1/datasets/{kb_id}/documents",
            json={"document_ids": batch},
            timeout=60,
        )
        print(f"[cleanup] deleted {min(i + 100, len(doc_ids))}/{len(doc_ids)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb-id", required=True)
    ap.add_argument("--all-suffix", action="store_true",
                    help="不按 .docx 过滤，列出全部（含方案B可能写入的非 docx）")
    args = ap.parse_args()

    docs = list_docs(args.kb_id) if args.all_suffix else _list_all(args.kb_id)
    print(f"[cleanup] kb={args.kb_id} docs={len(docs)}")
    if not docs:
        return 0
    for d in docs[:3]:
        print(f"  e.g. {d.get('id')} {d.get('name','')} run={d.get('run')}")
    ids = [d["id"] for d in docs if d.get("id")]
    delete_docs(args.kb_id, ids)
    # 复查
    remain = _list_all(args.kb_id)
    print(f"[cleanup] remaining docs after delete: {len(remain)}")
    return 0 if not remain else 1


def _list_all(kb_id: str) -> list[dict]:
    """不带 suffix 过滤，列出全部文档。"""
    docs: list[dict] = []
    page = 1
    while True:
        payload = ragflow_client.request_payload(
            "GET",
            f"/api/v1/datasets/{kb_id}/documents",
            params={"page": page, "page_size": 200},
            timeout=30,
        )
        data = payload.get("data", {})
        batch = data.get("docs", [])
        total = data.get("total", 0)
        docs.extend(batch)
        if len(batch) < 200 or len(docs) >= total:
            break
        page += 1
        if page > 500:
            break
    return docs


if __name__ == "__main__":
    raise SystemExit(main())
