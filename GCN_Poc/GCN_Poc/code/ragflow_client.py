#!/usr/bin/env python3
"""Small, strict RAGFlow API client for the PTR demo."""

from __future__ import annotations

import os
from typing import Any

import requests

BASE = os.environ.get("RAGFLOW_BASE_URL", "http://10.126.2.131:9388").rstrip("/")

KB_NORMAL = os.environ.get("RAGFLOW_KB_NORMAL", "4ec640408cc711f19f3f45f212d2b89e")
KB_GRAPH = os.environ.get("RAGFLOW_KB_GRAPH", "4ec8cbda8cc711f19f3f45f212d2b89e")
DOC_NORMAL = os.environ.get("RAGFLOW_DOC_NORMAL", "4ed0f9d68cc711f19f3f45f212d2b89e")
DOC_GRAPH = os.environ.get("RAGFLOW_DOC_GRAPH", "4ee267488cc711f19f3f45f212d2b89e")
CHAT_NORMAL = os.environ.get("RAGFLOW_CHAT_NORMAL", "d3df2baa8f0d11f18512c56e2ff23bb9")
CHAT_GRAPH = os.environ.get("RAGFLOW_CHAT_GRAPH", "2fc6e9e48f0e11f18512c56e2ff23bb9")


class RAGFlowError(RuntimeError):
    """Raised when transport, JSON, or RAGFlow business validation fails."""


def require_api_key() -> str:
    """Return the API key or fail before sending any request."""
    key = os.environ.get("RAGFLOW_API_KEY", "").strip()
    if not key:
        raise RAGFlowError("RAGFLOW_API_KEY is required")
    if any(character.isspace() or ord(character) < 32 for character in key):
        raise RAGFlowError("RAGFLOW_API_KEY contains whitespace or control characters")
    return key


