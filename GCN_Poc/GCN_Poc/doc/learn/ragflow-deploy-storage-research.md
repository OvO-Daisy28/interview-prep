# RAGFlow 部署 / 依赖 / 存储架构 / 数据全链路调研（源码核验版）

> 调研目标：回答 4 个问题——(1) 官方推荐部署方式 (2) 依赖有哪些 (3) 存储架构 (4) 数据从上传到问答全程落在哪、形态是什么；并**代码级核验 9 个存储/数据流问题**。
> 核验基线：RAGFlow **main 分支 commit `0d198fc`**（2026-08-14 通过 gh-proxy raw 拉取源码核验，非 v0.26.1）。
> 核验源文件（均已落盘 `GCN_Poc/code/ragflow/`，gitignored）：`rag/utils/minio_conn.py`、`rag/utils/base64_image.py`、`api/db/db_models.py`、`api/db/services/{file,document,file2document}_service.py`、`rag/svr/task_executor.py`、`rag/utils/{redis_conn,es_conn}.py`、`rag/nlp/search.py`、`rag/graphrag/{entity_resolution,utils}.py`、`rag/graphrag/general/{index,community_reports_extractor}.py`。

> ⚠️ **对旧草稿的关键修正（最重要）**：旧草稿认为「chunk 文本在 MySQL(`document_chunk`)和 ES 双份存储、实体/关系存 MySQL kg 表」——**这是错的**。源码核验结论：
> 1. **MySQL 没有 chunk 表**（`db_models.py` 无 Chunk 模型）。chunk 的文本+向量+元数据**只存在 ES**；MySQL 只存 Document/File/Task 等**元数据与计数**（`Document.chunk_num`/`token_num` 是计数器，非 chunk 内容）。
> 2. **知识图谱不在 MySQL**：整图/子图/实体/关系/社区报告**全部以「特殊 chunk」形式存 ES**（`knowledge_graph_kwd` 标记类型），处理时是内存 `networkx.Graph`。
> 3. **MinIO 桶名是运行时 ID**（`parent_id` 或 `kb_id`），不是固定字面量「parent/kb/doc」。

---

## 一、官方推荐的服务器部署方式

**结论：官方唯一主推 = Docker Compose（单机/小集群），另有 Kubernetes/Helm 作为可选。**

### 标准步骤（来自 README Self-Hosting / Start up）
1. 前置条件：CPU ≥ 4 核；`vm.max_map_count ≥ 262144`（否则 ES 起不来）：`sudo sysctl -w vm.max_map_count=262144` 并写入 `/etc/sysctl.conf`。
2. 进入 `ragflow/docker`，可选切稳定 tag（README 示例 `v0.26.4`）：`git checkout v0.26.4`。
3. 改 `docker/.env`：`SVR_HTTP_PORT`、`MYSQL_PASSWORD`、`MINIO_PASSWORD`、`RAGFLOW_IMAGE`。
4. 改 `docker/service_conf.yaml.template`：后端服务连接配置（容器启动时自动注入环境变量）。
5. 启动：CPU `docker compose -f docker-compose.yml up -d`；GPU 在 `.env` 加 `DEVICE=gpu`。
6. 验证：浏览器开 `http://<机器IP>`（默认 80）；在 `service_conf.yaml.template` 的 `user_default_llm` 选 LLM 厂商填 `API_KEY`。

### 起哪些容器
`docker-compose.yml` + `docker-compose-base.yml` 拉起：`ragflow`(API+前端)、`mysql`、`es01`(ES，默认文档引擎) 或 `infinity`(可选)、`redis`、`minio`、`sandbox-executor-manager`(gVisor 沙箱，Agent/代码执行隔离)。容器间走 Docker bridge 网络 `ragflow`，`/etc/hosts` 互映射。

> 对项目的意义：131 上已是 compose 部署，最新 main 的 compose 文件即「标准答案」——二开改 `service_conf.yaml`、`docker-compose*.yml`，不要手改容器内文件。

## 二、RAGFlow 依赖清单（及各自角色）

