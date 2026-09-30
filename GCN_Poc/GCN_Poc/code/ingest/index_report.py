"""两天测试总索引报告——汇总所有测试过程与结论，可点击跳转各子报告。

Usage:
    uv run --project code python code/ingest/index_report.py \
      --out doc/design/131_测试/批量上传测试总索引_20260908.html
"""

from __future__ import annotations

import argparse
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
  h1 { font-size:26px; font-weight:600; margin:0 0 4px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:28px; }
  h2 { font-size:18px; font-weight:600; margin:34px 0 14px;
       padding-bottom:8px; border-bottom:1px solid var(--line); }
  h3 { font-size:15px; font-weight:600; margin:20px 0 8px; color:var(--accent); }
  .panel { background:var(--panel); border:1px solid var(--line);
           border-radius:8px; padding:18px 20px; margin:14px 0; }
  .panel.tldr { border-left:3px solid var(--accent); }
  table { width:100%; border-collapse:collapse; font-size:13px; margin:8px 0; }
  th, td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--line);
           vertical-align:middle; }
  th { color:var(--muted); font-weight:500; font-size:12px; }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
  .tag { display:inline-block; padding:2px 9px; border-radius:11px;
         font-size:11.5px; border:1px solid; text-decoration:none; }
  .tag.ok { color:var(--ok); border-color:var(--ok); }
  .tag.warn { color:var(--warn); border-color:var(--warn); }
  .tag.err { color:var(--err); border-color:var(--err); }
  .tag.acc { color:var(--accent); border-color:var(--accent); }
  .grid4 { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:14px 0; }
  .stat { background:var(--panel); border:1px solid var(--line); border-radius:8px;
          padding:16px 14px; text-align:center; }
  .stat b { display:block; font-size:24px; font-weight:600; }
  .stat small { color:var(--muted); font-size:11.5px; }
  .stat.warn b { color:var(--warn); }
  .stat.err b { color:var(--err); }
  .stat.ok b { color:var(--ok); }
  .caveat { background:#2a2016; border-left:3px solid var(--warn); padding:12px 16px;
            border-radius:0 6px 6px 0; font-size:13px; color:#f0d9b5; margin:14px 0; }
  .note { background:#0d1016; border-radius:6px; padding:10px 14px; font-size:12.5px;
          color:#93a4b8; margin:10px 0; }
  code { background:#0d1016; padding:1.5px 6px; border-radius:4px; font-size:12px;
         color:#b9c6d8; }
  .toc { background:var(--panel); border:1px solid var(--line); border-radius:8px;
         padding:14px 20px; margin:20px 0; }
  .toc a { color:var(--accent); text-decoration:none; font-size:13px; }
  .toc a:hover { text-decoration:underline; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:8px;
          padding:16px 20px; margin:12px 0; transition:border-color 0.2s; }
  .card:hover { border-color:var(--accent); }
  .card h3 { margin-top:0; }
  .card .meta { color:var(--muted); font-size:12px; margin-bottom:8px; }
  .card .link { margin-top:10px; }
  .card .link a { color:var(--accent); text-decoration:none; font-size:13px; }
  .card .link a:hover { text-decoration:underline; }
  .timeline { position:relative; padding-left:24px; }
  .timeline::before { content:''; position:absolute; left:8px; top:0; bottom:0;
                       width:2px; background:var(--line); }
  .tl-item { position:relative; margin-bottom:20px; }
  .tl-item::before { content:''; position:absolute; left:-20px; top:6px;
                      width:10px; height:10px; border-radius:50%; background:var(--accent); }
  .tl-item.err::before { background:var(--err); }
  .tl-item.ok::before { background:var(--ok); }
  .tl-item.warn::before { background:var(--warn); }
  .tl-time { color:var(--muted); font-size:12px; }
  .footer { color:var(--muted); font-size:12px; margin-top:40px;
            padding-top:16px; border-top:1px solid var(--line); }
  .badge { display:inline-block; padding:1px 7px; border-radius:4px;
           font-size:11px; margin-left:6px; }
  .badge.done { background:#1a3a1a; color:var(--ok); }
  .badge.run { background:#3a2f0a; color:var(--warn); }
  .badge.todo { background:#2a2a33; color:var(--muted); }
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    today = date.today().isoformat()
    out_path = Path(args.out) if args.out else (
        ROOT / "doc" / "design" / f"批量上传测试总索引_{today}.html"
    )

    html = []
    html.append("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    html.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    html.append(f"<title>批量上传测试总索引 · {today}</title><style>{CSS}</style></head><body><div class='wrap'>")

    # 标题
    html.append("<h1>批量上传测试总索引</h1>")
    html.append(
        f"<p class='sub'>GCN 采购文件活化项目 · 2026-09-07~09-08 两天测试全过程汇总<br>"
        f"执行人：小zhu · 环境：131 服务器 RAGFlow v0.26.1 · "
        f"测试数据：law_data 法律法规 .docx</p>"
    )

    # 目录
    html.append("<div class='toc'><b>导航</b><br>"
                "<a href='#tldr'>一、一句话结论</a> · "
                "<a href='#timeline'>二、测试时间线</a> · "
                "<a href='#reports'>三、子报告索引</a> · "
                "<a href='#data'>四、关键数据汇总</a> · "
                "<a href='#bugs'>五、发现的问题</a> · "
                "<a href='#next'>六、后续行动</a></div>")

    # 一、TL;DR
    html.append("<h2 id='tldr'>一、一句话结论</h2>")
    tldr = (
        "<div class='panel tldr'><p>"
        "用 4 份可点击的子报告覆盖了 PM 第 1 点（批量上传可管理）的完整验证："
        "<b>RAGFlow 原生接口能完成文档上传与解析，但不可管</b>"
        "（进度只能猜、取消不生效、无暂停/重试，满足 PM 5 项需求中的 1 项）；"
        "<b>mentor 方案 B 自建编排解决了全部局限</b>（每阶段计时/暂停/重试/失败隔离全有），"
        "并发 3 最优（吞吐 0.18 份/s，embedding 清理后仍稳），"
        "<b>1 万份稳定性测试正在后台跑</b>（预计 16-22 小时）。"
        "</p></div>"
    )
    html.append(tldr)

    # KPI 卡片
    html.append("<div class='grid4'>")
    html.append('<div class="stat"><b>4</b><small>份子报告</small></div>')
    html.append('<div class="stat ok"><b>0.18</b><small>方案B最优吞吐</small></div>')
    html.append('<div class="stat err"><b>0/5</b><small>方案A满足PM需求</small></div>')
    html.append('<div class="stat warn"><b>1万</b><small>份测试进行中</small></div>')
    html.append("</div>")

    # 二、测试时间线
    html.append("<h2 id='timeline'>二、测试时间线（2026-09-07 ~ 09-08）</h2>")
    html.append('<div class="panel"><div class="timeline">')

    timeline_items = [
        ("09-07", "ok", "方案B千份 baseline",
         "mentor 已跑的 job 37：1000 份 law_data，796 成功/204 失败（.doc 脏数据），"
         "墙钟 3192s，吞吐 0.25 份/s，embedding 占 96%。"
         "<a href='批量导入规模验证_20260907.html' class='tag acc'>查看报告</a>"),
        ("09-08", "ok", "方案A纯原生测试（100份）",
         "直接调 RAGFlow HTTP API（POST /documents + /chunks + GET /documents 轮询），"
         "不走 mentor 编排。100 份全成功，墙钟 1104s，吞吐 0.091 份/s。"
         "进度可见性弱（progress_msg 只有 4 种排队文本）。"
         "<a href='RAGFlow原生批量上传测试_20260908.html' class='tag acc'>查看报告</a>"),
        ("09-08", "err", "方案A取消能力实测",
         "跑到 30% 时发 DELETE /chunks，最终 0 份变 CANCEL、100 份全 DONE。"
         "RAGFlow 原生取消在文档多的串行场景下不彻底，无 pause/resume。"),
        ("09-08", "ok", "方案B并发压测（1/3/6 × 50份）",
         "embedding 清理重置后重新标定并发数。并发3 吞吐 0.180 份/s（最优），"
         "并发6 与并发3 持平但单份 embed 翻倍（15s→30s）、长尾暴涨（73s→118s）。"
         "结论：并发3 甜点区未变。"
         "<a href='方案B并发压测_20260908.html' class='tag acc'>查看报告</a>"),
        ("09-08", "err", "发现方案B MySQL 持久化并发 bug",
         "用 --persist（MySQLRepository）跑 1 万份，task 全失败"
         "（'NoneType' has no attribute 'status'）。根因：threading.local 连接在 "
         "ThreadPoolExecutor 并发下断开。退回 InMemory 跑。值得反馈 mentor。"),
        ("09-08", "warn", "1万份稳定性测试",
         "InMemory 模式后台跑 1 万份 × 并发3。当前 wall=1443s succeeded=185 failed=0，"
         "吞吐 0.128 份/s，预计 16-22 小时跑完。<span class='badge run'>进行中</span>"),
    ]
    for t, cls, title, desc in timeline_items:
        html.append(f'<div class="tl-item {cls}"><div class="tl-time">{t}</div>'
                    f'<h3>{title}</h3><p>{desc}</p></div>')
    html.append("</div></div>")

    # 三、子报告索引
    html.append("<h2 id='reports'>三、子报告索引（点击查看详情）</h2>")

    reports = [
        ("批量导入规模验证_20260907.html", "方案B千份 baseline（09-07）",
         "mentor 自建方案 B 跑 1000 份 law_data 的规模验证。吞吐 0.25 份/s 线性稳定，"
         "embedding 占 96%，失败 100% 是 .doc 脏数据（系统零 bug）。",
         ["吞吐线性稳定", "失败归因", "每阶段耗时", "长尾分析"], "done"),
        ("RAGFlow原生批量上传测试_20260908.html", "方案A纯原生测试（09-08）",
         "直接调 RAGFlow HTTP API 跑 100 份纯真 .docx。100% 成功，墙钟 1104s，"
         "吞吐 0.091 份/s。progress_msg 只有排队文本，取消实测 0/70 生效。",
         ["KPI 指标", "进度爬升轨迹", "进度可见性", "取消能力实测", "与方案B对比"], "done"),
        ("方案B并发压测_20260908.html", "方案B并发压测（09-08）",
         "embedding 清理后重新标定并发数。1/3/6 三档 × 50 份。"
         "并发3 最优（0.180 份/s），并发6 无收益（争抢开销）。",
         ["三档对比", "每阶段耗时", "embedding 长尾", "最优并发结论"], "done"),
        ("RAGFlow原生局限与mentor方案结论_20260908.html", "结论报告（09-08）",
         "三重证据（源码+文档+实测）整合。RAGFlow 原生六大局限 + mentor 方案B解决了什么 + "
         "边界与风险 + 选型建议。",
         ["六大局限", "方案B解决矩阵", "边界风险", "选型建议"], "done"),
        ("（待生成）1万份稳定性报告", "1万份稳定性测试（09-08，进行中）",
         "InMemory 后台跑 1 万份 × 并发3，验证大规模稳定性。预计 16-22 小时。"
         "跑完后生成报告，含万份吞吐曲线 + 失败率 + 15小时长尾变化。",
         ["万份吞吐曲线", "稳定性验证", "MySQL bug 记录"], "run"),
    ]
    for href, title, desc, tags, status in reports:
        badge = {"done": '<span class="badge done">已完成</span>',
                 "run": '<span class="badge run">进行中</span>',
                 "todo": '<span class="badge todo">待做</span>'}[status]
        tag_html = "".join(f'<span class="tag acc">{t}</span> ' for t in tags)
        link = (f'<a href="{href}">点击查看 →</a>' if not href.startswith("（")
                 else '<span style="color:var(--muted)">跑完后生成</span>')
        html.append(
            f'<div class="card"><div class="meta">{title} {badge}</div>'
            f'<p>{desc}</p><div>{tag_html}</div>'
            f'<div class="link">{link}</div></div>'
        )

    # 四、关键数据汇总
    html.append("<h2 id='data'>四、关键数据汇总</h2>")
    html.append(
        '<div class="panel"><h3>所有测试批次对比</h3>'
        '<table><thead><tr><th>批次</th><th>方案</th><th class="num">文档数</th>'
        '<th class="num">墙钟</th><th class="num">吞吐</th>'
        '<th class="num">成功率</th><th>说明</th></tr></thead><tbody>'
        '<tr><td>job 35</td><td>B</td><td class="num">161</td>'
        '<td class="num">658s</td><td class="num">0.24</td>'
        '<td class="num">98.8%</td><td>百份级</td></tr>'
        '<tr><td>job 37</td><td>B</td><td class="num">1000</td>'
        '<td class="num">3192s</td><td class="num">0.25</td>'
        '<td class="num">79.6%</td><td>千份级（含 .doc 脏数据）</td></tr>'
        '<tr><td>本次</td><td>A 原生</td><td class="num">100</td>'
        '<td class="num">1104s</td><td class="num">0.091</td>'
        '<td class="num">100%</td><td>纯原生 API，数据预筛</td></tr>'
        '<tr><td>c1</td><td>B</td><td class="num">50</td>'
        '<td class="num">594s</td><td class="num">0.084</td>'
        '<td class="num">100%</td><td>并发1 串行基线</td></tr>'
        '<tr><td>c3</td><td>B</td><td class="num">50</td>'
        '<td class="num">278s</td><td class="num">0.180</td>'
        '<td class="num">100%</td><td>并发3 最优</td></tr>'
        '<tr><td>c6</td><td>B</td><td class="num">50</td>'
        '<td class="num">275s</td><td class="num">0.182</td>'
        '<td class="num">100%</td><td>并发6 无收益</td></tr>'
        '<tr><td>10k</td><td>B</td><td class="num">10000</td>'
        '<td class="num">~21h</td><td class="num">~0.128</td>'
        '<td class="num">?</td><td>进行中 <span class="badge run">跑</span></td></tr>'
        '</tbody></table></div>'
    )

    # 五、发现的问题
    html.append("<h2 id='bugs'>五、发现的问题</h2>")
    html.append(
        '<div class="panel"><h3>1. RAGFlow 原生取消不生效（方案A硬伤）</h3>'
        '<p>DELETE /chunks 在文档多的串行场景下取消不彻底——'
        '实测跑到 30% 时取消，最终 0 份变 CANCEL，100 份全部正常 DONE。'
        'RAGFlow 的取消是软取消（Redis 标志 + worker 阶段边界检查），'
        '但串行 embedding 下检查点之间文档已被处理完。</p>'
        '<div class="note">影响：方案A 无法满足 PM"随时暂停/重试"需求。</div></div>'
    )
    html.append(
        '<div class="panel"><h3>2. 方案B MySQL 持久化并发 bug（反馈 mentor）</h3>'
        '<p>MySQLRepository 用 threading.local() 每线程一个连接，'
        '在 Scheduler 的 ThreadPoolExecutor 并发下连接断开，'
        'get_task 返回 None 导致 task 全失败（'
        '<code>\'NoneType\' object has no attribute \'status\'</code>）。</p>'
        '<div class="note">复现：--persist --concurrency 3，10000 份 7 份成功后全卡死。'
        'InMemory 模式不受影响（50 份 c1/c3/c6 全成功）。'
        '<br>建议 mentor：MySQLRepository 加连接 ping 检查/自动重连机制。</div></div>'
    )
    html.append(
        '<div class="panel"><h3>3. embedding 长尾（两方案共性瓶颈）</h3>'
        '<p>bge-base 在 131 共享 CPU 上推理，单份 embed avg 11s（并发1）→ 30s（并发6），'
        'max 47s→118s。并发越高长尾越严重。提速正解是 GPU/独立部署，不是加并发。</p>'
        '<div class="note">131 是 34 容器混跑、load 22、无 GPU、embedding 服务跑 36 天。</div></div>'
    )

    # 六、后续行动
    html.append("<h2 id='next'>六、后续行动</h2>")
    html.append(
        '<div class="panel"><ul>'
        '<li><b>1万份跑完</b>：明天上午查进度，拉数据生成稳定性报告（含万份吞吐曲线）'
        '<span class="badge run">进行中</span></li>'
        '<li><b>反馈 mentor</b>：MySQL 并发 bug + 1万份稳定性结论 '
        '<span class="badge todo">待做</span></li>'
        '<li><b>轮2（可选）</b>：方案A 调 embed_limiter=3 对齐并发，'
        '看吞吐能否追上方案B <span class="badge todo">待确认</span></li>'
        '<li><b>embedding 提速</b>：给 bge-base 配 GPU 或独立部署 '
        '<span class="badge todo">PM关注</span></li>'
        '<li><b>复杂版面解析</b>：方案B 的 docx 解析较简单，'
        '核电手册含图复杂表格需对比 RAGFlow DeepDOC <span class="badge todo">待验证</span></li>'
        '</ul></div>'
    )

    # 文件清单
    html.append(
        '<div class="panel"><h3>本索引涉及的文件</h3>'
        '<table><thead><tr><th>文件</th><th>说明</th></tr></thead><tbody>'
        '<tr><td><code>RAGFlow原生批量上传测试_20260908.html</code></td>'
        '<td>方案A 100份测试详情</td></tr>'
        '<tr><td><code>方案B并发压测_20260908.html</code></td>'
        '<td>方案B 并发1/3/6 压测详情</td></tr>'
        '<tr><td><code>RAGFlow原生局限与mentor方案结论_20260908.html</code></td>'
        '<td>结论报告（六大局限+方案B解决矩阵）</td></tr>'
        '<tr><td><code>批量导入规模验证_20260907.html</code></td>'
        '<td>方案B 千份 baseline（mentor 前序工作）</td></tr>'
        '<tr><td><code>批量上传测试总索引_20260908.html</code></td>'
        '<td>本页（总索引）</td></tr>'
        '</tbody></table>'
        '<p class="note">所有 HTML 在同一目录（doc/design/），'
        '点击链接即可在浏览器打开。</p></div>'
    )

    html.append(
        f"<div class='footer'>生成于 {today} · index_report.py · "
        f"小zhu 两天测试汇总（2026-09-07~08）</div>"
    )
    html.append("</div></body></html>")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(html), encoding="utf-8")
    print(f"[report] saved -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
