# OCR 校对真实数据化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OCR 校对 mock 数据切换为真实手册《PTR冷却泵设备运行与维修手册.docx》抽取内容，右侧按真实块类型（标题/正文/图片/表格）展示与筛选，支持一键确认全部待校对。

**Architecture:** 新增 `tools/build_ocr_mock.py`（复用 build_mock_data.py 的 docx 解析手法，无第三方依赖）生成 `js/ocr-mock-data.js`（`window.OCR_MOCK`）；`parse.js` 的 OCR tab 改消费该数据，仿真页装饰由块类型驱动；`index.html` 加一行 script；`css/main.css` 加图片占位框样式。

**Tech Stack:** Python 3（开发期脚本）、Vue 3 (global)、Element Plus、原生 CSS。

**设计依据:** `docs/superpowers/specs/2026-08-06-ocr-realdata-increment.md`

**测试说明:** 无自动化测试设施。脚本任务验证 = 运行脚本并检查输出统计；前端任务验证 = `node --check` + Task 3 浏览器实测。

---

### Task 1: 真实数据抽取脚本 + 生成数据

**Files:**
- Create: `tools/build_ocr_mock.py`
- Create: `js/ocr-mock-data.js`（脚本生成）

- [ ] **Step 1: 编写脚本**

创建 `tools/build_ocr_mock.py`，完整内容：

```python
# -*- coding: utf-8 -*-
"""
build_ocr_mock.py — 从 PTR 冷却泵真实手册构建 OCR 校对仿真数据
运行: python tools/build_ocr_mock.py
输出: POC/js/ocr-mock-data.js  (window.OCR_MOCK = {...})
仅在开发期运行，演示不需要 Python。
"""
import zipfile, re, json, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"C:\Users\Lenovo\Desktop\中广核项目\PTR冷却泵POC验证文件"
DOCX = os.path.join(SRC, "PTR冷却泵设备运行与维修手册.docx")
OUT = os.path.join(BASE, "js", "ocr-mock-data.js")

MAX_BLOCKS = 40          # 总块数上限（约 5~6 个仿真页）
CHAPTER_RANGE = ("1", "2")  # 抽取第1、2章（含标题/正文/图片/表格全类型）

# ---------------------------------------------------------------- docx 解析（与 build_mock_data.py 同手法）
def load_docx_items(path):
    z = zipfile.ZipFile(path)
    xml = z.read("word/document.xml").decode("utf-8")
    items = []
    for m in re.finditer(r"<w:p\b.*?</w:p>|<w:tbl>.*?</w:tbl>", xml, re.S):
        it = m.group(0)
        if it.startswith("<w:p"):
            style = re.search(r'<w:pStyle w:val="([^"]+)"', it)
            text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", it)).strip()
            items.append(("p", style.group(1) if style else None,
                          "<w:numPr>" in it,
                          "<w:drawing" in it or "<w:pict" in it, text))
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

# ---------------------------------------------------------------- 抽取目标章节块
BODY_HEAD = {"2": 1, "3": 2, "4": 3}
NUM_RE = re.compile(r"^(第(\d+)章|(\d+(?:\.\d+)*))\s*(.*)$")

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
i = 0
while i < len(items) and len(blocks) < MAX_BLOCKS:
    it = items[i]
    if it[0] == "p":
        _, style, numpr, drawing, text = it
        m = NUM_RE.match(text) if (style in BODY_HEAD and numpr and text) else None
        if m:
            chap = m.group(1)
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
                blocks.append({"type": "图片", "text": "图：" + caption, "chapter": cur_chapter})
            elif text and len(text) >= 8 and "……" not in text:
                blocks.append({"type": "正文", "text": text, "chapter": cur_chapter})
    elif started and cur_chapter:
        rows = it[1]
        if rows:
            head = " | ".join(rows[0])[:60]
            blocks.append({"type": "表格",
                           "text": "表：%s（%d行×%d列）" % (head, len(rows), len(rows[0])),
                           "rows": len(rows), "chapter": cur_chapter})
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
    for k, (a, b) in enumerate(ERRORS):
        if (seed + k) % 3 == 0 and a in text:
            return text.replace(a, b, 1)
    return text

for idx, b in enumerate(blocks):
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
        h, w, x = min(0.42, 0.05 + b.get("rows", 4) * 0.032), 0.84, 0.08
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
    b.pop("rows", None)
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
```

