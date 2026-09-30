# -*- coding: utf-8 -*-
"""
build_mock_data.py — 从 PTR 冷却泵真实手册构建 POC 仿真数据
运行: python tools/build_mock_data.py
输出: POC/js/mock-data.js  (window.MOCK = {...})
仅在开发期运行，演示不需要 Python。
"""
import zipfile, re, json, os, sys, io
import xml.etree.ElementTree as ET

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"C:\Users\Lenovo\Desktop\中广核项目\PTR冷却泵POC验证文件"
DOCX = os.path.join(SRC, "PTR冷却泵设备运行与维修手册.docx")
XLSX = os.path.join(SRC, "PTR冷却泵分解数据结构.xlsx")
OUT = os.path.join(BASE, "js", "mock-data.js")

# ---------------------------------------------------------------- docx 解析
def load_docx_items(path):
    """按文档顺序返回 [('p', style, numpr, text) | ('tbl', rows)] """
    z = zipfile.ZipFile(path)
    xml = z.read("word/document.xml").decode("utf-8")
    items = []
    for m in re.finditer(r"<w:p\b.*?</w:p>|<w:tbl>.*?</w:tbl>", xml, re.S):
        it = m.group(0)
        if it.startswith("<w:p"):
            style = re.search(r'<w:pStyle w:val="([^"]+)"', it)
            text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", it)).strip()
            items.append(("p", style.group(1) if style else None,
                          "<w:numPr>" in it, text))
        else:
            rows = []
            for tr in re.findall(r"<w:tr\b.*?</w:tr>", it, re.S):
                cells = ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", c)).strip()
                         for c in re.findall(r"<w:tc>.*?</w:tc>", tr, re.S)]
                if any(cells):
                    rows.append(cells)
            items.append(("tbl", rows))
    return items

items = load_docx_items(DOCX)

# ---------------------------------------------------------------- 目录树(取自真实目录, 位于正文之前)
# TOC 段落样式(19/23/12)只出现在目录中，正文标题用样式 2/3/4，直接全文扫描
body_start = next(i for i, it in enumerate(items)
                  if it[0] == "p" and it[1] == "2" and it[2] and it[3])
TOC_LVL = {"19": 1, "23": 2, "12": 3}
toc_entries = []          # (level, number, title)
for it in items:
    if it[0] == "p" and it[1] in TOC_LVL and it[3]:
        t = re.sub(r"\s*\d+$", "", it[3])          # 去掉页码
        m = re.match(r"^(第[\d]+章|[\d.]+)\s*(.*)$", t)
        if m and m.group(2):
            toc_entries.append((TOC_LVL[it[1]], m.group(1), m.group(2)))

def build_tree(entries):
    root, stack = [], {}
    for lvl, num, title in entries:
        node = {"num": num, "title": title, "label": f"{num} {title}",
                "level": lvl, "children": []}
        if lvl == 1:
            root.append(node)
        elif (lvl - 1) in stack:
            stack[lvl - 1]["children"].append(node)
        stack[lvl] = node
    return root

toc_tree = build_tree(toc_entries)

# ---------------------------------------------------------------- 正文标题定位(与目录顺序对齐)
flat_titles = [t for _, _, t in toc_entries]
flat_nums = [n for _, n, _ in toc_entries]
flat_lvls = [l for l, _, _ in toc_entries]

BODY_HEAD = {"2": 1, "3": 2, "4": 3}
tagged = []            # (kind, payload, chapter_path)
ptr = 0
cur_path = []          # [(level, num, title)]
misses = 0
for it in items[body_start:]:
    if it[0] == "p" and it[2] and it[1] in BODY_HEAD and it[3]:
        title = re.sub(r"\s+", "", it[3])
        found = None
        for j in range(ptr, min(ptr + 10, len(flat_titles))):
            if re.sub(r"\s+", "", flat_titles[j]) == title:
                found = j
                break
        if found is not None:
            ptr = found + 1
            lvl = flat_lvls[found]
            cur_path = cur_path[:lvl - 1] + [(lvl, flat_nums[found], flat_titles[found])]
        else:
            misses += 1
        continue
    path = "/".join(f"{n}{t}" for _, n, t in cur_path)
    if it[0] == "p":
        if it[3]:
            tagged.append(("p", it[3], path))
    else:
        tagged.append(("tbl", it[1], path))

print(f"目录条目 {len(toc_entries)}，正文标题未匹配 {misses}，标注段落/表格 {len(tagged)}")

def in_chapter(path, prefixes):
    segs = path.split("/")
    return any(seg.startswith(p) for seg in segs for p in prefixes)

# ---------------------------------------------------------------- 内容块切分(重点章节全量)
TARGET_CHAPTERS = ["0.4", "1.2", "2.3", "3.7"]
SAFETY = {"注意": "注意", "警告": "警告", "危险": "危险"}

