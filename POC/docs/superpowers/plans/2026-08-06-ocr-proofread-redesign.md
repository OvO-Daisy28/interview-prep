# OCR 校对界面重设计实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 parse 页「扫描件 OCR 校对」tab 重做为 MinerU 风格三栏（目录树 / 仿真扫描页+框选 / 条目卡片流），支持双向定位联动与卡片内联修正。

**Architecture:** 纯前端 POC（Vue 3 全局构建 + Element Plus，`index.html` 双击即开，无构建步骤）。改动集中在 `js/pages/parse.js` 的 ocr tab 模板与 setup 逻辑，样式追加到 `css/main.css`（`ocr-` 前缀，复用 `--np-*` 变量与 `panel`/`conf-pill`/`mono` 既有类）。不改共享 store、不动其他 tab。

**Tech Stack:** Vue 3 (global)、Element Plus、原生 CSS。

**设计依据:** `docs/superpowers/specs/2026-08-06-ocr-proofread-redesign-design.md`

**测试说明:** 本仓库无自动化测试设施（纯静态演示页）。每个任务的验证手段为：`node --check` 校验 JS 语法 + 浏览器实测（Task 5）。这替代了 TDD 循环。

---

### Task 1: 新增 ocr- 三栏样式

**Files:**
- Modify: `css/main.css`（文件末尾追加）

- [ ] **Step 1: 追加样式**

在 `css/main.css` 末尾（第 739 行之后）追加：

