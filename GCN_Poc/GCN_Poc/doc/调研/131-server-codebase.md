# 131 服务器实习生代码资产调研

> 调研方式：2026-08-03 通过 JumpServer 对 `10.126.2.131` 做只读目录、进程、Git 状态和关键脚本结构检查；未修改服务器文件，未读取或复制密钥值。
> 目的：明确实习生已经做了什么、本 Demo 能复用什么、我们需要新增什么。

## 1. 结论先行

131 上不是一套单一的 LightRAG Demo，而是一组较完整的 RAG 对比与评测资产：

- SimpleRAG：FAISS Top-K baseline。
- SimpleRAG + Rerank：FAISS Top-20 + bge-reranker-v2-m3 + Top-3。
- LightRAG：hybrid、mix，以及带 rerank 的变体。
- GraphRAG-SDK：独立试验目录。
- RAGFlow：平台源码、服务和普通 RAG 评测。
- RAGAS：统一 JSONL 输出、多指标评测、延迟统计、断点/检查点和多跳问答评测。

因此我们不应从零写一套评测系统。最合适的复用方式是继承她的测试集字段、RAGFlow 调用适配、JSONL 结果格式、延迟统计和 RAGAS 评测流程，替换为核电设备手册数据，并补上“RAGFlow GraphRAG”这条她尚未验证的路径。

## 2. 服务器总体版图

### 2.1 主要目录

| 目录 | 作用 | 当前判断 |
|---|---|---|
| `/data/zwt/ragflow` | RAGFlow 源码与服务 | 平台底座，当前工作树有修改 |
| `/data/zwt/lightrag_my_bge` | LightRAG 服务、输入、图存储、缓存和日志 | 服务仍在运行；数据是法律/合同域 |
| `/data/zwt/simple_rag` | FAISS baseline 与 rerank 版本 | 可复用 baseline 结构，不复用法律数据 |
| `/data/zwt/rag_eval` | 单跳/平衡测试集、各系统运行脚本、输出、RAGAS 和延迟结果 | 可复用的统一评测骨架 |
| `/data/zwt/rag_eval_multihop` | 多跳问题集、RAGFlow/LightRAG/WeKnora 运行与评测 | 与本 Demo 的关系/全局题最接近，优先复用 |
| `/data/zwt/graphrag_sdk_test` | GraphRAG-SDK 试验 | 仅作技术参考，不是本 Demo 主线 |
| `/data/zwt/models/bge-reranker-v2-m3` | 本地 reranker | 如需强普通 RAG 基线可复用 |
| `/data/zwt/my_embedding_small` | 本地 BGE embedding 与代理 | 多套实验的依赖服务 |
| `/data/zwt/rerank_service` | 本地 rerank 服务 | 2026-07-31 起仍在运行 |

空间占用快照：`rag_eval` 约 131 MB，`rag_eval_multihop` 约 27 MB，`simple_rag` 约 804 KB，`lightrag_my_bge` 约 67 MB，`ragflow` 约 254 MB。

### 2.2 当前运行服务

2026-08-03 只读进程快照显示：

- RAGFlow API 服务正在运行。
- RAGFlow GraphRAG worker 正在运行，启动命令包含 `task_executor -t graphrag`。
- LightRAG 服务正在 `9622` 端口运行。
- 本地 embedding 和 embedding proxy 正在运行。
- 本地 rerank 服务正在运行。
- 当时有 `evaluate_ragflow_multihop_ragas.py` 评测进程仍在执行。

进程存在只证明服务在运行，不证明本次 PTR GraphRAG 已构建成功或问答链路使用了图谱。

2026-08-03 的失败快照为：`progress=-1.0`，747 个待嵌入节点在 `merge_subgraph` 两次 180 秒超时后失败，Graph API 为 0 nodes / 0 edges。2026-08-04 经模型链路、合并超时、社区 Prompt/稳定 ID 和 Chat KG 模型复用修复后，原任务已完成：`progress=1.0`、256 nodes / 128 edges、41 条有效社区报告，固定题集 7/7 API/答案级成功。前述失败只作为根因证据，不再代表当前状态。

## 3. 版本与可复现性风险

### 3.1 RAGFlow 版本漂移

