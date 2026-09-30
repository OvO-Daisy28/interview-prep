# 系统信息架构重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 POC 从"11 个平级页"重构为"3 分区 + 工作台"信息架构，目录轴贯穿文档相关页，解析任务改流水线视图，加 6 条跨页轻量联动。

**Architecture:** 纯前端 POC（Vue3 global build + Element Plus + ECharts + docx.js，离线）。共享状态集中在 `window.NP.store`（app.js），各页消费；跨页联动通过 store 上的 reactive 集合/计数 + 徽标 + 跳转按钮实现，不引入新框架。

**Tech Stack:** Vue 3 (global build, `<script>` 标签), Element Plus, ECharts, docx.js, 本地 vendor/ 离线库。

**测试机制（本项目无测试运行器）：** 用 gstack browse 二进制作为验证：`$B goto file://.../index.html#/<page>` → `$B js "断言"` + `$B console --errors` 应为 `(no console errors)`。每个任务的"验证"步骤即此。

**Git：** 当前目录非 git 仓库。检查点（checkpoint）步骤可选用 `git init` 后执行；不初始化则视为人工检查点，跳过 commit 命令即可。

**约束（来自 spec §九）：** 不重写已稳定页面，只调整落位/加目录轴/改流水线视图/加联动徽标；不动 `js/mock-data.js` 生成结构（新增目录/联动状态用组件内或 `NP.store` 实现）；保持零控制台报错。

**设计文档：** `docs/superpowers/specs/2026-08-04-system-ia-redesign-design.md`

---

## 文件结构

| 文件 | 责任 | 本计划改动 |
|------|------|-----------|
| `js/app.js` | 应用外壳、路由、共享 store、全局助手 | 新增共享目录/联动状态 + 助手；ROUTES 3 分区重构；FLOW_STEPS 改 4 步 |
| `js/pages/parse.js` | 内容解析（导入/任务/审核/增量） | 审核tab加目录选择器；任务tab改流水线视图；元素清单折叠；联动触发 |
| `js/pages/database.js` | 内容数据库 | 左侧加目录树（共享）；待复核徽标；通用块变更触发 dirtyManualRefs |
| `js/pages/knowledge.js` | 知识库与图谱 | 目录范围指示；新入库徽标；证据卡"跳回原文" |
| `js/pages/generate.js` | 手册生成 | 预览顶部读 dirtyManualRefs 显示红条 |
| `css/main.css` | 全局样式 | 流水线视图样式 + 目录选择器样式 + 徽标样式 + 分区组标题样式 |
| `js/pages/datamodel.js` | 数据模型 | 落位确认（仅验证，无功能改动） |

---

## Task 1: 共享状态基础（NP.store 目录轴 + 联动状态 + 助手）

**Files:**
- Modify: `js/app.js`（`window.NP.store` 定义处 + `window.NP.go` 之后的助手区）

- [ ] **Step 1: 在 `NP.store` 增加目录轴与联动共享状态**

找到 `window.NP.store = Vue.reactive({ ... manuals: [...], role: '审核员', });`，整体替换为：

```js
  window.NP.store = Vue.reactive({
    blocks: M.blocks.map(b => ({ ...b })),
    manuals: [
      { name: 'PTR冷却泵EOMM', version: 'V1.2', status: '已生成' },
      { name: 'RRI冷却泵EOMM', version: '在编', status: '在编' },
      { name: 'CEF补水泵EOMM', version: 'V1.0', status: '已生成' },
    ],
    role: '管理员', // 全管理员视角展示全部功能
    // 目录轴：多级目录（项目→区域→设备→文档），导入建立、全系统复用
    docTree: [
      { label: '太平岭一期（采购文件）', count: 5, children: [
        { label: '核岛主设备', count: 3, children: [
          { label: 'PTR冷却泵', filter: { equipment: 'PTR冷却泵' } },
          { label: 'RRI冷却泵', filter: { equipment: 'RRI冷却泵' } },
          { label: 'ASG辅助给水泵', filter: { equipment: 'ASG辅助给水泵' } },
        ]},
        { label: '常规岛设备', count: 1, children: [
          { label: 'CEF补水泵', filter: { equipment: 'CEF补水泵' } },
        ]},
        { label: '化容控制', count: 1, children: [
          { label: 'RCV上充泵', filter: { equipment: 'RCV上充泵' } },
        ]},
      ]},
    ],
    selectedFolder: null,          // 目录轴共享选中：{ equipment } | null
    pendingReview: [],             // 待复核内容块 id 列表（解析→数据库）
    dirtyManualRefs: 0,            // 被引用通用块变更数（数据库→生成）
    newEntityIds: [],              // 新入库图谱实体 id（解析→知识）
  });
```

- [ ] **Step 2: 在 `NP.go` 之后追加联动助手函数**

找到 `window.NP.go = function (page) { location.hash = '#/' + page; };`，在其后插入：