```css
/* ===================== 扫描件 OCR 校对（MinerU 风格三栏） ===================== */
.ocr-toolbar { display: flex; align-items: center; gap: 14px; padding: 10px 14px; margin-bottom: 10px; flex-wrap: wrap; }
.ocr-toolbar .ot-name { font-weight: 700; color: var(--np-deep); font-size: 13.5px; }
.ocr-toolbar .ot-stats { display: flex; gap: 12px; font-size: 12px; color: var(--np-text-sub); }
.ocr-toolbar .ot-stats b { font-family: var(--np-display); font-size: 14px; }

.ocr-layout { display: grid; grid-template-columns: 210px minmax(0, 1fr) 390px; gap: 12px; align-items: start; }
.ocr-toc { max-height: 560px; overflow: auto; }

.ocr-stage-wrap { min-width: 0; }
.ocr-stage { background: var(--np-surface-soft); border: 1px solid var(--np-border); border-radius: var(--np-radius-sm); height: 470px; overflow: auto; padding: 18px 0; display: flex; justify-content: center; align-items: flex-start; }
.ocr-paper { position: relative; background: #fff; box-shadow: var(--np-shadow-md); aspect-ratio: 1 / 1.414; flex: none; transition: width .15s; }
.ocr-paper .op-head { position: absolute; top: 2%; left: 8%; right: 8%; display: flex; justify-content: space-between; font-size: 10px; color: #9aa8a6; font-family: var(--np-mono); border-bottom: 1px solid #e3eae8; padding-bottom: 3px; }
.ocr-line { position: absolute; left: 8%; height: 1.05%; background: #dfe7e5; border-radius: 2px; }
.ocr-line.strong { background: #c3cfcc; height: 1.35%; }
.ocr-grid { position: absolute; border: 1px solid #b9c8c4; background-image: linear-gradient(to right, #cdd8d5 1px, transparent 1px), linear-gradient(to bottom, #cdd8d5 1px, transparent 1px); }

.ocr-box { position: absolute; border: 1.8px solid; border-radius: 3px; cursor: pointer; transition: box-shadow .15s; }
.ocr-box .ob-label { position: absolute; top: -15px; left: -2px; font-size: 9.5px; line-height: 1.2; color: #fff; padding: 1px 5px; border-radius: 3px; white-space: nowrap; font-family: var(--np-mono); }
.ocr-box.st-pending { border-color: var(--np-amber); background: rgba(240, 138, 62, .08); }
.ocr-box.st-pending .ob-label { background: var(--np-amber); }
.ocr-box.st-confirmed { border-color: var(--np-green); background: rgba(22, 133, 108, .06); }
.ocr-box.st-confirmed .ob-label { background: var(--np-green); }
.ocr-box.st-fixed { border-color: var(--np-primary); background: rgba(45, 108, 255, .07); }
.ocr-box.st-fixed .ob-label { background: var(--np-primary); }
.ocr-box.sel { box-shadow: 0 0 0 3px rgba(45, 108, 255, .22), var(--np-shadow-sm); z-index: 2; }

.ocr-ctrls { display: flex; align-items: center; justify-content: center; gap: 8px; padding-top: 8px; }
.ocr-ctrls .oc-page { font-family: var(--np-mono); font-size: 12px; color: var(--np-text-sub); min-width: 44px; text-align: center; }

.ocr-side { display: flex; flex-direction: column; max-height: 560px; }
.ocr-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.ocr-chip { border: 1px solid var(--np-border); background: #fff; border-radius: 20px; padding: 2px 10px; font-size: 12px; cursor: pointer; color: var(--np-text-sub); transition: all .12s; }
.ocr-chip:hover { border-color: var(--np-primary); color: var(--np-primary); }
.ocr-chip.active { background: var(--np-primary); border-color: var(--np-primary); color: #fff; }
.ocr-chip .cnt { font-family: var(--np-display); font-weight: 700; margin-left: 4px; }
.ocr-cards { overflow: auto; flex: 1; display: flex; flex-direction: column; gap: 8px; padding-right: 2px; }
.ocr-card { border: 1px solid var(--np-border); border-left: 3px solid var(--np-border-dark); border-radius: var(--np-radius-sm); padding: 8px 10px; background: #fff; cursor: pointer; transition: box-shadow .15s, border-color .15s; }
.ocr-card:hover { box-shadow: var(--np-shadow-sm); }
.ocr-card.st-pending { border-left-color: var(--np-amber); }
.ocr-card.st-confirmed { border-left-color: var(--np-green); }
.ocr-card.st-fixed { border-left-color: var(--np-primary); }
.ocr-card.sel { border-color: var(--np-primary); box-shadow: 0 0 0 3px rgba(45, 108, 255, .14); }
.ocr-card .oc-head { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; flex-wrap: wrap; }
.ocr-card .oc-text { font-size: 12.5px; line-height: 1.6; color: var(--np-text); }
.ocr-card .oc-foot { display: flex; align-items: center; gap: 6px; margin-top: 6px; }
.ocr-card .oc-meta { margin-left: auto; font-size: 11px; color: var(--np-text-sub); font-family: var(--np-mono); }
```

- [ ] **Step 2: Commit**

```bash
git add css/main.css
git commit -m "OCR校对: 新增三栏布局样式（仿真页/框选/卡片流）"
```

---

### Task 2: 重写 OCR mock 数据（4 页 + bbox + 仿真行）

**Files:**
- Modify: `js/pages/parse.js`（替换 setup() 中 `/* ---------- 扫描件 OCR 逐条校对 ---------- */` 段落的数据部分，原 770-785 行）

- [ ] **Step 1: 替换数据**

将 `parse.js` 中：

```js
    /* ---------- 扫描件 OCR 逐条校对 ---------- */
    const ocrDoc = { name: 'RRI冷却泵EOMM（扫描版）' };
    const ocrPages = ref([
      { dpi: 300, items: [
        { loc: 'P48-A1', text: '额定流量 640 m³/h', conf: 0.99, status: '已确认' },
        { loc: 'P48-A2', text: '额定扬程 36 m', conf: 0.97, status: '已确认' },
        { loc: 'P48-B1', text: '转速 1480 r/min', conf: 0.62, status: '待校对' },
        { loc: 'P48-B2', text: '入口压力 0.1~0.21 MPa(g)', conf: 0.71, status: '待校对' },
        { loc: 'P48-C1', text: '轴承型号 6308 ZZ', conf: 0.88, status: '待校对' },
      ]},
      { dpi: 300, items: [
        { loc: 'P72-A1', text: '叶轮直径 410 mm', conf: 0.98, status: '已确认' },
        { loc: 'P72-A2', text: '机械密封型号 MG-12', conf: 0.93, status: '已确认' },
        { loc: 'P72-B1', text: '联轴器膜片厚度 0.3 mm', conf: 0.59, status: '待校对' },
      ]},
    ]);
```

