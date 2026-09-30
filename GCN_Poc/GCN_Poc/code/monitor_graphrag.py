#!/usr/bin/env python3
"""Monitor the existing PTR GraphRAG task without mutating server state."""

import argparse
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
from ragflow_client import KB_GRAPH, get_graph, get_graphrag_progress

FAILURE_PATTERNS = (
    r"\bfailed(?:\s+after|:)",
    r"error processing chunk",
    r"maximum error count",
    r"no persisted graph found",
    r"api_key_disabled",
)


def validate_completed_graph(progress_message: str, graph: dict) -> tuple[list[str], int, int]:
    """Return failure patterns and graph size for a completed GraphRAG task."""
    normalized_message = progress_message.lower()
    failures = [
        pattern for pattern in FAILURE_PATTERNS if re.search(pattern, normalized_message)
    ]
    return failures, len(graph.get("nodes", [])), len(graph.get("edges", []))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--max-wait", type=int, default=6000)
    parser.add_argument("--kb-id", default=KB_GRAPH)
    args = parser.parse_args()
    if args.interval < 1 or args.max_wait < 1:
        parser.error("--interval and --max-wait must be positive")

    started = time.time()
    last_progress = None
    last_tail = None
    print(f"monitor_start={time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    while time.time() - started <= args.max_wait:
        progress = get_graphrag_progress(args.kb_id)
        value = progress.get("progress", 0)
        lines = [line.strip() for line in progress.get("progress_msg", "").splitlines() if line.strip()]
        tail = " | ".join(lines[-3:])
        if value != last_progress or tail != last_tail:
            elapsed = int(time.time() - started)
            print(
                f"{time.strftime('%H:%M:%S')} elapsed={elapsed}s progress={value} {tail}",
                flush=True,
            )
            last_progress = value
            last_tail = tail
        if value < 0:
            return 2
        if value >= 1:
            graph = get_graph(args.kb_id)
            failure_markers, node_count, edge_count = validate_completed_graph(
                progress.get("progress_msg", ""), graph
            )
            print(
                f"graph_validation nodes={node_count} edges={edge_count} "
                f"failure_markers={failure_markers}",
                flush=True,
            )
            if failure_markers or node_count < 1:
                return 4
            return 0
        time.sleep(args.interval)
    print("monitor_timeout", flush=True)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