| 组件 | 角色 | 本项目对应 |
|---|---|---|
| **MySQL 8.0.x** | 关系型**元数据**主库：用户、租户、KB、文档、文件、任务、对话、LLM 配置。**不含 chunk 内容** | RAGFlow 自带；与项目新建 PostgreSQL 双写不替换 |
| **Elasticsearch 8.x** / Infinity / OpenSearch | 文档引擎：**chunk 文本+向量+元数据** + 社区报告 + KG 实体/关系/图快照 | 131 用 ES；最新 main 默认 ES，可切 Infinity |
| **Redis**（或 Valkey） | 任务队列（**Redis Streams + 消费组**）、缓存、会话、分布式锁 | 已实测 |
| **MinIO / S3 兼容** | 对象存储：原始上传文件 + 解析抽取的图片（JPEG） | 已部署 |
| **sandbox-executor-manager** | gVisor 沙箱，隔离执行代码/工具 | 可选 |
| **DeepDoc / MinerU** | 文档解析（版面/OCR/表格/图片），内置镜像，吃 CPU/GPU | 已用 |
| **外部 LLM / Embedding** | **不内置**，配置端点（OpenAI/Ollama/vLLM…） | 走私有化 vLLM（规范书要求不出网） |

关键澄清：
- **RAGFlow 自己的结构化库是 MySQL，不是 PostgreSQL**。PostgreSQL 是项目新建「内容数据库」，与 RAGFlow 的 MySQL 双写。
- **LLM/Embedding 不在 RAGFlow 进程内**，只存配置（`tenant_llm` 表）调外部端点。
- **chunk 不在 MySQL**（见三/五），这点与旧认知不同。

## 三、存储架构（源码核验）

RAGFlow 是**多存储（polyglot persistence）**，按数据形态分库：

```
                上传文件(二进制)
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
     [ MinIO 对象存储 ]      [ MySQL 关系库 ]
     原始文件 + 解析图片        元数据/状态/配置(无chunk内容)
          │                       │
          │ 解析/向量化           │ Document计数(chunk_num/token_num)
          ▼                       ▼
     [ ES / Infinity 检索库 ]◄────┘
     chunk文本+向量+元数据 + 图快照 + 实体/关系 + 社区报告
          ▲
          │ 任务队列/缓存/锁
     [ Redis ]
```

- **MinIO（对象存储）**：只存二进制。桶名是**运行时 ID**：`file.parent_id`（文件管理器 LOCAL 源文件）或 `kb_id`（文档二进制/缩略图/chunk 图片）。无固定「parent/kb/doc」字面桶。（见 Q1）
- **MySQL（关系库）**：结构化元数据与状态。表含 `user/tenant/knowledgebase/document/file/file2document/task/dialog/conversation/...`。**无 `document_chunk`/chunk 表**；`Document.chunk_num`/`token_num`、`Knowledgebase.chunk_num` 仅是计数器。
- **ES/Infinity（检索库）**：可检索的「稠密索引」。索引按租户隔离：`ragflow_{tenant_id}`（`rag/nlp/search.py:35`）。每个 chunk 一条 doc，字段含 `content_with_weight`(文本)、`q_{DIM}_vec`(向量)、`content_ltks`(分词,BM25)、`img_id`(MinIO 图片引用)、`doc_id`/`kb_id`/`docnm_kwd`、`important_kwd`/`question_kwd`/`tag_kwd`、`page_num_int`/`position_int`、`available_int`、`source_id` 等。**图/实体/关系/社区报告也以特殊 chunk 存此**（`knowledge_graph_kwd` 区分）。
- **Redis（队列/缓存）**：Redis Streams 任务队列 + 消费组 + 未确认恢复 + 分布式锁 + LLM/embedding 缓存。

**backbone —— 四级 ID 链**：`tenant_id → kb_id → doc_id → chunk_id` 串联四大存储。

> 易错点修正：chunk 文本**只在 ES**（`content_with_weight`），MySQL 无 chunk 内容副本。备份只需保 MinIO + MySQL（不可再生），ES 可丢（重索引即可，但耗时，且换 embedding 模型须全量重建向量）。

## 四、数据全链路：从上传到问答（源码核验）

