# RAGFlow 普通 RAG 与 GraphRAG 技术附录

> 用途：解释项目经理新增技术问题，并作为 Demo 证据的技术追溯入口
> 版本：RAGFlow v0.26.1，结合 131 服务器源码归档和 PTR 实测
> 证据标记：A=官方/源码事实；B=131 实测；C=工程判断；D=待验证

## 一、先看全链路

```text
原始文档
  │
  ├─ 普通 RAG
  │    └─ 解析 → chunk → 词法文本 + 向量 → 全文/向量混合检索 → 引用 → Chat
  │
  └─ GraphRAG
       └─ chunk
          → 按 token 合并输入批次
          → LLM 抽取实体和关系
          → 文档级 subgraph
          → 合并到 dataset 全局 graph
          → Entity Resolution 实体消歧
          → PageRank
          → Leiden 社区发现
          → LLM 生成 community report
          → report 重新写入文档引擎
          → KG/local/global 上下文检索
          → Chat + 引用
```

这意味着 GraphRAG 不是“给普通 chunk 多加一个向量字段”，而是在离线构建阶段增加了多次 LLM 调用、图合并、实体消歧和社区摘要。在查询阶段，它可以把普通 chunk 与社区聚合上下文一起提供给 Chat。

## 二、普通 RAG 一条数据怎么存

### 2.1 逻辑结构

普通 RAG 的基本检索单元是 chunk。原文不会只保存成一个字符串，通常会同时保存：

- 原始或规范化后的 `content`；
- 分词后的 `content_ltks`，用于全文/词法检索；
- embedding 向量，实际可能由文档引擎的向量字段承载；
- `dataset_id`/`kb_id`；
- `document_id`；
- `document_keyword`，即来源文档名称；
- 文档类型、表格标记、位置信息和引用信息；
- `term_similarity`、`vector_similarity` 和融合后的 `similarity`。

### 2.2 PTR 实际检索样例

以下为 PTR 的一条目录 chunk 的字段抽样，字段名和数值来自 `test/results/2026-08-04/kg_retrieval_comparison.json`：

```json
{
  "content": "目录、版本、有效页\\n00.1目录\\n...",
  "content_ltks": "目录 版本 有效 页 001 目录 ...",
  "dataset_id": "4ec8cbda8cc711f19f3f45f212d2b89e",
  "document_id": "4ee267488cc711f19f3f45f212d2b89e",
  "document_keyword": "PTR冷却泵设备运行与维修手册.docx",
  "doc_type_kwd": "",
  "id": "fa479696312437c1",
  "positions": [],
  "similarity": 0.35949302993616405,
  "term_similarity": 0.18959584276594868,
  "vector_similarity": 0.7559198,
  "important_keywords": [],
  "tag_kwd": []
}
```

这里可以直接看出：

- `content` 是最终送入上下文的文本主体；
- `content_ltks` 是检索辅助字段，不是给用户看的答案；
- `vector_similarity` 和 `term_similarity` 分别体现向量和词法匹配；
- `document_id` 和 `document_keyword` 用于引用回溯；
- `dataset_id` 用于知识库过滤和权限边界；
- `positions` 为空不代表没有来源文档，只表示该条结果当前没有更细的页内位置字段。

PTR 的实际普通存储层核对为 162 个唯一 chunk。数据库中的 `chunk_count=324` 是历史累计计数，不能直接当作索引中存在 324 条不同内容。

### 2.3 普通 RAG 的检索过程

```text
用户问题
  ├─ 词法/BM25 候选
  ├─ 向量候选
  ├─ 融合排序/可选 rerank
  └─ 返回 chunk + similarity + document/source 信息
          ↓
       Chat 模型生成答案和引用
```

普通 RAG 更适合参数、条款、局部事实和明确的章节定位。它不需要为每个问题重新建图，因此通常是默认链路。

## 三、GraphRAG 数据怎么存

