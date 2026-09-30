"""1 万份稳定性压测报告生成。

读单份 10k 压测结果 JSON（mentor_b_bench.py 产出），生成暗色主题 HTML 报告，
与既有报告同风格、带共享顶部导航栏。

核心问题：
1. 规模从 100 份 → 10000 份，吞吐是否守住？（对比 c3 baseline 0.180 份/s）
2. 1 万份长跑下稳定性如何？（失败率、失败原因）
3. embedding 长尾在长跑下是否恶化？

Usage:
    uv run --project code python code/ingest/bench_10k_report.py \
      --result test/results/131_测试/bench_10k.json \
      --baseline test/results/131_测试/bench_c3.json \
      --out doc/design/131_测试/万份稳定性压测_YYYYMMDD.html
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 与 bench_report.py 一致的暗色主题
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
  .stat.acc b { color:var(--accent); }
  .bar-wrap { background:#0d1016; border-radius:4px; height:22px; position:relative;
              overflow:hidden; margin:6px 0; }
  .bar { height:100%; border-radius:4px; display:flex; align-items:center;
         justify-content:flex-end; padding-right:8px; font-size:11px; color:#fff;
         font-variant-numeric:tabular-nums; }
  .bar.parse { background:#4c8dff; } .bar.chunk { background:#4c8dff; }
  .bar.embed { background:#35c56a; } .bar.index { background:#f5a623; }
  .caveat { background:#2a2016; border-left:3px solid var(--warn); padding:12px 16px;
            border-radius:0 6px 6px 0; font-size:13px; color:#f0d9b5; margin:14px 0; }
  .note { background:#0d1016; border-radius:6px; padding:10px 14px; font-size:12.5px;
          color:#93a4b8; margin:10px 0; }
  .toc { background:var(--panel); border:1px solid var(--line); border-radius:8px;
         padding:14px 20px; margin:20px 0; }
  .toc a { color:var(--accent); text-decoration:none; font-size:13px; }
  .toc a:hover { text-decoration:underline; }
  .footer { color:var(--muted); font-size:12px; margin-top:40px;
            padding-top:16px; border-top:1px solid var(--line); }
"""


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def stage_stats(r: dict) -> dict:
    """从 stage_ms {stage: [ms...]} 汇总每阶段统计。"""
    out = {}
    total = 0
    for stage, vals in r.get("stage_ms", {}).items():
        if vals:
            s = sum(vals)
            out[stage] = {
                "sum": s, "avg": s // len(vals),
                "p50": int(statistics.median(vals)),
                "p90": vals[min(len(vals) - 1, int(len(vals) * 0.9))],
                "p99": vals[min(len(vals) - 1, int(len(vals) * 0.99))],
                "max": max(vals), "n": len(vals),
            }
            total += s
    for st in out:
        out[st]["share"] = out[st]["sum"] / total * 100 if total else 0
    return out


def fmt_ms(ms: int | None) -> str:
    if ms is None:
        return "—"
    return f"{ms/1000:.2f}s" if ms >= 1000 else f"{ms}ms"