### 阶段 0 · 上传
- **落点**：二进制 → **MinIO**（桶名 = `file.parent_id` 或 `kb_id`，键 = `file.location`/`doc.location`）；元数据 → **MySQL** `file` + `document` + `file2document`（`Document.run`/`status`/`progress` 标待处理）。
- **形态**：原始字节（MinIO）；一行 File + 一行 Document + 一行 File2Document（MySQL）。

### 阶段 1 · 解析（DeepDoc / MinerU）
- **触发**：任务写入 **Redis** Stream（`task_type` 见 Q3）；`task_executor.collect()` 消费（`task_executor.py:220`）。
- **处理**：`File2DocumentService.get_storage_address` 取 (bucket, location) → `get_storage_binary` 从 MinIO 拉原文件（`task_executor.py:311-312`）→ `chunker.chunk(...)` 版面分析 + OCR + 表格 + 图片抽取。
- **落点**：抽取**图片** → `image2id` 编码 JPEG → `STORAGE_IMPL.put(bucket=kb_id, fnm=chunk_id)` 存 **MinIO**，chunk 的 `img_id="{kb_id}-{chunk_id}"`（`base64_image.py:80-82`）；**文本+结构 → chunk dict**（`content_with_weight`/`content_ltks`/`img_id`/`page_num_int`/`position_int`…）。
- **形态**：结构化文本段（带版面坐标/页码）；图片二进制（MinIO）。**MySQL 不存 chunk，也不存图片记录。**

### 阶段 2 · 向量化 + 索引
- **处理**：chunk 增强 → LLM 生成 `important_kwd`(关键词)/`question_kwd`(问题)/`metadata_obj`(元数据)/`tag_kwd`(标签)（`task_executor.py:443-644`）→ `embedding(chunks, embedding_model, ...)` 算向量，写 `q_{dim}_vec`（`task_executor.py:1601`）。
- **落点**：`insert_chunks → docStoreConn.insert` → **ES** 索引 `ragflow_{tenant_id}`（`task_executor.py:1626`，`es_conn.py:343` bulk）；MySQL 仅 `DocumentService.increment_chunk_num` 更新 `chunk_num`/`token_num` 计数（`task_executor.py:1655`），`Document.run`/`status`/`progress` → 已解析/已索引。
- **形态**：稠密向量 + 可检索文本 + 元数据（ES）。

### 阶段 3 · GraphRAG 建图（可选，独立 pipeline）
- **处理**：`run_graphrag_for_kb`（`graphrag/general/index.py:256`）→ 逐文档 `generate_subgraph`（LLM 抽实体/关系 → 内存 `nx.Graph` 子图，存 ES `knowledge_graph_kwd=subgraph`，`index.py:731-812`）→ `merge_subgraph` 合并全局图 + pagerank → `set_graph` 持久化（整图 `knowledge_graph_kwd=graph` JSON + 实体/关系 embedding chunk，`utils.py:550`）→ `resolve_entities` 实体消歧（Q7）→ `extract_community` 社区报告（Q8）。
- **落点**：**全部存 ES**（`ragflow_{tenant_id}`）：整图/子图 JSON、实体 chunk(带 embedding)、关系 chunk(带 embedding)、社区报告 chunk(无 embedding)。MySQL 仅 `Knowledgebase.graphrag_task_id`/`graphrag_task_finish_at` 记任务状态。
- **形态**：内存 `nx.Graph`（处理时）+ ES JSON 快照（持久化）+ 实体/关系/社区报告 chunk。**不是 Neo4j。**

### 阶段 4 · 问答
- **召回**：用户 query → 向量 → `Dealer.retrieval` **ES 混合检索**（向量 + BM25 + rerank，按 `kb_id` 过滤，`available_int=1`，`search.py:559`）→ TopN chunk（含 `content_with_weight` 文本 + `img_id`）；可选 **KG 检索**（实体/关系/社区报告 chunk，见 Q9）。
- **溯源**：chunk 文本直接来自 ES（非 MySQL）；文档名/页码由 `doc_id`/`docnm_kwd`/`page_num_int`/`position_int` 给出；**原图**按 `img_id` 从 **MinIO** 拉（`id2image`，`base64_image.py:103`）。
- **生成**：上下文 + query → 外部 LLM(vLLM) → 答案 + citation(chunk_id/page/position)。

