/* P8 AI辅助编辑与知识增强 */
window.PAGES = window.PAGES || {};
window.PAGES.aiAssist = {
  template: `
  <div>
    <div style="display:flex; gap:14px;">
      <!-- 编辑区 -->
      <div class="panel" style="flex:1.4;">
        <div class="panel-title">
          <span>内容块编辑 · CB-0102（3.7 回装）</span>
          <span>
            <el-button size="small" type="primary" icon="MagicStick" @click="genSuggestions" :loading="analyzing">
              {{ analyzed ? '重新分析' : 'AI 智能分析' }}
            </el-button>
            <el-button size="small" icon="FolderChecked" @click="save">保存入库</el-button>
          </span>
        </div>
        <el-input v-model="text" type="textarea" :rows="12"
                  style="font-size:13.5px; line-height:1.9;" placeholder="在此编辑内容块…" />
        <div style="display:flex; gap:14px; margin-top:8px;" class="sub-text">
          <span>DMC: HPR1000-A-45-20-0000-00A-200J-D</span>
          <span>内容类型: 操作步骤</span>
          <span>版本: V2</span>
          <span style="margin-left:auto; color:var(--np-success);" v-if="adoptedCount">已采纳 {{ adoptedCount }} 条智能建议</span>
        </div>

        <!-- 智能审查 -->
        <div class="panel" style="margin-top:14px; margin-bottom:0;">
          <div class="panel-title">
            <span>智能审查助手 <span class="ai-badge">知识图谱推理</span></span>
            <el-button size="small" text type="primary" @click="runReview" :disabled="!analyzed">运行一致性/完整性审查</el-button>
          </div>
          <template v-if="reviewed">
            <div v-for="r in reviewResults" :key="r.text" style="display:flex; gap:8px; align-items:flex-start; padding:6px 0;">
              <el-icon :color="r.ok ? '#2e8b57' : '#e6a23c'" style="margin-top:2px;"><component :is="r.ok ? 'CircleCheckFilled' : 'WarningFilled'" /></el-icon>
              <span style="font-size:12.5px; line-height:1.7;">{{ r.text }}</span>
            </div>
          </template>
          <div v-else class="sub-text">基于知识图谱推理检查内容一致性与完整性（安全注意事项覆盖、技术特性完整性等）。</div>
        </div>
      </div>

      <!-- 智能建议面板 -->
      <div class="panel" style="flex:1; max-height:680px; overflow:auto;">
        <div class="panel-title">
          <span>智能写作助手 <span class="ai-badge">知识增强</span></span>
          <span class="sub-text">采纳反馈将用于优化建议准确性</span>
        </div>
        <template v-if="analyzed">
          <div v-for="(s, i) in suggestions" :key="i" class="sug-card" :class="s.level">
            <div class="sug-title">
              <el-icon :size="14"><component :is="s.icon" /></el-icon>
              {{ s.type }} · {{ s.title }}
            </div>
            <div class="sug-detail" :class="{typing: s.streaming}">{{ s.shown }}</div>
            <div v-if="!s.streaming">
              <template v-if="!s.done">
                <el-button size="small" type="success" @click="adopt(s)">一键采纳</el-button>
                <el-button size="small" text @click="ignore(s)">忽略</el-button>
              </template>
              <el-tag v-else size="small" :type="s.adopted ? 'success' : 'info'">
                {{ s.adopted ? '已采纳 ✓' : '已忽略' }}
              </el-tag>
            </div>
          </div>
        </template>
        <el-empty v-else description="点击「AI 智能分析」，基于知识库与知识图谱实时生成写作建议" :image-size="90" />
      </div>
    </div>

    <!-- 上下文知识检索 -->
    <div class="panel">
      <div class="panel-title">
        <span>上下文感知的知识检索</span>
        <span class="sub-text">根据当前编辑内容智能召回</span>
      </div>
      <div style="display:flex; gap:8px; margin-bottom:10px;">
        <el-input v-model="searchQ" placeholder="自然语言检索知识库，如：密封环跳动允差" @keyup.enter="searchKb" />
        <el-button icon="Search" @click="searchKb">检索</el-button>
      </div>
      <div v-if="recentSearches.length" style="margin-bottom:10px;">
        <span class="sub-text">最近检索：</span>
        <el-tag v-for="(q, i) in recentSearches" :key="i" size="small" effect="plain" style="cursor:pointer; margin-right:6px;" @click="quickSearch(q)">{{ q }}</el-tag>
      </div>
      <el-row :gutter="12">
        <el-col :span="8" v-for="k in kbResults" :key="k.title">
          <div style="border:1px solid var(--np-border); border-radius:4px; padding:10px 12px; height:100%;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <b style="font-size:12.5px;">{{ k.title }}</b>
              <el-tag size="small" type="success" effect="plain">{{ k.conf }}</el-tag>
            </div>
            <div class="sub-text" style="margin:6px 0; line-height:1.7;">{{ k.text }}</div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span class="dmc">{{ k.source }}</span>
              <el-button size="small" text type="primary" @click="insertRef(k)">插入引用</el-button>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>
  </div>`,

  setup() {
    const { ref, computed, onMounted } = Vue;
    const A = window.MOCK.aiAssist;
    const text = ref(A.editorText);
    const analyzing = ref(false);
    const analyzed = ref(false);
    const suggestions = ref([]);
    const adoptedCount = computed(() => suggestions.value.filter(s => s.done && s.adopted).length);

    function genSuggestions() {
      analyzing.value = true;
      analyzed.value = false;
      suggestions.value = [];
      // 逐条流式生成建议
      const list = A.suggestions.map(s => ({ ...s, shown: '', streaming: true, done: false, adopted: false }));
      let i = 0;
      setTimeout(() => {
        analyzing.value = false;
        analyzed.value = true;
        (function next() {
          if (i >= list.length) { suggestions.value = list; return; }
          const s = list[i];
          suggestions.value = [...list.slice(0, i + 1)];
          window.NP.stream(s.detail, t => { s.shown = t; suggestions.value = [...suggestions.value]; },
            () => { s.streaming = false; i++; next(); }, 18);
        })();
      }, 1500);
    }

    function adopt(s) {
      s.done = true; s.adopted = true;
      if (s.action === 'replace' && s.from) {
        text.value = text.value.replace(s.from, s.to);
      } else if (s.action === 'mark' && s.from) {
        text.value = text.value.replace(s.from, s.from + '【待复核：低于同类设备常见范围 55~70N·m】');
      } else if (s.action === 'cite') {
        text.value += '\n\n【引用】安全注意事项详见 CB-0021《安全操作说明》。';
      } else if (s.action === 'insert') {
        text.value += '\n\n【参考】转子部件装配完成后按 3.5.2 节要求检查叶轮密封环径向跳动，允差 0.05mm。';
      }
      ElementPlus.ElMessage.success('已采纳建议并记录反馈');
    }
    function ignore(s) { s.done = true; s.adopted = false; }

    const reviewed = ref(false);
    const reviewResults = ref([]);
    function runReview() {
      reviewed.value = true;
      const termAdopted = suggestions.value[0] && suggestions.value[0].done && suggestions.value[0].adopted;
      const citeAdopted = suggestions.value[2] && suggestions.value[2].done && suggestions.value[2].adopted;
      reviewResults.value = [
        termAdopted
          ? { ok: true, text: '一致性检查通过：文中「机械密封」与术语标准化字典一致（已采纳术语建议）。' }
          : { ok: false, text: '一致性提示：文中「机封」为非标准术语，与字典中「机械密封」不一致，建议先采纳术语建议。' },
        { ok: false, text: '完整性提示：操作步骤未包含装配前清洁度等级要求，同类内容块覆盖率 89%。' },
        { ok: false, text: '参数完整性：缺少「拧紧顺序」技术特性描述（力矩分3次对称拧紧），建议补充。' },
        citeAdopted
          ? { ok: true, text: '安全注意事项：已引用 CB-0021《安全操作说明》，覆盖装配作业安全要求。' }
          : { ok: false, text: '安全注意事项缺失：该装配操作未关联任何安全注意事项，建议采纳完整性提示建议。' },
      ];
    }

    function save() { ElementPlus.ElMessage.success('已保存入库，内容块版本 V2 → V3，变更记录可追溯'); }

    // 知识检索
    const searchQ = ref('');
    const recentSearches = ref(['密封环跳动允差', '螺栓拧紧力矩', '轴承润滑']);
    function quickSearch(q) { searchQ.value = q; searchKb(); }
    const KB_POOL = [
      { title: '叶轮密封环跳动检查要求', text: '转子部件装配完成后按 3.5.2 节要求检查转子部件中叶轮密封环的径向跳动。', conf: '0.95', source: '3.7.1 轴承体装配' },
      { title: '拧紧力矩通用要求', text: '拧紧时力矩必须分 3 次（或以上）拧紧到位，拧紧时必须对称拧紧完所有螺母。', conf: '0.93', source: '3.5.2 检查及维修' },
      { title: '相似设备：RRI冷却泵回装要点', text: '同类离心泵回装作业中，轴承润滑与密封面保护为质量关键点。', conf: '0.88', source: '知识库·相似设备' },
    ];
    const kbResults = ref(KB_POOL);
    function searchKb() {
      // 模拟上下文检索：始终返回按相关度排序的结果（顺序微调以示响应）
      kbResults.value = [...KB_POOL].sort(() => (searchQ.value ? 0 : 0));
      ElementPlus.ElMessage.success('已基于当前编辑上下文召回 3 条相关知识');
    }
    function insertRef(k) {
      text.value += `\n\n【引用】${k.text}（来源：${k.source}）`;
      ElementPlus.ElMessage.success('已插入引用内容');
    }

    onMounted(() => { genSuggestions(); });

    return {
      text, analyzing, analyzed, suggestions, adoptedCount, genSuggestions, adopt, ignore,
      reviewed, reviewResults, runReview, save,
      searchQ, kbResults, searchKb, insertRef, recentSearches, quickSearch,
    };
  },
};