```js
  // 目录轴
  window.NP.setFolder = function (filter) { window.NP.store.selectedFolder = filter; };
  // 解析→数据库：标记一批待复核块
  window.NP.markPendingReview = function (ids) {
    const s = new Set(window.NP.store.pendingReview);
    ids.forEach(id => s.add(id));
    window.NP.store.pendingReview = [...s];
  };
  window.NP.clearPendingReview = function (id) {
    window.NP.store.pendingReview = window.NP.store.pendingReview.filter(x => x !== id);
  };
  // 数据库→生成：通用块变更计数
  window.NP.markManualDirty = function (n) { window.NP.store.dirtyManualRefs = n; };
  window.NP.clearManualDirty = function () { window.NP.store.dirtyManualRefs = 0; };
  // 解析→知识：新入库实体
  window.NP.markNewEntities = function (ids) {
    const s = new Set(window.NP.store.newEntityIds);
    ids.forEach(id => s.add(id));
    window.NP.store.newEntityIds = [...s];
  };
```

- [ ] **Step 3: 验证**

```bash
B="$HOME/.claude/skills/gstack/browse/dist/browse"
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/dashboard" 2>&1 | tail -1
$B wait --load 2>&1 | tail -1
$B js "JSON.stringify({docTree:window.NP.store.docTree.length, setFolder:typeof window.NP.setFolder, markPending:typeof window.NP.markPendingReview})" 2>&1 | tail -1
$B console --errors 2>&1 | tail -3
```
Expected: `{"docTree":1,"setFolder":"function","markPending":"function"}` + `(no console errors)`。

- [ ] **Step 4: 检查点**

```bash
git add js/app.js && git commit -m "feat(ia): add shared docTree + cross-page linkage state to NP.store" 2>/dev/null || echo "checkpoint 1 (no git)"
```

---

## Task 2: 侧栏 3 分区重构 + 闭环改 4 步

**Files:**
- Modify: `js/app.js`（`ROUTES` 数组 + `FLOW_STEPS` 常量）

- [ ] **Step 1: 重排 ROUTES 为 3 分区**

找到 `const ROUTES = [ ... ];`，整体替换为：

```js
  const ROUTES = [
    { key: 'dashboard', title: '工作台', icon: 'Odometer', step: null },
    { key: 'parse', title: '内容解析', icon: 'DocumentChecked', step: 0, divider: '主流程 · 活化闭环' },
    { key: 'database', title: '内容数据库', icon: 'Coin', step: 1 },
    { key: 'knowledge', title: '知识库与图谱', icon: 'Share', step: 2 },
    { key: 'generate', title: '手册生成', icon: 'Notebook', step: 3 },
    { key: 'aiAssist', title: 'AI辅助编辑', icon: 'MagicStick', step: null },
    { key: 'govern', title: '内容治理', icon: 'Stamp', step: null, divider: '治理保障' },
    { key: 'datamodel', title: '数据模型', icon: 'Histogram', step: null, divider: '配置与运维' },
    { key: 'rules', title: '规则梳理', icon: 'DataLine', step: null },
    { key: 'system', title: '系统管理', icon: 'Setting', step: null },
    { key: 'audit', title: '审计日志', icon: 'List', step: null },
  ];
```

- [ ] **Step 2: 闭环改 4 步（去掉治理/AI）**

找到 `const FLOW_STEPS = [...]`，替换为：

```js
  const FLOW_STEPS = ['内容解析', '内容数据库', '知识图谱', '手册生成'];
```

- [ ] **Step 3: 验证分区与步骤高亮**

```bash
B="$HOME/.claude/skills/gstack/browse/dist/browse"
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/parse" 2>&1 | tail -1
$B wait --load 2>&1 | tail -1; sleep 1
$B js "JSON.stringify({dividers:document.querySelectorAll('.menu-divider').length, stages:document.querySelectorAll('.stage-node').length, cur:document.querySelector('.stage-node.current .stage-label')?.textContent})" 2>&1 | tail -1
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/generate" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.querySelector('.stage-node.current .stage-label')?.textContent" 2>&1 | tail -1
$B console --errors 2>&1 | tail -2
```
Expected: 3 dividers（主流程/治理保障/配置与运维），4 stage nodes，parse→current「内容解析」，generate→current「手册生成」，无报错。

- [ ] **Step 4: 检查点**

```bash
git add js/app.js && git commit -m "feat(ia): regroup sidebar into 3 sections, flow steps to 4" 2>/dev/null || echo "checkpoint 2"
```

---

## Task 3: 解析审核 tab 加目录选择器（目录轴贯穿）

**Files:**
- Modify: `js/pages/parse.js`（review tab-pane 顶部 + setup 消费 selectedFolder/docTree）

- [ ] **Step 1: 在 review tab 顶部加目录选择器**

在 parse.js 模板中找到 `<!-- 准确率面板 -->` 上方（即 `<el-tab-pane label="解析结果与 AI 审核" name="review">` 之后、`<div class="acc-banner">` 之前），插入目录选择器条：

