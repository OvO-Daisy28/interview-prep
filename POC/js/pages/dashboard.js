/* P1 工作台 */
window.PAGES = window.PAGES || {};
window.PAGES.dashboard = {
  template: `
  <div>
    <!-- ② KPI 统计卡 -->
    <el-row :gutter="14">
      <el-col :span="4" v-for="s in stats" :key="s.label">
        <div class="kpi-card" :class="'kpi-' + s.color" @click="go(s.page)" :title="'点击进入' + s.hint">
          <div class="kpi-top">
            <div class="kpi-icon"><el-icon :size="20"><component :is="s.icon" /></el-icon></div>
            <span class="kpi-trend">{{ s.trend }}</span>
          </div>
          <div class="num">{{ s.value }}</div>
          <div class="lbl">{{ s.label }}</div>
          <div class="sub">{{ s.sub }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- ① 四块 ECharts 图表 -->
    <div class="sec-head" style="margin-top:18px">
      <span class="sec-bar"></span>
      <span class="sec-title">数据概览</span>
      <span class="sec-sub">源自 PTR 冷却泵真实手册 · 实时统计</span>
    </div>
    <el-row :gutter="14" style="margin-top:10px">
      <el-col :span="6">
        <div class="chart-card">
          <div class="cc-title"><span>AI 提取准确率</span><span class="cc-sub">验收线 ≥ 95%</span></div>
          <div ref="accEl" class="chart-box"></div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="chart-card">
          <div class="cc-title"><span>内容块类型分布</span><span class="cc-sub">共 {{ blockCount }} 块</span></div>
          <div ref="typeEl" class="chart-box"></div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="chart-card">
          <div class="cc-title"><span>解析进度趋势</span><span class="cc-sub">近 7 日累计内容块</span></div>
          <div ref="trendEl" class="chart-box"></div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="chart-card">
          <div class="cc-title"><span>手册编制进度</span><span class="cc-sub">3 台设备</span></div>
          <div ref="manualEl" class="chart-box"></div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="14" style="margin-top:18px">
      <el-col :span="14">
        <div class="panel">
          <div class="panel-title"><span>待办任务</span><span class="pt-badge">{{ todo.length }} 项</span></div>
          <div v-for="t in todo" :key="t.text"
               style="display:flex; align-items:center; gap:8px; padding:9px 6px; border-bottom:1px dashed var(--np-border); cursor:pointer; transition:background .15s;"
               @click="go(t.page)"
               @mouseenter="$event.currentTarget.style.background='#f6f9fd'"
               @mouseleave="$event.currentTarget.style.background=''">
            <el-tag :type="t.level" size="small" effect="light">{{ {warning:'复核', info:'提醒', danger:'变更'}[t.level] }}</el-tag>
            <span style="flex:1">{{ t.text }}</span>
            <el-icon color="#7a8699"><ArrowRight /></el-icon>
          </div>
        </div>
      </el-col>
      <el-col :span="10">
        <div class="panel">
          <div class="panel-title"><span>当前验证项目</span><span class="pt-badge">PTR 试点</span></div>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="项目">太平岭一期 · 采购文件结构化试点</el-descriptions-item>
            <el-descriptions-item label="试点设备">{{ meta.equipment }}（{{ meta.nuclearLevel }} / {{ meta.qaLevel }} / {{ meta.seismic }}）</el-descriptions-item>
            <el-descriptions-item label="编制厂家">{{ meta.manufacturer }}</el-descriptions-item>
            <el-descriptions-item label="编码体系">SNS / DMC · 已挂接 {{ dmcCount }} 条编码</el-descriptions-item>
            <el-descriptions-item label="数据输出">
              <el-tag size="small" effect="plain" style="cursor:pointer" @click="showIetm">IETM 平台对接（入口预留）</el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>
    </el-row>
  </div>`,
  setup() {
    const { ref, onMounted, onUnmounted, nextTick } = Vue;
    const M = window.MOCK;
    const blocks = window.NP.store.blocks;
    const blockCount = blocks.length;

    const stats = [
      { label: '已导入文档', value: M.docs.length, sub: '含扫描版 1 份', trend: 'OCR 98.6%', color: 'blue', icon: 'Document', page: 'parse', hint: '内容解析' },
      { label: '解析内容块', value: blockCount, sub: '通用块 ' + blocks.filter(b => b.isCommon).length, trend: '↑ 本周 +12', color: 'cyan', icon: 'Files', page: 'database', hint: '内容数据库' },
      { label: '技术参数', value: M.params.length, sub: '准确率 95.8%', trend: '已复核 9 条', color: 'green', icon: 'DataAnalysis', page: 'parse', hint: '内容解析' },
      { label: '知识图谱实体', value: M.graph.nodes.length, sub: '关系 ' + M.graph.edges.length + ' 条', trend: '6 类实体', color: 'purple', icon: 'Share', page: 'knowledge', hint: '知识图谱' },
      { label: '已生成手册', value: 3, sub: '在编 1 份', trend: 'PTR / RRI / CEF', color: 'amber', icon: 'Notebook', page: 'generate', hint: '手册生成' },
      { label: '待复核 AI 结果', value: blocks.filter(b => b.reviewStatus === '待审核').length + 5, sub: '需人工确认', trend: '置信度<0.9', color: 'red', icon: 'MagicStick', page: 'parse', hint: '内容解析' },
    ];
    const flow = [];

    function go(p) { location.hash = '#/' + p; }
    function showIetm() {
      window.NP.showDialog('数据输出 · IETM 平台对接', `
        <h4>输出内容</h4>
        <p>结构化数据模块（DMC 编码内容块、技术参数、故障诊断、备件信息）按 IETM 数据模块规范打包，导入 IETM 平台进行交互式电子技术手册出版阅读。</p>
        <table>
          <tr><th>输出物</th><th>格式</th><th>说明</th></tr>
          <tr><td>数据模块包</td><td>XML（S1000D 参照）</td><td>79 个内容块，含 SNS/DMC 编码</td></tr>
          <tr><td>出版物结构</td><td>XML（PM）</td><td>按手册模板章节组织</td></tr>
          <tr><td>插图与多媒体</td><td>CGM/SVG/MP4</td><td>图纸信息表关联导出</td></tr>
        </table>
        <p class="sub-text" style="color:#7a8699">对接状态：接口规范已预留，待甲方 IETM 平台环境就绪后联调。</p>`);
    }

    /* ---------- ① ECharts 图表 ---------- */
    const accEl = ref(null), typeEl = ref(null), trendEl = ref(null), manualEl = ref(null);
    let charts = [];
    function onResize() { charts.forEach(c => c && c.resize()); }

    function initCharts() {
      // 1) AI 提取准确率仪表盘
      const acc = echarts.init(accEl.value);
      acc.setOption({
        series: [{
          type: 'gauge', startAngle: 200, endAngle: -20, min: 0, max: 100,
          radius: '92%', center: ['50%', '58%'],
          progress: { show: true, width: 13, roundCap: true, itemStyle: { color: '#0b2a4a' } },
          axisLine: { lineStyle: { width: 13, color: [[0.95, '#f0c36d'], [1, '#e6e9ef']] } },
          pointer: { width: 5, length: '58%', itemStyle: { color: '#0b2a4a' } },
          axisTick: { show: false }, splitLine: { length: 8, lineStyle: { color: '#fff', width: 2 } },
          axisLabel: { distance: -22, fontSize: 9, color: '#7a8699' },
          anchor: { show: true, size: 8, itemStyle: { color: '#0b2a4a' } },
          detail: { valueAnimation: true, formatter: '{value}%', fontSize: 20, color: '#0b2a4a', offsetCenter: [0, '32%'] },
          title: { offsetCenter: [0, '58%'], fontSize: 11, color: '#7a8699' },
          data: [{ value: 95.8, name: '当前准确率' }],
        }],
      });
      charts.push(acc);

      // 2) 内容块类型分布环形图
      const typeCounts = {};
      blocks.forEach(b => { typeCounts[b.contentType] = (typeCounts[b.contentType] || 0) + 1; });
      const palette = { '描述说明': '#2a6fb0', '操作步骤': '#0b2a4a', '技术要求': '#e54848', '注意事项': '#ff9800' };
      const donut = echarts.init(typeEl.value);
      donut.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} 块 ({d}%)' },
        legend: { bottom: 0, icon: 'circle', textStyle: { fontSize: 11 } },
        series: [{
          type: 'pie', radius: ['42%', '64%'], center: ['50%', '42%'],
          avoidLabelOverlap: true, padAngle: 2,
          itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
          label: { show: true, formatter: '{c}', fontSize: 11, color: '#3a4658' },
          labelLine: { length: 8, length2: 6 },
          data: Object.keys(typeCounts).map(k => ({ name: k, value: typeCounts[k], itemStyle: { color: palette[k] || '#999' } })),
        }],
      });
      charts.push(donut);

      // 3) 解析进度趋势折线（近 7 日累计）
      const trend = echarts.init(trendEl.value);
      const days = ['7-28', '7-29', '7-30', '7-31', '8-01', '8-02', '8-03'];
      const cum = [8, 19, 31, 44, 58, 70, blockCount];
      trend.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 32, right: 14, top: 22, bottom: 26 },
        xAxis: { type: 'category', data: days, axisLabel: { fontSize: 10, color: '#7a8699' }, axisLine: { lineStyle: { color: '#dfe4ec' } } },
        yAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#7a8699' }, splitLine: { lineStyle: { color: '#eef1f6' } } },
        series: [{
          type: 'line', smooth: true, data: cum, symbolSize: 6,
          lineStyle: { width: 3, color: '#0b2a4a' },
          itemStyle: { color: '#0b2a4a' },
          areaStyle: {
            color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
              { offset: 0, color: 'rgba(0,184,212,.22)' }, { offset: 1, color: 'rgba(0,184,212,.02)' },
            ] },
          },
          markPoint: { data: [{ type: 'max', name: '最大' }], symbolSize: 38, label: { fontSize: 10 } },
        }],
      });
      charts.push(trend);

      // 4) 手册编制进度横向条形
      const manual = echarts.init(manualEl.value);
      manual.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: 56, right: 40, top: 14, bottom: 24 },
        xAxis: { type: 'value', max: 100, axisLabel: { fontSize: 10, color: '#7a8699', formatter: '{value}%' }, splitLine: { lineStyle: { color: '#eef1f6' } } },
        yAxis: { type: 'category', data: ['CEF补水泵', 'RRI冷却泵', 'PTR冷却泵'], axisLabel: { fontSize: 11, color: '#3a4658' }, axisLine: { lineStyle: { color: '#dfe4ec' } } },
        series: [{
          type: 'bar', data: [
            { value: 100, itemStyle: { color: '#00a878' } },
            { value: 60, itemStyle: { color: '#ff9800' } },
            { value: 95, itemStyle: { color: '#0b2a4a' } },
          ],
          barWidth: 12, itemStyle: { borderRadius: [0, 6, 6, 0] },
          label: { show: true, position: 'right', formatter: '{c}%', fontSize: 10, color: '#7a8699' },
        }],
      });
      charts.push(manual);
    }

    onMounted(() => nextTick(() => {
      initCharts();
      window.addEventListener('resize', onResize);
    }));
    onUnmounted(() => {
      window.removeEventListener('resize', onResize);
      charts.forEach(c => c && c.dispose()); charts = [];
    });

    return { stats, todo: M.todo, meta: M.meta, dmcCount: M.dmcCount, go, showIetm,
             blockCount, accEl, typeEl, trendEl, manualEl };
  },
};