- [ ] **Step 2: 运行并检查输出**

```bash
cd "C:/Users/Lenovo/Desktop/中广核项目/POC" && python tools/build_ocr_mock.py
```
Expected: 打印「抽取块数: ≥15，类型分布含 标题/正文/图片/表格 四类」与「页数: 4~7」。若 assert 失败（块数过少或缺类型），把 `CHAPTER_RANGE` 扩为 `("1", "2", "3")` 重跑。

- [ ] **Step 3: 抽查生成数据**

读 `js/ocr-mock-data.js` 前 60 行确认：text 为真实手册内容、待校对条目含注入误字（如 rnm/Mpa/己/末）、bbox 均在 0~1 且递增不重叠。

- [ ] **Step 4: Commit**

```bash
git add tools/build_ocr_mock.py js/ocr-mock-data.js
git commit -m "OCR校对: 真实手册抽取脚本 + 生成数据（标题/正文/图片/表格+误字注入）"
```

---

### Task 2: parse.js 消费真实数据 + 类型驱动渲染 + 一键确认

**Files:**
- Modify: `js/pages/parse.js`
- Modify: `index.html`（mock-data.js 后加一行）
- Modify: `css/main.css`（追加图片占位框样式）

- [ ] **Step 1: index.html 加脚本引用**

`index.html` 第 19 行 `<script src="js/mock-data.js"></script>` 之后插入：

```html
<script src="js/ocr-mock-data.js"></script>
```

- [ ] **Step 2: CSS 追加**

`css/main.css` 末尾追加：

```css
.ocr-imgbox { position: absolute; border: 1.5px dashed #b9c8c4; border-radius: 4px; background: #f4f8f7; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; color: #9aa8a6; font-size: 11px; }
```

- [ ] **Step 3: parse.js 数据段替换**

把 OCR 数据段（`/* ---------- 扫描件 OCR 校对（三栏…） ---------- */` 注释起，含 `mkLines` 函数与 4 页 `ocrPages` 字面量，到 `]);` 止）整体替换为：

```js
    /* ---------- 扫描件 OCR 校对（真实手册数据：标题/正文/图片/表格） ---------- */
    const ocrDoc = { name: window.OCR_MOCK.doc, dpi: window.OCR_MOCK.dpi };
    const ocrPages = ref(window.OCR_MOCK.pages);
```

- [ ] **Step 4: parse.js 逻辑调整**

4a. `ocrCounts` 改为按类型计数，替换整个定义为：

```js
    const ocrCounts = computed(() => {
      const c = { 全部: ocrTotal.value, 标题: 0, 正文: 0, 图片: 0, 表格: 0 };
      ocrPages.value.forEach(p => p.items.forEach(i => { c[i.type] = (c[i.type] || 0) + 1; }));
      return c;
    });
```

4b. `ocrShownItems` 筛选条件由状态改类型：

```js
    const ocrShownItems = computed(() => ocrAllItems.value.filter(w => ocrFilter.value === '全部' || w.it.type === ocrFilter.value));
```

4c. `ocrFilter` 初始值保持 `'全部'` 不变。

4d. 删除 `ocrLineStyle` 与 `ocrGridStyle` 两个函数（仿真页装饰改由块驱动，不再需要）。

4e. 新增文本行铺排、类型着色与一键确认函数（加在 `ocrBoxStyle` 之后）：