def request_payload(
    method: str,
    path: str,
    *,
    timeout: int = 30,
    **kwargs: Any,
) -> dict[str, Any]:
    """Call RAGFlow and require HTTP success, JSON, and business code zero."""
    headers = dict(kwargs.pop("headers", {}))
    headers.setdefault("Content-Type", "application/json")
    headers["Authorization"] = f"Bearer {require_api_key()}"
    try:
        response = requests.request(
            method,
            f"{BASE}{path}",
            headers=headers,
            timeout=timeout,
            **kwargs,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RAGFlowError(f"RAGFlow {method.upper()} {path} failed: {exc}") from exc
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise RAGFlowError(
            f"RAGFlow {method.upper()} {path} returned invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise RAGFlowError(
            f"RAGFlow {method.upper()} {path} returned non-object JSON"
        )
    if payload.get("code") != 0:
        raise RAGFlowError(
            f"RAGFlow {method.upper()} {path} business error: {payload}"
        )
    return payload


def get_dataset(kb_id: str) -> dict[str, Any]:
    """Return dataset metadata, including the effective parser_config."""
    return request_payload("GET", f"/api/v1/datasets/{kb_id}").get("data", {})


def create_dataset(name: str, *, chunk_method: str = "naive", embedding_model: str | None = None, parser_config: dict | None = None) -> dict[str, Any]:
    """Create a dataset (knowledge base). Returns the created dataset metadata.

    注意：RAGFlow v0.26.1 的 POST /api/v1/datasets 不接受 language 和 llm_id 字段。
    llm_id 需在 parser_config 里配（通过 update_graphrag_config）。
    """
    body: dict[str, Any] = {"name": name, "chunk_method": chunk_method}
    if embedding_model:
        body["embedding_model"] = embedding_model
    if parser_config:
        body["parser_config"] = parser_config
    return request_payload("POST", "/api/v1/datasets", json=body, timeout=30).get("data", {})


def upload_document(kb_id: str, file_path: str) -> list[dict[str, Any]]:
    """Upload a document file to a dataset. Returns the document info list."""
    import pathlib

    p = pathlib.Path(file_path)
    if not p.exists():
        raise RAGFlowError(f"File not found: {file_path}")
    headers = {"Authorization": f"Bearer {require_api_key()}"}
    with open(p, "rb") as f:
        files = {"file": (p.name, f)}
        response = requests.post(
            f"{BASE}/api/v1/datasets/{kb_id}/documents",
            headers=headers,
            files=files,
            timeout=120,
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RAGFlowError(f"Upload failed: {payload}")
    return payload.get("data", [])


def list_documents(kb_id: str) -> list[dict[str, Any]]:
    """List documents in a dataset."""
    payload = request_payload(
        "GET", f"/api/v1/datasets/{kb_id}/documents", params={"page": 1, "page_size": 100}, timeout=15
    )
    return payload.get("data", {}).get("docs", [])


def update_graphrag_config(kb_id: str, **changes: Any) -> dict[str, Any]:
    """Merge GraphRAG settings and verify the effective server configuration."""
    parser_config = get_dataset(kb_id).get("parser_config", {})
    for read_only_field in (
        "children_delimiter",
        "image_context_size",
        "llm_id",
        "table_context_size",
        "enable_children",
    ):
        parser_config.pop(read_only_field, None)
    parser_config.setdefault("graphrag", {}).update(changes)
    request_payload(
        "PUT",
        f"/api/v1/datasets/{kb_id}",
        json={"parser_config": parser_config},
    )
    effective = get_dataset(kb_id).get("parser_config", {}).get("graphrag", {})
    mismatches = {
        key: (value, effective.get(key))
        for key, value in changes.items()
        if effective.get(key) != value
    }
    if mismatches:
        raise RAGFlowError(f"GraphRAG config verification failed: {mismatches}")
    return effective


def get_doc_status(kb_id: str, doc_id: str) -> dict[str, Any]:
    """Return run, progress, chunk count, and progress message for one document."""
    payload = request_payload(
        "GET",
        f"/api/v1/datasets/{kb_id}/documents",
        params={"id": doc_id},
        timeout=15,
    )
    docs = payload.get("data", {}).get("docs", [])
    if not docs:
        return {}
    document = docs[0]
    return {
        "run": document.get("run"),
        "progress": document.get("progress"),
        "chunk_count": document.get("chunk_count"),
        "progress_msg": document.get("progress_msg", ""),
    }


def get_graphrag_progress(kb_id: str) -> dict[str, Any]:
    """Return GraphRAG build progress and progress message."""
    data = request_payload(
        "GET", f"/api/v1/datasets/{kb_id}/index?type=graph", timeout=15
    ).get("data", {})
    return {
        "progress": data.get("progress", 0),
        "progress_msg": data.get("progress_msg", ""),
    }


def get_graph(kb_id: str) -> dict[str, Any]:
    """Return graph nodes and edges."""
    return request_payload(
        "GET", f"/api/v1/datasets/{kb_id}/graph", timeout=30
    ).get("data", {}).get("graph", {})


def delete_graph(kb_id: str) -> None:
    """Delete graph, subgraph, entities, relations, reports, and phase markers."""
    request_payload("DELETE", f"/api/v1/datasets/{kb_id}/graph", timeout=30)


def trigger_graphrag(kb_id: str) -> None:
    """Trigger a GraphRAG build."""
    request_payload(
        "POST", f"/api/v1/datasets/{kb_id}/index?type=graph", json={}, timeout=30
    )


def trigger_parse(kb_id: str, doc_id: str) -> int:
    """Trigger document parsing and return the reported success count."""
    data = request_payload(
        "POST",
        f"/api/v1/datasets/{kb_id}/documents/parse",
        json={"document_ids": [doc_id]},
        timeout=15,
    ).get("data", {})
    success_count = int(data.get("success_count", 0))
    if success_count < 1:
        raise RAGFlowError(f"Document parse trigger reported no success: {data}")
    return success_count


def create_chat(name: str, kb_id: str) -> str:
    """Create a chat and return its ID."""
    data = request_payload(
        "POST",
        "/api/v1/chats",
        json={"name": name, "dataset_ids": [kb_id]},
        timeout=15,
    ).get("data", {})
    if not isinstance(data, dict):
        raise RAGFlowError(f"Unexpected chat creation response: {data}")
    chat_id = data.get("id") or data.get("chat_id")
    if not chat_id:
        raise RAGFlowError(f"Chat creation response has no ID: {data}")
    return str(chat_id)


def ask_detail(chat_id: str, question: str, *, timeout: int = 180) -> dict[str, Any]:
    """Ask one non-streaming question and return the RAGFlow data object."""
    data = request_payload(
        "POST",
        f"/api/v1/chats/{chat_id}/completions",
        json={"question": question, "stream": False},
        timeout=timeout,
    ).get("data", {})
    if not isinstance(data, dict):
        raise RAGFlowError(f"Unexpected completion response: {data}")
    return data


def ask(chat_id: str, question: str) -> str:
    """Ask one question and return the answer text."""
    return str(ask_detail(chat_id, question).get("answer", ""))


def retrieve(
    question: str,
    kb_id: str,
    *,
    page_size: int = 5,
    use_kg: bool = False,
) -> dict[str, Any]:
    """Retrieve chunks without generating an answer."""
    data = request_payload(
        "POST",
        "/api/v1/retrieval",
        json={
            "question": question,
            "dataset_ids": [kb_id],
            "page_size": page_size,
            "use_kg": use_kg,
        },
        timeout=60,
    ).get("data", {})
    if not isinstance(data, dict):
        raise RAGFlowError(f"Unexpected retrieval response: {data}")
    return data


def main() -> int:
    """Run a read-only health check against both PTR datasets."""
    print("=== Document status ===")
    for label, kb_id, doc_id in (
        ("Normal RAG", KB_NORMAL, DOC_NORMAL),
        ("GraphRAG", KB_GRAPH, DOC_GRAPH),
    ):
        status = get_doc_status(kb_id, doc_id)
        print(
            f"  {label}: run={status.get('run')}, "
            f"progress={status.get('progress')}, chunks={status.get('chunk_count')}"
        )
    progress = get_graphrag_progress(KB_GRAPH)
    graph = get_graph(KB_GRAPH)
    print(f"GraphRAG progress={progress['progress']}")
    print(
        f"Graph nodes={len(graph.get('nodes', []))}, "
        f"edges={len(graph.get('edges', []))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
