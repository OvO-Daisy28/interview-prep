"""建一个新的 RAGFlow 知识库，用于隔离每次测试数据。

在 RAGFlow 容器内跑，复用 RAGFlow 自己的 service 层建库（create_with_name + 继承租户默认
embd_id + save），和 RAGFlow web 界面建库完全一致。

ES index 是 tenant 级别（ragflow_<tenant>），新 KB 共用，无需 init；MinIO bucket=kb_id
在首次写数据时自动创建。所以建库只需插入 knowledgebase 表一行。

Usage（4090 容器内）:
    docker exec docker-ragflow-gpu-1 /ragflow/.venv/bin/python3 \
      /ragflow/ingest/create_kb.py --name "GPU服务测试_0911" \
      --tenant-id 8a0845faace211f1850e49f1b996babd
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "/ragflow")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="知识库名")
    ap.add_argument(
        "--tenant-id",
        default="8a0845faace211f1850e49f1b996babd",
        help="租户 ID（4090 默认 admin's Kingdom）",
    )
    args = ap.parse_args()

    from common import settings
    settings.init_settings()

    from api.db.services.knowledgebase_service import KnowledgebaseService
    from api.db.services.user_service import TenantService

    ok, t = TenantService.get_by_id(args.tenant_id)
    if not ok:
        print(f"[create_kb] tenant {args.tenant_id} not found", file=sys.stderr)
        return 1

    ok, payload = KnowledgebaseService.create_with_name(
        name=args.name, tenant_id=args.tenant_id)
    if not ok:
        print(f"[create_kb] create_with_name failed: {payload}", file=sys.stderr)
        return 1

    # 继承租户默认 embedding（4090 上是 bge-base → bge-gpu GPU）
    payload["embd_id"] = t.embd_id

    if not KnowledgebaseService.save(**payload):
        print("[create_kb] save failed", file=sys.stderr)
        return 1

    # 输出：KB id（脚本唯一 stdout，便于捕获）
    print(payload["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
