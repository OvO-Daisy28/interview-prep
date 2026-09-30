"""Minimal end-to-end proof for infrastructure-reuse (方案 B).

Proves we can run the whole ingest pipeline OURSELVES — parse, chunk, embed,
index — writing into the same infrastructure RAGFlow uses, so that RAGFlow's
retrieval and GraphRAG keep working on documents we produced without ever
calling RAGFlow's parse API.

Verified contracts (see doc/design/infrastructure-reuse-feasibility.md):
  * MinIO   : bucket = kb_id, object key = filename
  * ES      : index = ragflow_<tenant_id>, 14-field chunk schema
  * chunk id: xxhash.xxh64(content_with_weight + doc_id).hexdigest()
              (task_executor.py:406 — must match or dedup/overwrite breaks)
  * embed   : OpenAI-compatible HTTP, bge-base, 1024-dim -> field q_1024_vec
  * tokenize: infinity.rag_tokenizer (pip package)
  * MySQL   : write document static metadata only; never touch run/progress
              (those belong to RAGFlow's worker state machine)

RAGFlow's worker consumes from Redis only (task_executor.collect), so writing
a document row does NOT get auto-picked-up — we stay in control.

Usage:
    source GCN_Poc/.env
    uv run --project code python code/ingest/selfrun_probe.py --file <docx> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# --- contract constants (verified on 131, 2026-08-19) ---
EMBED_DIM = 1024
EMBED_FIELD = f"q_{EMBED_DIM}_vec"
DEFAULT_EMBED_URL = "http://192.168.80.1:18001/v1"
DEFAULT_EMBED_MODEL = "bge-base"
CHUNK_TOKEN_TARGET = 128          # RAGFlow default chunk_token_num


def die(msg: str, code: int = 2):
    print(f"[probe] FATAL: {msg}", file=sys.stderr)
    raise SystemExit(code)


# --------------------------------------------------------------------------
# 1. parse: docx -> sections (no model, pure XML walk — see naive.py)
# --------------------------------------------------------------------------

def parse_docx(path: Path) -> list[str]:
    try:
        from docx import Document as DocxDocument
    except ImportError:
        die("python-docx not installed: uv add python-docx")
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


def parse_text(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return [p.strip() for p in raw.split("\n\n") if p.strip()]


# --------------------------------------------------------------------------
# 2. chunk: merge sections up to a token budget
# --------------------------------------------------------------------------

def chunk_sections(sections: list[str], target: int = CHUNK_TOKEN_TARGET) -> list[str]:
    """Naive merge: accumulate sections until roughly `target` tokens.

    Token estimate: CJK chars count 1, ASCII words count 1. Good enough for a
    probe; production should reuse RAGFlow's naive_merge for exact parity.
    """
    def est(s: str) -> int:
        cjk = sum(1 for ch in s if "一" <= ch <= "鿿")
        ascii_words = len([w for w in s.split() if w.isascii()])
        return cjk + ascii_words

    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for sec in sections:
        n = est(sec)
        if size + n > target and buf:
            chunks.append("\n".join(buf))
            buf, size = [], 0
        buf.append(sec)
        size += n
    if buf:
        chunks.append("\n".join(buf))
    return chunks


# --------------------------------------------------------------------------
# 3. tokenize: reuse RAGFlow's tokenizer (pip package, identical output)
# --------------------------------------------------------------------------

def make_tokenizer():
    """Return (tokenize, fine_grained_tokenize) matching RAGFlow's output.

    RAGFlow wraps the pip package in ``rag/nlp/rag_tokenizer.py`` (a subclass of
    ``infinity.rag_tokenizer.RagTokenizer``) and exports module-level helpers.
    Prefer that wrapper so our tokens are byte-identical to RAGFlow's; fall back
    to the raw pip class, then to whitespace.
    """
    # 1. RAGFlow's own wrapper (identical output by construction)
    try:
        from rag.nlp import rag_tokenizer as rt  # type: ignore
        return rt.tokenize, rt.fine_grained_tokenize
    except Exception:
        pass
    # 2. raw pip package class
    try:
        from infinity.rag_tokenizer import RagTokenizer  # type: ignore
        tk = RagTokenizer()
        fine = getattr(tk, "fine_grained_tokenize", None)
        return tk.tokenize, (fine or (lambda s: s))
    except Exception as exc:
        print(f"[probe] WARN tokenizer unavailable ({exc}); falling back to whitespace",
              file=sys.stderr)
        return (lambda s: " ".join(s.split()), lambda s: s)


# --------------------------------------------------------------------------
# 4. embed: OpenAI-compatible HTTP (the very service RAGFlow uses)
# --------------------------------------------------------------------------

def embed_texts(texts: list[str], base_url: str, model: str,
                api_key: str = "sk-noauth") -> list[list[float]]:
    import requests
    url = base_url.rstrip("/") + "/embeddings"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={"model": model, "input": texts},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    vecs = [d["embedding"] for d in sorted(data, key=lambda d: d.get("index", 0))]
    if not vecs:
        die(f"embedding service returned no vectors: {resp.text[:200]}")
    if len(vecs[0]) != EMBED_DIM:
        die(f"embedding dim mismatch: got {len(vecs[0])}, contract expects {EMBED_DIM}")
    return vecs


# --------------------------------------------------------------------------
# 5. build ES chunk docs matching the 14-field contract
# --------------------------------------------------------------------------

def build_chunks(texts, vectors, *, kb_id, doc_id, doc_name, tokenize, fine_tokenize):
    import xxhash
    now = datetime.now()
    title_tks = tokenize(Path(doc_name).stem)
    out = []
    for text, vec in zip(texts, vectors):
        content_ltks = tokenize(text)
        out.append({
            # exact id rule from task_executor.py:406
            "id": xxhash.xxh64((text + str(doc_id)).encode("utf-8", "surrogatepass")).hexdigest(),
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


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--kb-id", default=os.environ.get("RAGFLOW_KB_NORMAL", ""))
    ap.add_argument("--tenant-id", default=os.environ.get("RAGFLOW_TENANT_ID", ""))
    ap.add_argument("--embed-url", default=os.environ.get("EMBED_BASE_URL", DEFAULT_EMBED_URL))
    ap.add_argument("--embed-model", default=os.environ.get("EMBED_MODEL", DEFAULT_EMBED_MODEL))
    ap.add_argument("--dry-run", action="store_true",
                    help="parse/chunk/embed and print, write nothing")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        die(f"file not found: {path}")
    if not args.kb_id or not args.tenant_id:
        die("kb_id and tenant_id required (set RAGFLOW_KB_NORMAL / RAGFLOW_TENANT_ID)")

    print(f"[probe] file={path.name} kb={args.kb_id} tenant={args.tenant_id}")

    # 1. parse
    t0 = time.time()
    if path.suffix.lower() == ".docx":
        sections = parse_docx(path)
    else:
        sections = parse_text(path)
    t_parse = time.time() - t0
    print(f"[probe] parse   : {len(sections)} sections in {t_parse:.2f}s")

    # 2. chunk
    t0 = time.time()
    texts = chunk_sections(sections)
    t_chunk = time.time() - t0
    print(f"[probe] chunk   : {len(texts)} chunks in {t_chunk:.2f}s")

    # 3. tokenize
    tokenize, fine_tokenize = make_tokenizer()

    # 4. embed
    t0 = time.time()
    vectors = embed_texts(texts, args.embed_url, args.embed_model)
    t_embed = time.time() - t0
    print(f"[probe] embed   : {len(vectors)}x{len(vectors[0])} in {t_embed:.2f}s "
          f"({t_embed/max(1,len(vectors)):.3f}s/chunk)")

    doc_id = uuid.uuid4().hex
    chunks = build_chunks(texts, vectors, kb_id=args.kb_id, doc_id=doc_id,
                          doc_name=path.name, tokenize=tokenize,
                          fine_tokenize=fine_tokenize)
    print(f"[probe] built   : {len(chunks)} ES docs, doc_id={doc_id}")
    print(f"[probe] sample  : {json.dumps({k: (f'<{len(v)} floats>' if k == EMBED_FIELD else str(v)[:60]) for k, v in chunks[0].items()}, ensure_ascii=False, indent=2)}")

    if args.dry_run:
        print("[probe] dry-run: nothing written")
        return 0

    # ---- write path: MinIO -> MySQL document row -> ES chunks ----
    # Order matters: object first (so a document row never points at a missing
    # blob), metadata second, chunks last (so retrieval never sees a chunk whose
    # document row is absent).
    from ingest.selfrun_writer import write_all  # local import: probe-only dep

    stats = write_all(
        file_path=path, kb_id=args.kb_id, tenant_id=args.tenant_id,
        doc_id=doc_id, chunks=chunks,
    )
    print(f"[probe] wrote   : minio={stats['minio']} document_row={stats['mysql']} "
          f"es_chunks={stats['es']}")
    print(f"[probe] verify  : doc_id={doc_id}")
    print("[probe] next    : check RAGFlow Web / retrieval / GraphRAG see this doc")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
