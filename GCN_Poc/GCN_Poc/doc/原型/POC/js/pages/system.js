/* 系统管理：用户 / 角色权限 / 部门组织（RBAC 后台） */
window.PAGES = window.PAGES || {};
window.PAGES.system = {
  template: `
  <div>
    <el-tabs v-model="tab" type="border-card">
      <!-- 用户管理 -->
      <el-tab-pane name="user">
        <template #label>用户管理 <el-badge :value="users.length" type="info" style="margin-left:4px" /></template>
        <div style="display:flex; gap:10px; align-items:center; margin-bottom:12px;">
          <el-input v-model="userKw" placeholder="姓名/工号/部门" size="small" style="width:200px" clearable />
          <el-select v-model="userRoleFilter" size="small" clearable placeholder="角色" style="width:130px">
            <el-option v-for="r in roles" :key="r" :label="r" :value="r" />
          </el-select>
          <el-button type="primary" size="small" icon="Plus" :disabled="!canAdmin" @click="addUser">新增用户</el-button>
          <el-button size="small" icon="RefreshLeft" :disabled="!canAdmin" @click="resetPwdBatch">批量重置密码</el-button>
          <span class="sub-text" style="margin-left:auto">共 {{ filteredUsers.length }} 人</span>
        </div>
        <el-table :data="filteredUsers" border size="small">
          <el-table-column prop="name" label="姓名" width="90" />
          <el-table-column prop="empNo" label="工号" width="100"><template #default="{row}"><span class="mono">{{ row.empNo }}</span></template></el-table-column>
          <el-table-column prop="dept" label="部门" width="140" />
          <el-table-column label="角色" width="110">
            <template #default="{row}"><el-tag size="small" :type="roleType(row.role)">{{ row.role }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="phone" label="联系方式" width="130" />
          <el-table-column label="状态" width="80" align="center">
            <template #default="{row}"><el-tag size="small" :type="row.status === '启用' ? 'success' : 'info'">{{ row.status }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="lastLogin" label="最近登录" width="150" />
          <el-table-column label="操作" width="200" align="center">
            <template #default="{row}">
              <el-button size="small" text type="primary" :disabled="!canAdmin" @click="editUser(row)">编辑</el-button>
              <el-button size="small" text type="warning" :disabled="!canAdmin" @click="resetPwd(row)">重置密码</el-button>
              <el-button size="small" text :type="row.status === '启用' ? 'danger' : 'success'" :disabled="!canAdmin" @click="toggleUser(row)">{{ row.status === '启用' ? '停用' : '启用' }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 角色权限矩阵 -->
      <el-tab-pane label="角色权限" name="role">
        <div class="sub-text" style="margin-bottom:12px">四级角色权限矩阵（需求「使用权限规则」）。勾选即授予该角色对应能力，实时生效；当前登录角色为 <b>{{ store.role }}</b>。</div>
        <el-table :data="capMatrix" border size="small">
          <el-table-column prop="cap" label="能力" width="140"><template #default="{row}"><b>{{ row.cap }}</b></template></el-table-column>
          <el-table-column prop="desc" label="说明" min-width="220" />
          <el-table-column v-for="r in roles" :key="r" :label="r" width="90" align="center">
            <template #default="{row}">
              <el-checkbox :model-value="ROLE_CAPS[r].includes(row.key)" :disabled="!canAdmin" @change="v => toggleCap(r, row.key, v)" />
            </template>
          </el-table-column>
        </el-table>
        <el-alert type="info" :closable="false" show-icon style="margin-top:12px"
          title="能力定义：edit=编辑/导入/修正  export=导出文档/数据  approve=审核确认/审校/变更审批  admin=系统管理/枚举字典/规则配置" />
      </el-tab-pane>

      <!-- 部门组织 -->
      <el-tab-pane label="部门组织" name="dept">
        <el-row :gutter="14">
          <el-col :span="10">
            <div class="panel">
              <div class="panel-title">组织架构 <el-button size="small" type="primary" icon="Plus" circle :disabled="!canAdmin" @click="msg('新增部门')" /></div>
              <el-tree :data="deptTree" :props="{label:'label'}" default-expand-all>
                <template #default="{data}">
                  <span><b v-if="data.children">{{ data.label }}</b><span v-else>{{ data.label }}</span>
                    <el-tag size="small" effect="plain" style="margin-left:6px">{{ data.count }} 人</el-tag>
                  </span>
                </template>
              </el-tree>
            </div>
          </el-col>
          <el-col :span="14">
            <div class="panel">
              <div class="panel-title">部门职责与数据范围</div>
              <el-table :data="deptRoles" border size="small">
                <el-table-column prop="dept" label="部门" width="130" />
                <el-table-column prop="duty" label="主要职责" min-width="180" />
                <el-table-column prop="scope" label="数据可见范围" min-width="160" />
                <el-table-column prop="defaultRole" label="默认角色" width="100">
                  <template #default="{row}"><el-tag size="small">{{ row.defaultRole }}</el-tag></template>
                </el-table-column>
              </el-table>
              <div class="sub-text" style="margin-top:8px">数据可见范围按部门隔离：编制厂家仅见本厂家产权资料（§权限规则），文档中心见全量。</div>
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- 定时任务 -->
      <el-tab-pane name="task">
        <template #label>定时任务 <el-badge :value="tasks.filter(t=>t.status==='启用').length" type="success" style="margin-left:4px" /></template>
        <div style="display:flex; gap:10px; align-items:center; margin-bottom:12px;">
          <el-button type="primary" size="small" icon="Plus" :disabled="!canAdmin" @click="msg('新建定时任务')">新建任务</el-button>
          <el-button size="small" icon="VideoPlay" :disabled="!canAdmin" @click="msg('查看调度日志')">调度日志</el-button>
          <span class="sub-text" style="margin-left:auto">支持 Cron 表达式 · 计划外手动执行 · 失败重试与告警</span>
        </div>
        <el-table :data="tasks" border size="small">
          <el-table-column prop="name" label="任务名称" min-width="180"><template #default="{row}"><b>{{ row.name }}</b></template></el-table-column>
          <el-table-column prop="type" label="类型" width="110"><template #default="{row}"><el-tag size="small" effect="plain">{{ row.type }}</el-tag></template></el-table-column>
          <el-table-column prop="cron" label="调度表达式" width="150"><template #default="{row}"><span class="mono">{{ row.cron }}</span></template></el-table-column>
          <el-table-column prop="last" label="上次执行" width="150"><template #default="{row}"><span :class="'run-'+row.lastRes">{{ row.last }}</span></template></el-table-column>
          <el-table-column prop="next" label="下次执行" width="150" />
          <el-table-column label="状态" width="80" align="center"><template #default="{row}"><el-tag size="small" :type="row.status==='启用'?'success':'info'">{{ row.status }}</el-tag></template></el-table-column>
          <el-table-column label="操作" width="220" align="center">
            <template #default="{row}">
              <el-button size="small" text type="primary" :disabled="!canAdmin" @click="runTask(row)">立即执行</el-button>
              <el-button size="small" text :disabled="!canAdmin" @click="msg(row.name+' 调度日志')">日志</el-button>
              <el-button size="small" text :type="row.status==='启用'?'warning':'success'" :disabled="!canAdmin" @click="toggleTask(row)">{{ row.status==='启用'?'停用':'启用' }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 配置管理 -->
      <el-tab-pane name="config">
        <template #label>配置管理 <el-badge value="…" type="info" style="margin-left:4px" /></template>
        <el-row :gutter="16">
          <el-col :span="12">
            <div class="panel">
              <div class="panel-title">系统与阈值参数</div>
              <el-form label-width="150px" size="small">
                <el-form-item v-for="c in cfgSystem" :key="c.key" :label="c.label">
                  <el-input v-model="c.value" style="width:160px"><template #append>{{ c.unit }}</template></el-input>
                  <span class="sub-text" style="margin-left:8px">{{ c.hint }}</span>
                </el-form-item>
              </el-form>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="panel">
              <div class="panel-title">集成与安全参数</div>
              <el-form label-width="150px" size="small">
                <el-form-item v-for="c in cfgIntegration" :key="c.key" :label="c.label">
                  <el-input v-model="c.value" :placeholder="c.hint" style="width:240px" :disabled="!canAdmin" />
                </el-form-item>
              </el-form>
              <div class="sub-text" style="margin-top:8px">集成参数对接集团 UAU 授权中台、UBA 审计服务、统一消息队列与 4A 单点登录（后端实现，此处维护接入地址与开关）。</div>
            </div>
          </el-col>
        </el-row>
        <div style="margin-top:12px; text-align:right">
          <el-button @click="resetCfg">还原</el-button>
          <el-button type="primary" :disabled="!canAdmin" @click="saveCfg">保存配置</el-button>
        </div>
      </el-tab-pane>

      <!-- 统计分析 -->
      <el-tab-pane name="stats">
        <template #label>统计分析</template>
        <div class="kpi-row" style="display:flex; gap:12px; margin-bottom:14px">
          <div v-for="k in statKpi" :key="k.label" class="kpi-card" :class="'kpi-'+k.color" style="flex:1; cursor:default">
            <div class="num">{{ k.value }}</div><div class="lbl">{{ k.label }}</div>
            <div class="sub">{{ k.sub }}</div>
          </div>
        </div>
        <el-row :gutter="14">
          <el-col :span="14">
            <div class="chart-card"><div class="cc-title"><span>各部门使用次数（近 30 日）</span><span class="cc-sub">调用次数</span></div><div ref="deptUseEl" class="chart-box" style="height:280px"></div></div>
          </el-col>
          <el-col :span="10">
            <div class="chart-card"><div class="cc-title"><span>接口调用 Top</span><span class="cc-sub">本月</span></div><div ref="apiTopEl" class="chart-box" style="height:280px"></div></div>
          </el-col>
        </el-row>
        <div class="panel" style="margin-top:14px">
          <div class="panel-title">调用明细报表 <el-button size="small" icon="Download" style="float:right" @click="msg('导出统计报表（Excel/PDF）')">导出</el-button></div>
          <el-table :data="statReport" border size="small">
            <el-table-column prop="dept" label="部门" width="130" />
            <el-table-column prop="calls" label="调用次数" width="110" align="right"><template #default="{row}"><b>{{ row.calls }}</b></template></el-table-column>
            <el-table-column prop="active" label="活跃用户" width="100" align="right" />
            <el-table-column prop="audit" label="审查接口调用" width="130" align="right" />
            <el-table-column prop="avgMs" label="平均耗时(ms)" width="120" align="right"><template #default="{row}"><span :class="row.avgMs>2000?'run-fail':'run-ok'">{{ row.avgMs }}</span></template></el-table-column>
            <el-table-column prop="errRate" label="错误率" width="100" align="right"><template #default="{row}"><span :class="row.errRate>0?'run-fail':''">{{ row.errRate }}%</span></template></el-table-column>
            <el-table-column prop="trend" label="环比" min-width="100" />
          </el-table>
        </div>
      </el-tab-pane>

      <!-- 应用管理 -->
      <el-tab-pane name="app">
        <template #label>应用管理 <el-badge :value="apps.filter(a=>a.status==='上架').length" type="success" style="margin-left:4px" /></template>
        <div class="sub-text" style="margin-bottom:12px">个人 / 团队 / 公共搜索问答应用的创建、上下架、可见范围与嵌入方式配置；标准化接口组件库支持 API / 气泡 / iframe 快速移植至第三方业务场景。</div>
        <div style="display:flex; gap:10px; margin-bottom:10px">
          <el-button type="primary" size="small" icon="Plus" :disabled="!canAdmin" @click="msg('新建应用')">新建应用</el-button>
          <el-button size="small" icon="Download" @click="msg('导出日报/周报（PDF/Excel）')">应用监控日周报</el-button>
        </div>
        <el-table :data="apps" border size="small">
          <el-table-column prop="name" label="应用名称" min-width="160"><template #default="{row}"><b>{{ row.name }}</b> <el-tag size="small" effect="plain" style="margin-left:4px">{{ row.scope }}</el-tag></template></el-table-column>
          <el-table-column label="状态" width="90" align="center"><template #default="{row}"><el-tag size="small" :type="row.status==='上架'?'success':'info'">{{ row.status }}</el-tag></template></el-table-column>
          <el-table-column prop="visible" label="可见范围" min-width="140" />
          <el-table-column label="嵌入方式" width="140"><template #default="{row}"><el-tag v-for="m in row.embed" :key="m" size="small" effect="plain" style="margin-right:4px">{{ m }}</el-tag></template></el-table-column>
          <el-table-column prop="calls" label="调用次数" width="100" align="right" />
          <el-table-column prop="resp" label="响应(ms)" width="100" align="right"><template #default="{row}"><span :class="row.resp>800?'run-fail':'run-ok'">{{ row.resp }}</span></template></el-table-column>
          <el-table-column prop="err" label="错误率" width="90" align="right"><template #default="{row}"><span :class="row.err>0?'run-fail':''">{{ row.err }}%</span></template></el-table-column>
          <el-table-column label="操作" width="200" align="center">
            <template #default="{row}">
              <el-button size="small" text type="primary" :disabled="!canAdmin" @click="msg(row.name+' 编辑/参数设置')">编辑</el-button>
              <el-button size="small" text :type="row.status==='上架'?'warning':'success'" :disabled="!canAdmin" @click="toggleApp(row)">{{ row.status==='上架'?'下架':'上架' }}</el-button>
              <el-button size="small" text @click="msg(row.name+' 嵌入方案')">嵌入</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-alert type="warning" :closable="false" show-icon style="margin-top:10px"
          :title="'告警：'+alertApps.length+' 个应用接口响应超阈值或错误率>0，已触发邮件告警（'+alertApps.join('、')+'）'" v-if="alertApps.length" />
      </el-tab-pane>

      <!-- 模型集成 -->
      <el-tab-pane name="model">
        <template #label>模型集成</template>
        <div class="sub-text" style="margin-bottom:12px">大语言模型本地化 / 私有化部署登记；支持快速集成各类模型，本系统不向外部网络传输项目数据。</div>
        <el-table :data="models" border size="small">
          <el-table-column prop="name" label="模型名称" min-width="180"><template #default="{row}"><b>{{ row.name }}</b></template></el-table-column>
          <el-table-column prop="kind" label="类型" width="130"><template #default="{row}"><el-tag size="small" effect="plain">{{ row.kind }}</el-tag></template></el-table-column>
          <el-table-column prop="ver" label="版本" width="100" />
          <el-table-column prop="deploy" label="部署方式" width="120"><template #default="{row}"><el-tag size="small" :type="row.deploy==='私有化'?'success':'info'">{{ row.deploy }}</el-tag></template></el-table-column>
          <el-table-column prop="perf" label="推理性能" min-width="160"><template #default="{row}"><span class="mono">{{ row.perf }}</span></template></el-table-column>
          <el-table-column prop="used" label="用途" min-width="160" />
          <el-table-column label="状态" width="80" align="center"><template #default="{row}"><el-tag size="small" :type="row.status==='在线'?'success':'info'">{{ row.status }}</el-tag></template></el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- API 秘钥 -->
      <el-tab-pane name="api">
        <template #label>API 秘钥</template>
        <div style="display:flex; gap:10px; margin-bottom:10px">
          <el-button type="primary" size="small" icon="Key" :disabled="!canAdmin" @click="msg('生成 API 秘钥')">生成秘钥</el-button>
          <span class="sub-text" style="margin-left:auto">第三方系统通过 API 秘钥对认证方式接入，按秘钥限定可见范围与调用额度</span>
        </div>
        <el-table :data="apiKeys" border size="small">
          <el-table-column prop="app" label="调用方" min-width="160"><template #default="{row}"><b>{{ row.app }}</b></template></el-table-column>
          <el-table-column prop="key" label="API Key" min-width="240"><template #default="{row}"><span class="mono">{{ row.key }}</span></template></el-table-column>
          <el-table-column prop="scope" label="权限范围" min-width="160" />
          <el-table-column prop="quota" label="调用额度" width="120" align="right" />
          <el-table-column prop="used" label="已调用" width="100" align="right" />
          <el-table-column label="状态" width="80" align="center"><template #default="{row}"><el-tag size="small" :type="row.status==='生效'?'success':'info'">{{ row.status }}</el-tag></template></el-table-column>
          <el-table-column label="操作" width="160" align="center">
            <template #default="{row}">
              <el-button size="small" text type="primary" :disabled="!canAdmin" @click="msg('重置 '+row.app+' 秘钥')">重置</el-button>
              <el-button size="small" text :type="row.status==='生效'?'warning':'success'" :disabled="!canAdmin" @click="row.status = row.status==='生效'?'失效':'生效'">{{ row.status==='生效'?'停用':'启用' }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 用户编辑弹窗 -->
    <el-dialog v-model="userDlg" :title="editing.id ? '编辑用户' : '新增用户'" width="480px">
      <el-form label-width="80px" size="small">
        <el-form-item label="姓名" required><el-input v-model="editing.name" /></el-form-item>
        <el-form-item label="工号" required><el-input v-model="editing.empNo" /></el-form-item>
        <el-form-item label="部门"><el-select v-model="editing.dept" style="width:100%"><el-option v-for="d in allDepts" :key="d" :label="d" :value="d" /></el-select></el-form-item>
        <el-form-item label="角色"><el-select v-model="editing.role" style="width:100%"><el-option v-for="r in roles" :key="r" :label="r" :value="r" /></el-select></el-form-item>
        <el-form-item label="联系方式"><el-input v-model="editing.phone" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDlg = false">取消</el-button>
        <el-button type="primary" :disabled="!canAdmin" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>
  </div>`,
  setup() {
    const { ref, computed, watch, onMounted, onUnmounted, nextTick } = Vue;
    const store = window.NP.store;
    const roles = ['管理员', '审核员', '编制员', '浏览者'];
    const ROLE_CAPS = JSON.parse(JSON.stringify(window.NP.ROLE_CAPS));
    const canAdmin = computed(() => (ROLE_CAPS[store.role] || []).includes('admin'));
    const tab = ref('user');

    const users = ref([
      { id: 1, name: '张工', empNo: 'CGN-2018-0312', dept: '文档中心', role: '管理员', phone: '138****6201', status: '启用', lastLogin: '2026-08-03 09:12' },
      { id: 2, name: '李工', empNo: 'CGN-2019-0547', dept: '技术部', role: '审核员', phone: '139****3382', status: '启用', lastLogin: '2026-08-02 16:40' },
      { id: 3, name: '王工', empNo: 'CGN-2020-0891', dept: '技术部', role: '编制员', phone: '137****5502', status: '启用', lastLogin: '2026-08-03 10:05' },
      { id: 4, name: '赵工', empNo: 'CGN-2021-1103', dept: '质检部', role: '审核员', phone: '136****7718', status: '启用', lastLogin: '2026-08-01 14:20' },
      { id: 5, name: '陈工', empNo: 'CQPI-2019-227', dept: '重庆水泵厂', role: '编制员', phone: '158****9004', status: '启用', lastLogin: '2026-07-30 11:00' },
      { id: 6, name: '周工', empNo: 'CGN-2022-0345', dept: '文档中心', role: '编制员', phone: '159****1182', status: '启用', lastLogin: '2026-08-02 09:30' },
      { id: 7, name: '孙工', empNo: 'CGN-2017-0098', dept: '项目部', role: '浏览者', phone: '135****4420', status: '停用', lastLogin: '2026-06-12 10:00' },
    ]);
    const userKw = ref(''); const userRoleFilter = ref('');
    const filteredUsers = computed(() => users.value.filter(u =>
      (!userKw.value || (u.name + u.empNo + u.dept).includes(userKw.value)) &&
      (!userRoleFilter.value || u.role === userRoleFilter.value)));
    const userDlg = ref(false); const editing = ref({});
    function addUser() { editing.value = { name: '', empNo: '', dept: '技术部', role: '编制员', phone: '' }; userDlg.value = true; }
    function editUser(row) { editing.value = { ...row }; userDlg.value = true; }
    function saveUser() {
      if (!editing.value.name || !editing.value.empNo) { ElementPlus.ElMessage.warning('请填写姓名与工号'); return; }
      if (editing.value.id) {
        const i = users.value.findIndex(u => u.id === editing.value.id);
        users.value[i] = { ...editing.value };
      } else {
        editing.value.id = Date.now(); editing.value.status = '启用'; editing.value.lastLogin = '—';
        users.value.push({ ...editing.value });
      }
      userDlg.value = false;
      ElementPlus.ElMessage.success('用户信息已保存');
    }
    function resetPwd(row) { ElementPlus.ElMessage.success('已向 ' + row.phone + ' 发送密码重置链接'); }
    function resetPwdBatch() { ElementPlus.ElMessage.success('已向筛选出的 ' + filteredUsers.value.length + ' 位用户发送密码重置链接'); }
    function toggleUser(row) { row.status = row.status === '启用' ? '停用' : '启用'; ElementPlus.ElMessage.success('用户已' + row.status); }
    function roleType(r) { return { 管理员: 'danger', 审核员: 'warning', 编制员: 'primary', 浏览者: 'info' }[r]; }

    const capMatrix = [
      { key: 'edit', cap: '编辑/导入/修正', desc: '文档导入、内容块编辑与修正、手册生成与微调、知识检索' },
      { key: 'export', cap: '导出', desc: '导出 Word/PDF、导出术语/日志/参数对比数据' },
      { key: 'approve', cap: '审核/审批', desc: 'AI 结果审核确认、手册审校、变更审批、质量检查执行' },
      { key: 'admin', cap: '系统管理', desc: '枚举字典维护、规则配置、用户/角色/部门管理、权限矩阵' },
    ];
    function toggleCap(role, key, val) {
      if (val) ROLE_CAPS[role] = [...new Set([...ROLE_CAPS[role], key])];
      else ROLE_CAPS[role] = ROLE_CAPS[role].filter(c => c !== key);
      window.NP.ROLE_CAPS[role] = ROLE_CAPS[role];
      ElementPlus.ElMessage.success('已' + (val ? '授予' : '撤销') + ' ' + role + ' 的「' + key + '」能力');
    }

    const allDepts = ['文档中心', '技术部', '质检部', '项目部', '重庆水泵厂', '佳木斯电气'];
    const deptTree = [
      { label: '中广核太平岭一期', count: 7, children: [
        { label: '文档中心', count: 2 },
        { label: '技术部', count: 2 },
        { label: '质检部', count: 1 },
        { label: '项目部', count: 1 },
      ]},
      { label: '编制厂家', count: 1, children: [
        { label: '重庆水泵厂', count: 1 },
        { label: '佳木斯电气', count: 0 },
      ]},
    ];
    const deptRoles = [
      { dept: '文档中心', duty: '文档主数据管理、模板维护、变更审批', scope: '全量文档', defaultRole: '管理员' },
      { dept: '技术部', duty: '手册编制、内容编辑、AI审核', scope: '本部门+本厂家', defaultRole: '编制员' },
      { dept: '质检部', duty: '内容审校、质量检查、合规性审查', scope: '受控范围', defaultRole: '审核员' },
      { dept: '项目部', duty: '项目级文件查阅、需求确认', scope: '本项目只读', defaultRole: '浏览者' },
      { dept: '编制厂家', duty: '本厂家产权资料编制', scope: '仅本厂家资料', defaultRole: '编制员' },
    ];

    function msg(t) { ElementPlus.ElMessage.info(t + '：演示功能入口'); }

    /* ---------- 定时任务 ---------- */
    const tasks = ref([
      { name: '数据质量检查', type: '数据治理', cron: '0 2 * * *', last: '2026-08-06 02:00', lastRes: 'ok', next: '2026-08-07 02:00', status: '启用' },
      { name: '术语标准化扫描', type: '数据治理', cron: '0 3 * * 1', last: '2026-08-04 03:00', lastRes: 'ok', next: '2026-08-11 03:00', status: '启用' },
      { name: '信息块去重扫描', type: '数据治理', cron: '0 4 * * *', last: '2026-08-06 04:00', lastRes: 'warn', next: '2026-08-07 04:00', status: '启用' },
      { name: 'AI 抽取结果复核提醒', type: '流程通知', cron: '0 9 * * *', last: '2026-08-06 09:00', lastRes: 'ok', next: '2026-08-07 09:00', status: '启用' },
      { name: '知识库向量索引重建', type: '知识库', cron: '0 1 * * 6', last: '2026-08-03 01:00', lastRes: 'ok', next: '2026-08-10 01:00', status: '启用' },
      { name: '审计日志归档', type: '运维', cron: '0 0 1 * *', last: '2026-08-01 00:00', lastRes: 'ok', next: '2026-09-01 00:00', status: '启用' },
      { name: '知识图谱时序快照', type: '知识库', cron: '0 5 * * *', last: '2026-08-05 05:00', lastRes: 'fail', next: '2026-08-07 05:00', status: '停用' },
    ]);
    function runTask(row) { ElementPlus.ElMessage.success('已触发「' + row.name + '」计划外手动执行，调度日志已记录'); }
    function toggleTask(row) { row.status = row.status === '启用' ? '停用' : '启用'; ElementPlus.ElMessage.success('任务已' + row.status); }

    /* ---------- 配置管理 ---------- */
    const cfgSystemDef = [
      { key: 'dedup', label: '去重相似度阈值', value: '85', unit: '%', hint: '≥阈值判为通用块候选' },
      { key: 'ocr', label: 'OCR 置信度阈值', value: '95', unit: '%', hint: '低于阈值转人工校对' },
      { key: 'param', label: '参数提取置信度', value: '90', unit: '%', hint: '低于阈值标记待确认' },
      { key: 'llm', label: 'LLM 实体抽取召回', value: '85', unit: '%', hint: '召回率验收线' },
      { key: 'sess', label: '会话超时', value: '30', unit: '分钟', hint: '编辑会话保活时长' },
      { key: 'retry', label: '导入失败重试次数', value: '3', unit: '次', hint: '超过即转人工' },
    ];
    const cfgIntegrationDef = [
      { key: 'uau', label: 'UAU 授权中台地址', value: 'https://uau.cgnpc.local', hint: '统一授权' },
      { key: 'uba', label: 'UBA 审计服务地址', value: 'https://uba.cgnpc.local', hint: '日志集中' },
      { key: 'sso', label: '4A 单点登录端点', value: 'https://4a.cgnpc.local/sso', hint: '多因子认证' },
      { key: 'mq', label: '统一消息队列', value: 'kafka://mq.cgnpc.local:9092', hint: '事件发布' },
      { key: 'ietm', label: 'IETM 平台对接', value: '待联调', hint: '数据输出' },
    ];
    const cfgSystem = ref(JSON.parse(JSON.stringify(cfgSystemDef)));
    const cfgIntegration = ref(JSON.parse(JSON.stringify(cfgIntegrationDef)));
    function saveCfg() { ElementPlus.ElMessage.success('配置已保存并生效（后端持久化）'); }
    function resetCfg() { cfgSystem.value = JSON.parse(JSON.stringify(cfgSystemDef)); cfgIntegration.value = JSON.parse(JSON.stringify(cfgIntegrationDef)); ElementPlus.ElMessage.info('已还原为上次保存值'); }

    /* ---------- 统计分析 ---------- */
    const statKpi = [
      { label: '月度调用次数', value: '12,847', sub: '环比 +18%', color: 'blue' },
      { label: '活跃用户', value: '63', sub: '覆盖 5 部门', color: 'cyan' },
      { label: '审查接口调用', value: '2,304', sub: '本月', color: 'green' },
      { label: '平均响应', value: '0.8s', sub: '≤1s 达标', color: 'amber' },
    ];
    const statReport = [
      { dept: '文档中心', calls: 4820, active: 8, audit: 1240, avgMs: 612, errRate: 0, trend: '↑ 12%' },
      { dept: '技术部', calls: 3517, active: 22, audit: 602, avgMs: 748, errRate: 0, trend: '↑ 22%' },
      { dept: '质检部', calls: 1980, active: 12, audit: 388, avgMs: 905, errRate: 0.2, trend: '↑ 8%' },
      { dept: '项目部', calls: 1420, active: 15, audit: 64, avgMs: 1124, errRate: 0, trend: '↑ 5%' },
      { dept: '编制厂家', calls: 1110, active: 6, audit: 10, avgMs: 2380, errRate: 1.1, trend: '↓ 3%' },
    ];
    const deptUseEl = ref(null), apiTopEl = ref(null);
    let charts = []; const statInited = ref(false);
    function initStatCharts() {
      const dept = echarts.init(deptUseEl.value);
      dept.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: 60, right: 30, top: 24, bottom: 28 },
        xAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#7a8699' }, splitLine: { lineStyle: { color: '#eef1f6' } } },
        yAxis: { type: 'category', data: statReport.map(r => r.dept), axisLabel: { fontSize: 11, color: '#3a4658' }, axisLine: { lineStyle: { color: '#dfe4ec' } } },
        series: [{ type: 'bar', data: statReport.map(r => ({ value: r.calls, itemStyle: { color: r.calls > 3000 ? '#0b2a4a' : '#2a6fb0' } })), barWidth: 14, itemStyle: { borderRadius: [0, 6, 6, 0] }, label: { show: true, position: 'right', fontSize: 10, color: '#7a8699' } }],
      });
      const api = echarts.init(apiTopEl.value);
      api.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: { bottom: 0, icon: 'circle', textStyle: { fontSize: 11 } },
        series: [{ type: 'pie', radius: ['42%', '64%'], center: ['50%', '42%'], padAngle: 2, itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
          label: { show: true, formatter: '{c}', fontSize: 11, color: '#3a4658' }, labelLine: { length: 8, length2: 6 },
          data: [
            { name: '语义检索', value: 4180, itemStyle: { color: '#0b2a4a' } },
            { name: '手册生成', value: 2360, itemStyle: { color: '#2a6fb0' } },
            { name: 'AI 辅助编辑', value: 2840, itemStyle: { color: '#00a878' } },
            { name: '参数提取', value: 1980, itemStyle: { color: '#ff9800' } },
            { name: '知识图谱查询', value: 1487, itemStyle: { color: '#6a5acd' } },
          ] }],
      });
      charts.push(dept, api);
    }
    watch(tab, v => { if (v === 'stats' && !statInited.value) { statInited.value = true; nextTick(() => initStatCharts()); } });
    function onResize() { charts.forEach(c => c && c.resize()); }
    onMounted(() => { window.addEventListener('resize', onResize); });
    onUnmounted(() => { window.removeEventListener('resize', onResize); charts.forEach(c => c && c.dispose()); charts = []; });

    /* ---------- 应用管理 ---------- */
    const apps = ref([
      { name: '设备参数智能查询', scope: '公共', status: '上架', visible: '全员', embed: ['API', 'iframe'], calls: 4820, resp: 612, err: 0 },
      { name: '手册编制助手', scope: '团队', status: '上架', visible: '技术部·文档中心', embed: ['气泡', 'iframe'], calls: 2360, resp: 748, err: 0 },
      { name: '故障诊断问答', scope: '公共', status: '上架', visible: '全员', embed: ['API'], calls: 1980, resp: 905, err: 0.2 },
      { name: '术语标准化助理', scope: '团队', status: '上架', visible: '数据治理组', embed: ['API', 'iframe'], calls: 880, resp: 1124, err: 0 },
      { name: '厂家资料自检', scope: '个人', status: '下架', visible: '编制厂家', embed: ['iframe'], calls: 240, resp: 2380, err: 1.1 },
    ]);
    const alertApps = computed(() => apps.value.filter(a => a.status === '上架' && (a.resp > 800 || a.err > 0)).map(a => a.name));
    function toggleApp(row) { row.status = row.status === '上架' ? '下架' : '上架'; ElementPlus.ElMessage.success('应用已' + row.status); }

    /* ---------- 模型集成 ---------- */
    const models = ref([
      { name: 'CGN-LLM-70B', kind: 'LLM', ver: 'v2.1', deploy: '私有化', perf: '42 tok/s · 首 token 0.8s', used: '语义解析/抽取/生成', status: '在线' },
      { name: 'CGN-VL-34B', kind: '多模态', ver: 'v1.4', deploy: '私有化', perf: '复杂表格理解 · 18 tok/s', used: 'OCR/表格语义', status: '在线' },
      { name: 'CGN-Embed', kind: '向量化', ver: 'v3.0', deploy: '私有化', perf: '768 维 · 2.4ms/条', used: '语义检索索引', status: '在线' },
      { name: 'CGN-Rerank', kind: '重排', ver: 'v1.2', deploy: '私有化', perf: 'Top10 重排 · 8ms', used: '检索精排', status: '在线' },
      { name: 'CGN-GraphRAG', kind: '图谱推理', ver: 'v1.0', deploy: '私有化', perf: '社区发现+混合检索', used: '全局/局部检索', status: '在线' },
      { name: 'OCR-Engine', kind: 'OCR', ver: 'v5.2', deploy: '私有化', perf: '扫描件识别 98.6%', used: '扫描版 PDF', status: '在线' },
    ]);

    /* ---------- API 秘钥 ---------- */
    const apiKeys = ref([
      { app: 'IETM 交互手册平台', key: 'cgk_live_8f2a…d14b', scope: '内容块只读/手册生成', quota: '50000/月', used: '18240', status: '生效' },
      { app: '设备资产管理系统(EAM)', key: 'cgk_live_3c91…77e0', scope: '设备/参数只读', quota: '20000/月', used: '4120', status: '生效' },
      { app: '工程文档中心', key: 'cgk_live_a602…9f3c', scope: '知识检索/引用', quota: '100000/月', used: '27560', status: '生效' },
      { app: '统一任务中心(AUE)', key: 'cgk_live_b7d4…2e18', scope: '任务回写', quota: '5000/月', used: '0', status: '失效' },
    ]);

    return {
      tab, users, userKw, userRoleFilter, filteredUsers, roles,
      userDlg, editing, addUser, editUser, saveUser, resetPwd, resetPwdBatch, toggleUser, roleType,
      ROLE_CAPS, capMatrix, toggleCap, canAdmin, store,
      allDepts, deptTree, deptRoles, msg,
      tasks, runTask, toggleTask,
      cfgSystem, cfgIntegration, saveCfg, resetCfg,
      statKpi, statReport, deptUseEl, apiTopEl,
      apps, alertApps, toggleApp,
      models, apiKeys,
    };
  },
};
