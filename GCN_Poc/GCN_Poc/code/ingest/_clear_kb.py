"""清空测试 KB 的所有文档（先停解析再删）。容器内跑。

发现：DELETE /documents 的参数是 'ids' 不是 'document_ids'（后者 code:101）。
文档在 RUNNING 状态时也要先 DELETE /chunks 停解析再删。
"""
import requests

KB = "2f84a97aab4811f1a5be33e6206585a1"
TOKEN = "ragflow-jViws3pYe3tAxCiLQ7LgjsJ-SRYF730cGMDXKptJk98"
BASE = "http://localhost:9380"
HEADERS = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}


def list_all():
    all_docs = []
    page = 1
    while True:
        r = requests.get(f"{BASE}/api/v1/datasets/{KB}/documents",
                          params={"page": page, "page_size": 100}, headers=HEADERS, timeout=30)
        data = r.json().get("data") or {}
        batch = data.get("docs", []) or []
        if not batch:
            break
        all_docs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return all_docs


def main():
    docs = list_all()
    print("before clear:", len(docs))
    if not docs:
        return
    run_dist = {}
    for d in docs:
        run_dist[d.get("run", "?")] = run_dist.get(d.get("run", "?"), 0) + 1
    print("run distribution:", run_dist)

    ids = [d["id"] for d in docs]

    # 1. 先停解析（DELETE /chunks，参数 document_ids）— 清掉 RUNNING 的
    resp = requests.delete(f"{BASE}/api/v1/datasets/{KB}/chunks",
                           json={"document_ids": ids}, headers=HEADERS, timeout=60)
    print(f"stop parse: HTTP {resp.status_code} body={resp.text[:200]}")

    # 2. 删文档（DELETE /documents，参数 ids）
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        resp = requests.delete(f"{BASE}/api/v1/datasets/{KB}/documents",
                        json={"ids": batch}, headers=HEADERS, timeout=60)
        print(f"delete {i}-{i+len(batch)}: HTTP {resp.status_code} body={resp.text[:150]}")

    # 3. 复查
    remain = list_all()
    print("after clear:", len(remain))


if __name__ == "__main__":
    main()
