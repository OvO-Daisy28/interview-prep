#!/usr/bin/env python3
"""Delete and rebuild the PTR GraphRAG graph after explicit confirmation."""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter

from ragflow_client import (
    KB_GRAPH,
    delete_graph,
    get_graph,
    get_graphrag_progress,
    trigger_graphrag,
    update_graphrag_config,
)

CONFIRMATION = "DELETE_AND_REBUILD_PTR_GRAPH"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete the current PTR graph and start a complete rebuild."
    )
    parser.add_argument("--merge-timeout", type=int, default=900)
    parser.add_argument(
        "--max-wait", type=int, default=5400, help="Maximum polling time in seconds"
    )
    parser.add_argument(
        "--confirm-delete",
        metavar="TOKEN",
        help=f"Required destructive-operation token: {CONFIRMATION}",
    )
    args = parser.parse_args()
    if args.merge_timeout < 1 or args.max_wait < 1:
        parser.error("--merge-timeout and --max-wait must be positive")
    if args.confirm_delete != CONFIRMATION:
        parser.error(
            f"graph deletion was not confirmed; pass --confirm-delete {CONFIRMATION}"
        )
    return args


def main() -> int:
    args = parse_args()
    effective = update_graphrag_config(
        KB_GRAPH,
        merge_timeout_seconds=args.merge_timeout,
        retry_attempts=2,
    )
    print(
        "GraphRAG config verified: "
        f"merge_timeout_seconds={effective['merge_timeout_seconds']}, "
        f"retry_attempts={effective['retry_attempts']}"
    )

    delete_graph(KB_GRAPH)
    print("Current graph deleted")
    trigger_graphrag(KB_GRAPH)
    print("GraphRAG rebuild triggered")

    started = time.monotonic()
    last_progress = None
    terminal_status = "timeout"
    while time.monotonic() - started < args.max_wait:
        progress = get_graphrag_progress(KB_GRAPH)
        value = progress["progress"]
        if value != last_progress:
            print(f"elapsed={int(time.monotonic() - started)}s progress={value:.2f}")
            for line in progress["progress_msg"].splitlines()[-3:]:
                if line.strip():
                    print(f"  {line}")
            last_progress = value
        if value < 0:
            terminal_status = "failed"
            break
        if value >= 1:
            terminal_status = "completed"
            break
        time.sleep(30)

    graph = get_graph(KB_GRAPH)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    print(f"status={terminal_status}, nodes={len(nodes)}, edges={len(edges)}")
    if nodes:
        entity_types = Counter(node.get("entity_type", "?") for node in nodes)
        print(f"entity_types={dict(entity_types.most_common())}")
    return 0 if terminal_status == "completed" and nodes and edges else 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