GraphRAG 在 RAGFlow v0.26.1 中仍使用同一类文档引擎/索引体系，但通过 `knowledge_graph_kwd` 区分图谱相关记录。当前归档和实测中确认的类型包括：

```text
entity
relation
subgraph
 graph
community_report
```

### 3.1 Entity 节点

逻辑上是一条实体节点记录，核心字段类似：

```json
{
  "entity_name": "泵",
  "entity_type": "设备",
  "description": "PTR冷却泵设备及其运行、维修相关信息",
  "source_id": ["4ee267488cc711f19f3f45f212d2b89e"],
  "pagerank": 0.023,
  "knowledge_graph_kwd": "entity",
  "kb_id": "4ec8cbda8cc711f19f3f45f212d2b89e"
}
```

说明：

- `entity_name` 是图节点名称，也是关系的端点标识；
- `entity_type` 是抽取器给出的类型，General/Light 的类型结果依赖 Prompt 和模型；
- `description` 是 LLM 根据原文生成或整理的实体描述；
- `source_id` 保存该实体来自哪些文档；
- `pagerank` 用于图中的重要性排序；
- 真实索引中还会有 embedding、词法字段和内部文档元数据，以上只列解释所需核心字段。

### 3.2 Relation 边

逻辑上是一条实体之间的关系记录：

```json
{
  "src_id": "泵盖",
  "tgt_id": "机械密封",
  "description": "泵盖带机械密封，与托架部件和叶轮配合装配",
  "source_id": ["4ee267488cc711f19f3f45f212d2b89e"],
  "knowledge_graph_kwd": "relation",
  "kb_id": "4ec8cbda8cc711f19f3f45f212d2b89e"
}
```

关系的方向、描述和来源共同决定它能否用于关系题回答。Graph API 返回时会把它转成：

```json
{
  "source": "泵盖",
  "target": "机械密封",
  "weight": 1,
  "description": "..."
}
```

### 3.3 Subgraph 文档级子图

每份文档先形成一个 NetworkX 图，再序列化为 node-link JSON 写入文档引擎。逻辑结构如下：

```json
{
  "knowledge_graph_kwd": "subgraph",
  "kb_id": "4ec8cbda8cc711f19f3f45f212d2b89e",
  "source_id": ["4ee267488cc711f19f3f45f212d2b89e"],
  "available_int": 0,
  "removed_kwd": "N",
  "content_with_weight": "{\\"directed\\":false,\\"multigraph\\":false,\\"graph\\":{},\\"nodes\\":[...],\\"edges\\":[...]}"
}
```

`content_with_weight` 不是普通文本，而是序列化后的图结构。它保存文档级节点、边和属性，供后续全局图合并使用。

### 3.4 Graph 全局图

`graph_merge(old_graph, subgraph, change)` 会把新的文档级子图合并到 dataset 级全局图，并根据图结构重新计算 PageRank。当前 PTR 后端实测：

```text
Graph API: 256 nodes / 128 edges
ES index: entity=614, relation=292, graph=1, subgraph=1
```

Graph API 的节点还包括 `entity_type`、`description`、`pagerank`、`source_id`；边包括 `source`、`target`、`weight`、`description`。

### 3.5 Community Report

社区报告不是原始文档章节，也不是人工预先划分的目录。它是对图中一个连接较紧密的实体和关系子集生成的摘要记录：

```json
{
  "docnm_kwd": "PTR冷却泵设备与运维知识网络",
  "knowledge_graph_kwd": "community_report",
  "kb_id": "4ec8cbda8cc711f19f3f45f212d2b89e",
  "source_id": ["4ee267488cc711f19f3f45f212d2b89e"],
  "entities_kwd": ["泵", "电机", "联轴器"],
  "important_kwd": [],
  "weight_flt": 0.0,
  "available_int": 0,
  "content_with_weight": "{\\"report\\":{...},\\"evidences\\":\\"...\\"}",
  "content_ltks": "PTR 冷却 泵 设备 运维 ..."
}
```

