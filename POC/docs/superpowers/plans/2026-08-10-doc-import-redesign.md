# 文档导入与预处理重新设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重做「文档导入与预处理」页签——多级目录可拖拽/增删改/重命名，文档列表按目录+元数据+名称搜索，5 态分组带计数可点筛选，每文档 5 个解析子步骤（OCR/结构化/Embedding/实体关系/LLM抽取）行内流水线 + 展开详情。

**Architecture:** 纯前端 POC（Vue 3 全局 + Element Plus，`index.html` 双击即开，无构建步骤）。数据层：扩充 `js/mock-data.js` 的 `docs` 块（加 steps/归一状态）、升级 `js/app.js` 的 `store.docTree` 为带 id 的可编辑多级树（含文档叶子）+ tree helper。视图层：`js/pages/parse.js` 导入页签模板与 setup 重写，`css/main.css` 加 `imp-` 样式。

**Tech Stack:** Vue 3 (global)、Element Plus（el-tree draggable / el-table expand）、原生 CSS。

**设计依据:** `docs/superpowers/specs/2026-08-10-doc-import-redesign.md`

**测试说明:** 本仓库无自动化测试设施（纯静态演示页）。每个前端任务的验证 = `node --check <file>` 校验 JS 语法 + 浏览器实测（Task 5）。这替代 TDD 循环。

## 文件职责

- `js/mock-data.js` — `docs` 块：从 5 份扩到 20 份，每份加 `steps`（5 步）、归一 `status`（5 态），补 `type`。
- `js/app.js` — `store.docTree` 升级为带 `id` 的多级树（项目→区域→设备→文档叶子）；新增 `window.NP.tree*` helper（增删改查/计数）。
- `js/pages/parse.js` — 导入页签模板 + setup：树交互（拖拽/增删改）、目录+元数据+名称搜索、状态 chip、行内流水线列 + 展开详情。
- `css/main.css` — `imp-` 前缀样式（状态 chip / 行内流水线 / 展开详情 / 树节点悬浮操作）。

## 状态与子步骤口径（全任务共用，先读）

**5 态常量**：`完成` / `进行中` / `排队` / `失败` / `停止`

**子步骤 status 取值**：`done`（完成）/ `running`（进行中）/ `queued`（排队）/ `failed`（失败）/ `pending`（未开始）

**文档整体状态派生规则**（`docStatus(steps)`，Task 1 定义、Task 4 复用）：
1. 任一步 `failed` → `失败`
2. 否则任一步 `running` → `进行中`
3. 否则全部 `done` → `完成`
4. 否则任一步 `stopped`→ `停止`（注：steps 无 stopped 值时此分支不触发，停止态由 doc 级 `stopped:true` 标志表达，见 Task 1）
5. 否则 → `排队`

为简化，Task 1 直接给每份 doc 写好最终 `status` 字段（与其 steps 自洽），`docStatus` 仅用于导入动画后重算。停止态用 doc 的 `status:'停止'` 直接表达。

---

### Task 1: 扩充 docs mock 数据（20 份 + steps + 5 态）

**Files:**
- Modify: `js/mock-data.js`（替换 `"docs": [ ... ]` 整个数组，当前约 3013 行起）

- [ ] **Step 1: 替换 docs 数组**

先 Read `js/mock-data.js` 定位 `"docs": [` 到其闭合 `]`（下一个键是 `"params"` 或类似；用 Read 确认闭合位置）。将整个 `docs` 数组值替换为下面 20 份。每份字段：`id/name/type/equipment/manufacturer/pages/status/progress/steps`。`steps` 固定 5 步顺序，每步 `{key,label,status,progress,duration}`。

> 说明：JSON 块直接写字面量。5 步的 `key` 恒为 `ocr/struct/embed/entity/llm`，`label` 恒为 `OCR识别/结构化/Embedding/实体关系/LLM抽取`。`duration` 用字符串（完成步为耗时如 `"2.3s"`，未开始/排队为 `"—"`，进行中为已耗时如 `"1.8s"`）。