```html
        <!-- 目录轴：先选目录再选文档（解决审核页定位缺口） -->
        <div class="folder-bar">
          <span class="fb-label">目录：</span>
          <el-cascader v-model="folderPath" :options="docTree" :props="{ expandTrigger: 'hover', emitPath: false, checkStrictly: true }"
                       placeholder="选择文档（项目 → 设备）" clearable @change="onFolderChange" style="width:320px">
            <template #default="{data}"><span>{{ data.label }}<span v-if="data.count!=null" class="fb-cnt">{{ data.count }}</span></span></template>
          </el-cascader>
          <span class="sub-text" style="margin-left:10px">当前文档：<b>{{ currentDoc ? currentDoc.name : '— 未选择 —' }}</b></span>
          <span v-if="currentDoc" class="sub-text" style="margin-left:auto">{{ currentDoc.equipment }} · {{ currentDoc.manufacturer }} · {{ currentDoc.pages }} 页</span>
        </div>
```

- [ ] **Step 2: setup 增加 docTree/folderPath/currentDoc/onFolderChange**

在 parse.js setup 中找到 `const tocTree = M.tocTree;`，在其前插入：

```js
    // 目录轴（共享）
    const docTree = window.NP.store.docTree;
    const folderPath = ref(null);
    const currentDoc = ref(null);
    function onFolderChange(val) {
      const node = val ? findTreeNode(docTree, val) : null;
      const filter = node && node.filter;
      window.NP.setFolder(filter);
      currentDoc.value = filter ? M.docs.find(d => d.equipment === filter.equipment) : null;
    }
    function findTreeNode(nodes, label) {
      for (const n of nodes) { if (n.label === label) return n; if (n.children) { const r = findTreeNode(n.children, label); if (r) return r; } }
      return null;
    }
```

- [ ] **Step 3: return 增加 docTree/folderPath/currentDoc/onFolderChange**

找到 parse.js setup 的 `return { ... };`，在 `tocTree, currentNode, ...` 行前加入：

```js
      docTree, folderPath, currentDoc, onFolderChange,
```

- [ ] **Step 4: 加目录条样式**

在 `css/main.css` 末尾的「解析页」相关样式区追加：

```css
/* 目录轴选择条 */
.folder-bar { display: flex; align-items: center; gap: 8px; padding: 10px 14px; background: var(--np-primary-light); border: 1px solid #c9d8ee; border-radius: 8px; margin-bottom: 12px; }
.folder-bar .fb-label { font-size: 12.5px; color: var(--np-text-sub); }
.folder-bar .fb-cnt { font-size: 10px; color: var(--np-text-sub); background: #fff; border-radius: 8px; padding: 0 6px; margin-left: 4px; }
```

- [ ] **Step 5: 验证**

```bash
B="$HOME/.claude/skills/gstack/browse/dist/browse"
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/parse" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.querySelectorAll('.el-tabs__item')[2].click()" >/dev/null 2>&1; sleep 1
$B js "JSON.stringify({folderBar:!!document.querySelector('.folder-bar'),cascader:document.querySelectorAll('.folder-bar .el-cascader').length})" 2>&1 | tail -1
# 模拟选目录
$B js "document.querySelector('.folder-bar .el-cascader input').click()" >/dev/null 2>&1; sleep 1
$B js "[...document.querySelectorAll('.el-cascader-node')].find(n=>n.textContent.includes('PTR冷却泵'))?.click()" >/dev/null 2>&1; sleep 1
$B js "document.body.innerText.includes('当前文档') && document.body.innerText.includes('PTR')" 2>&1 | tail -1
$B console --errors 2>&1 | tail -2
```
Expected: `{"folderBar":true,"cascader":1}`，选 PTR 后 `true`，无报错。

- [ ] **Step 6: 检查点**

```bash
git add js/pages/parse.js css/main.css && git commit -m "feat(parse): add folder selector to review tab" 2>/dev/null || echo "checkpoint 3"
```

---

## Task 4: 解析任务 tab 改流水线视图

**Files:**
- Modify: `js/pages/parse.js`（task tab-pane 的三引擎卡片替换为流水线图）+ `css/main.css`

- [ ] **Step 1: 用流水线视图替换三引擎卡片循环**

在 parse.js 模板找到 `<div v-for="t in tasks" :key="t.id" class="panel">` ... 到对应 `</div>`（解析任务 tab 内的三引擎卡片块），将该 `v-for` 整体替换为流水线视图：

