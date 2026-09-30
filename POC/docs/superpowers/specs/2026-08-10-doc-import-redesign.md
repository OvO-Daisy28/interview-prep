# 文档导入与预处理重新设计（design spec）

日期：2026-08-10
状态：已获用户批准（4 个澄清问题均已确认）
范围：`js/mock-data.js`（docTree/docs 升级）、`js/app.js`（可编辑 docTree + helper）、`js/pages/parse.js`（导入页签重写）、`css/main.css`（imp- 样式）

## 需求（用户原文 4 点）

1. 多级目录，目录下的目录和文件都能随意拖动、切换目录、删除、新建、修改名字
2. 主页面导入文档列表，可按目录、元数据、文档名称搜索
3. 文档状态（进行中/排队中/失败/停止/完成）可见，每状态计数可见，点击状态筛选该状态文档
4. 每个文档的解析子步骤（OCR/结构化/embedding/实体关系抽取/LLM抽取），每步可见状态、处理时间、进度

## 已确认决策

1. **子步骤呈现**：行内迷你流水线 + 点击行展开详情（信息密度高，主列表不臃肿）
2. **目录拖拽**：全交互，演示级持久（会话内 store 生效，刷新复位）
3. **状态口径**：5 态——完成 / 进行中 / 排队 / 失败 / 停止
4. **目录数据源**：升级共享 `NP.store.docTree` 为可编辑多级树（项目→区域→设备→文档叶子），其他页面仍能消费

## 布局

导入页签内：左目录树（span 6）+ 右主区（span 18）。右主区自上而下：
搜索栏 → 状态分组 chip 栏 → 批量处理监控卡（保留）→ 批量操作栏 → 文档表格（含行内流水线列 + 展开详情）。

## 组件设计

### ① 多级目录全交互（app.js + mock-data.js + parse.js）

- `docTree` 升级为带稳定 `id` 的多级结构：项目 → 区域 → 设备 → **文档叶子**（文档挂到设备节点下，`docId` 关联 docs）。既有中间节点保留 `filter:{equipment}` 供其他页面（解析结果 cascader、数据库）消费；新增 `id` 字段不破坏既有消费方（它们按 label/filter 读取）。
- `el-tree` 配置：`draggable`、`node-key="id"`、`:allow-drop`（禁止把节点拖入文档叶子内部）、`@node-drop` 更新 store。
- 节点操作：树节点 `#default` slot 内悬浮显示操作按钮——文件夹节点有 ➕新建子文件夹 / ✏️重命名 / 🗑️删除；文档叶子有 ✏️重命名 / 🗑️删除。顶部面板标题保留 ➕新建根级文件夹。
- app.js 提供 helper（挂在 window.NP 下）：`treeAddNode(parentId, node)`、`treeRenameNode(id, label)`、`treeRemoveNode(id)`、`treeFindNode(id)`、`treeMoveNode`（node-drop 时 el-tree 已就地改数组，helper 仅做校验/计数刷新）。docTree 改为 `Vue.reactive` 保证响应式。
- 演示级持久：改动写入 store，当前会话内所有消费方生效；刷新复位（mock 重新加载）。

### ② 文档列表搜索（parse.js）

- 目录过滤：点树节点 → `folderFilter` 记录选中节点 id；`filteredDocs` 按"该节点子树下的所有 docId"递归匹配（文件夹节点收集子树全部文档，设备节点收集其下文档，文档叶子定位单份）。
- 搜索栏：名称关键词（`q.kw`）+ 设备（`q.equipment`）+ 厂家（`q.mfr`）+ 类型（`q.type`）下拉 + 重置。下拉选项从 docs 去重（`equipOptions/mfrOptions/typeOptions`）。
- 三维度叠加：目录过滤 ∧ 搜索栏 ∧ 状态 chip（③）共同作用于 `filteredDocs`。

### ③ 状态分组带计数可点筛选（parse.js + mock-data.js）

- docs 状态归一为 5 态常量：`完成 / 进行中 / 排队 / 失败 / 停止`。
- 状态派生：文档整体 `status` 由 `steps` 推导——全部 done→完成；任一 running/断点→进行中；任一 failed→失败；全 queued→排队；含 stopped 且无 running→停止。用 `docStatus(doc)` 计算并写回 `doc.status`，或直接 computed 呈现。
- 状态栏：5 个彩色 chip，每个显示 `标签 计数`（如 `完成 12`）。点击 chip → `statusFilter` 设为该状态并过滤；再点同一 chip → 清除。与搜索/目录叠加。计数基于"目录+搜索过滤后"的集合还是全量？→ 基于全量 docs（反映总体态势），点击后再叠加搜索/目录过滤结果显示在表格。
- chip 配色：完成绿 / 进行中蓝 / 排队灰 / 失败红 / 停止橙，选中态高亮。