```json
  "docs": [
   { "id": "D-001", "name": "PTR冷却泵设备运行与维修手册.docx", "type": "Word", "equipment": "PTR冷却泵", "manufacturer": "重庆水泵厂(CQPI)", "pages": 86, "status": "完成", "progress": 100,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"12.4s"},
       {"key":"embed","label":"Embedding","status":"done","progress":100,"duration":"8.1s"},
       {"key":"entity","label":"实体关系","status":"done","progress":100,"duration":"6.7s"},
       {"key":"llm","label":"LLM抽取","status":"done","progress":100,"duration":"21.3s"}
     ] },
   { "id": "D-002", "name": "PTR冷却泵安装调试记录.docx", "type": "Word", "equipment": "PTR冷却泵", "manufacturer": "重庆水泵厂(CQPI)", "pages": 34, "status": "完成", "progress": 100,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"5.2s"},
       {"key":"embed","label":"Embedding","status":"done","progress":100,"duration":"3.4s"},
       {"key":"entity","label":"实体关系","status":"done","progress":100,"duration":"2.9s"},
       {"key":"llm","label":"LLM抽取","status":"done","progress":100,"duration":"9.8s"}
     ] },
   { "id": "D-003", "name": "PTR冷却泵备件清单.xlsx", "type": "Excel", "equipment": "PTR冷却泵", "manufacturer": "重庆水泵厂(CQPI)", "pages": 12, "status": "进行中", "progress": 55,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"3.1s"},
       {"key":"embed","label":"Embedding","status":"running","progress":58,"duration":"2.0s"},
       {"key":"entity","label":"实体关系","status":"queued","progress":0,"duration":"—"},
       {"key":"llm","label":"LLM抽取","status":"queued","progress":0,"duration":"—"}
     ] },
   { "id": "D-004", "name": "RRI冷却泵设备运行与维修手册.docx", "type": "Word", "equipment": "RRI冷却泵", "manufacturer": "重庆水泵厂(CQPI)", "pages": 79, "status": "进行中", "progress": 62,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"11.0s"},
       {"key":"embed","label":"Embedding","status":"running","progress":40,"duration":"3.2s"},
       {"key":"entity","label":"实体关系","status":"queued","progress":0,"duration":"—"},
       {"key":"llm","label":"LLM抽取","status":"queued","progress":0,"duration":"—"}
     ] },
   { "id": "D-005", "name": "RRI冷却泵技术规格书.pdf", "type": "PDF", "equipment": "RRI冷却泵", "manufacturer": "重庆水泵厂(CQPI)", "pages": 28, "status": "进行中", "progress": 30,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"running","progress":48,"duration":"4.5s"},
       {"key":"embed","label":"Embedding","status":"queued","progress":0,"duration":"—"},
       {"key":"entity","label":"实体关系","status":"queued","progress":0,"duration":"—"},
       {"key":"llm","label":"LLM抽取","status":"queued","progress":0,"duration":"—"}
     ] },
   { "id": "D-006", "name": "CEF补水泵运行维修手册(扫描版).pdf", "type": "PDF扫描件", "equipment": "CEF补水泵", "manufacturer": "上海凯泉", "pages": 64, "status": "进行中", "progress": 18,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"running","progress":72,"duration":"14.2s"},
       {"key":"struct","label":"结构化","status":"queued","progress":0,"duration":"—"},
       {"key":"embed","label":"Embedding","status":"queued","progress":0,"duration":"—"},
       {"key":"entity","label":"实体关系","status":"queued","progress":0,"duration":"—"},
       {"key":"llm","label":"LLM抽取","status":"queued","progress":0,"duration":"—"}
     ] },
   { "id": "D-007", "name": "CEF补水泵采购技术规格书.docx", "type": "Word", "equipment": "CEF补水泵", "manufacturer": "上海凯泉", "pages": 22, "status": "完成", "progress": 100,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"4.0s"},
       {"key":"embed","label":"Embedding","status":"done","progress":100,"duration":"2.6s"},
       {"key":"entity","label":"实体关系","status":"done","progress":100,"duration":"2.1s"},
       {"key":"llm","label":"LLM抽取","status":"done","progress":100,"duration":"7.4s"}
     ] },
   { "id": "D-008", "name": "ASG辅助给水泵维修手册.pdf", "type": "PDF", "equipment": "ASG辅助给水泵", "manufacturer": "沈阳鼓风机集团", "pages": 112, "status": "排队", "progress": 0,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"queued","progress":0,"duration":"—"},
       {"key":"struct","label":"结构化","status":"queued","progress":0,"duration":"—"},
       {"key":"embed","label":"Embedding","status":"queued","progress":0,"duration":"—"},
       {"key":"entity","label":"实体关系","status":"queued","progress":0,"duration":"—"},
       {"key":"llm","label":"LLM抽取","status":"queued","progress":0,"duration":"—"}
     ] },
   { "id": "D-009", "name": "ASG辅助给水泵结构图纸.pdf", "type": "PDF", "equipment": "ASG辅助给水泵", "manufacturer": "沈阳鼓风机集团", "pages": 45, "status": "排队", "progress": 0,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"queued","progress":0,"duration":"—"},
       {"key":"struct","label":"结构化","status":"queued","progress":0,"duration":"—"},
       {"key":"embed","label":"Embedding","status":"queued","progress":0,"duration":"—"},
       {"key":"entity","label":"实体关系","status":"queued","progress":0,"duration":"—"},
       {"key":"llm","label":"LLM抽取","status":"queued","progress":0,"duration":"—"}
     ] },
   { "id": "D-010", "name": "ASG辅助给水泵试验报告(扫描版).pdf", "type": "PDF扫描件", "equipment": "ASG辅助给水泵", "manufacturer": "沈阳鼓风机集团", "pages": 18, "status": "失败", "progress": 40,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"failed","progress":40,"duration":"6.0s"},
       {"key":"struct","label":"结构化","status":"pending","progress":0,"duration":"—"},
       {"key":"embed","label":"Embedding","status":"pending","progress":0,"duration":"—"},
       {"key":"entity","label":"实体关系","status":"pending","progress":0,"duration":"—"},
       {"key":"llm","label":"LLM抽取","status":"pending","progress":0,"duration":"—"}
     ] },
   { "id": "D-011", "name": "RCV上充泵设备运行与维修手册.docx", "type": "Word", "equipment": "RCV上充泵", "manufacturer": "Flowserve", "pages": 95, "status": "完成", "progress": 100,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"13.7s"},
       {"key":"embed","label":"Embedding","status":"done","progress":100,"duration":"9.0s"},
       {"key":"entity","label":"实体关系","status":"done","progress":100,"duration":"7.2s"},
       {"key":"llm","label":"LLM抽取","status":"done","progress":100,"duration":"24.1s"}
     ] },
   { "id": "D-012", "name": "RCV上充泵密封件图册.pdf", "type": "PDF", "equipment": "RCV上充泵", "manufacturer": "Flowserve", "pages": 40, "status": "失败", "progress": 75,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"6.3s"},
       {"key":"embed","label":"Embedding","status":"done","progress":100,"duration":"4.1s"},
       {"key":"entity","label":"实体关系","status":"failed","progress":30,"duration":"2.2s"},
       {"key":"llm","label":"LLM抽取","status":"pending","progress":0,"duration":"—"}
     ] },
   { "id": "D-013", "name": "RCV上充泵备件清单.xlsx", "type": "Excel", "equipment": "RCV上充泵", "manufacturer": "Flowserve", "pages": 8, "status": "停止", "progress": 20,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"stopped","progress":35,"duration":"1.5s"},
       {"key":"embed","label":"Embedding","status":"pending","progress":0,"duration":"—"},
       {"key":"entity","label":"实体关系","status":"pending","progress":0,"duration":"—"},
       {"key":"llm","label":"LLM抽取","status":"pending","progress":0,"duration":"—"}
     ] },
   { "id": "D-014", "name": "主给水泵机组运行手册.docx", "type": "Word", "equipment": "主给水泵", "manufacturer": "哈尔滨电气", "pages": 130, "status": "完成", "progress": 100,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"18.0s"},
       {"key":"embed","label":"Embedding","status":"done","progress":100,"duration":"11.5s"},
       {"key":"entity","label":"实体关系","status":"done","progress":100,"duration":"9.4s"},
       {"key":"llm","label":"LLM抽取","status":"done","progress":100,"duration":"30.2s"}
     ] },
   { "id": "D-015", "name": "主给水泵振动分析报告.pdf", "type": "PDF", "equipment": "主给水泵", "manufacturer": "哈尔滨电气", "pages": 26, "status": "进行中", "progress": 80,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"4.8s"},
       {"key":"embed","label":"Embedding","status":"done","progress":100,"duration":"3.0s"},
       {"key":"entity","label":"实体关系","status":"running","progress":66,"duration":"2.4s"},
       {"key":"llm","label":"LLM抽取","status":"queued","progress":0,"duration":"—"}
     ] },
   { "id": "D-016", "name": "凝结水泵检修工艺规程.docx", "type": "Word", "equipment": "凝结水泵", "manufacturer": "上海电气", "pages": 58, "status": "完成", "progress": 100,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"8.6s"},
       {"key":"embed","label":"Embedding","status":"done","progress":100,"duration":"5.5s"},
       {"key":"entity","label":"实体关系","status":"done","progress":100,"duration":"4.3s"},
       {"key":"llm","label":"LLM抽取","status":"done","progress":100,"duration":"15.9s"}
     ] },
   { "id": "D-017", "name": "凝结水泵电机说明书(扫描版).pdf", "type": "PDF扫描件", "equipment": "凝结水泵", "manufacturer": "上海电气", "pages": 33, "status": "排队", "progress": 0,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"queued","progress":0,"duration":"—"},
       {"key":"struct","label":"结构化","status":"queued","progress":0,"duration":"—"},
       {"key":"embed","label":"Embedding","status":"queued","progress":0,"duration":"—"},
       {"key":"entity","label":"实体关系","status":"queued","progress":0,"duration":"—"},
       {"key":"llm","label":"LLM抽取","status":"queued","progress":0,"duration":"—"}
     ] },
   { "id": "D-018", "name": "余热排出泵运行维修手册.docx", "type": "Word", "equipment": "余热排出泵", "manufacturer": "大连深蓝泵业", "pages": 71, "status": "进行中", "progress": 45,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"9.9s"},
       {"key":"embed","label":"Embedding","status":"running","progress":52,"duration":"3.6s"},
       {"key":"entity","label":"实体关系","status":"queued","progress":0,"duration":"—"},
       {"key":"llm","label":"LLM抽取","status":"queued","progress":0,"duration":"—"}
     ] },
   { "id": "D-019", "name": "余热排出泵采购合同附件.pdf", "type": "PDF", "equipment": "余热排出泵", "manufacturer": "大连深蓝泵业", "pages": 15, "status": "停止", "progress": 0,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"stopped","progress":10,"duration":"0.8s"},
       {"key":"struct","label":"结构化","status":"pending","progress":0,"duration":"—"},
       {"key":"embed","label":"Embedding","status":"pending","progress":0,"duration":"—"},
       {"key":"entity","label":"实体关系","status":"pending","progress":0,"duration":"—"},
       {"key":"llm","label":"LLM抽取","status":"pending","progress":0,"duration":"—"}
     ] },
   { "id": "D-020", "name": "余热排出泵备件清单.xlsx", "type": "Excel", "equipment": "余热排出泵", "manufacturer": "大连深蓝泵业", "pages": 6, "status": "完成", "progress": 100,
     "steps": [
       {"key":"ocr","label":"OCR识别","status":"done","progress":100,"duration":"—"},
       {"key":"struct","label":"结构化","status":"done","progress":100,"duration":"2.2s"},
       {"key":"embed","label":"Embedding","status":"done","progress":100,"duration":"1.4s"},
       {"key":"entity","label":"实体关系","status":"done","progress":100,"duration":"1.1s"},
       {"key":"llm","label":"LLM抽取","status":"done","progress":100,"duration":"4.6s"}
     ] }
  ],
```

