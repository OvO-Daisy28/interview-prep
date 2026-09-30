# RAGFlow 二次开发重点研究计划

> 日期：2026-08-14
> 依据：项目经理 2026-08-13 沟通记录（`doc/客户/原始需求/项目经理沟通记录.md:36-41`）、`二次开发范围分析.md`、`architecture.md`、`ragflow_concepts_explained.md`、本地源码快照 `code/patches/ragflow-v0.26.1-2026-08-04/container/after/task_executor.py`
> 状态：4 点已在沟通记录中"原话登记"，本文将其升级为**可验收的研究/设计计划 + 首轮代码级发现**。
> 说明：本地 `code/patches/` 只保存了 131 服务器**实际改动**的少数文件（如 `task_executor.py` 的 before/after），**不是完整 RAGFlow 源码**。第 2 点要"摸清楚代码"需另取源码（见下）。

## 〇、项目经理对齐的 4 个重点（原话）

1. RAGFlow 的批量上传和导入文件功能，能不能支持每个阶段的时间记录、随时开始/停/重试，读取和修改队列里的状态；最好最后提供一个接口出来。
2. 详细调研 RAGFlow 内部的 GraphRAG 全流程到底怎么实现，摸清楚代码；最后最好也以接口形式。
3. 详细调研并且设计（**超关键**）：到底应该怎么分层组织？PBS 怎么组织，怎么回事儿。
4. 提升 GraphRAG 问答效果的关键是？遇到问答到底应该怎么组织路由？

## 一、统一结论（先给结论）

- 第 1、2 点本质是**在 RAGFlow 之上做外置编排/适配层 + 把内部能力封装成接口**，不是改 RAGFlow 内核（符合决策 8：先外置治理/编排，确需才改 worker）。
- 第 3 点是**知识组织模型设计**（分层 + PBS 树 + 信息块），是本项目数据底座的核心，必须先于代码定稿。
- 第 4 点是**检索/问答策略**（效果提升因子 + 路由架构），依赖第 2 点的代码理解和第 3 点的组织模型。
- 执行顺序建议：**3（建模）→ 1（编排/接口）→ 4（路由/效果）→ 2（代码级封装）**，但 2 的代码阅读可与 1 并行启动。

---

## 二、第 1 点：批量导入的任务编排与状态接口

### 2.1 当前代码事实（基于 task_executor.py 实测阅读）

| 维度 | RAGFlow 现状 | 是否满足 PM 要求 |
|---|---|---|
| 队列模型 | Redis Streams + 消费者组（`collect()` 拉取） | 黑盒，外部不可读写 |
| 进度记录 | `set_progress(task_id, prog, msg)`：单浮点 0~1 + 文本，**无分阶段时间戳** | ❌ 不满足 |
| 开始/停止 | 有 `has_canceled()` 硬取消（阶段边界轮询），**无暂停/恢复** | ❌ 部分（仅取消） |
| 重试 | 无内置重试；失败只能重新触发文档解析 | ❌ 不满足 |
| 队列状态读写 | 无对外接口；仅文档级 task 进度查询 | ❌ 不满足 |
| 阶段日志 | `PipelineOperationLogService` 仅记录 PARSE 阶段 DSL，非全阶段时间戳 | ❌ 不足 |

**结论**：4 项要求 RAGFlow 内核均不直接具备，必须建**外置编排服务**自己维护状态机与时间戳，再通过 RAGFlow 现有 API 驱动。

### 2.2 设计方案（外置编排层，新建）

- **状态机模型**（落 PostgreSQL，独立于 RAGFlow）：
  - `IngestJob`（一次批量）→ 多个 `IngestTask`（每份文档）→ 多个 `IngestStage`（upload / parse / chunk / embed / index / graph_build / graphrag_index）。
  - 每 stage 记录：`started_at`、`finished_at`、`status(pending|running|succeeded|failed|cancelled|paused)`、`retry_count`、`error`、`ragflow_progress`。
- **对外接口形态**（建议 REST，与 RAGFlow API 风格对齐）：
  - `POST /ingest/jobs` 创建批量（文件清单 + KB + 选项）
  - `GET /ingest/jobs/{id}` 总览 + 各 stage 时间线
  - `POST /ingest/tasks/{id}/pause|resume|retry|cancel` 控制
  - `GET /ingest/queue` 队列状态（pending/running/failed 计数、按 KB 维度）
  - `PATCH /ingest/tasks/{id}` 修改队列项状态/优先级
- **驱动方式**：编排层调 RAGFlow 上传/解析/建图 API，轮询 `set_progress` 并映射到本层状态机；取消经 RAGFlow 取消 API + 本层标记。
- **验收**：1/10/100 份批量导入，可随时暂停某文档、重试失败项、读出每阶段耗时、修改队列状态。

### 2.3 交付物

- 接口规格文档（请求/响应/状态机图）
- 编排层服务原型（最小可验证：单 KB 批量 + 暂停/重试/状态读出）

---

## 三、第 2 点：GraphRAG 全流程代码调研

### 3.1 已知流程（来自 architecture.md 一/六 + 部署实测）

`chunk → LLM 实体/关系抽取 → 子图(subgraph) → 合并(merge) → 实体消歧(resolution) → 社区发现(Leiden) → 社区报告(community_report) → KG retrieval 增强 → Chat`

### 3.2 代码入口（待深读）