社区报告的结构化输出要求：

```json
{
  "title": "...",
  "summary": "...",
  "rating": 0.0,
  "rating_explanation": "...",
  "findings": [
    {
      "summary": "...",
      "explanation": "..."
    }
  ]
}
```

当前实现还附加 `entities`、`community_level`、`community_id` 和 `weight`。社区报告稳定 ID 应同时使用社区层级、社区 ID 和实体集合，不能只使用 LLM 生成的标题，否则重复标题可能造成覆盖。

## 四、LLM 如何抽取实体和关系

### 4.1 抽取器选择

RAGFlow GraphRAG 配置中，`parser_config.graphrag.method` 选择抽取器：

```python
method = graphrag_config.get("method", "light")
if method == "general":
    extractor = GeneralKGExt
elif method == "ner":
    extractor = NerKGExt
else:
    extractor = LightKGExt
```

本项目重点实测的是：

- `general`：GeneralKGExt，LLM 驱动的实体/关系抽取；
- `light`：LightRAG 风格的抽取方法，但图存储、KG retrieval 和 Chat 仍走 RAGFlow；
- `ner`：源码支持的另一种抽取路径，本项目没有把它作为 PTR 主结果。

### 4.2 输入不是整本书，而是 chunk 批次

GraphRAG 先读取普通解析后的 chunks，再按 `batch_chunk_token_size` 合并输入批次。归档代码中的默认值为 4096 token，允许范围为 512～8196。

```text
原文 → 解析 chunks → 按 token 合并批次 → 调用抽取器
```

抽取器返回实体和关系集合：

```python
ents, rels = await ext(doc_id, chunks, callback, task_id=task_id)
```

然后写入 NetworkX：

```python
for ent in ents:
    ent["source_id"] = [doc_id]
    subgraph.add_node(ent["entity_name"], **ent)

for rel in rels:
    rel["source_id"] = [doc_id]
    subgraph.add_edge(rel["src_id"], rel["tgt_id"], **rel)
```

### 4.3 一条抽取结果的可解释形态

项目当前归档完整保留了抽取器调用点、下游节点/边写入格式和最终 ES 结构，但没有把每个 chunk 的原始 LLM JSONL 全部作为独立文件留证。因此下面是**源码确定的下游规范格式**，不是某一次原始模型响应的逐字副本：

```json
{
  "entities": [
    {
      "entity_name": "泵盖",
      "entity_type": "部件",
      "description": "泵盖是泵体组件的一部分，与机械密封、叶轮等部件发生装配关系"
    },
    {
      "entity_name": "机械密封",
      "entity_type": "密封部件",
      "description": "用于泵盖与转动部件之间的密封"
    }
  ],
  "relationships": [
    {
      "src_id": "泵盖",
      "tgt_id": "机械密封",
      "description": "泵盖与机械密封配合完成密封装配"
    }
  ]
}
```

写入子图后，实体和关系会增加 `source_id`；合并到全局图后还可能拥有 PageRank、社区标记和其他索引字段。

因此需要区分：

- **模型原始输出**：当前缺少每个 chunk 的独立原始 JSONL；
- **源码下游对象**：实体、关系字段和写入 NetworkX 的方式已确认；
- **最终索引/Graph API**：节点、边、来源和社区字段已通过 PTR 实测。

这也是当前项目唯一比较明确的中间过程留证缺口，但不影响本次平台选型结论。

## 五、实体消歧是怎么做的

### 5.1 为什么需要消歧

不同 chunk 或不同文档可能用不同名称指向同一对象，例如：

```text
PTR泵 / PTR冷却泵 / 冷却泵
泵盖 / 泵盖部件
```

如果不处理，图中会出现重复节点，关系会被拆散，PageRank、社区和问答上下文都会失真。