注意：替换时保留 `docs` 数组后的逗号与后续键（如 `"params"`）。Excel/PDF扫描件的 OCR 步骤对 Word/Excel 无意义，这里统一保留 5 步、Word/Excel 的 ocr 记为 done/`"—"`（表示无需 OCR，直接通过），扫描件 ocr 有真实耗时——此为演示合理化。

- [ ] **Step 2: 语法校验**

Run: `node --check js/mock-data.js`
Expected: 无输出（退出码 0）

- [ ] **Step 3: 校验数据自洽**

```bash
node -e "eval(require('fs').readFileSync('js/mock-data.js','utf8').replace('window.MOCK','globalThis.MOCK')); const d=MOCK.docs; console.log('count',d.length); const c={}; d.forEach(x=>c[x.status]=(c[x.status]||0)+1); console.log(c); console.log('all 5 steps', d.every(x=>x.steps&&x.steps.length===5));"
```
Expected: `count 20`；状态分布含 完成/进行中/排队/失败/停止 五类（完成≈7、进行中≈5、排队≈3、失败≈2、停止≈2、其余）；`all 5 steps true`。

- [ ] **Step 4: Commit**

```bash
git add js/mock-data.js
git commit -m "文档导入: docs扩至20份，加5步子步骤(steps)与5态归一"
```

---

### Task 2: 升级 docTree 为可编辑多级树 + tree helper

**Files:**
- Modify: `js/app.js`（`store.docTree` 定义，约 75-89 行；新增 helper，约在 line 108 setFolder 附近）

- [ ] **Step 1: 替换 docTree 定义**

先 Read `js/app.js` 确认 `docTree: [ ... ],` 范围（约 75-89）。替换为带 `id` 的多级树，设备节点下挂 20 份文档叶子（`docId` 关联 docs，`isDoc:true` 标记叶子）。中间节点保留 `filter`（供其他页消费），`count` 改由 helper 动态算，这里不写死 count 字段（删除现有 count）。

```javascript
    docTree: [
      { id: 'prj-tpl', label: '太平岭一期（采购文件）', children: [
        { id: 'area-ni', label: '核岛主设备', children: [
          { id: 'eq-ptr', label: 'PTR冷却泵', filter: { equipment: 'PTR冷却泵' }, children: [
            { id: 'doc-D-001', label: 'PTR冷却泵设备运行与维修手册.docx', isDoc: true, docId: 'D-001' },
            { id: 'doc-D-002', label: 'PTR冷却泵安装调试记录.docx', isDoc: true, docId: 'D-002' },
            { id: 'doc-D-003', label: 'PTR冷却泵备件清单.xlsx', isDoc: true, docId: 'D-003' },
          ] },
          { id: 'eq-rri', label: 'RRI冷却泵', filter: { equipment: 'RRI冷却泵' }, children: [
            { id: 'doc-D-004', label: 'RRI冷却泵设备运行与维修手册.docx', isDoc: true, docId: 'D-004' },
            { id: 'doc-D-005', label: 'RRI冷却泵技术规格书.pdf', isDoc: true, docId: 'D-005' },
          ] },
          { id: 'eq-asg', label: 'ASG辅助给水泵', filter: { equipment: 'ASG辅助给水泵' }, children: [
            { id: 'doc-D-008', label: 'ASG辅助给水泵维修手册.pdf', isDoc: true, docId: 'D-008' },
            { id: 'doc-D-009', label: 'ASG辅助给水泵结构图纸.pdf', isDoc: true, docId: 'D-009' },
            { id: 'doc-D-010', label: 'ASG辅助给水泵试验报告(扫描版).pdf', isDoc: true, docId: 'D-010' },
          ] },
        ] },
        { id: 'area-ci', label: '常规岛设备', children: [
          { id: 'eq-cef', label: 'CEF补水泵', filter: { equipment: 'CEF补水泵' }, children: [
            { id: 'doc-D-006', label: 'CEF补水泵运行维修手册(扫描版).pdf', isDoc: true, docId: 'D-006' },
            { id: 'doc-D-007', label: 'CEF补水泵采购技术规格书.docx', isDoc: true, docId: 'D-007' },
          ] },
          { id: 'eq-main', label: '主给水泵', filter: { equipment: '主给水泵' }, children: [
            { id: 'doc-D-014', label: '主给水泵机组运行手册.docx', isDoc: true, docId: 'D-014' },
            { id: 'doc-D-015', label: '主给水泵振动分析报告.pdf', isDoc: true, docId: 'D-015' },
          ] },
          { id: 'eq-cond', label: '凝结水泵', filter: { equipment: '凝结水泵' }, children: [
            { id: 'doc-D-016', label: '凝结水泵检修工艺规程.docx', isDoc: true, docId: 'D-016' },
            { id: 'doc-D-017', label: '凝结水泵电机说明书(扫描版).pdf', isDoc: true, docId: 'D-017' },
          ] },
        ] },
        { id: 'area-cvcs', label: '化容控制', children: [
          { id: 'eq-rcv', label: 'RCV上充泵', filter: { equipment: 'RCV上充泵' }, children: [
            { id: 'doc-D-011', label: 'RCV上充泵设备运行与维修手册.docx', isDoc: true, docId: 'D-011' },
            { id: 'doc-D-012', label: 'RCV上充泵密封件图册.pdf', isDoc: true, docId: 'D-012' },
            { id: 'doc-D-013', label: 'RCV上充泵备件清单.xlsx', isDoc: true, docId: 'D-013' },
          ] },
          { id: 'eq-rhr', label: '余热排出泵', filter: { equipment: '余热排出泵' }, children: [
            { id: 'doc-D-018', label: '余热排出泵运行维修手册.docx', isDoc: true, docId: 'D-018' },
            { id: 'doc-D-019', label: '余热排出泵采购合同附件.pdf', isDoc: true, docId: 'D-019' },
            { id: 'doc-D-020', label: '余热排出泵备件清单.xlsx', isDoc: true, docId: 'D-020' },
          ] },
        ] },
      ] },
    ],
```

