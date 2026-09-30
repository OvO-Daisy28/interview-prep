# GraphRAG 全流程原理（源码级）

> 定位：GraphRAG 故事和 QA 的前置知识。读完这份，故事 5/6 和 QA 环节⑦⑧才讲得清。
> 源码：`f:\byh\ragflow-main\rag\graphrag\`（vanilla v0.26.4）。部署版 v0.26.1 行号有 10-30 行漂移。

---

## 一、全流程总览（六阶段）

```
① chunk 合并成抽取单元（按 batch_chunk_token_size，默认 4096）
② LLM 抽实体+关系（gleaning 补抽）→ 解析 JSON → 文档子图
③ 子图合并成全局图（知识库级锁、同名实体描述追加、关系权重累加、PageRank 重算）
④ 可选：实体消歧（默认关）
⑤ 可选：Leiden 社区发现 + 社区报告（默认关）
⑥ 在线检索：query 改写 → 实体/关系/N-hop/社区报告四路召回 → 虚拟 chunk 进 prompt
```

**关键事实**：阶段④⑤默认关闭；light 模式根本不做社区发现（T1 测试实证）。全局问题依赖社区报告，没开就没优势。

---

## 二、阶段①②：抽取（extractor.py）

### 2.0 为什么用 LLM+Prompt 抽取而不是 NER？

GraphRAG 的实体抽取选 LLM+Prompt 模式，不是传统 NER。核心原因：要同时抽实体+关系，且类型要能按领域定制。

| 方法 | 抽实体 | 抽关系 | 类型灵活 | 核电适配 | 代价 |
|---|---|---|---|---|---|
| NER（BERT-NER/spaCy） | ✓ | ✗ | ✗ 固定类型（PER/ORG/LOC） | 需训练核电领域 NER 模型 | 快、便宜 |
| OpenIE | ✓ | ✓ | ✓ | 三元组质量低、噪声多 | 中速 |
| 规则匹配（正则/模板） | ✓ | ✓ | ✗ | 人工写规则覆盖不全 | 快、便宜 |
| **LLM+Prompt** | ✓ | ✓ | ✓ 换 prompt 即换类型 | 最好——prompt 写业务类型 | 慢、贵、格式不稳定 |

NER 只做序列标注（给 token 打标签），抽出来的是通用实体类型；GraphRAG 要抽"PTR冷却泵→连接→额定流量650"这种领域实体+关系，NER 做不到。LLM+Prompt 的代价是慢、贵、格式不稳定——所以才有格式遵循选型（见 GraphRAG问题与解决方式.md 深挖部分）。

### 2.1 实体类型清单决定抽什么

`DEFAULT_ENTITY_TYPES = ["organization", "person", "geo", "event", "category"]`（:46）——通用类型，不匹配核电业务（设备/参数/部件）。这就是 PBS 二开需求的根源：要换类型清单才能抽业务实体。

### 2.2 gleaning（补抽机制）

`ENTITY_EXTRACTION_MAX_GLEANINGS = 2`（:47）。每 chunk 抽完一轮，LLM 问"是否有遗漏"，补抽——提高召回但翻倍 token 成本。我实测每单元 1 次、90 万 tokens 大头在这里。

### 2.3 并发抽取

`MAX_CONCURRENT_PROCESS_AND_EXTRACT_CHUNK = 10`（:48，环境变量可配）。Semaphore 限并发——不是全串行。但 131 CPU 上 LLM 调用本身慢。

### 2.4 错误容忍

`max_errors = 3`（:138 `GRAPHRAG_MAX_ERRORS`），超阈值才整批失败。单 chunk 失败只记 warning 继续——失败隔离在抽取层就有。

### 2.5 空图根因（两条路径，源码实证）

`_entities_and_relations`（:114-129）解析 LLM 输出：
- `handle_single_entity_extraction`（:344）：要求 record 首字段是 `"entity"`、至少 4 个属性
- **entity_type 不在清单里的直接丢弃**（:122 `if ... in ent_types`）

**两条空图路径**：
1. **格式解析失败**：LLM 输出 JSON 格式漂移 → `handle_single_entity_extraction` 返回 None → 0 nodes
2. **类型被过滤**：LLM 抽了实体但 type 不在清单 → 丢弃 → 0 nodes

我实测的模型对比（GLM 成功/Flash 空图）走的是路径 1；如果换业务类型清单不改，走路径 2。

### 2.6 LLM 缓存

`get_llm_cache` / `set_llm_cache`（:79/:102）——按 (llm_name, system, history) 缓存响应，相同 chunk 不重复调用。但缓存可能被截断（:74 `_is_truncated_cache` 检查 len≤1），截断的会重新调用。

### 2.7 单次调用超时

`asyncio.wait_for(..., timeout=60*20)`（:95）——单次 LLM 调用 20 分钟超时，且**超时不重试**（:106 "timeout is not a transient error; do not retry"）。重试 3 次只针对其他异常。

---

## 三、阶段③：子图合并（index.py + utils.py graph_merge）

### 3.1 增量检查（T3 测试的源码基础）

`merge_subgraph_attempt`（:488-500）：
- `get_graph()` 读已有全局图
- **if doc_id in current_graph.graph["source_id"] → 跳过**（:490-492，"already merged, skipping retry"）
- 这就是 T3 测试"增量合并、只处理新文档子图"的源码机制

### 3.2 同名实体合并：描述追加，不替换（T3 "修改=叠加"的源码根因）

`graph_merge`（utils.py:306-336）：
```python
node = g1.nodes[node_name]
node["description"] += GRAPH_FIELD_SEP + attr["description"]  # :314 追加！
node["source_id"] += attr["source_id"]                        # :316 追加
```
**描述用 `<SEP>` 分隔追加，不替换**。所以修改文档传新版、同名实体（如"PTR COOLING PUMP"）的描述会同时包含旧值（640）和新值（650）——T3 测试"640 和 650 同时留在图里"的源码根因。

### 3.3 关系合并：权重累加

```python
edge["weight"] += attr.get("weight", 0)      # :324 累加
edge["description"] += GRAPH_FIELD_SEP + ...   # :325 追加
edge["keywords"] += attr["keywords"]           # :326 追加
edge["source_id"] += attr["source_id"]          # :328 追加
```

### 3.4 PageRank 重算

```python
for node_degree in g1.degree:
    g1.nodes[str(node_degree[0])]["rank"] = int(node_degree[1])  # :331 度数=rank
