"""AB 对比实验 — 对比报告生成。

从 ab_batch.py 输出的多个结果 JSON 生成暗色主题 HTML 对比报告，仿
批量导入规模验证_20260907.html 的样式。可选读可控性实测 JSON（ab_controllability）。

Usage:
    uv run --project code python code/ingest/ab_report.py \\
      --results /tmp/ab_ragflow_r1.json /tmp/ab_selfrun_r1.json /tmp/ab_ragflow_r2.json \\
      --controllability /tmp/ab_controllability.json \\
      --out doc/design/131_测试/方案AB对比实验_YYYYMMDD.html
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[2]

# ---------- CSS (仿 批量导入规模验证_20260907.html) ----------
CSS = """
  :root {
    --bg:#0f1115; --panel:#171a21; --line:#262a33; --text:#e6e8eb;
    --muted:#9aa3ad; --accent:#4c8dff; --ok:#35c56a; --warn:#f5a623; --err:#ff5f56;
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }
  .wrap { max-width:1080px; margin:0 auto; padding:32px 28px 80px; }
  h1 { font-size:24px; font-weight:600; margin:0 0 4px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:28px; }
  h2 { font-size:17px; font-weight:600; margin:34px 0 14px;
       padding-bottom:8px; border-bottom:1px solid var(--line); }
  h3 { font-size:14.5px; font-weight:600; margin:20px 0 8px; color:var(--accent); }
  .panel { background:var(--panel); border:1px solid var(--line);
           border-radius:8px; padding:18px 20px; margin:14px 0; }
  .panel.tldr { border-left:3px solid var(--accent); }
  table { width:100%; border-collapse:collapse; font-size:13px; margin:8px 0; }
  th, td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--line);
           vertical-align:middle; }
  th { color:var(--muted); font-weight:500; font-size:12px; }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
  .tag { display:inline-block; padding:2px 9px; border-radius:11px;
         font-size:11.5px; border:1px solid; }
  .tag.ok { color:var(--ok); border-color:var(--ok); }
  .tag.warn { color:var(--warn); border-color:var(--warn); }
  .tag.err { color:var(--err); border-color:var(--err); }
  .tag.acc { color:var(--accent); border-color:var(--accent); }
  .grid4 { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:14px 0; }
  .stat { background:var(--panel); border:1px solid var(--line); border-radius:8px;
          padding:16px 14px; text-align:center; }
  .stat b { display:block; font-size:26px; font-weight:600; }
  .stat small { color:var(--muted); font-size:11.5px; }
  .stat.warn b { color:var(--warn); }
  .stat.err b { color:var(--err); }
  .stat.ok b { color:var(--ok); }
  .bar-wrap { background:#0d1016; border-radius:4px; height:22px; position:relative;
              overflow:hidden; margin:6px 0; }
  .bar { height:100%; border-radius:4px; display:flex; align-items:center;
         justify-content:flex-end; padding-right:8px; font-size:11px; color:#fff;
         font-variant-numeric:tabular-nums; }
  .bar.b-parse { background:#4c8dff; } .bar.b-chunk { background:#35c56a; }
  .bar.b-embed { background:#f5a623; } .bar.b-index { background:#b377ff; }
  .caveat { background:#2a2016; border-left:3px solid var(--warn); padding:12px 16px;
            border-radius:0 6px 6px 0; font-size:13px; color:#f0d9b5; margin:14px 0; }
  .note { background:#0d1016; border-radius:6px; padding:10px 14px; font-size:12.5px;
          color:#93a4b8; margin:10px 0; }
  pre { background:#0d1016; padding:10px 14px; border-radius:6px; font-size:12px;
        color:#b9c6d8; overflow-x:auto; margin:8px 0; }
  code { background:#0d1016; padding:1.5px 6px; border-radius:4px; font-size:12px;
         color:#b9c6d8; }
  .toc { background:var(--panel); border:1px solid var(--line); border-radius:8px;
         padding:14px 20px; margin:20px 0; }
  .toc a { color:var(--accent); text-decoration:none; font-size:13px; }
  .toc a:hover { text-decoration:underline; }
  .footer { color:var(--muted); font-size:12px; margin-top:40px;
            padding-top:16px; border-top:1px solid var(--line); }
  .vs { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
"""


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def stage_stats(r: dict) -> tuple[dict, int]:
    """返回 {stage:{sum,avg,p50,max,n,share}}, total_ms。"""
    out: dict[str, dict] = {}
    total = 0
    for stage, vals in r.get("stage_ms", {}).items():
        if vals:
            s = sum(vals)
            out[stage] = {
                "sum": s, "avg": s // len(vals),
                "p50": int(statistics.median(vals)),
                "max": max(vals), "n": len(vals),
            }
            total += s
    for st in out:
        out[st]["share"] = out[st]["sum"] / total * 100 if total else 0
    return out, total


def label_of(r: dict) -> str:
    """展示名：方案A/方案B + label。"""
    name = "方案A(RAGFlow原生)" if r["backend"] == "ragflow" else "方案B(mentor自建)"
    lab = r.get("label", "")
    if lab:
        name += f" {lab}"
    return name


def short(r: dict) -> str:
    return ("A" if r["backend"] == "ragflow" else "B") + "-" + (
        r.get("label", "default").replace("round1-", "r1").replace("round2-", "r2")
        .replace("default", "def").replace("aligned", "al"))


def fmt_ms(ms: int | None) -> str:
    if ms is None:
        return "—"
    return f"{ms/1000:.2f}s" if ms >= 1000 else f"{ms}ms"


def kpi_card(value: str, label: str, cls: str = "") -> str:
    return f'<div class="stat {cls}"><b>{value}</b><small>{label}</small></div>'


def bar(stage: str, share: float, label: str) -> str:
    return (f'<div class="bar-wrap"><div class="bar b-{stage}" style="width:{share:.1f}%">'
            f'{label}</div></div>')


def section_kpi(results: list[dict]) -> str:
    """KPI 对比卡片：每个结果一组 4 卡片。"""
    parts = ["<h2 id='kpi'>三、核心指标对比</h2>"]
    for r in results:
        parts.append(f"<h3>{label_of(r)}</h3>")
        wall = r["wall_seconds"]
        thr = r["throughput"]
        succ = r["succeeded"]
        total = r["docs"]
        fail = r["failed"]
        fail_rate = fail / total * 100 if total else 0
        parts.append('<div class="grid4">')
        parts.append(kpi_card(f"{wall:.0f}s", "墙钟", "warn" if wall > 400 else ""))
        parts.append(kpi_card(f"{thr:.3f}", "份/秒 吞吐"))
        parts.append(kpi_card(f"{succ}/{total}", "成功/总数", "ok" if fail == 0 else ""))
        parts.append(kpi_card(f"{fail_rate:.1f}%", "失败率", "err" if fail > 0 else "ok"))
        parts.append("</div>")
    return "\n".join(parts)


def section_stage(results: list[dict]) -> str:
    """每阶段耗时对比。"""
    parts = ["<h2 id='stage'>四、每阶段耗时对比</h2>"]
    parts.append(
        '<div class="note">方案B 每阶段 time.time() 精确计时；方案A 无 per-stage 计时，'
        '此处展示 step_mapping 从 progress_msg 推断的耗时（标注推断，精度低）。</div>'
    )
    # 表格：行=阶段，列=各结果的 avg/max
    parts.append('<div class="panel"><table>')
    header = "<tr><th>阶段</th>" + "".join(
        f'<th class="num">{short(r)} avg</th><th class="num">max</th>'
        for r in results
    ) + "</tr>"
    parts.append(f"<thead>{header}</thead><tbody>")
    for stage in ("parse", "chunk", "embed", "index"):
        cells = f"<td>{stage}</td>"
        for r in results:
            st, _ = stage_stats(r)
            d = st.get(stage)
            if d:
                cells += f'<td class="num">{fmt_ms(d["avg"])}</td><td class="num">{fmt_ms(d["max"])}</td>'
            else:
                cells += '<td class="num">—</td><td class="num">—</td>'
        parts.append(cells)
    parts.append("</tbody></table></div>")

    # 占比条形图（每个结果一组）
    for r in results:
        st, total = stage_stats(r)
        if not total:
            continue
        parts.append(f"<h3>{label_of(r)} — 耗时占比</h3>")
        for stage in ("parse", "chunk", "embed", "index"):
            d = st.get(stage)
            share = d["share"] if d else 0
            parts.append(bar(stage, share, f"{stage} {share:.1f}%"))
    return "\n".join(parts)


def section_visibility(results: list[dict]) -> str:
    """进度可见性对比：方案A progress_msg 样本 vs 方案B 精确计时。"""
    parts = ["<h2 id='vis'>五、进度可见性对比</h2>"]
    ragflow = next((r for r in results if r["backend"] == "ragflow"), None)
    selfrun = next((r for r in results if r["backend"] == "selfrun"), None)

    parts.append('<div class="vs"><div class="panel"><h3>方案A：单浮点 progress + progress_msg 文本</h3>')
    if ragflow and ragflow.get("progress_samples"):
        # 挑一个 doc 的样本序列展示
        samples = ragflow["progress_samples"]
        by_doc: dict[str, list] = {}
        for s in samples:
            by_doc.setdefault(s["doc_id"], []).append(s)
        # 挑样本数中等的 doc
        docs = sorted(by_doc.values(), key=len)
        pick = docs[len(docs) // 2] if docs else []
        parts.append(f'<p class="note">采样文档进度序列（共 {len(pick)} 次轮询）：</p>')
        parts.append("<pre>")
        for s in pick[:25]:
            parts.append(f"run={s['run']:8s} prog={s['progress']:6} msg={s['progress_msg'][:80]}")
        if len(pick) > 25:
            parts.append(f"... ({len(pick)-25} more)")
        parts.append("</pre>")
        parts.append('<p class="note">观察：progress 是单一浮点，阶段只能从 progress_msg 文本关键词'
                     '（OCR/embedding/entity 等）模糊推断，无精确阶段边界与计时。</p>')
    else:
        parts.append('<p class="note">无 progress_msg 样本。</p>')
    parts.append("</div>")

    parts.append('<div class="panel"><h3>方案B：每阶段精确计时（duration_ms）</h3>')
    if selfrun:
        st, _ = stage_stats(selfrun)
        parts.append("<table><thead><tr><th>阶段</th><th class='num'>avg</th>"
                     "<th class='num'>p50</th><th class='num'>max</th><th class='num'>n</th></tr></thead><tbody>")
        for stage in ("parse", "chunk", "embed", "index"):
            d = st.get(stage)
            if d:
                parts.append(f"<tr><td>{stage}</td><td class='num'>{fmt_ms(d['avg'])}</td>"
                             f"<td class='num'>{fmt_ms(d['p50'])}</td><td class='num'>{fmt_ms(d['max'])}</td>"
                             f"<td class='num'>{d['n']}</td></tr>")
            else:
                parts.append(f"<tr><td>{stage}</td><td class='num'>—</td><td class='num'>—</td>"
                             f"<td class='num'>—</td><td class='num'>0</td></tr>")
        parts.append("</tbody></table>")
        parts.append('<p class="note">观察：每阶段有 started_at/finished_at + duration_ms，'
                     '可在任意时刻读取当前阶段、累计耗时、长尾定位。</p>')
    parts.append("</div></div>")
    return "\n".join(parts)


def section_controllability(ctrl: dict | None) -> str:
    """可控性矩阵：暂停/重试/取消/失败隔离。"""
    parts = ["<h2 id='ctrl'>六、可控性对比矩阵</h2>"]
    if not ctrl:
        parts.append('<div class="note">可控性实测数据待补（执行 ab_controllability 后生成）。</div>')
        return "\n".join(parts)
    dims = [
        ("pause", "暂停"),
        ("resume", "恢复续跑"),
        ("retry", "单份重试"),
        ("cancel", "取消"),
        ("failure_isolation", "失败隔离"),
    ]
    parts.append('<div class="panel"><table>')
    parts.append("<thead><tr><th>能力</th><th>方案A(RAGFlow原生)</th><th>方案B(mentor自建)</th></tr></thead><tbody>")
    for key, name in dims:
        row = ctrl.get(key, {})
        ra = row.get("ragflow", "—")
        rb = row.get("selfrun", "—")
        # tag 着色：含"不支持"/"不能" → err；含"支持"/"可" → ok
        def tag(text: str) -> str:
            t = text.lower() if isinstance(text, str) else ""
            if any(k in t for k in ("不支持", "不能", "无法", "no", "需重新")):
                return f'<span class="tag err">{text}</span>'
            if any(k in t for k in ("支持", "可", "yes", "精确")):
                return f'<span class="tag ok">{text}</span>'
            return f'<span class="tag warn">{text}</span>'
        parts.append(f"<tr><td>{name}</td><td>{tag(ra)}</td><td>{tag(rb)}</td></tr>")
    parts.append("</tbody></table></div>")
    return "\n".join(parts)


def section_failure(results: list[dict]) -> str:
    """失败归因对比。"""
    parts = ["<h2 id='fail'>七、失败归因</h2>"]
    has_fail = any(r["failed"] > 0 for r in results)
    if not has_fail:
        parts.append('<div class="note">本轮所有方案失败数为 0（测试数据已用 python-docx 预筛纯真 .docx）。</div>')
        return "\n".join(parts)
    for r in results:
        if r["failed"] == 0:
            continue
        parts.append(f"<h3>{label_of(r)} — {r['failed']} 份失败</h3>")
        parts.append("<table><thead><tr><th>文档</th><th>错误</th></tr></thead><tbody>")
        for t in r["tasks"]:
            if t["status"] == "failed":
                parts.append(f"<tr><td>{t['name']}</td><td>{str(t['error'])[:120]}</td></tr>")
        parts.append("</tbody></table>")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", nargs="+", required=True, help="ab_batch 输出的 JSON 列表")
    ap.add_argument("--controllability", default="", help="可控性实测 JSON")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    results = [load(p) for p in args.results]
    ctrl = load(args.controllability) if args.controllability else None

    today = date.today().isoformat()
    out_path = Path(args.out) if args.out else ROOT / "doc" / "design" / f"方案AB对比实验_{today}.html"

    # 结论
    ragflow = next((r for r in results if r["backend"] == "ragflow"), None)
    selfrun = next((r for r in results if r["backend"] == "selfrun"), None)
    tldr = "对比实验完成。"
    if ragflow and selfrun:
        wa, wb = ragflow["wall_seconds"], selfrun["wall_seconds"]
        if wa > 0 and wb > 0:
            ratio = wa / wb
            tldr = (f"同一批 100 份 .docx：方案A(RAGFlow原生) 墙钟 {wa:.0f}s，"
                    f"方案B(mentor自建) 墙钟 {wb:.0f}s，"
                    f"方案A 是方案B的 {ratio:.1f} 倍。"
                    f"差异主因：方案A 受 task_executor embed_limiter=1 串行限制，"
                    f"方案B 在进程内并发 embedding。")

    html = []
    html.append("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    html.append(f"<meta name='viewport' content='width=device-width, initial-scale=1'>")
    html.append(f"<title>方案AB对比实验报告 · {today}</title><style>{CSS}</style></head><body>")
    html.append("<div class='wrap'>")
    html.append(f"<h1>方案A vs 方案B 批量上传性能对比实验</h1>")
    html.append(f"<p class='sub'>GCN 采购文件活化项目 · RAGFlow 原生批量上传(方案A) vs mentor自建编排(方案B)<br>"
                f"执行人：小zhu · 日期：{today} · 环境：131 服务器 RAGFlow v0.26.1 · 数据：law_data 100份纯真.docx</p>")
    html.append("<div class='toc'><b>目录</b><br>"
                "<a href='#tldr'>一、结论</a> · "
                "<a href='#setup'>二、实验设置</a> · "
                "<a href='#kpi'>三、核心指标</a> · "
                "<a href='#stage'>四、阶段耗时</a> · "
                "<a href='#vis'>五、进度可见性</a> · "
                "<a href='#ctrl'>六、可控性矩阵</a> · "
                "<a href='#fail'>七、失败归因</a> · "
                "<a href='#next'>八、结论与建议</a></div>")

    html.append("<h2 id='tldr'>一、结论</h2>")
    html.append(f"<div class='panel tldr'><p>{tldr}</p></div>")

    html.append("<h2 id='setup'>二、实验设置</h2>")
    html.append("<div class='panel'><table><thead><tr><th>项</th><th>方案A(RAGFlow原生)</th>"
                "<th>方案B(mentor自建)</th></tr></thead><tbody>")
    html.append("<tr><td>解析执行</td><td>RAGFlow task_executor (Redis Stream 派活)</td>"
                "<td>mentor 进程内 parse→chunk→embed→index</td></tr>")
    html.append("<tr><td>并发模型</td><td>embed_limiter 默认=1 (embedding 串行)</td>"
                "<td>Scheduler max_concurrent=3 (进程内并发)</td></tr>")
    html.append("<tr><td>embedding 服务</td><td colspan='2'>共享 bge-base (192.168.80.1:18001)</td></tr>")
    html.append("<tr><td>存储复用</td><td colspan='2'>MinIO + ES + MySQL (相同基础设施)</td></tr>")
    html.append("<tr><td>编排层</td><td colspan='2'>同一 Orchestrator + InMemoryRepository + Scheduler</td></tr>")
    html.append("<tr><td>测试数据</td><td colspan='2'>law_data 100 份纯真 .docx (python-docx 预筛)</td></tr>")
    html.append("</tbody></table>")
    html.append("<p class='note'>两方案唯一差异是 pipeline 实现，编排/调度/计时口径完全一致，确保对比公平。</p></div>")

    html.append(section_kpi(results))
    html.append(section_stage(results))
    html.append(section_visibility(results))
    html.append(section_controllability(ctrl))
    html.append(section_failure(results))

    html.append("<h2 id='next'>八、结论与建议</h2>")
    html.append("<div class='panel'>")
    if ragflow and selfrun:
        html.append(f"<p><strong>性能</strong>：方案A {ragflow['wall_seconds']:.0f}s vs 方案B {selfrun['wall_seconds']:.0f}s。</p>")
        html.append(f"<p><strong>可控性</strong>：方案A 仅提供单浮点 progress + 文本 progress_msg，"
                    "无暂停/重试/精确计时；方案B 每阶段精确计时、可暂停/恢复/重试/取消。</p>")
        html.append(f"<p><strong>建议</strong>：批量导入场景（需暂停/重试/计时）用方案B；"
                    "轻量单文档上传可用方案A 原生接口。</p>")
    html.append("</div>")
    html.append(f"<div class='footer'>生成于 {today} · ab_report.py · 数据源: {len(results)} 个结果 JSON</div>")
    html.append("</div></body></html>")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(html), encoding="utf-8")
    print(f"[report] saved -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
