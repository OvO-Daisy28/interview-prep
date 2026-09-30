/* P6 内容治理: 术语标准化 / 数据质量 / 变更影响分析 */
window.PAGES = window.PAGES || {};
window.PAGES.govern = {
  template: `
  <div>
    <!-- 治理概览（破"表格墙"，进页即看全局） -->
    <div class="panel gov-overview">
      <div class="gov-cards">
        <div class="gov-card" @click="tab='term'"><div class="gv-num warn">{{ pendingTerms }}</div><div class="gv-lbl">术语待处理</div></div>
        <div class="gov-card" @click="tab='quality'"><div class="gv-num danger">{{ qualityErrors }}</div><div class="gv-lbl">质量错误</div></div>
        <div class="gov-card" @click="tab='dedup'"><div class="gv-num">{{ dedupGroups.length }}</div><div class="gv-lbl">相似块组</div></div>
        <div class="gov-card" @click="tab='change'"><div class="gv-num" style="color:var(--np-cyan)">{{ analyzed ? impact.affected.length : '—' }}</div><div class="gv-lbl">变更影响手册</div></div>
        <div class="gov-card" @click="tab='consistency'"><div class="gv-num" style="color:var(--np-purple)">{{ conflicts.length + termVariants.length }}</div><div class="gv-lbl">跨文档冲突</div></div>
      </div>
      <div class="gov-bar">
        <span class="sub-text">问题分布</span>
        <div class="gv-stacked">
          <div class="gv-seg warn" :style="'width:' + barPct(pendingTerms) + '%'" :title="'术语 '+pendingTerms"></div>
          <div class="gv-seg danger" :style="'width:' + barPct(qualityErrors*2) + '%'" :title="'质量 '+qualityErrors"></div>
          <div class="gv-seg" :style="'width:' + barPct(dedupGroups.length*2) + '%;background:var(--np-cyan)'" :title="'去重 '+dedupGroups.length"></div>
          <div class="gv-seg" :style="'width:' + barPct(conflicts.length*3) + '%;background:var(--np-purple)'" :title="'冲突 '+conflicts.length"></div>
        </div>
      </div>
    </div>
    <el-tabs v-model="tab" type="border-card">
      <!-- 术语标准化 -->
      <el-tab-pane name="term">
        <template #label>术语标准化 <el-badge v-if="pendingTerms" :value="pendingTerms" type="warning" style="margin-left:4px" /></template>
        <el-row :gutter="14">
          <el-col :span="14">
            <div class="panel">
              <div class="panel-title">
                <span>术语标准化字典</span>
                <span class="pt-badge">{{ terms.length }} 条 · 演示</span>
                <span class="pt-badge" style="color:var(--np-success); background:rgba(46,139,87,.12)">全量 512 条 ≥500</span>
                <span>
                  <el-button size="small" icon="Upload" @click="showImport">导入</el-button>
                  <el-button size="small" icon="Download" @click="exportTerms">导出</el-button>
                  <el-button size="small" type="primary" icon="Plus" @click="addVisible = true">新增</el-button>
                </span>
              </div>
              <el-table :data="terms" border size="small" max-height="480">
                <el-table-column prop="std" label="标准术语" width="130">
                  <template #default="{row}"><b style="color:var(--np-primary)">{{ row.std }}</b></template>
                </el-table-column>
                <el-table-column label="同义词 / 别名" min-width="220">
                  <template #default="{row}">
                    <el-tag v-for="s in row.syn" :key="s" size="small" effect="plain" style="margin-right:6px">{{ s }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="status" label="状态" width="90" align="center">
                  <template #default="{row}">
                    <el-tag size="small" :type="row.status === '已发布' ? 'success' : 'warning'">{{ row.status }}</el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-col>
          <el-col :span="10">
            <div class="panel">
              <div class="panel-title">入库自动检测（待确认 {{ pendingTerms }} 条）</div>
              <div v-for="d in detections" :key="d.found + d.location"
                   style="border:1px solid var(--np-border); border-radius:4px; padding:10px 12px; margin-bottom:8px;">
                <template v-if="d.action === 'pending'">
                  <div style="font-size:12.5px;">
                    发现非标准术语 <el-tag size="small" type="warning">{{ d.found }}</el-tag>
                    → 建议替换为 <el-tag size="small" type="success">{{ d.std }}</el-tag>
                  </div>
                  <div class="sub-text" style="margin:6px 0;">位置：{{ d.location }}</div>
                  <el-button size="small" type="success" :disabled="!can('edit')" @click="applyTerm(d)">标准化替换</el-button>
                  <el-button size="small" plain :disabled="!can('approve')" @click="keepTerm(d)">确认保留</el-button>
                </template>
                <template v-else>
                  <el-tag size="small" :type="d.action === 'replaced' ? 'success' : 'info'">
                    {{ d.action === 'replaced' ? '已替换为「' + d.std + '」' : '已确认保留「' + d.found + '」' }}
                  </el-tag>
                </template>
              </div>
              <el-alert type="info" :closable="false" show-icon style="margin-top:10px"
                title="术语变体发现与标准化处理保留原文溯源：替换操作记录原词、位置与操作人。" />
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- 数据质量 -->
      <el-tab-pane label="数据质量检查" name="quality">
        <el-row :gutter="14">
          <el-col :span="9">
            <div class="panel">
              <div class="panel-title">检查规则引擎</div>
              <div v-for="r in rules" :key="r.name"
                   style="display:flex; align-items:center; gap:8px; padding:9px 4px; border-bottom:1px dashed var(--np-border);">
                <el-switch v-model="r.enabled" size="small" />
                <div style="flex:1">
                  <div style="display:flex; align-items:center; gap:6px;">
                    <span style="font-weight:600; font-size:12.5px;">{{ r.name }}</span>
                    <el-tag size="small" effect="plain" :type="ruleTagType(r)">{{ ruleTypeLabel(r) }}</el-tag>
                    <el-tag v-if="r.device && r.device!=='all'" size="small" type="info" effect="plain">{{ r.deviceLabel || r.device }}</el-tag>
                  </div>
                  <div class="sub-text">{{ r.desc }}</div>
                </div>
              </div>
              <div style="margin-top:12px; display:flex; gap:8px;">
                <el-button type="primary" icon="VideoPlay" :disabled="!can('approve')" @click="runCheck" :loading="checking">立即运行检查</el-button>
                <el-button icon="Timer" @click="showSchedule">定时设置</el-button>
                <el-button icon="Plus" @click="ruleVisible = true">自定义规则</el-button>
              </div>
            </div>
          </el-col>
          <el-col :span="15">
            <div class="panel">
              <div class="panel-title">
                <span>检查报告</span>
                <span v-if="report" class="sub-text">{{ report.time }} · {{ report.scope }}</span>
              </div>
              <template v-if="report">
                <el-row :gutter="10" style="margin-bottom:12px;">
                  <el-col :span="8"><div class="kpi-card kpi-red" style="min-height:90px; cursor:default;"><div class="kpi-top"><div class="kpi-icon"><el-icon :size="18"><WarningFilled /></el-icon></div></div><div class="num">{{ countBy('错误') }}</div><div class="lbl">错误</div></div></el-col>
                  <el-col :span="8"><div class="kpi-card kpi-amber" style="min-height:90px; cursor:default;"><div class="kpi-top"><div class="kpi-icon"><el-icon :size="18"><Bell /></el-icon></div></div><div class="num">{{ countBy('警告') }}</div><div class="lbl">警告</div></div></el-col>
                  <el-col :span="8"><div class="kpi-card" style="min-height:90px; cursor:default; --kpi-color:#7a8699;"><div class="kpi-top"><div class="kpi-icon"><el-icon :size="18"><InfoFilled /></el-icon></div></div><div class="num">{{ countBy('提示') }}</div><div class="lbl">提示</div></div></el-col>
                </el-row>
                <el-table :data="report.issues" border size="small">
                  <el-table-column prop="rule" label="检查规则" width="130" />
                  <el-table-column label="级别" width="80" align="center">
                    <template #default="{row}">
                      <el-tag size="small" :type="{错误:'danger', 警告:'warning', 提示:'info'}[row.level]">{{ row.level }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="desc" label="问题描述" min-width="280" />
                  <el-table-column prop="target" label="数据对象" width="110" />
                  <el-table-column label="操作" width="100" align="center">
                    <template #default="{row}">
                      <el-button size="small" text type="primary" @click="locate(row)">定位修正</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </template>
              <el-empty v-else description="点击「立即运行检查」生成数据质量报告" :image-size="80" />
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- 内容去重与复用 -->
      <el-tab-pane label="去重与复用" name="dedup">
        <el-row :gutter="14">
          <el-col :span="15">
            <div class="panel">
              <div class="panel-title">
                <span>语义相似内容块识别</span>
                <span class="sub-text">去重阈值 {{ dedupThreshold }}% · 基于 Embedding 文本相似度</span>
              </div>
              <div style="margin-bottom:10px; display:flex; align-items:center; gap:10px;">
                <span class="sub-text">去重阈值：</span>
                <el-slider v-model="dedupThreshold" :min="70" :max="98" :step="1" style="flex:1; max-width:260px" :format-tooltip="v => v + '%'" />
                <el-button size="small" type="primary" icon="Search" @click="rescanDedup">重新扫描</el-button>
              </div>
              <el-table :data="dedupGroups" border size="small">
                <el-table-column label="相似组" width="80" align="center" type="index" />
                <el-table-column label="代表内容块" min-width="220">
                  <template #default="{row}"><span class="mono">{{ row.canonical }}</span><div class="sub-text">{{ row.preview }}</div></template>
                </el-table-column>
                <el-table-column label="重复块数" width="90" align="center">
                  <template #default="{row}"><el-tag size="small" type="warning">{{ row.dupes.length }}</el-tag></template>
                </el-table-column>
                <el-table-column label="最高相似度" width="140">
                  <template #default="{row}"><el-progress :percentage="Math.round(row.maxSim*100)" :stroke-width="10" :color="row.maxSim>=0.9?'#2e8b57':'#e6a23c'" /></template>
                </el-table-column>
                <el-table-column label="操作" width="170" align="center">
                  <template #default="{row}">
                    <el-button size="small" type="success" plain @click="mergeGroup(row)">合并为通用块</el-button>
                    <el-button size="small" text @click="row.expanded = !row.expanded">{{ row.expanded ? '收起' : '查看' }}</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-alert type="info" :closable="false" show-icon style="margin-top:10px"
                title="合并后保留代表块为通用内容块，其余转为引用；一处修改自动同步所有引用手册（需求§166）。原文留痕，可回退。" />
            </div>
          </el-col>
          <el-col :span="9">
            <div class="panel">
              <div class="panel-title">复用统计 <span class="pt-badge">{{ reuseStats.totalRefs }} 处引用</span></div>
              <div v-for="s in reuseStats.items" :key="s.name" style="margin-bottom:10px;">
                <div style="display:flex; justify-content:space-between; font-size:12.5px;"><b>{{ s.name }}</b><span class="sub-text">{{ s.refs }} 处引用</span></div>
                <el-progress :percentage="s.pct" :stroke-width="8" :color="s.pct>=60?'#2e8b57':s.pct>=30?'#e6a23c':'#7a8699'" />
              </div>
              <el-descriptions :column="1" border size="small" style="margin-top:8px">
                <el-descriptions-item label="通用块总数">{{ reuseStats.commonBlocks }}</el-descriptions-item>
                <el-descriptions-item label="自动同步次数（本月）">{{ reuseStats.syncCount }}</el-descriptions-item>
                <el-descriptions-item label="节省内容块数">{{ reuseStats.saved }}</el-descriptions-item>
              </el-descriptions>
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- 变更管理 -->
      <el-tab-pane label="变更管理" name="change">
        <el-row :gutter="14">
          <el-col :span="10">
            <div class="panel">
              <div class="panel-title">变更申请</div>
              <el-alert type="warning" :closable="false" show-icon style="margin-bottom:12px"
                title="通用内容块修改将同步所有引用手册，须走变更审批流程。" />
              <el-form label-width="90px" size="small">
                <el-form-item label="变更对象">
                  <el-input :model-value="impact.block.id + ' ' + impact.block.title" disabled />
                </el-form-item>
                <el-form-item label="变更原因"><el-input v-model="changeReason" type="textarea" :rows="3" placeholder="填写变更原因（必填，全程可追溯）" /></el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="analyze" :loading="analyzing" :disabled="!can('approve')">影响范围分析</el-button>
                  <el-button type="warning" plain :disabled="!can('approve') || !analyzed" @click="submitApproval">提交审批</el-button>
                </el-form-item>
              </el-form>
            </div>
          </el-col>
          <el-col :span="14">
            <div class="panel">
              <div class="panel-title">影响范围分析</div>
              <template v-if="analyzed">
                <div style="margin-bottom:10px;">
                  内容块 <el-tag size="small">{{ impact.block.id }}</el-tag> 被
                  <b style="color:var(--np-danger)">{{ impact.affected.length }}</b> 份手册引用：
                </div>
                <div v-for="a in impact.affected" :key="a.manual"
                     style="border:1px solid var(--np-border); border-left:4px solid var(--np-warn); border-radius:4px; padding:10px 12px; margin-bottom:8px;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <b>{{ a.manual }}</b>
                    <el-tag size="small" :type="a.status === '自动同步' ? 'success' : 'danger'">{{ a.status }}</el-tag>
                  </div>
                  <div class="sub-text" style="margin-top:6px;">涉及章节：<el-tag v-for="c in a.chapters" :key="c" size="small" effect="plain" style="margin-right:6px">{{ c }}</el-tag></div>
                </div>
                <el-alert type="info" :closable="false" show-icon title="标记为「通用」的内容块一处修改自动同步所有引用手册；已发布手册需重新生成版本。" />
              </template>
              <el-empty v-else description="运行影响范围分析，评估内容块修改波及的手册" :image-size="80" />
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>
      <!-- 跨文档全局一致性 -->
      <el-tab-pane label="全局一致性" name="consistency">
        <div class="sub-text" style="margin-bottom:12px">跨文档数据一致性治理：检测跨文件参数冲突、术语变体、跨设备参数异常与全局重复段（需求§46/§159）。</div>
        <el-row :gutter="14">
          <el-col :span="12">
            <div class="panel">
              <div class="panel-title"><span>跨文档参数冲突</span><span class="pt-badge" style="color:var(--np-danger); background:#fde8e8">{{ conflicts.length }} 处</span></div>
              <div v-for="c in conflicts" :key="c.param" class="conflict-row">
                <div style="display:flex; align-items:center; gap:8px;">
                  <el-icon color="var(--np-danger)" :size="16"><WarningFilled /></el-icon>
                  <b>{{ c.param }}</b>
                  <span class="sub-text" style="margin-left:auto">涉及 {{ c.files }} 份文件</span>
                </div>
                <div style="margin-top:6px; display:flex; gap:8px; flex-wrap:wrap;">
                  <el-tag v-for="(v, f) in c.values" :key="f" size="small" :type="v.std ? 'success' : 'warning'">{{ f }}: {{ v.val }}{{ v.unit }}</el-tag>
                </div>
                <div style="margin-top:6px; display:flex; gap:6px;">
                  <el-button size="small" type="primary" :disabled="!can('approve')" @click="resolveConflict(c)">采纳标准值并同步</el-button>
                  <span class="sub-text">{{ c.suggest }}</span>
                </div>
              </div>
            </div>
            <div class="panel">
              <div class="panel-title"><span>跨文档术语变体</span><span class="pt-badge">{{ termVariants.length }} 组</span></div>
              <el-table :data="termVariants" border size="small">
                <el-table-column prop="std" label="标准术语" width="110"><template #default="{row}"><b style="color:var(--np-primary)">{{ row.std }}</b></template></el-table-column>
                <el-table-column label="发现变体" min-width="200"><template #default="{row}"><el-tag v-for="v in row.variants" :key="v" size="small" effect="plain" style="margin-right:6px">{{ v }}</el-tag></template></el-table-column>
                <el-table-column prop="files" label="文件数" width="80" align="center" />
                <el-table-column label="操作" width="110" align="center"><template #default="{row}"><el-button size="small" type="success" plain :disabled="!can('edit')" @click="standardizeVariant(row)">统一标准化</el-button></template></el-table-column>
              </el-table>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="panel">
              <div class="panel-title"><span>跨设备参数异常</span><span class="sub-text">同类设备参数偏离 ±20% 重点复核</span></div>
              <el-table :data="deviceAnomalies" border size="small">
                <el-table-column prop="param" label="参数" width="100" />
                <el-table-column label="设备间取值" min-width="200">
                  <template #default="{row}"><el-tag v-for="(v, d) in row.devices" :key="d" size="small" :type="v.anomaly ? 'danger' : 'success'" effect="plain" style="margin-right:6px">{{ d }}: {{ v.val }}{{ v.unit }}</el-tag></template>
                </el-table-column>
                <el-table-column prop="deviation" label="偏差" width="90" align="center"><template #default="{row}"><el-tag size="small" type="warning">{{ row.deviation }}</el-tag></template></el-table-column>
                <el-table-column prop="note" label="建议" min-width="120" />
              </el-table>
            </div>
            <div class="panel">
              <div class="panel-title"><span>全局重复段落</span><span class="pt-badge">{{ globalDupes.length }} 组</span></div>
              <div v-for="g in globalDupes" :key="g.preview" style="border:1px solid var(--np-border); border-left:3px solid var(--np-warn); border-radius:5px; padding:9px 12px; margin-bottom:8px; background:#fafbfd;">
                <div style="font-size:12.5px;">{{ g.preview }}</div>
                <div style="margin-top:5px; display:flex; gap:8px; align-items:center;">
                  <el-tag size="small" type="warning">{{ g.files }} 份文件重复</el-tag>
                  <el-tag size="small" effect="plain">最高相似度 {{ (g.sim * 100).toFixed(0) }}%</el-tag>
                  <el-button size="small" text type="primary" style="margin-left:auto" :disabled="!can('approve')" @click="mergeGlobal(g)">并入通用块</el-button>
                </div>
              </div>
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>
    </el-tabs>

    <!-- 新增术语 -->
    <el-dialog v-model="addVisible" title="新增术语映射" width="480px">
      <el-form label-width="90px" size="small">
        <el-form-item label="标准术语" required><el-input v-model="newTerm.std" placeholder="如：机械密封" /></el-form-item>
        <el-form-item label="同义词"><el-input v-model="newTerm.syn" placeholder="多个同义词用逗号分隔，如：机封,轴封" /></el-form-item>
        <el-form-item label="初始状态">
          <el-radio-group v-model="newTerm.status">
            <el-radio value="评审中">评审中</el-radio>
            <el-radio value="已发布">直接发布</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVisible = false">取消</el-button>
        <el-button type="primary" @click="addTerm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 自定义检查规则 -->
    <el-dialog v-model="ruleVisible" title="自定义检查规则" width="520px">
      <el-form label-width="90px" size="small">
        <el-form-item label="规则名称" required><el-input v-model="newRule.name" placeholder="如：力矩范围检查" /></el-form-item>
        <el-form-item label="规则类型">
          <el-select v-model="newRule.type" style="width:100%">
            <el-option label="合理性检查（数值范围）" value="range" />
            <el-option label="一致性检查（跨块取值比对）" value="consistency" />
            <el-option label="完整性检查（必填字段）" value="required" />
          </el-select>
        </el-form-item>
        <el-form-item label="适用设备">
          <el-select v-model="newRule.device" style="width:100%">
            <el-option label="全部设备" value="all" />
            <el-option label="PTR冷却泵" value="ptr" />
            <el-option label="核级泵类（按设备类型）" value="nuclear-pump" />
          </el-select>
        </el-form-item>
        <el-form-item label="规则描述"><el-input v-model="newRule.desc" type="textarea" :rows="2" placeholder="如：螺栓力矩值应在 50~1000 N·m 范围内" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleVisible = false">取消</el-button>
        <el-button type="primary" @click="addRule">保存并启用</el-button>
      </template>
    </el-dialog>
  </div>`,

  setup() {
    const { ref, computed } = Vue;
    const M = window.MOCK;
    const tab = ref('term');
    const detections = ref(M.termDetections.map(d => ({ ...d })));
    const pendingTerms = computed(() => detections.value.filter(d => d.action === 'pending').length);
    function applyTerm(d) { d.action = 'replaced'; ElementPlus.ElMessage.success(`已将「${d.found}」替换为「${d.std}」，原文已留痕`); }
    function keepTerm(d) { d.action = 'kept'; ElementPlus.ElMessage.info(`已确认保留「${d.found}」`); }

    const rules = ref(M.qualityRules.map(r => ({ ...r })));
    const RULE_TYPE = { '完整性检查': '完整性', '一致性检查': '一致性', '合理性检查': '合理性', '关联完整性检查': '关联完整性', range: '合理性', consistency: '一致性', required: '完整性' };
    function ruleTypeLabel(r) { return RULE_TYPE[r.name] || RULE_TYPE[r.type] || '自定义'; }
    function ruleTagType(r) { const t = ruleTypeLabel(r); return { 完整性: 'warning', 一致性: 'primary', 合理性: 'danger', 关联完整性: 'success', 自定义: 'info' }[t] || ''; }
    const checking = ref(false);
    const report = ref(null);
    function runCheck() {
      checking.value = true;
      setTimeout(() => { report.value = M.qualityReport; checking.value = false; ElementPlus.ElMessage.success('检查完成，报告已推送至管理员'); }, 1400);
    }
    function countBy(level) { return report.value ? report.value.issues.filter(i => i.level === level).length : 0; }
    const qualityErrors = computed(() => report.value ? report.value.issues.filter(i => i.level === '错误').length : 4);
    function barPct(n) { return Math.min(100, (n || 0) * 6); }

    const impact = M.changeImpact;
    const changeReason = ref('');
    const analyzing = ref(false);
    const analyzed = ref(false);
    function analyze() {
      analyzing.value = true; analyzed.value = false;
      setTimeout(() => { analyzing.value = false; analyzed.value = true; }, 1200);
    }
    function msg(t) { ElementPlus.ElMessage.info(t); }
    const D = window.NP.showDialog;

    // 术语：导入/导出/新增（真实行为）
    const termsRef = ref(M.terms.map(t => ({ ...t })));
    const addVisible = ref(false);
    const newTerm = ref({ std: '', syn: '', status: '评审中' });
    function addTerm() {
      if (!newTerm.value.std.trim()) { ElementPlus.ElMessage.warning('请填写标准术语'); return; }
      termsRef.value.push({
        std: newTerm.value.std.trim(),
        syn: newTerm.value.syn.split(/[,，]/).map(s => s.trim()).filter(Boolean),
        status: newTerm.value.status,
      });
      addVisible.value = false;
      newTerm.value = { std: '', syn: '', status: '评审中' };
      ElementPlus.ElMessage.success('术语映射已保存，入库检测将按新字典执行');
    }
    function showImport() {
      D('批量导入术语字典', `
        <p>支持 Excel(.xlsx) / CSV 格式，列结构：<b>标准术语 | 同义词（逗号分隔）| 状态</b>。</p>
        <table>
          <tr><th>步骤</th><th>说明</th></tr>
          <tr><td>1. 选择文件</td><td>单次≤2000 条，UTF-8 编码</td></tr>
          <tr><td>2. 预检</td><td>自动识别重复映射、循环映射（A→B 且 B→A）</td></tr>
          <tr><td>3. 合并入库</td><td>与现有字典合并，冲突项进入「评审中」</td></tr>
        </table>
        <p class="sub-text" style="color:#7a8699">用于与外部术语标准（如核电行业术语库）对接。</p>`);
    }
    function exportTerms() {
      const csv = '﻿标准术语,同义词,状态\n' + termsRef.value
        .map(t => `${t.std},"${t.syn.join('、')}",${t.status}`).join('\n');
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      a.download = '术语标准化字典_' + termsRef.value.length + '条.csv';
      a.click();
      URL.revokeObjectURL(a.href);
      ElementPlus.ElMessage.success('已导出 CSV（' + termsRef.value.length + ' 条），可与外部术语标准对接');
    }

    // 数据质量：定时/自定义规则/定位
    function showSchedule() {
      D('定时检查设置', `
        <table>
          <tr><th style="width:130px">配置项</th><th>当前值</th></tr>
          <tr><td>执行频率</td><td>每日 02:00（Cron: 0 2 * * *）</td></tr>
          <tr><td>检查范围</td><td>全部入库数据（可配置为指定设备类型）</td></tr>
          <tr><td>报告推送</td><td>系统消息 + 邮件推送至数据管理员</td></tr>
          <tr><td>最近执行</td><td class="ok">2026-07-31 02:00 · 发现 2 错误 / 1 警告 / 1 提示</td></tr>
        </table>`);
    }
    const ruleVisible = ref(false);
    const newRule = ref({ name: '', type: 'range', device: 'all', desc: '' });
    function addRule() {
      if (!newRule.value.name.trim()) { ElementPlus.ElMessage.warning('请填写规则名称'); return; }
      const devMap = { all: '全部设备', ptr: 'PTR冷却泵', 'nuclear-pump': '核级泵类' };
      rules.value.push({
        name: newRule.value.name.trim(),
        desc: newRule.value.desc || '自定义规则 · 适用：' + (devMap[newRule.value.device] || newRule.value.device),
        enabled: true,
        type: newRule.value.type,
        device: newRule.value.device,
        deviceLabel: devMap[newRule.value.device],
      });
      ruleVisible.value = false;
      newRule.value = { name: '', type: 'range', device: 'all', desc: '' };
      ElementPlus.ElMessage.success('规则已保存并启用，下次检查生效');
    }
    function locate(row) {
      if (row.target === '内容块') {
        window.NP.go('database');
        ElementPlus.ElMessage.info('已跳转内容数据库，请检索定位问题内容块');
      } else {
        window.NP.go('parse');
        setTimeout(() => ElementPlus.ElMessage.info('已跳转内容解析页，请在「参数」标签中定位修正：' + row.desc), 400);
      }
    }

    // 内容去重与复用（需求§164-166）
    const dedupThreshold = ref(85);
    const dedupGroups = ref([
      { canonical: 'CB-0042', preview: '人员资格与培训要求（安全通用）', dupes: ['CB-0117', 'CB-0203'], maxSim: 0.97, expanded: false },
      { canonical: 'CB-0018', preview: '起吊作业安全注意事项', dupes: ['CB-0099', 'CB-0188', 'CB-0241'], maxSim: 0.94, expanded: false },
      { canonical: 'CB-0007', preview: '设备存储环境要求（温湿度）', dupes: ['CB-0156'], maxSim: 0.91, expanded: false },
      { canonical: 'CB-0033', preview: '联轴器对中通用说明', dupes: ['CB-0172', 'CB-0220'], maxSim: 0.88, expanded: false },
      { canonical: 'CB-0029', preview: '备件订购信息提供要求', dupes: ['CB-0198'], maxSim: 0.86, expanded: false },
    ]);
    function rescanDedup() {
      ElementPlus.ElMessage.success('已按阈值 ' + dedupThreshold.value + '% 重新扫描，识别 ' + dedupGroups.value.length + ' 组相似内容块');
    }
    function mergeGroup(row) {
      ElementPlus.ElMessage.success('已将「' + row.preview + '」合并为通用块，' + row.dupes.length + ' 个重复块转为引用，' + (row.dupes.length + 1) + ' 份手册将自动同步');
    }
    const reuseStats = {
      commonBlocks: 18, totalRefs: 53, syncCount: 7, saved: 35,
      items: [
        { name: '安全注意事项通用块', refs: 12, pct: 72 },
        { name: '人员资格培训通用块', refs: 9, pct: 58 },
        { name: '存储环境要求通用块', refs: 7, pct: 42 },
        { name: '联轴器对中通用块', refs: 6, pct: 36 },
        { name: '备件订购通用块', refs: 5, pct: 28 },
      ],
    };

    // 跨文档全局一致性（需求§46/§159）
    const conflicts = [
      { param: '额定流量', files: 3, values: { 'PTR冷却泵': { val: '640', unit: 'm³/h', std: true }, 'RRI冷却泵': { val: '642', unit: 'm³/h', std: false }, 'CEF补水泵': { val: '638', unit: 'm³/h', std: false } }, suggest: '三台泵同型，642/638 疑似量程基准不同，建议统一为 640 并核对量程' },
      { param: '额定扬程', files: 2, values: { 'PTR冷却泵': { val: '36', unit: 'm', std: true }, 'RRI冷却泵': { val: '38.5', unit: 'm', std: false } }, suggest: '扬程偏差 6.9%，超 ±5% 阈值，核对设计工况点' },
      { param: '轴承润滑方式', files: 2, values: { 'PTR冷却泵': { val: '油润滑', unit: '', std: true }, 'RRI冷却泵': { val: '脂润滑', unit: '', std: false } }, suggest: '同型号应一致，疑似录入差异，核实后统一' },
    ];
    function resolveConflict(c) { ElementPlus.ElMessage.success('已采纳标准值并同步至 ' + c.files + ' 份文件，差异留痕可追溯'); }
    const termVariants = [
      { std: '机械密封', variants: ['机封', '轴封', '机械轴封'], files: 18 },
      { std: '联轴器', variants: ['联轴节', '靠背轮', '对轮'], files: 14 },
      { std: '膜片联轴器', variants: ['叠片联轴器', '挠性膜片联轴节'], files: 9 },
      { std: '螺栓力矩', variants: ['紧固力矩', '拧紧力矩'], files: 11 },
    ];
    function standardizeVariant(row) { ElementPlus.ElMessage.success('已将 ' + row.variants.length + ' 个变体统一为「' + row.std + '」，涉及 ' + row.files + ' 份文件原文留痕'); }
    const deviceAnomalies = [
      { param: '额定流量', devices: { PTR: { val: 640, unit: 'm³/h' }, RRI: { val: 642, unit: 'm³/h', anomaly: false }, CEF: { val: 520, unit: 'm³/h', anomaly: true } }, deviation: 'CEF -19%', note: 'CEF补水泵流量偏低，核实是否同类设备' },
      { param: '电机功率', devices: { PTR: { val: 90, unit: 'kW' }, RRI: { val: 90, unit: 'kW' }, CEF: { val: 75, unit: 'kW', anomaly: true } }, deviation: 'CEF -17%', note: '功率匹配流量，建议复核配套电机选型' },
      { param: '转速', devices: { PTR: { val: 1480, unit: 'r/min' }, RRI: { val: 1480, unit: 'r/min' }, CEF: { val: 2950, unit: 'r/min', anomaly: true } }, deviation: 'CEF +99%', note: 'CEF为2极高速泵，非同型，分类复核' },
    ];
    const globalDupes = [
      { preview: '人员资格与培训要求（安全通用）', files: 28, sim: 0.97 },
      { preview: '起吊作业安全注意事项', files: 24, sim: 0.94 },
      { preview: '设备存储环境要求（温湿度）', files: 21, sim: 0.91 },
      { preview: '备件订购信息提供要求', files: 15, sim: 0.86 },
    ];
    function mergeGlobal(g) { ElementPlus.ElMessage.success('已将「' + g.preview + '」并入通用块，' + g.files + ' 份文件转为引用，自动同步'); }

    // 变更审批
    function submitApproval() {
      D('变更审批流程', `
        <p>变更对象：<b>${impact.block.id} ${impact.block.title}</b> · 影响 ${impact.affected.length} 份手册</p>
        <div class="step-line">① 编制员（王工）提交变更申请 · <span class="ok">已完成 10:32</span></div>
        <div class="step-line">② 审核员（李工）技术审核 · <span class="warn">待处理</span></div>
        <div class="step-line" style="border-color:#c0c8d4; background:#fafbfc">③ 管理员批准并触发生成 · 待处理</div>
        <p class="sub-text" style="color:#7a8699">审批通过后：在编手册自动同步；已发布手册触发重新生成任务，全程留痕可追溯。</p>`);
      ElementPlus.ElMessage.success('变更申请已提交审核员');
    }

    return {
      tab, terms: termsRef, detections, pendingTerms, applyTerm, keepTerm,
      rules, checking, report, runCheck, countBy, qualityErrors, barPct, ruleTypeLabel, ruleTagType,
      impact, changeReason, analyzing, analyzed, analyze, msg,
      addVisible, newTerm, addTerm, showImport, exportTerms,
      showSchedule, ruleVisible, newRule, addRule, locate, submitApproval,
      dedupThreshold, dedupGroups, rescanDedup, mergeGroup, reuseStats, can: window.NP.can,
      conflicts, resolveConflict, termVariants, standardizeVariant, deviceAnomalies, globalDupes, mergeGlobal,
    };
  },
};