**全链路数据形态**：`原始二进制(MinIO)` → `文本段+版面元数据+图片(MinIO)` → `文本+向量+元数据(ES) / 图(nx内存→ES JSON)+社区报告(ES)` → `答案+引用`。

## 五、九问代码核验（核心交付）

### Q1 · MinIO「按 parent/kb/doc 分桶」是什么意思？这些桶各是什么？

**结论：桶（bucket）名是运行时 ID，不是固定字面量。两种取值：`file.parent_id` 或 `kb_id`；无独立「doc」桶。**

- `RAGFlowMinio` 是单例（`minio_conn.py:42`），两种模式：
  - **多桶模式**（默认，未配 `MINIO.bucket`）：每个逻辑桶名 = 真实 MinIO 桶，`put` 时 `make_bucket` 自动建桶（`minio_conn.py:149-150`）。
  - **单桶模式**（配 `MINIO.bucket`）：所有对象进同一物理桶，逻辑桶名变成桶内路径前缀 `<logical_id>/<fnm>`（`use_prefix_path` 装饰器，`minio_conn.py:67-90`）。
- 桶名 = `STORAGE_IMPL.put/get(第一参)`。调用处：
  - 文档二进制/缩略图/chunk 图片：桶 = **`kb_id`**（`file_service.py:582/607/613`、`document_service.py:495/585`、`base64_image.py:80` 经 `task_executor.py:417` 传 `kb_id`）。
  - 文件管理器 LOCAL 源文件：桶 = **`file.parent_id`**（`file2document_service.py:91` `get_storage_address` 返回 `(file.parent_id, file.location)`）。
- 所以「parent」= `file.parent_id`（父文件夹 ID），「kb」= `kb_id`（知识库 ID）。**在所核调用处未见「doc」级独立桶**（本次仅核 `rag/` 下存储调用，未遍历全部 `api/`）——文档二进制与 chunk 图片都共享 `kb_id` 桶，靠 `doc.location`/`chunk_id` 作对象键区分。旧文档/认知里的「doc 分桶」可能是把「kb 桶下按 doc.location 键」误读成了桶。

### Q2 · 元数据→MySQL `file`+`document`（状态=待处理）：只存部分字段吗？一个文件在 MySQL 具体存什么？

**结论：存的是完整元数据（非「部分字段」），但绝不存 chunk 内容/二进制。一个上传文件 = `file` + `document` + `file2document` 三行。**

- `File`（`db_models.py:924`，`db_table=file`）：`id`、`parent_id`(父文件夹)、`tenant_id`、`created_by`、`name`、`location`(MinIO 键)、`size`、`type`(扩展名)、`source_type`。
- `Document`（`db_models.py:894`，`db_table=document`）：`id`、`thumbnail`、`kb_id`、`parser_id`、`pipeline_id`、`parser_config`(JSON)、`source_type`、`type`、`created_by`、`name`、`location`(MinIO 键)、`size`、`token_num`、`chunk_num`、`progress`、`progress_msg`、`process_begin_at`、`process_duration`、`suffix`、`content_hash`、`run`(1=运行/2=取消)、`status`(0=作废/1=有效)。
- `File2Document`（`db_models.py:939`）：`id`、`file_id`、`document_id`（文件↔文档映射）。
- 「状态=待处理」= `Document.run`/`status`/`progress` + `Task` 表（`db_models.py:1002`：`doc_id`/`from_page`/`to_page`/`task_type`/`progress`/`chunk_ids`…）。
- 二进制在 MinIO（桶+`location` 键），MySQL 只存 `location` 指针 + 元数据。`Document.thumbnail` 字段 help 写「base64」，但 `document_service.py:495` 用 `STORAGE_IMPL.obj_exist(doc.kb_id, doc.thumbnail)` 当 MinIO 对象键处理——实践中缩略图存 MinIO（`kb_id` 桶），help 文本滞后。
- **关键**：MySQL 没有 chunk 表，`chunk_num`/`token_num` 是计数器，不是 chunk 内容。

### Q3 · Redis 队列有多少种 `task_type`？需不需要适配？`task_executor` 是专门消费者吗？

