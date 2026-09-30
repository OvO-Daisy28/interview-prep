# GraphRAG 过程中遇到的问题及解决方式

> 定位：把 GraphRAG 相关的所有问题（实验踩坑 + T1/T3 测试发现 + 机制级问题）整理成一份，每个问题含现象、根因、解决、源码依据。
> 事实来源：实习记录文档 + T1/T3 测试报告 + 源码。

---

## 问题 1：多文档建图空图（0 nodes, 0 edges）

**现象**：GraphRAG 任务跑完，前端无图谱，ES 核验 0 实体 0 关系。

**根因**（两条路径，源码实证）：
1. **格式解析失败**：LLM 输出 JSON 格式漂移，`handle_single_entity_extraction`（utils.py:344）要求首字段是 `"entity"`、至少 4 个属性，格式不符返回 None
2. **类型被过滤**：LLM 抽了实体但 `entity_type` 不在 `DEFAULT_ENTITY_TYPES` 清单（:122 `if ... in ent_types`），直接丢弃

**我的实测结论**：根因是模型结构化输出稳定性，**不是文档规模**——
- qwen-plus：能建图但慢（470 节点/436 边）
- DeepSeek Flash：空图（格式漂移）
- GLM-5.2：稳定成功
- Qwen3.8-27B-AWQ-INT4：稳定成功（979 节点/719 边，17 抽取单元全成功，无空图）

**解决**：
- 模型对比选型，选格式遵循稳定的模型
- 分批解析策略（先 1-2 份验证再批量）
- 重跑前先做单请求连通性/权限验证（qwen-plus 问答 10 次返回 `Access to model denied` 的教训）

---

### 深挖：空图背后的原理与抽取模型选型

#### 为什么 RAGFlow 的格式要求比 JSON 更难

RAGFlow light 模式**不是让模型输出标准 JSON**，而是自定义分隔符格式（graph_prompt.py 定义）：

```
("entity"<t>实体名<t>实体类型<t>实体描述<COMPLETE>)
("relationship"<t>源实体<t>目标实体<t>关系描述<t>关键词<COMPLETE>)
```

`<t>` 是 tuple_delimiter，`<COMPLETE>` 是 record_delimiter。解析逻辑（utils.py:344 `handle_single_entity_extraction`）要求：第一个字段必须是字符串 `"entity"`（带引号）、至少 4 个字段、entity_type 必须在配置清单里。不符合任一条件 → 返回 None → 这条记录被丢弃。

#### 为什么结构化输出对 LLM 很难

LLM 本质是"概率续写"——每个 token 按概率采样。让它输出"严格格式"等于要求**几百个 token 里每一个都落在正确位置**。任何一个 token 漂移（多空格、引号位置错、分隔符漏写），整条记录解析失败。

**关键认知：对话能力 ≠ 格式遵循能力**。DeepSeek Flash 对话很好但格式漂移导致空图——不是模型"差"，是不适合"结构化抽取"这个特定任务维度。

**具体失败模式**：
1. JSON 漂移（模型输出 JSON 而非自定义格式）
2. 字段遗漏（字段数 < 4 → None）
3. 类型词漂移（type 不在清单 → 被过滤）
4. 输出截断（max_tokens 不够 → 最后几条不完整）
5. 遵循度差异（有些模型训练时强化了指令遵循，有些没有）

#### "约束模型"的局限

可做的约束：prompt few-shot 强化、temperature=0 降随机性、gleaning 补抽（RAGFlow 内置 ENTITY_EXTRACTION_MAX_GLEANINGS=2）。

**局限**：prompt 层约束是"建议"不是"强制"——模型可以不听。真正可靠的是模型本身的结构化输出能力（训练时学了遵守格式）或后处理容错解析器。

#### 模型选型：三个维度（按重要性排序）

**1. 格式遵循能力（最核心）**
- model card 是否支持 structured output / function calling
- 是否支持 `response_format=json_object` / JSON mode
- **实测**：跑 10-20 份 chunk，统计格式遵循率 = 解析成功数 / 总记录数，低于 90% 直接排除