def classify(text):
    head = text[:2]
    if head in SAFETY:
        return "注意事项", SAFETY[head]
    if re.match(r"^[（(]?\d+[）)]", text):
        return "操作步骤", None
    if re.search(r"(必须|不得|严禁|应当|禁止)", text):
        return "技术要求", None
    return "描述说明", None

blocks = []
bid = 0

def add_block(text, path):
    global bid
    ctype, slevel = classify(text)
    is_common = bool(re.search(r"(人员资格|安全操作说明|防护装置|资质)", text[:40])) or \
        path.split("/")[-1].startswith("0.4")
    bid += 1
    blocks.append({
        "id": f"CB-{bid:04d}", "chapterPath": path,
        "section": path.split("/")[-1] if path else "",
        "contentType": ctype, "safetyLevel": slevel,
        "content": text,
        "source": {"doc": "PTR冷却泵设备运行与维修手册.docx",
                   "chapter": path.split("/")[-1] if path else ""},
        "aiConfidence": round(0.85 + (bid * 7 % 14) * 0.01, 2),
        "reviewStatus": "待审核" if bid % 11 == 0 else "已确认",
        "isCommon": is_common,
        "version": 1, "relations": [],
    })

for kind, payload, path in tagged:
    if not in_chapter(path, TARGET_CHAPTERS):
        continue
    if kind == "p":
        if len(payload) >= 6:
            add_block(payload, path)
    else:
        rows = payload
        if len(rows) == 1 and len(rows[0]) == 1 and rows[0][0][:2] in SAFETY:
            add_block(rows[0][0], path)

print(f"内容块 {len(blocks)} 个")

# ---------------------------------------------------------------- 参数提取(规则化模式, 协同LLM场景由演示说明)
PARAM_PATTERNS = [
    ("额定流量", r"额定流量[:：]?\s*(\d+(?:\.\d+)?)\s*(m3/h|m³/h)", "性能参数", "泵本体"),
    ("额定扬程", r"额定扬程[:：]?\s*(\d+(?:\.\d+)?)\s*m\b", "性能参数", "泵本体"),
    ("额定转速", r"额定转速[:：]?\s*(\d+)\s*r/\s*min", "性能参数", "泵本体"),
    ("有效汽蚀余量", r"有效汽蚀余量[:：]?\s*(\d+(?:\.\d+)?)\s*m\b", "性能参数", "泵本体"),
    ("入口压力", r"入口压力[:：]?\s*([\d.~]+)\s*MPa(\(g\))?", "介质参数", "泵本体"),
    ("额定电压", r"额定电压[:：]?\s*(\d+)\s*V", "电气参数", "电机"),
    ("额定频率", r"额定频(?:率|为)[:：]?\s*(\d+)\s*Hz", "电气参数", "电机"),
    ("同步转速", r"同步转速[:：]?\s*(\d+)\s*r/min", "电气参数", "电机"),
    ("电机功率", r"功率[:：为]?\s*(\d+)\s*[kK][wW]", "电气参数", "电机"),
    ("电机极数", r"极数[:：为]?\s*(\d+)\s*极", "电气参数", "电机"),
    ("介质密度", r"密度[:：]?\s*(\d+(?:\.\d+)?)\s*kg/m3", "介质参数", "泵本体"),
    ("工作介质温度", r"(?:介质)?温度[:：]?\s*(\d+(?:\.\d+)?)\s*℃", "介质参数", "泵本体"),
]

params, pid = [], 0
seen = set()
full_text = [(p, path) for k, p, path in tagged if k == "p"]
for text, path in full_text:
    for name, pat, cat, comp in PARAM_PATTERNS:
        for m in re.finditer(pat, text):
            value = m.group(1)
            key = (name, value)
            if key in seen:
                continue
            seen.add(key)
            pid += 1
            unit = {"额定流量": "m³/h", "额定扬程": "m", "额定转速": "r/min",
                    "有效汽蚀余量": "m", "入口压力": "MPa(g)", "额定电压": "V",
                    "额定频率": "Hz", "同步转速": "r/min", "电机功率": "kW",
                    "电机极数": "极", "介质密度": "kg/m³", "工作介质温度": "℃"}[name]
            cond = "表压基准(g)" if name == "入口压力" and "(g)" in text[max(0, m.start()-5):m.end()+8] else None
            params.append({
                "id": f"P-{pid:04d}", "name": name, "value": value, "unit": unit,
                "category": cat, "component": comp, "condition": cond,
                "source": path or "第1章设备描述/1.1一般数据",
                "aiConfidence": round(0.94 + (pid % 5) * 0.012, 2),
            })
            break  # 每个参数名每段只取一次
params.sort(key=lambda p: p["name"])
for i, p in enumerate(params, 1):
    p["id"] = f"P-{i:04d}"
