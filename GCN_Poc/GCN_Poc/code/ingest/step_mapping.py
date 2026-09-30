"""Map RAGFlow progress to pipeline stages (design §4.2, §8 layer 2).

REWRITTEN 2026-08-19 after calibrating against real 131 samples. The first
version guessed keywords and got 4 things wrong; see ``doc/design/
ingest-orchestration.md`` §4.2 for the corrected contract.

Two layers, deliberately separated:

1. **Real stages** (this is the truth we record): parsed from RAGFlow's
   ``progress_msg``, matching what the engine actually does.

       received -> chunk -> embed -> index -> done        (built-in /chunks)
       extract -> merge -> resolution -> community        (GraphRAG /index)

2. **PM prototype projection** (presentation only): the 5 steps the PM's
   HTML prototype shows (OCR/结构化/Embedding/实体关系/LLM抽取). Configurable
   via ``PM_STEP_PROJECTION`` — if the PM changes the wording or step count,
   edit that table, not the orchestrator.

SCOPE NOTE (confirmed with user 2026-08-19, per 项目经理沟通记录 line 38 and
项目经理汇报结论 P0 "导入编排"): this interface covers only the RAGFlow
pipeline. LLM parameter extraction / 复合参数拆分 / 信息块 / PBS 关联 belong
to the separate 内容解析子系统 (需新建, NOT RAGFlow 二开). Hence the PM's 5th
step "LLM抽取" is reported as ``not_applicable`` here — this interface has no
data source for it by design.

Real sample vocabulary observed on 131 (v0.26.1, PTR docx, 2026-08-19):

    Task has been received.
    Page(1~100000001): Generate 162 chunks
    Page(1~100000001): Embedding chunks (114.90s)
    Page(1~100000001): Indexing done (41.82s).
    Page(1~100000001): Task done (165.66s)

Note the trap: ``Embedding chunks`` contains BOTH "embedding" and "chunk",
and progress_msg is CUMULATIVE (every poll returns the whole log). So we scan
for the LAST stage marker present, most-advanced-wins — never first-match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class StepStatus(str, Enum):
    """Per-step status (kept compatible with the PM prototype vocabulary)."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"           # stage does not apply to this doc/pipeline
    NOT_APPLICABLE = "not_applicable"  # no data source in this interface


# ---------------------------------------------------------------------------
# Layer 1: real stages
# ---------------------------------------------------------------------------

# Ingest stages, ordered. These are the stages we actually execute in the
# self-run pipeline; when driving RAGFlow over HTTP the same names are inferred
# from progress_msg ("received" is RAGFlow-only — a queue marker, not work).
PARSE_STAGES: tuple[str, ...] = ("parse", "chunk", "embed", "index")

# Recognised but not part of the ordered pipeline: RAGFlow emits this before
# any real work starts, so it is tracked for diagnosis only.
RAGFLOW_ONLY_STAGES: tuple[str, ...] = ("received",)

# GraphRAG build (POST /datasets/{kb}/index?type=graph). Ordered.
# TODO calibrate against a real graph build run (M5); markers below come from
# ragflow_operations.md logs, not yet from a live capture.
GRAPH_STAGES: tuple[str, ...] = ("extract", "merge", "resolution", "community")

# Stages that are pure markers, not real work — never attach a duration to
# them (RAGFlow reports none, and wall-clock would just measure our polling).
MARKER_ONLY_STAGES: frozenset[str] = frozenset({"received", "parse"})

