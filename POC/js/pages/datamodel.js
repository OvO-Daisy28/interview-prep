/* 数据模型（前端功能）：四层数据浏览 + 扩展字段管理（弹性设计）+ 关联关系浏览（需求§136-140） */
window.PAGES = window.PAGES || {};
window.PAGES.datamodel = {
  template: `
  <div>
    <el-tabs v-model="tab" type="border-card">
      <!-- ========== 四层数据浏览 ========== -->
      <el-tab-pane label="四层数据浏览" name="browse">
        <div class="layer-tabs">
          <div v-for="(ly, i) in layerList" :key="ly.key" class="layer-tab" :class="{active: layer === ly.key}" @click="pickLayer(ly.key)">
            <span class="lt-no">{{ i + 1 }}</span>
            <span class="lt-name">{{ ly.name }}</span>
            <span class="lt-cnt">{{ layerCount(ly.key) }}</span>
          </div>
          <span class="sub-text" style="margin-left:auto">四层数据模型：文档级 → 设备级 → 参数级 → 内容块级，逐层聚合（§137）</span>
        </div>

        <el-row :gutter="14" style="margin-top:12px">
          <el-col :span="14">
            <div class="panel" style="margin:0;">
              <div class="panel-title">
                <span>{{ currentLayer.name }}实例</span>
                <span class="pt-badge">{{ layerInstances.length }} 条</span>
              </div>
              <el-table :data="layerInstances" border size="small" highlight-current-row @row-click="onPick" max-height="440">
                <el-table-column v-for="c in currentLayer.cols" :key="c.prop" :prop="c.prop" :label="c.label" :min-width="c.width || 120" :formatter="c.formatter" :class-name="c.className" show-overflow-tooltip />
              </el-table>
              <div class="sub-text" style="margin-top:6px">点击行查看详情与关联关系（内容块级含引用/从属/顺序/交叉引用）</div>
            </div>
          </el-col>
          <el-col :span="10">
            <div class="panel" style="margin:0; max-height:520px; overflow:auto;">
              <div class="panel-title"><span>实例详情</span><span class="sub-text">{{ picked ? currentLayer.name + ' · ' + pickedLabel : '点击左侧实例' }}</span></div>
              <template v-if="picked">
                <el-descriptions :column="1" border size="small">
                  <el-descriptions-item v-for="c in currentLayer.cols" :key="c.prop" :label="c.label">{{ cellText(c, picked) }}</el-descriptions-item>
                </el-descriptions>
                <template v-if="layer === 'block'">
                  <div class="panel-title" style="margin-top:14px"><span>关联关系</span><span class="pt-badge">{{ pickedRels.length }} 条</span></div>
                  <div v-for="r in pickedRels" :key="r.type+r.target" class="rel-row" style="margin-bottom:6px;">
                    <el-tag size="small" :type="relTag(r.type)" effect="plain">{{ r.type }}</el-tag>
                    <span style="margin-left:6px; font-size:12px;">{{ r.target }}</span>
                    <div class="sub-text" style="font-size:11px;">{{ r.desc }}</div>
                  </div>
                  <el-button size="small" type="primary" plain style="margin-top:6px;width:100%" @click="goRelations(picked)">在关联浏览器中展开</el-button>
                </template>
              </template>
              <el-empty v-else description="选择左侧实例查看详情" :image-size="70" />
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ========== 扩展字段管理（弹性设计 §138） ========== -->
      <el-tab-pane label="扩展字段管理" name="ext">
        <div class="sub-text" style="margin-bottom:12px">弹性设计：核心字段固定，扩展字段随设备类型自定义（§138）。新增设备特性无需重构表结构，管理员在线维护。</div>
        <el-row :gutter="14">
          <el-col :span="9">
            <div class="panel" style="margin:0;">
              <div class="panel-title"><span>设备类型</span></div>
              <div v-for="et in extEquipTypes" :key="et.code" class="ext-type" :class="{active: extEquip === et.code}" @click="extEquip = et.code">
                <el-icon color="var(--np-primary)"><Cpu /></el-icon>
                <div style="flex:1"><b>{{ et.name }}</b><div class="sub-text" style="font-size:11px">核心 {{ et.coreCount }} · 扩展 {{ extFields(et.code).length }}</div></div>
                <el-icon v-if="extEquip === et.code" color="var(--np-primary)"><ArrowRight /></el-icon>
              </div>
            </div>
          </el-col>
          <el-col :span="15">
            <div class="panel" style="margin:0;">
              <div class="panel-title"><span>{{ extEquipName }} · 字段定义</span><el-button size="small" type="primary" icon="Plus" :disabled="!can('admin')" @click="extAddVisible = true">新增扩展字段</el-button></div>
              <div class="sub-text" style="margin-bottom:8px">核心字段（只读，保证数据完整性）</div>
              <div class="ext-fields">
                <span v-for="cf in extCoreFields" :key="cf" class="ext-field core"><el-icon><Lock /></el-icon>{{ cf }}</span>
              </div>
              <div class="sub-text" style="margin:14px 0 8px;">扩展字段（弹性预留，可增删）</div>
              <el-table :data="extFields(extEquip)" border size="small">
                <el-table-column prop="name" label="字段名" min-width="140"><template #default="{row}"><span class="mono">{{ row.name }}</span></template></el-table-column>
                <el-table-column prop="type" label="类型" width="120"><template #default="{row}"><el-tag size="small" effect="plain">{{ row.type }}</el-tag></template></el-table-column>
                <el-table-column prop="default" label="默认值" width="110" />
                <el-table-column prop="used" label="已填充" width="80" align="center"><template #default="{row}"><el-tag size="small" :type="row.used ? 'success' : 'info'">{{ row.used }}</el-tag></template></el-table-column>
                <el-table-column label="操作" width="80" align="center"><template #default="{row}"><el-button size="small" text type="danger" :disabled="!can('admin') || row.used > 0" @click="delExt(row)">删除</el-button></template></el-table-column>
              </el-table>
              <el-alert type="info" :closable="false" show-icon style="margin-top:10px"
                title="已被填充数据的扩展字段不可删除，保证数据一致性；新增字段对历史数据以默认值回填。" />
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ========== 关联关系浏览 ========== -->
      <el-tab-pane label="关联关系浏览" name="rel">
        <div class="sub-text" style="margin-bottom:12px">显式关联关系（§140）：通过关联表建立，不依赖隐式文本匹配。覆盖引用 / 从属 / 顺序 / 交叉引用四类。</div>
        <el-row :gutter="14">
          <el-col :span="9">
            <div class="panel" style="margin:0;">
              <div class="panel-title"><span>选择内容块</span><span class="pt-badge">{{ blocks.length }}</span></div>
              <el-input v-model="relKw" size="small" placeholder="按 ID/内容检索" clearable style="margin-bottom:8px" />
              <div style="max-height:440px; overflow:auto;">
                <div v-for="b in relBlocks" :key="b.id" class="ext-type" :class="{active: relBlock === b.id}" @click="relBlock = b.id">
                  <span class="mono" style="font-size:11px">{{ b.id }}</span>
                  <span style="font-size:11px; color:var(--np-text-sub); margin-left:6px">{{ b.contentType }}</span>
                </div>
              </div>
            </div>
          </el-col>
          <el-col :span="15">
            <div class="panel" style="margin:0;">
              <div class="panel-title"><span>{{ relPicked ? relPicked.id : '—' }} 的关联网络</span><span class="pt-badge">{{ relOfPicked.length }} 条</span></div>
              <template v-if="relPicked">
                <div v-for="r in relOfPicked" :key="r.type+r.target" class="rel-net-row">
                  <el-tag size="small" :type="relTag(r.type)">{{ r.type }}</el-tag>
                  <span class="mono" style="margin:0 8px;">{{ relPicked.id }}</span>
                  <el-icon color="#7a8699"><Right /></el-icon>
                  <span class="mono" style="margin:0 8px;">{{ r.target }}</span>
                  <span class="sub-text" style="margin-left:auto; font-size:11px;">{{ r.desc }}</span>
                </div>
                <el-alert type="success" :closable="false" show-icon style="margin-top:10px"
                  :title="'关联表 CB_RELATION 显式建立：' + relPicked.id + ' → 共 ' + relOfPicked.length + ' 条关联，覆盖 ' + [...new Set(relOfPicked.map(r=>r.type))].join(' / ')" />
              </template>
              <el-empty v-else description="选择左侧内容块查看关联网络" :image-size="80" />
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>
    </el-tabs>

    <!-- 新增扩展字段弹窗 -->
    <el-dialog v-model="extAddVisible" title="新增扩展字段" width="460px">
      <el-form label-width="90px" size="small">
        <el-form-item label="所属设备" required><el-input :model-value="extEquipName" disabled /></el-form-item>
        <el-form-item label="字段名" required><el-input v-model="extNew.name" placeholder="如 设计压力" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="extNew.type" style="width:100%">
            <el-option v-for="t in ['VARCHAR(200)','DECIMAL(10,2)','INT','DATETIME','TEXT','ENUM']" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="默认值"><el-input v-model="extNew.default" placeholder="历史数据回填值" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="extAddVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!can('admin')" @click="saveExt">保存</el-button>
      </template>
    </el-dialog>
  </div>`,
  setup() {
    const { ref, computed } = Vue;
    const M = window.MOCK;
    const blocks = window.NP.store.blocks;
    const can = window.NP.can;
    const tab = ref('browse');

    // ---- 四层数据浏览 ----
    // col.formatter 采用 el-table 官方签名 (row, column, cellValue) => string（纯文本，避免 v-html slot）
    const layers = {
      doc: { name: '文档级', cols: [
        { prop: 'name', label: '文档名称', width: 220 },
        { prop: 'type', label: '类型', width: 80 },
        { prop: 'equipment', label: '设备', width: 110 },
        { prop: 'manufacturer', label: '厂家', width: 130 },
        { prop: 'pages', label: '页数', width: 60 },
      ]},
      equipment: { name: '设备级', cols: [
        { prop: 'code', label: '设备编码', width: 100 },
        { prop: 'name', label: '设备名称', width: 140 },
        { prop: 'type', label: '类型', width: 80 },
        { prop: 'nuclear', label: '核安全', width: 90 },
        { prop: 'qa', label: '质保', width: 70 },
        { prop: 'manufacturer', label: '厂家', width: 140 },
      ]},
      param: { name: '参数级', cols: [
        { prop: 'name', label: '参数名称', width: 120 },
        { prop: 'value', label: '数值', width: 80 },
        { prop: 'unit', label: '单位', width: 70 },
        { prop: 'category', label: '分类', width: 90 },
        { prop: 'component', label: '所属部件', width: 100 },
      ]},
      block: { name: '内容块级', cols: [
        { prop: 'id', label: 'ID', width: 90, className: 'col-mono' },
        { prop: 'contentType', label: '类型', width: 90 },
        { prop: 'isCommon', label: '通用', width: 70, formatter: (r) => r.isCommon ? '通用' : '专用' },
        { prop: 'content', label: '内容摘要', width: 220, formatter: (r) => (r.content || '').slice(0, 24) + '…' },
      ]},
    };
    const layerList = [{ key: 'doc', name: '文档级' }, { key: 'equipment', name: '设备级' }, { key: 'param', name: '参数级' }, { key: 'block', name: '内容块级' }];
    const layer = ref('doc');
    const currentLayer = computed(() => layers[layer.value]);

    const equipInstances = [
      { code: 'PTR-001', name: 'PTR冷却泵', type: '离心泵', nuclear: '核安全3级', qa: 'QA1', manufacturer: '重庆水泵厂(CQPI)' },
      { code: 'RRI-002', name: 'RRI冷却泵', type: '离心泵', nuclear: '核安全3级', qa: 'QA1', manufacturer: '重庆水泵厂(CQPI)' },
      { code: 'CEF-003', name: 'CEF补水泵', type: '离心泵', nuclear: '非核级', qa: 'QA3', manufacturer: '上海凯泉' },
      { code: 'ASG-004', name: 'ASG辅助给水泵', type: '离心泵', nuclear: '核安全2级', qa: 'QA2', manufacturer: '沈阳鼓风机集团' },
      { code: 'RCV-005', name: 'RCV上充泵', type: '容积泵', nuclear: '核安全3级', qa: 'QA1', manufacturer: 'Flowserve' },
    ];
    const layerInstances = computed(() => {
      if (layer.value === 'doc') return M.docs;
      if (layer.value === 'equipment') return equipInstances;
      if (layer.value === 'param') return M.params;
      return blocks.slice(0, 60);
    });
    function layerCount(k) {
      if (k === 'doc') return M.docs.length;
      if (k === 'equipment') return equipInstances.length;
      if (k === 'param') return M.params.length;
      return blocks.length;
    }
    const picked = ref(null);
    const pickedLabel = computed(() => {
      if (!picked.value) return '';
      return picked.value.name || picked.value.id || picked.value.code || '';
    });
    function pickLayer(k) { layer.value = k; picked.value = null; }
    function onPick(row) { picked.value = row; }
    function cellText(c, row) {
      if (!row) return '—';
      if (c.formatter) return c.formatter(row);
      const v = row[c.prop];
      return v == null || v === '' ? '—' : v;
    }

    // 关联关系（内容块）
    const REL_POOL = [
      { type: '引用', target: 'CB-0021 安全操作说明', desc: '操作步骤引用注意事项' },
      { type: '从属', target: 'PTR冷却泵 / 泵本体', desc: '参数/部件从属于设备' },
      { type: '顺序', target: '下一条操作步骤', desc: '操作先后顺序' },
      { type: '交叉引用', target: '3.5.2 检查及维修', desc: '指向维修章节具体步骤' },
    ];
    const pickedRels = computed(() => {
      if (!picked.value || layer.value !== 'block') return [];
      const n = 2 + (parseInt((picked.value.id || 'CB-0000').slice(3)) % 3);
      return REL_POOL.slice(0, n);
    });
    function relTag(t) { return { 引用: 'success', 从属: 'primary', 顺序: 'warning', 交叉引用: 'danger' }[t] || ''; }
    function goRelations(b) { tab.value = 'rel'; relBlock.value = b.id; }

    // ---- 扩展字段管理 ----
    const extEquipTypes = [
      { code: 'pump', name: '离心泵', coreCount: 9 },
      { code: 'vol', name: '容积泵', coreCount: 9 },
      { code: 'valve', name: '阀门', coreCount: 8 },
      { code: 'he', name: '热交换器', coreCount: 7 },
    ];
    const extEquip = ref('pump');
    const extEquipName = computed(() => extEquipTypes.find(e => e.code === extEquip.value).name);
    const extCoreFields = ['设备编码', '设备名称', '设备类型', '核安全等级', '质保等级', '抗震类别', '系统代码', '生产厂家', '投运日期'];
    const extData = ref({
      pump: [
        { name: 'designPressure', type: 'DECIMAL(10,2)', default: '0.0', used: 4 },
        { name: 'operateTemp', type: 'DECIMAL(10,2)', default: '0.0', used: 4 },
        { name: 'ratedFlow', type: 'VARCHAR(200)', default: '—', used: 5 },
      ],
      vol: [{ name: 'displacement', type: 'DECIMAL(10,2)', default: '0.0', used: 1 }],
      valve: [{ name: 'dnSize', type: 'INT', default: '0', used: 2 }],
      he: [],
    });
    function extFields(code) { return extData.value[code] || []; }
    const extAddVisible = ref(false);
    const extNew = ref({ name: '', type: 'VARCHAR(200)', default: '' });
    function saveExt() {
      if (!extNew.value.name.trim()) { ElementPlus.ElMessage.warning('请填写字段名'); return; }
      extData.value[extEquip.value] = [...(extData.value[extEquip.value] || []), { ...extNew.value, used: 0 }];
      extAddVisible.value = false;
      extNew.value = { name: '', type: 'VARCHAR(200)', default: '' };
      ElementPlus.ElMessage.success('扩展字段已新增，历史数据按默认值回填，无需重构表结构');
    }
    function delExt(row) {
      extData.value[extEquip.value] = extData.value[extEquip.value].filter(f => f.name !== row.name);
      ElementPlus.ElMessage.success('扩展字段已删除');
    }

    // ---- 关联关系浏览 ----
    const relKw = ref('');
    const relBlock = ref(null);
    const relBlocks = computed(() => blocks.filter(b => !relKw.value || b.id.includes(relKw.value) || b.content.includes(relKw.value)).slice(0, 50));
    const relPicked = computed(() => blocks.find(b => b.id === relBlock.value));
    const relOfPicked = computed(() => {
      if (!relPicked.value) return [];
      const n = 2 + (parseInt((relPicked.value.id || 'CB-0000').slice(3)) % 3);
      return REL_POOL.slice(0, n);
    });

    return {
      tab, layers, layerList, layer, currentLayer, layerInstances, layerCount, picked, pickedLabel, pickLayer, onPick, cellText, pickedRels, relTag, goRelations,
      blocks, can,
      extEquipTypes, extEquip, extEquipName, extCoreFields, extFields, extAddVisible, extNew, saveExt, delExt,
      relKw, relBlock, relBlocks, relPicked, relOfPicked,
    };
  },
};
