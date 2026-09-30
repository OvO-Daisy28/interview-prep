# -*- coding: utf-8 -*-
"""
build_ocr_mock.py — 从 PTR 冷却泵真实手册构建 OCR 校对仿真数据
运行: python tools/build_ocr_mock.py
输出: POC/js/ocr-mock-data.js  (window.OCR_MOCK = {...})
仅在开发期运行，演示不需要 Python。
"""
import zipfile, re, json, os, sys, io, html

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"C:\Users\Lenovo\Desktop\中广核项目\PTR冷却泵POC验证文件"
DOCX = os.path.join(SRC, "PTR冷却泵设备运行与维修手册.docx")
OUT = os.path.join(BASE, "js", "ocr-mock-data.js")

MAX_BLOCKS = 55          # 总块数上限（约 6~7 个仿真页；实际在 1.4 节即满，覆盖第1章多张表格）
CHAPTER_RANGE = ("1", "2")  # 抽取范围上限第1、2章（含标题/正文/图片/表格全类型；达到 MAX_BLOCKS 即停）

# ---------------------------------------------------------------- docx 解析（与 build_mock_data.py 同手法）
IMG_EXT = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}
OCR_ASSETS = os.path.join(BASE, "assets", "ocr")

def load_docx_items(path):
    z = zipfile.ZipFile(path)
    xml = z.read("word/document.xml").decode("utf-8")
    rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
    relmap = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))
    items = []
    for m in re.finditer(r"<w:p\b.*?</w:p>|<w:tbl>.*?</w:tbl>", xml, re.S):
        it = m.group(0)
        if it.startswith("<w:p"):
            style = re.search(r'<w:pStyle w:val="([^"]+)"', it)
            text = html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", it))).strip()
            embed = re.search(r'r:embed="(rId\d+)"', it)
            items.append(("p", style.group(1) if style else None,
                          "<w:numPr>" in it,
                          "<w:drawing" in it or "<w:pict" in it, text,
                          embed.group(1) if embed else None))
        else:
            rows = []
            for tr in re.findall(r"<w:tr\b.*?</w:tr>", it, re.S):
                cells = [html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", c))).strip()
                         for c in re.findall(r"<w:tc>.*?</w:tc>", tr, re.S)]
                if any(cells):
                    rows.append(cells)
            items.append(("tbl", rows))
    return items, relmap

items, RELMAP = load_docx_items(DOCX)

def extract_image(target):
    """把 docx 内嵌图片写到 assets/ocr/，返回前端可用相对路径；非位图格式返回 None"""
    ext = target.rsplit(".", 1)[-1].lower() if "." in target else ""
    if ext not in IMG_EXT:
        return None
    fname = os.path.basename(target)
    os.makedirs(OCR_ASSETS, exist_ok=True)
    with zipfile.ZipFile(DOCX) as z:
        blob = z.read("word/" + target)
    with open(os.path.join(OCR_ASSETS, fname), "wb") as f:
        f.write(blob)
    return "assets/ocr/" + fname

# ---------------------------------------------------------------- 抽取目标章节块
BODY_HEAD = {"2": 1, "3": 2, "4": 3}
NUM_RE = re.compile(r"^(第(\d+)章|(\d+(?:\.\d+)*))\s*(.*)$")

# [偏离计划说明] 本手册正文标题的章节号由 Word 自动编号（w:numPr）生成，
# 段落文本中不含 "第1章"/"1.1" 等编号，故计划原逻辑 NUM_RE.match(text) 永远失配。
# 改为：先从目录条目（样式 19/23/12，文本形如 "第1章设备描述14" / "1.1一般数据14"）
# 建立 标题文本→章节号 映射，正文标题段落按文本查表取得章节号。
TOC_STYLE = {"19", "23", "12"}
TOC_NUM = {}
for it in items:
    if it[0] == "p" and it[1] in TOC_STYLE and it[4]:
        tm = NUM_RE.match(it[4])
        if tm:
            title = re.sub(r"\d+$", "", tm.group(4)).strip()   # 去掉目录尾部页码
            if title and title not in TOC_NUM:
                TOC_NUM[title] = tm.group(1)

def in_range(chapter_num):
    """chapter_num 如 '1.2' / '第1章'，顶级章号在 CHAPTER_RANGE 内"""
    m = NUM_RE.match(chapter_num)
    if not m:
        return False
    top = m.group(2) or m.group(3).split(".")[0]
    return top in CHAPTER_RANGE

blocks = []
cur_chapter = None       # 当前小节 num，如 '1.2'
started = False
body_n = 0               # [偏离计划说明] 正文候选计数：第1章前半正文密集而表格靠后
                         # （item 260+），55 块上限内需隔段取样正文才能覆盖多张真实表格；
                         # 含误字源字符（mm/MPa/密封/未/已等）的段落始终保留，
                         # 保证待校对条目能呈现多种注入误字（含中文误字对）
