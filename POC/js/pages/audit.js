/* 审计日志（核电可追溯：全程留痕，需求§权限规则/§变更可追溯的隐含要求）
   六类分项：登录 / 用户行为 / 知识库应用 / 应用问答 / 接口调用 / 异常 */
window.PAGES = window.PAGES || {};
window.PAGES.audit = {
  template: `
  <div>
    <!-- 审计概览 -->
    <div class="panel gov-overview">
      <div class="gov-cards">
        <div class="gov-card" style="cursor:default"><div class="gv-num">{{ logs.length }}</div><div class="gv-lbl">日志总数</div></div>
        <div class="gov-card" style="cursor:default"><div class="gv-num" style="color:var(--np-cyan)">{{ moduleDist.length }}</div><div class="gv-lbl">涉及模块</div></div>
        <div class="gov-card" style="cursor:default"><div class="gv-num" style="color:var(--np-success)">{{ successCount }}</div><div class="gv-lbl">成功操作</div></div>
        <div class="gov-card" style="cursor:default"><div class="gv-num" style="color:var(--np-amber)">{{ errCount }}</div><div class="gv-lbl">异常条目</div></div>
        <div class="gov-card" style="cursor:default"><div class="gv-num" style="color:var(--np-purple)">{{ roleDist.length }}</div><div class="gv-lbl">操作角色</div></div>
      </div>
      <div class="gov-bar">
        <span class="sub-text">操作类型分布</span>
        <div class="gov-stacked">
          <div v-for="(c, a) in actionDist" :key="a" class="gv-seg" :style="'width:' + Math.max(4, c*6) + '%; background:' + actionColor(a)" :title="a + ' ' + c"></div>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-title">
        <span>操作审计日志</span>
        <span class="sub-text">全程留痕 · 不可篡改 · 支持追溯与回放 · 集中转发至 UBA 审计服务</span>
      </div>
      <el-tabs v-model="cat" type="card" style="margin-top:4px">
        <el-tab-pane v-for="c in cats" :key="c.key" :name="c.key">
          <template #label>{{ c.label }} <el-badge :value="catCount(c.key)" :type="c.key==='异常' && catCount(c.key) ? 'danger' : 'info'" style="margin-left:2px" /></template>
        </el-tab-pane>
      </el-tabs>
      <el-form inline size="small" style="margin-top:6px">
        <el-form-item label="模块">
          <el-select v-model="q.module" style="width:150px" clearable placeholder="全部模块">
            <el-option v-for="m in modules" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="操作类型">
          <el-select v-model="q.action" style="width:130px" clearable placeholder="全部">
            <el-option v-for="a in actions" :key="a" :label="a" :value="a" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="q.role" style="width:120px" clearable placeholder="全部角色">
            <el-option v-for="r in roles" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="q.kw" placeholder="对象/操作人/详情" style="width:180px" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="Search" @click="() => {}">筛选</el-button>
          <el-button @click="reset">重置</el-button>
          <el-button icon="Download" :disabled="!can('export')" @click="exportLog">导出日志</el-button>
        </el-form-item>
      </el-form>
      <div class="sub-text">命中 {{ filtered.length }} / {{ logs.length }} 条</div>
    </div>

    <div class="panel">
      <div class="panel-title"><span>日志明细</span><span class="pt-badge">{{ filtered.length }} 条</span></div>
      <el-table :data="filtered" border size="small">
        <el-table-column prop="time" label="时间" width="150" />
        <el-table-column label="操作人 / 角色" width="150">
          <template #default="{row}"><b>{{ row.user }}</b> <el-tag size="small" effect="plain">{{ row.role }}</el-tag></template>
        </el-table-column>
        <el-table-column label="类别" width="110">
          <template #default="{row}"><el-tag size="small" :type="row.cat==='异常'?'danger':(row.cat==='登录'?'info':'')" effect="plain">{{ row.cat }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="module" label="模块" width="110" />
        <el-table-column prop="action" label="操作类型" width="100">
          <template #default="{row}"><el-tag size="small" :type="actionType(row.action)">{{ row.action }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="target" label="操作对象" width="200" show-overflow-tooltip />
        <el-table-column prop="detail" label="详情" min-width="260" show-overflow-tooltip />
        <el-table-column label="结果" width="90" align="center">
          <template #default="{row}"><el-tag size="small" :type="row.result === '成功' ? 'success' : 'danger'">{{ row.result }}</el-tag></template>
        </el-table-column>
      </el-table>
      <el-alert type="info" :closable="false" show-icon style="margin-top:10px"
        title="审计日志覆盖核电质保对数据可追溯的要求：每一次导入/解析/审核/修正/变更/生成/导出/登录/接口调用均记录操作人、时间、对象与变更前后内容，支持版本回放与责任界定。" />
    </div>
  </div>`,
  setup() {
    const { ref, computed } = Vue;
    const modules = ['导入解析', 'AI审核', '内容数据库', '内容治理', '手册生成', '知识图谱', '系统管理', '应用接口'];
    const actions = ['导入', '解析', '确认', '修正', '术语替换', '质量检查', '变更审批', '生成', '导出', '审校', '抽取并入', '枚举维护', '登录', '登出', '调用', '问答', '异常'];
    const roles = ['管理员', '审核员', '编制员', '浏览者', '系统'];
    const cats = [
      { key: '全部', label: '全部' },
      { key: '登录', label: '登录日志' },
      { key: '用户行为', label: '用户行为' },
      { key: '知识库应用', label: '知识库应用' },
      { key: '应用问答', label: '应用问答' },
      { key: '接口调用', label: '接口调用' },
      { key: '异常', label: '异常日志' },
    ];
    const logs = [
      // 登录日志
      { time: '2026-08-06 09:12', user: '张工', role: '管理员', cat: '登录', module: '系统管理', action: '登录', target: 'PC · 10.18.2.31', detail: '4A 单点登录成功 · 多因子(指纹)', result: '成功' },
      { time: '2026-08-06 09:14', user: '李工', role: '审核员', cat: '登录', module: '系统管理', action: '登录', target: 'PC · 10.18.2.46', detail: 'Token 认证成功', result: '成功' },
      { time: '2026-08-06 09:40', user: '未知', role: '系统', cat: '登录', module: '系统管理', action: '登录', target: '10.18.2.99', detail: '连续 3 次密码错误，账户已锁定', result: '失败' },
      { time: '2026-08-05 18:02', user: '王工', role: '编制员', cat: '登录', module: '系统管理', action: '登出', target: 'PC · 10.18.2.52', detail: '主动登出', result: '成功' },

      // 用户行为
      { time: '2026-07-31 10:32', user: '王工', role: '编制员', cat: '用户行为', module: '导入解析', action: '导入', target: 'PTR冷却泵手册.docx', detail: '批量导入，4级标题识别，61张表格定位', result: '成功' },
      { time: '2026-07-31 10:35', user: '系统', role: '系统', cat: '用户行为', module: '导入解析', action: '解析', target: 'CB-0001~CB-0012', detail: '三引擎协同解析完成，12个内容块入库', result: '成功' },
      { time: '2026-07-31 10:48', user: '李工', role: '审核员', cat: '用户行为', module: 'AI审核', action: '确认', target: 'CB-0007', detail: 'AI 提取结果人工确认，置信度0.96', result: '成功' },
      { time: '2026-07-31 10:52', user: '李工', role: '审核员', cat: '用户行为', module: 'AI审核', action: '修正', target: 'CB-0033 力矩值', detail: '45 N·m → 55 N·m（差异已记录用于模型优化）', result: '成功' },
      { time: '2026-07-31 11:10', user: '系统', role: '系统', cat: '用户行为', module: '内容治理', action: '术语替换', target: 'CB-0042', detail: '机封 → 机械密封，原文留痕', result: '成功' },
      { time: '2026-07-31 11:30', user: '王工', role: '编制员', cat: '用户行为', module: '内容治理', action: '质量检查', target: '全库检查', detail: '发现 2错误/1警告/1提示，推送至管理员', result: '成功' },
      { time: '2026-07-31 13:20', user: '张工', role: '管理员', cat: '用户行为', module: '内容数据库', action: '变更审批', target: 'CB-0021 通用块', detail: '变更审批通过，影响3份手册（2份重新生成、1份自动同步）', result: '成功' },
      { time: '2026-07-31 14:00', user: '系统', role: '系统', cat: '用户行为', module: '手册生成', action: '生成', target: 'PTR冷却泵EOMM V1.0', detail: '模板组装：8章、79内容块、12参数，2处槽位待人工补充', result: '成功' },
      { time: '2026-07-31 14:05', user: '王工', role: '编制员', cat: '用户行为', module: '手册生成', action: '导出', target: 'PTR冷却泵EOMM_V1.0.docx', detail: '导出 Word 文档，符合排版规范', result: '成功' },
      { time: '2026-07-31 14:30', user: '李工', role: '审核员', cat: '用户行为', module: '手册生成', action: '审校', target: 'PTR冷却泵EOMM', detail: '审校通过，进入定稿发布流程', result: '成功' },
      { time: '2026-07-31 15:42', user: '王工', role: '编制员', cat: '用户行为', module: '内容数据库', action: '导出', target: '跨设备参数对比表', detail: 'PTR/RRI/CEF 三台泵参数并列导出', result: '成功' },
      { time: '2026-08-01 09:05', user: '李工', role: '审核员', cat: '用户行为', module: 'AI审核', action: '修正', target: 'CB-0019', detail: '补充适用条件：入口压力0.1~0.21MPa(g)', result: '成功' },
      { time: '2026-08-01 10:10', user: '张工', role: '管理员', cat: '用户行为', module: '系统管理', action: '枚举维护', target: '设备类型字典', detail: '新增枚举值「热交换器」，已启用', result: '成功' },

      // 知识库应用
      { time: '2026-07-31 15:00', user: '系统', role: '系统', cat: '知识库应用', module: '知识图谱', action: '抽取并入', target: '8 个实体', detail: 'LLM 抽取经人工审核确认并入图谱', result: '成功' },
      { time: '2026-08-01 11:20', user: '系统', role: '系统', cat: '知识库应用', module: '知识图谱', action: '解析', target: '知识节点 KN-024', detail: '新增知识节点「机械密封结构」，状态已发布', result: '成功' },
      { time: '2026-08-02 14:00', user: '系统', role: '系统', cat: '知识库应用', module: '知识图谱', action: '质量检查', target: '向量索引重建', detail: '时序快照：运行阶段图谱已归档', result: '成功' },

      // 应用问答
      { time: '2026-08-03 10:21', user: '王工', role: '编制员', cat: '应用问答', module: 'AI审核', action: '问答', target: '手册编制助手', detail: '自然语言提问：密封环跳动允差', result: '成功' },
      { time: '2026-08-03 10:45', user: '陈工', role: '编制员', cat: '应用问答', module: 'AI审核', action: '问答', target: '故障诊断问答', detail: '查询：上充泵振动异常处理经验', result: '成功' },
      { time: '2026-08-03 11:02', user: '李工', role: '审核员', cat: '应用问答', module: 'AI审核', action: '确认', target: '智能写作建议', detail: '采纳术语标准化建议 3 条', result: '成功' },

      // 接口调用
      { time: '2026-08-03 09:30', user: '系统', role: '系统', cat: '接口调用', module: '应用接口', action: '调用', target: 'IETM 平台 → /blocks', detail: 'cgk_live_8f2a 调用内容块只读接口，耗时 612ms', result: '成功' },
      { time: '2026-08-03 09:31', user: '系统', role: '系统', cat: '接口调用', module: '应用接口', action: '调用', target: 'EAM → /equip/params', detail: 'cgk_live_3c91 拉取设备参数，耗时 880ms', result: '成功' },
      { time: '2026-08-03 09:35', user: '系统', role: '系统', cat: '接口调用', module: '应用接口', action: '调用', target: '统一任务中心(AUE)', detail: '任务回写，cgk_live_b7d4 秘钥已停用，拒绝', result: '成功' },

      // 异常日志
      { time: '2026-08-05 05:00', user: '系统', role: '系统', cat: '异常', module: '知识图谱', action: '异常', target: '知识图谱时序快照', detail: '数据库连接超时，任务已停用，已告警运维', result: '失败' },
      { time: '2026-08-04 16:12', user: '系统', role: '系统', cat: '异常', module: '手册生成', action: '异常', target: '厂家资料自检应用', detail: '接口响应 2380ms 超阈值，错误率 1.1%，触发邮件告警', result: '失败' },
      { time: '2026-08-03 09:40', user: '未知', role: '系统', cat: '异常', module: '系统管理', action: '异常', target: '登录失败', detail: '弱口令尝试 3 次被锁，IP 10.18.2.99', result: '失败' },
      { time: '2026-08-02 14:30', user: '系统', role: '系统', cat: '异常', module: '导入解析', action: '异常', target: 'RRI冷却泵手册.pdf', detail: 'PDF 第 48 页 OCR 置信度 0.62，转人工校对', result: '失败' },
    ];
    const cat = ref('全部');
    const q = ref({ module: '', action: '', role: '', kw: '' });
    const filtered = computed(() => logs.filter(l =>
      (cat.value === '全部' || l.cat === cat.value)
      && (!q.value.module || l.module === q.value.module)
      && (!q.value.action || l.action === q.value.action)
      && (!q.value.role || l.role === q.value.role)
      && (!q.value.kw || (l.target + l.user + l.detail).includes(q.value.kw))));
    function catCount(key) { return key === '全部' ? logs.length : logs.filter(l => l.cat === key).length; }
    function reset() { q.value = { module: '', action: '', role: '', kw: '' }; cat.value = '全部'; }
    function actionType(a) {
      const map = { 导入: 'primary', 解析: 'primary', 确认: 'success', 修正: 'warning', 术语替换: 'warning', 质量检查: 'info', 变更审批: 'danger', 生成: 'primary', 导出: 'info', 审校: 'success', 抽取并入: 'success', 枚举维护: 'info', 登录: 'info', 登出: 'info', 调用: 'primary', 问答: 'success', 异常: 'danger' };
      return map[a] || '';
    }
    function actionColor(a) { const t = actionType(a); return { success:'#00a878', primary:'#0b2a4a', warning:'#ff9800', danger:'#e54848', info:'#6b7a90', '':'#6a5acd' }[t] || '#6a5acd'; }
    const moduleDist = [...new Set(logs.map(l => l.module))];
    const roleDist = [...new Set(logs.map(l => l.role))];
    const successCount = logs.filter(l => l.result === '成功').length;
    const errCount = logs.filter(l => l.result === '失败').length;
    const actionDist = logs.reduce((m, l) => { m[l.action] = (m[l.action]||0)+1; return m; }, {});
    function exportLog() {
      const rows = filtered.value;
      const csv = '时间,操作人,角色,类别,模块,操作类型,对象,详情,结果\n' + rows
        .map(l => `${l.time},${l.user},${l.role},${l.cat},${l.module},${l.action},"${l.target}","${l.detail}",${l.result}`).join('\n');
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
      a.download = '审计日志_' + rows.length + '条.csv';
      a.click(); URL.revokeObjectURL(a.href);
      ElementPlus.ElMessage.success('已导出审计日志 CSV（' + rows.length + ' 条）');
    }
    return { cats, cat, catCount, modules, actions, roles, logs, filtered, q, reset, actionType, actionColor, moduleDist, roleDist, successCount, errCount, actionDist, exportLog, can: window.NP.can };
  },
};
