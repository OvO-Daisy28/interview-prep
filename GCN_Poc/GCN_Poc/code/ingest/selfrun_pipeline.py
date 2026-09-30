"""Self-run pipeline: we do parse/chunk/embed/index ourselves (方案 B).

Proven end-to-end on 131 (2026-08-19): a document ingested entirely by this
path shows up in RAGFlow's document list and is retrieved by RAGFlow's own
search (sim=0.476, top hit) — without RAGFlow's parser ever running. See
``doc/design/infrastructure-reuse-feasibility.md`` §七.

Why this instead of driving RAGFlow's API
-----------------------------------------
Owning the loop is what makes the rest of the requirements achievable:
stage timings are recorded rather than guessed from a log string, pause is a
real checkpoint rather than "wait for RAGFlow to finish", retries can resume
per stage, and throughput is ours to tune (batch size, concurrency) instead of
being capped by a single shared worker.

What we reuse, deliberately
---------------------------
Storage and models — MinIO, Elasticsearch, the embedding service, the
tokenizer — so everything downstream (RAGFlow retrieval, GraphRAG) keeps
working on documents we produced. We reuse *infrastructure*, not code paths.

Deployment note: the embedding service lives on 131's internal network, so
this pipeline runs on the server, not on a dev laptop.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ingest.pipeline import PipelineError, StageCallback

# --- contract constants, verified on 131 (feasibility doc §二) ---
EMBED_DIM = 1024
EMBED_FIELD = f"q_{EMBED_DIM}_vec"
DEFAULT_EMBED_URL = "http://192.168.80.1:18001/v1"
DEFAULT_EMBED_MODEL = "bge-base"
DEFAULT_CHUNK_TOKENS = 128
EMBED_BATCH = 16          # keep request bodies small enough for CPU inference

# RAGFlow run vocabulary — the state machine speaks this regardless of backend.
RUN_UNSTART, RUN_RUNNING, RUN_CANCEL, RUN_DONE, RUN_FAIL = (
    "UNSTART", "RUNNING", "CANCEL", "DONE", "FAIL")


class SelfRunPipeline:
    """Runs the ingest pipeline in-process, writing to shared infrastructure."""

    def __init__(
        self,
        *,
        tenant_id: str,
        embed_url: str = DEFAULT_EMBED_URL,
        embed_model: str = DEFAULT_EMBED_MODEL,
        embed_api_key: str = "sk-noauth",
        chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
        writer=None,
        mineru=None,
    ):
        self.tenant_id = tenant_id
        self.embed_url = embed_url.rstrip("/")
        self.embed_model = embed_model
        self.embed_api_key = embed_api_key
        self.chunk_tokens = chunk_tokens
        self.mineru = mineru           # MinerUClient, required only for PDFs
        self._writer = writer          # injected for tests; real one is lazy
        # doc_id -> latest status dict, so get_document_status stays cheap
        self._status: dict[str, dict[str, Any]] = {}
        self._cancelled: set[str] = set()
        self._pending_files: dict[str, Path] = {}

    # ---- writer (lazy: importing it pulls in RAGFlow settings) ----

    @property
    def writer(self):
        if self._writer is None:
            from ingest import selfrun_writer
            self._writer = selfrun_writer
        return self._writer

    def warm_up(self, kb_id: str | None = None) -> dict[str, float]:
        """Pay initialisation cost at service start, not on the first document.

        RAGFlow's ``init_settings()`` plus the first MySQL/ES round-trip cost
        ~18s and ~14s respectively on 131. Left lazy, document #0 absorbs all
        of it (measured: 14.7s vs 60-80ms for #1 onward), which is what made
        index p90 look catastrophic next to p50. Call this once at boot.
        """
        warm = getattr(self.writer, "warm_up", None)
        if warm is None:
            return {}
        return warm(kb_id=kb_id, tenant_id=self.tenant_id)

    # ---- upload ----

    def upload_documents(self, kb_id: str, file_paths: list[str]) -> list[dict[str, Any]]:
        """Store raw files in MinIO and register them, without parsing yet.

        Mirrors RAGFlow's semantics: after upload a document exists but is
        UNSTART; ``start_parse`` is what produces chunks.

        Paths prefixed ``__demo__`` are materialised on the fly, so the review
        console can submit a batch without the reviewer preparing files. The
        pipeline that then runs is the real one — nothing else about the path
        is special-cased.
        """
        import uuid

        out = []
        for p in file_paths:
            path = _materialise_demo(p) if str(p).startswith("__demo") else Path(p)
            if not path.exists():
                raise PipelineError(f"file not found: {path}")
            doc_id = uuid.uuid4().hex
            self._pending_files[doc_id] = path
            self._status[doc_id] = {
                "run": RUN_UNSTART, "progress": 0.0,
                "progress_msg": "Uploaded, awaiting parse.",
                "chunk_count": 0, "doc_id": doc_id,
            }
            out.append({"id": doc_id, "name": path.name, "run": RUN_UNSTART})
        return out

    # ---- parse (synchronous: returns once the document is fully ingested) ----

    def start_parse(self, kb_id: str, doc_ids: list[str], *,
                    on_stage: StageCallback | None = None) -> None:
        for doc_id in doc_ids:
            path = self._pending_files.get(doc_id)
            if path is None:
                raise PipelineError(f"unknown doc_id (upload first): {doc_id}")
            try:
                self._ingest_one(kb_id, doc_id, path, on_stage)
            except Exception as exc:
                self._status[doc_id] = {
                    "run": RUN_FAIL, "progress": -1.0,
                    "progress_msg": f"[ERROR] {exc}",
                    "chunk_count": 0, "doc_id": doc_id,
                }
                raise PipelineError(str(exc)) from exc

    def _ingest_one(self, kb_id, doc_id, path: Path, on_stage) -> None:
        def stage(name, status, pct, dur_ms=None, detail=""):
            self._status[doc_id] = {
                "run": RUN_RUNNING, "progress": pct / 100,
                "progress_msg": f"{name}: {status}",
                "chunk_count": 0, "doc_id": doc_id,
            }
            if on_stage:
                on_stage(name, status, pct, dur_ms, detail)
            if doc_id in self._cancelled:
                raise PipelineError("cancelled")

        # 1. parse
        t0 = time.time()
        stage("parse", "running", 5)
        sections = parse_file(path, mineru=self.mineru)
        stage("parse", "done", 20, int((time.time() - t0) * 1000),
              f"{len(sections)} sections")

        # 2. chunk
        t0 = time.time()
        stage("chunk", "running", 25)
        texts = chunk_sections(sections, self.chunk_tokens)
        if not texts:
            raise PipelineError("no content extracted")
        stage("chunk", "done", 40, int((time.time() - t0) * 1000),
              f"{len(texts)} chunks")

        # 3. embed
        t0 = time.time()
        stage("embed", "running", 45)
        vectors = self.embed_texts(texts)
        stage("embed", "done", 80, int((time.time() - t0) * 1000),
              f"{len(vectors)}x{EMBED_DIM}")

        # 4. index (MinIO + MySQL + ES)
        t0 = time.time()
        stage("index", "running", 85)
        tokenize, fine = make_tokenizer()
        chunks = build_chunk_docs(
            texts, vectors, kb_id=kb_id, doc_id=doc_id, doc_name=path.name,
            tokenize=tokenize, fine_tokenize=fine)
        self.writer.write_all(
            file_path=path, kb_id=kb_id, tenant_id=self.tenant_id,
            doc_id=doc_id, chunks=chunks)
        stage("index", "done", 100, int((time.time() - t0) * 1000),
              f"{len(chunks)} indexed")

        self._status[doc_id] = {
            "run": RUN_DONE, "progress": 1.0,
            "progress_msg": f"Task done. {len(chunks)} chunks indexed.",
            "chunk_count": len(chunks), "doc_id": doc_id,
        }

    # ---- control / status ----

    def stop_parse(self, kb_id: str, doc_ids: list[str]) -> None:
        """Mark documents cancelled; the ingest loop checks this at each stage."""
        for doc_id in doc_ids:
            self._cancelled.add(doc_id)
            cur = self._status.get(doc_id, {})
            if cur.get("run") not in (RUN_DONE, RUN_FAIL):
                self._status[doc_id] = {
                    "run": RUN_CANCEL, "progress": cur.get("progress", 0),
                    "progress_msg": "Cancelled by request.",
                    "chunk_count": 0, "doc_id": doc_id,
                }

    def clear_stop(self, kb_id: str, doc_ids: list[str]) -> None:
        """Undo ``stop_parse`` so a resumed task can run again.

        Only meaningful after a force-pause: without this the abort flag
        survives and the resumed run aborts at its first stage boundary.
        """
        for doc_id in doc_ids:
            self._cancelled.discard(doc_id)
            if self._status.get(doc_id, {}).get("run") == RUN_CANCEL:
                self._status[doc_id] = {
                    "run": RUN_UNSTART, "progress": 0.0,
                    "progress_msg": "Resumed, awaiting parse.",
                    "chunk_count": 0, "doc_id": doc_id,
                }

    def get_document_status(self, kb_id: str, doc_id: str) -> dict[str, Any]:
        return dict(self._status.get(doc_id, {}))

    # ---- GraphRAG: still RAGFlow's job (it reads our chunks from ES) ----

    def start_graph_build(self, kb_id: str) -> None:
        raise NotImplementedError(
            "GraphRAG build is still driven through RAGFlow (it reads our "
            "chunks from ES). Use ChunksPipelineAdapter for graph stages until "
            "M5 decides whether to own that loop too.")

    def get_graph_build_progress(self, kb_id: str) -> dict[str, Any]:
        raise NotImplementedError(
            "GraphRAG progress comes from RAGFlow; see start_graph_build.")

    def delete_graph(self, kb_id: str) -> None:
        raise NotImplementedError(
            "Graph deletion is RAGFlow's API; see start_graph_build.")

    # ---- embedding ----

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Call the shared embedding service in batches."""
        import requests

        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            resp = requests.post(
                f"{self.embed_url}/embeddings",
                headers={"Authorization": f"Bearer {self.embed_api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.embed_model, "input": batch},
                timeout=180,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            vecs = [d["embedding"] for d in sorted(data, key=lambda x: x.get("index", 0))]
            if len(vecs) != len(batch):
                raise PipelineError(
                    f"embedding count mismatch: sent {len(batch)}, got {len(vecs)}")
            if vecs and len(vecs[0]) != EMBED_DIM:
                raise PipelineError(
                    f"embedding dim {len(vecs[0])} != contract {EMBED_DIM}")
            out.extend(vecs)
        return out


# ---------------------------------------------------------------------------
# pure functions (no I/O) — unit-testable without a server
# ---------------------------------------------------------------------------

DEMO_TEXT = """PTR冷却泵设备技术文档（演示样例 {n}）

一、设备概述
PTR冷却泵是核电站余热排出系统的关键设备，用于停堆后导出堆芯余热。

二、主要技术参数
额定流量：640立方米每小时。额定扬程：36米。转速：1480转每分钟。电机功率：90千瓦。

三、常见故障与处理
故障现象：泵体振动超标。可能原因：叶轮不平衡、轴承磨损。处理措施：检查叶轮动平衡，更换磨损轴承。

四、维护要求
每运行2000小时检查轴承润滑状态；解体检修周期为一年。
"""


def _materialise_demo(spec: str) -> Path:
    """Create a sample document for the review console.

    ``__demo_bad__`` produces an unsupported file type on purpose, so the
    failure-isolation behaviour can be demonstrated rather than described.
    """
    import tempfile
    import uuid

    tmp = Path(tempfile.gettempdir()) / "gcn_demo"
    tmp.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:8]

    if spec.startswith("__demo_bad__"):
        path = tmp / f"损坏样例_{token}.zip"
        path.write_bytes(b"PK not a document")
        return path

    index = spec.split(":", 1)[1] if ":" in spec else "0"
    path = tmp / f"演示文档_{index}_{token}.txt"
    path.write_text(DEMO_TEXT.format(n=index), encoding="utf-8")
    return path


def parse_file(path: Path, *, mineru=None) -> list[str]:
    """Extract text sections.

    docx/xlsx/txt are structural formats — we walk them directly, no model, in
    under a millisecond. PDFs are not: the file stores glyph positions (or,
    when scanned, only pixels), so recovering structure needs layout analysis
    and OCR. That is delegated to MinerU, which is the expensive path.
    """
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _parse_docx(path)
    if suffix in (".txt", ".md"):
        raw = path.read_text(encoding="utf-8", errors="replace")
        return [p.strip() for p in raw.split("\n\n") if p.strip()]
    if suffix == ".pdf":
        if mineru is None:
            raise PipelineError(
                "PDF parsing requires a MinerU client; construct the pipeline "
                "with mineru=MinerUClient(...)")
        return mineru.parse_pdf(path)
    raise PipelineError(f"unsupported file type: {suffix}")


def _parse_docx(path: Path) -> list[str]:
    from docx import Document as DocxDocument

    doc = DocxDocument(str(path))
    out: list[str] = []
    for para in doc.paragraphs:
        t = (para.text or "").strip()
        if t:
            out.append(t)
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [(c.text or "").strip() for c in row.cells]
            if any(cells):
                rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        if rows:
            out.append("<table>" + "".join(rows) + "</table>")
    return out


def estimate_tokens(s: str) -> int:
    """Rough token count: CJK chars count 1, ASCII words count 1."""
    cjk = sum(1 for ch in s if "一" <= ch <= "鿿")
    ascii_words = len([w for w in s.split() if w.isascii()])
    return cjk + ascii_words


def chunk_sections(sections: list[str], target: int = DEFAULT_CHUNK_TOKENS) -> list[str]:
    """Merge sections until roughly ``target`` tokens per chunk."""
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for sec in sections:
        n = estimate_tokens(sec)
        if size + n > target and buf:
            chunks.append("\n".join(buf))
            buf, size = [], 0
        buf.append(sec)
        size += n
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def make_tokenizer():
    """Return (tokenize, fine_grained_tokenize) matching RAGFlow's output."""
    try:
        from rag.nlp import rag_tokenizer as rt  # RAGFlow's own wrapper
        return rt.tokenize, rt.fine_grained_tokenize
    except Exception:
        pass
    try:
        from infinity.rag_tokenizer import RagTokenizer
        tk = RagTokenizer()
        return tk.tokenize, getattr(tk, "fine_grained_tokenize", lambda s: s)
    except Exception:
        return (lambda s: " ".join(s.split()), lambda s: s)


def build_chunk_docs(texts, vectors, *, kb_id, doc_id, doc_name,
                     tokenize, fine_tokenize) -> list[dict[str, Any]]:
    """Assemble ES documents matching RAGFlow's 14-field chunk schema.

    The id rule must match task_executor.py:406 exactly, otherwise dedup and
    overwrite semantics diverge from RAGFlow's.
    """
    import xxhash

    now = datetime.now()
    title_tks = tokenize(Path(doc_name).stem)
    out = []
    for text, vec in zip(texts, vectors):
        content_ltks = tokenize(text)
        out.append({
            "id": xxhash.xxh64(
                (text + str(doc_id)).encode("utf-8", "surrogatepass")).hexdigest(),
            "kb_id": kb_id,
            "doc_id": doc_id,
            "docnm_kwd": doc_name,
            "title_tks": title_tks,
            "title_sm_tks": fine_tokenize(title_tks),
            "content_with_weight": text,
            "content_ltks": content_ltks,
            "content_sm_ltks": fine_tokenize(content_ltks),
            "doc_type_kwd": "table" if text.lstrip().startswith("<table>") else "",
            "img_id": "",
            "create_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "create_timestamp_flt": now.timestamp(),
            EMBED_FIELD: vec,
        })
    return out
