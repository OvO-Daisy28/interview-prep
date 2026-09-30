/* P4 内容数据库: 多维检索 / 内容块详情 / 版本diff / 跨设备参数对比 */
window.PAGES = window.PAGES || {};
window.PAGES.database = {
  template: `
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
        <!-- 数据库概览 -->
        <div class="panel db-overview">
          <div class="gov-card" style="cursor:default"><div class="gv-num">{{ dbStats.total }}</div><div class="gv-lbl">内容块总数</div></div>
          <div class="gov-card" style="cursor:default"><div class="gv-num" style="color:var(--np-success)">{{ dbStats.common }}</div><div class="gv-lbl">通用块</div></div>
          <div class="gov-card" style="cursor:default"><div class="gv-num" style="color:var(--np-amber)">{{ dbStats.pending }}</div><div class="gv-lbl">待复核</div></div>
          <div class="gov-card" style="cursor:default"><div class="gv-num" style="color:var(--np-cyan)">{{ dbStats.versions }}</div><div class="gv-lbl">版本数</div></div>
        </div>
        <div class="panel">
          <div class="panel-title">多维组合检索 <span class="sub-text">常规检索 &lt;2s · 复杂组合检索 &lt;5s</span></div>
      <el-form inline size="small">
        <el-form-item label="设备编码"><el-input v-model="q.code" placeholder="如 PTR-001" style="width:120px" clearable /></el-form-item>
        <el-form-item label="设备类型">
          <el-select v-model="q.eqType" style="width:110px" clearable placeholder="全部">
            <el-option v-for="t in ['离心泵','容积泵','阀门','热交换器','容器']" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容类型">
          <el-select v-model="q.type" style="width:110px" clearable placeholder="全部">
            <el-option v-for="t in ['操作步骤','注意事项','技术要求','描述说明']" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词"><el-input v-model="q.kw" placeholder="内容块全文模糊匹配" style="width:180px" clearable @keyup.enter="doSearch" /></el-form-item>
        <el-form-item>
          <el-button size="small" text type="primary" @click="showAdvanced = !showAdvanced">
            {{ showAdvanced ? '收起高级 ▴' : '高级检索 ▾' }}<el-badge v-if="advancedCount > 0 && !showAdvanced" :value="advancedCount" type="info" style="margin-left:4px" />
          </el-button>
        </el-form-item>
        <div v-show="showAdvanced" style="border-top:1px dashed var(--np-border); padding-top:8px; margin-top:4px;">
          <el-form-item label="设备名称"><el-input v-model="q.eqName" placeholder="如 PTR冷却泵" style="width:120px" clearable /></el-form-item>
          <el-form-item label="系统代码"><el-input v-model="q.sysCode" placeholder="如 PTR" style="width:90px" clearable /></el-form-item>
          <el-form-item label="核安全">
            <el-select v-model="q.nuclear" style="width:110px" clearable placeholder="全部">
              <el-option v-for="n in ['核安全1级','核安全2级','核安全3级','非核级']" :key="n" :label="n" :value="n" />
            </el-select>
          </el-form-item>
          <el-form-item label="质保">
            <el-select v-model="q.qa" style="width:80px" clearable placeholder="全部">
              <el-option v-for="q in ['QA1','QA2','QA3']" :key="q" :label="q" :value="q" />
            </el-select>
          </el-form-item>
          <el-form-item label="厂家"><el-input v-model="q.mfr" placeholder="生产厂家" style="width:120px" clearable /></el-form-item>
          <el-form-item label="通用性">
            <el-select v-model="q.common" style="width:90px" clearable placeholder="全部">
              <el-option label="通用" value="1" /><el-option label="专用" value="0" />
            </el-select>
          </el-form-item>
          <el-form-item label="章节路径"><el-input v-model="q.chapter" placeholder="如 3.7" style="width:100px" clearable /></el-form-item>
          <el-form-item label="参数名称"><el-input v-model="q.param" placeholder="如 额定流量" style="width:110px" clearable /></el-form-item>
          <el-form-item label="备件名称"><el-input v-model="q.spare" placeholder="备件关键字" style="width:110px" clearable /></el-form-item>
        </div>
        <el-form-item>
          <el-button type="primary" icon="Search" @click="doSearch">检索</el-button>
          <el-button @click="reset">重置</el-button>
          <el-button icon="Star" @click="saveSearch" :disabled="!hasFilter">保存常用检索</el-button>
          <el-button icon="Files" :disabled="!can('admin')" @click="enumVisible = true">枚举字典</el-button>
          <el-button icon="DataAnalysis" @click="compareVisible = true">跨设备对比</el-button>
        </el-form-item>
      </el-form>
      <div v-if="savedSearches.length" style="margin-top:4px; display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
        <span class="sub-text">常用检索：</span>
        <el-tag v-for="(s, i) in savedSearches" :key="i" size="small" effect="plain" closable style="cursor:pointer" @click="loadSearch(s)" @close="savedSearches.splice(i, 1)">{{ s.name }}</el-tag>
      </div>
      <div v-if="searchMs !== null" class="search-result">命中 <b>{{ filtered.length }}</b> 条 · 响应 <b>{{ searchMs }}ms</b> · 12 维组合检索（§142）</div>
    </div>

    <div class="panel">
      <div class="panel-title"><span>内容块</span><span class="pt-badge">{{ filtered.length }} 条</span></div>
      <el-table :data="paged" border size="small" @row-click="openDetail" highlight-current-row style="cursor:pointer">
          <el-table-column label="ID" width="100">
            <template #default="{row}"><span class="mono">{{ row.id }}</span><el-badge v-if="isPending(row.id)" value="待复核" type="warning" style="margin-left:4px" /></template>
          </el-table-column>
        <el-table-column label="DMC 编码" min-width="230">
          <template #default="{row}"><span class="dmc">{{ row.dmc }}</span></template>
        </el-table-column>
        <el-table-column prop="section" label="所属章节" width="170" show-overflow-tooltip />
        <el-table-column label="内容类型" width="95" align="center">
          <template #default="{row}"><el-tag size="small" :type="typeColor(row.contentType)">{{ row.contentType }}</el-tag></template>
        </el-table-column>
        <el-table-column label="通用/专用" width="90" align="center">
          <template #default="{row}">
            <el-tag size="small" :type="row.isCommon ? 'success' : 'info'" effect="plain">{{ row.isCommon ? '通用' : '专用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="60" align="center">
          <template #default="{row}">V{{ row.version }}</template>
        </el-table-column>
        <el-table-column label="内容摘要" min-width="260" show-overflow-tooltip>
          <template #default="{row}"><span v-html="hl(row.content)"></span></template>
        </el-table-column>
      </el-table>
      <el-pagination style="margin-top:10px; justify-content:flex-end;" layout="total, prev, pager, next" :total="filtered.length"
                     :page-size="pageSize" v-model:current-page="page" />
    </div>

    <!-- 内容块详情抽屉 -->
    <el-drawer v-model="detailVisible" size="640px" :title="current ? current.id + ' · ' + current.section : ''">
      <template v-if="current">
        <div style="display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap;">
          <el-tag :type="typeColor(current.contentType)" size="small">{{ current.contentType }}</el-tag>
          <el-tag v-if="current.safetyLevel" type="danger" size="small" effect="plain">{{ current.safetyLevel }}</el-tag>
          <el-tag :type="current.isCommon ? 'success' : 'info'" size="small" effect="plain">{{ current.isCommon ? '通用（跨手册共享引用）' : '专用' }}</el-tag>
          <el-tag size="small" effect="plain">V{{ current.version }}</el-tag>
        </div>
        <div class="dmc" style="margin-bottom:8px;">DMC: {{ current.dmc }}</div>
        <div class="original-view" style="max-height:180px; overflow:auto;">{{ current.content }}</div>
        <el-descriptions :column="1" border size="small" style="margin-top:12px">
          <el-descriptions-item label="章节路径">{{ current.chapterPath }}</el-descriptions-item>
          <el-descriptions-item label="来源文档">{{ current.source.doc }}</el-descriptions-item>
          <el-descriptions-item label="AI 置信度">{{ current.aiConfidence }}（{{ current.reviewStatus }}）</el-descriptions-item>
        </el-descriptions>

        <div class="panel" style="margin-top:14px">
          <div class="panel-title">显式关联关系</div>
          <el-table :data="relations" size="small" border>
            <el-table-column prop="type" label="关系类型" width="100">
              <template #default="{row}"><el-tag size="small" effect="plain">{{ row.type }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="target" label="关联对象" min-width="200" />
            <el-table-column prop="desc" label="说明" min-width="160" />
          </el-table>
          <div class="sub-text" style="margin-top:6px">通过关联表显式建立，不依赖隐式文本匹配；覆盖引用 / 从属 / 顺序 / 交叉引用四类关系。</div>
        </div>

        <div class="panel">
          <div class="panel-title">
            <span>版本管理</span>
            <el-button size="small" type="primary" plain @click="diffVisible = true">版本对比</el-button>
              <el-button v-if="current.isCommon" size="small" type="warning" plain @click="flagManualDirty(current)">模拟通用块变更</el-button>
          </div>
          <el-timeline style="padding-left:4px">
            <el-timeline-item v-for="v in versions" :key="v.v" :timestamp="v.time + ' · ' + v.user" :type="v.v === versions.length ? 'primary' : ''">
              <b>V{{ v.v }}</b> · {{ v.reason }}
              <el-button v-if="v.v !== versions.length" size="small" text type="warning" :disabled="!can('admin')" style="margin-left:8px" @click="rollback(v)">回退到此版本</el-button>
            </el-timeline-item>
          </el-timeline>
          <el-alert v-if="current.isCommon" type="warning" :closable="false" show-icon
            title="该通用内容块已被 3 份手册引用，修改将触发影响范围分析（见内容治理）。" />
        </div>
      </template>
    </el-drawer>

    <!-- 版本 diff -->
    <el-dialog v-model="diffVisible" title="版本对比 · V1 → V2" width="700px">
      <div style="display:flex; gap:14px;">
        <div style="flex:1">
          <div class="sub-text" style="margin-bottom:6px">V1（2026-07-20 王工）</div>
          <div class="original-view">
            <span v-for="(d, i) in diffOld" :key="i" class="diff-line" :class="'diff-' + d.t">{{ d.text }}</span>
          </div>
        </div>
        <div style="flex:1">
          <div class="sub-text" style="margin-bottom:6px">V2（2026-07-28 李工）</div>
          <div class="original-view">
            <span v-for="(d, i) in diffNew" :key="i" class="diff-line" :class="'diff-' + d.t">{{ d.text }}</span>
          </div>
        </div>
      </div>
      <div class="sub-text" style="margin-top:8px">修改原因：按审查意见补充润滑检查要求 · 新增 <span style="color:#1e7b44">绿色</span> / 删除 <span style="color:#b03a2e">红色</span></div>
    </el-dialog>

    <!-- 跨设备参数对比 -->
    <el-dialog v-model="compareVisible" title="跨设备参数对比" width="760px">
      <el-table :data="compareRows" border size="small">
        <el-table-column prop="name" label="参数名称" width="130" fixed />
        <el-table-column v-for="d in compareDevices" :key="d.code" :label="d.name + '（' + d.code + '）'" min-width="150" align="center">
          <template #default="{row}">{{ row[d.code] || '—' }}</template>
        </el-table-column>
      </el-table>
      <div class="sub-text" style="margin-top:8px">同类参数并列展示，便于工程师横向对比；差异超过 ±20% 的参数建议重点复核。</div>
    </el-dialog>

    <!-- 枚举字典管理（需求§40/§139） -->
    <el-dialog v-model="enumVisible" title="枚举字典在线维护" width="720px">
      <div style="margin-bottom:10px; display:flex; align-items:center; gap:10px;">
        <el-select v-model="enumActive" size="small" style="width:240px">
          <el-option v-for="e in enumDicts" :key="e.key" :label="e.name + '（' + e.values.length + '）'" :value="e.key" />
        </el-select>
        <el-button size="small" type="primary" icon="Plus" @click="addEnum">新增枚举值</el-button>
        <span class="sub-text">管理员在线维护，新增设备类型无需重构表结构（弹性设计 §138）</span>
      </div>
      <el-table :data="currentEnumValues" border size="small">
        <el-table-column prop="code" label="编码" width="120">
          <template #default="{row}"><span class="mono">{{ row.code }}</span></template>
        </el-table-column>
        <el-table-column prop="label" label="显示名称" min-width="160" />
        <el-table-column prop="used" label="引用次数" width="90" align="center">
          <template #default="{row}"><el-tag size="small" effect="plain">{{ row.used }}</el-tag></template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{row}"><el-tag size="small" :type="row.status === '启用' ? 'success' : 'info'">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="{row}">
            <el-button size="small" text type="primary" @click="toggleEnum(row)">{{ row.status === '启用' ? '停用' : '启用' }}</el-button>
            <el-button size="small" text type="danger" :disabled="row.used > 0" @click="delEnum(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="sub-text" style="margin-top:8px">已被引用（引用次数>0）的枚举值不可删除，仅可停用，保证数据一致性。</div>
    </el-dialog>
      </div>
    </div>
  </div>`,

  setup() {
    const { ref, computed } = Vue;
    const M = window.MOCK;
    const q = ref({ code: '', eqType: '', eqName: '', sysCode: '', nuclear: '', qa: '', mfr: '', type: '', common: '', chapter: '', param: '', spare: '', kw: '' });
    const showAdvanced = ref(false);
    const advancedCount = computed(() => Object.entries(q.value).filter(([k,v]) => v && !['code','eqType','type','kw'].includes(k)).length);
    const dbStats = { total: window.NP.store.blocks.length, common: window.NP.store.blocks.filter(b=>b.isCommon).length, pending: window.NP.store.pendingReview.length, versions: M.versionDemo.versions.length };
    const searchMs = ref(null);
    const page = ref(1);
    const pageSize = 10;
    // 设备级上下文（当前库为 PTR 冷却泵）：用于设备级检索维度的匹配
    const eqMeta = { eqType: '离心泵', eqName: 'PTR冷却泵', sysCode: 'PTR', nuclear: '核安全3级', qa: 'QA1', mfr: '重庆水泵厂' };
    const hasFilter = computed(() => Object.values(q.value).some(v => v));
    const savedSearches = ref([
      { name: '联轴器·注意事项', q: { type: '注意事项', kw: '联轴器', code:'', eqType:'', eqName:'', sysCode:'', nuclear:'', qa:'', mfr:'', common:'', chapter:'', param:'', spare:'' } },
    ]);
    function saveSearch() {
      const name = Object.entries(q.value).filter(([, v]) => v).map(([k, v]) => `${k}=${v}`).join(' / ');
      savedSearches.value.push({ name: name.slice(0, 28) + (name.length > 28 ? '…' : ''), q: { ...q.value } });
      ElementPlus.ElMessage.success('已保存为常用检索');
    }
    function loadSearch(s) { q.value = { ...s.q }; doSearch(); }

    const isPending = (id) => window.NP.store.pendingReview.includes(id);
    const docTree = window.NP.store.docTree;
    function onFolderClick(data) {
      if (data.filter) { window.NP.setFolder(data.filter); q.value.eqName = data.filter.equipment; doSearch(); }
      else { window.NP.setFolder(null); q.value.eqName = ''; doSearch(); }
    }
    const filtered = computed(() => window.NP.store.blocks.filter(b => {
      if (q.value.code && !/ptr/i.test(q.value.code)) return false;
      if (q.value.eqType && eqMeta.eqType !== q.value.eqType) return false;
      if (q.value.eqName && !eqMeta.eqName.includes(q.value.eqName)) return false;
      if (q.value.sysCode && !eqMeta.sysCode.includes(q.value.sysCode.toUpperCase())) return false;
      if (q.value.nuclear && eqMeta.nuclear !== q.value.nuclear) return false;
      if (q.value.qa && eqMeta.qa !== q.value.qa) return false;
      if (q.value.mfr && !eqMeta.mfr.includes(q.value.mfr)) return false;
      if (q.value.type && b.contentType !== q.value.type) return false;
      if (q.value.common !== '' && String(b.isCommon ? 1 : 0) !== q.value.common) return false;
      if (q.value.chapter && !b.chapterPath.includes(q.value.chapter)) return false;
      if (q.value.param && !window.MOCK.params.some(p => p.name.includes(q.value.param) && p.component)) return false;
      if (q.value.spare && !b.content.includes(q.value.spare)) return false;
      if (q.value.kw && !b.content.includes(q.value.kw)) return false;
      const sf = window.NP.store.selectedFolder;
      if (sf && sf.equipment && eqMeta.eqName !== sf.equipment) return false;
      return true;
    }));
    const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize));
    function doSearch() {
      const complex = ['type', 'chapter', 'kw', 'param', 'spare'].some(k => q.value[k]);
      searchMs.value = complex ? 860 + Math.floor(Math.random() * 300) : 240 + Math.floor(Math.random() * 160);
      page.value = 1;
    }
    // 全文检索命中高亮：转义后包裹关键词（kw/spare/param）为 <mark>
    function hl(text) {
      const terms = [q.value.kw, q.value.spare, q.value.param].filter(Boolean);
      if (!text) return '';
      let s = String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      for (const t of terms) {
        const re = new RegExp('(' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        s = s.replace(re, '<mark>$1</mark>');
      }
      return s;
    }
    function reset() { q.value = { code: '', eqType: '', eqName: '', sysCode: '', nuclear: '', qa: '', mfr: '', type: '', common: '', chapter: '', param: '', spare: '', kw: '' }; searchMs.value = null; page.value = 1; }

    // 详情
    const detailVisible = ref(false);
    const current = ref(null);
    const relations = ref([]);
    const REL_POOL = [
      { type: '引用', target: 'CB-0021 安全操作说明', desc: '操作步骤引用注意事项' },
      { type: '从属', target: 'PTR冷却泵 / 泵本体', desc: '参数从属于部件' },
      { type: '顺序', target: '下一条操作步骤', desc: '操作先后顺序' },
      { type: '交叉引用', target: '3.5.2 检查及维修', desc: '指向维修章节具体步骤' },
    ];
    function openDetail(row) {
      current.value = row;
      relations.value = REL_POOL.slice(0, 2 + (parseInt(row.id.slice(3)) % 3));
      detailVisible.value = true;
    }

    // 版本 diff（使用预置演示版本对）
    const versions = M.versionDemo.versions;
    const diffVisible = ref(false);
    const diffs = window.NP.diffText(versions[0].content, versions[1].content);
    const diffOld = diffs.filter(d => d.t !== 'add');
    const diffNew = diffs.filter(d => d.t !== 'del');
    function rollback(v) {
      ElementPlus.ElMessageBox.confirm(`确定将内容块回退到 V${v.v} 吗？当前版本将保留为新历史版本。`, '版本回退', { type: 'warning' })
        .then(() => ElementPlus.ElMessage.success(`已回退到 V${v.v}，生成新版本 V3`))
        .catch(() => {});
    }
    function flagManualDirty(row) {
      window.NP.markManualDirty(3);
      ElementPlus.ElMessage.warning('该通用块被 3 份手册引用，已通知手册生成页');
    }

    // 参数对比
    const compareVisible = ref(false);
    const compareDevices = M.compareDevices;
    const compareRows = Object.keys(compareDevices[0].params).map(name => {
      const row = { name };
      compareDevices.forEach(d => { row[d.code] = d.params[name]; });
      return row;
    });

    // 枚举字典管理（需求§40/§139：管理员在线维护标准枚举值）
    const enumVisible = ref(false);
    const enumDicts = ref([
      { key: 'deviceType', name: '设备类型', values: [
        { code: 'PUMP_CENT', label: '离心泵', used: 47, status: '启用' },
        { code: 'PUMP_POS', label: '容积泵', used: 12, status: '启用' },
        { code: 'VALVE', label: '阀门', used: 31, status: '启用' },
        { code: 'HE', label: '热交换器', used: 18, status: '启用' },
        { code: 'TANK', label: '容器', used: 9, status: '启用' },
      ]},
      { key: 'nuclear', name: '核安全等级', values: [
        { code: 'N1', label: '核安全1级', used: 6, status: '启用' },
        { code: 'N2', label: '核安全2级', used: 11, status: '启用' },
        { code: 'N3', label: '核安全3级', used: 23, status: '启用' },
        { code: 'NC', label: '非核级', used: 38, status: '启用' },
      ]},
      { key: 'qa', name: '质保等级', values: [
        { code: 'QA1', label: 'QA1', used: 40, status: '启用' },
        { code: 'QA2', label: 'QA2', used: 22, status: '启用' },
        { code: 'QA3', label: 'QA3', used: 14, status: '启用' },
      ]},
      { key: 'contentType', name: '内容类型', values: [
        { code: 'OP', label: '操作步骤', used: 28, status: '启用' },
        { code: 'CAU', label: '注意事项', used: 4, status: '启用' },
        { code: 'REQ', label: '技术要求', used: 7, status: '启用' },
        { code: 'DESC', label: '描述说明', used: 40, status: '启用' },
      ]},
      { key: 'seismic', name: '抗震类别', values: [
        { code: 'S1', label: '抗震I类', used: 33, status: '启用' },
        { code: 'S2', label: '抗震II类', used: 19, status: '启用' },
        { code: 'NS', label: '非抗震', used: 24, status: '启用' },
      ]},
    ]);
    const enumActive = ref('deviceType');
    const currentEnumValues = computed(() => (enumDicts.value.find(e => e.key === enumActive.value) || {}).values || []);
    function addEnum() {
      ElementPlus.ElMessageBox.prompt('输入枚举显示名称', '新增枚举值', { inputPattern: /.+/, inputErrorMessage: '不能为空' })
        .then(({ value }) => {
          const cur = enumDicts.value.find(e => e.key === enumActive.value);
          cur.values.push({ code: 'NEW_' + Date.now().toString(36).slice(-4).toUpperCase(), label: value, used: 0, status: '启用' });
          ElementPlus.ElMessage.success('枚举值已新增并启用，后续入库即可选用');
        }).catch(() => {});
    }
    function toggleEnum(row) {
      row.status = row.status === '启用' ? '停用' : '启用';
      ElementPlus.ElMessage.success('枚举值已' + (row.status === '启用' ? '启用' : '停用') + (row.status === '停用' ? '，新内容不再可选，历史数据保留' : ''));
    }
    function delEnum(row) {
      const cur = enumDicts.value.find(e => e.key === enumActive.value);
      cur.values = cur.values.filter(v => v.code !== row.code);
      ElementPlus.ElMessage.success('枚举值已删除');
    }

    return {
      q, showAdvanced, advancedCount, dbStats, filtered, paged, page, pageSize, searchMs, doSearch, reset, hasFilter, savedSearches, saveSearch, loadSearch, hl,
      docTree, onFolderClick,
      detailVisible, current, relations, openDetail, isPending, flagManualDirty,
      versions, diffVisible, diffOld, diffNew, rollback,
      compareVisible, compareDevices, compareRows,
      enumVisible, enumDicts, enumActive, currentEnumValues, addEnum, toggleEnum, delEnum,
      typeColor: window.NP.contentTypeColor, can: window.NP.can,
    };
  },
};
