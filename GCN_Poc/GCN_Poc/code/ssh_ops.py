#!/usr/bin/env python3
"""Inspect or operate the 131 GraphRAG worker through JumpServer."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time

RAGFLOW_CONTAINER = os.environ.get("RAGFLOW_CONTAINER", "docker-ragflow-cpu-1")
REDIS_CONTAINER = os.environ.get("RAGFLOW_REDIS_CONTAINER", "docker-redis-1")


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def ssh_command() -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "IdentitiesOnly=yes",
        "-i",
        required_env("RAGFLOW_SSH_KEY"),
        "-p",
        os.environ.get("RAGFLOW_SSH_PORT", "2222"),
        required_env("RAGFLOW_SSH_TARGET"),
    ]


def run_remote(command: str, *, timeout: int = 60) -> str:
    result = subprocess.run(
        ssh_command() + [command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"remote command failed: {result.returncode}")
    return result.stdout


def redis_cli(command: str) -> str:
    password = shlex.quote(required_env("RAGFLOW_REDIS_PASSWORD"))
    return run_remote(
        f"docker exec {shlex.quote(REDIS_CONTAINER)} redis-cli -a {password} -n 1 {command}"
    )


def check() -> None:
    print("=== task_executor processes ===")
    print(
        run_remote(
            f"docker exec {shlex.quote(RAGFLOW_CONTAINER)} bash -c "
            "'ps aux | grep task_executor | grep -v grep'"
        )
    )
    print("=== Redis stream groups ===")
    print(redis_cli("XINFO GROUPS te.0.common"))
    print("=== Redis stream consumers ===")
    print(redis_cli("XINFO CONSUMERS te.0.common rag_flow_svr_task_broker"))
    print("=== GraphRAG worker heartbeat ===")
    print(redis_cli("ZREVRANGE task_executor_graphrag_0 0 0 WITHSCORES"))
    print("=== GraphRAG worker log tail ===")
    print(
        run_remote(
            f"docker exec {shlex.quote(RAGFLOW_CONTAINER)} bash -c "
            "'tail -30 /tmp/graphrag_worker.log 2>/dev/null; "
            "tail -30 /ragflow/logs/task_executor_graphrag*.log 2>/dev/null'"
        )
    )


def start_worker() -> None:
    print(
        run_remote(
            f"docker exec -d {shlex.quote(RAGFLOW_CONTAINER)} bash -c "
            "'cd /ragflow && nohup python -m rag.svr.task_executor -t graphrag "
            "> /tmp/graphrag_worker.log 2>&1'"
        )
    )


def restart_worker() -> None:
    run_remote(
        f"docker exec {shlex.quote(RAGFLOW_CONTAINER)} bash -c "
        "'pkill -f \"python -m rag.svr.task_executor -t graphrag\" || true'"
    )
    time.sleep(3)
    start_worker()
    time.sleep(2)
    print(
        run_remote(
            f"docker exec {shlex.quote(RAGFLOW_CONTAINER)} bash -c "
            "'ps aux | grep task_executor | grep -v grep'"
        )
    )


def restart_container() -> None:
    print(run_remote(f"docker restart {shlex.quote(RAGFLOW_CONTAINER)}", timeout=120))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("check", "start_worker", "restart_worker", "restart_container"),
        nargs="?",
        default="check",
    )
    args = parser.parse_args()
    actions = {
        "check": check,
        "start_worker": start_worker,
        "restart_worker": restart_worker,
        "restart_container": restart_container,
    }
    actions[args.action]()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