**结论：约 13 种 task_type（`PipelineTaskType` 枚举）；Redis 用 Stream+消费组；`task_executor.collect()` 是专门消费者。适配只需加枚举+handler，队列层不用改。**

- 队列机制（`redis_conn.py`）：**Redis Streams + 消费组**。`queue_product`→`xadd`（`:404`），`queue_consumer`→`xreadgroup`（`:415`），`ack`→`xack`（`:47`），`get_unacked_iterator` 恢复未确认消息。
- `task_type` 种类（`task_executor.py:131-143` 映射 `PipelineTaskType`）：`dataflow`(PARSE)、`raptor`、`graphrag`、`mindmap`、`memory`、`wiki`(ARTIFACT)、`skill`、`structure_graph`、`structure_mindmap`、`timeline`、`session_graph`、`session_essence`、`structure` —— **约 13 种**。
- KB 级扇出类型（`_KB_FANOUT_TASK_TYPES`，`task_executor.py:148-160`）：`graphrag/raptor/mindmap/wiki/skill/structure_*` 等，其 Task 行 `doc_id` 是假哨兵，真实文档在 `task["doc_ids"]`。
- `collect()`（`task_executor.py:220`）：**专门消费者**长跑循环——先恢复 unacked，再 `queue_consumer(svr_queue_name, SVR_CONSUMER_GROUP_NAME, CONSUMER_NAME)`；`svr_queue_names = settings.get_svr_queue_names("common")`（可多队列）；按 `task_type` 分发到 `build_chunks`/`run_graphrag`/`run_dataflow`/`run_raptor_for_kb` 等 handler。
- **适配建议**：若 GCN 要自定义任务类型，加 `PipelineTaskType` 枚举 + dispatch 分支即可；Redis Stream 层（生产/消费/ack/恢复）无需改动。

### Q4 · 解析出的图片存 MinIO 后是否在 MySQL 存记录？解析文字=chunk 存关系库？表格存哪？MySQL 的 chunk 都是结构化文本段吗？

**结论：图片只在 MinIO（无 MySQL 记录，靠 ES chunk 的 `img_id` 引用）；文字 chunk 只在 ES（不在 MySQL）；表格也是 chunk 在 ES（列元数据聚合到 Document 元数据）；「MySQL 的 chunk」不存在——MySQL 无 chunk 表。**

- **图片**：`image2id`（`base64_image.py:32-82`）把 chunk 的 `image` 编码 JPEG → `STORAGE_IMPL.put(bucket=kb_id, fnm=chunk_id)` 存 MinIO → chunk 设 `img_id="{kb_id}-{chunk_id}"`。该 `img_id` 随 chunk 存 ES。**MySQL 无图片记录。**
- **文字 chunk**：`content_with_weight` + `content_ltks` + `q_{dim}_vec` + 元数据字段 → **只存 ES**（`docStoreConn.insert`，`task_executor.py:1626`）。MySQL 无 chunk 表。
- **表格**：table parser 产出的表格也成 chunk（表格内容在 `content_with_weight`，存 ES）；表格列角色/模式聚合到 Document 级元数据（`aggregate_table_doc_metadata` → `DocMetadataService.update_document_metadata`，`task_executor.py:1659-1691`）。
- **「MySQL 的 chunk 都是结构化文本段吗？」**：**前提不成立**。`db_models.py` 无 Chunk 模型；chunk(文本+向量+元数据) 全在 ES。MySQL 只有 `Document.chunk_num`/`token_num` 计数器。

### Q5 · chunk 文本+向量+元数据→ES 索引 `ragflow_{tenant_id}`；MySQL 状态→已解析/已索引。「元数据」指什么？

**结论：索引名 = `ragflow_{tenant_id}`（一租户一索引）；「元数据」指 chunk 上除文本/向量外的辅助字段（关键词/问题/标签/结构坐标/来源等），用于增强检索与溯源。**

