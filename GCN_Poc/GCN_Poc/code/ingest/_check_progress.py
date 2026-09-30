"""查 KB 当前文档 run 状态分布（快速，看测试跑到哪了）。"""
import requests

KB = "2f84a97aab4811f1a5be33e6206585a1"
TOKEN = "ragflow-jViws3pYe3tAxCiLQ7LgjsJ-SRYF730cGMDXKptJk98"
H = {"Authorization": "Bearer " + TOKEN}

# 拉全部
all_docs = []
page = 1
while True:
    r = requests.get(f"http://localhost:9380/api/v1/datasets/{KB}/documents",
                     params={"page": page, "page_size": 100}, headers=H, timeout=30)
    data = r.json().get("data") or {}
    batch = data.get("docs", []) or []
    if not batch:
        break
    all_docs.extend(batch)
    if len(batch) < 100:
        break
    page += 1

runs = {}
for x in all_docs:
    rv = x.get("run", "?")
    runs[rv] = runs.get(rv, 0) + 1
print("total:", len(all_docs), "runs:", runs)
# 看 progress 分布
progs = [round(x.get("progress", 0), 3) for x in all_docs]
print("progress range:", min(progs) if progs else 0, "-", max(progs) if progs else 0)