**2. 中文理解能力**
- 训练数据含大量中文
- 实测：看实体名是不是合理中文实体（不是整句话当实体名）

**3. 成本与速度**
- token 单价 + 速度
- 本地部署 vs 云端 API 权衡

#### 我的实际选型路径（诚实版：工程务实导向）

Qwen3.8-27B 被选中不是"系统性格式遵循率测试后选的"，路径更务实：
1. **项目要求本地部署**（甲方内网、数据不出网、不能调云端 API）
2. **4090 有 4 张卡**，27B AWQ-INT4 量化后 TP2 占 GPU0+3 放得下
3. **Qwen 系列是中文场景默认选择**（阿里出品、中文训练充分、社区认可）
4. 部署后发现建图也能用 → 一个模型干两件事（抽取 + 问答）

选完之后验证：979 节点/719 边、17 抽取单元全成功、无空图 → 证明选型有效。

#### 为什么 Qwen3.8-27B 能成功（三层原因）

**1. Qwen 系列格式遵循能力强**——Qwen 技术报告强调 structured output / function calling，训练时强化了指令遵循。对比：

| 模型 | 通用对话 | 格式遵循 | 我的实测 |
|---|---|---|---|
| DeepSeek Flash | 强 | 弱 | 空图 |
| GLM-5.2 | 中 | 强 | 成功 |
| Qwen3.8-27B | 强 | 强 | 成功（979/719） |

**2. 27B 规模足够**——结构化抽取要求模型理解复杂 prompt（类型清单+格式要求+few-shot+gleaning 追问），27B 够了，不必 70B。

**3. AWQ-INT4 量化影响小**——AWQ 保留更多关键权重精度，格式遵循这类精细能力受影响较小（比 naive int4 / int2 好）。

#### 面试的精确答法

被问"选 Qwen3.8-27B 的依据"：
> "选型是工程务实导向——项目要求内网本地部署、4090 有卡、Qwen 是中文场景默认选择，27B AWQ-INT4 量化后刚好放得下。选完验证能用：建图 979 节点/719 边、17 单元全成功无空图。成功原因是 Qwen 系列格式遵循能力强——结构化抽取的瓶颈不在模型大小或对话能力，在'能不能稳定按指定格式输出'，我之前实测 DeepSeek Flash 对话很好但格式漂移导致空图。所以选型真正要看格式遵循率，不是榜单分数。"

被问"格式遵循率怎么测"：
> "我当时是三个模型对比试出来的。更系统的做法是：先跑 10-20 份 chunk、看模型原始输出、统计解析成功率（格式遵循率），低于 90% 直接排除——不用等建图失败才发现。后来在 4090 上建图前先做单请求连通性验证，就是之前踩坑的教训固化。"

---

## 问题 2：4090 建图第一次全失败（CONNECTION_ERROR）

**现象**：4090 上第一次 GraphRAG，17 个 chunk 全部 CONNECTION_ERROR，35 秒失败。

**根因**：模型实例名 `qwen38-local` 未找到——RAGFlow 配置的模型实例名和实际部署的 vLLM 模型名不匹配。

**解决**：修正模型实例名配置，重跑成功（979 nodes/719 edges/1310s）。

**教训**：建图前先单请求验证模型连通性——和问题 1 的 qwen-plus 教训一致，固化为流程。

---

## 问题 3：建图成本高（21.8 分钟、90 万 tokens）

**现象**：1 份 PTR 手册 116 chunks，建图 1310.67 秒、约 90 万 tokens。

**根因**：
- gleaning 补抽（`ENTITY_EXTRACTION_MAX_GLEANINGS=2`，每 chunk 抽完问"是否遗漏"再补一轮）
- LLM 单次调用 20 分钟超时上限（extractor.py:95）
- 17 个抽取单元 × 多轮调用 × 长 prompt