（`store` 已是 `Vue.reactive(...)`——确认 app.js 里 store 用 `Vue.reactive` 包裹；docTree 作为其属性天然深响应，无需额外处理。若 store 非 reactive，Read 确认后按现状，本 POC 中 `window.NP.store` 已是 reactive。）

- [ ] **Step 2: 新增 tree helper**

在 `js/app.js` 的 `window.NP.setFolder = ...`（约 line 108）之后插入：

```javascript
  // ---- docTree 编辑 helper（导入页拖拽/增删改用） ----
  let _treeSeq = 0;
  window.NP.treeNewId = function (prefix) { _treeSeq += 1; return (prefix || 'node') + '-' + Date.now() + '-' + _treeSeq; };
  window.NP.treeFind = function (id, nodes) {
    nodes = nodes || window.NP.store.docTree;
    for (const n of nodes) {
      if (n.id === id) return n;
      if (n.children) { const r = window.NP.treeFind(id, n.children); if (r) return r; }
    }
    return null;
  };
  window.NP.treeFindParent = function (id, nodes, parent) {
    nodes = nodes || window.NP.store.docTree;
    for (const n of nodes) {
      if (n.id === id) return parent || null;
      if (n.children) { const r = window.NP.treeFindParent(id, n.children, n); if (r !== undefined && r !== null) return r; if (window.NP.treeFind(id, n.children)) return n; }
    }
    return null;
  };
  window.NP.treeAddFolder = function (parentId, label) {
    const node = { id: window.NP.treeNewId('folder'), label: label, children: [] };
    if (!parentId) { window.NP.store.docTree.push(node); return node; }
    const p = window.NP.treeFind(parentId);
    if (p) { if (!p.children) p.children = []; p.children.push(node); }
    return node;
  };
  window.NP.treeRename = function (id, label) {
    const n = window.NP.treeFind(id); if (n) n.label = label; return n;
  };
  window.NP.treeRemove = function (id) {
    const strip = (nodes) => {
      const i = nodes.findIndex(n => n.id === id);
      if (i >= 0) { nodes.splice(i, 1); return true; }
      return nodes.some(n => n.children && strip(n.children));
    };
    return strip(window.NP.store.docTree);
  };
  // 子树文档数（文件夹 count 动态计算）
  window.NP.treeDocCount = function (node) {
    if (node.isDoc) return 1;
    return (node.children || []).reduce((s, c) => s + window.NP.treeDocCount(c), 0);
  };
  // 收集某节点子树下的全部 docId（目录过滤用）
  window.NP.treeDocIds = function (node) {
    if (node.isDoc) return node.docId ? [node.docId] : [];
    return (node.children || []).flatMap(c => window.NP.treeDocIds(c));
  };
```

- [ ] **Step 3: 语法校验**

Run: `node --check js/app.js`
Expected: 无输出（退出码 0）

- [ ] **Step 4: 浏览器冒烟（防止 docTree 升级打挂其他页）**

```bash
cd "C:/Users/Lenovo/Desktop/中广核项目/POC" && python -m http.server 8018
```
用 Playwright 打开 `http://localhost:8018/index.html`（chromium 慢就复用 `%LOCALAPPDATA%/ms-playwright/chromium_headless_shell-1223` 的 executable_path），核对：
- 内容数据库页左目录树能展开、显示文档叶子、点设备节点仍能触发筛选（onFolderClick 读 data.filter，文档叶子无 filter 点击无副作用即可）
- 解析结果页 cascader 能打开（Task 4 会过滤文档叶子；此步只确认不报错）
- console 无报错
关服务。

- [ ] **Step 5: Commit**

```bash
git add js/app.js
git commit -m "文档导入: docTree升级为带id多级树(挂文档叶子)+tree编辑helper"
```

---

### Task 3: 新增 imp- 样式

**Files:**
- Modify: `css/main.css`（文件末尾追加）

- [ ] **Step 1: 追加样式**

在 `css/main.css` 末尾追加：

```css
/* ===================== 文档导入与预处理（imp-） ===================== */
/* 状态分组 chip 栏 */
.imp-status-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; padding: 8px 12px; }
.imp-chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 12px; border-radius: 20px; border: 1px solid var(--np-border); background: #fff; cursor: pointer; font-size: 12.5px; color: var(--np-text); transition: all .12s; }
.imp-chip:hover { border-color: var(--np-primary); }
.imp-chip .cnt { font-family: var(--np-display); font-weight: 700; }
.imp-chip .dot { width: 8px; height: 8px; border-radius: 50%; }
.imp-chip.st-done .dot { background: var(--np-success); }
.imp-chip.st-run .dot { background: var(--np-primary); }
.imp-chip.st-queue .dot { background: #9aa8a6; }
.imp-chip.st-fail .dot { background: var(--np-danger); }
.imp-chip.st-stop .dot { background: var(--np-warn); }
.imp-chip.active { color: #fff; border-color: transparent; }
.imp-chip.active.st-done { background: var(--np-success); }
.imp-chip.active.st-run { background: var(--np-primary); }
.imp-chip.active.st-queue { background: #6b7a77; }
.imp-chip.active.st-fail { background: var(--np-danger); }
.imp-chip.active.st-stop { background: var(--np-warn); }
.imp-chip.active .dot { background: #fff; }

/* 行内迷你流水线 */
.imp-pipe { display: flex; align-items: center; gap: 0; }
.imp-node { display: flex; flex-direction: column; align-items: center; gap: 2px; min-width: 30px; }
.imp-dot { width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px; color: #fff; border: 1.5px solid transparent; }
.imp-dot.done { background: var(--np-success); }
.imp-dot.running { background: var(--np-primary); }
.imp-dot.queued { background: #cbd5d1; color: #6b7a77; }
.imp-dot.failed { background: var(--np-danger); }
.imp-dot.pending { background: #fff; border-color: #cbd5d1; color: #b8c4c0; }
.imp-dot.stopped { background: var(--np-warn); }
.imp-node .imp-nlabel { font-size: 9px; color: var(--np-text-sub); white-space: nowrap; }
.imp-link { width: 14px; height: 2px; background: #dfe7e5; margin-bottom: 13px; }
.imp-link.done { background: var(--np-success); }

/* 展开详情 */
.imp-expand { padding: 8px 16px 12px 48px; background: var(--np-surface-soft); }
.imp-step-row { display: grid; grid-template-columns: 120px 90px 1fr 70px; align-items: center; gap: 12px; padding: 5px 0; border-bottom: 1px dashed var(--np-border); font-size: 12.5px; }
.imp-step-row:last-child { border-bottom: 0; }
.imp-step-row .isr-label { display: flex; align-items: center; gap: 6px; font-weight: 600; color: var(--np-text); }
.imp-step-row .isr-dur { text-align: right; font-family: var(--np-mono); color: var(--np-text-sub); font-size: 11.5px; }

/* 目录树节点悬浮操作 */
.imp-tree-node { display: flex; align-items: center; gap: 5px; width: 100%; }
.imp-tree-node .itn-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.imp-tree-node .itn-ops { display: none; gap: 2px; }
.imp-tree-node:hover .itn-ops { display: inline-flex; }
.imp-tree-node .itn-cnt { font-size: 11px; color: var(--np-text-sub); font-family: var(--np-mono); }
```