```html
        <!-- 解析产物流水线（多产物线分流，替代三引擎卡片） -->
        <div class="panel">
          <div class="panel-title"><span>解析产物流水线</span><span class="ai-badge">三引擎协同</span></div>
          <div class="pipeline">
            <div class="pipe-stage">
              <div class="ps-node done"><el-icon><Document /></el-icon><div class="ps-name">导入</div><div class="ps-sub">{{ docs.length }} 份</div></div>
            </div>
            <div class="ps-arrow">→</div>
            <div class="pipe-stage">
              <div class="ps-node done"><el-icon><Files /></el-icon><div class="ps-name">程序结构化</div><div class="ps-sub">章节/段落/表格/图片 + DMC</div></div>
            </div>
            <div class="ps-arrow">→</div>
            <div class="pipe-stage">
              <div class="ps-node done"><el-icon><Reading /></el-icon><div class="ps-name">OCR（扫描件）</div><div class="ps-sub">文字版 · 98.6%</div></div>
            </div>
            <div class="ps-arrow">⤓</div>
            <div class="pipe-branches">
              <div class="ps-branch">
                <div class="ps-node done"><el-icon><DataLine /></el-icon><div class="ps-name">大模型参数提取 + DMC</div><div class="ps-sub">{{ params.length }} 条参数</div></div>
                <div class="ps-arrow">→</div>
                <div class="ps-target">参数表 → <b>内容数据库</b></div>
              </div>
              <div class="ps-branch">
                <div class="ps-node done"><el-icon><Connection /></el-icon><div class="ps-name">分片向量化</div><div class="ps-sub">480 片</div></div>
                <div class="ps-arrow">→</div>
                <div class="ps-target">RAG 向量库 → <b>知识库（语义检索）</b></div>
              </div>
              <div class="ps-branch">
                <div class="ps-node done"><el-icon><Share /></el-icon><div class="ps-name">实体抽取/消歧/关系</div><div class="ps-sub">31 实体 · 39 关系</div></div>
                <div class="ps-arrow">→</div>
                <div class="ps-target">知识图谱 → <b>知识库（推理）</b></div>
              </div>
            </div>
          </div>
          <div class="sub-text" style="margin-top:8px">三条产物线并行：①结构化元素+参数 → 内容数据库；②分片向量化 → RAG向量库；③实体关系 → 知识图谱。后两者同属知识库。</div>
        </div>
```

- [ ] **Step 2: 加流水线样式**

在 `css/main.css` 追加：

```css
/* 解析产物流水线 */
.pipeline { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 10px 4px; }
.pipe-stage { display: flex; align-items: center; gap: 8px; }
.pipe-branches { display: flex; gap: 16px; flex-wrap: wrap; justify-content: center; width: 100%; }
.ps-branch { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1; min-width: 200px; background: #fafbfd; border: 1px dashed var(--np-border); border-radius: 8px; padding: 10px; }
.ps-node { display: flex; flex-direction: column; align-items: center; gap: 3px; width: 150px; padding: 10px 8px; border-radius: 8px; background: #fff; border: 1px solid var(--np-border); box-shadow: var(--np-shadow-sm); }
.ps-node.done { border-top: 3px solid var(--np-success); }
.ps-node .ps-name { font-size: 12.5px; font-weight: 600; }
.ps-node .ps-sub { font-size: 11px; color: var(--np-text-sub); text-align: center; }
.ps-arrow { color: var(--np-primary); font-size: 16px; font-weight: 700; }
.ps-target { font-size: 12px; color: var(--np-text-sub); }
.ps-target b { color: var(--np-primary); }
```

- [ ] **Step 3: 验证**

```bash
B="$HOME/.claude/skills/gstack/browse/dist/browse"
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/parse" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.querySelectorAll('.el-tabs__item')[1].click()" >/dev/null 2>&1; sleep 1
$B js "JSON.stringify({pipeline:!!document.querySelector('.pipeline'),branches:document.querySelectorAll('.ps-branch').length,targets:document.body.innerText.includes('内容数据库')&&document.body.innerText.includes('RAG 向量库')})" 2>&1 | tail -1
$B console --errors 2>&1 | tail -2
```
Expected: `{"pipeline":true,"branches":3,"targets":true}`，无报错。

- [ ] **Step 4: 检查点**

```bash
git add js/pages/parse.js css/main.css && git commit -m "feat(parse): replace engine cards with product pipeline view" 2>/dev/null || echo "checkpoint 4"
```

---

## Task 5: 解析审核元素清单折叠分层

**Files:**
- Modify: `js/pages/parse.js`（元素清单 panel 包裹 el-collapse）

- [ ] **Step 1: 用折叠包裹元素清单**

在 parse.js 模板找到 `<!-- 解析元素清单（§70：标注元素类型与在文档中的位置） -->` 下面的 `<div class="panel" ...>`，将其改为可折叠。把该 panel 的内容（panel-title 之后到 panel 结束）包进 `<el-collapse>`：

找到元素清单 panel 内的：
```html
          <div class="elem-stats">
```
在其前插入折叠触发，把 panel 改为：

```html
        <div class="panel" style="margin-bottom:14px;">
          <el-collapse v-model="elemCollapse" style="border:none">
            <el-collapse-item name="elem">
              <template #title>
                <span style="font-size:13px; font-weight:600;">解析元素清单</span>
                <span class="sub-text" style="margin-left:10px">本章 {{ elements.length }} 个元素 · 类型/页码/位置（§70，点击展开）</span>
              </template>
              <div class="elem-stats">
                <span class="es-item p">段落 {{ cnt.段落 }}</span>
                <span class="es-item t">表格 {{ cnt.表格 }}</span>
                <span class="es-item i">图片 {{ cnt.图片 }}</span>
                <span class="es-item w">警示框 {{ cnt.警示框 }}</span>
              </div>
              <el-table :data="elements" border size="small" style="margin-top:8px; max-height:160px; overflow:auto;">
                <el-table-column label="类型" width="90"><template #default="{row}"><el-tag size="small" :type="elemTag(row.type)">{{ row.type }}</el-tag></template></el-table-column>
                <el-table-column prop="page" label="页码" width="70" align="center"><template #default="{row}">第 {{ row.page }} 页</template></el-table-column>
                <el-table-column prop="pos" label="位置" width="140"><template #default="{row}"><span class="mono">{{ row.pos }}</span></template></el-table-column>
                <el-table-column prop="label" label="元素说明" min-width="260" show-overflow-tooltip />
                <el-table-column label="定位" width="80" align="center"><template #default="{row}"><el-button size="small" text type="primary" @click="locateElem(row)">定位</el-button></template></el-table-column>
              </el-table>
              <div v-if="images.length" class="elem-images">
                <div v-for="(img, i) in images" :key="i" class="elem-img-card">
                  <div class="ei-placeholder"><el-icon :size="28" color="#aab4c4"><Picture /></el-icon></div>
                  <div class="ei-label">{{ img.label }}</div>
                  <div class="sub-text">第 {{ img.page }} 页</div>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
```