### ④ 每文档 5 子步骤（mock-data.js + parse.js + css）

- 每个 doc 加 `steps` 数组，5 步固定顺序：
  `[{key:'ocr',label:'OCR',...},{key:'struct',label:'结构化'},{key:'embed',label:'Embedding'},{key:'entity',label:'实体关系'},{key:'llm',label:'LLM抽取'}]`
  每步字段：`status`（done/running/queued/failed/pending）、`progress`（0-100）、`duration`（如 '2.3s' / '—'）。
- 表格「解析流水线」列：行内迷你流水线——5 个小节点横排，节点间连线；按 status 着色：done=绿✓ / running=蓝◐（显示 progress）/ queued=灰⋯ / failed=红✗ / pending=空心—。悬浮 title 显示该步 `label · 状态 · 进度/耗时`。
- 点击表格行展开（el-table `expand` 列或行点击 toggle）：展开区列出 5 步详情——每步一行：图标+标签、状态 tag、进度条（running 显示 progress）、处理耗时。
- OCR 完成的文档，展开详情里 OCR 步骤"查看校对"入口可跳 OCR 校对 tab（复用现有 tab 切换，非必须，作演示增强）。

### 数据变化（mock-data.js）

- `docTree`：升级为带 id + 文档叶子的多级结构（保留 filter 中间节点）。
- `docs`：扩到约 18~24 份（覆盖 5 态与多设备/厂家/类型，让分组和搜索有料）；每条加 `steps`（5 步）、`type`（Word/PDF/PDF扫描件/Excel 等，用于类型搜索）、状态归一为 5 态。真实文件名沿用现有 + 合理扩充（同设备多文档）。
- 保留 `batch`（批量监控卡）数据。

### app.js 变化

- `store.docTree` 从普通数组改为 `Vue.reactive` 包裹（若已在 reactive store 内则确保深响应）。
- 新增 tree helper 函数（见①）。
- 不动其他 store 字段与 helper。

### css/main.css 变化

新增 `imp-` 前缀样式：`.imp-status-bar`/`.imp-chip`（5 态配色+选中态）、`.imp-pipe`（行内流水线容器）、`.imp-node`（节点+状态修饰 done/running/queued/failed/pending）、`.imp-pipe-line`（连线）、`.imp-expand`（展开详情区）、`.imp-step-row`（步骤行）、`.imp-tree-ops`（树节点悬浮操作）。沿用 `--np-*` 变量。

## 跨页影响（docTree 升级的连带处理）

共享 `docTree` 现有消费方：`database.js`（左目录树，line 10）、`parse.js` 解析结果页的 cascader（line 150，项目→设备选择）。加入文档叶子后：
- `database.js` 树会显示文档叶子——可接受（数据库按设备+文档定位本就合理），无需改。
- `parse.js` review cascader 用于选"项目→设备"，出现文档叶子会显得杂乱——cascader 用 `checkStrictly`，实现时在 cascader 层过滤掉文档叶子节点（用 `:props` 或预处理一份"仅文件夹"的树给 cascader）。
- 计数字段 `count`：文件夹节点 count 改为"子树文档数"动态计算，避免手工维护不一致。

## 非目标

- 不做真实文件上传/后端；导入为动画模拟（沿用现有 startImport 手法）
- 不改其他页签（解析结果/OCR校对/增量重解析/专用表格）功能，仅确保 docTree 升级后它们仍能消费
- 拖拽不做跨会话持久化

## 校验

POC 无自动化测试。实现后浏览器实测：
- 目录树拖拽移动、新建/重命名/删除文件夹与文档、切换目录过滤
- 搜索栏目录+设备+厂家+类型+名称叠加过滤、重置
- 状态 5 chip 计数正确、点击筛选、再点取消、与搜索叠加
- 行内流水线 5 节点按状态着色、展开看 5 步状态/进度/耗时
- 回归：解析结果 cascader、数据库页目录消费正常
- console 无报错
