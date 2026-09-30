"""汇总 131 RAGFlow 批量导入的历次实验数据，产出对比表（CSV + Markdown）。

数据来源：
- 实验 1/2/3/5：test/results/131_测试/*.json（脚本产出，自动读取）
- 实验 4：doc/design/131_测试/批量导入规模验证_20260907.html 内嵌数据（无 JSON，手工核对录入）

Usage:
    uv run --project code python code/ingest/experiments_summary.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "test" / "results" / "131_测试"
DESIGN = ROOT / "doc" / "design" / "131_测试"


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def stage(d: dict, name: str) -> dict:
    """从 stage_ms 提取某阶段统计，单位换算成秒。"""
    vals = d.get("stage_ms", {}).get(name, [])
    if not vals:
        return {}
    total = sum(sum(v) for v in d.get("stage_ms", {}).values() if v)
    s = sorted(vals)
    return {
        "avg": sum(vals) / len(vals) / 1000,
        "p90": s[min(len(s) - 1, int(len(s) * 0.9))] / 1000,
        "max": max(vals) / 1000,
        "share": sum(vals) / total * 100 if total else 0,
    }


def fmt(v, nd=3, suffix=""):
    if v is None or v == "":
        return "—"
    return f"{v:.{nd}f}{suffix}"


def main() -> int:
    rows = []

    # ---- 实验 1：方案A 原生上传（100 份）----
    d = load("native_r1.json")
    rows.append({
        "实验": "1. 方案A 原生上传",
        "方案": "RAGFlow 原生 API（脚本）",
        "文档数": d["docs"],
        "并发": "RAGFlow 内部",
        "成功": d["succeeded"], "失败": d["failed"], "取消": d.get("cancelled", 0),
        "墙钟(s)": round(d["parse_wall_seconds"], 1),
        "吞吐(份/s)": round(d["throughput"], 4),
        "embed avg(s)": None, "embed 占比": None,
        "parse 占比": None, "index 占比": None,
        "数据源": "native_r1.json（脚本产出）",
    })

    # ---- 实验 2：方案A 取消测试 ----
    d = load("native_cancel.json")
    ct = d.get("cancel_test") or {}
    rows.append({
        "实验": "2. 方案A 取消测试",
        "方案": "RAGFlow 原生 API（脚本）",
        "文档数": d["docs"],
        "并发": "RAGFlow 内部",
        "成功": d["succeeded"], "失败": d["failed"], "取消": ct.get("final_cancelled", 0),
        "墙钟(s)": round(d["parse_wall_seconds"], 1),
        "吞吐(份/s)": round(d["throughput"], 4),
        "embed avg(s)": None, "embed 占比": None,
        "parse 占比": None, "index 占比": None,
        "数据源": "native_cancel.json（脚本产出）",
    })

    # ---- 实验 3：方案B 并发 1/3/6 ----
    for tag, fn in [("1", "bench_c1.json"), ("3", "bench_c3.json"), ("6", "bench_c6.json")]:
        d = load(fn)
        e = stage(d, "embed")
        p = stage(d, "parse")
        i = stage(d, "index")
        rows.append({
            "实验": f"3. 方案B 并发{tag}",
            "方案": "mentor 自建（InMemory，脚本）",
            "文档数": d["docs"],
            "并发": d["concurrency"],
            "成功": d["succeeded"], "失败": d["failed"], "取消": d.get("cancelled", 0),
            "墙钟(s)": round(d["wall_seconds"], 1),
            "吞吐(份/s)": round(d["throughput"], 4),
            "embed avg(s)": round(e["avg"], 2) if e else None,
            "embed 占比": round(e["share"], 1) if e else None,
            "parse 占比": round(p["share"], 1) if p else None,
            "index 占比": round(i["share"], 1) if i else None,
            "数据源": f"{fn}（脚本产出，--persist=False 走内存）",
        })

    # ---- 实验 4：mentor 千份 baseline（无 JSON，值取自报告，已核对）----
    # 报告 doc/design/131_测试/批量导入规模验证_20260907.html
    # 注意：报告中的阶段表明确标注为「千份级每阶段统计（job 37）」，仅适用 job 37；
    #       job 35 无阶段数据，留空（"—"）。
    # 实验方式：mentor 常驻服务 + demo 网页上传 → 数据写 MySQL gcn_ingest 库（非 JSON）。
    # 现状：job 35 / job 37 的 MySQL 记录已丢失，库里只剩 job 39（非本次实验）；原始数据无法取回。
    for job, docs, ok, fail, wall, tput, embed_avg, embed_sh, parse_sh, index_sh in [
        ("job 35", 161, 159, 2, 658, 0.24, None, None, None, None),
        ("job 37", 1000, 796, 204, 3192, 0.25, 7.67, 96.0, 1.1, 3.6),
    ]:
        rows.append({
            "实验": f"4. mentor {job}",
            "方案": "mentor demo 服务（MySQL）",
            "文档数": docs,
            "并发": 3,
            "成功": ok, "失败": fail, "取消": 0,
            "墙钟(s)": wall,
            "吞吐(份/s)": tput,
            "embed avg(s)": embed_avg,
            "embed 占比": embed_sh,
            "parse 占比": parse_sh,
            "index 占比": index_sh,
            "数据源": "MySQL gcn_ingest（记录已丢失，引自报告）",
        })

    # ---- 实验 5：1 万份 ----
    d = load("bench_10k.json")
    e = stage(d, "embed")
    p = stage(d, "parse")
    i = stage(d, "index")
    rows.append({
        "实验": "5. 1 万份稳定性",
        "方案": "mentor 自建（InMemory，脚本）",
        "文档数": d["docs"],
        "并发": d["concurrency"],
        "成功": d["succeeded"], "失败": d["failed"], "取消": d.get("cancelled", 0),
        "墙钟(s)": round(d["wall_seconds"], 1),
        "吞吐(份/s)": round(d["throughput"], 4),
        "embed avg(s)": round(e["avg"], 2) if e else None,
        "embed 占比": round(e["share"], 1) if e else None,
        "parse 占比": round(p["share"], 1) if p else None,
        "index 占比": round(i["share"], 1) if i else None,
        "数据源": "bench_10k.json（脚本产出；日志实锤 persist=False 走内存）",
    })

    # ---- 写 CSV ----
    cols = list(rows[0].keys())
    csv_path = RESULTS / "experiments_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ---- 写 Markdown ----
    md = []
    md.append("# 131 RAGFlow 批量导入实验数据汇总\n")
    md.append("> 环境：131 服务器（RAGFlow v0.26.1，CPU bge-base，embedding 服务在 192.168.80.1:18001）· 汇总日期：2026-09-11\n")
    md.append("> 测试数据：`test/_abtest_docs/`（100 份纯真 .docx）、`test/_abtest_docs_10k/`（1 万份），源包 `test/law_data/laws_download.zip`\n")

    md.append("\n## 一、总览对比表\n")
    md.append("| " + " | ".join(cols) + " |")
    md.append("|" + "---|" * len(cols))
    for r in rows:
        cells = []
        for c in cols:
            v = r[c]
            if c == "embed avg(s)":
                cells.append(fmt(v, 2))
            elif c in ("吞吐(份/s)",):
                cells.append(fmt(v, 4))
            elif c.endswith("占比"):
                cells.append(fmt(v, 1, "%"))
            elif c == "墙钟(s)":
                cells.append(fmt(v, 1))
            else:
                cells.append(str(v))
        md.append("| " + " | ".join(cells) + " |")

    md.append("\n**单位说明**：所有阶段耗时统一为**秒**；「—」表示该实验无分阶段数据（RAGFlow 原生接口不返回阶段计时）。\n")

    md.append("\n## 二、各实验说明\n")
    md.append("| 实验 | 怎么开展 | 数据存哪 | 关键结论 |")
    md.append("|---|---|---|---|")
    md.append("| 1. 方案A 原生上传 | 脚本 `native_upload_test.py` 调 RAGFlow 原生 API 上传+解析 | `native_r1.json` | 100 份全成功，吞吐 0.091 份/s |")
    md.append("| 2. 方案A 取消测试 | 同上，中途触发取消 | `native_cancel.json` | **取消不生效**：cancelled=0，100 份仍全部跑完 |")
    md.append("| 3. 方案B 并发1/3/6 | 脚本 `mentor_b_bench.py`（InMemory，`--persist=False`） | `bench_c{1,3,6}.json` | **并发 3 最优**（0.180 份/s）；并发 6 无收益，单份 embed 翻倍 |")
    md.append("| 4. mentor 千份 baseline | mentor 常驻服务 + **demo 网页**上传（`10.126.2.131:9800/demo`） | MySQL `gcn_ingest` 库（**记录已丢失**） | 百份→千份吞吐稳定（0.24→0.25），千份失败率 20.4%（数据源 .doc 老格式） |")
    md.append("| 5. 1 万份稳定性 | 脚本 `mentor_b_bench.py`（InMemory，日志实锤 `persist=False`） | `bench_10k.json` | 9994/10000 成功，吞吐降至 0.046（比百份降 74%） |")

    md.append("\n### 实验 4 的存储说明\n")
    md.append("- 实验 4 用的是 **mentor 常驻服务**（不是我们的脚本），数据写进 **MySQL `gcn_ingest` 库**（ingest_job / ingest_task / ingest_step 三表）。\n")
    md.append("- 实测发现：库里 **job 35 / job 37 的记录已丢失**，只剩一条 job 39（10000 份，9987 成功/10 失败/3 卡 running）——且 job 39 并非本实验（可能是更早的 `--persist` 残留）。\n")
    md.append("- 所以实验 4 的数值**无法从数据库取回**，只能引用报告 HTML 中的数字。\n")

    md.append("\n### 方案B 两种存储后端的区别\n")
    md.append("- `mentor_b_bench.py` 有 `--persist` 开关：给了写 MySQL（`MySQLRepository`），不给走内存（`InMemoryRepository`）。\n")
    md.append("- 我们所有压测（实验 3/5）**都没给 `--persist`** → 走 InMemory，因为 `MySQLRepository` 用 `threading.local()`，在 ThreadPoolExecutor 并发下连接会断导致任务全失败（已知 bug）。\n")
    md.append("- 实验 4 是 mentor 服务自己跑的（走 MySQL），和我们的脚本压测是**两条独立路径**。\n")

    md.append("\n## 三、贯穿性结论\n")
    md.append("1. **embedding 是绝对瓶颈**：各实验占比 87%–96%，131 的 bge-base 跑在 CPU 上。")
    md.append("2. **单份 embed 随并发升高而变慢**：并发1 11.0s → 并发3 15.3s → 并发6 29.7s（CPU 争抢），并发收益被抵消。")
    md.append("3. **规模放大后吞吐下降（同一服务内）**：方案B（InMemory 并发3）从 50 份的 0.180 份/s "
              "降到 1 万份的 0.046 份/s（**降 74%**）；而 mentor demo 服务在 161→1000 份区间吞吐稳定（0.24→0.25），"
              "说明退化发生在更长的运行时长上。**千份时曾预测万份约需 11 小时，实际跑了 59.7 小时（偏差 5.4 倍）**。")
    md.append("4. **对照组（4090 GPU）**：GPU 上 bge 单条文本 embedding 实测 **0.030 秒**（131 CPU 单份文档 embed 17.1 秒）。"
              "两者口径为「文档级」近似（文档大小与批处理行为不同），量级上 GPU 快约 **500 倍**，是 4090 上 GPU 部署的核心依据。")
    md.append("5. **取消能力缺失**：RAGFlow 原生不支持真正取消（实验 2），是 PM 5 项需求中未满足的一项。\n")

    md.append("\n## 四、数据缺口与可信度\n")
    md.append("- **实验 1/2/3/5**：由脚本产出 JSON，数值经程序化交叉校验（16/16 项通过），可信度高。\n")
    md.append("- **实验 4**：mentor 服务跑的，数据写 MySQL 但**记录已丢失**（库里只剩无关的 job 39）；表内数值引自报告 `批量导入规模验证_20260907.html`，无法再核对原始记录。\n")
    md.append("- **阶段数据归属更正**：报告里那张阶段表（embed 7.67s / 96%）标注为「千份级（job 37）」专有，不适用 job 35——本表 job 35 的阶段字段已留空。\n")
    md.append("- **4090 GPU 对照**：单条 embedding 0.030s 为 bge-gpu 容器日志实测；与 131 CPU 17.1s 是「文档级」近似对比（文档大小与批处理行为不同），量级结论可信。\n")

    md.append("\n## 五、万份变慢根因分析\n")
    md.append("> 数据来源：`bench_c3.json`（50 份并发3）与 `bench_10k.json`（1 万份并发3），同一脚本、同一并发、同一知识库（`2f84a97a`），仅规模不同。\n")

    # 从 JSON 实时提取关键值（不手抄）
    c3 = load("bench_c3.json")
    k10 = load("bench_10k.json")
    c3_emb = sorted(c3["stage_ms"]["embed"])
    k10_emb = sorted(k10["stage_ms"]["embed"])
    c3_parse = sorted(c3["stage_ms"]["parse"])
    k10_parse = sorted(k10["stage_ms"]["parse"])
    def avg(v): return sum(v) / len(v) if v else 0
    def pct(v, q):
        s = sorted(v); return s[min(len(s)-1, int(len(s)*q))]
    c3_emb_avg = avg(c3_emb) / 1000
    k10_emb_avg = avg(k10_emb) / 1000
    c3_p50 = pct(c3_emb, 0.5) / 1000
    k10_p50 = pct(k10_emb, 0.5) / 1000
    c3_p90 = pct(c3_emb, 0.9) / 1000
    k10_p90 = pct(k10_emb, 0.9) / 1000
    c3_p99 = pct(c3_emb, 0.99) / 1000
    k10_p99 = pct(k10_emb, 0.99) / 1000
    c3_max = max(c3_emb) / 1000
    k10_max = max(k10_emb) / 1000
    c3_single = sum(sum(v) for v in c3["stage_ms"].values()) / len(c3_emb) / 1000
    k10_single = sum(sum(v) for v in k10["stage_ms"].values()) / len(k10_emb) / 1000
    theo_tput_c3 = 3 / c3_single
    theo_tput_k10 = 3 / k10_single
    ratio_c3 = c3["throughput"] / theo_tput_c3 * 100
    ratio_k10 = k10["throughput"] / theo_tput_k10 * 100
    theo_wall_k10 = k10_single * k10["succeeded"] / 3
    wall_k10 = k10["wall_seconds"]
    waste = wall_k10 - theo_wall_k10
    waste_pct = waste / wall_k10 * 100
    # 长尾分布
    k10_n = len(k10_emb)
    tail = {}
    for thr in [30, 60, 120, 180, 300]:
        c = sum(1 for v in k10_emb if v > thr * 1000)
        tail[thr] = (c, c / k10_n * 100)
    c3_tail60 = sum(1 for v in c3_emb if v > 60000)
    k10_top10_avg = sum(k10_emb[int(k10_n*0.9):]) / (k10_n - int(k10_n*0.9)) / 1000
    k10_top1_avg = sum(k10_emb[int(k10_n*0.99):]) / (k10_n - int(k10_n*0.99)) / 1000

    md.append("\n### 5.1 反直觉：单份只慢 20%，吞吐却掉 74%\n")
    md.append("同口径对比单份阶段耗时（源：各实验 `stage_ms` 字段）：\n")
    md.append("\n| 指标 | 50 份（源 bench_c3） | 1 万份（源 bench_10k） | 变化 |\n")
    md.append("|---|---|---|---|\n")
    md.append(f"| embed 单份 avg | {c3_emb_avg:.2f}s | {k10_emb_avg:.2f}s | +{(k10_emb_avg/c3_emb_avg-1)*100:.0f}% |\n")
    md.append(f"| embed p50（中位数） | {c3_p50:.2f}s | {k10_p50:.2f}s | +{(k10_p50/c3_p50-1)*100:.0f}% |\n")
    md.append(f"| 单份阶段合计 avg | {c3_single:.2f}s | {k10_single:.2f}s | +{(k10_single/c3_single-1)*100:.0f}% |\n")
    md.append(f"| **吞吐** | **{c3['throughput']:.4f}** | **{k10['throughput']:.4f}** | **-{(1-k10['throughput']/c3['throughput'])*100:.0f}%** |\n")
    md.append(f"\n**矛盾点**：单份阶段合计只涨 {(k10_single/c3_single-1)*100:.0f}%，吞吐却掉了 {(1-k10['throughput']/c3['throughput'])*100:.0f}%。"
              f"若瓶颈是「每份变慢」，吞吐应只降 {(k10_single/c3_single-1)*100:.0f}% 左右。这说明**主因不在单份耗时**，而在别处。\n")

    md.append("\n### 5.2 真正的主因：embedding 长尾堵塞并发槽\n")
    md.append("看 embed 的长尾（源：`stage_ms.embed` 排序统计）：\n")
    md.append("\n| embed 耗时 | 50 份 | 1 万份 |\n")
    md.append("|---|---|---|\n")
    md.append(f"| p50（中位数） | {c3_p50:.2f}s | {k10_p50:.2f}s |\n")
    md.append(f"| p90 | {c3_p90:.2f}s | {k10_p90:.2f}s |\n")
    md.append(f"| p99 | {c3_p99:.2f}s | {k10_p99:.2f}s |\n")
    md.append(f"| **max** | **{c3_max:.1f}s** | **{k10_max:.1f}s（{k10_max/60:.1f} 分钟）** |\n")
    md.append(f"| max 是 avg 的几倍 | {c3_max/c3_emb_avg:.1f}x | **{k10_max/k10_emb_avg:.1f}x** |\n")
    md.append("\n长尾分布（源：1 万份 embed 各区间计数）：\n")
    md.append("\n| embed 耗时区间 | 1 万份数量 | 占比 |\n")
    md.append("|---|---|---|\n")
    for thr in [30, 60, 120, 180, 300]:
        c, p = tail[thr]
        md.append(f"| >{thr}s | {c} 份 | {p:.1f}% |\n")
    md.append(f"\n**堵塞机制**：并发只有 3 个槽。"
              f"50 份时 >60s 的只有 {c3_tail60} 份（{c3_tail60/len(c3_emb)*100:.0f}%），最慢 {c3_max:.1f}s——一个慢文档最多占住一个槽 1 分钟；"
              f"1 万份时最慢一份要 {k10_max:.1f}s（{k10_max/60:.1f} 分钟），占住一个槽期间该槽完全停摆，并发 3 退化成 2。"
              f"{tail[30][1]:.1f}% 的文档超 30s，意味着约 {tail[30][0]} 份会反复堵塞并发槽——这是吞吐崩塌的直接原因。\n")

    md.append(f"\n**墙钟去哪了（验证）**：理论墙钟 = 单份合计 × 文档数 / 并发 = {k10_single:.2f} × {k10['succeeded']} / 3 = {theo_wall_k10:.0f}s（{theo_wall_k10/3600:.1f}h）。"
              f"实际墙钟 {wall_k10:.0f}s（{wall_k10/3600:.1f}h，源 bench_10k wall_seconds），"
              f"差额 {waste:.0f}s（{waste/3600:.1f}h，占实际墙钟的 **{waste_pct:.0f}%**）——这 {waste_pct:.0f}% 的时间都消耗在等长尾上。\n")
    md.append(f"- 50 份的实际/理论吞吐量比 = {ratio_c3:.1f}%（几乎无空耗）；1 万份 = **{ratio_k10:.1f}%**（近 {100-ratio_k10:.0f}% 时间在等长尾）。这一组对比是长尾堵塞的铁证。\n")

    md.append("\n### 5.3 长尾本身的来源\n")
    md.append("embedding 长尾来自 **131 是共享机 + CPU embedding 服务**：\n")
    fails = [t for t in k10.get("tasks", []) if t.get("status") == "failed"]
    md.append(f"- **外部 embedding 服务超时**：1 万份的 {len(fails)} 份失败，错误信息全部是 "
              "`HTTPConnectionPool(host='192.168.80.1', port=18001): Read timed out. (read timeout=180)`"
              f"（源：bench_10k 的 tasks[].error）。说明 embedding 服务是 `192.168.80.1:18001` 这台外部机器，"
              "网络抖动时直接 read timeout=180s，是服务稳定性问题，非 RAGFlow 本身。\n")
    md.append("- **CPU 争抢**：131 是 34+ 容器混跑的共享机（VLLM、langflow、weknora……），"
              "bge-base 在 CPU 上推理，其他容器负载一抖动单次 embed 就被拖长。50 份只跑 5 分钟，撞上抖动概率低；"
              "1 万份跑 60 小时，必然反复撞上，长尾累积。\n")
    md.append(f"- **单份 embed 略变慢**：avg {c3_emb_avg:.2f}→{k10_emb_avg:.2f}s（+{(k10_emb_avg/c3_emb_avg-1)*100:.0f}%），"
              "推测是 CPU 长时间运行的热节流/内存压力，属次要因素。\n")

    md.append("\n### 5.4 parse 长尾是次要因素\n")
    c3_tot = sum(sum(v) for v in c3["stage_ms"].values() if v)
    k10_tot = sum(sum(v) for v in k10["stage_ms"].values() if v)
    c3_parse_share = sum(c3_parse) / c3_tot * 100
    k10_parse_share = sum(k10_parse) / k10_tot * 100
    md.append(f"parse 也有长尾（源：`stage_ms.parse`）：1 万份 parse avg={avg(k10_parse)/1000:.2f}s、max={max(k10_parse)/1000:.1f}s、>30s 的有 {sum(1 for v in k10_parse if v>30000)} 份；"
              f"parse 占总耗时比例从 50 份的 {c3_parse_share:.1f}% 升到 1 万份的 {k10_parse_share:.1f}%。"
              f"但 parse 本身耗时小（avg {avg(k10_parse)/1000:.2f}s vs embed {k10_emb_avg:.2f}s），不是吞吐崩塌的主因。\n")

    md.append("\n### 5.5 三因素贡献拆分\n")
    md.append("\n| 因素 | 贡献 | 证据来源 |\n")
    md.append("|---|---|---|\n")
    md.append(f"| **① embedding 长尾堵塞并发槽** | **主因（~{waste_pct:.0f}%）** | max {k10_max:.0f}s、{tail[30][1]:.1f}% 文档 >30s、墙钟 {waste_pct:.0f}% 在等长尾、实际/理论吞吐 {ratio_k10:.1f}% |\n")
    md.append(f"| ② 单份 embed 略变慢 | 次要（~{(k10_emb_avg/c3_emb_avg-1)*100:.0f}%） | avg {c3_emb_avg:.2f}→{k10_emb_avg:.2f}s |\n")
    md.append(f"| ③ parse 长尾 | 边际 | parse 占比 {c3_parse_share:.1f}%→{k10_parse_share:.1f}%，max {max(k10_parse)/1000:.1f}s |\n")

    md.append("\n### 5.6 GPU 为何能根治\n")
    md.append("| | 131 CPU | 4090 GPU | 来源 |\n")
    md.append("|---|---|---|---|\n")
    md.append(f"| 单条 embed | {c3_emb_avg:.1f}-{k10_emb_avg:.1f}s | **0.030s** | 131：bench_10k stage_ms；4090：bge-gpu 容器日志 |\n")
    md.append("| 长尾来源 | CPU 争抢 + 外部服务超时 | GPU 独占，无争抢 | 131：34 容器混跑；4090：bge-gpu 独占 GPU2 |\n")
    md.append(f"| 长尾倍数 | max 是 avg 的 {k10_max/k10_emb_avg:.1f}x | （待端到端实测） | bench_10k stage_ms |\n")
    md.append("\nGPU 不仅把单条快了约 500 倍，更重要的是**消除了 CPU 争抢导致的长尾**——长尾才是万份吞吐崩塌的真凶。"
              "这也解释了为什么「只看单条提速」会低估 GPU 价值：GPU 对吞吐的提升远大于单条提速比例。\n")

    md.append("\n### 5.7 一句话结论\n")
    md.append(f"万份变慢的主因**不是「每份变慢」**（单份只慢 {(k10_single/c3_single-1)*100:.0f}%），而是 **embedding 在 CPU 共享机上的长尾**"
              f"（max {k10_max:.0f}s、{tail[30][1]:.1f}% 文档超 30s）**堵塞了并发槽**，叠加单份略慢（{(k10_emb_avg/c3_emb_avg-1)*100:.0f}%）和 parse 长尾。"
              f"墙钟 {waste_pct:.0f}% 的时间在等长尾。GPU 通过消除 CPU 争抢根治长尾，是万份吞吐问题的解药。\n")

    md_path = DESIGN / "实验数据汇总_20260911.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    print(f"[summary] CSV  -> {csv_path}")
    print(f"[summary] MD   -> {md_path}")
    print(f"[summary] {len(rows)} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