整体替换为：

```js
    /* ---------- 扫描件 OCR 校对（三栏：目录 / 仿真页框选 / 条目卡片） ---------- */
    const ocrDoc = { name: 'RRI冷却泵EOMM（扫描版）' };
    // 仿真页文字行（灰色条），y/w 为相对页高/页宽的比例
    function mkLines(startY, n, gap = 0.034) {
      const ws = [0.84, 0.78, 0.84, 0.62, 0.84, 0.71, 0.84, 0.55, 0.80, 0.84, 0.66, 0.84];
      const arr = [];
      for (let i = 0; i < n; i++) arr.push({ y: +(startY + i * gap).toFixed(3), w: ws[i % ws.length], strong: i === 0 });
      return arr;
    }
    // bbox: [x1, y1, x2, y2] 归一化坐标；chapter 关联 tocTree 节点 num，用于目录跳转
    const ocrPages = ref([
      { page: 48, dpi: 300, chapter: '1.2',
        lines: [...mkLines(0.06, 6), ...mkLines(0.72, 5)],
        grid: { x: 0.08, y: 0.30, w: 0.84, h: 0.36, cols: 4, rows: 5 },
        items: [
          { loc: 'P48-A1', text: '额定流量 640 m³/h', conf: 0.99, status: '已确认', type: '参数', bbox: [0.10, 0.315, 0.46, 0.368] },
          { loc: 'P48-A2', text: '额定扬程 36 m', conf: 0.97, status: '已确认', type: '参数', bbox: [0.54, 0.315, 0.90, 0.368] },
          { loc: 'P48-B1', text: '转速 1480 r/min', conf: 0.62, status: '待校对', type: '参数', bbox: [0.10, 0.387, 0.46, 0.440] },
          { loc: 'P48-B2', text: '入口压力 0.1~0.21 MPa(g)', conf: 0.71, status: '待校对', type: '参数', bbox: [0.54, 0.387, 0.90, 0.440] },
          { loc: 'P48-C1', text: '轴承型号 6308 ZZ', conf: 0.88, status: '待校对', type: '参数', bbox: [0.10, 0.459, 0.46, 0.512] },
        ] },
      { page: 49, dpi: 300, chapter: '1.5',
        lines: [...mkLines(0.06, 4), ...mkLines(0.64, 5)],
        grid: { x: 0.08, y: 0.24, w: 0.84, h: 0.34, cols: 3, rows: 5 },
        items: [
          { loc: 'P49-A1', text: 'M20 螺栓 拧紧力矩 55 N·m', conf: 0.98, status: '已确认', type: '表格行', bbox: [0.10, 0.308, 0.90, 0.374] },
          { loc: 'P49-B1', text: 'M16 螺栓 拧紧力矩 32 N·m', conf: 0.68, status: '待校对', type: '表格行', bbox: [0.10, 0.376, 0.90, 0.442] },
          { loc: 'P49-C1', text: '注意：紧固后复查力矩并记录。', conf: 0.91, status: '待校对', type: '段落', bbox: [0.08, 0.674, 0.66, 0.708] },
        ] },
      { page: 72, dpi: 300, chapter: '2.3',
        lines: [...mkLines(0.06, 5), ...mkLines(0.58, 6)],
        grid: { x: 0.08, y: 0.28, w: 0.84, h: 0.24, cols: 3, rows: 4 },
        items: [
          { loc: 'P72-A1', text: '叶轮直径 410 mm', conf: 0.98, status: '已确认', type: '参数', bbox: [0.10, 0.295, 0.46, 0.354] },
          { loc: 'P72-A2', text: '机械密封型号 MG-12', conf: 0.93, status: '已确认', type: '参数', bbox: [0.54, 0.295, 0.90, 0.354] },
          { loc: 'P72-B1', text: '联轴器膜片厚度 0.3 mm', conf: 0.59, status: '待校对', type: '参数', bbox: [0.10, 0.415, 0.46, 0.474] },
        ] },
      { page: 96, dpi: 300, chapter: '3.7',
        lines: [...mkLines(0.06, 4), ...mkLines(0.70, 4)],
        grid: { x: 0.08, y: 0.24, w: 0.84, h: 0.40, cols: 5, rows: 6 },
        items: [
          { loc: 'P96-A1', text: '机械密封组件 MG-12 · Q1 · 5年', conf: 0.96, status: '已确认', type: '表格行', bbox: [0.10, 0.306, 0.90, 0.372] },
          { loc: 'P96-B1', text: '驱动端轴承 6308 ZZ · Q3 · 8年', conf: 0.66, status: '待校对', type: '表格行', bbox: [0.10, 0.374, 0.90, 0.440] },
          { loc: 'P96-B2', text: '联轴器膜片 MF-300 · Q2 · 10年', conf: 0.57, status: '待校对', type: '表格行', bbox: [0.10, 0.442, 0.90, 0.508] },
        ] },
    ]);
```

