"""MinerU client — PDF and scanned-document parsing.

MinerU runs as a standalone HTTP service (FastAPI) on 131 at port 8010,
separate from RAGFlow. We use its async ``/tasks`` flow: ``POST /tasks`` to
submit, poll ``GET /tasks/{id}``, then fetch ``GET /tasks/{id}/result``.
(RAGFlow itself calls the synchronous ``/file_parse``, but that endpoint
answers 503 on this deployment, and async suits minutes-long OCR anyway.)

This is what unblocks PDFs. Our own parser handles docx/xlsx/txt by walking
their structure, which is fast and model-free, but a PDF carries only glyph
positions — and a scanned one carries only pixels. Recovering structure from
those needs layout analysis and OCR, which is exactly MinerU's job.

Cost note: this is the expensive path. docx parsing is sub-millisecond;
MinerU runs vision models, and 131 has no GPU. Reach for it only when the
file actually requires it.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

DEFAULT_MINERU_URL = "http://172.17.0.1:8010"   # host gateway, see note below
PARSE_TIMEOUT = 1800                            # vision models on CPU are slow

# Address note (measured 2026-08-20): mineru-web sits on the default `bridge`
# network (172.17.0.9) while RAGFlow sits on `docker_ragflow` (192.168.80.6),
# so the containers cannot resolve each other by name. Both can reach the host
# gateway, so we go through 172.17.0.1:8010 (the published port). Override via
# the constructor when deploying elsewhere.


class MinerUError(RuntimeError):
    """Raised when MinerU is unreachable or returns something unusable."""


class MinerUClient:
    """Thin client over MinerU's synchronous ``/file_parse`` endpoint."""

    def __init__(self, base_url: str = DEFAULT_MINERU_URL, *,
                 timeout: int = PARSE_TIMEOUT, lang: str = "ch",
                 backend: str = "pipeline", method: str = "auto"):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.lang = lang
        # "pipeline" is the backend that actually works on 131 (measured):
        # the service default "hybrid-auto-engine" and "vlm-transformers" both
        # fail with "Local path for repo_mode 'vlm' is not configured" because
        # no VLM weights are installed there.
        self.backend = backend
        self.method = method

    def health(self) -> bool:
        import requests
        try:
            r = requests.get(f"{self.base_url}/docs", timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    def parse_pdf(self, path: Path, *, formula: bool = True,
                  table: bool = True, poll_interval: float = 3.0) -> list[str]:
        """Parse a PDF into text sections, tables rendered as HTML.

        Uses the async ``/tasks`` flow (submit → poll → fetch result) rather
        than ``/file_parse``. The synchronous endpoint returns 503 on this
        deployment, and async is the right shape anyway: OCR on CPU takes
        minutes (a 312-page scan took ~10 min here), which no sensible HTTP
        timeout should sit through.

        Returns the same shape as our docx parser, so chunking downstream does
        not care which parser produced the sections.
        """
        import requests

        if not path.exists():
            raise MinerUError(f"file not found: {path}")

        task_id = self._submit(path, formula=formula, table=table)
        self._await_completion(task_id, poll_interval=poll_interval)

        try:
            resp = requests.get(f"{self.base_url}/tasks/{task_id}/result",
                                timeout=120)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise MinerUError(f"MinerU result fetch failed: {exc}") from exc

        return self._extract_sections(resp.content,
                                      resp.headers.get("content-type", ""))

    def _submit(self, path: Path, *, formula: bool, table: bool) -> str:
        import requests

        data = {
            "lang_list": self.lang,
            "parse_method": self.method,
            "formula_enable": str(formula).lower(),
            "table_enable": str(table).lower(),
            "return_md": "true",
            "return_content_list": "true",
        }
        if self.backend:
            data["backend"] = self.backend
        try:
            with open(path, "rb") as fh:
                files = {"files": (path.name, fh, "application/pdf")}
                resp = requests.post(f"{self.base_url}/tasks", files=files,
                                     data=data, timeout=300)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise MinerUError(f"MinerU submit failed: {exc}") from exc

        try:
            payload = resp.json()
        except ValueError as exc:
            raise MinerUError("MinerU submit returned non-JSON") from exc
        task_id = (payload.get("task_id") or payload.get("id")
                   or payload.get("data", {}).get("task_id"))
        if not task_id:
            raise MinerUError(f"MinerU submit returned no task id: {payload}")
        return str(task_id)

    def _await_completion(self, task_id: str, *, poll_interval: float) -> None:
        import time

        import requests

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                resp = requests.get(f"{self.base_url}/tasks/{task_id}", timeout=60)
                resp.raise_for_status()
                state = resp.json()
            except requests.RequestException as exc:
                raise MinerUError(f"MinerU status poll failed: {exc}") from exc

            status = str(state.get("status") or state.get("state") or "").lower()
            if status in ("done", "success", "succeeded", "completed", "finished"):
                return
            if status in ("failed", "error"):
                raise MinerUError(
                    f"MinerU task {task_id} failed: {state.get('error') or state}")
            time.sleep(poll_interval)
        raise MinerUError(f"MinerU task {task_id} exceeded {self.timeout}s")

    def _extract_sections(self, body: bytes, content_type: str) -> list[str]:
        """Pull text sections out of MinerU's response (zip or JSON)."""
        if "zip" in content_type or body[:2] == b"PK":
            return self._sections_from_zip(body)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise MinerUError("MinerU returned neither zip nor JSON") from exc
        return self._sections_from_payload(payload)

    def _sections_from_zip(self, body: bytes) -> list[str]:
        sections: list[str] = []
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            names = zf.namelist()
            # content_list.json is structured (blocks with types); prefer it
            for name in names:
                if name.endswith("content_list.json"):
                    blocks = json.loads(zf.read(name))
                    sections = self._sections_from_blocks(blocks)
                    break
            if not sections:
                for name in names:
                    if name.endswith(".md"):
                        md = zf.read(name).decode("utf-8", "replace")
                        sections = [p.strip() for p in md.split("\n\n") if p.strip()]
                        break
        if not sections:
            raise MinerUError("MinerU zip contained no content_list.json or .md")
        return sections

    def _sections_from_payload(self, payload: dict[str, Any]) -> list[str]:
        # Async /tasks/{id}/result shape: results is keyed BY FILE STEM, since
        # the endpoint accepts several files per task.
        #   {"status": "completed",
        #    "results": {"手册": {"md_content": "...", "content_list": [...]}}}
        results = payload.get("results")
        if isinstance(results, dict) and results:
            sections: list[str] = []
            for per_file in results.values():
                if not isinstance(per_file, dict):
                    continue
                blocks = per_file.get("content_list")
                if isinstance(blocks, list) and blocks:
                    sections.extend(self._sections_from_blocks(blocks))
                    continue
                md = per_file.get("md_content") or per_file.get("md")
                if isinstance(md, str) and md.strip():
                    sections.extend(p.strip() for p in md.split("\n\n") if p.strip())
            if sections:
                return sections

        for key in ("content_list", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list) and value:
                return self._sections_from_blocks(value)
        md = payload.get("md") or payload.get("markdown")
        if isinstance(md, str) and md.strip():
            return [p.strip() for p in md.split("\n\n") if p.strip()]
        raise MinerUError(f"unrecognised MinerU payload keys: {list(payload)[:8]}")

    @staticmethod
    def _sections_from_blocks(blocks: list[Any]) -> list[str]:
        """Flatten MinerU content blocks, keeping tables as HTML.

        Tables are kept in HTML because that is what RAGFlow's own chunks
        store (``content_with_weight`` holds ``<table>...``), and retrieval
        quality depends on the table surviving as a unit.
        """
        out: list[str] = []
        for block in blocks:
            if not isinstance(block, dict):
                if isinstance(block, str) and block.strip():
                    out.append(block.strip())
                continue
            btype = block.get("type", "")
            if btype == "table":
                html = (block.get("table_body") or block.get("html")
                        or block.get("text") or "")
                if html.strip():
                    out.append(html.strip())
            elif btype in ("text", "title", "list", "equation", ""):
                text = block.get("text") or block.get("content") or ""
                if isinstance(text, list):
                    text = "\n".join(str(t) for t in text)
                if str(text).strip():
                    out.append(str(text).strip())
        return out