INFORMATIVE = ("m³", "mm", "MPa", "已", "未", "密封")
i = 0
while i < len(items) and len(blocks) < MAX_BLOCKS:
    it = items[i]
    if it[0] == "p":
        _, style, numpr, drawing, text, embed = it
        chap = TOC_NUM.get(text) if (style in BODY_HEAD and numpr and text) else None
        if chap:
            if in_range(chap):
                started = True
                cur_chapter = chap
                blocks.append({"type": "标题", "text": text, "chapter": chap})
            elif started:
                break          # 出范围（第3章起）即停
        elif started and cur_chapter:
            if drawing:
                # 图注：取紧随其后的“图x-x …”段落作为说明
                caption = "插图"
                if i + 1 < len(items):
                    nxt = items[i + 1]
                    if nxt[0] == "p" and re.match(r"^图[\d\-－]", nxt[4] or ""):
                        caption = nxt[4]
                        i += 1   # 图注段落不再单独成块
                blk = {"type": "图片", "text": "图：" + caption, "chapter": cur_chapter}
                if embed and embed in RELMAP:
                    img = extract_image(RELMAP[embed])
                    if img:
                        blk["img"] = img
                blocks.append(blk)
            elif text and len(text) >= 8 and "……" not in text:
                body_n += 1
                if body_n % 2 == 1 or any(s in text for s in INFORMATIVE):
                    blocks.append({"type": "正文", "text": text, "chapter": cur_chapter})
    elif started and cur_chapter:
        rows = it[1]
        if rows:
            head = " | ".join(rows[0])[:60]
            blocks.append({"type": "表格",
                           "text": "表：%s（%d行×%d列）" % (head, len(rows), len(rows[0])),
                           "rows": rows, "chapter": cur_chapter})
    i += 1

assert len(blocks) >= 15, "抽取块数过少（%d），检查章节范围" % len(blocks)
types = {}
for b in blocks:
    types[b["type"]] = types.get(b["type"], 0) + 1
print("抽取块数:", len(blocks), "类型分布:", types)
assert "图片" in types and "表格" in types, "缺少图片或表格块，需扩大章节范围"

# ---------------------------------------------------------------- 状态/置信度 + OCR 误字注入（确定性）
ERRORS = [("m³", "m3"), ("mm", "rnm"), ("MPa", "Mpa"), ("0", "O"),
          ("1", "l"), ("已", "己"), ("未", "末"), ("密封", "蜜封")]

def inject(text, seed):
    # [偏离计划说明] 两遍环形扫描，起始位按 seed 轮换（ERRORS[seed % n] 起）：
    # 第 1 遍只扫非纯数字误字对（m³/mm/MPa/已/未/密封），第 2 遍才兜底 0→O、1→l。
    # 手册数字密集，单遍扫描时数字对总是抢先命中；两遍制保证单位/中文误字
    # （含 已→己/未→末/密封→蜜封）优先生效，同时保留数字误字，全程确定性。
    n = len(ERRORS)
    ring = [(seed + step) % n for step in range(n)]
    for k in ring:
        a, b = ERRORS[k]
        if a not in ("0", "1") and a in text:
            return text.replace(a, b, 1)
    for k in ring:
        a, b = ERRORS[k]
        if a in text:
            return text.replace(a, b, 1)
    return text

for idx, b in enumerate(blocks):
    b["orig"] = b["text"]                     # 注入前原文（已确认块 text==orig 也存，前端统一用 orig 渲染）
    if idx % 5 in (1, 3):                       # 约 40% 待校对
        b["status"] = "待校对"
        b["conf"] = round(0.55 + ((idx * 13) % 39) / 100, 2)
        b["text"] = inject(b["text"], idx)
    else:
        b["status"] = "已确认"
        b["conf"] = round(0.96 + ((idx * 7) % 4) / 100, 2)

# ---------------------------------------------------------------- 流式分页 + bbox 布局
pages, page_no, y, seq = [], 12, 0.06, 0
cur = {"page": page_no, "items": []}
for b in blocks:
    t = b["type"]
    if t == "标题":
        h, w, x = 0.030, min(0.84, 0.14 + len(b["text"]) * 0.013), 0.08
    elif t == "图片":
        h, w, x = 0.17, 0.56, 0.20
    elif t == "表格":
        h, w, x = min(0.42, 0.05 + len(b.get("rows", [])) * 0.032), 0.84, 0.08
    else:
        lines = max(1, (len(b["text"]) + 44) // 45)
        h, w, x = 0.016 + lines * 0.022, 0.84, 0.08
    if y + h > 0.94 and cur["items"]:
        pages.append(cur)
        page_no += 1
        cur, y, seq = {"page": page_no, "items": []}, 0.06, 0
    seq += 1
    b["loc"] = "P%d-%02d" % (page_no, seq)
    b["bbox"] = [round(x, 3), round(y, 3), round(x + w, 3), round(y + h, 3)]
    cur["items"].append(b)
    y = round(y + h + 0.018, 3)
if cur["items"]:
    pages.append(cur)

data = {"doc": "PTR冷却泵设备运行与维修手册（扫描版）", "dpi": 300, "pages": pages}
with open(OUT, "w", encoding="utf-8") as f:
    f.write("/* OCR 校对仿真数据 — 由 tools/build_ocr_mock.py 从真实手册生成，请勿手改 */\n")
    f.write("window.OCR_MOCK = ")
    json.dump(data, f, ensure_ascii=False, indent=1)
    f.write(";\n")
print("页数:", len(pages), "→", OUT)