- [ ] **Step 2: 语法校验**

Run: `node --check js/pages/parse.js`
Expected: 无输出（退出码 0）

- [ ] **Step 3: Commit**

```bash
git add js/pages/parse.js
git commit -m "OCR校对: mock数据扩至4页，补bbox/仿真行/章节关联"
```

---

### Task 3: 重写 OCR tab 模板为三栏布局

**Files:**
- Modify: `js/pages/parse.js`（替换模板中 OCR tab-pane，原 381-428 行）

- [ ] **Step 1: 替换模板**

将模板中从 `<!-- ========== 扫描件 OCR 逐条校对 ========== -->` 到对应 `</el-tab-pane>` 的整段，替换为：

```html
      <!-- ========== 扫描件 OCR 校对（三栏：目录 / 仿真页框选 / 条目卡片） ========== -->
      <el-tab-pane name="ocr">
        <template #label>扫描件 OCR 校对 <el-badge v-if="ocrPending" :value="ocrPending" type="warning" style="margin-left:4px" /></template>

        <!-- 顶栏：文档 + 统计 + 操作 -->
        <div class="panel ocr-toolbar">
          <span class="ot-name">{{ ocrDoc.name }}</span>
          <span class="ot-stats">
            <span>识别 <b>{{ ocrTotal }}</b></span>
            <span style="color:var(--np-success)">已处理 <b>{{ ocrDone }}</b></span>
            <span style="color:var(--np-warn)">待校对 <b>{{ ocrPending }}</b></span>
            <span :style="'color:' + (ocrAcc >= 95 ? 'var(--np-success)' : 'var(--np-warn)')">准确率 <b>{{ ocrAcc }}%</b><small> ≥95%</small></span>
          </span>
          <span style="margin-left:auto; display:flex; gap:6px;">
            <el-button size="small" icon="DocumentChecked" @click="msg('保存校对进度')">保存</el-button>
            <el-button size="small" type="primary" icon="Download" @click="msg('导出校对结果')">导出</el-button>
          </span>
        </div>

        <div class="ocr-layout">
          <!-- 左：目录树（点章节跳扫描页） -->
          <div class="panel ocr-toc">
            <div class="panel-title"><span>目录</span><span class="pt-badge">{{ ocrPages.length }} 页扫描件</span></div>
            <el-tree :data="tocTree" :props="{label:'label'}" default-expand-all highlight-current
                     :expand-on-click-node="false" @node-click="onOcrTocNode">
              <template #default="{data}"><span style="font-size:12px;">{{ data.label }}</span></template>
            </el-tree>
          </div>

          <!-- 中：仿真扫描页 + 状态框选 -->
          <div class="panel ocr-stage-wrap">
            <div class="panel-title">
              <span>扫描页预览 · 第 {{ ocrPageData.page }} 页</span>
              <span class="pt-badge">{{ ocrPageData.dpi }} DPI · 框选按状态着色</span>
            </div>
            <div class="ocr-stage" ref="ocrStageEl">
              <div class="ocr-paper" :style="ocrPaperStyle">
                <div class="op-head"><span>{{ ocrDoc.name }}</span><span>- {{ ocrPageData.page }} -</span></div>
                <div v-for="(l, i) in ocrPageData.lines" :key="'l'+i" class="ocr-line" :class="{strong: l.strong}" :style="ocrLineStyle(l)"></div>
                <div v-if="ocrPageData.grid" class="ocr-grid" :style="ocrGridStyle(ocrPageData.grid)"></div>
                <div v-for="it in ocrPageData.items" :key="it.loc" class="ocr-box" :data-oid="it.loc"
                     :class="[ocrStatusCls(it.status), { sel: ocrSelId === it.loc }]"
                     :style="ocrBoxStyle(it)" :title="it.loc + ' · ' + it.type + ' · 置信度 ' + (it.conf*100).toFixed(0) + '%'"
                     @click="onOcrBoxClick(it)">
                  <span class="ob-label">{{ it.type }} {{ (it.conf*100).toFixed(0) }}%</span>
                </div>
              </div>
            </div>
            <div class="ocr-ctrls">
              <el-button size="small" circle icon="Minus" @click="ocrZoomBy(-0.15)" />
              <span class="oc-page">{{ Math.round(ocrZoom*100) }}%</span>
              <el-button size="small" circle icon="Plus" @click="ocrZoomBy(0.15)" />
              <span style="width:16px"></span>
              <el-button size="small" circle icon="ArrowLeft" :disabled="ocrPage<=1" @click="ocrGoto(ocrPage-1)" />
              <span class="oc-page">{{ ocrPage }} / {{ ocrPages.length }}</span>
              <el-button size="small" circle icon="ArrowRight" :disabled="ocrPage>=ocrPages.length" @click="ocrGoto(ocrPage+1)" />
            </div>
          </div>

          <!-- 右：条目卡片流（chips 筛选 + 内联修正） -->
          <div class="panel ocr-side">
            <div class="panel-title"><span>识别条目</span><span class="sub-text">点击卡片 / 框选双向定位</span></div>
            <div class="ocr-chips">
              <button v-for="c in ['全部','待校对','已修正','已确认']" :key="c" class="ocr-chip"
                      :class="{active: ocrFilter===c}" @click="ocrFilter=c">{{ c }}<span class="cnt">{{ ocrCounts[c] }}</span></button>
            </div>
            <div class="ocr-cards" ref="ocrCardsEl">
              <div v-for="w in ocrShownItems" :key="w.it.loc" class="ocr-card" :data-oid="w.it.loc"
                   :class="[ocrStatusCls(w.it.status), { sel: ocrSelId === w.it.loc }]" @click="selectOcr(w)">
                <div class="oc-head">
                  <el-tag size="small" effect="plain" class="mono">{{ w.it.loc }}</el-tag>
                  <el-tag size="small" type="info" effect="plain">{{ w.it.type }}</el-tag>
                  <span class="conf-pill" :class="confType(w.it.conf)">{{ (w.it.conf*100).toFixed(0) }}%</span>
                  <el-tag size="small" :type="w.it.status==='已确认'?'success':(w.it.status==='已修正'?'primary':'warning')">{{ w.it.status }}</el-tag>
                </div>
                <div v-if="ocrEditId !== w.it.loc" class="oc-text">{{ w.it.text }}</div>
                <el-input v-else v-model="ocrEditText" type="textarea" :rows="2" @click.stop />
                <div class="oc-foot">
                  <template v-if="ocrEditId === w.it.loc">
                    <el-button size="small" type="primary" @click.stop="ocrSaveEdit(w.it)">保存修正</el-button>
                    <el-button size="small" @click.stop="ocrCancelEdit">取消</el-button>
                  </template>
                  <template v-else-if="w.it.status === '待校对'">
                    <el-button size="small" type="success" :disabled="!can('approve')" @click.stop="ocrConfirm(w.it)">确认</el-button>
                    <el-button size="small" type="warning" plain :disabled="!can('edit')" @click.stop="ocrStartEdit(w.it)">修正</el-button>
                  </template>
                  <el-tag v-else size="small" effect="dark" :type="w.it.status==='已确认'?'success':'primary'">已处理</el-tag>
                  <span class="oc-meta">第 {{ ocrPages[w.pageIdx].page }} 页</span>
                </div>
              </div>
              <el-empty v-if="!ocrShownItems.length" description="当前筛选无条目" :image-size="70" />
            </div>
          </div>
        </div>
        <el-alert type="info" :closable="false" show-icon style="margin-top:10px"
          title="修正差异将记录于「AI 结果与人工修正差异库」，用于 OCR 模型微调与准确率统计；原文图像与识别文本、修正文本一一映射，可追溯。" />
      </el-tab-pane>
```