```
合并后按节点度数重算 rank——度数越高（连接越多）rank 越高，检索时优先召回。

### 3.5 知识库级锁

`RedisDistributedLock(f"graphrag_task_{kb_id}", ...)`（:471，timeout=1200s）——合并阶段加锁，防止多个 graphrag 任务同时合并同一个 KB 的图导致数据竞争。

### 3.6 阶段标记（断点恢复）

`has_phase_marker(kb_id, PHASE_RESOLUTION)` / `PHASE_COMMUNITY`（:463-464）——消歧和社区阶段完成后打 marker，下次任务跳过已完成阶段。这是断点恢复机制。

### 3.7 图谱不落 Neo4j

图序列化成特殊 chunk 写回 ES（`knowledge_graph_kwd` 区分 graph/subgraph/entity/relation/community_report）。检索链路统一，不用多维护一套图数据库。

---

## 四、阶段④：实体消歧（entity_resolution.py，默认关）

### 4.1 触发

`with_resolution=True` 开启（index.py:265 默认 True，但 phase marker 控制是否实际执行）。**注意**：light 模式可能跳过此阶段——T1 测试确认 light 不做社区，消歧行为待确认。

### 4.2 机制

- 按实体类型分组
- 字符相似度/编辑距离生成候选实体对
- 过滤数字差异明显的实体
- 候选对批量送 LLM 判断是否同一实体
- 合并同义实体/别名节点、重连关系、删重复节点
- checkpoint 保存在 Redis，支持中断恢复

---

## 五、阶段⑤：社区发现 + 报告（leiden.py + community_reports_extractor.py，默认关）

### 5.1 Leiden 社区发现

层次化 Leiden 算法，发现多层级社区（实体聚类）。

**为什么选 Leiden 不选 Louvain？**

| 维度 | Louvain | Leiden | Girvan-Newman | 谱聚类 |
|---|---|---|---|---|
| 原理 | 贪心模块度优化 | Louvain 改进+自举分区 | 边介数中心度 | 拉普拉斯矩阵特征值 |
| 社区连通性 | **不保证**（可能有孤立节点） | **保证连通** | 保证 | 保证 |
| 速度 | 快 | 稍慢 | 很慢 O(E²) | 中 |
| 层次化 | 否 | **是**（多层级） | 是 | 否 |
| 适用场景 | 大规模快速发现 | **需要可靠社区结构** | 小图研究 | 聚类数已知 |

Leiden 相对 Louvain 的核心改进是 **refinement phase（自举分区）**——Louvain 合并节点到社区后可能有节点和社区不连通（通过模块度计算间接合并），Leiden 在合并前先做局部优化保证每个社区是连通子图。GraphRAG 用层次化 Leiden 发现多层级社区（大社区里有子社区），社区报告按层级生成。

### 5.2 社区报告

- 收集社区内实体和内部关系
- 实体表+关系表送 LLM
- 生成社区摘要 + findings
- 写成 `community_report` chunk（含 report + evidences + entities_kwd + weight_flt）

### 5.3 为什么默认关

成本高（LLM 生成摘要），且依赖消歧后的干净图。light 模式根本不做——这就是 T1 全局问题 KG 无优势的根因。

---

## 六、阶段⑥：在线检索（search.py KGSearch，面试最热）

详见 [RAGFlow源码全链路调研.md 环节⑧](RAGFlow源码全链路调研.md)。这里补检索和构建的关联：

- 检索读 ES 里的 entity/relation/community_report chunk
- 打分公式 `score = sim × pagerank`（pagerank 是合并阶段算的度数）
- N-hop 扩展沿关系图遍历（关系是合并阶段累加的）
- 社区报告按 entities_kwd 匹配（社区是阶段⑤生成的）
- **没开社区报告 → 全局问题 KG 无优势**（T1 实证，源码闭环）

---

## 七、一句话原理总结（背下来）

GraphRAG 在普通 RAG chunks 之上加结构化检索层：chunk 按 token 合并成抽取单元 → LLM 按 prompt 抽实体+关系（JSON 格式，gleaning 补抽）→ 文档子图合并成全局图（同名实体描述追加、关系权重累加、PageRank 重算）→ 可选消歧+社区发现 → 检索时四路召回（实体/关系/N-hop/社区）拼成虚拟 chunk 进 prompt。关键：实体类型清单决定抽什么、LLM 格式遵循决定能不能成图、社区报告决定全局问题能力、合并是追加不是替换（修改文档旧数据残留）。

## 来源

- extractor.py:46-48（类型/gleaning/并发）、:114-129（解析+空图过滤）、:95（20min超时）
- index.py:256-518（run_graphrag_for_kb 全流程）、:488-500（增量检查）
- utils.py:306-336（graph_merge 追加机制）、:344-375（handle_single 解析）
- entity_resolution.py / leiden.py / community_reports_extractor.py（阶段④⑤）
- search.py:35-295（KGSearch 检索）