# Stage -> regexes matching that stage's marker in progress_msg.
# Order within the dict does not matter; we pick the MOST ADVANCED match.
STAGE_MARKERS: dict[str, tuple[re.Pattern[str], ...]] = {
    "received": (re.compile(r"task\s+has\s+been\s+received", re.I),
                 re.compile(r"task\s+is\s+queued", re.I)),
    "parse":    (re.compile(r"start\s+to\s+parse", re.I),
                 re.compile(r"task\s+has\s+been\s+received", re.I),
                 re.compile(r"task\s+is\s+queued", re.I)),
    "chunk":    (re.compile(r"generate\s+\d+\s+chunks?", re.I),
                 re.compile(r"finish\s+parsing", re.I),
                 # real 131 failure capture: the error line names the stage
                 re.compile(r"error.*while\s+chunking", re.I),
                 re.compile(r"file\s+type\s+not\s+supported", re.I)),
    "embed":    (re.compile(r"embedding\s+chunks?", re.I),
                 re.compile(r"start\s+to\s+embedding", re.I)),
    "index":    (re.compile(r"indexing\s+done", re.I),
                 re.compile(r"start\s+to\s+index", re.I),
                 re.compile(r"\[doc\s+engine\]", re.I)),
    # GraphRAG
    "extract":    (re.compile(r"entit(y|ies)\s+extract", re.I),
                   re.compile(r"extract.*entit", re.I)),
    "merge":      (re.compile(r"merge.*subgraph", re.I),
                   re.compile(r"get\s+embedding\s+of\s+nodes", re.I)),
    "resolution": (re.compile(r"entity\s+resolution", re.I),
                   re.compile(r"resolution", re.I)),
    "community":  (re.compile(r"communit", re.I),),
}

# "Task done (165.66s)" — terminal marker, not a stage of its own.
_DONE_RE = re.compile(r"task\s+done\s*\(([\d.]+)s\)", re.I)
# Any "(12.34s)" duration RAGFlow reports inline.
_DURATION_RE = re.compile(r"\(([\d.]+)\s*s\)")

_RUN_MAP: dict[str, str] = {
    "0": "UNSTART", "1": "RUNNING", "2": "CANCEL", "3": "DONE", "4": "FAIL",
    "UNSTART": "UNSTART", "RUNNING": "RUNNING",
    "CANCEL": "CANCEL", "DONE": "DONE", "FAIL": "FAIL",
}


@dataclass
class StageState:
    """One real stage's state."""

    name: str
    status: StepStatus = StepStatus.QUEUED
    progress: int = 0
    duration_ms: int | None = None   # parsed from RAGFlow's own "(x.xxs)"
    detail: str = ""                 # the matched log line, for diagnosis


@dataclass
class ParseSnapshot:
    """Everything one poll of a document tells us."""

    run: str
    progress: int
    active_stage: str | None
    stages: list[StageState] = field(default_factory=list)
    total_duration_ms: int | None = None


def normalize_run(run: str) -> str:
    """Normalize RAGFlow run (text or number) to UNSTART/RUNNING/CANCEL/DONE/FAIL."""
    return _RUN_MAP.get(str(run).strip().upper(), str(run).strip().upper())


def _lines(progress_msg: str) -> list[str]:
    return [ln.strip() for ln in (progress_msg or "").splitlines() if ln.strip()]


def most_advanced_stage(progress_msg: str, stages: tuple[str, ...]) -> tuple[str | None, dict[str, str]]:
    """Return the furthest stage mentioned in the cumulative log, plus per-stage lines.

    progress_msg is cumulative: it holds every stage reached so far. Matching
    the FIRST keyword would misread ``Embedding chunks`` as the chunk stage
    (it contains "chunk"), so we take the most advanced stage that matched.
    """
    hits: dict[str, str] = {}
    for line in _lines(progress_msg):
        for stage in stages:
            for pattern in STAGE_MARKERS.get(stage, ()):
                if pattern.search(line):
                    hits[stage] = line  # later lines overwrite: keep newest
                    break
    if not hits:
        return None, hits
    # most advanced = highest index in the ordered stage tuple
    active = max(hits, key=lambda s: stages.index(s))
    return active, hits


def _duration_ms(line: str) -> int | None:
    """Extract RAGFlow's own reported duration, e.g. 'Embedding chunks (114.90s)'."""
    m = _DURATION_RE.search(line or "")
    if not m:
        return None
    try:
        return int(float(m.group(1)) * 1000)
    except ValueError:
        return None