- [ ] **Step 2: 语法校验**

Run: `node --check js/pages/parse.js`
Expected: 无输出（退出码 0）。注意模板在 JS 模板字符串内，`node --check` 只能查 JS 语法，模板错误在 Task 5 浏览器验证。

- [ ] **Step 3: Commit**

```bash
git add js/pages/parse.js
git commit -m "OCR校对: tab模板改为三栏（目录/仿真页框选/卡片流）"
```

---

### Task 4: 重写 setup() 中的 OCR 交互逻辑

**Files:**
- Modify: `js/pages/parse.js`（替换 Task 2 数据段之后的旧逻辑与 return 导出）

- [ ] **Step 1: 替换逻辑代码**

将 Task 2 新数据段之后、到 `/* ---------- 专用表格清单解析 ---------- */` 之前的旧逻辑（原 `const ocrPage = ref(1);` … `ocrFix` 函数整段），替换为：

```js
    const ocrPage = ref(1);
    const ocrZoom = ref(1);
    const ocrSelId = ref(null);      // 当前选中条目 loc（卡片 ↔ 框选双向联动）
    const ocrFilter = ref('全部');
    const ocrEditId = ref(null);     // 内联修正中的条目 loc
    const ocrEditText = ref('');
    const ocrStageEl = ref(null);
    const ocrCardsEl = ref(null);

    const ocrTotal = computed(() => ocrPages.value.reduce((s, p) => s + p.items.length, 0));
    const ocrDone = computed(() => ocrPages.value.reduce((s, p) => s + p.items.filter(i => i.status !== '待校对').length, 0));
    const ocrPending = computed(() => ocrPages.value.reduce((s, p) => s + p.items.filter(i => i.status === '待校对').length, 0));
    const ocrAcc = computed(() => ocrTotal.value ? Math.round(ocrDone.value / ocrTotal.value * 1000) / 10 : 0);
    const ocrPageData = computed(() => ocrPages.value[ocrPage.value - 1]);
    const ocrCounts = computed(() => ({
      全部: ocrTotal.value,
      待校对: ocrPending.value,
      已修正: ocrPages.value.reduce((s, p) => s + p.items.filter(i => i.status === '已修正').length, 0),
      已确认: ocrPages.value.reduce((s, p) => s + p.items.filter(i => i.status === '已确认').length, 0),
    }));
    // 包装 {it, pageIdx}：保持条目引用（内联编辑直接改 it 才响应式），并携带页码用于跳页
    const ocrAllItems = computed(() => ocrPages.value.flatMap((p, pi) => p.items.map(it => ({ it, pageIdx: pi }))));
    const ocrShownItems = computed(() => ocrAllItems.value.filter(w => ocrFilter.value === '全部' || w.it.status === ocrFilter.value));

    function ocrBoxStyle(it) {
      const [x1, y1, x2, y2] = it.bbox;
      return { left: x1 * 100 + '%', top: y1 * 100 + '%', width: (x2 - x1) * 100 + '%', height: (y2 - y1) * 100 + '%' };
    }
    function ocrLineStyle(l) { return { top: l.y * 100 + '%', width: l.w * 100 + '%' }; }
    function ocrGridStyle(g) {
      return { left: g.x * 100 + '%', top: g.y * 100 + '%', width: g.w * 100 + '%', height: g.h * 100 + '%',
               backgroundSize: (100 / g.cols) + '% 100%, 100% ' + (100 / g.rows) + '%' };
    }
    function ocrStatusCls(s) { return { 待校对: 'st-pending', 已确认: 'st-confirmed', 已修正: 'st-fixed' }[s]; }
    const ocrPaperStyle = computed(() => ({ width: (62 * ocrZoom.value) + '%' }));
    function ocrZoomBy(d) { ocrZoom.value = Math.min(1.6, Math.max(0.7, +(ocrZoom.value + d).toFixed(2))); }
    function ocrGoto(p) { ocrPage.value = Math.min(ocrPages.value.length, Math.max(1, p)); }

    // 双向联动：选中条目 → 跳页 + 框选/卡片同时滚动定位
    function selectOcr(w) {
      ocrSelId.value = w.it.loc;
      if (ocrPage.value !== w.pageIdx + 1) ocrPage.value = w.pageIdx + 1;
      nextTick(() => {
        const box = ocrStageEl.value && ocrStageEl.value.querySelector('[data-oid="' + w.it.loc + '"]');
        if (box) box.scrollIntoView({ block: 'center', behavior: 'smooth' });
        const card = ocrCardsEl.value && ocrCardsEl.value.querySelector('[data-oid="' + w.it.loc + '"]');
        if (card) card.scrollIntoView({ block: 'center', behavior: 'smooth' });
      });
    }
    function onOcrBoxClick(it) {
      const w = ocrAllItems.value.find(x => x.it === it);
      if (w) selectOcr(w);
    }
    // 目录树跳页：先精确匹配 num（如 1.2），章级节点（第1章）匹配同章第一页
    function onOcrTocNode(data) {
      if (!data.num) return;
      let idx = ocrPages.value.findIndex(p => p.chapter === data.num);
      if (idx < 0) {
        const m = String(data.num).match(/^第?(\d+)/);
        if (m) idx = ocrPages.value.findIndex(p => p.chapter.split('.')[0] === String(+m[1]));
      }
      if (idx >= 0) ocrGoto(idx + 1);
      else ElementPlus.ElMessage.info('该章节暂无扫描页（演示仅 ' + ocrPages.value.length + ' 页）');
    }

    function ocrConfirm(it) { it.status = '已确认'; ElementPlus.ElMessage.success('已确认 ' + it.loc); }
    function ocrStartEdit(it) { ocrEditId.value = it.loc; ocrEditText.value = it.text; }
    function ocrCancelEdit() { ocrEditId.value = null; }
    function ocrSaveEdit(it) {
      if (ocrEditText.value && ocrEditText.value !== it.text) {
        it.text = ocrEditText.value; it.conf = 1; it.status = '已修正';
        ElementPlus.ElMessage.success('OCR 修正已记录，差异入库用于模型优化');
      }
      ocrEditId.value = null;
    }
```

