/* P3 规则梳理与建模 */
window.PAGES = window.PAGES || {};
window.PAGES.rules = {
  template: `
  <div>
    <el-alert type="info" :closable="false" show-icon style="margin-bottom:14px"
      title="基于语料库（32 份存量手册）的统计分析与规律挖掘，输出规则草案，经甲方业务部门评审后作为拆解执行依据。" />

    <el-row :gutter="14">
      <el-col :span="12">
        <div class="panel">
          <div class="panel-title">① 文档结构聚类分析 <span class="sub-text">章节体系共性与差异</span></div>
          <div v-for="c in rd.clusters" :key="c.name"
               style="border:1px solid var(--np-border); border-radius:4px; padding:10px 12px; margin-bottom:8px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <b>{{ c.name }}</b>
              <el-tag size="small" type="success" effect="plain">内聚度 {{ (c.sim * 100).toFixed(0) }}%</el-tag>
            </div>
            <div class="sub-text" style="margin-top:6px;">典型章节框架：{{ c.frame }}</div>
          </div>
          <div class="sub-text">输出物：章节结构聚类报告 + 典型章节框架模板</div>
        </div>

        <div class="panel">
          <div class="panel-title">② 内容相似度分析 <span class="sub-text">通用内容候选（阈值 ≥85%）</span></div>
          <el-table :data="rd.similarityTop" border size="small">
            <el-table-column prop="content" label="高频通用内容" min-width="200" />
            <el-table-column prop="count" label="出现文件数" width="100" align="center" sortable />
            <el-table-column label="相似度" width="150">
              <template #default="{row}">
                <el-progress :percentage="Math.round(row.sim * 100)" :stroke-width="10" :color="row.sim >= 0.9 ? '#00a878' : '#ff9800'" />
              </template>
            </el-table-column>
            <el-table-column label="建议" width="110" align="center">
              <template #default="{row}">
                <el-button v-if="!marked.has(row.content)" size="small" type="success" plain @click="markCommon(row)">标记为通用块</el-button>
                <el-tag v-else size="small" type="success">已入库 ✓</el-tag>
              </template>
            </el-table-column>
          </el-table>
          <div class="sub-text" style="margin-top:6px">输出物：按相似度排序的通用内容候选清单 → 进入数据库作为主数据参考</div>
        </div>
      </el-col>

      <el-col :span="12">
        <div class="panel">
          <div class="panel-title">③ 术语频率与共现分析 <span class="sub-text">词频 TOP8</span></div>
          <div ref="termChart" style="height:240px;"></div>
          <div class="sub-text">输出物：术语标准化字典初稿（标准术语 + 同义词映射，≥500 条）→ <a href="#/govern" style="color:var(--np-primary)">查看术语字典</a></div>
        </div>

        <div class="panel">
          <div class="panel-title">④ 内容粒度分析 <span class="sub-text">切分粒度建议</span></div>
          <el-table :data="granularity" border size="small">
            <el-table-column prop="type" label="内容类型" width="90">
              <template #default="{row}">
                <el-tag size="small" :type="typeColor(row.type)">{{ row.type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="freq" label="出现频次" width="90" align="center" />
            <el-table-column prop="avgLen" label="典型长度" width="100" />
            <el-table-column prop="density" label="信息密度" width="100" />
            <el-table-column prop="dep" label="上下文依赖度" width="110">
              <template #default="{row}"><el-tag size="small" :type="{高:'danger',中:'warning',低:'info'}[row.dep]" effect="plain">{{ row.dep }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="suggest" label="推荐切分粒度" min-width="150" />
          </el-table>
          <div class="sub-text" style="margin-top:6px">依据：各形态出现频次、段落长度、信息密度、上下文依赖程度统计（§121）</div>
        </div>
      </el-col>
    </el-row>

    <!-- ⑤ 表格结构分类（需求§107 点名的第5种分析手段） -->
    <div class="panel" style="margin-top:14px">
      <div class="panel-title">⑤ 表格结构分类 <span class="sub-text">常见表格类型与典型列结构 → 解析规则草案</span></div>
      <el-table :data="tableTypes" border size="small">
        <el-table-column prop="type" label="表格类型" width="150">
          <template #default="{row}"><b style="color:var(--np-primary)">{{ row.type }}</b></template>
        </el-table-column>
        <el-table-column prop="cols" label="典型列结构" min-width="240" />
        <el-table-column prop="count" label="出现频次" width="90" align="center" />
        <el-table-column label="识别置信度" width="130">
          <template #default="{row}">
            <el-progress :percentage="Math.round(row.conf * 100)" :stroke-width="10" :color="row.conf >= 0.9 ? '#00a878' : '#ff9800'" />
          </template>
        </el-table-column>
        <el-table-column prop="rule" label="解析规则草案" min-width="200" />
      </el-table>
      <div class="sub-text" style="margin-top:6px">需求导向：仅纳入下游业务实际使用的表格类型做结构化解析（§123），输出表格类型分类清单 + 解析规则草案</div>
    </div>

    <div class="panel" style="text-align:center; padding:22px; margin-top:14px;">
      <el-button type="primary" size="large" icon="Document" @click="draftVisible = true">输出规则草案（提交甲方评审）</el-button>
      <div class="sub-text" style="margin-top:8px">章节结构框架 · 文件解析规则 · 生成规则 · 审查规则 · 使用权限规则</div>
    </div>

    <el-dialog v-model="draftVisible" title="规则草案 V0.9（首轮评审稿）" width="680px">
      <el-collapse v-model="draftActive">
        <el-collapse-item title="一、章节结构框架（核级泵类 EOMM）" name="1">
          <p>概述 → 设备描述 → 安装调试 → 运行细则 → 故障处理 → 维护维修 → 图纸和文件 → 附件。</p>
          <p class="sub-text">来源于 17 份核级泵类手册聚类结果（内聚度 92%），与《PTR冷却泵设备期望生成技术资料》框架一致。</p>
        </el-collapse-item>
        <el-collapse-item title="二、文件解析规则" name="2">
          <p>1. 章节识别：四级标题，编码遵循《SNS 编码规范》与《结构化信息码编码规范》（DMC 挂接）。</p>
          <p>2. 内容块切分：按最小可复用单元原则，操作步骤按单指令切分、注意事项按单条切分。</p>
          <p>3. 参数提取：表格参数由传统程序解析；正文内嵌复合参数由 LLM 拆分至单参数级。</p>
          <p>4. 表格解析（需求导向，纳入清单）：设备代码清单 / 适用标准表 / 备件清单 / 部件清单 / 故障诊断表 / 螺栓力矩表。</p>
        </el-collapse-item>
        <el-collapse-item title="三、内容生成规则" name="3">
          <p>1. 模板槽位按内容类型匹配内容块；参数槽位自动填充目标设备参数值。</p>
          <p>2. 条件化输出：核安全等级、质保等级相关章节仅核级设备包含。</p>
          <p>3. 通用内容块跨手册共享引用，一处修改同步生效。</p>
        </el-collapse-item>
        <el-collapse-item title="四、审查规则" name="4">
          <p>完整性 / 一致性 / 合理性 / 关联完整性四类自动校验；AI 提取结果 100% 人工复核后方可正式入库。</p>
        </el-collapse-item>
        <el-collapse-item title="五、使用权限规则" name="5">
          <p>文件编制厂家产权资料未经许可不得向第三方扩散；角色分为管理员 / 审核员 / 编制员 / 浏览者四级。</p>
        </el-collapse-item>
      </el-collapse>
      <template #footer>
        <el-button @click="draftVisible = false">关闭</el-button>
        <el-button type="primary" @click="submitReview">提交甲方评审</el-button>
      </template>
    </el-dialog>
  </div>`,

  setup() {
    const { ref, onMounted, nextTick } = Vue;
    const rd = window.MOCK.rulesData;
    // §121：补"出现频次"与"上下文依赖程度"两列
    const depMap = { 操作步骤: { freq: '312', dep: '高' }, 注意事项: { freq: '48', dep: '中' }, 技术要求: { freq: '96', dep: '低' }, 描述说明: { freq: '184', dep: '中' } };
    const granularity = rd.granularity.map(g => ({ ...g, freq: depMap[g.type].freq, dep: depMap[g.type].dep }));
    // 需求§107-108：表格结构分类清单（典型列结构 + 解析规则草案）
    const tableTypes = [
      { type: '参数表', cols: '序号·项目·参数·单位', count: 31, conf: 0.96, rule: '传统程序按列解析；正文内嵌复合参数交 LLM 拆分' },
      { type: '设备代码清单', cols: '序号·名称·型号·设备编码·生产厂家', count: 28, conf: 0.97, rule: '行列解析 + 设备-仪表关联关系建立' },
      { type: '备件清单', cols: '名称·型号·质保等级·图纸编码·存储要求·设计寿期·生产厂家', count: 24, conf: 0.94, rule: '合并单元格处理；质保等级枚举匹配' },
      { type: '部件清单(BOM)', cols: '零部件编号·名称·数量·关联图纸', count: 19, conf: 0.92, rule: '层级解析（总成→分总成）；图纸引用关联完整性校验' },
      { type: '故障诊断表', cols: '故障现象·可能原因·处理措施', count: 22, conf: 0.95, rule: '三元组结构化；与章节上下文关联' },
      { type: '螺栓力矩表', cols: '部位·规格·力矩值·力矩单位', count: 12, conf: 0.93, rule: '数值范围合理性检查（50~1000 N·m）' },
      { type: '适用标准表', cols: '序号·类别·标准代号·名称·版本', count: 17, conf: 0.91, rule: '区分国/行/企/国际标准；版本字段结构化' },
    ];
    const termChart = ref(null);
    const draftVisible = ref(false);
    const draftActive = ref(['1']);
    onMounted(() => nextTick(() => {
      const chart = echarts.init(termChart.value);
      chart.setOption({
        grid: { left: 70, right: 30, top: 20, bottom: 25 },
        tooltip: {},
        xAxis: { type: 'value' },
        yAxis: { type: 'category', data: rd.termFreq.map(t => t.term).reverse(), axisLabel: { fontSize: 11 } },
        series: [{
          type: 'bar', data: rd.termFreq.map(t => t.count).reverse(),
          itemStyle: { color: '#0b2a4a', borderRadius: [0, 3, 3, 0] }, barWidth: 14,
          label: { show: true, position: 'right', fontSize: 10 },
        }],
      });
      window.addEventListener('resize', () => chart.resize());
    }));
    function submitReview() {
      draftVisible.value = false;
      ElementPlus.ElMessage.success('规则草案已提交甲方业务部门评审（首轮）');
    }
    const marked = ref(new Set());
    function markCommon(row) {
      marked.value = new Set([...marked.value, row.content]);
      ElementPlus.ElMessage.success(`「${row.content}」已标记为通用内容块，进入内容数据库主数据参考`);
    }
    return { rd, granularity, tableTypes, termChart, draftVisible, draftActive, submitReview, marked, markCommon, typeColor: window.NP.contentTypeColor };
  },
};