（删除原来未折叠的元素清单 panel 内容，替换为上述折叠版）

- [ ] **Step 2: setup 加 elemCollapse**

在 parse.js setup 找到 `const resultTab = ref('blocks');` 附近，加：

```js
    const elemCollapse = ref([]); // 元素清单默认折叠
```

并在 return 的 `elements, cnt, images, elemTag, locateElem,` 行补 `elemCollapse,`。

- [ ] **Step 3: 验证**

```bash
B="$HOME/.claude/skills/gstack/browse/dist/browse"
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/parse" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.querySelectorAll('.el-tabs__item')[2].click()" >/dev/null 2>&1; sleep 1
$B js "const n=[...document.querySelectorAll('.el-tree-node__content')].find(n=>n.textContent.trim().startsWith('2.3 ')); n?.click()" >/dev/null 2>&1; sleep 1
# 默认折叠：元素清单表格不可见
$B js "JSON.stringify({collapse:document.querySelectorAll('.el-collapse-item').length, collapsed: document.querySelectorAll('.el-collapse-item__wrap.is-active').length===0})" 2>&1 | tail -1
# 点击展开
$B js "document.querySelector('.el-collapse-item__header')?.click()" >/dev/null 2>&1; sleep 1
$B js "document.querySelectorAll('.el-collapse-item__wrap.is-active').length>0" 2>&1 | tail -1
$B console --errors 2>&1 | tail -2
```
Expected: 折叠存在且默认收起，点击后展开，无报错。

- [ ] **Step 4: 检查点**

```bash
git add js/pages/parse.js && git commit -m "feat(parse): make element inventory collapsible" 2>/dev/null || echo "checkpoint 5"
```

---

## Task 6: 跨页联动徽标（解析→数据库 待复核）

**Files:**
- Modify: `js/pages/parse.js`（审核完成触发 markPendingReview）+ `js/pages/database.js`（行徽标 + 确认清除）+ `css/main.css`

- [ ] **Step 1: parse 审核确认/批量导入完成触发待复核**

在 parse.js setup 的 `function confirm(b) { b.reviewStatus = '已确认'; }` 处改为：

```js
    function confirm(b) { b.reviewStatus = '已确认'; window.NP.clearPendingReview(b.id); ElementPlus.ElMessage.success('已确认，准确率已更新'); }
```

在 parse.js 的批量导入模拟完成处（`startImport` 里 `target.status = '解析完成'` 那行后）追加标记待复核。找到：
```js
          setTimeout(() => { target.status = '解析完成'; ElementPlus.ElMessage.success(target.name + ' 解析完成'); }, 1800);
```
替换为：
```js
          setTimeout(() => {
            target.status = '解析完成';
            const newIds = blocks.filter(b => b.chapterPath).slice(0, 5).map(b => b.id);
            window.NP.markPendingReview(newIds);
            ElementPlus.ElMessage.success(target.name + ' 解析完成，' + newIds.length + ' 块已进入待复核');
          }, 1800);
```

- [ ] **Step 2: database 列表加待复核徽标**

在 database.js 模板的 内容块 el-table 里，在「ID」列模板加徽标。找到 ID 列：
```html
          <el-table-column prop="id" label="ID" width="80" />
```
替换为：
```html
          <el-table-column label="ID" width="100">
            <template #default="{row}"><span class="mono">{{ row.id }}</span><el-badge v-if="isPending(row.id)" value="待复核" type="warning" style="margin-left:4px" /></template>
          </el-table-column>
```

- [ ] **Step 3: database setup 加 isPending + 目录轴联动**

在 database.js setup 的 `const filtered = computed(...)` 之前加：

```js
    const isPending = (id) => window.NP.store.pendingReview.includes(id);
```

并让数据库的检索响应目录轴：在 `filtered` computed 的 filter 末尾、`return true;` 前加一行：
```js
      const sf = window.NP.store.selectedFolder;
      if (sf && sf.equipment && eqMeta.eqName !== sf.equipment) return false;
```
（`eqMeta` 已在 database.js 定义）

- [ ] **Step 4: database 详情抽屉加"标记通用块变更"触发 dirtyManualRefs（数据库→生成联动）**