注意：原 `ocrConfirm(row)`/`ocrFix(row)` 整段删除（含旧 `ocrTotal/ocrDone/ocrPending/ocrAcc` 定义，已被上面新版本替代——确认不重复定义）。

- [ ] **Step 2: 更新 return 导出**

把 setup() return 对象中的：

```js
      ocrDoc, ocrPages, ocrPage, ocrTotal, ocrDone, ocrPending, ocrAcc, ocrConfirm, ocrFix,
```

替换为：

```js
      ocrDoc, ocrPages, ocrPage, ocrTotal, ocrDone, ocrPending, ocrAcc,
      ocrZoom, ocrSelId, ocrFilter, ocrEditId, ocrEditText, ocrStageEl, ocrCardsEl,
      ocrPageData, ocrCounts, ocrShownItems,
      ocrBoxStyle, ocrLineStyle, ocrGridStyle, ocrStatusCls, ocrPaperStyle,
      ocrZoomBy, ocrGoto, selectOcr, onOcrBoxClick, onOcrTocNode,
      ocrConfirm, ocrStartEdit, ocrSaveEdit, ocrCancelEdit,
```

- [ ] **Step 3: 语法校验 + 检查无残留引用**

```bash
node --check js/pages/parse.js
grep -n "ocrFix" js/pages/parse.js
```
Expected: `node --check` 无输出；grep 无匹配（ocrFix 已彻底移除）。