```js
    // 文本块装饰：把 bbox 区域铺成 n 条灰条（标题 1 条粗条；正文按高度铺多行，末行缩短）
    function ocrTextLines(it) {
      const [x1, y1, x2, y2] = it.bbox;
      const h = y2 - y1;
      const n = it.type === '标题' ? 1 : Math.max(1, Math.round(h / 0.024));
      const gap = h / n;
      const arr = [];
      for (let i = 0; i < n; i++) {
        arr.push({
          top: (y1 + i * gap + gap * 0.25) * 100 + '%',
          left: x1 * 100 + '%',
          width: ((i === n - 1 && n > 1 ? 0.62 : 1) * (x2 - x1)) * 100 + '%',
          height: gap * 0.45 * 100 + '%',
        });
      }
      return arr;
    }
    function ocrTypeTag(t) { return { 标题: 'primary', 正文: 'info', 图片: 'success', 表格: 'warning' }[t] || 'info'; }
    // 一键确认：全部待校对 → 已确认
    function ocrConfirmAll() {
      ElementPlus.ElMessageBox.confirm('将全部 ' + ocrPending.value + ' 条待校对条目确认为识别无误？', '一键确认', {
        confirmButtonText: '全部确认', cancelButtonText: '取消', type: 'warning',
      }).then(() => {
        ocrPages.value.forEach(p => p.items.forEach(i => { if (i.status === '待校对') i.status = '已确认'; }));
        ElementPlus.ElMessage.success('已一键确认全部待校对条目，准确率已更新');
      }).catch(() => {});
    }
```

4f. `onOcrBoxClick` 的筛选复位条件由状态改类型：

```js
    function onOcrBoxClick(it) {
      const w = ocrAllItems.value.find(x => x.it === it);
      if (!w) return;
      if (ocrFilter.value !== '全部' && it.type !== ocrFilter.value) ocrFilter.value = '全部';
      selectOcr(w);
    }
```

4g. `onOcrTocNode` 改为按条目 chapter 匹配（一页可能跨小节）：

```js
    // 目录树跳页：找第一个包含该章节条目的页（精确 num → 章级回退）
    function onOcrTocNode(data) {
      if (!data.num) return;
      const m = String(data.num).match(/^第?(\d+(?:\.\d+)*)/);
      const want = m ? m[1] : null;
      if (!want) return;
      const hit = (ch) => ch === want || ch.startsWith(want + '.') || want.startsWith(ch + '.') || ch.split('.')[0] === want.split('.')[0];
      const idx = ocrPages.value.findIndex(p => p.items.some(it => hit(it.chapter)));
      if (idx >= 0) ocrGoto(idx + 1);
      else ElementPlus.ElMessage.info('该章节暂无扫描页（演示仅 ' + ocrPages.value.length + ' 页）');
    }
```

4h. return 导出更新：删 `ocrLineStyle, ocrGridStyle,`，在 `ocrBoxStyle,` 后加 `ocrTextLines, ocrTypeTag, ocrConfirmAll,`。

- [ ] **Step 5: parse.js 模板调整**

5a. 仿真页装饰区：把现有三行装饰渲染

```html
                <div v-for="(l, i) in ocrPageData.lines" :key="'l'+i" class="ocr-line" :class="{strong: l.strong}" :style="ocrLineStyle(l)"></div>
                <div v-if="ocrPageData.grid" class="ocr-grid" :style="ocrGridStyle(ocrPageData.grid)"></div>
```

替换为块驱动装饰：

```html
                <template v-for="it in ocrPageData.items" :key="'d'+it.loc">
                  <div v-if="it.type==='表格'" class="ocr-grid" :style="ocrBoxStyle(it)"></div>
                  <div v-else-if="it.type==='图片'" class="ocr-imgbox" :style="ocrBoxStyle(it)">
                    <el-icon :size="22" color="#9aa8a6"><Picture /></el-icon><span>图片</span>
                  </div>
                  <div v-else v-for="(ln, li) in ocrTextLines(it)" :key="'ln'+li" class="ocr-line" :class="{strong: it.type==='标题'}" :style="ln"></div>
                </template>
```

（框选 `ocr-box` 的 v-for 保持不变，仍在装饰之后渲染。）