### 5.2 当前源码确认的调用链

```python
er = EntityResolution(llm_bdl)
reso = await er(
    graph,
    subgraph_nodes,
    callback=callback,
    task_id=task_id,
    checkpoints=checkpoints,
    save_resolution_checkpoint=save_resolution_checkpoint,
)
graph = reso.graph
change = reso.change
```

随后系统根据 `change` 处理被移除的节点和边，并重新保存图、重新计算 PageRank。回调消息会报告类似：

```text
Graph resolution removed N nodes and M edges.
```

### 5.3 本项目能确认到什么程度

- 输入：当前全局图、新子图节点和 LLM/embedding 相关组件；
- 输出：消歧后的图和节点/边变更集合；
- 行为：合并应合并的实体，删除重复节点及相关边，保留合并后的关系和来源；
- PTR 过程证据：曾记录 51 对实体消歧候选，最终图为 256 节点、128 条边。

当前项目归档没有完整保留 `entity_resolution.py` 的实现文件，因此候选生成细节、精确相似度阈值和完整 Prompt 不能作为本项目已经确认的固定规则对外承诺。正确表述是：**RAGFlow 已有 LLM/embedding 辅助的实体消歧流程，具体阈值和候选策略需要以当前部署源码版本进一步固化。**

## 六、社区是什么，依据什么组织

### 6.1 社区的概念

社区不是原文目录，也不是人工把第 1 章、第 2 章分组。它是知识图中一组连接相对紧密的实体及其关系，目的是把大量局部事实组织成可供全局问题检索的高层摘要。

例如，PTR 图中可能形成围绕以下主题的社区：

```text
设备组成与驱动
安装对中与装配
故障特征与处理
维护与润滑
```

实际社区边界由图结构决定，不能仅凭文档章节名称推断。

### 6.2 当前实现的组织依据

源码中调用：

```python
communities = leiden.run(graph, {})
```

Leiden 根据节点和边的连接结构进行社区发现。之后系统为每个社区收集：

- 社区内实体名称和描述；
- 社区内部关系和关系描述；
- 节点度等排序信息。

这些内容被转换成 CSV 表格，注入社区报告 Prompt：

```python
prompt_variables = {
    "entity_df": ent_df.to_csv(index_label="id"),
    "relation_df": rela_df.to_csv(index_label="id")
}
```

LLM 只能基于这些真实实体和关系生成报告，结构化结果经过 JSON 解析和字段类型校验后落库。

### 6.3 PTR 社区实测

```text
Leiden 候选社区：43
最终 ES community_report：41
唯一报告 ID：41/41
来源 kb_id/source_id：正确
已知 Prompt 污染词：0
```

43 个候选社区和 41 条最终报告不矛盾：少量社区可能因为节点数不足、报告生成失败或结构化校验不通过而不落库。正式验收应看最终 ES 报告数和唯一性，不能只看日志中的候选数量。

## 七、社区报告如何进入问答

GraphRAG 的关键不是“图建出来”，而是图或社区报告真正进入问答上下文。PTR 做了显式对照：

```text
use_kg=false
  返回 4 个普通 chunk
  community_chunk_count=0
  没有 Related content in Knowledge Graph

use_kg=true
  返回 5 个 chunk
  community_chunk_count=1
  首条 document_keyword = Related content in Knowledge Graph
```

这条社区聚合块示例包含：

```text
---- Community Report ----
# PTR冷却泵设备与运维知识网络
## Content
...
## Evidences
...
```

因此当前已证明三件事：

1. 社区报告真实落库；
2. `use_kg=true` 时检索分支确实返回社区聚合内容；
3. 社区内容可以进入 Chat 上下文，并支持关系题和全局题。

## 八、一次问答能否基于多个知识库

API 和 Chat 模型层都使用列表字段：

```json
{
  "dataset_ids": ["kb_id_1", "kb_id_2"]
}
```

