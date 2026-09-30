"""Pipeline adapter — /chunks implementation (design §四, §八 layer 3).

Encapsulates every RAGFlow HTTP call the orchestration layer makes. The
/chunks (built-in chunking pipeline) implementation is here; swapping to
/ingest later only replaces this module — the state machine, step mapping
and public API stay put (design §8 flexibility layer 3).

Reuses ragflow_client.request_payload (Bearer + code==0 + JSON validation,
already POC-proven) for JSON requests. Upload is multipart and goes through
requests directly because request_payload forces Content-Type: application/json.

Pause force/cancel side effects live here as stop_parse() (DELETE /chunks);
soft pause does NOT call it (design §5.3). The orchestrator decides whether
to call stop_parse based on force flag — the adapter only exposes verbs.
"""

from __future__ import annotations

from typing import Any

import requests

import ragflow_client


class PipelineError(RuntimeError):
    """Raised when a RAGFlow pipeline call fails or returns bad data."""


class ChunksPipelineAdapter:
    """Adapter over the built-in chunking pipeline (/chunks path).

    PTR datasets use this path (naive chunk_method + parser_config.graphrag,
    per operations.md). DELETE /chunks is the native stop; DELETE /graph is
    the graph-retry precondition (decision 3).
    """

    def upload_documents(
        self, kb_id: str, file_paths: list[str]
    ) -> list[dict[str, Any]]:
        """POST /datasets/{kb}/documents (multipart, multi-file).

        Returns the list of created document dicts (each has 'id', 'name',
        'run', ...). RAGFlow run starts at UNSTART; parsing must be triggered
        separately via start_parse().
        """
        url = f"{ragflow_client.BASE}/api/v1/datasets/{kb_id}/documents"
        headers = {"Authorization": f"Bearer {ragflow_client.require_api_key()}"}
        files = []
        opened = []
        try:
            for p in file_paths:
                f = open(p, "rb")
                opened.append(f)
                files.append(("file", (p.rsplit("/", 1)[-1].rsplit("\\", 1)[-1], f)))
            try:
                resp = requests.post(url, headers=headers, files=files, timeout=120)
                resp.raise_for_status()
            except requests.RequestException as exc:
                raise PipelineError(f"upload failed: {exc}") from exc
            try:
                payload = resp.json()
            except requests.exceptions.JSONDecodeError as exc:
                raise PipelineError("upload returned invalid JSON") from exc
            if payload.get("code") != 0:
                raise PipelineError(f"upload business error: {payload}")
            data = payload.get("data", [])
            if not isinstance(data, list):
                raise PipelineError(f"upload returned non-list data: {data}")
            return data
        finally:
            for f in opened:
                f.close()

    def start_parse(self, kb_id: str, doc_ids: list[str]) -> None:
        """POST /datasets/{kb}/chunks — start parsing (built-in pipeline)."""
        ragflow_client.request_payload(
            "POST",
            f"/api/v1/datasets/{kb_id}/chunks",
            json={"document_ids": doc_ids},
        )

    def stop_parse(self, kb_id: str, doc_ids: list[str]) -> None:
        """DELETE /datasets/{kb}/chunks — stop parsing.

        Native stop (api_reference line 2078). Used by pause(force=true) and
        cancel(). Soft pause does NOT call this (design §5.3).
        """
        ragflow_client.request_payload(
            "DELETE",
            f"/api/v1/datasets/{kb_id}/chunks",
            json={"document_ids": doc_ids},
        )

    def get_document_status(
        self, kb_id: str, doc_id: str
    ) -> dict[str, Any]:
        """GET /datasets/{kb}/documents?id= — run/progress/progress_msg/chunks."""
        payload = ragflow_client.request_payload(
            "GET",
            f"/api/v1/datasets/{kb_id}/documents",
            params={"id": doc_id},
            timeout=15,
        )
        docs = payload.get("data", {}).get("docs", [])
        if not docs:
            return {}
        d = docs[0]
        return {
            "run": d.get("run"),
            "progress": d.get("progress", 0),
            "progress_msg": d.get("progress_msg", ""),
            "chunk_count": d.get("chunk_count", 0),
            "doc_id": d.get("id"),
        }

    def start_graph_build(self, kb_id: str) -> None:
        """POST /datasets/{kb}/index?type=graph — trigger GraphRAG build."""
        ragflow_client.request_payload(
            "POST", f"/api/v1/datasets/{kb_id}/index?type=graph", json={}
        )

    def get_graph_build_progress(self, kb_id: str) -> dict[str, Any]:
        """GET /datasets/{kb}/index?type=graph — graph build progress."""
        data = ragflow_client.request_payload(
            "GET", f"/api/v1/datasets/{kb_id}/index?type=graph", timeout=15
        ).get("data", {})
        return {
            "progress": data.get("progress", 0),
            "progress_msg": data.get("progress_msg", ""),
        }

    def delete_graph(self, kb_id: str) -> None:
        """DELETE /datasets/{kb}/graph — clear graph (decision 3 retry precondition).

        Must be called before re-running GraphRAG or RAGFlow skips with
        'already merged' (坑#4/#5).
        """
        ragflow_client.request_payload(
            "DELETE", f"/api/v1/datasets/{kb_id}/graph", timeout=30
        )