- 部署态入口：`task_executor.py` 中 `PipelineTaskType.GRAPH_RAG` 派发（第 136 行映射 `"graphrag": GRAPH_RAG`）。
- 真正逻辑在 `rag/graphrag/`（**本地快照没有，需另取**）：`utils.py`（`get_llm_cache/set_llm_cache/chat_limiter`）、抽取/合并/社区/报告模块。
- 关键待读：实体抽取 Prompt 构造、子图合并与 `does_graph_contains`/`load_subgraph`/`merge_subgraph_attempt`（决策 3 提及的调用链）、Leiden 社区发现、社区报告 ID 稳定性（决策 9）、KG retrieval 触发条件（`parser_id=knowledge_graph` 或 `use_kg=true`）。

### 3.3 取源码方式（需确认其一）

- **方案 A（推荐，离线干净）**：克隆 RAGFlow `v0.26.1` tag 到本地只读目录，逐模块读 + grep，与 131 部署态 diff 对照。
- **方案 B**：经 `ssh_ops.py` SSH 进 131 读运行态源码（运行态准确，但需凭据与授权，且污染风险）。

### 3.4 交付物

- GraphRAG 代码流程图（模块级调用链 + 关键函数清单）
- 对外封装接口规格（如 `POST /graphrag/build`、`GET /graphrag/{kb}/status`、`GET /graphrag/{kb}/communities`）

---

## 四、第 3 点：分层组织 + PBS 设计（超关键）

### 4.1 两个独立维度

1. **知识库分层分类**（规范书 4.2.3）：RAGFlow 原生平铺，需加分类目录层——按知识类型分（设备/参数/操作/故障/部件/标准）和/或按业务域分。
2. **PBS（Plant Breakdown Structure，电厂分解结构）**：系统→子系统→设备→部件→零件 的层级树，是核电工程标准分解方式。规范书要求每个参数/故障/操作/备件都关联到 PBS 节点。**RAGFlow 完全没有 PBS 概念**（`ragflow_concepts_explained.md:73`）。

### 4.2 PBS 组织方案（首轮提案，待甲方 SNS 编码规范校准）

采用**双轨**：

- **权威树（PostgreSQL，新建）**：PBS 树 + 信息块（PBS对象 + 专业维度 + 信息类型 + 内容 + 来源 + 审核状态 + 版本）。这是结构化数据底座，支持增删改查/版本/检索。
- **图谱实体（RAGFlow KG）**："系统PBS"是 10 类实体之一，PBS 层级用"组成/从属"关系连成图，支撑跨章节/跨设备图遍历（GraphRAG 全局题）。
- **标签/元数据（RAGFlow 文档/ chunk）**：每份文档/ chunk 打 PBS 路径 + 专业维度标签，供检索适配层做 PBS 域限定查询。

三者的关联键：统一的 `pbs_code`（建议沿用甲方 SNS 编码，如系统码-设备码-部件码）。

### 4.3 关键依赖（阻塞项）

- **甲方 SNS 编码规范 + 样本**（二次开发范围分析 3.3 已标"需拿到编码规范和样本后验证"）。没有它，PBS 树只能先建"结构/占位"，编码映射待填。

### 4.4 交付物

- PBS 组织与分层模型设计文档（含 ER 草图、与 RAGFlow KB/KG 的映射、pbs_code 方案）
- 信息块数据模型（PostgreSQL 表结构草案）

---

## 五、第 4 点：GraphRAG 问答效果提升 + 路由

### 5.1 提升效果的关键因子（首轮清单）

- **抽取质量**：10 类实体 + 6 类关系领域 Prompt（决策/范围分析已定），污染词清零、稳定 ID（决策 9）。
- **社区报告质量**：Leiden 社区粒度、报告是否覆盖跨章节汇总（全局题核心）。
- **检索策略**：`use_kg` 开关、KG 聚合块选择、local vs global 路径、与向量/BM25 混合、rerank（architecture 4.3）。
- **延迟瓶颈**：当前 E2E P50=15-23s，生成残差占 86%~91%，根因在外部 LLM；本地化 vLLM 是前提（范围分析 3.2-9）。
- ** chunk/上下文组织**：引用来源、置信度、PBS/专业维度标注（二次开发范围分析 2.2）。

### 5.2 路由架构（基于 architecture 4.3 深化）

- **默认主链路**：普通 RAG（参数/条文/局部事实），不足时加 rerank。
- **关系/故障因果链** → KG local 或 Light。
- **跨文档全局归纳** → General 社区报告。
- **路由判定**：候选——(a) 规则/意图分类（查询类型标签）；(b) LLM 路由器（分类小模型）；(c) 并行多路召回 + 融合。需以固定题集 A/B 验证哪类问题走哪条路收益最大。
- **硬约束**：所有请求不默认开最重 GraphRAG 路径，否则延迟/成本失控（architecture 4.3）。

### 5.3 交付物

- 效果提升因子清单 + 优先级（含验证方式）
- 路由架构设计（判定逻辑 + 接口形状 + A/B 题集方案）

---

## 六、执行计划与待确认项

| 点 | 下一步动作 | 阻塞/待确认 |
|---|---|---|
| 1 | 写接口规格 + 编排层原型骨架 | 无 |
| 2 | 取 v0.26.1 源码（方案 A 克隆 / 方案 B SSH）后逐模块读 | **需确认取源码方式** |
| 3 | 出 PBS 组织 + 分层 + 信息块模型设计文档 | **需甲方 SNS 编码规范/样本** |
| 4 | 出效果因子清单 + 路由架构设计 | 依赖 2、3 |

**待用户确认**：
1. 第 2 点取源码用方案 A（克隆离线）还是方案 B（SSH 131）？
2. 第 3 点是否有甲方 SNS/PBS 编码规范可先用？没有则先按结构占位设计。
3. 是否同意执行顺序 3→1→4→2，或希望先并行启动第 2 点代码阅读？