- 索引名：`index_name(uid) = f"ragflow_{uid}"`（`search.py:35-36`，uid=tenant_id）；建索引 `create_idx(idxnm, kb_id, vector_size, parser_id)`（`task_executor.py:706`）；写入 `es.bulk`（`es_conn.py:343`）。
- chunk 文档字段：`content_with_weight`(文本)、`content_ltks`/`content_sm_ltks`(分词,BM25)、`q_{DIM}_vec`(向量)、`img_id`、`doc_id`、`kb_id`、`docnm_kwd`、`important_kwd`、`question_kwd`、`tag_kwd`、`page_num_int`、`position_int`、`available_int`、`source_id` 等。
- **「元数据」具体指**：
  - LLM 生成：`important_kwd`(关键词，rerank 时权重×5，`search.py:462`)、`question_kwd`(生成问题，权重×6)、`metadata_obj`(内置/自定义元数据)。
  - 结构/溯源：`page_num_int`、`position_int`、`docnm_kwd`、`doc_id`、`kb_id`、`source_id`、`img_id`。
  - 检索控制：`available_int`(1=默认可检索；0=graph/subgraph/community_report/toc 等隐藏)、`removed_kwd`。
- MySQL 状态：`Document.run`/`status`/`progress` → 已解析/已索引；`increment_chunk_num` 更新 `chunk_num`/`token_num`（`task_executor.py:1655`）。
- `available_int` 过滤逻辑见 `es_conn.py:204-208`：检索 `available_int=1` 时排除 `<1` 的 chunk。

### Q6 · networkx 是在内存里吗？

**结论：是。GraphRAG 全程用内存 `networkx.Graph`；持久化时序列化为 JSON 存 ES（非图数据库）。**

- 处理时：`import networkx as nx`（`entity_resolution.py:24`、`community_reports_extractor.py:17`），实体抽取/合并/消歧/社区发现/pagerank 都在内存 `nx.Graph` 上做（`index.py` `merge_subgraph`/`resolve_entities`/`extract_community`）。
- 持久化：`set_graph`（`utils.py:550`）把图序列化为 `json.dumps(nx.node_link_data(graph, edges="edges"))` 存 ES（`knowledge_graph_kwd=graph` 整图 + `subgraph` 逐文档，`utils.py:564-592`，`available_int=0`）。
- 加载：`get_graph`（`utils.py:530`）/`load_subgraph_from_store`（`index.py:209`）从 ES 读 `content_with_weight` JSON → `nx.node_link_graph(..., edges="edges")` 重建内存图。
- 即：**内存计算 + ES JSON 快照**，断点可续；不是 Neo4j/图数据库。

### Q7 · 实体消歧（entity resolution）怎么做？

**结论：字符串相似度预筛 → LLM 逐对判定 → 连通分量合并 → 重算 pagerank；增量只处理涉及变更子图节点的对。**（`rag/graphrag/entity_resolution.py`）

1. 按 `entity_type` 分组所有节点（`entity_resolution.py:95-100`）。
2. 候选对：`itertools.combinations` 同类型两两，过滤 `is_similarity(a,b)` 且 (a 或 b ∈ `subgraph_nodes` 变更集) —— **增量**（`:102-104`）。
3. `is_similarity`（`:275-289`）：
   - 数字 2-gram 差异守卫：若 2-gram 对称差含数字 → 判不相似（避免「公司1」合并「公司2」）。
   - 英文：`Levenshtein.distance ≤ min(len)/2` → 相似。
   - 非英文(中文等)：字符集 Jaccard `≥ 0.8`（短串 `>1` 重叠）。
4. 候选对分批（100/批），并发 5（信号量），**LLM 判定**「A 和 B 是否同一 {type}」→ Yes/No（`:199-243`）；支持 checkpoint 与取消。
5. Yes 的对建 `connect_graph`，`nx.connected_components` 找连通分量，每分量节点 `_merge_graph_nodes` 合并（`:166-187`）。
6. 合并后 `nx.pagerank(graph)` 重算并写到节点属性（`:190-192`）。

### Q8 · 社区报告直接存 ES？需要 embedding 吗？

**结论：存 ES（作为 `knowledge_graph_kwd=community_report` 的特殊 chunk）；但社区报告本身不做向量 embedding，靠关键词/实体匹配检索。实体/关系 chunk 才有 embedding。**