本地操作文档记录的是 `v0.26.1` Docker 镜像，但服务器源码仓库实际返回：

- branch：`main`
- describe：`nightly-3-g8ff6a21af-dirty`

进一步只读核验结果：

- 宿主仓库的未提交内容只有 `docker/.env` 及一个未跟踪的备份文件，没有 GraphRAG 源码 diff。
- 实际容器镜像仍是 `infiniflow/ragflow:v0.26.1`。
- 容器内 `/ragflow/rag/llm/chat_model.py` 与宿主仓库同路径文件校验和不同。
- 容器代码明确存在两处 `[GCN_Poc]` 运行时补丁，将 `max_tokens` 默认设为 16000；该补丁未纳入宿主 Git。
- 当前数据集配置的 `merge_timeout_seconds=180`、`retry_attempts=2`，本次正是在合并 747 个节点时两次 180 秒超时。

因此，当前可复现性风险不是“宿主 GraphRAG 源码 dirty”，而是“容器内存在未版本化补丁 + 数据集超时参数不足”。修复前应先保存容器补丁 diff 和配置快照，再决定只调整数据集超时还是更换非 reasoning 模型重建。

### 3.2 环境与依赖

- 实习生主要使用 `/data/zwt/envs/rag_env`，Python 3.11 痕迹明显。
- 本地 `GCN_Poc/code` 没有 `pyproject.toml`、`uv.lock`、`.python-version`、README 或 `.env.example`。
- 本地脚本语法检查通过，但在当前受管 Python 3.13 环境运行时因缺少 `requests` 直接失败。
- 这说明本地代码尚未达到“新环境按说明即可运行”的可复现标准。

## 4. 可复用资产

### 4.1 统一测试集与结果契约

实习生脚本已形成较稳定的字段约定：

```text
user_input
response
retrieved_contexts
reference
reference_contexts
latency_seconds / answer_latency_seconds / total_latency_seconds
```

这是我们最应该复用的接口。核电 Demo 的 6 个问题也应按此契约保存，而不是只在控制台打印。

### 4.2 RAGFlow 调用适配

`/data/zwt/rag_eval/scripts/run_ragflow_50_balanced.py` 已包含：

- 通过环境变量读取 RAGFlow 地址、API Key 和 Chat ID；
- 调用 Chat completion；
- 从响应中抽取答案和引用 chunks；
- 保存完整答案、检索上下文、参考答案和耗时；
- 失败时保留错误记录。

它比本地 `run_demo.py` 更接近可验收运行器，应作为改造起点。

### 4.3 多跳与全局问题评测

`/data/zwt/rag_eval_multihop` 已具备：

- 带答案和标准上下文的多跳问题集；
- RAGFlow 运行脚本 `generate_ragflow_multihop.py`；
- 按 hop 分组统计；
- 五/六指标 RAGAS 评测；
- checkpoint、超时、重试和逐指标运行；
- 针对短参考答案的“问题感知关键事实召回率”自定义指标。

PTR Demo 的关系题和全局汇总题应优先借鉴这套结构，而非只做主观截图对比。

### 4.4 延迟统计

已有脚本会统计 mean、median、P90、P95、P99、min、max，并区分检索、重排和答案生成耗时。对于 6 题 Demo 不需要过度解读分位数，但应保留单题耗时和平均值；若扩充到 20 题以上，再使用分位数。

## 5. 不应直接复用的内容

- 法律法规与合同类数据、索引、参考答案：领域与核电设备手册不同。
- 旧的绝对路径和知识库 ID：只能作为服务器历史记录，不能硬编码到新 Demo。
- 多套 `.bak`、历史输出和临时日志：不能当作当前基线。
- LightRAG 的法律域参数与结论：不能外推到 RAGFlow GraphRAG 的核电域表现。
- SimpleRAG `rag.py` 中的占位凭据和交互式 Demo 结构：不适合作为交付代码。
- 任何明文 API Key：必须改为环境变量或受控密钥注入。

## 6. 实习生已经完成了什么

按本地报告与服务器证据，可以确认：