# 复合描述拆分示例(需求点名场景), 固定置顶展示
compound_demo = {"sentence": "额定流量640m³/h，额定扬程36m",
                 "results": [{"name": "额定流量", "value": "640", "unit": "m³/h"},
                             {"name": "额定扬程", "value": "36", "unit": "m"}]}
print(f"参数 {len(params)} 条")

# ---------------------------------------------------------------- 特征表格
def find_table(header_kw=None, chapter_prefix=None, min_rows=2):
    for kind, payload, path in tagged:
        if kind != "tbl" or len(payload) < min_rows:
            continue
        if chapter_prefix and not in_chapter(path, chapter_prefix):
            continue
        # 表头定位: 第一行多列的行
        hdr_idx = next((i for i, r in enumerate(payload[:3]) if len(r) > 1), None)
        if hdr_idx is None:
            continue
        hdr = "|".join(payload[hdr_idx])
        if header_kw and not all(k in hdr for k in header_kw):
            continue
        return {"chapterPath": path, "header": payload[hdr_idx],
                "title": payload[0][0] if len(payload[0]) == 1 else None,
                "rows": payload[hdr_idx + 1: hdr_idx + 16]}
    return None

tables = {
    "paramTable": find_table(["项目", "参数", "单位"], ["1.1"]),
    "deviceCodeTable": find_table(["名称", "型号"], ["0.6"]),
    "torqueTable": find_table(["拧紧力矩"], ["1.5.14", "4."]),
    "faultTable": find_table(["故障"], ["2.3", "4."], min_rows=5),
    "spareTable": find_table(["备件名称"], None),
    "spareTable2": find_table(["物项中文描述", "备件型号"], None),
    "standardTable": find_table(["标准"], ["0.9"]),
}
for k, v in tables.items():
    print(f"表格 {k}: {'OK ' + str(len(v['rows'])) + '行' if v else '未找到'}")

# ---------------------------------------------------------------- DMC 编码映射
def load_dmc(path):
    z = zipfile.ZipFile(path)
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    ss = []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    for si in root.findall(ns + "si"):
        ss.append("".join(t.text or "" for t in si.iter(ns + "t")))
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sheet.iter(ns + "row"):
        vals = []
        for c in row.findall(ns + "c"):
            v = c.find(ns + "v")
            if v is None:
                vals.append("")
            elif c.get("t") == "s":
                vals.append(ss[int(v.text)])
            else:
                vals.append(v.text)
        rows.append(vals)
    mapping = {}
    for r in rows:
        if len(r) >= 3 and r[0].startswith("HPR1000"):
            mapping[r[-1].strip()] = r[0].strip()
    return mapping

dmc_map = load_dmc(XLSX)
print(f"DMC 编码 {len(dmc_map)} 条")

def find_dmc(block):
    path = block["chapterPath"]
    for info, dmc in dmc_map.items():
        if info and info in path:
            return dmc
    for info, dmc in dmc_map.items():
        if info and len(info) >= 4 and any(info in seg or (len(seg) > 4 and seg in info) for seg in path.split("/")):
            return dmc
    return None

for b in blocks:
    b["dmc"] = find_dmc(b) or "HPR1000-A-45-20-0000-00A-XXX-D(待分配)"

# 去重: 内容完全相同的块只保留第一个(内容去重能力在治理页另行演示)
seen_content = set()
deduped = []
for b in blocks:
    if b["content"] in seen_content:
        continue
    seen_content.add(b["content"])
    deduped.append(b)
blocks = deduped
# 重新编号并预置部分"已修正"块, 使初始 AI 准确率 ≈96%(避免 100% 显得不真实)
for i, b in enumerate(blocks, 1):
    b["id"] = f"CB-{i:04d}"
    b["reviewStatus"] = "已修正" if i % 26 == 0 else ("待审核" if i % 11 == 0 else "已确认")
print(f"去重后内容块 {len(blocks)} 个")

# ---------------------------------------------------------------- 汇总输出
MOCK = {
    "meta": {
        "project": "采购文件活化平台 POC",
        "equipment": "PTR冷却泵",
        "equipmentCode": "HPR1000-A-45-20-0000-00A",
        "nuclearLevel": "核安全3级", "qaLevel": "QA1", "seismic": "抗震I类",
        "manufacturer": "重庆水泵厂有限责任公司(CQPI)",
    },
    "tocTree": toc_tree,
    "blocks": blocks,
    "params": params,
    "compoundDemo": compound_demo,
    "tables": tables,
    "dmcCount": len(dmc_map),
}
const_path = os.path.join(BASE, "tools", "mock_constants.json")
MOCK.update(json.loads(open(const_path, encoding="utf-8").read()))

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// 由 tools/build_mock_data.py 生成，请勿手改\n")
    f.write("window.MOCK = ")
    f.write(json.dumps(MOCK, ensure_ascii=False, indent=1))
    f.write(";\n")
print("输出:", OUT, os.path.getsize(OUT), "bytes")