- [ ] **Step 2: Commit**

```bash
git add css/main.css
git commit -m "文档导入: 新增imp-样式(状态chip/行内流水线/展开详情/树操作)"
```

---

### Task 4: 重写导入页签模板与 setup

**Files:**
- Modify: `js/pages/parse.js`（导入 el-tab-pane 模板约 8-142 行；setup 导入相关逻辑约 520-635 行；review cascader 约 150 行；return 导出）

本任务较大，按子步骤逐块改。每子步骤后不单独 commit，全部完成一次 `node --check` + 一次 commit。

- [ ] **Step 1: 重写导入页签模板**

将导入 el-tab-pane（`<el-tab-pane label="文档导入与预处理" name="import">` 到其 `</el-tab-pane>`，约 8-142 行）整体替换为：

```html
      <!-- ========== Tab1 文档导入与预处理（多级目录 + 多维搜索 + 状态分组 + 子步骤流水线） ========== -->
      <el-tab-pane label="文档导入与预处理" name="import">
        <el-row :gutter="14">
          <!-- 左：多级文档目录树（拖拽/增删改） -->
          <el-col :span="6">
            <div class="panel" style="min-height:560px;">
              <div class="panel-title">
                <span>文档目录</span>
                <el-button size="small" type="primary" icon="FolderAdd" circle :disabled="!can('edit')" title="新建根级文件夹" @click="treeAddRoot" />
              </div>
              <el-input v-model="treeFilter" size="small" placeholder="搜索目录…" prefix-icon="Search" clearable style="margin-bottom:8px" />
              <el-tree ref="docTreeEl" :data="docTree" node-key="id" :props="{label:'label'}" default-expand-all highlight-current
                       :expand-on-click-node="false" draggable :allow-drop="allowTreeDrop" :filter-node-method="filterTreeNode"
                       @node-click="onTreeNode" @node-drop="onTreeDrop">
                <template #default="{node, data}">
                  <span class="imp-tree-node">
                    <el-icon v-if="data.isDoc" :size="13" color="#7a8699"><Document /></el-icon>
                    <el-icon v-else :size="14" color="#1B4F9C"><Folder /></el-icon>
                    <span class="itn-label" :title="data.label">{{ data.label }}</span>
                    <span v-if="!data.isDoc" class="itn-cnt">{{ treeCount(data) }}</span>
                    <span class="itn-ops">
                      <el-button v-if="!data.isDoc" size="small" text icon="Plus" :disabled="!can('edit')" title="新建子文件夹" @click.stop="treeAddChild(data)" />
                      <el-button size="small" text icon="EditPen" :disabled="!can('edit')" title="重命名" @click.stop="treeRename(data)" />
                      <el-button size="small" text type="danger" icon="Delete" :disabled="!can('edit')" title="删除" @click.stop="treeRemove(data)" />
                    </span>
                  </span>
                </template>
              </el-tree>
              <div class="sub-text" style="margin-top:10px">多级目录：项目→区域→设备→文档；支持拖拽移动、右侧悬浮按钮新建/重命名/删除（演示级，刷新复位）。</div>
            </div>
          </el-col>

          <!-- 右：搜索 + 状态分组 + 监控 + 批量 + 文档表 -->
          <el-col :span="18">
            <!-- 多维搜索 -->
            <div class="panel" style="margin-bottom:10px;">
              <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                <el-input v-model="q.kw" size="small" placeholder="文档名称关键词…" prefix-icon="Search" clearable style="width:190px" />
                <el-select v-model="q.equipment" size="small" placeholder="设备" clearable style="width:120px">
                  <el-option v-for="e in equipOptions" :key="e" :label="e" :value="e" />
                </el-select>
                <el-select v-model="q.mfr" size="small" placeholder="厂家" clearable style="width:130px">
                  <el-option v-for="m in mfrOptions" :key="m" :label="m" :value="m" />
                </el-select>
                <el-select v-model="q.type" size="small" placeholder="类型" clearable style="width:120px">
                  <el-option v-for="t in typeOptions" :key="t" :label="t" :value="t" />
                </el-select>
                <el-button size="small" plain icon="RefreshLeft" @click="resetQuery">重置</el-button>
                <span class="sub-text" style="margin-left:auto">当前目录：<b style="color:var(--np-primary)">{{ currentFolder }}</b> · 命中 {{ filteredDocs.length }} / {{ docs.length }}</span>
              </div>
            </div>

            <!-- 状态分组 chip（点击筛选） -->
            <div class="panel imp-status-bar" style="margin-bottom:10px;">
              <span v-for="s in statusChips" :key="s.key" class="imp-chip" :class="[s.cls, { active: statusFilter === s.key }]" @click="toggleStatus(s.key)">
                <span class="dot"></span>{{ s.key }}<span class="cnt">{{ s.count }}</span>
              </span>
              <span v-if="statusFilter" class="sub-text" style="margin-left:8px; cursor:pointer; color:var(--np-primary)" @click="statusFilter=null">清除状态筛选</span>
            </div>

            <!-- 批量处理监控 -->
            <div class="batch-monitor" style="margin-bottom:10px;">
              <div class="bm-head">
                <span class="bm-title"><span class="bm-bar"></span>批量处理监控</span>
                <span class="bm-sub">太平岭一期存量文件 · {{ batch.total }} 份</span>
                <span class="bm-live"><span class="live-dot"></span>实时</span>
              </div>
              <div class="bm-stats">
                <div class="bm-stat"><div class="bms-num">{{ batch.parsed }}</div><div class="bms-lbl">已解析</div></div>
                <div class="bm-stat warn"><div class="bms-num">{{ batch.queue }}</div><div class="bms-lbl">队列等待</div></div>
                <div class="bm-stat ok"><div class="bms-num">{{ batch.successRate }}</div><div class="bms-lbl">成功率</div></div>
                <div class="bm-stat danger"><div class="bms-num">{{ batch.failed }}</div><div class="bms-lbl">失败/重试</div></div>
                <div class="bm-stat"><div class="bms-num">{{ batch.ocr }}</div><div class="bms-lbl">OCR 处理中</div></div>
                <div class="bm-stat"><div class="bms-num">{{ batch.concurrency }} 路</div><div class="bms-lbl">并发通道</div></div>
              </div>
              <div class="bm-progress">
                <div class="bmp-label">整体进度 <b>{{ batch.progress }}%</b> · 吞吐 {{ batch.throughput }} 文件/秒 · 预计完成 {{ batch.eta }}</div>
                <div class="bmp-bar"><div class="bmp-fill" :style="'width:' + batch.progress + '%'"></div></div>
              </div>
              <div class="sub-text" style="margin-top:8px">单份失败不影响批量（§72）；断点续传；失败任务自动进入重试队列，3 次失败转人工。</div>
            </div>

            <!-- 批量操作 -->
            <div class="panel" style="margin-bottom:10px;">
              <div class="batch-bar">
                <span class="sub-text">共 {{ filteredDocs.length }} 份 · 已选 {{ selectedCount }}</span>
                <span style="margin-left:auto; display:flex; gap:6px; flex-wrap:wrap;">
                  <el-button size="small" type="primary" icon="Upload" :disabled="!can('edit')" @click="startImport">批量导入</el-button>
                  <el-button size="small" type="warning" plain :disabled="!can('edit') || !failedCount" @click="batchRetryFailed">批量重试失败 ({{ failedCount }})</el-button>
                  <el-button size="small" plain :disabled="!can('edit') || !selectedCount" @click="batchReparse">批量重解析</el-button>
                  <el-button size="small" plain :disabled="!can('edit') || !runningCount" @click="stopAll">停止全部</el-button>
                  <el-button size="small" type="danger" plain :disabled="!can('edit') || !selectedCount" @click="batchDelete">批量删除</el-button>
                </span>
              </div>
            </div>

            <!-- 文档表（行内流水线 + 展开详情） -->
            <el-table :data="filteredDocs" border size="small" row-key="id" @selection-change="onSelection">
              <el-table-column type="selection" width="38" :selectable="() => can('edit')" />
              <el-table-column type="expand">
                <template #default="{row}">
                  <div class="imp-expand">
                    <div v-for="st in row.steps" :key="st.key" class="imp-step-row">
                      <span class="isr-label"><span class="imp-dot" :class="st.status">{{ stepIcon(st.status) }}</span>{{ st.label }}</span>
                      <el-tag size="small" :type="stepTagType(st.status)">{{ stepStatusText(st.status) }}</el-tag>
                      <el-progress :percentage="st.progress" :status="st.status==='failed'?'exception':(st.status==='done'?'success':'')" :stroke-width="8" />
                      <span class="isr-dur">{{ st.duration }}</span>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="name" label="文档名称" min-width="230">
                <template #default="{row}">
                  <el-icon style="vertical-align:-2px; margin-right:4px;" :color="row.type.includes('PDF') ? '#c0392b' : (row.type==='Excel' ? '#1e7b44' : '#1B4F9C')"><Document /></el-icon>
                  <span :title="row.name">{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="equipment" label="设备" width="110" show-overflow-tooltip />
              <el-table-column prop="manufacturer" label="厂家" width="120" show-overflow-tooltip />
              <el-table-column prop="type" label="类型" width="90" />
              <el-table-column label="解析流水线" width="230">
                <template #default="{row}">
                  <div class="imp-pipe">
                    <template v-for="(st, i) in row.steps" :key="st.key">
                      <span v-if="i>0" class="imp-link" :class="{done: row.steps[i-1].status==='done'}"></span>
                      <span class="imp-node" :title="st.label + ' · ' + stepStatusText(st.status) + (st.status==='running' ? ' ' + st.progress + '%' : (st.duration!=='—' ? ' · ' + st.duration : ''))">
                        <span class="imp-dot" :class="st.status">{{ stepIcon(st.status) }}</span>
                        <span class="imp-nlabel">{{ st.short }}</span>
                      </span>
                    </template>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="110">
                <template #default="{row}">
                  <el-tag size="small" :type="statusType(row.status)">
                    <el-icon v-if="row.status==='进行中'" class="is-loading" style="vertical-align:-1px"><Loading /></el-icon>
                    {{ row.status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" align="center">
                <template #default="{row}">
                  <template v-if="row.status==='进行中'">
                    <el-button size="small" text type="warning" :disabled="!can('edit')" @click="stopRow(row)">停止</el-button>
                  </template>
                  <template v-else-if="row.status==='失败' || row.status==='停止'">
                    <el-button size="small" text type="primary" :disabled="!can('edit')" @click="retry(row)">重试</el-button>
                  </template>
                  <template v-else-if="row.status==='完成'">
                    <el-button size="small" text type="primary" @click="tab='review'">查看解析</el-button>
                  </template>
                  <el-button size="small" text type="danger" :disabled="!can('edit')" @click="deleteRow(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="sub-text" style="margin-top:8px">
              点击文档行展开查看 5 个解析子步骤（OCR/结构化/Embedding/实体关系/LLM抽取）的状态、进度与处理耗时；扫描件走 OCR，Word/Excel 直接结构化。
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>
```

