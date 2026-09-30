"""给 5 份报告 HTML 注入共享顶部导航栏。

固定顶部横条 navbar，暗色主题，当前页高亮，相对链接同目录跳转。
直接改写 HTML 文件（在 <body> 后插入 navbar，并给内容加 padding-top 避免遮挡）。

Usage:
    uv run --project code python code/ingest/inject_navbar.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "doc" / "design"

# 导航项：(显示名, 文件名)
NAV_ITEMS = [
    ("总索引", "批量上传测试总索引_20260908.html"),
    ("方案A测试", "RAGFlow原生批量上传测试_20260908.html"),
    ("方案B并发压测", "方案B并发压测_20260908.html"),
    ("结论报告", "RAGFlow原生局限与mentor方案结论_20260908.html"),
    ("千份baseline", "批量导入规模验证_20260907.html"),
    ("万份压测", "万份稳定性压测_20260911.html"),
]

# navbar CSS + HTML 模板
NAVBAR_CSS = """
  #topnav { position:fixed; top:0; left:0; right:0; height:44px; z-index:9999;
            background:#0b0d12; border-bottom:1px solid #262a33;
            display:flex; align-items:center; padding:0 20px; gap:4px;
            font:13px/1.4 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }
  #topnav a { color:#9aa3ad; text-decoration:none; padding:6px 12px; border-radius:6px;
              white-space:nowrap; }
  #topnav a:hover { background:#171a21; color:#e6e8eb; }
  #topnav a.active { color:#4c8dff; background:#111620; }
  #topnav .brand { font-weight:600; color:#e6e8eb; margin-right:12px;
                   padding-right:12px; border-right:1px solid #262a33; }
  body { padding-top:44px !important; }
  body > .wrap { margin-top:20px; }
"""

NAVBAR_TEMPLATE = '<div id="topnav"><span class="brand">批量上传测试</span>{items}</div>'


def build_navbar(current_file: str) -> str:
    items = []
    for name, fname in NAV_ITEMS:
        cls = ' class="active"' if fname == current_file else ""
        items.append(f'<a href="{fname}"{cls}>{name}</a>')
    return NAVBAR_TEMPLATE.format(items="".join(items))


def inject(filepath: Path) -> str:
    """给一份 HTML 注入 navbar，返回处理结果描述。"""
    if not filepath.exists():
        return f"SKIP (not found): {filepath.name}"
    html = filepath.read_text(encoding="utf-8")
    current_file = filepath.name

    # 已注入过就跳过（幂等）
    if 'id="topnav"' in html:
        # 更新 active 状态
        html = re.sub(r'<a href="[^"]*" class="active"', '<a href="{0}"'.format(current_file),
                      html)  # 简单处理：重新生成更稳
        # 实际上直接重新注入更干净：先删旧 navbar
        html = re.sub(r'<div id="topnav">.*?</div>\n?', '', html, flags=re.S)

    # 注入 CSS（在 </style> 前追加）
    if NAVBAR_CSS.strip() not in html:
        html = html.replace("</style>", NAVBAR_CSS + "\n</style>", 1)

    # 注入 navbar HTML（在 <body> 后）
    navbar = build_navbar(current_file)
    # 找 <body> 后第一个位置
    html = re.sub(r'(<body[^>]*>)', r'\1\n' + navbar, html, count=1)

    filepath.write_text(html, encoding="utf-8")
    return f"OK: {filepath.name}"


def main() -> int:
    results = []
    for _, fname in NAV_ITEMS:
        fp = DESIGN / fname
        results.append(inject(fp))
    for r in results:
        print(f"[nav] {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
