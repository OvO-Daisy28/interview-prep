/* 采购文件活化平台 POC — 应用外壳与路由 */
(function () {
  const { createApp, ref, computed, onMounted, onUnmounted, watch, nextTick } = Vue;
  const M = window.MOCK;

  /* ---------------- 共享工具 ---------------- */
  window.NP = {
    // 打字机流式动画: stepCb(已输出文本), doneCb()
    stream(text, stepCb, doneCb, speed) {
      let i = 0;
      const sp = speed || 24;
      const timer = setInterval(() => {
        i += 2 + Math.floor((i % 3));
        if (i >= text.length) {
          stepCb(text);
          clearInterval(timer);
          doneCb && doneCb();
        } else {
          stepCb(text.slice(0, i));
        }
      }, sp);
      return timer;
    },
    // 模拟 AI 处理: steps=[{label, ms}], 逐步回调
    simulate(steps, onStep, onDone) {
      let idx = 0;
      function run() {
        if (idx >= steps.length) { onDone && onDone(); return; }
        onStep(idx, steps[idx]);
        setTimeout(() => { idx++; run(); }, steps[idx].ms);
      }
      run();
    },
    confTagType(c) { return c >= 0.95 ? 'success' : c >= 0.9 ? 'warning' : 'danger'; },
    contentTypeColor(t) {
      return { '操作步骤': 'primary', '注意事项': 'warning', '技术要求': 'danger', '描述说明': 'info' }[t] || 'info';
    },
    entityColor(t) { return (M.graph.entityColors || {})[t] || '#666'; },
    escapeHtml(s) {
      return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    },
    // 简易 diff: 按句子切分对比, 返回 [{t:'same|add|del', text}]
    diffText(oldText, newText) {
      const seg = s => s.split(/(?<=[。；;])/).filter(x => x.trim());
      const a = seg(oldText), b = seg(newText);
      const res = [];
      let i = 0, j = 0;
      while (i < a.length || j < b.length) {
        if (i < a.length && j < b.length && a[i] === b[j]) {
          res.push({ t: 'same', text: a[i] }); i++; j++;
        } else if (j < b.length && !a.includes(b[j])) {
          res.push({ t: 'add', text: b[j] }); j++;
        } else if (i < a.length && !b.includes(a[i])) {
          res.push({ t: 'del', text: a[i] }); i++;
        } else {
          if (i < a.length) { res.push({ t: 'del', text: a[i] }); i++; }
          if (j < b.length) { res.push({ t: 'add', text: b[j] }); j++; }
        }
      }
      return res;
    },
  };

  /* ---------------- 全局共享状态(跨页面) ---------------- */
  // 内容块审核状态在 内容解析页 与 内容数据库页 之间共享
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
    selectedFolder: null,          // 目录轴共享选中：{ equipment } | null
    pendingReview: [],             // 待复核内容块 id 列表（解析→数据库）
    dirtyManualRefs: 0,            // 被引用通用块变更数（数据库→生成）
    newEntityIds: [],              // 新入库图谱实体 id（解析→知识）
  });

  /* ---------------- 全局演示对话框 ---------------- */
  // 所有功能入口按钮统一打开有真实内容的对话框，不出现"死按钮"
  window.NP._dlg = Vue.reactive({ visible: false, title: '', body: '', width: '560px' });
  window.NP.showDialog = function (title, bodyHtml, width) {
    window.NP._dlg.title = title;
    window.NP._dlg.body = bodyHtml;
    window.NP._dlg.width = width || '560px';
    window.NP._dlg.visible = true;
  };
  window.NP.go = function (page) { location.hash = '#/' + page; };

  // 目录轴
  window.NP.setFolder = function (filter) { window.NP.store.selectedFolder = filter; };

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

  /* ---------------- 角色权限（RBAC，需求「使用权限规则」四级） ---------------- */
  // 能力矩阵：角色 → 具备的能力集合
  const ROLE_CAPS = {
    管理员: ['edit', 'export', 'approve', 'admin'],
    审核员: ['edit', 'export', 'approve'],
    编制员: ['edit', 'export'],
    浏览者: [],
  };
  window.NP.ROLE_CAPS = ROLE_CAPS;
  window.NP.can = function (cap) {
    const role = window.NP.store.role;
    return (ROLE_CAPS[role] || []).includes(cap);
  };

  /* ---------------- 路由定义 ---------------- */
  const ROUTES = [
    { key: 'dashboard', title: '工作台', icon: 'Odometer', step: null, divider: '看全局' },
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
  const FLOW_STEPS = ['内容解析', '内容数据库', '知识图谱', '手册生成'];

  /* ---------------- 根组件 ---------------- */
  const App = {
    template: `
    <div class="layout" :class="{ 'nav-collapsed': collapsed }">
      <aside class="sidebar" :class="{ collapsed }">
        <div class="logo">
          <div class="brand">
            <span class="brand-mark"><i></i><i></i><i></i></span>
            <div class="brand-copy">
              <div class="t1">采购文件活化平台</div>
              <div class="t2">CGN · 工程知识工作台</div>
            </div>
          </div>
          <button class="nav-toggle" type="button" :title="collapsed ? '展开导航' : '收起导航'" @click="toggleCollapse">
            <el-icon :size="16"><component :is="collapsed ? 'Expand' : 'Fold'" /></el-icon>
          </button>
        </div>
        <nav class="menu">
          <template v-for="(r, i) in routes" :key="r.key">
            <div v-if="r.divider" class="menu-divider">
              <span>{{ r.divider }}</span>
            </div>
            <div class="menu-item" :class="{active: route === r.key}" @click="go(r.key)" :title="collapsed ? r.title : ''">
              <el-icon class="menu-ic" :size="17"><component :is="r.icon" /></el-icon>
              <span class="menu-label">{{ r.title }}</span>
            </div>
          </template>
        </nav>
      </aside>
      <div class="main">
        <header class="topbar">
          <div class="page-title">{{ currentTitle }}</div>
          <div class="flow-steps">
            <div class="stage-bar">
              <div class="stage-track"><div class="stage-fill" :style="'width:' + (activeStep >= 0 ? Math.round(activeStep / (flowSteps.length - 1) * 100) : 0) + '%'"></div></div>
              <template v-for="(s, i) in flowSteps" :key="i">
                <div class="stage-node" :class="{done: activeStep >= 0 && i < activeStep, current: i === activeStep}" @click="goStep(i)" :title="s">
                  <span class="stage-dot">
                    <el-icon v-if="activeStep >= 0 && i < activeStep" :size="11"><Check /></el-icon>
                    <span v-else>{{ i + 1 }}</span>
                  </span>
                  <span class="stage-label">{{ s }}</span>
                </div>
              </template>
            </div>
          </div>
          <div class="user-chip" title="当前登录用户">
            <span class="uc-avatar"><el-icon :size="14"><User /></el-icon></span>
            <span class="uc-name">张工</span>
            <span class="uc-role">{{ store.role }}</span>
          </div>
        </header>
        <main class="content">
          <component :is="currentComp" />
        </main>
      </div>
      <el-dialog v-model="dlg.visible" :title="dlg.title" :width="dlg.width" append-to-body>
        <div v-html="dlg.body" style="line-height:1.9; font-size:13px;" class="dlg-body"></div>
        <template #footer>
          <el-button type="primary" @click="dlg.visible = false">关 闭</el-button>
        </template>
      </el-dialog>
    </div>`,
    setup() {
      const route = ref(location.hash.replace('#/', '') || 'dashboard');
      const routes = ROUTES;
      const flowSteps = FLOW_STEPS;
      const collapsed = ref(localStorage.getItem('np-nav-collapsed') === '1');
      function toggleCollapse() {
        collapsed.value = !collapsed.value;
        localStorage.setItem('np-nav-collapsed', collapsed.value ? '1' : '0');
      }
      const meta = M.meta;
      const dlg = window.NP._dlg;
      const store = window.NP.store;
      function sync() {
        const h = location.hash.replace('#/', '');
        if (ROUTES.some(r => r.key === h)) route.value = h;
      }
      onMounted(() => window.addEventListener('hashchange', sync));
      onUnmounted(() => window.removeEventListener('hashchange', sync));
      function go(k) { location.hash = '#/' + k; route.value = k; }
      const currentTitle = computed(() => (ROUTES.find(r => r.key === route.value) || {}).title || '');
      const activeStep = computed(() => {
        const r = ROUTES.find(r => r.key === route.value);
        return r && r.step !== null ? r.step : -1;
      });
      function goStep(i) {
        const r = ROUTES.find(r => r.step === i);
        if (r) go(r.key);
      }
      const currentComp = computed(() => window.PAGES[route.value] || window.PAGES.dashboard);
      return { route, routes, go, goStep, currentTitle, currentComp, activeStep, flowSteps, meta, dlg, store, collapsed, toggleCollapse };
    },
  };

  const app = createApp(App);
  app.use(ElementPlus, { locale: ElementPlusLocaleZhCn });
  for (const [name, comp] of Object.entries(ElementPlusIconsVue)) app.component(name, comp);
  for (const [name, comp] of Object.entries(window.PAGES || {})) app.component('page-' + name, comp);
  app.mount('#app');
})();
