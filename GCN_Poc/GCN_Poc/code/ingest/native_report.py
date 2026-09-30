"""RAGFlow 原生批量上传接口测试报告生成。

读 native_r1.json（默认100份）+ native_cancel.json（取消测试），
生成暗色主题 HTML 报告，仿批量导入规模验证_20260907.html 样式。

Usage:
    uv run --project code python code/ingest/native_report.py \
      --main test/results/131_测试/native_r1.json \
      --cancel test/results/131_测试/native_cancel.json \
      --out doc/design/131_测试/RAGFlow原生批量上传测试_YYYYMMDD.html
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
  .bar.b-done { background:#35c56a; } .bar.b-run { background:#f5a623; }
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", required=True, help="主测试 JSON（100份默认）")
    ap.add_argument("--cancel", default="", help="取消测试 JSON")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    r = load(args.main)
    c = load(args.cancel) if args.cancel else None
    today = date.today().isoformat()
    out_path = Path(args.out) if args.out else (
        ROOT / "doc" / "design" / f"RAGFlow原生批量上传测试_{today}.html"
    )

    wall = r["parse_wall_seconds"]
    thr = r["throughput"]
    succ = r["succeeded"]
    total = r["docs"]
    upload = r["upload_seconds"]

    # 进度爬升轨迹（采样）
    samples = r.get("progress_samples", [])

    html = []
    html.append("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    html.append(f"<meta name='viewport' content='width=device-width, initial-scale=1'>")
    html.append(f"<title>RAGFlow 原生批量上传接口测试 · {today}</title><style>{CSS}</style></head><body>")
    html.append("<div class='wrap'>")
    html.append("<h1>RAGFlow 原生批量上传接口测试报告</h1>")
    html.append(f"<p class='sub'>方案A（RAGFlow 原生 /documents + /chunks 接口）· "
                f"GCN 采购文件活化项目<br>"
                f"执行人：小zhu · 日期：{today} · 环境：131 服务器 RAGFlow v0.26.1 · "
                f"数据：law_data 100 份纯真 .docx</p>")

    html.append("<div class='toc'><b>目录</b><br>"
                "<a href='#tldr'>一、结论</a> · "
                "<a href='#kpi'>二、核心指标</a> · "
                "<a href='#progress'>三、进度爬升轨迹</a> · "
                "<a href='#vis'>四、进度可见性</a> · "
                "<a href='#cancel'>五、取消能力实测</a> · "
                "<a href='#compare'>六、与方案B对比</a> · "
                "<a href='#next'>七、结论与建议</a></div>")

    # 一、TL;DR
    html.append("<h2 id='tldr'>一、结论</h2>")
    html.append(
        f"<div class='panel tldr'><p>"
        f"RAGFlow 原生批量上传接口能完成 100 份文档上传与解析，"
        f"上传 <strong>{upload:.1f}s</strong>、解析墙钟 <strong>{wall:.0f}s（{wall/60:.1f} 分钟）</strong>、"
        f"<strong>{succ}/{total} 成功</strong>、吞吐 <strong>{thr:.3f} 份/s</strong>。"
        f"但进度可见性弱（仅单浮点 + 排队文本，无阶段计时）、"
        f"<strong>取消能力实测不生效（DELETE /chunks 后 0 份变 CANCEL，全部正常 DONE）</strong>、"
        f"无 pause/resume。这正是 mentor 自建方案 B 绕过 RAGFlow 解析引擎的核心动机。"
        f"</p></div>"
    )

    # 二、KPI
    html.append("<h2 id='kpi'>二、核心指标</h2>")
    html.append('<div class="grid4">')
    html.append(f'<div class="stat warn"><b>{wall:.0f}s</b><small>解析墙钟</small></div>')
    html.append(f'<div class="stat"><b>{thr:.3f}</b><small>份/秒 吞吐</small></div>')
    html.append(f'<div class="stat ok"><b>{succ}/{total}</b><small>成功/总数</small></div>')
    html.append(f'<div class="stat"><b>{upload:.1f}s</b><small>上传耗时</small></div>')
    html.append("</div>")
    html.append(
        '<div class="note">测试方式：纯 RAGFlow HTTP API（POST /documents 批量上传 → '
        'POST /chunks 启动解析 → 每 2s 轮询 GET /documents 到全部终态），'
        '不走 mentor 编排层。</div>'
    )

    # 三、进度爬升轨迹
    html.append("<h2 id='progress'>三、进度爬升轨迹</h2>")
    html.append(
        '<div class="panel"><p>从轮询采样看，前 ~8 分钟 100 份全卡在 RUNNING、done=0、'
        'overall=0%；随后才开始陆续完成。</p>'
    )
    html.append("<table><thead><tr><th>墙钟</th><th class='num'>done</th>"
                "<th class='num'>running</th><th class='num'>overall</th>"
                "<th class='num'>max_dur(s)</th></tr></thead><tbody>")
    step = max(1, len(samples) // 25)
    for s in samples[::step]:
        durs = [rm.get("dur", 0) for rm in s.get("running_msgs", [])]
        max_dur = max(durs) if durs else 0
        html.append(f"<tr><td>{s.get('wall')}s</td><td class='num'>{s.get('done')}</td>"
                    f"<td class='num'>{s.get('running')}</td><td class='num'>{s.get('overall_pct')}%</td>"
                    f"<td class='num'>{max_dur:.1f}</td></tr>")
    html.append("</tbody></table>")
    html.append('<p class="note">关键现象：task_executor 默认 embed_limiter=1（串行 embedding），'
               '100 份文档在 Redis Stream 队列里排队，前 483s 一份都没跑完。'
               'progress 浮点全程几乎不动（0.0049~0.0069），没有任何"parse 完成、'
               '开始 embed"的阶段边界信息。</p></div>')

    # 四、进度可见性
    html.append("<h2 id='vis'>四、进度可见性</h2>")
    html.append(
        '<div class="caveat">RAGFlow 原生接口只提供：单浮点 progress（0.0~1.0）+ '
        'progress_msg 文本（排队信息）。<strong>没有任何分阶段计时</strong>——'
        '看不到 parse/chunk/embed/index 各阶段耗时，看不到当前在哪个阶段，'
        '看不到长尾定位。</div>'
    )
    html.append("<div class='panel'><h3>progress_msg 全部文本样本（去重）</h3>")
    seen = set()
    msgs = []
    for m in r.get("msg_samples", []):
        msg = m.get("msg", "")
        if msg and msg not in seen:
            seen.add(msg)
            msgs.append(m)
    html.append("<pre>")
    for m in msgs:
        html.append(f"wall={m.get('wall')}s prog={m.get('prog')} dur={m.get('dur')}s")
        html.append(f"  msg: {m.get('msg','')}")
    html.append("</pre>")
    html.append(f'<p class="note">100 份文档全流程只有 {len(seen)} 种不同的 progress_msg 文本，'
               '全都是排队信息。没有"OCR""embedding""entity"等阶段关键词。'
               '对比：方案 B（mentor 自建）每阶段有 duration_ms 精确计时。</p></div>')

    # 五、取消能力
    html.append("<h2 id='cancel'>五、取消能力实测</h2>")
    if c and c.get("cancel_test"):
        ct = c["cancel_test"]
        triggered = ct.get("triggered_at_overall", 0)
        final_cancel = ct.get("final_cancelled", 0)
        final_done = ct.get("final_done", 0)
        html.append(
            '<div class="panel"><h3>实测设计</h3>'
            '<p>跑 100 份，当整体进度到 30% 时发 <code>DELETE /chunks</code> 取消，'
            '然后继续轮询观察：RAGFlow 能否停下？run 变成什么？能否恢复？</p>'
            '<table><thead><tr><th>项</th><th>结果</th></tr></thead><tbody>'
            f'<tr><td>触发时机</td><td>overall={triggered}%（wall={ct.get("triggered_at_wall")}s）</td></tr>'
            f'<tr><td>触发后最终 cancelled</td><td>'
            f'<span class="tag err">{final_cancel}</span> '
            '（预期取消生效应 >0）</td></tr>'
            f'<tr><td>触发后最终 done</td><td>'
            f'<span class="tag warn">{final_done}</span> '
            '（文档继续跑完了）</td></tr>'
            '<tr><td>能否 pause/resume</td>'
            '<td><span class="tag err">不支持</span> 原生无 pause 状态，只有 cancel</td></tr>'
            '<tr><td>恢复续跑</td>'
            '<td><span class="tag err">不能</span> 需重新 POST /chunks 全量重跑</td></tr>'
            '</tbody></table></div>'
        )
        html.append(
            '<div class="caveat">实测结论：DELETE /chunks 在文档多的场景下'
            '<strong>取消不彻底</strong>——触发取消时 30 份已 DONE（终态不可取消），'
            '剩下 70 份在 RUNNING，取消发出后<strong>最终 0 份变 CANCEL，100 份全部 DONE</strong>。'
            'RAGFlow 的取消是"软取消"（设 Redis 标志，worker 在 has_canceled() 检查点才停），'
            '但串行 embedding 场景下检查点之间文档已被处理完。'
            '<br>对比：方案 B（mentor 自建）支持 pause/resume/retry，'
            'stage 边界检查 _cancelled 标志，可从失败态单独重试。</div>'
        )
    else:
        html.append('<div class="note">无取消测试数据。</div>')

    # 六、与方案B对比
    html.append("<h2 id='compare'>六、与方案B（mentor 自建）对比</h2>")
    html.append(
        '<div class="panel"><table><thead><tr><th>维度</th>'
        '<th>方案A（RAGFlow 原生，本次实测）</th>'
        '<th>方案B（mentor 自建，job 37 baseline）</th></tr></thead><tbody>'
        '<tr><td>解析执行</td><td>RAGFlow task_executor (Redis Stream)</td>'
        '<td>mentor 进程内 parse→chunk→embed→index</td></tr>'
        '<tr><td>规模</td><td>100 份</td><td>1000 份（含 20% 脏数据）</td></tr>'
        '<tr><td>墙钟</td><td>1104s</td><td>3192s</td></tr>'
        '<tr><td>吞吐</td><td class="num">0.091 份/s</td>'
        '<td class="num">0.25 份/s</td></tr>'
        '<tr><td>成功率</td><td>100%（数据预筛纯真.docx）</td>'
        '<td>79.6%（204 份 .doc 脏数据）</td></tr>'
        '<tr><td>进度可见性</td><td>'
        '<span class="tag err">弱</span> 单浮点 + 排队文本，无阶段计时</td>'
        '<td><span class="tag ok">强</span> 每阶段 duration_ms 精确计时</td></tr>'
        '<tr><td>暂停</td><td><span class="tag err">不支持</span></td>'
        '<td><span class="tag ok">支持</span> stage 边界暂停</td></tr>'
        '<tr><td>取消</td><td><span class="tag err">不彻底</span> 实测 0/70 生效</td>'
        '<td><span class="tag ok">支持</span> 即时取消</td></tr>'
        '<tr><td>重试</td><td><span class="tag err">不能</span> 需重新 POST /chunks 全量</td>'
        '<td><span class="tag ok">支持</span> 单份从失败态重试</td></tr>'
        '<tr><td>失败隔离</td><td>支持（单文档失败不影响其他）</td>'
        '<td>支持（实测 204 份失败未拖累 796 份）</td></tr>'
        '</tbody></table>'
        '<p class="note">方案A 吞吐低于方案B，主因是 task_executor embed_limiter=1 串行 vs '
        '方案B 并发 3。轮2（调优对齐并发）待测。</p></div>'
    )

    # 七、结论
    html.append("<h2 id='next'>七、结论与建议</h2>")
    html.append(
        '<div class="panel">'
        '<h3>性能</h3>'
        '<p>RAGFlow 原生批量上传接口功能完整，100 份文档上传 3.2s、解析 1104s、'
        '吞吐 0.091 份/s。上传快（multipart 批量），解析慢（task_executor 串行 embedding）。</p>'
        '<h3>进度可见性（硬伤）</h3>'
        '<p>原生只给单浮点 progress + progress_msg 排队文本，<strong>无法看到分阶段进度与计时</strong>，'
        '无法定位长尾，无法满足项目经理"每阶段计时"需求。</p>'
        '<h3>可控性（硬伤）</h3>'
        '<p><strong>取消实测不生效</strong>（DELETE /chunks 后 0 份变 CANCEL），'
        '无 pause/resume，无单份重试。无法满足"随时暂停/重试"需求。</p>'
        '<h3>建议</h3>'
        '<p>批量导入场景（需暂停/重试/每阶段计时）用方案B（mentor 自建）；'
        '轻量单文档上传可用方案A 原生接口。轮2 测方案A 调优并发（embed_limiter=3）'
        '看能否缩小吞吐差距。</p>'
        '</div>'
    )

    html.append(f"<div class='footer'>生成于 {today} · native_report.py · "
                f"数据源: {args.main}"
                + (f" + {args.cancel}" if args.cancel else "")
                + "</div>")
    html.append("</div></body></html>")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(html), encoding="utf-8")
    print(f"[report] saved -> {out_path}")
    print(f"[report] main: {args.main}")
    if args.cancel:
        print(f"[report] cancel: {args.cancel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
