/* P5 知识库与知识图谱: 知识树 / 图谱可视化 / 时序版本 / GraphRAG 语义检索 */
window.PAGES = window.PAGES || {};
window.PAGES.knowledge = {
  template: `
  <div>
    <el-tabs v-model="tab" type="border-card">
      <!-- 知识库管理 -->
      <el-tab-pane label="知识库管理" name="kb">
        <div style="display:flex; gap:14px;">
          <div class="panel" style="width:300px; min-width:300px;">
            <div class="panel-title">
              <span>知识分类树</span>
              <el-button size="small" icon="Plus" circle @click="kbMsg('新增知识节点')" />
            </div>
            <el-tree :data="kbTree" :props="{label:'label'}" default-expand-all highlight-current @node-click="n => kbNode = n.label" />
            <div style="margin-top:10px; display:flex; gap:8px;">
              <el-button size="small" icon="Upload" @click="kbMsg('批量导入（Excel/CSV/JSON）')">批量导入</el-button>
              <el-button size="small" icon="Download" @click="kbMsg('批量导出')">导出</el-button>
            </div>
          </div>
          <div class="panel" style="flex:1">
            <div class="panel-title">知识节点详情</div>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="知识ID">KB-{{ Math.abs(hash(kbNode)) % 9000 + 1000 }}</el-descriptions-item>
              <el-descriptions-item label="知识类型">{{ kbNode.includes('故障') ? '故障知识' : kbNode.includes('参数') ? '参数知识' : kbNode.includes('操作') || kbNode.includes('启动') || kbNode.includes('对中') ? '操作知识' : kbNode.includes('密封') || kbNode.includes('联轴器') || kbNode.includes('承') ? '部件知识' : '设备知识' }}</el-descriptions-item>
              <el-descriptions-item label="知识标题">{{ kbNode }}</el-descriptions-item>
              <el-descriptions-item label="知识状态"><el-tag size="small" type="success">已发布</el-tag></el-descriptions-item>
              <el-descriptions-item label="知识来源">PTR冷却泵设备运行与维修手册.docx</el-descriptions-item>
              <el-descriptions-item label="时序节点">运行阶段</el-descriptions-item>
              <el-descriptions-item label="创建时间">2026-07-20 14:32</el-descriptions-item>
              <el-descriptions-item label="更新时间">2026-07-28 10:15（V3）</el-descriptions-item>
            </el-descriptions>
            <div class="panel-title" style="margin-top:14px">知识内容</div>
            <div class="original-view" style="max-height:200px; overflow:auto;">{{ kbContent }}</div>
            <div style="margin-top:10px; display:flex; gap:8px;">
              <el-button size="small" type="primary" plain icon="Edit" @click="kbMsg('编辑知识')">编辑</el-button>
              <el-button size="small" plain icon="Clock" @click="kbMsg('版本追踪/对比/回退')">版本管理</el-button>
              <el-button size="small" plain icon="CircleCheck" @click="kbMsg('质量检查')">质量检查</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 实体抽取审核（需求§84：知识标注工具） -->
      <el-tab-pane label="实体抽取审核" name="extract">
        <div class="sub-text" style="margin-bottom:12px">
          LLM 从结构化内容块自动抽取设备/部件/参数/故障等实体及关系，经人工审核确认后构建知识图谱。审核界面提供原文-AI 抽取对照，支持逐条确认/修正/补充，差异记录用于模型优化。
        </div>
        <el-row :gutter="14">
          <el-col :span="9">
            <div class="panel">
              <div class="panel-title">抽取任务进度 <span class="pt-badge">{{ extractDone }}/{{ extractList.length }}</span></div>
              <div style="margin-bottom:8px;"><span class="sub-text">整体准确率</span> <b style="color:var(--np-success); font-size:15px;">{{ extractAcc }}%</b></div>
              <el-progress :percentage="Math.round(extractDone / extractList.length * 100)" :stroke-width="10" />
              <div style="margin-top:12px; display:flex; flex-direction:column; gap:6px;">
                <div v-for="(e, i) in extractList" :key="i" class="ext-task" :class="{done: e.status === 'done', current: i === extractIdx}" @click="extractIdx = i">
                  <el-icon v-if="e.status === 'done'" color="#2e8b57"><CircleCheckFilled /></el-icon>
                  <span v-else class="ext-idx">{{ i + 1 }}</span>
                  <span class="ext-task-label">{{ e.source }}</span>
                  <span class="sub-text" style="margin-left:auto">{{ e.entities.length }} 实体</span>
                </div>
              </div>
            </div>
          </el-col>
          <el-col :span="15">
            <div class="panel">
              <div class="panel-title">抽取结果对照审核 <span class="ai-badge">LLM 抽取</span></div>
              <template v-if="currentExtract">
                <div class="original-view" style="max-height:120px; overflow:auto; margin-bottom:12px;">{{ currentExtract.text }}</div>
                <div class="sub-text" style="margin-bottom:6px">来源：{{ currentExtract.source }} · 已抽取 {{ currentExtract.entities.length }} 个实体</div>
                <el-table :data="currentExtract.entities" border size="small">
                  <el-table-column label="实体" min-width="140">
                    <template #default="{row}"><b>{{ row.name }}</b></template>
                  </el-table-column>
                  <el-table-column label="类型" width="100">
                    <template #default="{row}"><span class="legend-chip"><span class="dot" :style="'background:'+colors[row.type]"></span>{{ row.type }}</span></template>
                  </el-table-column>
                  <el-table-column prop="rel" label="抽取关系" min-width="160" />
                  <el-table-column label="置信度" width="90" align="center">
                    <template #default="{row}"><span class="conf-pill" :class="confType(row.conf)">{{ row.conf }}</span></template>
                  </el-table-column>
                  <el-table-column label="审核" width="150" align="center">
                    <template #default="{row}">
                      <template v-if="row.verdict === 'pending'">
                        <el-button size="small" type="success" @click="row.verdict = 'confirmed'">确认</el-button>
                        <el-button size="small" type="warning" plain @click="row.verdict = 'rejected'">修正</el-button>
                      </template>
                      <el-tag v-else :type="row.verdict === 'confirmed' ? 'success' : 'warning'" size="small">{{ row.verdict === 'confirmed' ? '已确认' : '待修正' }}</el-tag>
                    </template>
                  </el-table-column>
                </el-table>
                <div style="margin-top:10px; display:flex; gap:8px;">
                  <el-button size="small" type="primary" :disabled="!can('approve')" @click="confirmAllExtract">全部确认并入图谱</el-button>
                  <el-button size="small" plain @click="nextExtract">下一条</el-button>
                </div>
              </template>
              <el-empty v-else description="选择左侧抽取任务查看对照审核" :image-size="80" />
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- 知识图谱 -->
      <el-tab-pane label="知识图谱" name="graph">
        <div v-if="folderLabel" class="folder-chip"><el-icon><Folder /></el-icon> 目录范围：{{ folderLabel }}（图谱按目录过滤）</div>
        <div style="display:flex; gap:6px; align-items:center; margin-bottom:10px; flex-wrap:wrap;">
          <span class="sub-text">时序版本：</span>
          <el-radio-group v-model="phase" size="small" @change="renderGraph">
            <el-radio-button value="全部">全部</el-radio-button>
            <el-radio-button value="设计">设计阶段</el-radio-button>
            <el-radio-button value="制造">制造阶段</el-radio-button>
            <el-radio-button value="安装调试">安装调试</el-radio-button>
            <el-radio-button value="运行">运行阶段</el-radio-button>
          </el-radio-group>
          <span style="margin-left:16px" class="sub-text">实体类型：</span>
          <span v-for="(c, t) in colors" :key="t" class="legend-chip"><span class="dot" :style="'background:'+c"></span>{{ t }}</span>
          <span style="margin-left:auto" class="sub-text">按设备生命周期构建时序版本图谱 · 时序标签串联</span>
        </div>
        <div style="display:flex; gap:14px;">
          <div class="panel" style="flex:1.6">
            <div ref="graphEl" class="graph-box"></div>
          </div>
          <div class="panel" style="flex:1; max-height:580px; overflow:auto;">
            <div class="panel-title">实体详情 <span class="sub-text">点击图谱节点</span><el-badge v-if="newEntityCount > 0" :value="'新+' + newEntityCount" type="success" style="margin-left:8px" /></div>
            <template v-if="selNode">
              <div class="sel-node-head" :style="'--nc:'+colors[selNode.type]">
                <span class="sel-node-type" :style="'background:'+colors[selNode.type]">{{ selNode.type }}</span>
                <b class="sel-node-name">{{ selNode.name }}</b>
                <el-tag size="small" effect="plain" style="margin-left:auto">时序: {{ selNode.phase }}</el-tag>
              </div>
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item v-for="(v, k) in selNode.props" :key="k" :label="k">{{ v }}</el-descriptions-item>
                <el-descriptions-item label="置信度"><span class="conf-pill success">0.93</span> 人工已审核</el-descriptions-item>
                <el-descriptions-item label="来源">PTR冷却泵手册 · {{ selNode.props['章节'] || selNode.props['DMC'] || '相关章节' }}</el-descriptions-item>
              </el-descriptions>
              <div class="panel-title" style="margin-top:12px">关联关系 <span class="pt-badge">{{ selRels.length }}</span></div>
              <div v-for="r in selRels" :key="r.text" class="rel-row">
                <el-tag size="small" effect="plain">{{ r.rel }}</el-tag> {{ r.text }}
              </div>
            </template>
            <el-empty v-else description="点击左侧图谱节点查看实体属性、置信度与证据链" :image-size="80" />
          </div>
        </div>
      </el-tab-pane>

      <!-- 语义检索与推理 -->
      <el-tab-pane label="语义检索与推理" name="qa">
        <div style="display:flex; gap:14px;">
          <div class="panel" style="flex:1.2; min-height:520px;">
            <div class="panel-title">智能知识查询 <span class="ai-badge">GraphRAG</span></div>
            <div style="display:flex; gap:8px; margin-bottom:12px;">
              <el-input v-model="question" placeholder="自然语言提问，如：轴承发热怎么处理？" @keyup.enter="ask" />
              <el-button type="primary" icon="Search" @click="ask" :loading="asking">查询</el-button>
            </div>
            <div style="margin-bottom:12px;">
              <span class="sub-text">示例问题：</span>
              <el-tag v-for="qa in qaList" :key="qa.q" size="small" effect="plain" style="cursor:pointer; margin-right:6px;" @click="question = qa.q; ask()">{{ qa.q }}</el-tag>
            </div>
            <div v-if="answer" class="qa-answer">
              <div class="qa-head">
                <span class="ai-badge">GraphRAG</span>
                <el-tag size="small" :type="answer.mode.includes('Global') ? 'warning' : 'primary'" effect="plain">{{ answer.mode }}</el-tag>
                <span class="sub-text" style="margin-left:auto">{{ asking ? '正在检索知识图谱…' : '回答完成' }}</span>
              </div>
              <div class="qa-body" :class="{typing: asking}">{{ answerText }}</div>
            </div>
            <el-empty v-if="!answer && !asking" description="基于知识库与知识图谱的语义检索：实体/关系/路径/相似性查询，支持 GraphRAG 全局/局部混合检索" :image-size="90" />
          </div>
          <div class="panel" style="flex:1; max-height:560px; overflow:auto;">
            <div class="panel-title">证据链与置信度 <span class="pt-badge" v-if="answer">{{ answer.evidence.length }} 条</span></div>
            <template v-if="answer">
              <div v-for="(e, i) in answer.evidence" :key="i" class="evidence-card">
                <div class="ev-text">{{ e.text }}</div>
                <div class="ev-meta">
                  <el-tag size="small" type="success" effect="plain">置信度 {{ e.conf }}</el-tag>
                  <el-tag size="small" effect="plain">时序: {{ e.phase }}</el-tag>
                  <span class="sub-text" style="font-size:11px;">{{ e.source }}</span>
                  <el-button size="small" text type="primary" style="margin-left:auto" @click="jumpToOriginal(e)">跳回原文</el-button>
                </div>
              </div>
              <el-alert type="info" :closable="false" show-icon title="检索结果均标注来源（原始文件 / 章节路径 / 时序节点），支持证据链可视化追踪。" />
            </template>
            <el-empty v-else description="查询后展示证据链" :image-size="80" />
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>`,

  setup() {
    const { ref, computed, watch, nextTick, onMounted } = Vue;
    const M = window.MOCK;
    const tab = ref('graph');
    const kbTree = M.knowledgeTree;
    const kbNode = ref('机械密封(PLAN01冲洗)');
    const kbContent = computed(() => {
      const b = M.blocks.find(x => x.content.includes(kbNode.value.slice(0, 4)));
      return b ? b.content : '泵盖一端的轴封采用集装式机械密封，冲洗方案 PLAN01，即采用泵的输送介质对机械密封进行冲洗和冷却，所取冲洗水的流量和压力能够满足机械密封的冲洗和冷却要求。';
    });
    function hash(s) { let h = 0; for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) | 0; return h; }
    const folderLabel = computed(() => { const sf = window.NP.store.selectedFolder; return sf && sf.equipment ? sf.equipment : ''; });
    function kbMsg(what) {
      const D = window.NP.showDialog;
      const node = kbNode.value;
      if (what.includes('新增')) {
        D('新增知识节点', `
          <el-row><b>所属分类：</b>${node}</el-row>
          <table>
            <tr><th style="width:110px">属性</th><th>填写内容</th></tr>
            <tr><td>知识类型</td><td>设备知识 / 参数知识 / 操作知识 / 故障知识 / 部件知识 / 标准知识</td></tr>
            <tr><td>知识标题</td><td>（输入）</td></tr>
            <tr><td>知识内容</td><td>（富文本编辑，支持插入内容块引用与图谱实体链接）</td></tr>
            <tr><td>知识来源</td><td>默认关联当前文档：PTR冷却泵设备运行与维修手册.docx</td></tr>
            <tr><td>初始状态</td><td>草稿 → 审核后发布</td></tr>
          </table>`);
      } else if (what.includes('导入')) {
        D('批量导入知识', `
          <p>支持 Excel / CSV / JSON 格式，字段映射：知识ID、知识类型、知识标题、知识内容、知识来源、时序节点。</p>
          <table>
            <tr><th>步骤</th><th>说明</th></tr>
            <tr><td>1. 下载模板</td><td>知识导入模板.xlsx（含字段示例）</td></tr>
            <tr><td>2. 上传文件</td><td>单次≤5000 条，自动去重与格式校验</td></tr>
            <tr><td>3. 预检报告</td><td>列出重复/缺字段/类型非法条目，确认后入库</td></tr>
          </table>
          <p class="ok">最近一次导入：2026-07-28 · 术语知识 512 条 · 成功率 99.2%</p>`);
      } else if (what.includes('导出')) {
        D('批量导出知识', `
          <p>导出范围：<b>${node}</b> 及其子节点（含版本信息）。</p>
          <table>
            <tr><th>格式</th><th>适用场景</th></tr>
            <tr><td>Excel (.xlsx)</td><td>与外部术语标准对接、线下评审</td></tr>
            <tr><td>CSV (.csv)</td><td>系统间数据交换</td></tr>
            <tr><td>JSON (.json)</td><td>知识库全量备份与迁移</td></tr>
          </table>`);
      } else if (what.includes('编辑')) {
        D('编辑知识 · ' + node, `
          <table>
            <tr><th style="width:110px">字段</th><th>当前值</th></tr>
            <tr><td>知识标题</td><td>${node}</td></tr>
            <tr><td>知识内容</td><td>（富文本编辑区，支持引用内容块 DMC 与图谱实体）</td></tr>
            <tr><td>知识状态</td><td>已发布 → 修改后转为「修订中」，需重新审核发布</td></tr>
          </table>
          <p class="sub-text" style="color:#7a8699">保存后自动生成新版本 V4，旧版本保留可追溯。</p>`);
      } else if (what.includes('版本')) {
        D('版本管理 · ' + node, `
          <table>
            <tr><th>版本</th><th>时间</th><th>操作人</th><th>变更说明</th><th>操作</th></tr>
            <tr><td>V3（当前）</td><td>2026-07-28 10:15</td><td>李工</td><td>补充 PLAN01 冲洗方案说明</td><td>—</td></tr>
            <tr><td>V2</td><td>2026-07-24 16:40</td><td>王工</td><td>修正泄漏量描述</td><td class="warn">对比 / 回退</td></tr>
            <tr><td>V1</td><td>2026-07-20 14:32</td><td>系统</td><td>解析入库初始版本</td><td class="warn">对比 / 回退</td></tr>
          </table>`);
      } else if (what.includes('质量')) {
        D('质量检查 · ' + node, `
          <table>
            <tr><th>检查项</th><th>结果</th></tr>
            <tr><td>必填属性完整性（ID/类型/来源/时序）</td><td class="ok">通过</td></tr>
            <tr><td>知识内容与来源文档一致性</td><td class="ok">通过（相似度 97%）</td></tr>
            <tr><td>术语标准化（是否含非标准术语）</td><td class="warn">1 处提示：「机封」建议替换为「机械密封」</td></tr>
            <tr><td>图谱关联完整性（实体是否已建图谱节点）</td><td class="ok">已关联：机械密封(P3)</td></tr>
          </table>`);
      }
    }

    // ---- 实体抽取审核（需求§84：知识标注工具）----
    const extractList = ref([
      { source: 'CB-0007 机械密封组件', text: '泵盖一端的轴封采用集装式机械密封，冲洗方案 PLAN01，采用泵输送介质对机械密封进行冲洗和冷却。', status: 'done',
        entities: [
          { name: '机械密封', type: '部件', rel: '组成→泵盖', conf: 0.96, verdict: 'confirmed' },
          { name: 'PLAN01冲洗方案', type: '标准', rel: '适用→机械密封', conf: 0.91, verdict: 'confirmed' },
          { name: '冲洗冷却', type: '操作', rel: '特性→机械密封', conf: 0.88, verdict: 'confirmed' },
        ]},
      { source: 'CB-0033 联轴器对中', text: '泵与电机采用膜片式挠性联轴器连接，对中时需测量端面跳动和径向跳动，跳动允差 0.05mm。', status: 'current',
        entities: [
          { name: '膜片式挠性联轴器', type: '部件', rel: '组成→泵/电机', conf: 0.94, verdict: 'pending' },
          { name: '对中操作', type: '操作', rel: '特性→联轴器', conf: 0.89, verdict: 'pending' },
          { name: '跳动允差0.05mm', type: '参数', rel: '约束→对中', conf: 0.86, verdict: 'pending' },
        ]},
      { source: 'CB-0042 轴承发热诊断', text: '轴承温度超过 80℃时，检查润滑油位和冷却水流量，必要时更换轴承。', status: 'pending',
        entities: [
          { name: '轴承发热', type: '故障', rel: '对象→轴承', conf: 0.93, verdict: 'pending' },
          { name: '润滑油位', type: '参数', rel: '解决→轴承发热', conf: 0.85, verdict: 'pending' },
          { name: '冷却水流量', type: '参数', rel: '解决→轴承发热', conf: 0.84, verdict: 'pending' },
        ]},
    ]);
    const extractIdx = ref(1);
    const currentExtract = computed(() => extractList.value[extractIdx.value]);
    const extractDone = computed(() => extractList.value.filter(e => e.status === 'done').length);
    const extractAcc = computed(() => {
      const all = extractList.value.flatMap(e => e.entities);
      const conf = all.filter(x => x.verdict === 'confirmed').length;
      return all.length ? Math.round(conf / all.length * 100) : 0;
    });
    function confType(c) { return c >= 0.95 ? 'success' : c >= 0.9 ? 'warning' : 'danger'; }
    function confirmAllExtract() {
      currentExtract.value.entities.forEach(en => { if (en.verdict === 'pending') en.verdict = 'confirmed'; });
      const ids = currentExtract.value.entities.map(e => e.name);
      window.NP.markNewEntities(ids);
      currentExtract.value.status = 'done';
      ElementPlus.ElMessage.success('抽取结果已确认并入知识图谱，' + ids.length + ' 实体留痕');
    }
    function nextExtract() {
      if (extractIdx.value < extractList.value.length - 1) extractIdx.value++;
    }

    const newEntityCount = computed(() => window.NP.store.newEntityIds.length);
    function jumpToOriginal(e) {
      window.NP.go('parse');
      setTimeout(() => ElementPlus.ElMessage.info('已跳转解析审核页，请定位：' + (e.source || '相关章节')), 300);
    }

    // ---- 图谱 ----
    const colors = M.graph.entityColors;
    const phase = ref('全部');
    const graphEl = ref(null);
    const selNode = ref(null);
    let chart = null;
    function renderGraph() {
      if (!chart) return;
      const nodes = M.graph.nodes.filter(n => phase.value === '全部' || n.phase === phase.value || n.type === '设备');
      const ids = new Set(nodes.map(n => n.id));
      const edges = M.graph.edges.filter(e => ids.has(e.from) && ids.has(e.to));
      const cats = Object.keys(colors).map(t => ({ name: t, itemStyle: { color: colors[t] } }));
      chart.setOption({
        tooltip: { formatter: p => p.dataType === 'edge' ? `${p.data.source} —[${p.data.rel}]→ ${p.data.target}` : `<b>${p.data.name}</b><br/>${p.data.cat} · 时序: ${p.data.phase}` },
        legend: { data: Object.keys(colors), bottom: 0, textStyle: { fontSize: 11 } },
        series: [{
          type: 'graph', layout: 'force', roam: true, categories: cats,
          force: { repulsion: 320, edgeLength: [60, 110], gravity: 0.08 },
          label: { show: true, fontSize: 10, position: 'right' },
          edgeLabel: { show: true, fontSize: 9, color: '#98a4b5', formatter: p => p.data.rel },
          lineStyle: { color: '#b7c2d0', curveness: 0.08 },
          emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
          data: nodes.map(n => ({
            id: n.id, name: n.name, category: n.type, cat: n.type, phase: n.phase,
            symbolSize: n.type === '设备' ? 52 : n.type === '部件' ? 34 : 28,
            value: n,
          })),
          links: edges.map(e => ({ source: e.from, target: e.to, rel: e.rel })),
        }],
      });
    }
    function initGraph() {
      if (!graphEl.value) return;
      chart = echarts.init(graphEl.value);
      chart.on('click', p => { if (p.dataType === 'node') selNode.value = p.data.value; });
      renderGraph();
      window.addEventListener('resize', () => chart && chart.resize());
    }
    watch(tab, v => { if (v === 'graph') nextTick(() => { if (!chart) initGraph(); else chart.resize(); }); });
    onMounted(() => nextTick(() => { if (tab.value === 'graph') initGraph(); }));

    const selRels = computed(() => {
      if (!selNode.value) return [];
      const id = selNode.value.id;
      const nameOf = x => (M.graph.nodes.find(n => n.id === x) || {}).name || x;
      return M.graph.edges.filter(e => e.from === id || e.to === id)
        .map(e => ({ rel: e.rel, text: e.from === id ? `${selNode.value.name} → ${nameOf(e.to)}` : `${nameOf(e.from)} → ${selNode.value.name}` }));
    });

    // ---- GraphRAG 问答 ----
    const qaList = M.semanticQA;
    const question = ref('');
    const answer = ref(null);
    const answerText = ref('');
    const asking = ref(false);
    function ask() {
      if (!question.value.trim()) return;
      const q = question.value;
      let hit = qaList.find(x => q.includes(x.q.slice(0, 4)) || x.q.includes(q.slice(0, 6)));
      if (!hit) {
        // 关键词意图匹配：故障/处理→故障类；参数→参数类；对比/全厂/模式→全局类
        if (/(对比|全厂|模式|汇总|统计|社区)/.test(q)) hit = qaList[2];
        else if (/(参数|流量|扬程|转速|功率|汽蚀)/.test(q)) hit = qaList[1];
        else hit = qaList[0];
      }
      answer.value = hit;
      answerText.value = '';
      asking.value = true;
      window.NP.stream(hit.answer, t => { answerText.value = t; }, () => { asking.value = false; }, 30);
    }

    return {
      tab, kbTree, kbNode, kbContent, hash, kbMsg,
      folderLabel,
      colors, phase, graphEl, selNode, selRels, renderGraph,
      qaList, question, answer, answerText, asking, ask,
      extractList, extractIdx, currentExtract, extractDone, extractAcc, confType, confirmAllExtract, nextExtract,
      newEntityCount, jumpToOriginal, can: window.NP.can,
    };
  },
};