在 database.js 详情抽屉的版本管理 panel-title 旁加按钮。找到：
```html
            <el-button size="small" type="primary" plain @click="diffVisible = true">版本对比</el-button>
```
在其后加：
```html
              <el-button v-if="current.isCommon" size="small" type="warning" plain @click="flagManualDirty(current)">模拟通用块变更</el-button>
```

在 database.js setup 加函数（在 `function rollback` 附近）：
```js
    function flagManualDirty(row) {
      window.NP.markManualDirty(3);
      ElementPlus.ElMessage.warning('该通用块被 3 份手册引用，已通知手册生成页');
    }
```

并在 return 补 `isPending, flagManualDirty,`。

- [ ] **Step 5: 加徽标样式**

`css/main.css` 追加：
```css
.badge-pending .el-badge__content { font-size: 10px; }
```

- [ ] **Step 6: 验证联动**

```bash
B="$HOME/.claude/skills/gstack/browse/dist/browse"
# 触发：parse 批量导入完成 → markPendingReview
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/parse" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.querySelectorAll('.el-tabs__item')[0].click()" >/dev/null 2>&1; sleep 1  # 导入tab
$B js "[...document.querySelectorAll('button')].find(b=>b.textContent.includes('批量导入')).click()" >/dev/null 2>&1; sleep 3
# 看 database 是否有待复核徽标
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/database" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "JSON.stringify({pending:window.NP.store.pendingReview.length, badges:document.querySelectorAll('.el-badge__content').length})" 2>&1 | tail -1
$B console --errors 2>&1 | tail -2
```
Expected: pending>0 且 database 有「待复核」徽标，无报错。

- [ ] **Step 7: 检查点**

```bash
git add js/pages/parse.js js/pages/database.js css/main.css && git commit -m "feat(linkage): parse→database pending-review badge + manual-dirty flag" 2>/dev/null || echo "checkpoint 6"
```

---

## Task 7: 联动（数据库→生成 红条 + 知识→解析原文 + 解析→知识新实体）

**Files:**
- Modify: `js/pages/generate.js`（读 dirtyManualRefs 红条）+ `js/pages/knowledge.js`（新实体徽标 + 跳回原文）+ `js/pages/parse.js`（实体抽取审核通过触发 markNewEntities）

- [ ] **Step 1: generate 预览顶部读 dirtyManualRefs 显示红条**

在 generate.js 模板找到预览工具栏（含「组装完成」tag 的那个 panel），在 `</div>`（工具栏 panel 结束）后、`<div class="doc-desk">` 前插入：

```html
          <el-alert v-if="dirtyRefs > 0" type="warning" :closable="false" show-icon style="margin-bottom:10px"
            :title="'引用的 ' + dirtyRefs + ' 处通用内容块已变更，建议重审后重新生成'" >
            <template #default><el-button size="small" type="warning" plain @click="reviewDirty">去内容数据库核查</el-button></template>
          </el-alert>
```

在 generate.js setup 加：
```js
    const dirtyRefs = computed(() => window.NP.store.dirtyManualRefs);
    function reviewDirty() { window.NP.clearManualDirty(); window.NP.go('database'); }
```
return 补 `dirtyRefs, reviewDirty,`。

- [ ] **Step 2: knowledge 证据卡"跳回原文"+ 新实体徽标**

在 knowledge.js 模板找到语义检索证据卡 `.evidence-card`，在 `.ev-meta` div 内末尾加按钮：
```html
                  <el-button size="small" text type="primary" style="margin-left:auto" @click="jumpToOriginal(e)">跳回原文</el-button>
```

在 knowledge 图谱页 panel-title 旁加新实体徽标。找到 `<div class="panel-title">实体详情` 那行，改为：
```html
              <div class="panel-title">实体详情 <span class="sub-text">点击图谱节点</span><el-badge v-if="newEntityCount > 0" :value="'新+' + newEntityCount" type="success" style="margin-left:8px" /></div>
```

在 knowledge.js setup 加：
```js
    const newEntityCount = computed(() => window.NP.store.newEntityIds.length);
    function jumpToOriginal(e) {
      window.NP.go('parse');
      setTimeout(() => ElementPlus.ElMessage.info('已跳转解析审核页，请定位：' + (e.source || '相关章节')), 300);
    }
```
return 补 `newEntityCount, jumpToOriginal,`。

- [ ] **Step 3: parse 实体抽取审核通过触发新实体**

在 parse.js 找到 knowledge 抽取相关？不——实体抽取审核在 knowledge.js（不是 parse）。修正：在 knowledge.js 的 `function confirmAllExtract()` 里追加。找到 knowledge.js setup 的 `function confirmAllExtract()`，改为：
```js
    function confirmAllExtract() {
      currentExtract.value.entities.forEach(en => { if (en.verdict === 'pending') en.verdict = 'confirmed'; });
      const ids = currentExtract.value.entities.map(e => e.name);
      window.NP.markNewEntities(ids);
      currentExtract.value.status = 'done';
      ElementPlus.ElMessage.success('抽取结果已确认并入知识图谱，' + ids.length + ' 实体留痕');
    }
```

- [ ] **Step 4: 验证**