- [ ] **Step 2: 重写 setup 中导入相关逻辑**

在 setup 中，找到导入相关代码块（约 520-635 行：`const docs = ref(...)` 到 `function msg(...)`），替换为下面（保留 `batch`、`msg`、`blocks` 相关不在此块的代码；`tab` ref 保留）：

```javascript
    // ---- 文档数据（含 5 子步骤 steps） ----
    const docs = ref(JSON.parse(JSON.stringify(M.docs)));

    // 批量处理监控（太平岭一期 30万+ 文件规模）
    const batch = {
      total: '305,842', parsed: '89,216', queue: '1,240', successRate: '99.2%',
      failed: '714', ocr: '23', concurrency: '8', throughput: '12.4',
      progress: 29, eta: '约 3 天 6 小时',
    };

    // ---- 子步骤展示辅助 ----
    const STEP_SHORT = { ocr: 'OCR', struct: '结构化', embed: 'Embed', entity: '实体', llm: 'LLM' };
    // 给每个 step 补 short（用于行内流水线小标签）
    docs.value.forEach(d => d.steps && d.steps.forEach(s => { s.short = STEP_SHORT[s.key] || s.key; }));
    function stepIcon(status) { return { done: '✓', running: '◐', failed: '✗', stopped: '‖', queued: '', pending: '' }[status] || ''; }
    function stepStatusText(status) { return { done: '完成', running: '进行中', queued: '排队', failed: '失败', pending: '未开始', stopped: '已停止' }[status] || status; }
    function stepTagType(status) { return { done: 'success', running: 'primary', failed: 'danger', stopped: 'warning', queued: 'info', pending: 'info' }[status] || 'info'; }

    // ---- 文档整体状态派生（导入动画后重算） ----
    function docStatus(steps) {
      if (steps.some(s => s.status === 'failed')) return '失败';
      if (steps.some(s => s.status === 'running')) return '进行中';
      if (steps.every(s => s.status === 'done')) return '完成';
      if (steps.some(s => s.status === 'stopped')) return '停止';
      return '排队';
    }

    // ---- 导入模拟（推进第一个未完成步骤） ----
    function startImport() {
      const target = docs.value.find(d => d.status === '排队');
      if (!target) { ElementPlus.ElMessage.info('当前无排队中的文档'); return; }
      const step = target.steps.find(s => s.status !== 'done');
      if (!step) return;
      step.status = 'running';
      target.status = '进行中';
      const timer = setInterval(() => {
        step.progress = Math.min(100, step.progress + 12);
        target.progress = Math.min(100, target.progress + 6);
        if (step.progress >= 100) {
          step.status = 'done'; step.duration = (5 + Math.round(step.progress / 12)) + '.0s';
          clearInterval(timer);
          const next = target.steps.find(s => s.status === 'queued' || s.status === 'pending');
          if (next) { next.status = 'queued'; }
          target.status = docStatus(target.steps);
          if (target.status === '完成') target.progress = 100;
          ElementPlus.ElMessage.success(target.name + ' 推进一步：' + step.label + ' 完成');
        }
      }, 400);
    }
    function retry(row) {
      const step = row.steps.find(s => s.status === 'failed' || s.status === 'stopped' || s.status === 'pending');
      if (!step) { ElementPlus.ElMessage.info('无可重试步骤'); return; }
      step.status = 'running'; step.progress = Math.max(10, step.progress);
      row.status = '进行中';
      const timer = setInterval(() => {
        step.progress = Math.min(100, step.progress + 14);
        if (step.progress >= 100) {
          step.status = 'done'; step.duration = '6.0s';
          clearInterval(timer);
          row.status = docStatus(row.steps);
          ElementPlus.ElMessage.success(row.name + ' 已从断点恢复：' + step.label);
        }
      }, 350);
    }

    // ---- 目录树（消费共享 NP.store.docTree，可编辑） ----
    const docTree = window.NP.store.docTree;
    const currentFolder = ref('全部');
    const folderDocIds = ref(null);   // 选中目录子树的 docId 集合（null=全部）
    function onTreeNode(data) {
      if (data.isDoc) {
        folderDocIds.value = data.docId ? [data.docId] : [];
        currentFolder.value = data.label;
      } else {
        folderDocIds.value = window.NP.treeDocIds(data);
        currentFolder.value = data.label;
      }
    }
    function treeCount(data) { return window.NP.treeDocCount(data); }

    // 目录树查询（按名过滤）
    const treeFilter = ref('');
    const docTreeEl = ref(null);
    Vue.watch(treeFilter, (v) => { if (docTreeEl.value) docTreeEl.value.filter(v); });
    function filterTreeNode(value, data) { return !value || (data.label || '').includes(value); }

    // 目录树编辑（新建/重命名/删除/拖拽）
    function treeAddRoot() {
      ElementPlus.ElMessageBox.prompt('新建根级文件夹名称', '新建文件夹', { confirmButtonText: '创建', cancelButtonText: '取消', inputValue: '新建文件夹' })
        .then(({ value }) => { window.NP.treeAddFolder(null, value || '新建文件夹'); ElementPlus.ElMessage.success('已新建'); }).catch(() => {});
    }
    function treeAddChild(data) {
      ElementPlus.ElMessageBox.prompt('在「' + data.label + '」下新建子文件夹', '新建子文件夹', { confirmButtonText: '创建', cancelButtonText: '取消', inputValue: '新建文件夹' })
        .then(({ value }) => { window.NP.treeAddFolder(data.id, value || '新建文件夹'); ElementPlus.ElMessage.success('已新建'); }).catch(() => {});
    }
    function treeRename(data) {
      ElementPlus.ElMessageBox.prompt('重命名', '重命名', { confirmButtonText: '保存', cancelButtonText: '取消', inputValue: data.label })
        .then(({ value }) => { if (value) { window.NP.treeRename(data.id, value); ElementPlus.ElMessage.success('已重命名'); } }).catch(() => {});
    }
    function treeRemove(data) {
      ElementPlus.ElMessageBox.confirm('确认删除「' + data.label + '」' + (data.isDoc ? '' : '及其下全部内容') + '？', '删除', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
        .then(() => { window.NP.treeRemove(data.id); ElementPlus.ElMessage.success('已删除'); }).catch(() => {});
    }
    // 禁止把节点拖进文档叶子内部
    function allowTreeDrop(draggingNode, dropNode, type) {
      if (dropNode.data.isDoc && type === 'inner') return false;
      return true;
    }
    function onTreeDrop() { ElementPlus.ElMessage.success('已移动目录节点'); }

    // ---- 多维搜索 ----
    const q = Vue.reactive({ kw: '', equipment: null, mfr: null, type: null });
    const equipOptions = computed(() => [...new Set(docs.value.map(d => d.equipment))]);
    const mfrOptions = computed(() => [...new Set(docs.value.map(d => d.manufacturer))]);
    const typeOptions = computed(() => [...new Set(docs.value.map(d => d.type))]);
    function resetQuery() { q.kw = ''; q.equipment = null; q.mfr = null; q.type = null; }

    // ---- 状态分组 chip ----
    const statusFilter = ref(null);
    const STATUS_META = [
      { key: '完成', cls: 'st-done' }, { key: '进行中', cls: 'st-run' }, { key: '排队', cls: 'st-queue' },
      { key: '失败', cls: 'st-fail' }, { key: '停止', cls: 'st-stop' },
    ];
    const statusChips = computed(() => STATUS_META.map(m => ({ ...m, count: docs.value.filter(d => d.status === m.key).length })));
    function toggleStatus(k) { statusFilter.value = statusFilter.value === k ? null : k; }

    // ---- 过滤（目录 ∧ 搜索 ∧ 状态） ----
    const filteredDocs = computed(() => docs.value.filter(d =>
      (!folderDocIds.value || folderDocIds.value.includes(d.id))
      && (!q.kw || d.name.includes(q.kw))
      && (!q.equipment || d.equipment === q.equipment)
      && (!q.mfr || d.manufacturer === q.mfr)
      && (!q.type || d.type === q.type)
      && (!statusFilter.value || d.status === statusFilter.value)));

    // ---- 批量统计 ----
    const selectedRows = ref([]);
    const onSelection = (s) => selectedRows.value = s;
    const selectedCount = computed(() => selectedRows.value.length);
    const runningCount = computed(() => docs.value.filter(d => d.status === '进行中').length);
    const failedCount = computed(() => docs.value.filter(d => d.status === '失败').length);
    function statusType(s) {
      return { '完成': 'success', '失败': 'danger', '停止': 'warning', '排队': 'info', '进行中': 'primary' }[s] || 'info';
    }
    function batchRetryFailed() {
      const failed = docs.value.filter(d => d.status === '失败');
      failed.forEach((d, i) => setTimeout(() => retry(d), i * 200));
      ElementPlus.ElMessage.success('已对 ' + failed.length + ' 份失败文档发起批量重试');
    }
    function batchReparse() { ElementPlus.ElMessage.success('已对 ' + selectedRows.value.length + ' 份文档加入批量重解析队列'); }
    function batchDelete() {
      const ids = new Set(selectedRows.value.map(r => r.id));
      docs.value = docs.value.filter(d => !ids.has(d.id));
      ElementPlus.ElMessage.success('已删除 ' + ids.size + ' 份文档（逻辑删除，可恢复）');
    }
    function stopAll() {
      docs.value.forEach(d => { if (d.status === '进行中') { d.steps.forEach(s => { if (s.status === 'running') s.status = 'stopped'; }); d.status = '停止'; } });
      ElementPlus.ElMessage.warning('已停止全部进行中的任务');
    }
    function stopRow(row) { row.steps.forEach(s => { if (s.status === 'running') s.status = 'stopped'; }); row.status = '停止'; ElementPlus.ElMessage.warning(row.name + ' 已停止'); }
    function deleteRow(row) { docs.value = docs.value.filter(d => d.id !== row.id); ElementPlus.ElMessage.success('已删除 ' + row.name); }
    function msg(t) { ElementPlus.ElMessage.info(t + '：演示功能入口'); }
```