**解决/对策**：
- 不是所有库都该开 GraphRAG——按问题类型路由：局部问题走普通 RAG，全局问题才走 KG
- gleaning 次数可配（默认 2，我实测用 1）
- batch_chunk_token_size 控制（4096 token 合并单元）

---

## 问题 4：全局问题 KG 检索无优势（T1 测试发现）

**现象**：T1 测试 8 道全局问题，KG 开关对检索相似度 0 变化（和局部题 +40% 形成对比）。

**根因**（三层）：
1. **社区报告缺失**：light 模式架构上不做社区发现（T1 前置确认实证），没有 `community_report` chunk。全局问题依赖社区报告跨章节汇总，没开就没优势
2. **实体匹配不适用**：全局问题（"有哪些故障模式"）不含具体实体名称，KG 的实体匹配→子图扩展机制无法触发有效路径
3. **向量检索已足够**：手册单文档，top_n=6 向量召回已覆盖不同章节，LLM 在 prompt 里自行汇总

**解决/对策**：
- 局部问题开 KG（+40% 相似度），全局问题开但不期望显著收益
- 要提升全局效果需切 general 模式开社区发现（T6 会对比）
- 这是 light 模式架构限制，不是配置遗漏

---

## 问题 5：文档修改后图谱旧数据残留（T3 测试发现）

**现象**：传修改版文档（640→650）后，图谱里 640 和 650 同时存在，旧数据不自动清理。

**根因**（源码实证）：`graph_merge`（utils.py:314）同名实体描述**追加不替换**：
```python
node["description"] += GRAPH_FIELD_SEP + attr["description"]  # 追加！
```
RAGFlow 不区分旧版本和新版本——实体描述是叠加的。修改文档被当成新文档（新 doc_id），同名实体描述叠加。

**解决/对策**：
- 原生不支持自动覆盖，需二开：文档版本管理 + 图谱自动清理触发
- 最佳实践：删除旧文档 → `DELETE /index?type=graph` 清图 → 传新文档 → 重建（最干净但全量）
- 增量方案（可接受残留）：直接传新版，省 20% 时间，但旧数据保留

---

## 问题 6：删除文档后图谱不自动清理（T3 测试发现）

**现象**：删除 v1 文档后，图节点/边数不变，ES graph 记录数不变，只标记 `removed_kwd=Y`。

**根因**：文档 API 的 `DELETE /documents` 不级联清理图谱——图谱是独立 chunk，文档删除只软删（打 removed 标记），图谱记录残留。

**解决**：手动调 `DELETE /api/v1/datasets/<id>/index?type=graph`（wipe=true 默认）清除所有 `knowledge_graph_kwd` 记录 + phase markers。

---

## 问题 7：图谱规模前端展示有上限

**现象**：前端/API 图谱展示不完整，节点边数对不上。

**根因**：页面/API 的图谱展示存在返回上限。

**解决**：绕过前端，直查 ES `knowledge_graph_kwd=graph` 记录核验真实规模。这是我固化的核验习惯——不信任前端展示。

---

## 问题 8：图谱合并超时失败（08-14 假死关联）

**现象**：GraphRAG 合并阶段超时，任务卡住。

**根因**：vanilla 合并超时固定 180s，但任务实际需 215s。超时只包协程，底层 embedding 线程取消不掉，重试产生重复计算。

**解决**（团队补丁）：`_effective_merge_timeout_seconds`（index.py:122）按 embedding 工作量动态计算：
```python
embedding_items = graph.number_of_nodes() + graph.number_of_edges()
estimated_batches = math.ceil(embedding_items / embedding_concurrency)
return max(configured_timeout, base_seconds + estimated_batches * seconds_per_batch)
```
+ 单 embedding 请求限 120s + 超时后取消清理（避免重复计算）。

**关联**：这是故事 2 假死修复的根因之一，详见 [故事2_假死修复.md](03_核心故事/故事2_假死修复.md)。

---

## 问题 9：图谱合并并发竞争

**现象**：多个 graphrag 任务同时合并同一个 KB 的图，数据竞争。

**根因**：合并是读-改-写操作，无锁会互相覆盖。

