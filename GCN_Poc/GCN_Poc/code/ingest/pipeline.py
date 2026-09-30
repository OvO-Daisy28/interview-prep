"""Pipeline protocol — what the orchestrator needs from any execution backend.

The orchestrator does not care HOW a document gets ingested; it needs to
start work, learn how far it got, and stop it. Two backends implement this:

  ``ChunksPipelineAdapter``  drives RAGFlow's own parser over HTTP (M1 route).
  ``SelfRunPipeline``        runs parse/chunk/embed/index ourselves and writes
                             into the shared infrastructure (方案 B, current).

Design §8 layer 3: swapping backends must not touch the state machine, the
scheduler, the REST API, or their tests.

Two execution shapes, one protocol
----------------------------------
RAGFlow's route is *submit-then-poll*: ``start_parse`` returns immediately and
progress arrives later via ``get_document_status``. Our own route is
*synchronous*: by the time ``start_parse`` returns, the work is done.

Rather than force one shape onto the other, the protocol keeps the poll-based
interface (it is the more general of the two) and ``SelfRunPipeline`` reports
a terminal status on the first poll. The orchestrator's loop is unchanged;
it simply sees a document that finished quickly.

Progress reporting is push-capable: a backend may invoke ``on_stage`` as it
moves between stages, so the self-run pipeline reports real stage boundaries
instead of the orchestrator inferring them from a log string.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

# Called by a backend when it enters/leaves a stage.
#   on_stage(stage_name, status, progress_pct, duration_ms | None, detail)
StageCallback = Callable[[str, str, int, "int | None", str], None]


class PipelineError(RuntimeError):
    """Raised when a pipeline backend fails or returns unusable data."""


@runtime_checkable
class IngestPipeline(Protocol):
    """Backend contract. Both HTTP-driven and self-run implementations satisfy it."""

    def upload_documents(
        self, kb_id: str, file_paths: list[str]
    ) -> list[dict[str, Any]]:
        """Persist the raw files and return one dict per document.

        Each dict must carry at least ``id`` (the document id downstream
        RAGFlow uses) and ``name``.
        """
        ...

    def start_parse(
        self, kb_id: str, doc_ids: list[str], *,
        on_stage: StageCallback | None = None,
    ) -> None:
        """Begin (or perform) parsing for the given documents."""
        ...

    def stop_parse(self, kb_id: str, doc_ids: list[str]) -> None:
        """Stop in-flight parsing. Used by force-pause and cancel (§5.3)."""
        ...

    def get_document_status(self, kb_id: str, doc_id: str) -> dict[str, Any]:
        """Return ``{run, progress, progress_msg, chunk_count, doc_id}``.

        ``run`` follows RAGFlow's vocabulary (UNSTART/RUNNING/CANCEL/DONE/FAIL)
        so the state machine stays backend-agnostic.
        """
        ...

    def start_graph_build(self, kb_id: str) -> None:
        """Trigger GraphRAG construction for the dataset."""
        ...

    def get_graph_build_progress(self, kb_id: str) -> dict[str, Any]:
        """Return ``{progress, progress_msg}`` for the graph build."""
        ...

    def delete_graph(self, kb_id: str) -> None:
        """Clear the graph — required before a rebuild (decision 3)."""
        ...
