"""M5 setup: create a dedicated KB, ingest OUR chunks, ready for graph build.

Why a new KB instead of reusing PTR_GraphRAG: that KB's graph is the
validated POC baseline (256 nodes / 41 community reports, decision 9) and
rebuilding it would destroy the reference. A small dedicated KB also keeps
the build fast — a handful of chunks instead of 162 — while still proving the
one assumption M5 exists to check: GraphRAG reads chunks from ES and does not
care who wrote them.

Run inside the container; needs RAGFLOW_API_KEY in the environment.

Usage:
    docker exec -e RAGFLOW_API_KEY=... docker-ragflow-cpu-1 bash -c \
      "cd /ragflow && PYTHONPATH=/ragflow python /ragflow/ingest/m5_setup.py"
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "/ragflow")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest.selfrun_pipeline import SelfRunPipeline  # noqa: E402

TENANT = "56f78bf26ac611f187cd7db89d62ca74"
API = "http://localhost:9380"

# entity vocabulary matches the PTR config (decision 2): these types are what
# the extraction prompt asks for, so the text uses them deliberately.
DOC = """PTR余热排出系统设备手册（M5 自研摄入验证）

一、设备概述
PTR冷却泵是核电站余热排出系统的关键设备，用于停堆后导出堆芯余热。
RRI冷却泵与PTR冷却泵同属核三级设备，由重庆水泵厂制造。

二、主要技术参数
额定流量：640立方米每小时。
额定扬程：36米。
转速：1480转每分钟。
电机功率：90千瓦。
入口压力：0.35兆帕。

三、部件构成
PTR冷却泵由叶轮、泵壳、轴承、机械密封和联轴器组成。
叶轮采用双吸结构，材料为不锈钢。
机械密封为集装式单端面密封。

四、常见故障与处理
故障现象：泵体振动超标。
可能原因：叶轮不平衡、轴承磨损、联轴器对中不良。
处理措施：检查叶轮动平衡，更换磨损轴承，重新对中联轴器。

故障现象：轴封泄漏量增大。
可能原因：机械密封面磨损。
处理措施：更换机械密封组件。

五、维护标准
每运行2000小时检查轴承润滑状态。
解体检修周期为一年，需更换机械密封和O型圈。
振动限值执行GB/T6075标准。"""


def api(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {os.environ['RAGFLOW_API_KEY']}")
    return json.load(urllib.request.urlopen(req, timeout=60))


def main() -> int:
    # 1. create the KB, graphrag enabled from the start (same shape as PTR)
    payload = {
        "name": "m5_selfrun_graphrag",
        "chunk_method": "naive",
        "parser_config": {
            "pages": [[1, 1000000]],
            "graphrag": {
                "use_graphrag": True,
                "method": "general",
                "entity_types": ["设备", "部件", "参数", "故障现象",
                                 "故障原因", "处理措施", "标准"],
                "community": True,
                "resolution": True,
                "batch_chunk_token_size": 4096,
            },
        },
    }
    resp = api("POST", "/api/v1/datasets", payload)
    assert resp.get("code") == 0, f"create dataset failed: {resp}"
    kb_id = resp["data"]["id"]
    print(f"[m5] kb created: {kb_id} (m5_selfrun_graphrag)")

    # 2. ingest one document ENTIRELY through our own pipeline (real embedder)
    doc_path = Path("/tmp/m5_doc.txt")
    doc_path.write_text(DOC, encoding="utf-8")

    pipe = SelfRunPipeline(tenant_id=TENANT)
    warm = pipe.warm_up(kb_id=kb_id)
    print(f"[m5] warm-up: {warm.get('settings_ms', 0):.0f}ms "
          f"mysql={warm.get('mysql_ms', 0):.0f}ms "
          f"docstore={warm.get('docstore_ms', 0):.0f}ms")

    docs = pipe.upload_documents(kb_id, [str(doc_path)])
    doc_id = docs[0]["id"]
    pipe.start_parse(kb_id, [doc_id])
    st = pipe.get_document_status(kb_id, doc_id)
    print(f"[m5] ingested via self-run pipeline: run={st['run']} "
          f"chunks={st['chunk_count']} doc_id={doc_id}")
    assert st["run"] == "DONE", st

    # 3. sanity: the chunks are in ES under the new kb_id
    from common import settings as s
    from rag.nlp.search import index_name
    res = s.docStoreConn.es.search(index=index_name(TENANT),
                                   query={"term": {"kb_id": kb_id}}, size=5)
    total = res["hits"]["total"]["value"] if isinstance(res["hits"]["total"], dict) \
        else res["hits"]["total"]
    print(f"[m5] ES chunks under new kb: {total}")
    assert total >= 3, "expected several chunks in ES"

    print(f"\n[m5] ready. trigger with:")
    print(f"  curl -X POST '{API}/api/v1/datasets/{kb_id}/index?type=graph' "
          f"-H 'Authorization: Bearer $RAGFLOW_API_KEY' -H 'Content-Length: 0'")
    print(f"KB_ID={kb_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