- 生成：`CommunityReportsExtractor`（`community_reports_extractor.py:40`）→ `leiden.run(graph)` 社区发现 → 每社区(≥2 实体) LLM 生成结构化报告(title/summary/findings/rating) → `add_community_info2graph` 写回图节点 → 返回 `CommunityReportsResult`（`:58-190`）。**提取器自身不落库。**
- 持久化：`extract_community`（`index.py:897`）把报告转 chunk（`:952-967`）：`content_with_weight`=JSON{report,evidences}、`content_ltks`=分词、`knowledge_graph_kwd="community_report"`、`entities_kwd`/`important_kwd`=实体、`available_int=0` → `insert_chunks_bounded` → `docStoreConn.insert` → **ES**（`:996`）；先插后删旧(`old_ids-new_ids`)保证崩溃安全。
- **embedding?** **不需要/不做**。该 chunk 字段表无 `q_{dim}_vec`；`docStoreConn.insert` 是纯 `es.bulk`，不自动算向量（`es_conn.py:343-360`）。故社区报告靠 `content_ltks`(BM25) + `entities_kwd`/`important_kwd`(实体匹配) 检索，**非向量相似**。
- 对比：实体/关系 chunk 由 `graph_node_to_chunk`（`utils.py:628-633`）用 `embd_mdl.encode` 生成向量（实体名/关系描述），**有 embedding**，可向量检索。
- `available_int=0`：默认检索(`available_int=1`)排除社区报告，仅 KG 专项检索取用。

### Q9 · KG 检索是什么？原文本片段为什么从 MinIO 拉、不能从 MySQL 拉？还是要显示原图？

**结论：KG 检索 = 在 ES 上检索图相关特殊 chunk（实体/关系/社区报告/图快照）；chunk 文本来自 ES（非 MySQL/MinIO）；「从 MinIO 拉」指的是拉 chunk 的原图（裁切的 PDF/Word 页/区域图），因为图片二进制只在 MinIO，MySQL 既无 chunk 表也无图片。**

- **KG 检索是什么**：知识图谱(实体/关系/社区报告/整图)以特殊 chunk 存 ES（`knowledge_graph_kwd` ∈ graph/subgraph/community_report + 实体/关系 chunk 带 `entity_kwd`/`from_entity_kwd`/`to_entity_kwd`）。已核事实：检索层 `get_filters`（`search.py:127`）支持按 `knowledge_graph_kwd`/`entity_kwd`/`from_entity_kwd`/`to_entity_kwd`/`removed_kwd` 过滤，即可对这些图类特殊 chunk 做条件检索。
- ⚠️ **以下为基于 ES 数据布局的推断，未核 api 检索编排层（本次只拉了 `rag/` 下源文件，未拉 `api/` 的 retrieval/graph 检索 handler）**：典型流程可能是「query 向量 → 命中实体 chunk(实体名 embedding) → 沿 `from_entity`/`to_entity` 扩展邻居关系 → 取覆盖这些实体的社区报告 → 作为图上下文与文本 chunk 一并返回」；若需全图遍历可能用 `get_graph`（`utils.py:530`，该函数建图阶段用于 resume 加载已持久化图，**检索阶段是否调用未核**）从 ES 读 JSON 重建 `nx.Graph`。要确定实际 KG 检索编排需补读 `api/` 下 retrieval/graph 相关 handler。
- **原文本片段从哪来**：chunk 的**文本**由 `retrieval` 直接从 ES `content_with_weight` 返回（`search.py:712`），**不是从 MySQL、也不是从 MinIO**。
- **为什么从 MinIO 拉**：chunk 的**原图**（解析时裁切的 PDF/Word 页/区域图）是二进制，由 `image2id` 存 MinIO（桶=`kb_id`，键=`chunk_id`），chunk 仅存 `img_id="{kb_id}-{chunk_id}"` 引用。要**显示原图**时，前端调 `id2image`（`base64_image.py:103`）解析 `img_id` → `STORAGE.get(kb_id, chunk_id)` 从 MinIO 取 JPEG。
- **为什么不能从 MySQL 拉**：(1) MySQL 无 chunk 表、无图片二进制，只有 Document/File 元数据 + `location` 指针；(2) 图片/原文件是大二进制 → 对象存储(MinIO)，不宜入关系库；(3) RAGFlow 刻意三存储分工：MinIO=二进制、ES=可检索文本+向量、MySQL=元数据。所以「从 MinIO 拉」=拉原图/原文件，**文本来自 ES**，MySQL 两样都没有。
- 原始整份文件二进制也在 MinIO（桶=`kb_id`/`parent_id`，键=`doc.location`/`file.location`），重解析或展示原文件时按 `location` 拉。