```bash
B="$HOME/.claude/skills/gstack/browse/dist/browse"
# database 触发 dirty → generate 红条
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/database" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "window.NP.markManualDirty(3)" >/dev/null 2>&1
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/generate" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.querySelectorAll('.el-tabs__item')[1].click()" >/dev/null 2>&1; sleep 1
$B js "[...document.querySelectorAll('button')].find(b=>b.textContent.includes('开始智能组装'))?.click()" >/dev/null 2>&1; sleep 5
$B js "JSON.stringify({redBar:document.body.innerText.includes('已变更，建议重审')})" 2>&1 | tail -1
# knowledge 抽取确认 → 新实体徽标
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/knowledge" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.querySelectorAll('.el-tabs__item')[0].click()" >/dev/null 2>&1; sleep 1
$B js "[...document.querySelectorAll('button')].find(b=>b.textContent.includes('全部确认并入图谱'))?.click()" >/dev/null 2>&1; sleep 1
$B js "JSON.stringify({newEnt:window.NP.store.newEntityIds.length})" 2>&1 | tail -1
$B console --errors 2>&1 | tail -2
```
Expected: generate 红条 true；knowledge newEnt>0；无报错。

- [ ] **Step 5: 检查点**

```bash
git add js/pages/generate.js js/pages/knowledge.js js/pages/parse.js && git commit -m "feat(linkage): manual-dirty red bar + new-entity badge + jump-to-original" 2>/dev/null || echo "checkpoint 7"
```

---

## Task 8: 数据模型页落位确认 + 目录轴联动（database/knowledge 目录过滤）

**Files:**
- Modify: `js/pages/database.js`（左侧目录树面板）+ `js/pages/knowledge.js`（目录范围指示）+ 验证 datamodel 落位

- [ ] **Step 1: database 左侧加目录树面板（消费共享 docTree）**

在 database.js 模板最外层 `<div>` 内，把现有结构改为左右布局：左侧目录树 + 右侧检索。在第一个 `<div class="panel">`（多维检索）前加左目录树 + 用 el-row 包裹。最小改动：在检索 panel 前插入目录树 panel，并用 flex 包裹。

找到 database.js 模板开头 `<div>\n    <div class="panel">\n      <div class="panel-title">多维组合检索`，替换为：
```html
  <div>
    <div style="display:flex; gap:14px; align-items:flex-start;">
      <!-- 目录轴 -->
      <div class="panel" style="width:230px; min-width:230px;">
        <div class="panel-title"><span>文档目录</span></div>
        <el-tree :data="docTree" :props="{label:'label'}" default-expand-all highlight-current :expand-on-click-node="false" @node-click="onFolderClick">
          <template #default="{data}"><span class="doc-tree-node"><span>{{ data.label }}</span><span v-if="data.count!=null" class="tree-count">{{ data.count }}</span></span></template>
        </el-tree>
        <div class="sub-text" style="margin-top:8px">点击设备过滤当前目录；切目录全系统联动</div>
      </div>
      <div style="flex:1; min-width:0;">
```
并在最后一个 `</el-dialog>`（跨设备对比/枚举字典）前、`</div>`（根 div 结束）前补闭合 `</div>`：
找到 database.js 模板最后的 `</el-dialog>\n  </div>`，改为 `</el-dialog>\n      </div>\n    </div>\n  </div>`。

在 database.js setup 加：
```js
    const docTree = window.NP.store.docTree;
    function onFolderClick(data) {
      if (data.filter) { window.NP.setFolder(data.filter); q.value.eqName = data.filter.equipment; doSearch(); }
      else { window.NP.setFolder(null); q.value.eqName = ''; doSearch(); }
    }
```
return 补 `docTree, onFolderClick,`。

- [ ] **Step 2: knowledge 目录范围指示**

在 knowledge.js 图谱页的时序/实体类型条上方加范围指示。找到 `<div style="display:flex; gap:6px; align-items:center; margin-bottom:10px; flex-wrap:wrap;">`（图谱页工具条），在其前加：
```html
        <div v-if="folderLabel" class="folder-chip"><el-icon><Folder /></el-icon> 目录范围：{{ folderLabel }}（图谱按目录过滤）</div>
```
setup 加：
```js
    const folderLabel = computed(() => { const sf = window.NP.store.selectedFolder; return sf && sf.equipment ? sf.equipment : ''; });
```
return 补 `folderLabel,`。

`css/main.css` 追加：
```css
.folder-chip { display:inline-flex; align-items:center; gap:5px; font-size:12px; color:var(--np-primary); background:var(--np-primary-light); padding:3px 10px; border-radius:12px; margin-bottom:8px; }
```

- [ ] **Step 3: 验证 datamodel 落位 + 目录轴联动**