- [ ] **Step 3: review cascader 过滤文档叶子**

在 setup 中找到 review 页 cascader 用的 `docTree`（约 line 649 `const docTree = window.NP.store.docTree;` 已在 Step 2 定义；review 用同一个 docTree）。为 cascader 过滤掉文档叶子，新增一份"仅文件夹"的树 computed，并把模板 line ~150 的 `:options="docTree"` 改为 `:options="folderOnlyTree"`：

setup 加：
```javascript
    // review cascader 只用文件夹层级（滤掉文档叶子）
    function stripDocs(nodes) {
      return nodes.filter(n => !n.isDoc).map(n => ({ ...n, children: n.children ? stripDocs(n.children) : undefined }));
    }
    const folderOnlyTree = computed(() => stripDocs(docTree));
```
模板改：`<el-cascader v-model="folderPath" :options="folderOnlyTree" ...>`（其余属性不变）。

- [ ] **Step 4: 更新 return 导出**

setup return 对象中，导入相关导出替换为：
```javascript
      tab, docs, batch, startImport, retry,
      docTree, docTreeEl, currentFolder, onTreeNode, treeCount,
      treeFilter, filterTreeNode, treeAddRoot, treeAddChild, treeRename, treeRemove, allowTreeDrop, onTreeDrop,
      q, equipOptions, mfrOptions, typeOptions, resetQuery,
      statusFilter, statusChips, toggleStatus,
      filteredDocs, selectedCount, runningCount, failedCount, onSelection,
      statusType, batchRetryFailed, batchReparse, batchDelete, stopAll, stopRow, deleteRow, msg,
      stepIcon, stepStatusText, stepTagType,
      folderOnlyTree,
```
删除旧导出里已不存在的名字：`currentFolder`（保留，已在上）、`onTreeNode`（保留）、`filteredDocs`（保留）、`selectedRows`（不再导出，仅内部用）、`doneCount/queueCount/stoppedCount`（已删）、`pauseRow`（已删）、`folderFilter`（已删）。用 grep 核对（见 Step 5）。