## 六、关键点（主动补充）

1. **Redis 不只是缓存**：Stream 任务队列 + 消费组 + 未确认恢复 + 分布式锁。停/重试/队列状态改造点在此。
2. **MinIO 存原文件 + 解析图片**，chunk 用 `img_id` 引用；图片不可再生（除非重解析）。
3. **chunk 只在 ES**（文本+向量+元数据），MySQL 无 chunk 副本。备份保 MinIO + MySQL（不可再生），ES 可丢重索引。
4. **恢复优先级**：MinIO → MySQL → ES → 容器。MinIO 和 MySQL 必须备份。
5. **多租户隔离内建**：ES 索引按 `tenant_id`（`ragflow_{tenant_id}`），MinIO 按 `parent_id`/`kb_id` 分桶。
6. **GraphRAG 图不在图数据库**：内存 `nx.Graph` + ES JSON 快照 + 实体/关系/社区报告 chunk。要真正图查询/路径/时序须外置（项目 architecture 已规划 Neo4j/PG-AGE 候选，那是新建系统用，与 RAGFlow 内置 KG 两回事）。
7. **换 embedding 模型 → ES 向量须全量重建**（迁移/升级隐藏成本）。
8. **对话历史在 MySQL**（`conversation` 表），非无状态。
9. **LLM/Embedding 完全外置**：RAGFlow 只存配置发请求，私有化 vLLM 是独立服务，符合「LLM 不出网」。
10. **社区报告无向量 embedding**（Q8），与实体/关系 chunk 不同；检索时注意 `available_int=0` 的过滤行为。

## 七、与项目对接关系（落地提示）

- **PostgreSQL = 项目新建内容库**，与 RAGFlow MySQL 双写不替换：RAGFlow 管检索/图谱，PostgreSQL 管结构化参数/PBS/版本/时序/审核。
- **vLLM 私有化** 是 RAGFlow 的外部 LLM，经 `service_conf.yaml` 的 `user_default_llm`/`embedding` 指向内网。
- **二开边界**：批量编排、GraphRAG 封装、PBS/分层、路由都在 RAGFlow **之外**加编排/治理/适配层，或改 `service_conf.yaml` + 少量源码；不动 MySQL/ES/MinIO 存储职责划分。自定义任务类型加 `PipelineTaskType` 枚举 + dispatch（Q3）。

## 八、核验状态（旧「待核验清单」已结案）

- [x] MinIO 桶/路径约定：桶名 = `parent_id` 或 `kb_id`（运行时 ID），非固定字面量（Q1）。
- [x] `db_models.py` 真实表结构：**无 chunk/kg 内容表**；chunk 只在 ES；图在 ES 特殊 chunk（Q2/Q4/Q6）。
- [x] ES 索引模板：`ragflow_{tenant_id}`，向量字段 `q_{DIM}_vec`，`available_int` 控检索可见性（Q5）。
- [x] Redis 队列：Stream + 消费组，约 13 种 `task_type`，`task_executor.collect()` 专门消费（Q3）。
- [x] GraphRAG 落库：整图/子图 JSON、实体/关系(embedding)、社区报告(无 embedding) 全在 ES；内存 `nx.Graph`（Q6/Q7/Q8）。
- [x] 图片/原图：解析图存 MinIO(`kb_id`/`chunk_id`)，`img_id` 引用；文本来自 ES，原图来自 MinIO，MySQL 两样都没有（Q4/Q9）。
- [ ] `docker/docker-compose*.yml` 镜像名/默认口令/端口/`DOC_ENGINE` 默认值：本次未逐条核（docker 文件已落盘可直接读，非存储/数据流问题，可后续补）。
- [ ] 与 131 v0.26.1 差异：需对照 131 实际版本，本次仅核 main。
