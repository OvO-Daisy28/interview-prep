/* P7 手册生成: 模板管理 / 生成向导 / 组装 / 在线预览微调 / 导出Word */
window.PAGES = window.PAGES || {};
window.PAGES.generate = {
  template: `
  <div>
    <el-tabs v-model="tab" type="border-card">
      <!-- ========== 模板管理 ========== -->
      <el-tab-pane label="模板管理" name="tpl">
        <div style="display:flex; gap:14px;">
          <div class="panel" style="width:260px; min-width:260px;">
            <div class="panel-title">
              <span>模板列表</span>
              <el-button size="small" type="primary" icon="Plus" circle @click="newTpl" />
            </div>
            <div v-for="t in templates" :key="t.id" class="tpl-card" :class="{active: selTpl.id === t.id}" @click="selTpl = t">
              <div class="tpl-head">
                <span class="tpl-ic"><el-icon :size="16"><Notebook /></el-icon></span>
                <b>{{ t.name }}</b>
                <el-tag size="small" effect="plain">{{ t.version }}</el-tag>
              </div>
              <div class="sub-text" style="margin-top:5px;">适用：{{ t.deviceType }} · {{ t.chapters.length }} 章</div>
              <div class="tpl-actions">
                <el-button size="small" text type="primary" @click.stop="deriveTpl(t)">派生</el-button>
                <el-button size="small" text type="primary" @click.stop="compareTpl(t)">版本对比</el-button>
              </div>
            </div>
          </div>
          <div class="panel" style="flex:1">
            <div class="panel-title">
              <span>模板编辑器 · {{ selTpl.name }}</span>
              <span class="sub-text">章节结构定义 + 内容槽位定义 + 条件化规则</span>
            </div>
            <el-table :data="tplRows" border size="small" row-key="rid" default-expand-all
                      :tree-props="{children: 'children'}">
              <el-table-column prop="name" label="章节 / 槽位" min-width="240">
                <template #default="{row}">
                  <el-icon v-if="row.isSlot" color="#7a8699" style="vertical-align:-2px; margin-right:4px;"><Connection /></el-icon>
                  <b v-if="!row.isSlot">{{ row.name }}</b><span v-else>{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column label="类型" width="110" align="center">
                <template #default="{row}">
                  <el-tag v-if="row.isSlot" size="small" :type="typeColor(row.slotType)">{{ row.slotType }}</el-tag>
                  <span v-else class="sub-text">章节</span>
                </template>
              </el-table-column>
              <el-table-column label="必含" width="70" align="center">
                <template #default="{row}">
                  <el-icon v-if="!row.isSlot && row.required" color="#c0392b"><StarFilled /></el-icon>
                </template>
              </el-table-column>
              <el-table-column label="条件化规则" width="150" align="center">
                <template #default="{row}">
                  <el-tag v-if="row.condition" size="small" type="warning" effect="plain">核级设备包含</el-tag>
                  <span v-else class="sub-text">—</span>
                </template>
              </el-table-column>
              <el-table-column prop="source" label="内容来源" min-width="180">
                <template #default="{row}"><span class="sub-text">{{ row.source }}</span></template>
              </el-table-column>
            </el-table>
            <div style="margin-top:14px; text-align:center;">
              <el-button type="primary" size="large" icon="Promotion" @click="startWizard">使用该模板生成手册</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ========== 手册生成 ========== -->
      <el-tab-pane label="手册生成" name="gen">
        <!-- 生成向导 -->
        <div v-if="stage === 'wizard'" class="panel" style="max-width:680px; margin:30px auto;">
          <div class="panel-title">生成向导</div>
          <el-steps :active="2" align-center style="margin-bottom:24px;">
            <el-step title="选择模板" /><el-step title="选择设备" /><el-step title="组装生成" />
          </el-steps>
          <el-form label-width="110px">
            <el-form-item label="目标模板">
              <el-select v-model="genTplId" style="width:100%">
                <el-option v-for="t in templates" :key="t.id" :label="t.name + '（' + t.version + '）'" :value="t.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="目标设备">
              <el-select v-model="genDev" style="width:100%">
                <el-option label="PTR冷却泵（PTR-001 · 核安全3级 / QA1）" value="PTR冷却泵" />
                <el-option label="RRI冷却泵（RRI-002 · 核安全3级）" value="RRI冷却泵" />
              </el-select>
            </el-form-item>
            <el-form-item label="输出格式">
              <el-checkbox-group v-model="formats">
                <el-checkbox value="word" label="Word (.docx)" />
                <el-checkbox value="pdf" label="PDF" />
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="批量生成">
              <el-switch v-model="batch" />
              <span class="sub-text" style="margin-left:8px">选定一批设备按同一模板批量派生手册</span>
            </el-form-item>
            <el-form-item v-if="batch" label="设备批次">
              <el-checkbox-group v-model="batchDevices">
                <el-checkbox value="PTR冷却泵" label="PTR冷却泵（PTR-001）" />
                <el-checkbox value="RRI冷却泵" label="RRI冷却泵（RRI-002）" />
                <el-checkbox value="CEF补水泵" label="CEF补水泵（CEF-003）" />
              </el-checkbox-group>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" size="large" icon="MagicStick" @click="assemble">开始智能组装</el-button>
            </el-form-item>
          </el-form>
        </div>

        <!-- 组装动画 -->
        <div v-if="stage === 'assembling'" class="panel assemble-panel" style="max-width:680px; margin:30px auto;">
          <div class="panel-title">正在组装手册 <span class="ai-badge">AI + 规则引擎</span></div>
          <div class="assemble-timeline">
            <div v-for="(s, i) in assembleSteps" :key="s.label" class="asm-step" :class="{done: s.done, running: s.running}">
              <div class="asm-badge">
                <el-icon v-if="s.done" :size="16"><CircleCheckFilled /></el-icon>
                <el-icon v-else-if="s.running" class="is-loading" :size="16"><Loading /></el-icon>
                <span v-else>{{ i + 1 }}</span>
              </div>
              <div class="asm-body">
                <div class="asm-label">{{ s.label }}</div>
                <div class="sub-text">{{ s.detail }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 在线预览 -->
        <div v-if="stage === 'preview'">
          <div class="panel" style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
            <b>《{{ manual.equipment }}设备运行与维修手册》</b>
            <el-tag size="small" type="success">组装完成</el-tag>
            <el-tag size="small" type="warning" effect="plain">{{ emptySlots }} 处待人工补充</el-tag>
            <el-tag size="small" type="info" effect="plain">排版规范 v1.0 ✓</el-tag>
            <span style="margin-left:auto"></span>
            <el-checkbox v-model="editMode" :disabled="!can('edit')" style="margin-right:6px;">预览微调模式</el-checkbox>
            <el-button size="small" icon="Upload" :disabled="!can('edit') || !dirty" @click="writeBack">回写数据库</el-button>
            <el-button size="small" icon="View" :disabled="!can('approve')" @click="submitReview">提交审校</el-button>
            <el-button type="primary" size="small" icon="Document" :disabled="!can('export')" @click="exportWord">导出 Word</el-button>
            <el-button size="small" icon="Printer" :disabled="!can('export')" @click="exportPdf">导出 PDF</el-button>
          </div>

          <el-alert v-if="dirtyRefs > 0" type="warning" :closable="false" show-icon style="margin-bottom:10px"
            :title="'引用的 ' + dirtyRefs + ' 处通用内容块已变更，建议重审后重新生成'">
            <template #default><el-button size="small" type="warning" plain @click="reviewDirty">去内容数据库核查</el-button></template>
          </el-alert>

          <div class="doc-desk">
            <div class="doc-preview">
              <!-- 封面 -->
              <div class="doc-cover">
                <div class="sub-text">{{ meta.equipmentCode }}</div>
                <div class="doc-name">{{ manual.equipment }}设备<br>运行与维修手册</div>
                <div class="sub-text">（依据模板：{{ manual.tplName }} 自动生成）</div>
                <table style="width:300px; margin:40px auto 0;">
                  <tr><td>设备编码</td><td>{{ manual.equipment === 'PTR冷却泵' ? 'PTR-001' : 'RRI-002' }}</td></tr>
                  <tr><td>核安全等级</td><td>{{ meta.nuclearLevel }}</td></tr>
                  <tr><td>质保等级</td><td>{{ meta.qaLevel }}</td></tr>
                  <tr><td>版本</td><td>V1.0（2026-07-31 自动生成）</td></tr>
                </table>
              </div>

              <!-- 目录 -->
              <h2 style="margin-top:40px;">目录（自动生成）</h2>
              <div v-for="c in manual.chapters" :key="'toc' + c.no" style="padding:2px 0;">
                <span class="mono">{{ c.no }}</span>&nbsp;&nbsp;{{ c.title }}
                <span v-if="c.skipped" class="sub-text">（条件化裁剪：非核级设备不包含）</span>
              </div>

              <!-- 章节 -->
              <template v-for="c in manual.chapters" :key="c.no">
                <template v-if="!c.skipped">
                  <h2 :id="'ch' + c.no">第{{ c.no }}章 {{ c.title }}</h2>
                  <template v-for="(item, i) in c.items" :key="c.no + '-' + i">
                    <!-- 文本块 -->
                    <div v-if="item.kind === 'text'" style="position:relative;">
                      <div v-if="item.safety" class="safety-box" :class="'safety-' + item.safety">
                        <span class="s-tag">【{{ item.safety }}】</span>{{ item.text }}
                      </div>
                      <p v-else style="margin:6px 0; text-indent:2em;">{{ item.text }}</p>
                      <div v-if="editMode" style="position:absolute; right:0; top:0; background:rgba(255,255,255,.9);">
                        <el-button size="small" text icon="Top" @click="moveItem(c, i, -1)" />
                        <el-button size="small" text icon="Bottom" @click="moveItem(c, i, 1)" />
                        <el-button size="small" text icon="Edit" @click="editItem(item)" />
                      </div>
                    </div>
                    <!-- 参数表 -->
                    <table v-else-if="item.kind === 'params'">
                      <tr><th>参数名称</th><th>数值</th><th>单位</th><th>分类</th><th>所属部件</th></tr>
                      <tr v-for="p in item.rows" :key="p.id"><td>{{ p.name }}</td><td>{{ p.value }}</td><td>{{ p.unit }}</td><td>{{ p.category }}</td><td>{{ p.component }}</td></tr>
                    </table>
                    <!-- 通用表格 -->
                    <table v-else-if="item.kind === 'table'">
                      <tr><th v-for="(h, hi) in item.header" :key="hi">{{ h }}</th></tr>
                      <tr v-for="(r, ri) in item.rows" :key="ri"><td v-for="(cell, ci) in r" :key="ci">{{ cell }}</td></tr>
                    </table>
                    <!-- 参数键值（核安全等级等） -->
                    <table v-else-if="item.kind === 'kv'">
                      <tr v-for="kv in item.rows" :key="kv[0]"><td style="width:40%">{{ kv[0] }}</td><td>{{ kv[1] }}</td></tr>
                    </table>
                    <!-- 空槽位 -->
                    <div v-else-if="item.kind === 'empty'" class="slot-empty">
                      ⚠ 槽位「{{ item.slot }}」暂无匹配内容，需人工补充
                      <el-button size="small" text type="primary" @click="goDatabase">去补充</el-button>
                    </div>
                  </template>
                </template>
              </template>

              <!-- 有效页 -->
              <h2 style="margin-top:36px;">有效页清单（自动更新）</h2>
              <table>
                <tr><th>章节</th><th>页码</th><th>版本</th><th>日期</th></tr>
                <tr v-for="c in manual.chapters.filter(x => !x.skipped)" :key="'vp' + c.no">
                  <td>第{{ c.no }}章 {{ c.title }}</td><td>{{ 2 + Number(c.no) * 3 }}~{{ 4 + Number(c.no) * 3 }}</td><td>V1.0</td><td>2026-07-31</td>
                </tr>
              </table>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ========== 批量生成 ========== -->
      <el-tab-pane name="batch">
        <template #label>批量生成 <el-badge v-if="batchJobs.filter(j=>j.status==='生成中').length" :value="batchJobs.filter(j=>j.status==='生成中').length" type="primary" style="margin-left:4px" /></template>
        <div class="sub-text" style="margin-bottom:10px">选定一批设备按同一模板批量生成手册；队列并发执行，逐台组装、逐台记录槽位缺口与审校状态（需求§手册生成-文档输出-4）。</div>
        <div style="display:flex; gap:10px; margin-bottom:10px">
          <el-button type="primary" size="small" icon="Plus" :disabled="!can('edit')" @click="newBatchJob">新建批量任务</el-button>
          <el-button size="small" icon="VideoPlay" :disabled="!can('edit') || !batchJobs.some(j=>j.status==='排队')" @click="runBatch">启动排队任务</el-button>
          <span class="sub-text" style="margin-left:auto">共 {{ batchJobs.length }} 个任务 · 成功 {{ batchDone }} · 失败 {{ batchFailed }} · 进行中 {{ batchRunning }}</span>
        </div>
        <div v-for="j in batchJobs" :key="j.id" class="panel" style="margin-bottom:10px">
          <div class="panel-title"><span>{{ j.name }}</span>
            <span class="pt-badge">{{ j.devices.length }} 台设备</span>
            <span class="pt-badge">{{ j.tpl }}</span>
            <el-tag size="small" :type="batchStatusType(j.status)" effect="plain" style="margin-left:6px">{{ j.status }}</el-tag>
            <el-button size="small" text type="primary" style="margin-left:auto" :disabled="j.status!=='完成'" @click="msg(j.name+' 批量导出 Word/PDF')">批量导出</el-button>
          </div>
          <div class="bm-progress" style="margin-bottom:8px">
            <div class="bmp-label">进度 <b>{{ j.pct }}%</b> · {{ j.done }}/{{ j.devices.length }} 成功 · 失败 {{ j.failed }}</div>
            <div class="bmp-bar"><div class="bmp-fill" :style="'width:' + j.pct + '%'"></div></div>
          </div>
          <el-table :data="j.devices" border size="small">
            <el-table-column prop="name" label="目标设备" min-width="140"><template #default="{row}"><b>{{ row.name }}</b></template></el-table-column>
            <el-table-column prop="sys" label="系统" width="120" />
            <el-table-column prop="type" label="设备类型" width="120" />
            <el-table-column label="状态" width="100" align="center"><template #default="{row}"><el-tag size="small" :type="batchStatusType(row.status)">{{ row.status }}</el-tag></template></el-table-column>
            <el-table-column label="空槽位" width="90" align="center"><template #default="{row}"><span :class="row.empty>0?'run-warn':''">{{ row.empty }}</span></template></el-table-column>
            <el-table-column label="耗时" width="90" align="right"><template #default="{row}"><span class="mono">{{ row.ms ? row.ms+'s' : '—' }}</span></template></el-table-column>
            <el-table-column label="操作" width="160" align="center">
              <template #default="{row}">
                <el-button size="small" text type="primary" :disabled="row.status!=='完成'" @click="msg('预览 '+row.name+' 手册')">预览</el-button>
                <el-button size="small" text :disabled="row.status!=='完成'" @click="msg('导出 '+row.name+' Word/PDF')">导出</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
    <el-dialog v-model="reviewVisible" title="提交人工审校 · 生成—审校—修正—定稿 闭环" width="560px">
      <el-steps :active="1" align-center style="margin-bottom:18px;">
        <el-step title="生成" description="AI 组装完成" />
        <el-step title="审校" description="当前环节" />
        <el-step title="修正" description="意见反馈触发内容修正" />
        <el-step title="定稿" description="发布版本" />
      </el-steps>
      <el-form label-width="90px" size="small">
        <el-form-item label="审校人">
          <el-select v-model="reviewer" style="width:100%">
            <el-option label="李工（主任工程师）" value="李工" />
            <el-option label="王工（高级工程师）" value="王工" />
          </el-select>
        </el-form-item>
        <el-form-item label="审校意见">
          <el-input v-model="reviewComment" type="textarea" :rows="3" placeholder="填写审校意见，将反馈并触发内容修正…" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewVisible = false">取消</el-button>
        <el-button type="warning" plain @click="sendReview(false)">退回修正</el-button>
        <el-button type="primary" @click="sendReview(true)">审校通过</el-button>
      </template>
    </el-dialog>
  </div>`,

  setup() {
    const { ref, computed } = Vue;
    const M = window.MOCK;
    const meta = M.meta;
    const tab = ref('tpl');
    const msg = t => ElementPlus.ElMessage.info(t + '：POC 演示功能入口');

    // ---------- 模板 ----------
    const templates = ref(M.templates.map(t => ({ ...t })));
    const selTpl = ref(templates.value[0]);
    function newTpl() {
      window.NP.showDialog('新建模板', `
        <h4>两种方式</h4>
        <div class="step-line">① 空白创建：逐章定义章节结构、内容槽位与条件化规则</div>
        <div class="step-line">② 反向提取（推荐）：从已拆解的工程文件中自动提取章节框架与槽位结构，大幅降低模板创建工作量</div>
        <p class="sub-text" style="color:#7a8699">反向提取候选：PTR冷却泵设备运行与维修手册（已拆解 79 个内容块、8 章结构完整）。模板保存后进入版本管理（V1.0），支持多套模板并行维护。</p>`);
    }
    function deriveTpl(t) {
      const copy = JSON.parse(JSON.stringify(t));
      copy.id = t.id + '-D' + (templates.value.filter(x => x.id.startsWith(t.id)).length);
      copy.name = t.name.replace('模板', '') + '派生模板';
      copy.version = 'V1.0';
      templates.value.push(copy);
      selTpl.value = copy;
      ElementPlus.ElMessage.success(`已基于「${t.name} ${t.version}」派生新模板，可在编辑器中调整章节与槽位`);
    }
    function compareTpl(t) {
      window.NP.showDialog('模板版本对比 · ' + t.name, `
        <table>
          <tr><th>对比项</th><th>V2.0</th><th class="ok">V2.1（当前）</th></tr>
          <tr><td>章节数</td><td>8</td><td>8（无变化）</td></tr>
          <tr><td>槽位定义</td><td>故障处理章仅含故障表</td><td class="ok">新增「故障隔离程序」槽位</td></tr>
          <tr><td>条件化规则</td><td>仅核安全等级</td><td class="ok">新增抗震类别条件</td></tr>
          <tr><td>修改人 / 时间</td><td>王工 · 2026-07-15</td><td>李工 · 2026-07-28</td></tr>
        </table>
        <p class="sub-text" style="color:#7a8699">模板支持复制、派生与任意版本对比；历史版本可回退。</p>`);
    }
    const tplRows = computed(() => selTpl.value.chapters.map((c, i) => ({
      rid: 'c' + i, name: `第${c.no}章 ${c.title}`, isSlot: false,
      required: c.required, condition: c.condition, source: '',
      children: c.slots.map((s, j) => ({
        rid: `c${i}s${j}`, name: s.source, isSlot: true,
        slotType: s.type === '参数' ? '技术要求' : s.type === '表格' ? '描述说明' : s.type,
        required: false, condition: s.condition || null, source: '内容块类型: ' + s.type,
      })),
    })));
    function startWizard() { tab.value = 'gen'; }

    // ---------- 生成向导 ----------
    const stage = ref('wizard');
    const genTplId = ref(templates.value[0].id);
    const genDev = ref('PTR冷却泵');
    const formats = ref(['word']);
    const batch = ref(false);
    const batchDevices = ref(['PTR冷却泵']);

    /* ---------- 批量生成任务队列 ---------- */
    const DEV_POOL = [
      { name: 'RRI冷却泵', sys: 'RRI', type: '核级泵' },
      { name: 'CEF补水泵', sys: 'CEF', type: '核级泵' },
      { name: 'PTR冷却泵', sys: 'PTR', type: '核级泵' },
      { name: 'RCV上充泵', sys: 'RCV', type: '核级泵' },
      { name: 'EAS喷淋泵', sys: 'EAS', type: '核级泵' },
      { name: 'TEP冷却泵', sys: 'TEP', type: '非核级泵' },
    ];
    function mkJob(id, name, tpl, devNames, status, pct, done, failed) {
      return { id, name, tpl, status, pct, done, failed,
        devices: devNames.map(n => { const d = DEV_POOL.find(x => x.name === n); return { ...d, status, empty: 0, ms: 0 }; }) };
    }
    const batchJobs = ref([
      { id: 1, name: '核级泵类批量生成 · V1.0', tpl: 'EOMM-泵类-核级 V2.3', status: '完成', pct: 100, done: 3, failed: 0,
        devices: [
          { name: 'PTR冷却泵', sys: 'PTR', type: '核级泵', status: '完成', empty: 2, ms: 4.2 },
          { name: 'RRI冷却泵', sys: 'RRI', type: '核级泵', status: '完成', empty: 0, ms: 3.8 },
          { name: 'CEF补水泵', sys: 'CEF', type: '核级泵', status: '完成', empty: 1, ms: 4.0 },
        ] },
      { id: 2, name: '上充泵/喷淋泵批量生成 · V1.0', tpl: 'EOMM-泵类-核级 V2.3', status: '生成中', pct: 50, done: 1, failed: 0,
        devices: [
          { name: 'RCV上充泵', sys: 'RCV', type: '核级泵', status: '完成', empty: 3, ms: 4.5 },
          { name: 'EAS喷淋泵', sys: 'EAS', type: '核级泵', status: '生成中', empty: 0, ms: 0 },
        ] },
      { id: 3, name: 'TEP冷却泵批量生成 · V1.0', tpl: 'EOMM-泵类-非核级 V1.2', status: '排队', pct: 0, done: 0, failed: 0,
        devices: [{ name: 'TEP冷却泵', sys: 'TEP', type: '非核级泵', status: '排队', empty: 0, ms: 0 }] },
    ]);
    const batchDone = computed(() => batchJobs.value.filter(j => j.status === '完成').length);
    const batchFailed = computed(() => batchJobs.value.reduce((s, j) => s + j.failed, 0));
    const batchRunning = computed(() => batchJobs.value.filter(j => j.status === '生成中').length);
    function batchStatusType(s) { return { 完成: 'success', 生成中: 'primary', 排队: 'info', 失败: 'danger' }[s] || ''; }
    let batchSeq = 4;
    function newBatchJob() {
      ElementPlus.ElMessageBox.prompt('输入批量任务名称', '新建批量生成任务', { inputValue: '新批量任务 · V1.0', confirmButtonText: '创建', cancelButtonText: '取消' })
        .then(({ value }) => {
          if (!value) return;
          batchJobs.value.push({ id: batchSeq++, name: value.trim(), tpl: 'EOMM-泵类-核级 V2.3', status: '排队', pct: 0, done: 0, failed: 0,
            devices: DEV_POOL.slice(0, 3).map(d => ({ ...d, status: '排队', empty: 0, ms: 0 })) });
          ElementPlus.ElMessage.success('批量任务已创建并入队');
        }).catch(() => {});
    }
    function runBatch() {
      const job = batchJobs.value.find(j => j.status === '排队');
      if (!job) return;
      job.status = '生成中';
      let i = 0;
      (function step() {
        if (i >= job.devices.length) { job.status = '完成'; job.pct = 100; job.done = job.devices.length; ElementPlus.ElMessage.success('批量任务「' + job.name + '」全部完成'); return; }
        const d = job.devices[i];
        d.status = '生成中';
        setTimeout(() => {
          d.status = '完成'; d.empty = Math.floor(Math.random() * 4); d.ms = (3.5 + Math.random()).toFixed(1);
          i++; job.done = i; job.pct = Math.round(i / job.devices.length * 100);
          step();
        }, 700);
      })();
    }

    const assembleSteps = ref([]);
    const manual = ref({ chapters: [], equipment: '', tplName: '' });
    const emptySlots = ref(0);

    function blocksOf(chapterPrefix, type) {
      return M.blocks.filter(b => b.chapterPath.split('/').some(s => s.startsWith(chapterPrefix))
        && (!type || b.contentType === type));
    }

    function buildManual() {
      const tpl = templates.value.find(t => t.id === genTplId.value);
      const isNuclear = true; // PTR/RRI 均为核级
      let empty = 0;
      const chapters = tpl.chapters.map(c => {
        const skipped = c.condition === 'nuclear' && !isNuclear;
        const items = [];
        const pushTexts = (bs, limit) => bs.slice(0, limit || 6).forEach(b =>
          items.push({ kind: 'text', text: b.content.replace(/^注意[:：!！]?|^警告[:：!！]?/, ''), safety: b.safetyLevel, bid: b.id }));
        if (c.title === '概述') {
          items.push({ kind: 'kv', rows: [['核安全等级', meta.nuclearLevel], ['质保等级', meta.qaLevel], ['抗震类别', meta.seismic], ['编制厂家', meta.manufacturer]] });
          pushTexts(blocksOf('0.4'), 5);
        } else if (c.title === '设备描述') {
          items.push({ kind: 'params', rows: M.params });
          pushTexts(blocksOf('1.2'), 6);
        } else if (c.title === '安装调试') {
          if (M.tables.torqueTable) items.push({ kind: 'table', header: M.tables.torqueTable.header, rows: M.tables.torqueTable.rows });
          items.push({ kind: 'empty', slot: '安装/对中操作步骤' }); empty++;
        } else if (c.title === '运行细则') {
          pushTexts(blocksOf('2.3'), 4);
        } else if (c.title === '故障处理') {
          if (M.tables.faultTable) items.push({ kind: 'table', header: M.tables.faultTable.header, rows: M.tables.faultTable.rows.slice(0, 10) });
        } else if (c.title === '维护维修') {
          pushTexts(blocksOf('3.7'), 6);
          if (M.tables.spareTable) items.push({ kind: 'table', header: M.tables.spareTable.header, rows: M.tables.spareTable.rows.slice(0, 8) });
        } else if (c.title === '图纸和文件') {
          if (M.tables.deviceCodeTable) items.push({ kind: 'table', header: M.tables.deviceCodeTable.header, rows: M.tables.deviceCodeTable.rows.slice(0, 8) });
        } else {
          items.push({ kind: 'empty', slot: c.slots.map(s => s.source).join('、') || c.title }); empty++;
        }
        return { no: c.no, title: c.title, skipped, items };
      });
      emptySlots.value = empty;
      manual.value = { equipment: genDev.value, tplName: tpl.name, chapters };
    }

    function assemble() {
      stage.value = 'assembling';
      const steps = [
        { label: '检索内容块', detail: '从内容数据库检索 ' + M.blocks.length + ' 个内容块、' + M.params.length + ' 条参数' },
        { label: '参数槽位填充', detail: '填入目标设备参数：额定流量 640m³/h、扬程 36m、转速 1480r/min…' },
        { label: '条件化裁剪', detail: '核安全3级设备：保留核安全/质保章节' },
        { label: '章节编号编排', detail: '编号连续性与层级校验通过' },
        { label: '目录与有效页生成', detail: '目录 8 章 · 有效页清单已更新 · 版本信息 V1.0' },
      ].map(s => ({ ...s, done: false, running: false }));
      assembleSteps.value = steps;
      let i = 0;
      (function run() {
        if (i > 0) steps[i - 1].done = true;
        if (i >= steps.length) {
          buildManual();
          stage.value = 'preview';
          const batchTip = batch.value ? `（批量批次 ${batchDevices.value.length} 台设备已建生成队列，当前预览第 1 台）` : '';
          ElementPlus.ElMessage.success('手册组装完成' + batchTip + '，' + emptySlots.value + ' 处槽位待人工补充');
          return;
        }
        steps[i].running = true;
        i++;
        setTimeout(run, 900 + Math.random() * 500);
      })();
    }

    const dirtyRefs = computed(() => window.NP.store.dirtyManualRefs);
    function reviewDirty() { window.NP.clearManualDirty(); window.NP.go('database'); }

    // ---------- 微调 ----------
    const editMode = ref(false);
    const dirty = ref(false);
    function moveItem(c, i, dir) {
      const j = i + dir;
      if (j < 0 || j >= c.items.length) return;
      const t = c.items[i]; c.items[i] = c.items[j]; c.items[j] = t;
      dirty.value = true;
    }
    function editItem(item) {
      ElementPlus.ElMessageBox.prompt('编辑段落内容', '在线微调', {
        inputValue: item.text, inputType: 'textarea',
      }).then(({ value }) => { item.text = value; dirty.value = true; }).catch(() => {});
    }
    function writeBack() {
      dirty.value = false;
      ElementPlus.ElMessage.success('微调内容已回写数据库，相关内容块版本 +1');
    }
    function goDatabase() {
      window.NP.go('database');
      ElementPlus.ElMessage.info('已跳转内容数据库，检索匹配内容后可补充到该槽位');
    }

    // ---------- 人工审校 ----------
    const reviewVisible = ref(false);
    const reviewer = ref('李工');
    const reviewComment = ref('');
    function submitReview() { reviewVisible.value = true; }
    function sendReview(pass) {
      reviewVisible.value = false;
      if (pass) {
        ElementPlus.ElMessage.success(`审校通过，手册进入定稿发布流程（V1.0 → 受控发布）`);
      } else {
        ElementPlus.ElMessage.warning(`已退回修正：审校意见已反馈至内容数据库，触发相关内容块修正任务`);
      }
    }

    // ---------- 导出 ----------
    function exportWord() {
      const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, AlignmentType, HeadingLevel, Header, Footer, PageNumber, TabStopType, TabStopPosition, BorderStyle } = docx;
      const m = manual.value;
      const children = [];
      children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 2400, after: 400 },
        children: [new TextRun({ text: m.equipment + '设备运行与维修手册', bold: true, size: 48, font: 'SimHei' })] }));
      children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
        children: [new TextRun({ text: '模板：' + m.tplName + ' · 版本 V1.0 · 2026-07-31 自动生成', size: 20, color: '666666' })] }));
      children.push(new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: '目录', bold: true, size: 32, font: 'SimHei' })] }));
      m.chapters.filter(c => !c.skipped).forEach(c => children.push(new Paragraph({
        children: [new TextRun({ text: `第${c.no}章 ${c.title}`, size: 24 })] })));
      m.chapters.filter(c => !c.skipped).forEach(c => {
        children.push(new Paragraph({ pageBreakBefore: c.no === '1', heading: HeadingLevel.HEADING_2, spacing: { before: 300, after: 200 },
          children: [new TextRun({ text: `第${c.no}章 ${c.title}`, bold: true, size: 30, font: 'SimHei' })] }));
        c.items.forEach(item => {
          if (item.kind === 'text') {
            children.push(new Paragraph({ spacing: { after: 120 },
              children: [new TextRun({ text: (item.safety ? `【${item.safety}】` : '') + item.text, size: 21, bold: !!item.safety, color: item.safety ? 'B03A2E' : '000000' })] }));
          } else if (item.kind === 'empty') {
            children.push(new Paragraph({ spacing: { after: 120 },
              children: [new TextRun({ text: `【待补充】槽位「${item.slot}」暂无匹配内容`, size: 21, color: 'B8860B', highlight: 'yellow' })] }));
          } else {
            const header = item.kind === 'params' ? ['参数名称', '数值', '单位', '分类', '所属部件']
              : item.kind === 'kv' ? ['项目', '内容'] : item.header;
            const rows = item.kind === 'params' ? item.rows.map(p => [p.name, p.value, p.unit, p.category, p.component])
              : item.kind === 'kv' ? item.rows : item.rows;
            children.push(new Table({
              width: { size: 100, type: WidthType.PERCENTAGE },
              rows: [new TableRow({ children: header.map(h => new TableCell({
                shading: { fill: 'EEF2F8' },
                children: [new Paragraph({ children: [new TextRun({ text: String(h), bold: true, size: 18 })] })] })) }),
                ...rows.map(r => new TableRow({ children: r.map(cell => new TableCell({
                  children: [new Paragraph({ children: [new TextRun({ text: String(cell), size: 18 })] })] })) }))],
            }));
            children.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
          }
        });
      });
      const equipCode = m.equipment === 'PTR冷却泵' ? 'PTR-001' : 'RRI-002';
      // 页眉：设备编码 + 文档名 + 版本 + 密级，底部细分隔线
      const header = new Header({ children: [new Paragraph({
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: '1B4F9C' } },
        tabStops: [{ type: TabStopType.RIGHT, position: 9360 }],
        children: [
          new TextRun({ text: equipCode + ' · ' + m.equipment + '设备运行与维修手册', size: 16, color: '888888' }),
          new TextRun({ text: '\tV1.0 · 密级：内部', size: 16, color: '888888' }),
        ],
      })] });
      // 页脚：项目名 + 页码 + 生成日期
      const footer = new Footer({ children: [new Paragraph({
        tabStops: [{ type: TabStopType.CENTER, position: 4680 }, { type: TabStopType.RIGHT, position: 9360 }],
        children: [
          new TextRun({ text: '中广核 · 太平岭一期采购文件结构化试点', size: 14, color: 'AAAAAA' }),
          new TextRun({ text: '\t第 ', size: 14, color: 'AAAAAA' }),
          new TextRun({ children: [PageNumber.CURRENT], size: 14, color: 'AAAAAA' }),
          new TextRun({ text: ' 页 / 共 ', size: 14, color: 'AAAAAA' }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 14, color: 'AAAAAA' }),
          new TextRun({ text: ' 页\t2026-07-31', size: 14, color: 'AAAAAA' }),
        ],
      })] });
      const doc = new Document({
        styles: { default: { document: { run: { font: 'SimSun', size: 21 } } } },
        sections: [{ headers: { default: header }, footers: { default: footer }, children }],
      });
      Packer.toBlob(doc).then(blob => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = m.equipment + '设备运行与维修手册_V1.0.docx';
        a.click();
        URL.revokeObjectURL(a.href);
        ElementPlus.ElMessage.success('Word 文档已生成（含页眉页脚/目录/有效页/版本信息，符合甲方排版规范，可继续编辑）');
      });
    }
    function exportPdf() { window.print(); }

    return {
      tab, msg, templates, selTpl, tplRows, startWizard, newTpl, deriveTpl, compareTpl,
      stage, genTplId, genDev, formats, batch, batchDevices, assemble, assembleSteps,
      manual, meta, emptySlots, editMode, dirty, moveItem, editItem, writeBack,
      exportWord, exportPdf, goDatabase, dirtyRefs, reviewDirty,
      reviewVisible, reviewer, reviewComment, submitReview, sendReview,
      batchJobs, batchDone, batchFailed, batchRunning, batchStatusType, newBatchJob, runBatch,
      typeColor: window.NP.contentTypeColor, can: window.NP.can,
    };
  },
};