5b. 面板标题 DPI 改为数据驱动：`{{ ocrPageData.dpi }} DPI · 框选按状态着色` 改为 `{{ ocrDoc.dpi }} DPI · 框选按状态着色`（OCR_MOCK 页级无 dpi 字段）。

5c. 右栏头部加一键确认按钮，把：

```html
            <div class="panel-title"><span>识别条目</span><span class="sub-text">点击卡片 / 框选双向定位</span></div>
```

改为：

```html
            <div class="panel-title"><span>识别条目</span>
              <span style="display:flex; align-items:center; gap:8px;">
                <span class="sub-text">点击卡片 / 框选双向定位</span>
                <el-button size="small" type="success" plain :disabled="!can('approve') || !ocrPending" @click="ocrConfirmAll">一键确认 ({{ ocrPending }})</el-button>
              </span>
            </div>
```

5d. chips 数组 `['全部','待校对','已修正','已确认']` 改为 `['全部','标题','正文','图片','表格']`。

5e. 卡片类型 tag：`<el-tag size="small" type="info" effect="plain">{{ w.it.type }}</el-tag>` 改为 `<el-tag size="small" :type="ocrTypeTag(w.it.type)" effect="plain">{{ w.it.type }}</el-tag>`。

- [ ] **Step 6: 校验**

```bash
node --check js/pages/parse.js
grep -n "ocrLineStyle\|ocrGridStyle\|ocrPageData.lines\|ocrPageData.grid\|mkLines" js/pages/parse.js
```
Expected: node --check 通过；grep 无匹配。

- [ ] **Step 7: Commit**

```bash
git add js/pages/parse.js index.html css/main.css
git commit -m "OCR校对: 消费真实手册数据 + 类型驱动仿真页 + 类型chips + 一键确认"
```

---

### Task 3: 浏览器实测验证

**Files:** 无改动（除非修复）。

- [ ] **Step 1: 启动服务并用 Playwright 打开**

```bash
cd "C:/Users/Lenovo/Desktop/中广核项目/POC" && python -m http.server 8017
```
打开 `http://localhost:8017/index.html` → 内容解析 → 扫描件 OCR 校对 tab。（Playwright chromium 下载慢时复用 `chromium_headless_shell-1223` 的 executable_path。）

- [ ] **Step 2: 逐项核对**

- 文档名为「PTR冷却泵设备运行与维修手册（扫描版）」，页数为脚本生成的页数
- 中间仿真页：标题粗条、正文多行灰条（末行缩短）、表格网格、图片虚线占位框（图标+「图片」）均渲染，互不重叠
- 卡片 text 为真实手册内容；待校对卡片可见注入误字（rnm / Mpa / 己 / 末 / m3 等）
- chips 为 全部/标题/正文/图片/表格 且计数正确；逐个点选筛选正确；卡片类型 tag 着色（标题蓝/正文灰/图片绿/表格橙）
- 点「一键确认 (N)」→ 确认弹窗 → 全部待校对变已确认、chips 上方待校对数清零、框选全变绿、准确率 100%
- 重新加载页面，双向联动（卡片↔框选）、内联修正、缩放/翻页、目录跳页（点 1.2 / 第1章 / 无扫描页章节提示）均正常
- console 无报错（硬性）

- [ ] **Step 3: 有问题修复复测并单独 commit；杀服务；git status 干净**

---

## Self-Review 记录

- **Spec 覆盖**：真实数据（T1）、真实类型展示+chips（T2 4a/4b/5d/5e）、误字注入（T1 ERRORS）、一键确认（T2 4e/5c）、类型驱动仿真页（T2 5a/4e）— 全覆盖。
- **占位符**：无；脚本与全部前端改动完整给出。
- **命名一致性**：模板引用 `ocrTextLines/ocrTypeTag/ocrConfirmAll/ocrDoc.dpi`，逻辑段定义且 return 导出（4h）；删除的 `ocrLineStyle/ocrGridStyle` 在 Step 6 grep 验证无残留。`Picture` 图标已全局注册（ElementPlusIconsVue）。T1 数据含 `chapter/loc/bbox/type/text/conf/status`，与 T2 消费字段一致。
