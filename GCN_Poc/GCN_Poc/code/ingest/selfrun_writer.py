"""Write path for the self-run probe: MinIO + MySQL + ES (方案 B).

Writes into the same infrastructure RAGFlow uses, following the contracts
verified on 131 (doc/design/infrastructure-reuse-feasibility.md §二):

  MinIO  bucket = kb_id, object key = filename
  MySQL  document row — STATIC metadata only. We deliberately set
         run=DONE/progress=1.0 because *we* did the parsing; RAGFlow's worker
         never picks this row up (it consumes from Redis only), so there is no
         double-writer conflict on those fields.
  ES     index = ragflow_<tenant_id>, 14-field chunk schema, _id = chunk id

Runs INSIDE the RAGFlow container (needs the internal network for MinIO/ES/
MySQL and the embedding service), so it reuses RAGFlow's own settings module
for connection details instead of duplicating credentials.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any


def _settings():
    """Load RAGFlow's runtime settings (connection info for MinIO/ES/MySQL).

    v0.26 keeps STORAGE_IMPL / docStoreConn in ``common.settings`` (they used to
    live in ``api.settings``), and they stay ``None`` until ``init_settings()``
    has run.

    ``init_settings()`` is expensive — measured at ~18s on 131, because it
    builds every storage/doc-store client and loads the model registry. Call
    ``warm_up()`` at service start so this cost is paid once at boot rather
    than by whichever document happens to arrive first.
    """
    from common import settings as rag_settings
    if getattr(rag_settings, "STORAGE_IMPL", None) is None or \
       getattr(rag_settings, "docStoreConn", None) is None:
        rag_settings.init_settings()
    return rag_settings


def warm_up(*, kb_id: str | None = None, tenant_id: str | None = None) -> dict[str, float]:
    """Pay the one-time initialisation cost up front; return what each step took.

    Without this the first document absorbs the whole cold start: measured on
    131, document #0 took 14.7s while #1-#3 took 60-80ms. That is what made
    index p90 (~28s) look nine times worse than p50 (~8.5s) — not contention,
    just the first caller paying for everyone.

    Warms three things, in the order a real ingest touches them:
      1. ``init_settings()``      — clients and model registry (~18s)
      2. peewee's MySQL pool      — connection + table metadata
      3. the doc-store handle     — ES client and its connection pool
    """
    timings: dict[str, float] = {}

    t = time.time()
    s = _settings()
    timings["settings_ms"] = (time.time() - t) * 1000

    t = time.time()
    try:
        from api.db.services.knowledgebase_service import KnowledgebaseService
        if kb_id:
            KnowledgebaseService.get_or_none(id=kb_id)
        else:
            KnowledgebaseService.get_or_none(id="__warmup__")
    except Exception:
        pass       # the lookup missing is fine; the connection is what we want
    timings["mysql_ms"] = (time.time() - t) * 1000

    t = time.time()
    try:
        from rag.nlp.search import index_name
        if tenant_id and kb_id:
            s.docStoreConn.index_exist(index_name(tenant_id), kb_id)
    except Exception:
        pass
    timings["docstore_ms"] = (time.time() - t) * 1000

    timings["total_ms"] = sum(timings.values())
    return timings


def put_object(kb_id: str, filename: str, blob: bytes) -> str:
    """MinIO: bucket = kb_id, key = filename (dedup by suffixing '_')."""
    s = _settings()
    storage = s.STORAGE_IMPL
    location = filename
    while storage.obj_exist(kb_id, location):
        location += "_"
    storage.put(kb_id, location, blob)
    return location


def insert_document_row(*, doc_id: str, kb_id: str, tenant_id: str,
                        name: str, location: str, size: int,
                        chunk_num: int) -> bool:
    """Insert a document row so RAGFlow's UI / GraphRAG can see this document.

    We own the parsing, so we mark the row already-parsed (run=DONE,
    progress=1.0). RAGFlow's task_executor consumes from Redis and never scans
    this table, so it will not re-parse or fight us for these fields.

    IMPORTANT (verified 2026-08-19): ``DocumentService.get_by_kb_id`` INNER
    JOINs ``File2Document`` and ``File`` (document_service.py:140-142). A
    document row alone is invisible to the list API and the Web UI — the
    ``file`` + ``file2document`` rows are mandatory, not optional bookkeeping.
    """
    from api.db.services.document_service import DocumentService
    from api.db.services.file_service import FileService
    from api.db.services.file2document_service import File2DocumentService
    from api.db.services.knowledgebase_service import KnowledgebaseService
    from api.db import FileType
    from common.misc_utils import get_uuid
    from common.constants import TaskStatus

    suffix = Path(name).suffix.lstrip(".").lower()
    file_type = FileType.DOC.value if suffix in ("doc", "docx", "txt", "md") \
        else FileType.OTHER.value
    doc = {
        "id": doc_id,
        "kb_id": kb_id,
        "parser_id": "naive",
        "parser_config": {"pages": [[1, 1000000]]},
        "source_type": "local",
        "type": file_type,
        "created_by": tenant_id,
        "name": name,
        "location": location,
        "size": size,
        "token_num": 0,
        "chunk_num": chunk_num,
        "progress": 1.0,
        "progress_msg": "Parsed by GCN ingest service (self-run pipeline).",
        "run": TaskStatus.DONE.value,
        "status": "1",
        "suffix": suffix,
    }
    ok = DocumentService.insert(doc)

    # file + file2document: required for the document to be visible (INNER JOIN)
    kb = KnowledgebaseService.get_or_none(id=kb_id)
    root_folder = FileService.get_root_folder(tenant_id)
    parent_id = root_folder["id"]
    kb_folder = FileService.new_a_file_from_kb(
        kb.tenant_id if kb else tenant_id,
        kb.name if kb else kb_id,
        parent_id,
    )
    file_id = get_uuid()
    FileService.insert({
        "id": file_id,
        "parent_id": kb_folder["id"],
        "tenant_id": tenant_id,
        "created_by": tenant_id,
        "name": name,
        "type": file_type,
        "size": size,
        "location": location,
        "source_type": "local",
    })
    File2DocumentService.insert({
        "id": get_uuid(),
        "file_id": file_id,
        "document_id": doc_id,
    })
    return ok


def bulk_index_chunks(chunks: list[dict[str, Any]], *, tenant_id: str,
                      kb_id: str, wait_for_refresh: bool = False) -> int:
    """Write chunks into ragflow_<tenant_id>.

    Assumes the index already exists (it does for any KB RAGFlow has ingested
    into). Creating it from scratch is a separate concern — RAGFlow's
    ``init_kb`` owns that, and reusing it keeps the mapping identical.

    ``wait_for_refresh`` is the single biggest performance lever we have.
    RAGFlow's own ``ESConnection.insert`` hardcodes ``refresh="wait_for"``
    (es_conn.py:320), which blocks until Elasticsearch makes the write
    searchable — about 900ms regardless of whether you wrote 1 chunk or 50.
    Measured on 131: 719ms with the wait, 14ms without. That single flag was
    ~75% of total ingest time.

    Defaulting to False is safe for batch import: documents become searchable
    within ES's normal refresh interval (1s by default) instead of us paying
    that latency per document, serially. Pass True when a caller must read its
    own write immediately (e.g. an interactive single-file upload that jumps
    straight to a preview).
    """
    s = _settings()
    from rag.nlp.search import index_name

    idx = index_name(tenant_id)
    if wait_for_refresh:
        res = s.docStoreConn.insert(chunks, idx, kb_id)
        if res:
            raise RuntimeError(f"ES insert reported errors: {res}")
        return len(chunks)

    # Same bulk payload shape as ESConnection.insert, minus the refresh wait.
    operations: list[dict[str, Any]] = []
    for d in chunks:
        payload = dict(d)
        doc_id = payload.pop("id")
        operations.append({"index": {"_index": idx, "_id": doc_id}})
        operations.append(payload)

    resp = s.docStoreConn.es.bulk(index=idx, operations=operations,
                                  refresh=False, timeout="60s")
    if resp.get("errors"):
        failed = [item for op in resp.get("items", [])
                  for action, item in op.items()
                  if item.get("status", 200) >= 400]
        raise RuntimeError(f"ES bulk had {len(failed)} failures: {failed[:3]}")
    return len(chunks)


def write_all(*, file_path: Path, kb_id: str, tenant_id: str, doc_id: str,
              chunks: list[dict[str, Any]]) -> dict[str, Any]:
    blob = file_path.read_bytes()
    location = put_object(kb_id, file_path.name, blob)
    ok = insert_document_row(
        doc_id=doc_id, kb_id=kb_id, tenant_id=tenant_id,
        name=file_path.name, location=location, size=len(blob),
        chunk_num=len(chunks),
    )
    n = bulk_index_chunks(chunks, tenant_id=tenant_id, kb_id=kb_id)
    return {"minio": location, "mysql": bool(ok), "es": n}