def parse_progress(
    run: str,
    progress: float,
    progress_msg: str = "",
    *,
    stages: tuple[str, ...] = PARSE_STAGES,
) -> ParseSnapshot:
    """Project one RAGFlow poll onto real stages with real durations."""
    run_norm = normalize_run(run)
    pct = max(0, min(100, int((progress or 0) * 100)))
    active, hits = most_advanced_stage(progress_msg, stages)

    done_match = _DONE_RE.search(progress_msg or "")
    total_ms = _duration_ms(done_match.group(0)) if done_match else None

    states: list[StageState] = []
    active_idx = stages.index(active) if active else -1

    for i, name in enumerate(stages):
        line = hits.get(name, "")
        dur = _duration_ms(line)
        if run_norm == "DONE":
            states.append(StageState(name, StepStatus.DONE, 100, dur, line))
        elif run_norm == "UNSTART":
            states.append(StageState(name, StepStatus.QUEUED, 0, None, ""))
        elif run_norm == "CANCEL":
            st = StepStatus.DONE if i < active_idx else StepStatus.PENDING
            states.append(StageState(name, st, 100 if i < active_idx else 0, dur, line))
        elif run_norm == "FAIL":
            if i < active_idx:
                states.append(StageState(name, StepStatus.DONE, 100, dur, line))
            elif i == active_idx:
                states.append(StageState(name, StepStatus.FAILED, pct, dur, line))
            else:
                states.append(StageState(name, StepStatus.QUEUED, 0, None, ""))
        else:  # RUNNING
            if i < active_idx:
                states.append(StageState(name, StepStatus.DONE, 100, dur, line))
            elif i == active_idx:
                states.append(StageState(name, StepStatus.RUNNING, pct, dur, line))
            else:
                states.append(StageState(name, StepStatus.QUEUED, 0, None, ""))

    return ParseSnapshot(run_norm, pct, active, states, total_ms)


# ---------------------------------------------------------------------------
# Layer 2: PM prototype projection (presentation only, configurable)
# ---------------------------------------------------------------------------

# PM prototype's 5 steps (doc/原型/POC/js/mock-data.js) -> which real stage
# feeds each. ``None`` = no data source in this interface (see SCOPE NOTE).
PM_STEP_PROJECTION: tuple[tuple[str, str, str | None], ...] = (
    # (pm_key, pm_label, source_real_stage)
    ("ocr",    "OCR识别",   "parse"),   # OCR is part of parsing; only scanned docs
    ("struct", "结构化",     "chunk"),   # = chunking (NOT parameter extraction)
    ("embed",  "Embedding", "embed"),
    ("entity", "实体关系",   "extract"), # GraphRAG only
    ("llm",    "LLM抽取",   None),      # 参数提取 — 内容解析子系统, not this interface
)


def project_to_pm_steps(
    parse: ParseSnapshot,
    graph: ParseSnapshot | None = None,
    *,
    is_scanned: bool = False,
) -> list[StageState]:
    """Project real stages onto the PM prototype's 5 steps (presentation).

    Steps with no data source report ``not_applicable``; steps whose stage
    does not apply to this document (e.g. OCR on a .docx, GraphRAG stages on a
    plain-RAG dataset) report ``skipped``.
    """
    by_name: dict[str, StageState] = {s.name: s for s in parse.stages}
    if graph:
        by_name.update({s.name: s for s in graph.stages})

    out: list[StageState] = []
    for pm_key, _label, source in PM_STEP_PROJECTION:
        if source is None:
            out.append(StageState(pm_key, StepStatus.NOT_APPLICABLE, 0, None,
                                  "参数提取属内容解析子系统，不在本接口范围"))
            continue
        if pm_key == "ocr" and not is_scanned:
            out.append(StageState(pm_key, StepStatus.SKIPPED, 0, None,
                                  "非扫描件无需 OCR"))
            continue
        if pm_key == "entity" and graph is None:
            out.append(StageState(pm_key, StepStatus.SKIPPED, 0, None,
                                  "普通 RAG 链路无 GraphRAG 抽取"))
            continue
        src = by_name.get(source)
        if src is None:
            out.append(StageState(pm_key, StepStatus.QUEUED, 0, None, ""))
        else:
            out.append(StageState(pm_key, src.status, src.progress,
                                  src.duration_ms, src.detail))
    return out
