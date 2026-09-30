"""AB 对比实验 — 数据准备：从 law_data 筛 N 份纯真 .docx。

laws_download.zip 内 29346 份文件全标 .docx，但 2026-09-07 baseline 证实其中
约 20% 是 .doc 老格式（OLE 二进制）改名为 .docx，python-docx 打不开。本脚本
用 python-docx 逐份探测有效性，筛出真正可被 OOXML 解析的 .docx，优先从
02_法律 / 03_行政法规 子目录取（体量适中，减少长尾偏置），解压到扁平目录
供 docker cp 进容器，并输出清单 JSON 供 ab_batch.py 两方案共用。

Usage (本地跑，用 code/ 的 uv 环境):
    uv run --project code python code/ingest/ab_prepare_docs.py --count 100
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

try:
    import docx  # python-docx
except ImportError:
    print("python-docx 未安装，执行: uv add --project code python-docx", file=sys.stderr)
    raise

# f:/byh/GCN_Poc/GCN_Poc/
ROOT = Path(__file__).resolve().parents[2]
LAW_ZIP = ROOT / "test" / "law_data" / "laws_download.zip"
OUT_DIR = ROOT / "test" / "_abtest_docs"
LIST_JSON = ROOT / "test" / "results" / "ab_doc_list.json"

# 优先从这些子目录取（体量适中），地方法规子目录文件最多但可能超长
PRIORITY_DIRS = ("02_法律", "03_行政法规", "06_司法解释", "01_总纲", "04_办法类")


def is_valid_docx(data: bytes) -> tuple[bool, int]:
    """python-docx 能打开且有非空文本 → 纯真 .docx。

    排除: .doc 改名（OLE 二进制，打不开）、空内容、加密件。
    返回 (是否有效, 字符数)。
    """
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception:
        return False, 0
    text = "\n".join(p.text for p in document.paragraphs).strip()
    if len(text) < 20:
        # 段落近乎空，看表格
        tbl = []
        for t in document.tables:
            for row in t.rows:
                for cell in row.cells:
                    tbl.append(cell.text)
        text = "".join(tbl).strip()
    return len(text) >= 20, len(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--zip", default=str(LAW_ZIP))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--list-json", default=str(LIST_JSON))
    args = ap.parse_args()

    zfp = Path(args.zip)
    if not zfp.exists():
        print(f"zip not found: {zfp}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    list_json = Path(args.list_json)
    list_json.parent.mkdir(parents=True, exist_ok=True)

    scanned = valid = 0
    by_subdir: dict[str, int] = {}
    selected: list[dict] = []

    with zipfile.ZipFile(zfp) as zf:
        names = zf.namelist()
        # 按优先级子目录排序
        def prio(name: str) -> int:
            for i, d in enumerate(PRIORITY_DIRS):
                if d in name:
                    return i
            return len(PRIORITY_DIRS)
        names.sort(key=prio)

        for name in names:
            if not name.endswith(".docx") or name.endswith("/"):
                continue
            scanned += 1
            try:
                data = zf.read(name)
            except Exception:
                continue
            ok, chars = is_valid_docx(data)
            if not ok:
                continue
            valid += 1
            base = name.rsplit("/", 1)[-1]
            # 扁平解压到 out_dir，覆盖同名
            (out_dir / base).write_bytes(data)
            subdir = "/".join(name.split("/")[:-1]) or "(root)"
            by_subdir[subdir] = by_subdir.get(subdir, 0) + 1
            selected.append({"name": base, "zip_path": name, "chars": chars})
            if len(selected) >= args.count:
                break

    list_json.write_text(
        json.dumps(
            {"count": len(selected), "zip": str(zfp), "out_dir": str(out_dir), "docs": selected},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    print(f"[prepare] scanned={scanned} valid={valid} selected={len(selected)}")
    print(f"[prepare] by subdir: {by_subdir}")
    print(f"[prepare] docs -> {out_dir}")
    print(f"[prepare] list  -> {list_json}")
    if selected:
        chars = [d["chars"] for d in selected]
        print(f"[prepare] chars: min={min(chars)} max={max(chars)} "
              f"median={sorted(chars)[len(chars)//2]}")
    return 0 if len(selected) == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