- [ ] **Step 4: Commit**

```bash
git add js/pages/parse.js
git commit -m "OCR校对: 交互逻辑重写（双向联动/内联修正/缩放翻页/目录跳页）"
```

---

### Task 5: 浏览器实测验证

**Files:** 无改动，仅验证。

- [ ] **Step 1: 启动本地服务并打开页面**

```bash
cd "C:/Users/Lenovo/Desktop/中广核项目/POC" && python -m http.server 8017
```
用 webapp-testing / Playwright 打开 `http://localhost:8017/index.html`（file:// 亦可，但 http 更接近真实加载）。

- [ ] **Step 2: 逐项核对（进入 内容解析 → 扫描件 OCR 校对 tab）**

- 三栏布局正常：左目录树 / 中仿真页（灰条+表格网格+彩色框选带标签）/ 右卡片流
- tab 徽标显示待校对数 8；顶栏统计 识别14·已处理6·待校对8·准确率42.9%
- 点右侧卡片 → 中间跳到对应页、框选高亮；点中间框选 → 右侧卡片高亮滚动定位
- chips 筛选「待校对」→ 只剩 8 张卡片；「全部」恢复 14
- 待校对卡片点「修正」→ 内联 textarea，改字保存 → 状态变「已修正」、框选变蓝、准确率上升
- 「确认」→ 状态变绿、统计更新
- 缩放 −/+（70%~160%）与翻页 ‹ ›（1~4 页）正常
- 左目录点「1.2」/「第1章」→ 跳到第 1 页；点无扫描页章节 → info 提示
- 浏览器 console 无报错

