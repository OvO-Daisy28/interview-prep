# OCR 校对真实数据化（增量 spec）

日期：2026-08-06
状态：已获用户批准（三个关键决策均选推荐项）
前置：`2026-08-06-ocr-proofread-redesign-design.md`（三栏布局已落地）
范围：新增 `tools/build_ocr_mock.py` + `js/ocr-mock-data.js`；改 `js/pages/parse.js`、`css/main.css`（少量）、`index.html`（一行）

## 需求

1. OCR 校对 mock 数据来自真实文档《PTR冷却泵设备运行与维修手册.docx》（`C:\Users\Lenovo\Desktop\中广核项目\PTR冷却泵POC验证文件\`）
2. 右侧卡片按真实块类型显示：标题 / 正文 / 图片 / 表格
3. 支持「一键确认」（确认全部待校对条目）

## 已确认决策

1. **OCR 误字**：在真实文本上注入典型 OCR 错误（0/O、1/l、mm→rnm、m³→m3、MPa→Mpa、已→己、未→末 等），仅注入到「待校对」条目
2. **一键确认范围**：本文档全部待校对条目
3. **右侧 chips**：改为按类型筛选（全部/标题/正文/图片/表格，带计数）；状态仍以卡片 tag + 框选颜色表达

## 设计

### 数据构建（tools/build_ocr_mock.py → js/ocr-mock-data.js）

- 复用 `build_mock_data.py` 的 docx 解析手法（zipfile + 正则，无第三方依赖）
- 抽取范围：第 1 章（1.1~1.5，含标题/正文/图片/表格全类型），约 25~40 块
- 块类型判定：段落样式 2/3/4 → 标题；含 `<w:drawing` 的段落 → 图片（图注取相邻"图x-x"段落）；`<w:tbl>` → 表格；其余非空段落 → 正文
- 表格 text 摘要：`表：首行…（N行×M列）`；图片 text：图注或「插图」
- 分页：流式布局仿真——按块类型给 bbox 高度（标题矮、正文按字数、图片 0.18、表格按行数），y 超出 0.94 换页；页码从 12 起递增；chapter 记录所属小节 num
- conf/status 确定性分配：约 40% 待校对（conf 0.55~0.94），其余已确认（0.96~0.99）
- 误字注入：仅待校对条目，确定性选取 1~2 处替换
- 输出 `window.OCR_MOCK = { doc, pages }`（doc 名改真实手册名）

### parse.js 改造

- `ocrPages` 改从 `window.OCR_MOCK.pages` 初始化；`ocrDoc` 用真实手册名
- 中间仿真页装饰**由块驱动**（替代写死的 lines/grid）：
  - 标题 → 粗灰条；正文 → 按 bbox 高度铺多条灰条；表格 → 网格矩形；图片 → 虚线图片占位框（图标+「图片」）
  - 上方仍叠加状态色 bbox + 类型/置信度标签
- 右侧 chips 改类型维度：`['全部','标题','正文','图片','表格']`，`ocrCounts` 按类型计数
- 类型 tag 着色：标题 primary / 正文 info / 图片 success / 表格 warning
- 「一键确认」按钮（右栏头部，权限 `can('approve')`）：ElMessageBox.confirm 后把全部待校对 → 已确认
- 移除上一版「筛选下点框选自动切全部」的特殊逻辑（筛选维度变了，点框选时若条目类型不在筛选内，同样自动切回「全部」——逻辑保留、条件改类型）

### index.html

`js/mock-data.js` 之后加 `<script src="js/ocr-mock-data.js"></script>`

### CSS（少量新增）

`.ocr-imgbox`（虚线图片占位框）、`.oc-type-*` 如需。

## 非目标

- 不加载真实扫描图像（仍为 CSS 仿真页）
- 不改 build_mock_data.py 与其他页签

## 校验

跑 `python tools/build_ocr_mock.py` 生成数据；浏览器实测：类型 chips、真实文本+误字、一键确认、双向联动、console 无报错。
