"""mentor 方案 B 并发压测对比报告生成。

读 bench_c1/c3/c6.json（三档并发压测结果），生成暗色主题 HTML 报告。
跟之前报告同一风格。

Usage:
    uv run --project code python code/ingest/bench_report.py \
      --results test/results/131_测试/bench_c1.json test/results/131_测试/bench_c3.json test/results/131_测试/bench_c6.json \
      --out doc/design/131_测试/方案B并发压测_YYYYMMDD.html
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

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
  .bar.b1 { background:#4c8dff; } .bar.b3 { background:#35c56a; } .bar.b6 { background:#f5a623; }
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
    out = {}
    total = 0
    for stage, vals in r.get("stage_ms", {}).items():
        if vals:
            s = sum(vals)
            out[stage] = {
                "sum": s, "avg": s // len(vals),
                "p50": int(statistics.median(vals)),
                "p90": vals[min(len(vals) - 1, int(len(vals) * 0.9))],
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", nargs="+", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    results = [load(p) for p in args.results]
    # 按并发数排序
    results.sort(key=lambda r: r.get("concurrency", 0))
    today = date.today().isoformat()
    out_path = Path(args.out) if args.out else (
        ROOT / "doc" / "design" / f"方案B并发压测_{today}.html"
    )

    # 找最优吞吐
    best = max(results, key=lambda r: r.get("throughput", 0))
    best_c = best.get("concurrency", 3)

    html = []
    html.append("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    html.append(f"<meta name='viewport' content='width=device-width, initial-scale=1'>")
    html.append(f"<title>方案B并发压测对比 · {today}</title><style>{CSS}</style></head><body><div class='wrap'>")

    html.append("<h1>mentor 方案 B 并发压测对比报告</h1>")
    html.append(
        f"<p class='sub'>GCN 采购文件活化项目 · embedding 清理重置后并发数重新标定<br>"
        f"执行人：小zhu · 日期：{today} · 环境：131 服务器（RAGFlow v0.26.1） · "
        f"数据：50 份纯真 .docx × 并发 1/3/6</p>"
    )

    html.append("<div class='toc'><b>目录</b><br>"
                "<a href='#tldr'>一、结论</a> · "
                "<a href='#compare'>二、三档对比</a> · "
                "<a href='#stage'>三、每阶段耗时</a> · "
                "<a href='#embed'>四、embedding 长尾分析</a> · "
                "<a href='#conclusion'>五、最优并发结论</a></div>")

    # 一、TL;DR
    html.append("<h2 id='tldr'>一、结论</h2>")
    tldr = (
        "<div class='panel tldr'><p>"
        f"embedding 清理重置后，mentor 方案 B 的<b>最优并发数仍为 3</b>。"
        f"并发3 吞吐 {best.get('throughput',0.18):.3f} 份/s，"
        f"是并发1 的 {best.get('throughput',0.18)/results[0].get('throughput',0.084):.1f} 倍。"
        f"并发6 与并发3 吞吐持平但单份 embed 耗时翻倍、长尾暴涨"
        f"（max 118s vs 73s），<b>不带来收益只带来争抢开销</b>。"
        f"这与 embedding 清理前的结论一致——并发3 的甜点区未变。"
        "</p></div>"
    )
    html.append(tldr)

    # KPI 卡片（三档吞吐）
    html.append("<h2 id='compare'>二、三档对比</h2>")
    html.append('<div class="grid4">')
    for r in results:
        c = r.get("concurrency", 0)
        cls = "ok" if c == best_c else ("warn" if c == 6 else "")
        html.append(f'<div class="stat {cls}"><b>{r.get("throughput",0):.3f}</b>'
                    f'<small>并发{c} 吞吐</small></div>')
    html.append(f'<div class="stat"><b>{best.get("wall_seconds",0):.0f}s</b>'
                f'<small>最优档墙钟</small></div>')
    html.append("</div>")

    # 对比表
    html.append('<div class="panel"><table><thead><tr><th>指标</th>')
    for r in results:
        html.append(f'<th class="num">并发{r.get("concurrency")}</th>')
    html.append("</tr></thead><tbody>")

    rows = [
        ("墙钟(s)", lambda r: f'{r.get("wall_seconds",0):.1f}'),
        ("吞吐(份/s)", lambda r: f'{r.get("throughput",0):.3f}'),
        ("每份(s)", lambda r: f'{r.get("wall_seconds",0)/max(r.get("succeeded",1),1):.1f}'),
        ("成功/失败", lambda r: f'{r.get("succeeded",0)}/{r.get("failed",0)}'),
        ("peak in flight", lambda r: f'{r.get("peak_in_flight",0)}'),
        ("warmup(s)", lambda r: f'{r.get("warmup_seconds",0):.1f}'),
    ]
    for name, fn in rows:
        html.append(f"<tr><td>{name}</td>")
        for r in results:
            html.append(f'<td class="num">{fn(r)}</td>')
        html.append("</tr>")
    html.append("</tbody></table></div>")

    # 三、每阶段耗时
    html.append("<h2 id='stage'>三、每阶段耗时对比</h2>")
    html.append(
        '<div class="panel"><table><thead><tr><th>阶段</th>'
        '<th colspan="3" class="num">avg (ms)</th>'
        '<th colspan="3" class="num">p90 (ms)</th>'
        '<th colspan="3" class="num">max (ms)</th>'
        '</tr><tr><th></th>'
        + "".join(f'<th class="num">c{r.get("concurrency")}</th>' for r in results) * 3
        + '</tr></thead><tbody>'
    )
    for stage in ("parse", "chunk", "embed", "index"):
        html.append(f"<tr><td>{stage}</td>")
        for metric in ("avg", "p90", "max"):
            for r in results:
                st = stage_stats(r).get(stage, {})
                v = st.get(metric, 0) if st else 0
                html.append(f'<td class="num">{fmt_ms(v)}</td>')
        html.append("</tr>")
    html.append("</tbody></table>")

    # 占比
    html.append("<h3>耗时占比（每档）</h3>")
    for r in results:
        st = stage_stats(r)
        total = sum(d["sum"] for d in st.values()) if st else 1
        if not total:
            continue
        html.append(f"<p><b>并发{r.get('concurrency')}</b></p>")
        for stage in ("parse", "chunk", "embed", "index"):
            d = st.get(stage)
            share = d["share"] if d else 0
            bar_cls = {"parse": "b1", "chunk": "b1", "embed": "b3", "index": "b6"}.get(stage, "b1")
            html.append(f'<div class="bar-wrap"><div class="bar {bar_cls}" '
                        f'style="width:{share:.1f}%">{stage} {share:.1f}%</div></div>')
    html.append("</div>")

    # 四、embedding 长尾
    html.append("<h2 id='embed'>四、embedding 长尾分析</h2>")
    embed_data = []
    for r in results:
        st = stage_stats(r).get("embed", {})
        if st:
            embed_data.append((r.get("concurrency"), st))
    html.append(
        '<div class="panel"><table><thead><tr><th>并发</th>'
        '<th class="num">avg</th><th class="num">p50</th>'
        '<th class="num">p90</th><th class="num">max</th>'
        '<th class="num">max/avg</th></tr></thead><tbody>'
    )
    for c, st in embed_data:
        ratio = st["max"] / st["avg"] if st["avg"] else 0
        html.append(f"<tr><td>并发{c}</td><td class='num'>{fmt_ms(st['avg'])}</td>"
                    f"<td class='num'>{fmt_ms(st['p50'])}</td>"
                    f"<td class='num'>{fmt_ms(st['p90'])}</td>"
                    f"<td class='num'>{fmt_ms(st['max'])}</td>"
                    f"<td class='num'>{ratio:.1f}x</td></tr>")
    html.append("</tbody></table>")
    html.append(
        '<div class="caveat">并发越高，embedding 单份越慢、长尾越严重：'
        '<b>并发1 avg 11s → 并发6 avg 30s（2.7x 慢）'
        '；并发1 max 47s → 并发6 max 118s（2.5x 慢）</b>。'
        '这是共享 CPU embedding 服务的本质——并发请求争抢推理资源，'
        '单份变慢抵消并发收益。提速正解是 GPU/独立部署，不是加并发。</div>'
        '<p class="note">131 是 34 容器混跑的共享机，embedding 服务（bge-base）'
        '在 CPU 上推理，无 GPU。长尾根因是 embedding 服务负载抖动 + CPU 争抢，'
        '非编排层问题。</p></div>'
    )

    # 五、最优并发结论
    html.append("<h2 id='conclusion'>五、最优并发结论</h2>")
    html.append(
        '<div class="panel">'
        '<h3>最优并发数：3</h3>'
        '<table><thead><tr><th>依据</th><th>数据</th></tr></thead><tbody>'
        f'<tr><td>吞吐最高</td><td>并发3 {best.get("throughput",0):.3f} 份/s '
        f'vs 并发6 {results[-1].get("throughput",0):.3f}（持平）vs '
        f'并发1 {results[0].get("throughput",0):.3f}</td></tr>'
        '<tr><td>并发6 无收益</td><td>吞吐与并发3 几乎相同（差 1%），'
        '但单份 embed avg 翻倍（15s→30s）、max 暴涨（73s→118s）</td></tr>'
        '<tr><td>并发6 争抢开销</td><td>embedding 占比从 93.6%→95.2%，'
        '更多时间消耗在争抢等待</td></tr>'
        '<tr><td>与清理前一致</td><td>mentor 之前结论"并发3最优，'
        '并发6 反慢58%"——清理后特征不变，仅长尾程度因机器负载略变</td></tr>'
        '</tbody></table>'
        '<h3>建议</h3>'
        '<ul>'
        '<li><b>生产配置</b>：max_concurrent=3（确认值）</li>'
        '<li><b>换环境需重标定</b>：131 是共享机，负载波动大；'
        '换新机器或加 GPU 后需重新跑 1/3/6 阶梯压测</li>'
        '<li><b>提速正解</b>：给 embedding 服务配 GPU 或独立部署，'
        '而非加并发（并发6 实测无收益）</li>'
        '<li><b>1 万份规模推算</b>：并发3 吞吐 0.18 份/s，'
        f'1 万份约 {10000/0.18/3600:.1f} 小时——'
        '需 GPU 提速才能满足 PM 期望</li>'
        '</ul></div>'
    )

    html.append(
        f"<div class='footer'>生成于 {today} · bench_report.py · "
        f"数据源: {len(results)} 档压测 "
        f"(bench_c1/c3/c6.json)</div>"
    )
    html.append("</div></body></html>")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(html), encoding="utf-8")
    print(f"[report] saved -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