检索接口也支持：

```json
{
  "question": "...",
  "dataset_ids": ["kb_id_1", "kb_id_2"],
  "page_size": 5,
  "use_kg": true
}
```

因此，**接口和模型层具备多知识库问答基础**。但本项目尚未把“两个知识库同时问答”的质量、权限隔离、引用归属和同名实体冲突作为独立实测结论。生产化前应补充一个多知识库冒烟测试，至少检查：

- 两个知识库的 chunk 是否都能召回；
- 引用是否带有正确的 `dataset_id/document_id`；
- 不允许访问的知识库是否不会泄露结果；
- 同名实体在不同域是否会错误合并；
- GraphRAG 社区报告是否跨库混合且可解释。

## 九、知识图谱如何可视化

### 9.1 后端数据

后端接口：

```text
GET /api/v1/datasets/{kb_id}/graph
```

返回内容包括：

```json
{
  "nodes": [
    {
      "id": "泵盖",
      "entity_type": "部件",
      "description": "...",
      "pagerank": 0.02,
      "source_id": ["doc_id"]
    }
  ],
  "edges": [
    {
      "source": "泵盖",
      "target": "机械密封",
      "weight": 1,
      "description": "..."
    }
  ]
}
```

PTR 后端已经返回 256 个节点和 128 条边，具备前端渲染条件。

### 9.2 RAGFlow Web 展示

RAGFlow Web 可以作为现场演示入口，建议操作顺序：

1. 打开知识库，确认文档解析完成；
2. 打开 GraphRAG 配置，展示 `method=general` 或 `light`；
3. 打开知识图谱页面，展示节点、边和社区/mind map；
4. 点击节点或关系，查看实体描述和来源；
5. 打开 GraphRAG Chat，提问 Q5 关系题和 Q6 全局题；
6. 展开 `Related content in Knowledge Graph` 引用，证明社区报告进入上下文。

后端图谱和社区产物已经验收；Web 节点、边、社区展示和引用展开仍需要一次人工现场终验。该终验是演示操作验收，不是继续重建图谱的理由。

## 十、技术结论的证据边界

| 问题 | 当前结论 | 证据等级 |
|---|---|---|
| 普通 RAG 一条 chunk 的字段 | 已有实际检索 JSON 样例 | B |
| GraphRAG entity/relation/subgraph/graph/report 结构 | 源码和 ES/API 字段已确认 | A+B |
| LLM 抽取调用链 | 源码已确认；原始逐 chunk 响应未完整归档 | A，原始响应 D |
| 实体消歧存在且会修改图 | 调用链和变更对象已确认；具体阈值未固化 | A+B，细节 D |
| 社区按什么组织 | Leiden 基于图结构；报告由 LLM 生成 | A+B |
| 社区是否进入问答 | `use_kg` 对照已确认 | B |
| 多知识库问答 | API/模型层支持；质量和权限未实测 | A，实测 D |
| 知识图谱可视化 | Graph API 已验收；Web 现场操作待终验 | A+B，Web D |
| 上万份/30 万份生产容量 | 尚未同规模压测 | D |

## 十一、当前项目应收束在哪里

本附录补齐了“中间机制如何工作”的解释，但不把它扩展成新的无限实验计划。项目当前收束为：

```text
可行性评估阶段完成
  ├─ 平台选择：RAGFlow 可继续作为主平台
  ├─ Demo 能力：普通 RAG + GraphRAG 单文档闭环通过
  ├─ 性能边界：2s/5s E2E 未满足，瓶颈方向已定位
  ├─ 规模边界：万份/30 万份未验证，不能承诺
  ├─ 更新边界：删除/修订/回滚需要治理层
  ├─ 二开路线：版本治理 + 编排 + 分域图谱 + 路由 + 观测
  └─ 备选方案：KAG 观察，非当前替换方案

规模专项与生产化专项待立项
```