```bash
B="$HOME/.claude/skills/gstack/browse/dist/browse"
# datamodel 在配置与运维区
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/datamodel" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "JSON.stringify({inConfig:!![...document.querySelectorAll('.menu-divider')].find(d=>d.textContent.includes('配置与运维'))})" 2>&1 | tail -1
# database 目录树 + 切目录过滤
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/database" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "JSON.stringify({tree:document.querySelectorAll('.doc-tree-node').length>0})" 2>&1 | tail -1
$B js "const n=[...document.querySelectorAll('.el-tree-node__content')].find(n=>n.textContent.includes('PTR冷却泵')); n?.click()" >/dev/null 2>&1; sleep 1
$B js "JSON.stringify({folder:window.NP.store.selectedFolder?.equipment})" 2>&1 | tail -1
# knowledge 范围指示
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/knowledge" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.body.innerText.includes('目录范围')" 2>&1 | tail -1
$B console --errors 2>&1 | tail -2
```
Expected: datamodel 在配置区、database 有目录树、切 PTR→selectedFolder.equipment='PTR冷却泵'、knowledge 有目录范围、无报错。

- [ ] **Step 4: 检查点**

```bash
git add js/pages/database.js js/pages/knowledge.js css/main.css && git commit -m "feat(ia): doc-tree axis on database + folder scope on knowledge" 2>/dev/null || echo "checkpoint 8"
```

---

## Task 9: 全量回归验证

**Files:** 无修改

- [ ] **Step 1: 全 11 页零报错 + 关键联动复测**

```bash
B="$HOME/.claude/skills/gstack/browse/dist/browse"
for p in dashboard parse database knowledge govern generate aiAssist rules datamodel audit system; do
  $B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/$p" >/dev/null 2>&1
  $B wait --load >/dev/null 2>&1; sleep 1
  $B console --clear >/dev/null 2>&1; sleep 1
  err=$($B console --errors 2>&1 | grep -vE "BEGIN|END|UNTRUSTED|no console" | head -1)
  echo "[$p] ${err:-ok}"
done
```
Expected: 全部 `ok`。

- [ ] **Step 2: 联动端到端复测**

```bash
B="$HOME/.claude/skills/gstack/browse/dist/browse"
# 1 目录轴：database 切 PTR → knowledge 显示范围
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/database" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "const n=[...document.querySelectorAll('.el-tree-node__content')].find(n=>n.textContent.includes('PTR冷却泵')); n?.click()" >/dev/null 2>&1; sleep 1
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/knowledge" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.body.innerText.includes('PTR冷却泵')" 2>&1 | tail -1   # → true
# 2 解析→数据库 待复核徽标
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/parse" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.querySelectorAll('.el-tabs__item')[0].click()" >/dev/null 2>&1; sleep 1
$B js "[...document.querySelectorAll('button')].find(b=>b.textContent.includes('批量导入')).click()" >/dev/null 2>&1; sleep 3
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/database" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.querySelectorAll('.el-badge__content').length>0" 2>&1 | tail -1   # → true
# 3 数据库→生成 红条
$B js "window.NP.markManualDirty(3)" >/dev/null 2>&1
$B goto "file:///C:/Users/Lenovo/Desktop/中广核项目/POC/index.html#/generate" >/dev/null 2>&1; $B wait --load >/dev/null 2>&1; sleep 1
$B js "document.querySelectorAll('.el-tabs__item')[1].click()" >/dev/null 2>&1; sleep 1
$B js "[...document.querySelectorAll('button')].find(b=>b.textContent.includes('开始智能组装'))?.click()" >/dev/null 2>&1; sleep 5
$B js "document.body.innerText.includes('已变更，建议重审')" 2>&1 | tail -1   # → true
```
Expected: 三个 `true`。

- [ ] **Step 3: 最终检查点**

```bash
git add -A && git commit -m "chore: full regression pass for IA redesign" 2>/dev/null || echo "final checkpoint (no git)"
```

---

## 自检（spec 覆盖）

- spec §三 分区落位 → Task 2 ✓
- spec §四 目录轴贯穿 → Task 1（store）+ Task 3（parse 审核）+ Task 8（database/knowledge） ✓
- spec §五 解析产物流水线 → Task 4 ✓
- spec §六 6 条联动：解析→数据库(Task 6)、解析→知识(Task 7)、数据库→生成(Task 7)、知识→原文(Task 7)、治理→库/生成（治理页已有变更影响分析，红条复用 dirtyManualRefs，未单列——见下）、目录轴(Task 8) ✓
- spec §七 角色简化管理员全开 → Task 1（role 改'管理员'） ✓
- spec §八 解析展示分层 → Task 3（目录选择器）+ Task 5（元素清单折叠）+ Task 4（流水线） ✓
- spec §十 实施分项 1-6 → 全覆盖 ✓

**注：** spec §六 的「治理→数据库/生成」联动，治理页已有「变更影响分析」展示影响手册数；数据库的 `flagManualDirty` 已作为变更入口触发生成红条，治理侧无需额外按钮。如需在治理变更审批通过时也触发 `markManualDirty`，可在 Task 6 Step 1 旁追加——当前设计已由数据库侧覆盖，不补。

**类型一致性：** `NP.store.selectedFolder`（{equipment}|null）、`pendingReview`（array）、`dirtyManualRefs`（number）、`newEntityIds`（array）；助手 `setFolder/markPendingReview/clearPendingReview/markManualDirty/clearManualDirty/markNewEntities` 在 Task 1 定义，Task 6/7/8 引用名称一致 ✓。

**占位符扫描：** 无 TBD/TODO，每步含完整代码或完整验证命令 ✓。