- [ ] **Step 3: 关闭服务，若有问题修复后复测，最终 Commit（如有修复）**

---

## Self-Review 记录

- **Spec 覆盖**：三栏布局(T3)、仿真页+框选(T1/T2/T3)、目录树(T3/T4)、chips 筛选(T3/T4)、内联修正(T3/T4)、双向联动(T4)、缩放翻页(T3/T4)、顶栏统计+保存导出演示(T3)、底部说明条(T3)、准确率口径(T4 ocrAcc 沿用) — 全覆盖。
- **占位符**：无；所有代码完整给出。
- **命名一致性**：模板引用 `ocrPageData/ocrCounts/ocrShownItems/ocrBoxStyle/ocrLineStyle/ocrGridStyle/ocrStatusCls/ocrPaperStyle/ocrZoomBy/ocrGoto/selectOcr/onOcrBoxClick/onOcrTocNode/ocrConfirm/ocrStartEdit/ocrSaveEdit/ocrCancelEdit/ocrZoom/ocrSelId/ocrFilter/ocrEditId/ocrEditText/ocrStageEl/ocrCardsEl` 与 Task 4 定义及 return 导出逐一核对一致。旧引用 `ocrFix` 已删除并在 Task 4 Step 3 用 grep 验证。`confType`/`can`/`msg`/`tocTree`/`nextTick` 均为 parse.js 既有导出/导入。