1. 搭建了普通 RAG、普通 RAG + rerank、LightRAG 多模式、GraphRAG-SDK、RAGFlow 等多套实验路径。
2. 构建了 50 条 balanced 法律测试集以及多跳测试集。
3. 统一保存问题、答案、检索上下文、参考答案和耗时。
4. 跑过 RAGAS 多指标评测和产品模式延迟评测。
5. 对 LightRAG cache、reranker 兼容、RAGAS 指标语义和多跳短答案评测做了较深入排查。
6. 在 RAGFlow 普通检索配置上跑过法律域对比，但本地报告明确写明当时没有开启知识图谱。

不能确认：

- 她是否为 PTR 冷却泵文档编写或运行过核电域评测；
- 当前 PTR GraphRAG 是否已产生有效关系和社区；
- 当前 RAGFlow 服务使用的具体补丁和配置；
- `rag_eval_multihop` 当前运行任务的最终结果与用途；
- 哪些脚本是她认可的主线，哪些是历史探索残留。

## 7. 我们应该在她的基础上做什么

### 7.1 直接复用

- 测试集与结果 JSONL 字段契约。
- RAGFlow Chat API 的答案/引用提取逻辑。
- checkpoint、错误记录、超时和重试模式。
- RAGAS 和延迟统计脚本的结构。
- 多跳问题的分级方法和参考上下文设计。

### 7.2 新增或改造

1. 建立 PTR 冷却泵 6 题最小金标集：问题类型、问题、参考答案、关键事实、来源章节、是否要求跨章节。
2. 为同一问题分别运行普通 RAG Chat ID 和 GraphRAG Chat ID，输出同一契约的两份 JSONL。
3. 增加图谱健康检查：nodes、edges、community、实体类型、关系样例；健康检查失败时禁止继续宣称 GraphRAG 对比有效。
4. 增加配置快照：RAGFlow commit/镜像、KB parser_config、检索参数、LLM/embedding/reranker、运行时间。
5. 增加最小人工评分，而不是直接把 6 题交给 RAGAS：事实正确、完整、来源正确、跨章节覆盖、幻觉。
6. 在结果确有差异后再运行 RAGAS，避免把评测成本花在无效图谱或错误配置上。
7. 生成可复用的对比表与截图清单，支撑项目经理内部预演。

### 7.3 不做

- 不重写实习生已有的通用 RAGAS 框架。
- 不把 LightRAG 改造成主交付平台，除非 RAGFlow 明确不满足且项目经理要求替代方案。
- 不在 131 上直接整理或删除历史目录。
- 不把本次 6 题 Demo 伪装成 30 万文档规模的系统验收。

## 8. 面向项目经理的规模、效率与增量判断

### 8.1 当前能证明什么

- 普通 RAG 单份 PTR 文档已经完成解析和索引，现有规模为 162 chunks。
- GraphRAG 修复前抽取阶段产生 747 个待嵌入节点，并在两次 180 秒合并超时后失败；该历史失败用于定位根因。
- 修复后真实终态为 `progress=1.0`、256 nodes / 128 edges；ES 中有 41 条有效社区报告、41 个唯一 ID、来源正确、污染词为 0。
- 显式 `use_kg=true` retrieval 和 `demo_graph_v4` 均返回 KG 聚合块；固定题集 7/7 API/答案级成功，Q5/Q6 有效，P1 仍有长答案截断。
- 已有法律域评测中，RAGFlow 使用普通 RAG 配置且没有开启知识图谱；这些数据不能外推到 PTR GraphRAG。

### 8.2 百份至上万份文档的工程外推

| 规模 | 普通 RAG 判断 | GraphRAG 判断 | 今天的证据状态 |
|---:|---|---|---|
| 1 份 | 普通 RAG 与 GraphRAG 已真实跑通 | 256 nodes / 128 edges / 41 条有效社区报告 | B：131 实测 |
| 10 份 | 可通过批量异步解析验证 | 需要验证跨文件子图合并和失败隔离 | D：待测 |
| 100 份 | 原生链路原则上可规划；要观察索引、内存和队列 | 不建议直接合成一张大图，优先按设备/主题分域 | A+C：官方事实+工程外推 |
| 1,000 份 | 需要容量、并发和存储压测 | 需要分批、分域、外部图存储或定开编排 | C+D：外推+待测 |
| 10,000 份 | 不能由单文档 Demo 承诺；需容量规划和分层知识库 | 原生单数据集统一图风险高，需定开和专项压测 | C+D |
| 300,000+ 份 | 采购背景规模，不是本次 Demo 验收 | 必须单独设计数据湖/治理库/分域图谱和离线任务体系 | A：需求事实；D：未测 |