**解决**（源码已有）：`RedisDistributedLock(f"graphrag_task_{kb_id}", timeout=1200)`（index.py:471）——知识库级锁，保证同一 KB 的合并串行。

---

## 问题 10：增量合并跳过已合并文档

**现象**：重跑 GraphRAG 时，已合并的文档被跳过（不重复 LLM 提取），但怎么实现的？

**根因**（源码实证）：`merge_subgraph_attempt`（index.py:490-492）：
```python
if current_graph and doc_id in current_graph.graph.get("source_id", []):
    callback(msg=f"merge_subgraph doc:{doc_id} already merged, skipping retry.")
    return current_graph
```
全局图的 `source_id` 列表记录已合并的 doc_id，重跑时跳过——这就是 T3 "增量合并省 20%" 的源码机制。

**副作用**：结合问题 5，已合并的旧文档即使内容变了也不会重新提取（除非先清图）——增量是新文档增量，不是修改增量。

---

## 问题 11：阶段断点恢复

**现象**：GraphRAG 任务中途失败/取消，重跑时哪些阶段要重做？

**根因**（源码实证）：`phase_markers.py` + `has_phase_marker(kb_id, PHASE_RESOLUTION/COMMUNITY)`（index.py:463-464）：
- 消歧和社区阶段完成后打 marker
- 重跑时检查 marker，已完成阶段跳过
- 这是断点恢复机制

**副作用**：如果消歧/社区阶段有 bug 导致结果错误，marker 会让后续重跑跳过——需要手动清 marker 或清图重建。

---

## 问题 12：社区报告默认关闭导致全局问题能力缺失

**现象**：light 模式建图后，全局问题 KG 检索无优势（问题 4）。

**根因**：light 模式架构上不做社区发现——不是配置遗漏，是模式选择。

**解决/对策**：
- 切 general 模式开启社区发现（T6 会对比成本/质量）
- 或接受 light 模式限制，全局问题靠向量召回 + LLM 在 prompt 里汇总

---

## 问题分类总结

| 类别 | 问题 | 核心能力体现 |
|---|---|---|
| **模型相关** | 1 空图、2 连接错误、3 成本高 | 模型选型 + 格式遵循判断 |
| **架构限制** | 4 全局无优势、12 社区默认关 | 模式选型 + 诚实评估能力边界 |
| **数据治理** | 5 修改残留、6 删除不清理、7 展示上限 | 版本管理 + 直查 ES 核验 |
| **调度/并发** | 8 合并超时、9 并发竞争、10 增量跳过、11 断点恢复 | 源码级机制理解 |
| **运维** | 7 展示上限 | 不信任前端、直查底层 |

## 这份问题清单的面试价值

1. **每个问题都有源码依据**——不是"遇到过"，是"定位到行号"
2. **覆盖 GraphRAG 全生命周期**——抽取/合并/消歧/社区/检索/更新/删除
3. **诚实区分**：哪些是 vanilla 设计、哪些是配置遗漏、哪些需二开
4. **T1/T3 测试发现的问题**（4/5/6）是别人没做过的——量化证据 + 源码根因，是差异化资产

## 来源

- [更完整的实习记录.md §15](../../docs/实习记录文档/更完整的实习记录.md)（GraphRAG 数据流）
- [解决后端问题0902-0905.md §2.4](../../docs/实习记录文档/解决后端问题0902-0905.md)（空图模型对比）
- [T1_全局GraphRAG检索对比报告.md](../../GCN_Poc/GCN_Poc/doc/design/4090_测试/T1_全局GraphRAG检索对比报告.md)
- [T3_文档更新删除图谱行为报告.md](../../GCN_Poc/GCN_Poc/doc/design/4090_测试/T3_文档更新删除图谱行为报告.md)
- [4090_PTR端到端验证_延迟基准.md](../docs/4090_PTR端到端验证_延迟基准.md)
- 源码：`ragflow-main/rag/graphrag/`（extractor.py / index.py / utils.py / search.py）