def fmt_dur(sec: float) -> str:
    sec = float(sec or 0)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec - h * 3600 - m * 60
    if h:
        return f"{h}h{m:02d}m{int(s):02d}s"
    if m:
        return f"{m}m{int(s):02d}s"
    return f"{int(s)}s"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True, help="10k 压测结果 JSON")
    ap.add_argument("--baseline", default="", help="100 份 c3 baseline JSON（可选对比）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    r = load(args.result)
    base = load(args.baseline) if args.baseline else None
    today = date.today().isoformat()
    out_path = Path(args.out) if args.out else (
        ROOT / "doc" / "design" / f"万份稳定性压测_{today}.html"
    )

    docs = r.get("docs", 0)
    succ = r.get("succeeded", 0)
    fail = r.get("failed", 0)
    skip = r.get("skipped", 0)
    wall = r.get("wall_seconds", 0)
    tput = r.get("throughput", 0)
    conc = r.get("concurrency", 3)
    fail_rate = fail / docs * 100 if docs else 0
    st = stage_stats(r)

    # 规模退化判断
    base_tput = base.get("throughput", 0) if base else 0
    degrade = (1 - tput / base_tput) * 100 if base_tput else 0

    html = []
    html.append("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    html.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    html.append(f"<title>万份稳定性压测 · {today}</title><style>{CSS}</style></head><body><div class='wrap'>")

    html.append("<h1>mentor 方案 B · 1 万份稳定性压测报告</h1>")
    env = "131 服务器（RAGFlow v0.26.1，CPU bge-base，共享机）"
    html.append(
        f"<p class='sub'>GCN 采购文件活化项目 · 规模验证的最后一档：100 份 → 1 万份<br>"
        f"执行人：小zhu · 日期：{today} · 环境：{env} · "
        f"数据：{docs} 份纯真 .docx · 并发 {conc}</p>"
    )

    html.append("<div class='toc'><b>目录</b><br>"
                "<a href='#tldr'>一、结论</a> · "
                "<a href='#kpi'>二、总览</a> · "
                "<a href='#scale'>三、规模退化</a> · "
                "<a href='#stage'>四、每阶段耗时</a> · "
                "<a href='#embed'>五、embedding 长尾</a> · "
                "<a href='#stab'>六、稳定性与失败</a></div>")

    # 一、TL;DR
    verdict_tag = "ok" if fail_rate < 1 else ("warn" if fail_rate < 5 else "err")
    tldr_lines = []
    if base_tput:
        if degrade > 15:
            tldr_lines.append(
                f"规模从 100 份 → 1 万份，吞吐 <b>{base_tput:.3f} → {tput:.3f} 份/s</b>"
                f"（降 {degrade:.0f}%），<b>长跑下吞吐明显退化</b>。"
            )
        else:
            tldr_lines.append(
                f"规模从 100 份 → 1 万份，吞吐 <b>{base_tput:.3f} → {tput:.3f} 份/s</b>"
                f"（降 {degrade:.0f}%），<b>吞吐基本守住</b>。"
            )
    else:
        tldr_lines.append(f"1 万份吞吐 <b>{tput:.3f} 份/s</b>（每份 {wall/max(succ,1):.1f}s）。")
    tldr_lines.append(
        f"1 万份长跑（{fmt_dur(wall)}）失败 {fail} 份，失败率 "
        f"<span class='tag {verdict_tag}'>{fail_rate:.2f}%</span>。"
    )
    embed_st = st.get("embed", {})
    if embed_st:
        tldr_lines.append(
            f"embedding 仍是绝对瓶颈（占比 {embed_st['share']:.0f}%），"
            f"长跑下 max={fmt_ms(embed_st['max'])}、p99={fmt_ms(embed_st['p99'])}，"
            f"长尾不因规模放大而消失。"
        )
    html.append("<h2 id='tldr'>一、结论</h2>")
    html.append("<div class='panel tldr'><p>" + "<br>".join(tldr_lines) + "</p></div>")

    # 二、KPI 总览
    html.append("<h2 id='kpi'>二、总览</h2>")
    html.append('<div class="grid4">')
    html.append(f'<div class="stat ok"><b>{succ}</b><small>成功</small></div>')
    html.append(f'<div class="stat {"err" if fail else "ok"}"><b>{fail}</b><small>失败</small></div>')
    html.append(f'<div class="stat acc"><b>{tput:.3f}</b><small>吞吐(份/s)</small></div>')
    html.append(f'<div class="stat"><b>{fmt_dur(wall)}</b><small>墙钟</small></div>')
    html.append("</div>")

    html.append('<div class="panel"><table><tbody>')
    rows = [
        ("文档总数", f"{docs}"),
        ("并发数", f"{conc}"),
        ("成功 / 失败 / 跳过", f"{succ} / {fail} / {skip}"),
        ("失败率", f"{fail_rate:.2f}%"),
        ("墙钟", fmt_dur(wall)),
        ("吞吐", f"{tput:.3f} 份/s"),
        ("每份均时", f"{wall/max(succ,1):.1f}s"),
        ("peak in flight", f"{r.get('peak_in_flight',0)}"),
    ]
    if base:
        rows.append(("100 份 baseline 吞吐", f"{base_tput:.3f} 份/s"))
        rows.append(("规模退化", f"-{degrade:.0f}%" if degrade > 0 else "+{:.0f}%".format(-degrade)))
    for name, val in rows:
        html.append(f"<tr><td>{name}</td><td class='num'>{val}</td></tr>")
    html.append("</tbody></table></div>")

    # 三、规模退化
    html.append("<h2 id='scale'>三、规模退化分析</h2>")
    if base:
        html.append(
            '<div class="panel"><table><thead><tr><th>规模</th>'
            '<th class="num">文档数</th><th class="num">吞吐(份/s)</th>'
            '<th class="num">每份(s)</th><th class="num">墙钟</th>'
            '<th class="num">失败</th></tr></thead><tbody>'
        )
        for label, rr in [("100 份 baseline", base), ("1 万份", r)]:
            html.append(
                f"<tr><td>{label}</td>"
                f"<td class='num'>{rr.get('docs',0)}</td>"
                f"<td class='num'>{rr.get('throughput',0):.3f}</td>"
                f"<td class='num'>{rr.get('wall_seconds',0)/max(rr.get('succeeded',1),1):.1f}</td>"
                f"<td class='num'>{fmt_dur(rr.get('wall_seconds',0))}</td>"
                f"<td class='num'>{rr.get('failed',0)}</td></tr>"
            )
        html.append("</tbody></table>")
        if degrade > 15:
            html.append(
                '<div class="caveat">吞吐退化超 15%。根因是 1 万份长跑下 131 共享机 '
                'CPU 争抢持续、embedding 服务（bge-base CPU）负载累积，'
                '单份 embed 耗时被拉长。<b>这正是上 GPU 的核心理由</b>：'
                'GPU embedding 既能提单份速度，也能在高并发长跑下稳住吞吐。</div>'
            )
        else:
            html.append(
                '<div class="note">吞吐在 1 万份规模下基本守住，说明编排层 '
                '（mentor 方案 B InMemory）在长跑下稳定，瓶颈仍在 embedding。</div>'
            )
        html.append("</div>")
    else:
        html.append('<div class="note">未提供 100 份 baseline，跳过规模退化对比。</div>')

    # 四、每阶段耗时
    html.append("<h2 id='stage'>四、每阶段耗时</h2>")
    if st:
        html.append(
            '<div class="panel"><table><thead><tr><th>阶段</th>'
            '<th class="num">n</th><th class="num">avg</th><th class="num">p50</th>'
            '<th class="num">p90</th><th class="num">p99</th><th class="num">max</th>'
            '<th class="num">占比</th></tr></thead><tbody>'
        )
        for stage in ("parse", "chunk", "embed", "index"):
            d = st.get(stage)
            if not d:
                continue
            html.append(
                f"<tr><td>{stage}</td><td class='num'>{d['n']}</td>"
                f"<td class='num'>{fmt_ms(d['avg'])}</td>"
                f"<td class='num'>{fmt_ms(d['p50'])}</td>"
                f"<td class='num'>{fmt_ms(d['p90'])}</td>"
                f"<td class='num'>{fmt_ms(d['p99'])}</td>"
                f"<td class='num'>{fmt_ms(d['max'])}</td>"
                f"<td class='num'>{d['share']:.1f}%</td></tr>"
            )
        html.append("</tbody></table>")
        # 占比条
        html.append("<h3>耗时占比</h3>")
        for stage in ("parse", "chunk", "embed", "index"):
            d = st.get(stage)
            if not d:
                continue
            html.append(
                f'<div class="bar-wrap"><div class="bar {stage}" '
                f'style="width:{d["share"]:.1f}%">{stage} {d["share"]:.1f}%</div></div>'
            )
        html.append("</div>")
    else:
        html.append('<div class="note">无阶段耗时数据。</div>')

    # 五、embedding 长尾
    html.append("<h2 id='embed'>五、embedding 长尾分析（1 万份长跑）</h2>")
    embed_st = st.get("embed")
    if embed_st:
        ratio = embed_st["max"] / embed_st["avg"] if embed_st["avg"] else 0
        html.append(
            '<div class="panel"><table><thead><tr><th>阶段</th>'
            '<th class="num">avg</th><th class="num">p50</th><th class="num">p90</th>'
            '<th class="num">p99</th><th class="num">max</th>'
            '<th class="num">max/avg</th></tr></thead><tbody>'
        )
        html.append(
            f"<tr><td>embed</td><td class='num'>{fmt_ms(embed_st['avg'])}</td>"
            f"<td class='num'>{fmt_ms(embed_st['p50'])}</td>"
            f"<td class='num'>{fmt_ms(embed_st['p90'])}</td>"
            f"<td class='num'>{fmt_ms(embed_st['p99'])}</td>"
            f"<td class='num'>{fmt_ms(embed_st['max'])}</td>"
            f"<td class='num'>{ratio:.1f}x</td></tr>"
        )
        html.append("</tbody></table>")
        html.append(
            '<div class="caveat">1 万份长跑下 embedding 长尾依然显著：'
            f'avg {fmt_ms(embed_st["avg"])} 但 max {fmt_ms(embed_st["max"])}'
            f'（{ratio:.1f}x）。长尾来自 131 共享机 CPU 争抢 + bge-base 在 CPU 推理，'
            '<b>规模放大不消除长尾，只会让长尾累计更多</b>。'
            '提速正解仍是 GPU embedding。</div>'
            '<p class="note">131 是多容器混跑的共享机，embedding 服务（bge-base）'
            '在 CPU 上推理，无 GPU。长跑下其他容器负载波动直接传导到 embedding 耗时。</p></div>'
        )
    else:
        html.append('<div class="note">无 embedding 阶段数据。</div>')

    # 六、稳定性与失败
    html.append("<h2 id='stab'>六、稳定性与失败分析</h2>")
    html.append('<div class="panel">')
    html.append(
        f"<p><b>失败率</b>：{fail_rate:.2f}%（{fail}/{docs}）"
        f'<span class="tag {verdict_tag}">'
        f'{"达标(<1%)" if fail_rate < 1 else "警告(<5%)" if fail_rate < 5 else "超标"}</span></p>'
    )
    failures = [t for t in r.get("tasks", []) if t.get("status") == "failed"]
    if failures:
        html.append(f"<h3>失败明细（共 {len(failures)} 份，仅列前 30）</h3>")
        html.append(
            '<table><thead><tr><th>文档</th><th>错误（截断 120 字）</th></tr></thead><tbody>'
        )
        for t in failures[:30]:
            err = str(t.get("error", ""))[:120]
            html.append(f"<tr><td>{t.get('name','')}</td><td>{err}</td></tr>")
        html.append("</tbody></table>")
    else:
        html.append("<p>无失败任务。</p>")
    # 失败原因聚类
    if failures:
        from collections import Counter
        causes = Counter()
        for t in failures:
            err = str(t.get("error", ""))
            # 取第一行/关键短语聚类
            key = err.split(":")[0][:40] if err else "unknown"
            causes[key] += 1
        html.append("<h3>失败原因聚类</h3><table><thead><tr><th>原因</th>"
                    "<th class='num'>次数</th></tr></thead><tbody>")
        for cause, n in causes.most_common():
            html.append(f"<tr><td>{cause}</td><td class='num'>{n}</td></tr>")
        html.append("</tbody></table>")
    html.append("</div>")

    # footer
    html.append(
        f"<div class='footer'>生成于 {today} · mentor 方案 B InMemory · "
        f"数据 {docs} 份 · 并发 {conc} · 环境 {env}<br>"
        f"报告脚本 code/ingest/bench_10k_report.py</div>")

    html.append("</div></body></html>")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(html), encoding="utf-8")
    print(f"[10k-report] saved -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