普通 RAG 的查询时间不应简单按文档数线性增长，因为倒排和向量索引会承担候选定位；但索引规模增长会增加内存、缓存、磁盘 I/O 和并发排队压力，P95/P99 可能显著变差。GraphRAG 还增加实体关系上下文、社区摘要和更大的 LLM prompt，查询成本和离线构建成本对规模更敏感。这些是架构层判断，不是 131 同规模基准。

### 8.3 增量更新边界

官方 RAGFlow 文档说明：新文件开始解析时，数据集级知识图谱会自动更新；删除相关文件不会自动更新图谱，必须重新生成。因此应区分：

- **新增文档**：原生可触发，但需要等待抽取、合并、消歧和社区任务完成；本次需将合并超时从 180 秒提高到 900 秒才完成，说明“可触发”不等于“快速稳定完成”。
- **删除文档**：原生 GraphRAG 不提供即时、精确的图谱清理闭环，需重生成。
- **文档修订**：生产上应创建新版本并保留旧版本、来源和生效时间；图谱层需重新处理受影响子图和社区。
- **版本/时序/影响范围**：采购需求明确要求，但当前 RAGFlow 原生证据不足，需要外置治理库和任务编排层。

### 8.4 RAGFlow 二次开发可行性

RAGFlow 官方仓库是 Apache-2.0 开源项目，包含前端、API、RAG、GraphRAG、文档解析、Python SDK、Docker 和 Helm 资产。可定开模块包括：

1. 导入编排：批量、断点、重试、限流和失败隔离。
2. GraphRAG 任务：增量子图、删除后重建、实体消歧、受影响社区重算和健康检查。
3. 治理数据：文档/设备/版本/生效时间/来源 ID、审核、回滚和影响范围。
4. 检索适配：普通向量/BM25 与图局部/全局检索融合，统一引用、置信度和时序过滤。
5. 展示与观测：图谱筛选、来源回溯、任务状态、P50/P95、token、队列和存储监控。

优先外置适配和编排，再按证据修改 RAGFlow worker/检索内核；不要直接把 131 容器内运行时补丁当作正式版本。

### 8.5 可复用开源方案

- Microsoft GraphRAG：global/local/DRIFT 查询、Leiden 社区、社区报告和增量 update 设计参考。
- LightRAG：local/global/hybrid/mix 查询、增量插入、按文档删除、Neo4j/PostgreSQL/AGE 等图存储、GraphML 可视化和 `source_id` 溯源字段。131 已有其法律域代码，但不能直接外推核电效果。
- Neo4j/PostgreSQL AGE：外置图存储候选，用于实体关系、版本和来源属性治理。
- RAGAS/JSONL：131 已有评测契约、checkpoint、延迟和质量指标脚本，应作为本项目结果格式基础。

开源组件具备能力不等于已完成 RAGFlow 集成；是否采用必须经过接口、性能、许可证和部署边界评审。

## 9. 下一轮服务器调研清单

下列动作仍应保持只读，除非单独批准：

1. 保存容器内 `[GCN_Poc]` 补丁与宿主 Git/镜像版本信息。
2. 保存 PTR 普通库/GraphRAG 库 parser_config、图谱进度、超时参数和任务日志快照。
3. 若获得隔离实验授权，执行 1/10/100 份阶梯导入，记录构建成功率、耗时、节点/边/社区、资源和查询 P50/P95。
4. 重点验证新增文件后图谱是否自动更新，以及删除文件后是否必须重生成。
5. 核实 `rag_eval_multihop` 当前进程的任务来源、完成状态和最终产物。
6. 和实习生确认她认可的主线脚本、环境启动方式、已知不可复用部分。

涉及 `DELETE /graph`、重启 worker/容器、重新解析、重跑图谱等动作会改变服务器状态，必须在只读证据核对完后单独确认。
