/* P2 内容解析: 文档导入 / 解析任务 / AI审核对照 */
window.PAGES = window.PAGES || {};
window.PAGES.parse = {
  template: `
  <div>
    <el-tabs v-model="tab" type="border-card">
      <!-- ========== Tab1 文档导入与预处理（多级目录 + 多维搜索 + 状态分组 + 子步骤流水线） ========== -->
      <el-tab-pane label="文档导入与预处理" name="import">
        <el-row :gutter="14">
          <!-- 左：多级文档目录树（拖拽/增删改） -->
          <el-col :span="6">
            <div class="panel" style="min-height:560px;">
              <div class="panel-title">
                <span>文档目录</span>
                <el-button size="small" type="primary" icon="FolderAdd" circle :disabled="!can('edit')" title="新建根级文件夹" @click="treeAddRoot" />
              </div>
              <el-input v-model="treeFilter" size="small" placeholder="搜索目录…" prefix-icon="Search" clearable style="margin-bottom:8px" />
              <el-tree ref="docTreeEl" :data="docTree" node-key="id" :props="{label:'label'}" default-expand-all highlight-current
                       :expand-on-click-node="false" draggable :allow-drop="allowTreeDrop" :filter-node-method="filterTreeNode"
                       @node-click="onTreeNode" @node-drop="onTreeDrop">
                <template #default="{node, data}">
                  <span class="imp-tree-node">
                    <el-icon v-if="data.isDoc" :size="13" color="#7a8699"><Document /></el-icon>
                    <el-icon v-else :size="14" color="#1B4F9C"><Folder /></el-icon>
                    <span class="itn-label" :title="data.label">{{ data.label }}</span>
                    <span v-if="!data.isDoc" class="itn-cnt">{{ treeCount(data) }}</span>
                    <span class="itn-ops">
                      <el-button v-if="!data.isDoc" size="small" text icon="Plus" :disabled="!can('edit')" title="新建子文件夹" @click.stop="treeAddChild(data)" />
                      <el-button size="small" text icon="EditPen" :disabled="!can('edit')" title="重命名" @click.stop="treeRename(data)" />
                      <el-button size="small" text type="danger" icon="Delete" :disabled="!can('edit')" title="删除" @click.stop="treeRemove(data)" />
                    </span>
                  </span>
                </template>
              </el-tree>
              <div class="sub-text" style="margin-top:10px">多级目录：项目→区域→设备→文档；支持拖拽移动、右侧悬浮按钮新建/重命名/删除（演示级，刷新复位）。</div>
            </div>
          </el-col>

          <!-- 右：搜索 + 状态分组 + 监控 + 批量 + 文档表 -->
          <el-col :span="18">
            <!-- 多维搜索 -->
            <div class="panel" style="margin-bottom:10px;">
              <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                <el-input v-model="q.kw" size="small" placeholder="文档名称关键词…" prefix-icon="Search" clearable style="width:190px" />
                <el-select v-model="q.equipment" size="small" placeholder="设备" clearable style="width:120px">
                  <el-option v-for="e in equipOptions" :key="e" :label="e" :value="e" />
                </el-select>
                <el-select v-model="q.mfr" size="small" placeholder="厂家" clearable style="width:130px">
                  <el-option v-for="m in mfrOptions" :key="m" :label="m" :value="m" />
                </el-select>
                <el-select v-model="q.type" size="small" placeholder="类型" clearable style="width:120px">
                  <el-option v-for="t in typeOptions" :key="t" :label="t" :value="t" />
                </el-select>
                <el-button size="small" plain icon="RefreshLeft" @click="resetQuery">重置</el-button>
                <span class="sub-text" style="margin-left:auto">当前目录：<b style="color:var(--np-primary)">{{ currentFolder }}</b> · 命中 {{ filteredDocs.length }} / {{ docs.length }}</span>
              </div>
            </div>

            <!-- 状态分组 chip（点击筛选） -->
            <div class="panel imp-status-bar" style="margin-bottom:10px;">
              <span v-for="s in statusChips" :key="s.key" class="imp-chip" :class="[s.cls, { active: statusFilter === s.key }]" @click="toggleStatus(s.key)">
                <span class="dot"></span>{{ s.key }}<span class="cnt">{{ s.count }}</span>
              </span>
              <span v-if="statusFilter" class="sub-text" style="margin-left:8px; cursor:pointer; color:var(--np-primary)" @click="statusFilter=null">清除状态筛选</span>
            </div>

            <!-- 批量处理监控 -->
            <div class="batch-monitor" style="margin-bottom:10px;">
              <div class="bm-head">
                <span class="bm-title"><span class="bm-bar"></span>批量处理监控</span>
                <span class="bm-sub">太平岭一期存量文件 · {{ batch.total }} 份</span>
                <span class="bm-live"><span class="live-dot"></span>实时</span>
              </div>
              <div class="bm-stats">
                <div class="bm-stat"><div class="bms-num">{{ batch.parsed }}</div><div class="bms-lbl">已解析</div></div>
                <div class="bm-stat warn"><div class="bms-num">{{ batch.queue }}</div><div class="bms-lbl">队列等待</div></div>
                <div class="bm-stat ok"><div class="bms-num">{{ batch.successRate }}</div><div class="bms-lbl">成功率</div></div>
                <div class="bm-stat danger"><div class="bms-num">{{ batch.failed }}</div><div class="bms-lbl">失败/重试</div></div>
                <div class="bm-stat"><div class="bms-num">{{ batch.ocr }}</div><div class="bms-lbl">OCR 处理中</div></div>
                <div class="bm-stat"><div class="bms-num">{{ batch.concurrency }} 路</div><div class="bms-lbl">并发通道</div></div>
              </div>
              <div class="bm-progress">
                <div class="bmp-label">整体进度 <b>{{ batch.progress }}%</b> · 吞吐 {{ batch.throughput }} 文件/秒 · 预计完成 {{ batch.eta }}</div>
                <div class="bmp-bar"><div class="bmp-fill" :style="'width:' + batch.progress + '%'"></div></div>
              </div>
              <div class="sub-text" style="margin-top:8px">单份失败不影响批量（§72）；断点续传；失败任务自动进入重试队列，3 次失败转人工。</div>
            </div>

            <!-- 批量操作 -->
            <div class="panel" style="margin-bottom:10px;">
              <div class="batch-bar">
                <span class="sub-text">共 {{ filteredDocs.length }} 份 · 已选 {{ selectedCount }}</span>
                <span style="margin-left:auto; display:flex; gap:6px; flex-wrap:wrap;">
                  <el-button size="small" type="primary" icon="Upload" :disabled="!can('edit')" @click="startImport">批量导入</el-button>
                  <el-button size="small" type="warning" plain :disabled="!can('edit') || !failedCount" @click="batchRetryFailed">批量重试失败 ({{ failedCount }})</el-button>
                  <el-button size="small" plain :disabled="!can('edit') || !selectedCount" @click="batchReparse">批量重解析</el-button>
                  <el-button size="small" plain :disabled="!can('edit') || !runningCount" @click="stopAll">停止全部</el-button>
                  <el-button size="small" type="danger" plain :disabled="!can('edit') || !selectedCount" @click="batchDelete">批量删除</el-button>
                </span>
              </div>
            </div>

            <!-- 文档表（行内流水线 + 展开详情） -->
            <el-table :data="filteredDocs" border size="small" row-key="id" @selection-change="onSelection">
              <el-table-column type="selection" width="38" :selectable="() => can('edit')" />
              <el-table-column type="expand">
                <template #default="{row}">
                  <div class="imp-expand">
                    <div v-for="st in row.steps" :key="st.key" class="imp-step-row">
                      <span class="isr-label"><span class="imp-dot" :class="st.status">{{ stepIcon(st.status) }}</span>{{ st.label }}</span>
                      <el-tag size="small" :type="stepTagType(st.status)">{{ stepStatusText(st.status) }}</el-tag>
                      <el-progress :percentage="st.progress" :status="st.status==='failed'?'exception':(st.status==='done'?'success':'')" :stroke-width="8" />
                      <span class="isr-dur">{{ st.duration }}</span>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="name" label="文档名称" min-width="230">
                <template #default="{row}">
                  <el-icon style="vertical-align:-2px; margin-right:4px;" :color="row.type.includes('PDF') ? '#c0392b' : (row.type==='Excel' ? '#1e7b44' : '#1B4F9C')"><Document /></el-icon>
                  <span :title="row.name">{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="equipment" label="设备" width="110" show-overflow-tooltip />
              <el-table-column prop="manufacturer" label="厂家" width="120" show-overflow-tooltip />
              <el-table-column prop="type" label="类型" width="90" />
              <el-table-column label="解析流水线" width="230">
                <template #default="{row}">
                  <div class="imp-pipe">
                    <template v-for="(st, i) in row.steps" :key="st.key">
                      <span v-if="i>0" class="imp-link" :class="{done: row.steps[i-1].status==='done'}"></span>
                      <span class="imp-node" :title="st.label + ' · ' + stepStatusText(st.status) + (st.status==='running' ? ' ' + st.progress + '%' : (st.duration!=='—' ? ' · ' + st.duration : ''))">
                        <span class="imp-dot" :class="st.status">{{ stepIcon(st.status) }}</span>
                        <span class="imp-nlabel">{{ st.short }}</span>
                      </span>
                    </template>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="110">
                <template #default="{row}">
                  <el-tag size="small" :type="statusType(row.status)">
                    <el-icon v-if="row.status==='进行中'" class="is-loading" style="vertical-align:-1px"><Loading /></el-icon>
                    {{ row.status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" align="center">
                <template #default="{row}">
                  <template v-if="row.status==='进行中'">
                    <el-button size="small" text type="warning" :disabled="!can('edit')" @click="stopRow(row)">停止</el-button>
                  </template>
                  <template v-else-if="row.status==='失败' || row.status==='停止'">
                    <el-button size="small" text type="primary" :disabled="!can('edit')" @click="retry(row)">重试</el-button>
                  </template>
                  <template v-else-if="row.status==='完成'">
                    <el-button size="small" text type="primary" @click="tab='review'">查看解析</el-button>
                  </template>
                  <el-button size="small" text type="danger" :disabled="!can('edit')" @click="deleteRow(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="sub-text" style="margin-top:8px">
              点击文档行展开查看 5 个解析子步骤（OCR/结构化/Embedding/实体关系/LLM抽取）的状态、进度与处理耗时；扫描件走 OCR，Word/Excel 直接结构化。
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ========== Tab2 解析详情 + AI审核 ========== -->
      <el-tab-pane label="解析结果与 AI 审核" name="review">
        <!-- 顶部工具条：文档+章节选择 + 准确率 mini 统计 + 待审核筛选 -->
        <div class="rv-toolbar">
          <div class="rv-nav">
            <span class="rv-label">文档</span>
            <el-cascader v-model="folderPath" :options="folderOnlyTree" :props="{ expandTrigger: 'hover', emitPath: false, checkStrictly: true }"
                         placeholder="项目 → 设备" clearable @change="onFolderChange" style="width:220px">
              <template #default="{data}"><span>{{ data.label }}<span v-if="data.count!=null" class="fb-cnt">{{ data.count }}</span></span></template>
            </el-cascader>
            <span class="sub-text" style="margin-left:auto">{{ currentDoc ? currentDoc.name : '— 未选文档 —' }}</span>
          </div>
          <div class="rv-stats">
            <span class="rv-stat acc" :style="'color:' + (accuracy >= 95 ? 'var(--np-success)' : 'var(--np-warn)')"><b>{{ accuracy }}%</b> 准确率<span class="rv-mini"> ≥95%</span></span>
            <span class="rv-stat">提取 <b>{{ blocks.length }}</b></span>
            <span class="rv-stat ok">确认 <b>{{ confirmed }}</b></span>
            <span class="rv-stat warn">修正 <b>{{ corrected }}</b></span>
            <span class="rv-stat danger">待审 <b>{{ pending }}</b></span>
            <el-checkbox v-model="onlyPending" size="small">只看待审核</el-checkbox>
          </div>
        </div>

        <!-- 三栏：章节树 / 原文 / AI 提取 -->
        <div class="rv-cols">
          <!-- 左：章节树 -->
          <div class="panel rv-tree">
            <div class="panel-title">章节</div>
            <el-tree :data="tocTree" node-key="label" :props="{label: 'label'}" default-expand-all
                     highlight-current @node-click="onNode" :expand-on-click-node="false">
              <template #default="{data}"><span style="font-size:12px;">{{ data.label }}</span></template>
            </el-tree>
          </div>

          <!-- 中：原文 -->
          <div class="panel rv-col">
            <div class="panel-title">
              <span>原文视图 · {{ currentNode ? currentNode.label : '—' }}</span>
              <el-button size="small" text icon="List" @click="elemDrawer = true">元素清单 ({{ elements.length }})</el-button>
            </div>
            <div class="rv-orig" ref="origEl">
              <div v-if="currentBlocks.length" class="doc-page">
                <div class="dp-chap-no">{{ currentNode ? currentNode.num : '' }}</div>
                <h2 class="dp-h">{{ currentNode ? currentNode.title : '' }}</h2>
                <template v-for="b in currentBlocks" :key="b.id">
                  <div v-if="b.safetyLevel" class="safety-box" :class="['safety-' + b.safetyLevel, { hl: highlightId === b.id }]" :data-id="b.id">
                    <span class="s-tag">【{{ b.safetyLevel }}】</span>{{ b.content.replace(/^注意[:：!！]?|^警告[:：!！]?|^危险[:：!！]?/, '') }}
                  </div>
                  <p v-else class="dp-p" :class="{ hl: highlightId === b.id }" :data-id="b.id">{{ b.content }}</p>
                </template>
                <table v-if="currentOriginalTable" class="dp-table">
                  <thead><tr><th v-for="(h, i) in currentOriginalTable.header" :key="i">{{ h }}</th></tr></thead>
                  <tbody><tr v-for="(r, ri) in currentOriginalTable.rows" :key="ri"><td v-for="(c, ci) in r" :key="ci">{{ c }}</td></tr></tbody>
                </table>
                <div class="dp-footer">— 本章节原文结束 · 共 {{ currentBlocks.length }} 个内容块 —</div>
              </div>
              <el-empty v-else description="选择文档与章节查看原文（演示仅对 0.4 / 1.2 / 2.3 / 3.7 章节做全量内容块展示）" :image-size="70" />
            </div>
          </div>

          <!-- 右：AI 提取结果 -->
          <div class="panel rv-col">
            <div class="panel-title">
              <span>AI 提取结果 <span class="ai-badge">LLM</span></span>
              <el-radio-group v-model="resultTab" size="small">
                <el-radio-button value="blocks">内容块</el-radio-button>
                <el-radio-button value="params">参数</el-radio-button>
                <el-radio-button value="tables">表格</el-radio-button>
              </el-radio-group>
            </div>
            <div class="rv-extract">
              <!-- 内容块：点击定位原文 -->
              <div v-if="resultTab === 'blocks'">
                <div v-for="b in shownBlocks" :key="b.id"
                     class="extract-card" :class="'ext-' + b.reviewStatus" @click="locateBlock(b)">
                  <div class="ext-bar" :style="'width:' + Math.round(b.aiConfidence * 100) + '%'" :title="'置信度 ' + b.aiConfidence"></div>
                  <div class="ext-tags">
                    <el-tag size="small" effect="plain" class="mono">{{ b.id }}</el-tag>
                    <el-tag size="small" :type="typeColor(b.contentType)">{{ b.contentType }}</el-tag>
                    <el-tag v-if="b.safetyLevel" size="small" type="danger" effect="plain">{{ b.safetyLevel }}</el-tag>
                    <el-tag v-if="b.isCommon" size="small" type="success" effect="plain">通用</el-tag>
                    <el-tag v-else size="small" type="info" effect="plain">专用</el-tag>
                    <span class="conf-pill" :class="confType(b.aiConfidence)">置信度 {{ b.aiConfidence }}</span>
                    <span style="margin-left:auto"></span>
                    <template v-if="b.reviewStatus === '待审核'">
                      <el-button size="small" type="success" :disabled="!can('approve')" @click.stop="confirm(b)">确认</el-button>
                      <el-button size="small" type="warning" plain :disabled="!can('edit')" @click.stop="openFix(b)">修正</el-button>
                    </template>
                    <el-tag v-else :type="b.reviewStatus === '已确认' ? 'success' : 'warning'" size="small" effect="dark">{{ b.reviewStatus }}</el-tag>
                  </div>
                  <div class="ext-content">{{ b.content }}</div>
                  <div class="dmc ext-dmc">DMC: {{ b.dmc }} · <el-button size="small" text type="primary" @click.stop="locateBlock(b)">定位原文</el-button></div>
                </div>
                <el-empty v-if="!shownBlocks.length" description="当前章节无内容块（或待审核已筛完）" :image-size="70" />
              </div>

              <!-- 参数 -->
              <div v-if="resultTab === 'params'">
                <el-alert type="success" :closable="false" show-icon style="margin-bottom:10px">
                  <template #title>
                    复合参数拆分示例：<span class="mono">{{ compound.sentence }}</span>
                    <div style="margin-top:4px">
                      → 拆分为 <b>{{ compound.results.length }} 条</b>独立参数记录：
                      <el-tag v-for="r in compound.results" :key="r.name" size="small" style="margin-right:6px">{{ r.name }} {{ r.value }}{{ r.unit }}</el-tag>
                    </div>
                  </template>
                </el-alert>
                <el-table :data="params" border size="small" max-height="430">
                  <el-table-column prop="name" label="参数名称" width="110" />
                  <el-table-column prop="value" label="数值" width="80" align="right" />
                  <el-table-column prop="unit" label="单位" width="70" />
                  <el-table-column prop="category" label="分类" width="90" />
                  <el-table-column prop="component" label="所属部件" width="90" />
                  <el-table-column label="适用条件" width="100">
                    <template #default="{row}"><span class="sub-text">{{ row.condition || '—' }}</span></template>
                  </el-table-column>
                  <el-table-column label="置信度" width="80" align="center">
                    <template #default="{row}">
                      <el-tag size="small" :type="confType(row.aiConfidence)">{{ row.aiConfidence }}</el-tag>
                    </template>
                  </el-table-column>
                </el-table>
              </div>

              <!-- 表格 -->
              <div v-if="resultTab === 'tables'">
                <el-select v-model="tableKey" size="small" style="width:100%; margin-bottom:10px;">
                  <el-option v-for="t in tableOptions" :key="t.key" :label="t.label" :value="t.key" />
                </el-select>
                <template v-if="currentTable">
                  <div class="sub-text" style="margin-bottom:6px">所属章节: {{ currentTable.chapterPath || '—' }} · 已保留与章节上下文关联</div>
                  <el-table :data="currentTable.rows" border size="small" max-height="430">
                    <el-table-column v-for="(h, i) in currentTable.header" :key="i" :label="h" :prop="'c' + i" min-width="90" show-overflow-tooltip />
                  </el-table>
                </template>
                <el-empty v-else description="该类型表格未在演示数据中解析" :image-size="70" />
                <div class="sub-text" style="margin-top:8px">已支持合并单元格/跨行跨列解析；仅解析规则梳理阶段纳入清单的表格类型（需求导向原则）。</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 元素清单抽屉（§70） -->
        <el-drawer v-model="elemDrawer" title="解析元素清单（§70）" size="420px">
          <div class="elem-stats">
            <span class="es-item p">段落 {{ cnt.段落 }}</span>
            <span class="es-item t">表格 {{ cnt.表格 }}</span>
            <span class="es-item i">图片 {{ cnt.图片 }}</span>
            <span class="es-item w">警示框 {{ cnt.警示框 }}</span>
          </div>
          <el-table :data="elements" border size="small" style="margin-top:8px;">
            <el-table-column label="类型" width="80"><template #default="{row}"><el-tag size="small" :type="elemTag(row.type)">{{ row.type }}</el-tag></template></el-table-column>
            <el-table-column prop="page" label="页码" width="70" align="center"><template #default="{row}">第 {{ row.page }} 页</template></el-table-column>
            <el-table-column prop="pos" label="位置" width="120"><template #default="{row}"><span class="mono">{{ row.pos }}</span></template></el-table-column>
            <el-table-column prop="label" label="元素说明" min-width="180" show-overflow-tooltip />
          </el-table>
          <div v-if="images.length" class="elem-images">
            <div v-for="(img, i) in images" :key="i" class="elem-img-card">
              <div class="ei-placeholder"><el-icon :size="28" color="#aab4c4"><Picture /></el-icon></div>
              <div class="ei-label">{{ img.label }}</div>
              <div class="sub-text">第 {{ img.page }} 页</div>
            </div>
          </div>
        </el-drawer>
      </el-tab-pane>

      <!-- ========== Tab4 增量重解析 ========== -->
      <el-tab-pane label="增量重解析" name="reparse">
        <el-alert type="success" :closable="false" show-icon style="margin-bottom:14px"
          title="规则草案 V0.9 已评审通过并生效，触发增量重解析（仅重解析受规则变更影响的内容，避免全量重算）" />
        <div class="panel">
          <div class="panel-title"><span>规则变更影响范围</span><span class="pt-badge">{{ reparseAffectedBlocks }} 块受影响</span></div>
          <el-table :data="reparseRules" border size="small">
            <el-table-column prop="ruleType" label="规则类型" width="130" />
            <el-table-column prop="change" label="规则变更说明" min-width="260" />
            <el-table-column prop="files" label="受影响文件" width="110" align="center" />
            <el-table-column prop="blocks" label="受影响内容块" width="120" align="center" />
            <el-table-column label="优先级" width="90" align="center">
              <template #default="{row}"><el-tag size="small" :type="{高:'danger',中:'warning',低:'info'}[row.priority]">{{ row.priority }}</el-tag></template>
            </el-table-column>
            <el-table-column label="状态" width="100" align="center">
              <template #default="{row}"><el-tag size="small" :type="row.status === '已完成' ? 'success' : row.status === '重解析中' ? 'primary' : 'info'">{{ row.status }}</el-tag></template>
            </el-table-column>
          </el-table>
        </div>
        <div class="panel">
          <div class="panel-title"><span>重解析队列</span><span class="sub-text">已重解析 {{ reparseDone }}/{{ reparseTotal }} · 并发 8 路</span></div>
          <div class="bm-progress" style="margin-bottom:8px">
            <div class="bmp-label">整体进度 <b>{{ reparsePct }}%</b> · 成功 {{ reparseDone }} · 失败重试 0 · 队列 {{ reparseQueue }}</div>
            <div class="bmp-bar"><div class="bmp-fill" :style="'width:' + reparsePct + '%'"></div></div>
          </div>
          <div class="sub-text">增量策略：按规则变更定位受影响内容块（通过关联表反查），仅重解析命中块并重新校验关联完整性；不影响的内容块版本不变。</div>
        </div>
        <div class="panel">
          <div class="panel-title"><span>重解析差异（示例 · CB-0033 螺栓力矩）</span><span class="ai-badge">规则更新前 → 后</span></div>
          <el-row :gutter="14">
            <el-col :span="12">
              <div class="sub-text" style="margin-bottom:6px">重解析前（V2）</div>
              <div class="original-view">
                <span v-for="(d, i) in reparseDiff" :key="'o'+i" class="diff-line" :class="d.t === 'del' ? 'diff-del' : 'diff-same'">{{ d.text }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="sub-text" style="margin-bottom:6px">重解析后（V3）</div>
              <div class="original-view">
                <span v-for="(d, i) in reparseDiff" :key="'n'+i" class="diff-line" :class="d.t === 'add' ? 'diff-add' : 'diff-same'">{{ d.text }}</span>
              </div>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

      <!-- ========== 扫描件 OCR 校对（三栏：目录 / 仿真页框选 / 条目卡片） ========== -->
      <el-tab-pane name="ocr">
        <template #label>扫描件 OCR 校对 <el-badge v-if="ocrPending" :value="ocrPending" type="warning" style="margin-left:4px" /></template>

        <!-- 顶栏：文档 + 统计 + 操作 -->
        <div class="panel ocr-toolbar">
          <span class="ot-name">{{ ocrDoc.name }}</span>
          <span class="ot-stats">
            <span>识别 <b>{{ ocrTotal }}</b></span>
            <span style="color:var(--np-success)">已处理 <b>{{ ocrDone }}</b></span>
            <span style="color:var(--np-warn)">待校对 <b>{{ ocrPending }}</b></span>
            <span :style="'color:' + (ocrAcc >= 95 ? 'var(--np-success)' : 'var(--np-warn)')">准确率 <b>{{ ocrAcc }}%</b><small> ≥95%</small></span>
          </span>
          <span style="margin-left:auto; display:flex; gap:6px;">
            <el-button size="small" icon="DocumentChecked" :disabled="!can('edit')" @click="msg('保存校对进度')">保存</el-button>
            <el-button size="small" type="primary" icon="Download" :disabled="!can('export')" @click="msg('导出校对结果')">导出</el-button>
          </span>
        </div>

        <div class="ocr-layout">
          <!-- 左：目录树（点章节跳扫描页） -->
          <div class="panel ocr-toc">
            <div class="panel-title"><span>目录</span><span class="pt-badge">{{ ocrPages.length }} 页扫描件</span></div>
            <el-tree :data="tocTree" :props="{label:'label'}" default-expand-all highlight-current
                     :expand-on-click-node="false" @node-click="onOcrTocNode">
              <template #default="{data}"><span style="font-size:12px;">{{ data.label }}</span></template>
            </el-tree>
          </div>

          <!-- 中：仿真扫描页 + 状态框选 -->
          <div class="panel ocr-stage-wrap">
            <div class="panel-title">
              <span>扫描页预览 · 第 {{ ocrPageData.page }} 页</span>
              <span class="pt-badge">{{ ocrDoc.dpi }} DPI · 框选按状态着色</span>
            </div>
            <div class="ocr-stage" ref="ocrStageEl">
              <div class="ocr-paper" :style="ocrPaperStyle">
                <div class="op-head"><span>{{ ocrDoc.name }}</span><span>- {{ ocrPageData.page }} -</span></div>
                <template v-for="it in ocrPageData.items" :key="'d'+it.loc">
                  <div v-if="it.type==='表格'" class="ocr-tbl" :style="ocrBoxStyle(it)">
                    <table><tr v-for="(r, ri) in it.rows" :key="ri"><td v-for="(c, ci) in r" :key="ci">{{ c }}</td></tr></table>
                  </div>
                  <div v-else-if="it.type==='图片'" class="ocr-imgbox" :style="ocrBoxStyle(it)">
                    <img v-if="it.img" :src="it.img" alt="" />
                    <template v-else><el-icon :size="22" color="#9aa8a6"><Picture /></el-icon><span>图片</span></template>
                  </div>
                  <div v-else class="ocr-txt" :class="{strong: it.type==='标题'}" :style="ocrBoxStyle(it)">{{ it.orig }}</div>
                </template>
                <div v-for="it in ocrPageData.items" :key="it.loc" class="ocr-box" :data-oid="it.loc"
                     :class="[ocrStatusCls(it.status), { sel: ocrSelId === it.loc }]"
                     :style="ocrBoxStyle(it)" :title="it.loc + ' · ' + it.type + ' · 置信度 ' + (it.conf*100).toFixed(0) + '%'"
                     @click="onOcrBoxClick(it)">
                  <span class="ob-label">{{ it.type }} {{ (it.conf*100).toFixed(0) }}%</span>
                </div>
              </div>
            </div>
            <div class="ocr-ctrls">
              <el-button size="small" circle icon="Minus" title="缩小" @click="ocrZoomBy(-0.15)" />
              <span class="oc-page" style="cursor:pointer" title="重置为 100%" @click="ocrZoom = 1">{{ Math.round(ocrZoom*100) }}%</span>
              <el-button size="small" circle icon="Plus" title="放大" @click="ocrZoomBy(0.15)" />
              <span style="width:16px"></span>
              <el-button size="small" circle icon="ArrowLeft" title="上一页" :disabled="ocrPage<=1" @click="ocrGoto(ocrPage-1)" />
              <span class="oc-page">{{ ocrPage }} / {{ ocrPages.length }}</span>
              <el-button size="small" circle icon="ArrowRight" title="下一页" :disabled="ocrPage>=ocrPages.length" @click="ocrGoto(ocrPage+1)" />
            </div>
          </div>

          <!-- 右：条目卡片流（chips 筛选 + 内联修正） -->
          <div class="panel ocr-side">
            <div class="panel-title"><span>识别条目</span>
              <span style="display:flex; align-items:center; gap:8px;">
                <span class="sub-text">点击卡片 / 框选双向定位</span>
                <el-button size="small" type="success" plain :disabled="!can('approve') || !ocrPending" @click="ocrConfirmAll">一键确认 ({{ ocrPending }})</el-button>
              </span>
            </div>
            <div class="ocr-chips">
              <button v-for="c in ['全部','标题','正文','图片','表格']" :key="c" class="ocr-chip"
                      :class="{active: ocrFilter===c}" @click="ocrFilter=c">{{ c }}<span class="cnt">{{ ocrCounts[c] }}</span></button>
            </div>
            <div class="ocr-cards" ref="ocrCardsEl">
              <div v-for="w in ocrShownItems" :key="w.it.loc" class="ocr-card" :data-oid="w.it.loc"
                   :class="[ocrStatusCls(w.it.status), { sel: ocrSelId === w.it.loc }]" @click="selectOcr(w)">
                <div class="oc-head">
                  <el-tag size="small" effect="plain" class="mono">{{ w.it.loc }}</el-tag>
                  <el-tag size="small" :type="ocrTypeTag(w.it.type)" effect="plain">{{ w.it.type }}</el-tag>
                  <span class="conf-pill" :class="confType(w.it.conf)">{{ (w.it.conf*100).toFixed(0) }}%</span>
                  <el-tag size="small" :type="w.it.status==='已确认'?'success':(w.it.status==='已修正'?'primary':'warning')">{{ w.it.status }}</el-tag>
                </div>
                <div v-if="ocrEditId !== w.it.loc" class="oc-text">{{ w.it.text }}</div>
                <el-input v-else v-model="ocrEditText" type="textarea" :rows="2" @click.stop />
                <div class="oc-foot">
                  <template v-if="ocrEditId === w.it.loc">
                    <el-button size="small" type="primary" @click.stop="ocrSaveEdit(w.it)">保存修正</el-button>
                    <el-button size="small" @click.stop="ocrCancelEdit">取消</el-button>
                  </template>
                  <template v-else-if="w.it.status === '待校对'">
                    <el-button size="small" type="success" :disabled="!can('approve')" @click.stop="ocrConfirm(w.it)">确认</el-button>
                    <el-button size="small" type="warning" plain :disabled="!can('edit')" @click.stop="ocrStartEdit(w.it)">修正</el-button>
                  </template>
                  <el-tag v-else size="small" effect="dark" :type="w.it.status==='已确认'?'success':'primary'">已处理</el-tag>
                  <span class="oc-meta">第 {{ ocrPages[w.pageIdx].page }} 页</span>
                </div>
              </div>
              <el-empty v-if="!ocrShownItems.length" description="当前筛选无条目" :image-size="70" />
            </div>
          </div>
        </div>
        <el-alert type="info" :closable="false" show-icon style="margin-top:10px"
          title="修正差异将记录于「AI 结果与人工修正差异库」，用于 OCR 模型微调与准确率统计；原文图像与识别文本、修正文本一一映射，可追溯。" />
      </el-tab-pane>

      <!-- ========== 专用表格清单解析 ========== -->
      <el-tab-pane name="tables">
        <template #label>专用表格解析</template>
        <div class="sub-text" style="margin-bottom:10px">规则梳理与建模阶段会同甲方业务部门确定需结构化解析的表格类型与解析粒度；仅纳入清单范围内的表格类型进行结构化解析（需求§表格解析 a-d）。</div>
        <el-tabs v-model="tableKind" type="card">
          <el-tab-pane v-for="t in tableTypes" :key="t.key" :name="t.key" :label="t.name + '（' + t.parsed + '）'">
            <el-row :gutter="14">
              <el-col :span="9">
                <div class="panel">
                  <div class="panel-title"><span>{{ t.name }}</span><span class="pt-badge">{{ t.parsed }} 项</span></div>
                  <div class="sub-text" style="margin-bottom:6px">典型列结构</div>
                  <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px">
                    <el-tag v-for="c in t.cols" :key="c" size="small" effect="plain">{{ c }}</el-tag>
                  </div>
                  <div class="sub-text" style="margin-bottom:4px">解析规则</div>
                  <div style="font-size:12.5px; color:var(--np-text); line-height:1.8">{{ t.rule }}</div>
                  <div class="sub-text" style="margin-top:8px">来源章节：{{ t.chapter }} · 合并单元格/跨行跨列：{{ t.merge }}</div>
                </div>
              </el-col>
              <el-col :span="15">
                <div class="panel">
                  <div class="panel-title"><span>解析结果（{{ t.name }}）</span>
                    <span class="sub-text">关联设备：{{ t.equip }} · 关联至 PBS 对象与部件</span>
                  </div>
                  <el-table :data="t.rows" border size="small">
                    <el-table-column v-for="(c, i) in t.cols" :key="i" :prop="'c'+i" :label="c" :min-width="t.widths[i]" show-overflow-tooltip>
                      <template #default="{row}">{{ row['c'+i] }}</template>
                    </el-table-column>
                  </el-table>
                  <div class="sub-text" style="margin-top:8px">解析结果保留与章节上下文关联（该表属于 {{ t.chapter }} · 描述 {{ t.equip }}）；结构化记录入库为信息块，支持后续手册生成引用。</div>
                </div>
              </el-col>
            </el-row>
          </el-tab-pane>
        </el-tabs>
      </el-tab-pane>
    </el-tabs>

    <!-- 修正对话框 -->
    <el-dialog v-model="fixVisible" :title="'人工修正 · ' + (fixBlock ? fixBlock.id : '')" width="620px">
      <div class="sub-text" style="margin-bottom:6px">AI 提取原文：</div>
      <div class="original-view" style="margin-bottom:10px; max-height:120px; overflow:auto;">{{ fixBlock ? fixBlock.content : '' }}</div>
      <el-input v-model="fixText" type="textarea" :rows="5" />
      <div style="margin-top:8px" class="sub-text">修正差异将记录用于 AI 模型优化与准确率统计。</div>
      <template #footer>
        <el-button @click="fixVisible = false">取消</el-button>
        <el-button type="primary" @click="saveFix">保存修正</el-button>
      </template>
    </el-dialog>
  </div>`,

  setup() {
    const { ref, computed, onMounted, nextTick } = Vue;
    const M = window.MOCK;
    const tab = ref('import');
    // ---- 文档数据（含 5 子步骤 steps） ----
    const docs = ref(JSON.parse(JSON.stringify(M.docs)));

    // 批量处理监控（太平岭一期 30万+ 文件规模）
    const batch = {
      total: '305,842', parsed: '89,216', queue: '1,240', successRate: '99.2%',
      failed: '714', ocr: '23', concurrency: '8', throughput: '12.4',
      progress: 29, eta: '约 3 天 6 小时',
    };

    // ---- 子步骤展示辅助 ----
    const STEP_SHORT = { ocr: 'OCR', struct: '结构化', embed: 'Embed', entity: '实体', llm: 'LLM' };
    // 给每个 step 补 short（用于行内流水线小标签）
    docs.value.forEach(d => d.steps && d.steps.forEach(s => { s.short = STEP_SHORT[s.key] || s.key; }));
    function stepIcon(status) { return { done: '✓', running: '◐', failed: '✗', stopped: '‖', queued: '', pending: '' }[status] || ''; }
    function stepStatusText(status) { return { done: '完成', running: '进行中', queued: '排队', failed: '失败', pending: '未开始', stopped: '已停止' }[status] || status; }
    function stepTagType(status) { return { done: 'success', running: 'primary', failed: 'danger', stopped: 'warning', queued: 'info', pending: 'info' }[status] || 'info'; }

    // ---- 文档整体状态派生（导入动画后重算） ----
    function docStatus(steps) {
      if (steps.some(s => s.status === 'failed')) return '失败';
      if (steps.some(s => s.status === 'running')) return '进行中';
      if (steps.every(s => s.status === 'done')) return '完成';
      if (steps.some(s => s.status === 'stopped')) return '停止';
      return '排队';
    }

    // ---- 导入模拟（推进第一个未完成步骤） ----
    function startImport() {
      const target = docs.value.find(d => d.status === '排队');
      if (!target) { ElementPlus.ElMessage.info('当前无排队中的文档'); return; }
      const step = target.steps.find(s => s.status !== 'done');
      if (!step) return;
      step.status = 'running';
      target.status = '进行中';
      const timer = setInterval(() => {
        step.progress = Math.min(100, step.progress + 12);
        target.progress = Math.min(100, target.progress + 6);
        if (step.progress >= 100) {
          step.status = 'done'; step.duration = (5 + Math.round(step.progress / 12)) + '.0s';
          clearInterval(timer);
          const next = target.steps.find(s => s.status === 'queued' || s.status === 'pending');
          if (next) { next.status = 'queued'; }
          target.status = docStatus(target.steps);
          if (target.status === '完成') target.progress = 100;
          ElementPlus.ElMessage.success(target.name + ' 推进一步：' + step.label + ' 完成');
        }
      }, 400);
    }
    function retry(row) {
      const step = row.steps.find(s => s.status === 'failed' || s.status === 'stopped' || s.status === 'pending');
      if (!step) { ElementPlus.ElMessage.info('无可重试步骤'); return; }
      step.status = 'running'; step.progress = Math.max(10, step.progress);
      row.status = '进行中';
      const timer = setInterval(() => {
        step.progress = Math.min(100, step.progress + 14);
        if (step.progress >= 100) {
          step.status = 'done'; step.duration = '6.0s';
          clearInterval(timer);
          row.status = docStatus(row.steps);
          ElementPlus.ElMessage.success(row.name + ' 已从断点恢复：' + step.label);
        }
      }, 350);
    }

    // ---- 目录树（消费共享 NP.store.docTree，可编辑） ----
    const docTree = window.NP.store.docTree;
    const currentFolder = ref('全部');
    const folderDocIds = ref(null);   // 选中目录子树的 docId 集合（null=全部）
    function onTreeNode(data) {
      if (data.isDoc) {
        folderDocIds.value = data.docId ? [data.docId] : [];
        currentFolder.value = data.label;
      } else {
        folderDocIds.value = window.NP.treeDocIds(data);
        currentFolder.value = data.label;
      }
    }
    function treeCount(data) { return window.NP.treeDocCount(data); }

    // 目录树查询（按名过滤）
    const treeFilter = ref('');
    const docTreeEl = ref(null);
    Vue.watch(treeFilter, (v) => { if (docTreeEl.value) docTreeEl.value.filter(v); });
    function filterTreeNode(value, data) { return !value || (data.label || '').includes(value); }

    // 目录树编辑（新建/重命名/删除/拖拽）
    function treeAddRoot() {
      ElementPlus.ElMessageBox.prompt('新建根级文件夹名称', '新建文件夹', { confirmButtonText: '创建', cancelButtonText: '取消', inputValue: '新建文件夹' })
        .then(({ value }) => { window.NP.treeAddFolder(null, value || '新建文件夹'); ElementPlus.ElMessage.success('已新建'); }).catch(() => {});
    }
    function treeAddChild(data) {
      ElementPlus.ElMessageBox.prompt('在「' + data.label + '」下新建子文件夹', '新建子文件夹', { confirmButtonText: '创建', cancelButtonText: '取消', inputValue: '新建文件夹' })
        .then(({ value }) => { window.NP.treeAddFolder(data.id, value || '新建文件夹'); ElementPlus.ElMessage.success('已新建'); }).catch(() => {});
    }
    function treeRename(data) {
      ElementPlus.ElMessageBox.prompt('重命名', '重命名', { confirmButtonText: '保存', cancelButtonText: '取消', inputValue: data.label })
        .then(({ value }) => { if (value) { window.NP.treeRename(data.id, value); ElementPlus.ElMessage.success('已重命名'); } }).catch(() => {});
    }
    function treeRemove(data) {
      ElementPlus.ElMessageBox.confirm('确认删除「' + data.label + '」' + (data.isDoc ? '' : '及其下全部内容') + '？', '删除', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
        .then(() => { window.NP.treeRemove(data.id); ElementPlus.ElMessage.success('已删除'); }).catch(() => {});
    }
    // 禁止把节点拖进文档叶子内部
    function allowTreeDrop(draggingNode, dropNode, type) {
      if (dropNode.data.isDoc && type === 'inner') return false;
      return true;
    }
    function onTreeDrop() { ElementPlus.ElMessage.success('已移动目录节点'); }

    // ---- 多维搜索 ----
    const q = Vue.reactive({ kw: '', equipment: null, mfr: null, type: null });
    const equipOptions = computed(() => [...new Set(docs.value.map(d => d.equipment))]);
    const mfrOptions = computed(() => [...new Set(docs.value.map(d => d.manufacturer))]);
    const typeOptions = computed(() => [...new Set(docs.value.map(d => d.type))]);
    function resetQuery() { q.kw = ''; q.equipment = null; q.mfr = null; q.type = null; }

    // ---- 状态分组 chip ----
    const statusFilter = ref(null);
    const STATUS_META = [
      { key: '完成', cls: 'st-done' }, { key: '进行中', cls: 'st-run' }, { key: '排队', cls: 'st-queue' },
      { key: '失败', cls: 'st-fail' }, { key: '停止', cls: 'st-stop' },
    ];
    const statusChips = computed(() => STATUS_META.map(m => ({ ...m, count: docs.value.filter(d => d.status === m.key).length })));
    function toggleStatus(k) { statusFilter.value = statusFilter.value === k ? null : k; }

    // ---- 过滤（目录 ∧ 搜索 ∧ 状态） ----
    const filteredDocs = computed(() => docs.value.filter(d =>
      (!folderDocIds.value || folderDocIds.value.includes(d.id))
      && (!q.kw || d.name.includes(q.kw))
      && (!q.equipment || d.equipment === q.equipment)
      && (!q.mfr || d.manufacturer === q.mfr)
      && (!q.type || d.type === q.type)
      && (!statusFilter.value || d.status === statusFilter.value)));

    // ---- 批量统计 ----
    const selectedRows = ref([]);
    const onSelection = (s) => selectedRows.value = s;
    const selectedCount = computed(() => selectedRows.value.length);
    const runningCount = computed(() => docs.value.filter(d => d.status === '进行中').length);
    const failedCount = computed(() => docs.value.filter(d => d.status === '失败').length);
    function statusType(s) {
      return { '完成': 'success', '失败': 'danger', '停止': 'warning', '排队': 'info', '进行中': 'primary' }[s] || 'info';
    }
    function batchRetryFailed() {
      const failed = docs.value.filter(d => d.status === '失败');
      failed.forEach((d, i) => setTimeout(() => retry(d), i * 200));
      ElementPlus.ElMessage.success('已对 ' + failed.length + ' 份失败文档发起批量重试');
    }
    function batchReparse() { ElementPlus.ElMessage.success('已对 ' + selectedRows.value.length + ' 份文档加入批量重解析队列'); }
    function batchDelete() {
      const ids = new Set(selectedRows.value.map(r => r.id));
      docs.value = docs.value.filter(d => !ids.has(d.id));
      ElementPlus.ElMessage.success('已删除 ' + ids.size + ' 份文档（逻辑删除，可恢复）');
    }
    function stopAll() {
      docs.value.forEach(d => { if (d.status === '进行中') { d.steps.forEach(s => { if (s.status === 'running') s.status = 'stopped'; }); d.status = '停止'; } });
      ElementPlus.ElMessage.warning('已停止全部进行中的任务');
    }
    function stopRow(row) { row.steps.forEach(s => { if (s.status === 'running') s.status = 'stopped'; }); row.status = '停止'; ElementPlus.ElMessage.warning(row.name + ' 已停止'); }
    function deleteRow(row) { docs.value = docs.value.filter(d => d.id !== row.id); ElementPlus.ElMessage.success('已删除 ' + row.name); }
    function msg(t) { ElementPlus.ElMessage.info(t + '：演示功能入口'); }

    // ---- 审核(与内容数据库页共享同一份内容块状态) ----
    const blocks = window.NP.store.blocks;
    const confirmed = computed(() => blocks.filter(b => b.reviewStatus === '已确认').length);
    const corrected = computed(() => blocks.filter(b => b.reviewStatus === '已修正').length);
    const pending = computed(() => blocks.filter(b => b.reviewStatus === '待审核').length);
    const accuracy = computed(() => {
      const done = confirmed.value + corrected.value;
      return done ? ((confirmed.value / done) * 100).toFixed(1) : '—';
    });
    const reviewedPct = computed(() => Math.round((confirmed.value + corrected.value) / blocks.length * 100));

    // 目录轴（共享，docTree 已在导入块定义）
    // review cascader 只用文件夹层级（滤掉文档叶子）
    function stripDocs(nodes) {
      return nodes.filter(n => !n.isDoc).map(n => ({ ...n, children: n.children ? stripDocs(n.children) : undefined }));
    }
    const folderOnlyTree = computed(() => stripDocs(docTree));
    const folderPath = ref(null);
    const currentDoc = ref(null);
    function onFolderChange(val) {
      const node = val ? findTreeNode(docTree, val) : null;
      const filter = node && node.filter;
      window.NP.setFolder(filter);
      currentDoc.value = filter ? M.docs.find(d => d.equipment === filter.equipment) : null;
    }
    function findTreeNode(nodes, label) {
      for (const n of nodes) { if (n.label === label) return n; if (n.children) { const r = findTreeNode(n.children, label); if (r) return r; } }
      return null;
    }

    const tocTree = M.tocTree;
    const currentNode = ref(null);
    const resultTab = ref('blocks');
    const elemDrawer = ref(false); // 元素清单抽屉
    const highlightId = ref(null); // 原文联动高亮块
    const origEl = ref(null);
    const onlyPending = ref(false); // 只看待审核
    function onNode(data) { currentNode.value = data; }
    // 章节 cascader 选项（tocTree 映射）
    function mapTree(nodes) {
      return nodes.map(n => ({ value: n.label, label: n.label, children: n.children && n.children.length ? mapTree(n.children) : undefined }));
    }
    const chapterOptions = computed(() => mapTree(tocTree));
    const chapterPath = ref(null);
    function onChapterChange(val) {
      const node = val ? findTreeNode(tocTree, val) : null;
      currentNode.value = node || null;
      highlightId.value = null;
    }
    // 双栏对照联动：点 AI 提取条目 → 原文对应块高亮 + 滚动定位
    function locateBlock(b) {
      highlightId.value = b.id;
      nextTick(() => {
        const el = origEl.value && origEl.value.querySelector('[data-id="' + b.id + '"]');
        if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      });
    }
    const currentBlocks = computed(() => {
      if (!currentNode.value) return [];
      const num = currentNode.value.num;
      return blocks.filter(b => b.chapterPath.split('/').some(s => s.startsWith(num)));
    });
    // 当前章节对应的原始表格（原文视图内嵌渲染，使原文与真实 Word 一致）
    const currentOriginalTable = computed(() => {
      if (!currentNode.value) return null;
      const num = currentNode.value.num;
      const map = { '2.3': 'faultTable', '3.7': 'spareTable', '1.5': 'torqueTable', '0.6': 'deviceCodeTable' };
      const key = map[num] || map[Object.keys(map).find(k => num.startsWith(k))];
      const t = key && (M.tables[key] || EXTRA_TABLES[key]);
      if (!t) return null;
      return t;
    });
    // 待审核筛选：只看待审核时仅显示 reviewStatus==='待审核' 的块
    const shownBlocks = computed(() => onlyPending.value ? currentBlocks.value.filter(b => b.reviewStatus === '待审核') : currentBlocks.value);

    function confirm(b) { b.reviewStatus = '已确认'; window.NP.clearPendingReview(b.id); ElementPlus.ElMessage.success('已确认，准确率已更新'); }
    const fixVisible = ref(false);
    const fixBlock = ref(null);
    const fixText = ref('');
    function openFix(b) { fixBlock.value = b; fixText.value = b.content; fixVisible.value = true; }
    function saveFix() {
      fixBlock.value.content = fixText.value;
      fixBlock.value.reviewStatus = '已修正';
      fixVisible.value = false;
      ElementPlus.ElMessage.success('已保存修正，差异记录将用于 AI 模型优化');
    }

    // 增量重解析（规则生效 → 影响范围 → 重解析）
    const reparseRules = [
      { ruleType: '内容块切分', change: '操作步骤最小可复用单元粒度调整（按单指令切分）', files: 134, blocks: 892, priority: '高', status: '重解析中' },
      { ruleType: '参数提取', change: '正文内嵌复合参数拆分阈值更新', files: 89, blocks: 156, priority: '中', status: '重解析中' },
      { ruleType: '章节识别', change: '非标准章节「机组主要螺栓拧紧力矩」归类为安装调试/技术要求', files: 47, blocks: 312, priority: '高', status: '已完成' },
      { ruleType: '表格解析', change: '新增部件清单(BOM)纳入结构化解析', files: 23, blocks: 0, priority: '中', status: '已完成' },
      { ruleType: '术语标准化', change: '新增映射：机封 → 机械密封', files: 211, blocks: 380, priority: '低', status: '排队中' },
    ];
    const reparseAffectedBlocks = reparseRules.reduce((s, r) => s + r.blocks, 0);
    const reparseTotal = reparseAffectedBlocks || 1;
    const reparseDone = 1196;
    const reparseQueue = 144;
    const reparsePct = Math.round(reparseDone / reparseTotal * 100);
    const reparseDiff = window.NP.diffText(
      '拧紧力矩：M20 螺栓 45N·m。注意：紧固后复查。',
      '拧紧力矩：M20 螺栓 55N·m（按 RCCM 规范调整）。注意：紧固后复查力矩并记录。'
    );

    // 解析元素清单（§70：标注类型与位置）
    const elements = computed(() => {
      if (!currentBlocks.value.length) return [];
      const list = [];
      const basePage = 8 + (currentNode.value ? (currentNode.value.num.charCodeAt(0) % 10) : 2);
      currentBlocks.value.forEach((b, i) => {
        if (b.safetyLevel) list.push({ type: '警示框', page: basePage + i, pos: `§${currentNode.value?.num || ''}.${i + 1}`, label: b.safetyLevel + '标识：' + b.content.slice(0, 24) });
        else list.push({ type: '段落', page: basePage + i, pos: `§${currentNode.value?.num || ''}.${i + 1}`, label: b.contentType + '·' + b.content.slice(0, 24) });
      });
      if (currentOriginalTable.value) list.push({ type: '表格', page: basePage + 2, pos: `表-${currentNode.value?.num || '1'}`, label: (currentOriginalTable.value.header || []).join('·') + '（' + (currentOriginalTable.value.rows || []).length + '行）' });
      // 图片元素（手册真实含图，演示占位）
      const imgCount = currentNode.value && currentNode.value.num.startsWith('1') ? 2 : 1;
      for (let k = 0; k < imgCount; k++) list.push({ type: '图片', page: basePage + 1 + k * 2, pos: `图-${currentNode.value?.num || '1'}-${k + 1}`, label: ['结构示意图', '外形尺寸图', '原理框图'][k] || '插图' });
      return list;
    });
    const cnt = computed(() => {
      const c = { 段落: 0, 表格: 0, 图片: 0, 警示框: 0 };
      elements.value.forEach(e => { c[e.type] = (c[e.type] || 0) + 1; });
      return c;
    });
    const images = computed(() => elements.value.filter(e => e.type === '图片'));
    function elemTag(t) { return { 段落: 'info', 表格: 'primary', 图片: 'success', 警示框: 'warning' }[t] || ''; }
    function locateElem(row) { ElementPlus.ElMessage.info('定位至第 ' + row.page + ' 页 · ' + row.pos); }

    // ---- 参数/表格 ----
    const params = M.params;
    const compound = M.compoundDemo;
    const tableOptions = [
      { key: 'paramTable', label: '技术参数表（1.1.1 供电和流体特性）' },
      { key: 'deviceCodeTable', label: '设备代码清单（0.6）' },
      { key: 'torqueTable', label: '螺栓力矩表（1.5.14）' },
      { key: 'faultTable', label: '故障诊断表（2.3 现象-原因-措施）' },
      { key: 'spareTable', label: '备件清单（表3.1 易损件）' },
      { key: 'stdTable', label: '适用标准表（0.7 引用标准与规范性文件）' },
      { key: 'bomTable', label: '部件清单（1.3 总成与分总成组成）' },
    ];
    const tableKey = ref('faultTable');
    // 需求§123-128 点名的表格类型：demo 补「适用标准表」「部件清单」两类（其余来自真实手册抽取）
    const EXTRA_TABLES = {
      stdTable: {
        chapterPath: '第0章概述/0.7引用标准及规范性文件',
        header: ['序号', '类别', '标准代号', '名称', '版本'],
        rows: [
          ['1', '国家标准', 'GB/T 3216', '回转动力泵 水力性能验收试验', '2016'],
          ['2', '国家标准', 'GB/T 5657', '离心泵 技术条件', '2012'],
          ['3', '核行业标准', 'EJ/T', '核安全相关设备抗震鉴定', '2003'],
          ['4', 'RCC-M', 'RCC-M', '压水堆核岛机械设备设计和建造规则', '2007+2007Add'],
          ['5', '国际标准', 'ASME B73.1', '化工流程卧式泵', '2019'],
          ['6', '企业技术文件', 'CQPI-TR-2021-08', '核级泵机械密封选型与冲洗方案导则', 'V2.1'],
        ],
      },
      bomTable: {
        chapterPath: '第1章设备描述/1.3总成与分总成组成',
        header: ['零部件编号', '名称', '数量', '关联图纸'],
        rows: [
          ['PTR-001-01', '泵本体（总成）', '1', 'DWG-PTR-001-A'],
          ['PTR-001-02', '泵壳', '1', 'DWG-PTR-002-A'],
          ['PTR-001-03', '叶轮', '1', 'DWG-PTR-003-A'],
          ['PTR-001-04', '泵盖', '1', 'DWG-PTR-004-A'],
          ['PTR-001-05', '机械密封组件（集装式）', '1', 'DWG-PTR-005-A'],
          ['PTR-001-06', '联轴器组件（膜片挠性）', '1', 'DWG-PTR-006-A'],
          ['PTR-001-07', '轴承组件（驱动端/非驱动端）', '2', 'DWG-PTR-007-A'],
          ['PTR-001-08', '主轴', '1', 'DWG-PTR-008-A'],
        ],
      },
    };
    const currentTable = computed(() => {
      const t = M.tables[tableKey.value] || EXTRA_TABLES[tableKey.value];
      if (!t) return null;
      return { ...t, rows: t.rows.map(r => Object.fromEntries(r.map((c, i) => ['c' + i, c]))) };
    });

    /* ---------- 扫描件 OCR 校对（真实手册数据：标题/正文/图片/表格） ---------- */
    const ocrDoc = { name: window.OCR_MOCK.doc, dpi: window.OCR_MOCK.dpi };
    const ocrPages = ref(window.OCR_MOCK.pages);
    const ocrPage = ref(1);
    const ocrZoom = ref(1);
    const ocrSelId = ref(null);      // 当前选中条目 loc（卡片 ↔ 框选双向联动）
    const ocrFilter = ref('全部');
    const ocrEditId = ref(null);     // 内联修正中的条目 loc
    const ocrEditText = ref('');
    const ocrStageEl = ref(null);
    const ocrCardsEl = ref(null);

    const ocrTotal = computed(() => ocrPages.value.reduce((s, p) => s + p.items.length, 0));
    const ocrDone = computed(() => ocrPages.value.reduce((s, p) => s + p.items.filter(i => i.status !== '待校对').length, 0));
    const ocrPending = computed(() => ocrPages.value.reduce((s, p) => s + p.items.filter(i => i.status === '待校对').length, 0));
    // 识别准确率 = 确认/(确认+修正)，与「AI 审核」tab 同口径（机器答对占比，人工裁决统计）
    const ocrAcc = computed(() => {
      const confirmed = ocrPages.value.reduce((s, p) => s + p.items.filter(i => i.status === '已确认').length, 0);
      const corrected = ocrPages.value.reduce((s, p) => s + p.items.filter(i => i.status === '已修正').length, 0);
      const done = confirmed + corrected;
      return done ? +((confirmed / done) * 100).toFixed(1) : 100;
    });
    const ocrPageData = computed(() => ocrPages.value[ocrPage.value - 1]);
    const ocrCounts = computed(() => {
      const c = { 全部: ocrTotal.value, 标题: 0, 正文: 0, 图片: 0, 表格: 0 };
      ocrPages.value.forEach(p => p.items.forEach(i => { c[i.type] = (c[i.type] || 0) + 1; }));
      return c;
    });
    // 包装 {it, pageIdx}：保持条目引用（内联编辑直接改 it 才响应式），并携带页码用于跳页
    const ocrAllItems = computed(() => ocrPages.value.flatMap((p, pi) => p.items.map(it => ({ it, pageIdx: pi }))));
    const ocrShownItems = computed(() => ocrAllItems.value.filter(w => ocrFilter.value === '全部' || w.it.type === ocrFilter.value));

    function ocrBoxStyle(it) {
      const [x1, y1, x2, y2] = it.bbox;
      return { left: x1 * 100 + '%', top: y1 * 100 + '%', width: (x2 - x1) * 100 + '%', height: (y2 - y1) * 100 + '%' };
    }
    function ocrTypeTag(t) { return { 标题: 'primary', 正文: 'info', 图片: 'success', 表格: 'warning' }[t] || 'info'; }
    // 一键确认：全部待校对 → 已确认
    function ocrConfirmAll() {
      ElementPlus.ElMessageBox.confirm('将全部 ' + ocrPending.value + ' 条待校对条目确认为识别无误？', '一键确认', {
        confirmButtonText: '全部确认', cancelButtonText: '取消', type: 'warning',
      }).then(() => {
        ocrPages.value.forEach(p => p.items.forEach(i => { if (i.status === '待校对') i.status = '已确认'; }));
        ElementPlus.ElMessage.success('已一键确认全部待校对条目，准确率已更新');
      }).catch(() => {});
    }
    function ocrStatusCls(s) { return { 待校对: 'st-pending', 已确认: 'st-confirmed', 已修正: 'st-fixed' }[s]; }
    const ocrPaperStyle = computed(() => ({ width: (62 * ocrZoom.value) + '%' }));
    function ocrZoomBy(d) { ocrZoom.value = Math.min(1.6, Math.max(0.7, +(ocrZoom.value + d).toFixed(2))); }
    function ocrGoto(p) { ocrPage.value = Math.min(ocrPages.value.length, Math.max(1, p)); }

    // 双向联动：选中条目 → 跳页 + 框选/卡片同时滚动定位
    function selectOcr(w) {
      ocrEditId.value = null;
      ocrSelId.value = w.it.loc;
      if (ocrPage.value !== w.pageIdx + 1) ocrPage.value = w.pageIdx + 1;
      nextTick(() => {
        const box = ocrStageEl.value && ocrStageEl.value.querySelector('[data-oid="' + w.it.loc + '"]');
        if (box) box.scrollIntoView({ block: 'center', behavior: 'smooth' });
        const card = ocrCardsEl.value && ocrCardsEl.value.querySelector('[data-oid="' + w.it.loc + '"]');
        if (card) card.scrollIntoView({ block: 'center', behavior: 'smooth' });
      });
    }
    function onOcrBoxClick(it) {
      const w = ocrAllItems.value.find(x => x.it === it);
      if (!w) return;
      if (ocrFilter.value !== '全部' && it.type !== ocrFilter.value) ocrFilter.value = '全部';
      selectOcr(w);
    }
    // 目录树跳页：找第一个包含该章节条目的页（先精确匹配，-1 时章级回退，再 -1 提示）
    function onOcrTocNode(data) {
      if (!data.num) return;
      const m = String(data.num).match(/^第?(\d+(?:\.\d+)*)/);
      const want = m ? m[1] : null;
      if (!want) return;
      const exact = (ch) => ch === want || ch.startsWith(want + '.') || want.startsWith(ch + '.');
      const chapHit = (ch) => ch.split('.')[0] === want.split('.')[0];
      let idx = ocrPages.value.findIndex(p => p.items.some(it => exact(it.chapter)));
      if (idx < 0 && want.indexOf('.') < 0) idx = ocrPages.value.findIndex(p => p.items.some(it => chapHit(it.chapter)));
      if (idx >= 0) ocrGoto(idx + 1);
      else ElementPlus.ElMessage.info('该章节暂无扫描页（演示仅 ' + ocrPages.value.length + ' 页）');
    }

    function ocrConfirm(it) { it.status = '已确认'; ElementPlus.ElMessage.success('已确认 ' + it.loc); }
    function ocrStartEdit(it) { ocrEditId.value = it.loc; ocrEditText.value = it.text; }
    function ocrCancelEdit() { ocrEditId.value = null; }
    function ocrSaveEdit(it) {
      if (ocrEditText.value && ocrEditText.value !== it.text) {
        it.text = ocrEditText.value; it.conf = 1; it.status = '已修正';
        ElementPlus.ElMessage.success('OCR 修正已记录，差异入库用于模型优化');
      }
      ocrEditId.value = null;
    }

    /* ---------- 专用表格清单解析 ---------- */
    const tableKind = ref('equip');
    const tableTypes = ref([
      { key: 'equip', name: '设备代码清单', parsed: 12, equip: 'PTR冷却泵及配套仪表', chapter: '第1章 设备描述/1.1 设备代码', merge: '已处理', cols: ['设备/仪表编码', '名称', '型号', '生产厂家', '核安全等级'], widths: [140, 120, 120, 140, 100],
        rule: '识别手册涉及的全部设备及仪表编码，建立主设备与配套仪表的关联（主从关系）。跨页续表按设备编码归并。',
        rows: [
          { c0: 'PTR-001', c1: 'PTR冷却泵', c2: 'LPS-300', c3: '重庆水泵厂', c4: '核3级' },
          { c0: 'PTR-001-IT01', c1: '入口压力变送器', c2: 'EJA-310E', c3: '横河电机', c4: '非核级' },
          { c0: 'PTR-001-IT02', c1: '出口压力变送器', c2: 'EJA-310E', c3: '横河电机', c4: '非核级' },
          { c0: 'PTR-001-FT01', c1: '流量计', c2: '8742R', c3: 'E+H', c4: '非核级' },
        ] },
      { key: 'std', name: '适用标准清单', parsed: 8, equip: 'PTR冷却泵', chapter: '第1章 设备描述/1.2 引用标准', merge: '已处理', cols: ['标准代号', '名称', '版本', '类别'], widths: [140, 200, 80, 120],
        rule: '区分国际/国家/行业/企业标准，按代号+版本去重；区分规范性引用与资料性引用。',
        rows: [
          { c0: 'GB/T 3215', c1: '离心泵技术条件', c2: 'I类', c3: '国家标准' },
          { c0: 'RCC-M', c1: '压水堆核岛机械设备设计和建造规则', c2: '2007+2009', c3: '核行业标准' },
          { c0: 'NB/T 20003.6', c1: '核电厂核安全相关泵', c2: '2019', c3: '核行业标准' },
          { c0: 'Q/CGN-PTR-001', c1: 'PTR冷却泵采购技术规格书', c2: 'V2.1', c3: '企业内部' },
        ] },
      { key: 'spare', name: '备件清单', parsed: 18, equip: 'PTR冷却泵', chapter: '第6章 维修/6.4 备件信息', merge: '已处理', cols: ['备件名称', '型号', '质保等级', '图纸编码', '设计寿期', '生产厂家'], widths: [140, 120, 90, 130, 90, 130],
        rule: '解析易损件/备品备件，关联质保等级与图纸编码；存储要求抽取至关联字段。',
        rows: [
          { c0: '机械密封组件', c1: 'MG-12', c2: 'Q1', c3: 'DWG-MS-001', c4: '5年', c5: '约翰克兰' },
          { c0: '驱动端轴承', c1: '6308 ZZ', c2: 'Q3', c3: 'DWG-BR-006', c4: '8年', c5: 'SKF' },
          { c0: '联轴器膜片', c1: 'MF-300', c2: 'Q2', c3: 'DWG-CO-012', c4: '10年', c5: '哈尔滨电气' },
        ] },
      { key: 'part', name: '部件清单', parsed: 24, equip: 'PTR冷却泵', chapter: '第1章 设备描述/1.3 总成与分总成组成', merge: '已处理(跨行)', cols: ['零部件编号', '名称', '数量', '关联图纸', '层级'], widths: [130, 140, 70, 140, 90],
        rule: '解析总成-分总成-零部件层级，处理跨行合并单元格；建立部件间组成(从属)关系。',
        rows: [
          { c0: 'PTR-001-01', c1: '泵本体（总成）', c2: '1', c3: 'DWG-PTR-001-A', c4: 'L1' },
          { c0: 'PTR-001-02', c1: '泵壳', c2: '1', c3: 'DWG-PTR-002-A', c4: 'L2' },
          { c0: 'PTR-001-03', c1: '叶轮', c2: '1', c3: 'DWG-PTR-003-A', c4: 'L2' },
          { c0: 'PTR-001-05', c1: '机械密封组件', c2: '1', c3: 'DWG-PTR-005-A', c4: 'L2' },
        ] },
    ]);

    onMounted(() => {
      // 默认选中 1.2 详细描述
      const ch1 = tocTree.find(n => n.num === '第1章');
      const n12 = ch1 && ch1.children.find(n => n.num === '1.2');
      if (n12) currentNode.value = n12;
    });

    return {
      tab, docs, batch, startImport, retry,
      docTree, docTreeEl, currentFolder, onTreeNode, treeCount,
      treeFilter, filterTreeNode, treeAddRoot, treeAddChild, treeRename, treeRemove, allowTreeDrop, onTreeDrop,
      q, equipOptions, mfrOptions, typeOptions, resetQuery,
      statusFilter, statusChips, toggleStatus,
      filteredDocs, selectedCount, runningCount, failedCount, onSelection,
      statusType, batchRetryFailed, batchReparse, batchDelete, stopAll, stopRow, deleteRow, msg,
      stepIcon, stepStatusText, stepTagType,
      folderOnlyTree,
      blocks, confirmed, corrected, pending, accuracy, reviewedPct,
      folderPath, currentDoc, onFolderChange,
      chapterPath, chapterOptions, onChapterChange, onlyPending, shownBlocks, highlightId, locateBlock, origEl, elemDrawer,
      tocTree, currentNode, currentBlocks, currentOriginalTable, onNode, resultTab,
      elements, cnt, images, elemTag, locateElem,
      confirm, openFix, saveFix, fixVisible, fixBlock, fixText,
      params, compound, tableOptions, tableKey, currentTable,
      reparseRules, reparseAffectedBlocks, reparseTotal, reparseDone, reparseQueue, reparsePct, reparseDiff,
      ocrDoc, ocrPages, ocrPage, ocrTotal, ocrDone, ocrPending, ocrAcc,
      ocrZoom, ocrSelId, ocrFilter, ocrEditId, ocrEditText, ocrStageEl, ocrCardsEl,
      ocrPageData, ocrCounts, ocrShownItems,
      ocrBoxStyle, ocrTypeTag, ocrConfirmAll, ocrStatusCls, ocrPaperStyle,
      ocrZoomBy, ocrGoto, selectOcr, onOcrBoxClick, onOcrTocNode,
      ocrConfirm, ocrStartEdit, ocrSaveEdit, ocrCancelEdit,
      tableKind, tableTypes,
      typeColor: window.NP.contentTypeColor, confType: window.NP.confTagType, can: window.NP.can,
    };
  },
};