- [ ] **Step 5: 校验无残留引用**

```bash
node --check js/pages/parse.js
grep -n "pauseRow\|folderFilter\|doneCount\|queueCount\|stoppedCount\|batch-stats\|bs-item" js/pages/parse.js
```
Expected: node --check 通过；grep 无匹配（这些旧标识/类已随模板重写移除）。若 grep 命中，说明模板或 return 有残留，清理干净。

- [ ] **Step 6: Commit**

```bash
git add js/pages/parse.js
git commit -m "文档导入: 导入页重写(树增删改拖拽/多维搜索/状态chip/子步骤流水线+展开)"
```

---

### Task 5: 浏览器实测验证

**Files:** 无改动（除非修复）。

- [ ] **Step 1: 启动服务并打开**

```bash
cd "C:/Users/Lenovo/Desktop/中广核项目/POC" && python -m http.server 8018
```
用 Playwright 打开 `http://localhost:8018/index.html`（chromium 慢就复用 `%LOCALAPPDATA%/ms-playwright/chromium_headless_shell-1223` executable_path）→ 内容解析 → 文档导入与预处理 tab。

- [ ] **Step 2: 逐项核对**

- **目录树**：显示项目→区域→设备→文档四级；文件夹节点显示子树文档计数；悬浮出现 新建/重命名/删除 按钮
- **树增删改**：新建根/子文件夹（prompt）、重命名、删除（确认框）均生效；拖拽一个设备节点到另一区域下成功移动（node-drop 提示）；拖拽禁止落入文档叶子内部
- **目录搜索**：树上方输入过滤节点；点某设备节点 → 右侧文档表只显示该设备文档，currentFolder 更新；点文档叶子 → 定位单份
- **多维搜索**：名称关键词、设备、厂家、类型下拉逐项过滤；叠加；重置恢复；命中计数正确
- **状态分组**：5 个 chip 显示且计数正确（完成/进行中/排队/失败/停止，合计 20）；点 chip 筛选该状态、再点取消；与搜索叠加；"清除状态筛选"生效
- **子步骤流水线**：每行显示 5 节点，按状态着色（✓完成绿/◐进行中蓝/排队灰/✗失败红/未开始空心）；悬浮 title 显示步骤名+状态+进度或耗时
- **展开详情**：点行展开，列出 5 步的图标+标签、状态 tag、进度条、耗时
- **导入动画**：点"批量导入"推进一个排队文档的下一步骤（进度动、步骤转 done、整体状态重算）
- **重试**：失败文档点重试，failed 步骤恢复推进
- **回归**：内容数据库页目录树正常（含文档叶子不报错）；解析结果页 cascader 只显示文件夹层级（无文档叶子）；OCR 校对页签正常
- **console 无报错（硬性）**；截图留存 %TEMP%

- [ ] **Step 3: 有问题修复复测，单独 commit；关服务；git status 干净**

---

## Self-Review 记录

- **Spec 覆盖**：多级目录拖拽/增删改/切换（T2 helper + T4 Step1/2）、目录+元数据+名称搜索（T4 Step2 filteredDocs + 搜索栏）、5 态分组带计数可点筛选（T4 statusChips/toggleStatus）、5 子步骤状态/时间/进度（T1 steps + T4 行内流水线+展开）、cascader 过滤文档叶子（T4 Step3）、database 页兼容（T2 Step4 冒烟）— 全覆盖。
- **占位符**：无；数据与代码完整给出。
- **命名一致性**：`stepIcon/stepStatusText/stepTagType/docStatus/treeDocIds/treeDocCount/treeAddFolder/treeRename/treeRemove/treeFind` 在 T1/T2 定义、T4 模板与 return 引用；step 字段 `key/label/status/progress/duration/short`（short 在 T4 Step2 运行时补）一致；状态 5 态字符串 `完成/进行中/排队/失败/停止` 全文一致；step status 值 `done/running/queued/failed/pending/stopped` 一致（stopped 由 stopRow/stopAll 运行时产生，mock 中 D-013/D-019 预置 stopped 步骤）。`folderOnlyTree` 供 cascader、`docTree` 供导入树与 database（database 用自己的 window.NP.store.docTree 引用，含文档叶子，已在 T2 Step4 确认可接受）。
