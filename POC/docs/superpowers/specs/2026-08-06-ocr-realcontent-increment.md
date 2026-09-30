# OCR 校对仿真页真实内容化（增量 spec 2）

日期：2026-08-06
状态：用户提出"扫描页预览还是看不到真实内容"，方案已说明并获默认（直接迭代）
前置：`2026-08-06-ocr-realdata-increment.md`

## 需求

仿真扫描页预览要看到真实内容，而不是灰条/占位框。

## 设计

概念对齐真实校对场景：**中间"扫描页"显示原文（正确内容），右侧卡片显示 OCR 识别结果（待校对条目带注入误字）**，人工对照修正。

1. **文字块（标题/正文）**：页内直接渲染真实原文（`orig` 字段），扫描件风格灰色小字；字号用 cqw（`.ocr-paper` 设 `container-type: inline-size`），随缩放自适应
2. **图片块**：从 docx 提取真实嵌入图片（r:embed → document.xml.rels → word/media/*）复制到 `assets/ocr/`，页内 `<img>` 显示；emf/wmf 等浏览器不支持格式回退虚线占位框
3. **表格块**：数据保留真实 `rows` 二维数组，页内渲染迷你表格（真实单元格文字）
4. 框选叠加层与状态着色、右栏卡片（显示含误字的 `text`）不变

## 数据变化（build_ocr_mock.py）

- 每条新增 `orig`（注入前原文）
- 表格块保留 `rows`
- 图片块新增 `img`（assets 相对路径，可显示格式才有）
- 其余不变；确定性不变

## 前端变化（parse.js / main.css）

- 仿真页装饰：`.ocr-txt`（真实文字，标题加粗加大）/ `.ocr-tbl`（迷你表格）/ `.ocr-imgbox img`
- 删除不再用的 `ocrTextLines`、`ocrTableStyle` 及 `.ocr-line`/`.ocr-grid` 样式
- 框选 overlay 不变

## 校验

脚本重跑确定性；浏览器实测：页内可见真实文字/图片/表格、缩放清晰、联动/修正/一键确认回归、console 无报错。
