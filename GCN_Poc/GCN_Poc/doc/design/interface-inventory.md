# 接口与数据库清单（GCN 二次开发）

> 日期：2026-08-14
> 依据：`ragflow-dev-research.md`（4 点研究计划）、`pbs-and-layering.md`（第 3 点 + 时序维度）、`architecture.md`、决策 8
> 状态：接口**分组已定**，单 endpoint 精确数量待接口规格定稿（当前估算约 15–20 个 REST endpoint）

## 一、结论先行：我们要开发 4 组对外接口

对应已和项目经理对齐的 4 个重点，每组是一个"接口域"，内含若干 endpoint：

| # | 接口域 | 对应重点 | 核心职责 | 我们新建的库 |
|---|---|---|---|---|
| 1 | **批量导入编排接口** | 第 1 点 | 批量上传的任务编排 + 状态机（暂停/恢复/重试/取消/队列读写/分阶段时间戳） | PostgreSQL |
| 2 | **GraphRAG 封装接口** | 第 2 点 | 把 RAGFlow 内部建图/状态/社区能力封装成稳定 API | 无（读 RAGFlow） |
| 3 | **PBS/分层/信息块 + 检索适配接口** | 第 3 点 | PBS 树、信息块 CRUD，以及统一检索入口（域限定 + 时序） | PostgreSQL |
| 4 | **问答路由接口** | 第 4 点 | 统一问答入口 + 路由判定（RAG / KG-local / KG-global） | 无（读 RAGFlow + PG） |

> 说明：第 3 点的"检索适配层"是第 4 点"问答路由"的数据底座——路由决定走哪条路，适配层负责把结构化条件翻译成 RAGFlow 的 tag 过滤 + KG 子图范围。

---

## 二、各组接口明细

### 组 1：批量导入编排接口（第 1 点）
新建**外置编排服务**，自己维护状态机与时间戳，再通过 RAGFlow 现有 API 驱动。

- `POST /ingest/jobs` —— 创建批量（文件清单 + KB + 选项）
- `GET /ingest/jobs/{id}` —— 总览 + 各 stage 时间线
- `POST /ingest/tasks/{id}/pause|resume|retry|cancel` —— 控制单文档任务
- `GET /ingest/queue` —— 队列状态（pending/running/failed 计数，按 KB 维度）
- `PATCH /ingest/tasks/{id}` —— 修改队列项状态/优先级

状态机（PostgreSQL）：`IngestJob → IngestTask → IngestStage`（upload/parse/chunk/embed/index/graph_build/graphrag_index），每 stage 记 `started_at / finished_at / status / retry_count / error / ragflow_progress`。

### 组 2：GraphRAG 封装接口（第 2 点）
把内核能力包成稳定 API，屏蔽 RAGFlow 内部变化。

- `POST /graphrag/{kb}/build` —— 触发建图
- `GET /graphrag/{kb}/status` —— 建图状态/进度
- `GET /graphrag/{kb}/communities` —— 社区/子图查询
- （可选）`DELETE /graphrag/{kb}` —— 清图（对应决策 3 的官方 DELETE /graph）

### 组 3：PBS/分层/信息块 + 检索适配接口（第 3 点）
- PBS 树：`GET/POST/PUT/DELETE /pbs/nodes`、`GET /pbs/nodes/{code}/ancestors|descendants`
- 信息块：`GET/POST/PUT/DELETE /information-blocks`（带 `pbs_code / knowledge_type / specialty / time_node / 版本 / 审核`）
- 检索适配层：`POST /search`（入参 `{ pbs_scope, knowledge_type, specialty, time_node, query }` → 翻译成 RAGFlow chunk tag 过滤 + KG 子图范围，回传带 `pbs_code / specialty / time_node / confidence / source`）

### 组 4：问答路由接口（第 4 点）
- `POST /qa` —— 统一问答入口（内部按路由判定走 普通RAG / KG-local / KG-global，可并行多路召回融合）
- （可选）`GET /qa/route?q=...` —— 暴露路由判定结果，便于 A/B 调参

---

## 三、数据库总览

### 我们新建 / 拥有（算法团队维护）
| 数据库 | 用途 | 存什么 |
|---|---|---|
| **PostgreSQL** | 结构化数据底座（权威） | 批量状态机（IngestJob/Task/Stage）、PBS 树（pbs_node）、信息块（information_block）、枚举字典（enum_dict）、版本/时序（time_node）属性 |

### RAGFlow 既有（甲方已部署 131，我们**不替换、只调用其 API**）
| 数据库 | 角色 | 存什么 |
|---|---|---|
| **MySQL** | RAGFlow 主关系库 | 文档/数据集/用户/图谱元数据 |
| **Elasticsearch (ES)** | 检索与索引 | chunk 向量 + BM25、社区报告（community_report）、KG 检索 |
| **Redis** | 任务队列 | 解析/建图任务（已实测：Redis Streams + 消费者组，见 `task_executor.py`） |
| **MinIO** | 对象存储 | 原始上传文件 |

> ⚠️ **数据库选型更正（决策 16，2026-08-20）**：下表及本文其余处写的 PostgreSQL **无依据**——规范书只要求「关系型数据库」，未指定产品。**编排层（组 1）已改用 MySQL**（复用 131 现有实例，独立库 `gcn_ingest`）。组 3 的 PBS/信息块若确有 PG 特性需求可独立选型，两层解耦。

### 关键边界（决策 8 → 已被决策 15 收窄，2026-08-19）
- RAGFlow 是**主平台**，当前实现只在外部加"编排/治理/适配层"。
- ⚠️ "不改动内核"是 POC 阶段策略，**不是开发阶段的硬约束**。核心目标是交付好用的系统；改与不改按收益/成本判断，见 [ragflow-modification-candidates.md](ragflow-modification-candidates.md)。
- 凡涉及**状态、版本、PBS 归属、专业维度、时序节点、来源追溯**的权威数据 → 落 **PostgreSQL**（双写：结构化入 PG，语义/向量入 RAGFlow）。
- 强图治理（实体关系/版本/时序属性）如需超出 RAGFlow 能力，候选是 **Neo4j / PostgreSQL AGE**（见 `ragflow-scale-feasibility-assessment.md`），目前**不引入**，待隔离验证。

---

## 四、数据流向（一句话）
```
用户/批处理
  → 组1 编排层(PostgreSQL 状态机) → 调 RAGFlow API(MySQL/ES/Redis/MinIO) 驱动上传/解析/建图
  → 组3 检索适配层(PostgreSQL PBS/信息块 + RAGFlow KG/chunk) 做域限定+时序过滤
  → 组4 问答路由 决定走 RAG / KG-local / KG-global，结果回带 pbs_code/专业/时序/置信度/来源
  → 组2 封装 暴露建图/状态/社区，供运维与前端调用
```
