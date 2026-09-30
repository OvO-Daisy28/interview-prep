# 批量导入编排接口设计（第 1 点，组 1）

> 日期：2026-08-18（重写，吸收 PM 原型 + 官方 HTTP API 参考后修正 4 处错误假设）
> 定位：本项目「要长成什么样」的现在时蓝图，随实现持续更新。对接 [interface-inventory.md](interface-inventory.md) 组 1。
> 依据：
> - 官方 API：[ragflow_http_api_reference.md](../learn/ragflow_http_api_reference.md)（v0.26.1，8623 行 SSOT）
> - PM 原型：`doc/原型/POC/js/mock-data.js` + `docs/superpowers/specs/2026-08-10-doc-import-redesign.md`（5 态 + 5 子步骤业务口径）
> - POC 实证：[ragflow_operations.md](../learn/ragflow_operations.md) + `code/ragflow_client.py`
> - 源码：`code/ragflow`（本地稀疏检出 v0.26.1，db_models/task_executor/redis_conn）
> 状态：首轮设计，待用户审批后进开发。

## 一、结论先行

开发**外置编排服务**：在 RAGFlow 之上维护一套自己的状态与编排（MySQL，见[决策 16](../../memory/decisions.md)），通过 RAGFlow HTTP API 驱动上传/解析/建图，轮询 RAGFlow 进度映射回本层。

> **范围说明（决策 15，2026-08-19 修正）**：当前实现走"不改 RAGFlow 内核"路线，这是**起步选择而非硬约束**——先用现有 API 跑通、拿到真实数据，再按收益/成本决定哪些该二开。
> **核心目标是交付好用、鲁棒、符合业界规范的批量上传能力，RAGFlow 是手段不是约束。** 现有 API 满足不了的地方（进度只有单浮点、无真暂停、无自动重试、embedding 慢），二开候选与优先级见 [ragflow-modification-candidates.md](ragflow-modification-candidates.md)，由 M2 实测数据驱动决策。
> 早期[决策 8](../../memory/decisions.md) 的"不改内核"是 POC 阶段策略，已被决策 15 收窄，不再作为设计前提。

**解析路径定：/chunks（内置 chunking pipeline）**。理由见 §二验证。/ingest 路径不适配本项目（GraphRAG），作为演进项保留接口抽象。

四项需求（用户确认全做）与实现：

| 用户需求 | 实现方式 | RAGFlow 原生支持度 |
|---|---|---|
| 每阶段时间记录 | 编排层记录 API 调用边界 + 轮询 progress 映射 5 子步骤 | 部分（progress 单浮点，子步骤靠映射） |
| 读取队列状态 | 透传 `GET /documents?run=` + 编排层聚合 | 完全支持（原生 run 过滤） |
| 修改队列状态/优先级 | `DELETE /chunks` 取消 + 编排层优先级调度 | 取消原生支持；优先级编排层侧 |
| 提供统一对外接口 | 一套 REST（/ingest/jobs 等）屏蔽 RAGFlow 内部 | 编排层自建 |
| 大批量数据 | 编排层并发限流 + 阶梯压测（决策10） | 单 worker 瓶颈；提速需二开（候选 C2 embedding/多worker） |
| 随时暂停/重启/重试 | 暂停=停提交后续 + 取消当前；重试=删旧重 POST | 取消原生；暂停/重试编排层组合 |
| 灵活性（PM 状态可变） | 状态映射配置层 + pipeline 适配层，换状态/换 pipeline 改映射不改接口 | 编排层自建 |

## 二、解析路径验证结论（为什么走 /chunks）

RAGFlow v0.26.1 有**两条互斥的解析路径**（[api_reference](../learn/ragflow_http_api_reference.md) line 513/555/623-628/1960/2018）：

| 路径 | 建 KB 时配置 | 启动/控制 API | GraphRAG | PTR 适配 |
|---|---|---|---|---|
| **内置 chunking** | `chunk_method`（naive/qa/book/.../knowledge_graph）+ `parser_config` | `POST /datasets/{kb}/chunks` 启动 / `DELETE .../chunks` 停止 | ✓（`parser_config.graphrag` 或 `chunk_method=knowledge_graph`） | ✓ PTR 现状（naive+graphrag） |
| **ingestion pipeline** | `parse_type` + `pipeline_id`（**禁带 parser_config**） | `POST /documents/ingest`（run=1/2, delete=true） | 未知（pipeline 禁 parser_config，GraphRAG 配置无处放，HTTP 文档不答） | ✗ PTR 不满足前置 |

**结论**：
1. GraphRAG 属内置 `chunk_method` 路径（operations.md 实证 PTR = naive + `parser_config.graphrag.use_graphrag=true`）。
2. /ingest 只对可视化 pipeline KB，且其能否含 GraphRAG 未确认；PTR KB 不满足前置。
3. **PTR 用 /chunks**——已 POC 实证，GraphRAG 可用，取消有原生 `DELETE /chunks`。
4. /ingest 作演进项：编排层接口设计成 pipeline 类型无关（§八统一接口层），后续若 ingestion pipeline 确认支持 GraphRAG 且大批量暴露痛点，迁 /ingest 只改适配层不改接口——这就是灵活性。

## 三、RAGFlow 内核与 API 事实（实证）

### 3.1 文档 run 状态 = PM 要的 5 态（完全对齐，无需重造）

[api_reference](../learn/ragflow_http_api_reference.md) line 1791-1798：

| RAGFlow run | PM 原型状态 | 编排层映射 |
|---|---|---|
| `UNSTART(0)` | 排队 | pending |
| `RUNNING(1)` | 进行中 | running |
| `CANCEL(2)` | 停止 | cancelled |
| `DONE(3)` | 完成 | succeeded |
| `FAIL(4)` | 失败 | failed |

编排层状态机**直接对齐 RAGFlow 原生 5 态**。`GET /documents` 支持按 `run` 过滤（line 1788）+ `metadata_condition`（line 1800，PBS 标签过滤）——队列查询和域过滤原生支持。

### 3.2 已实证 HTTP API（编排层调用）

| 操作 | endpoint | 请求体 | 用途 |
|---|---|---|---|
| 批量上传（多文件） | `POST /api/v1/datasets/{kb}/documents` | multipart，多 `file` 字段；`type=local/web/empty` | upload |
| 查文档列表/状态 | `GET /api/v1/datasets/{kb}/documents?run=&id=&suffix=` | - | 轮询 + 队列读 |
| 启动解析 | `POST /api/v1/datasets/{kb}/chunks` | `{"document_ids":[...]}` | parse 启动 |
| **停止解析** | `DELETE /api/v1/datasets/{kb}/chunks` | `{"document_ids":[...]}` | 取消（原生，非 SSH） |
| 查/改 KB 配置 | `GET/PUT /api/v1/datasets/{kb}` | parser_config | graphrag 配置 |
| 触发建图 | `POST /api/v1/datasets/{kb}/index?type=graph` | `{}` | graph_build |
| 查建图进度 | `GET /api/v1/datasets/{kb}/index?type=graph` | - | 轮询 |
| 删图（重试前置） | `DELETE /api/v1/datasets/{kb}/graph` | - | 决策3 |

**修正之前的错误**：取消有原生 `DELETE /chunks`（line 2078），不是"无 cancel endpoint 要 SSH"。重试=删旧 chunks + 重 POST /chunks（或靠 content_hash 变更检测，待实测）。

### 3.3 数据模型（源码 `api/db/db_models.py`）

- Document：`run`(0-4) / `progress`(浮点0~1，单值) / `progress_msg`(文本，子阶段线索) / `process_begin_at` / `process_duration` / `chunk_num` / `content_hash`(变更检测)
- Task：`doc_id`/`from_page`/`to_page`/`priority`(内核字段，当前实现不动它) / `retry_count`(字段在，task_executor 无自动重试消费逻辑——二开候选 C4，当前编排层自记)

### 3.4 task_executor 内核（源码 `rag/svr/task_executor.py`）

- `set_progress`：写 Document.progress/progress_msg，轮询 `has_canceled`
- `has_canceled`：读 Redis 取消标志，**阶段边界轮询**（非即时中断）
- **无暂停/恢复**：只有取消；**无自动重试**：失败即 failed
- Redis Streams + 消费者组（`queue_consumer`/`queue_info`/`requeue_msg`，源码 `rag/utils/redis_conn.py`）

## 四、PM 原型口径（必须对齐，不自造）

来自 `doc/原型/POC/js/mock-data.js` + `docs/superpowers/specs/2026-08-10-doc-import-redesign.md`（PM 已批准）：

### 4.1 文档 5 态（§3.1 已对齐）
完成 / 进行中 / 排队 / 失败 / 停止。

### 4.2 5 子步骤（固定顺序，编排层必须映射出这 5 步）
```
OCR识别 → 结构化 → Embedding → 实体关系 → LLM抽取
```
每步字段：`status`(done/running/queued/failed/pending) / `progress`(0-100) / `duration`。

**映射难点**：RAGFlow 只给文档级单浮点 progress + progress_msg 文本，不给 5 步独立进度。映射规则（经验，待 M1 实测校准）：
- OCR：扫描件走 OCR（progress_msg 含 "OCR"）；Word/Excel 直接结构化，OCR 步 done/duration=—
- 结构化：progress_msg 含 "chunk"/"parsing"
- Embedding：progress_msg 含 "embedding"，progress ~0.3-0.8
- 实体关系/LLM抽取：GraphRAG 阶段，progress_msg 含 "entity"/"extract"
- 映射是**经验值非精确**（§九待验证项），但满足 PM"可见每步状态/进度/耗时"的诉求

### 4.3 文档整体 status 派生
全 done→完成；任一 running→进行中；任一 failed→失败；全 queued→排队；含 stopped 无 running→停止（原型 spec §③）。

## 五、状态机模型

### 5.1 三级层级
```
IngestJob（一次批量）
  └─ IngestTask（每份文档，独立状态机，失败隔离）
      └─ IngestStep（5 子步骤，映射自 RAGFlow progress）
```

### 5.2 Task 状态机（对齐 RAGFlow run 5 态）
```
pending(排队/UNSTART) → running(进行中/RUNNING) → succeeded(完成/DONE)
                            ↘ failed(失败/FAIL) →[retry]→ pending
                            ↘ cancelled(停止/CANCEL)
                  [paused: 停提交后续 step，当前 RAGFlow 任务跑完或取消]
```

### 5.3 暂停/重试/取消的真实语义（/chunks 路径）

**暂停 pause**（行业惯例 graceful default + force）：
- 编排层停止为该 task 提交后续 step
- RAGFlow 无原生暂停，当前正在跑的 parse 不可即时中断，故分两式：
  - **软暂停（默认，graceful）**：不调 DELETE /chunks，等当前 RAGFlow task 跑完（progress=1.0 或 fail）后停在边界，resume 从下一 step。不浪费已跑进度（GraphRAG 建图 21 分钟跑到 90% 不作废），不产生半截脏状态（坑#4/#5）。代价：暂停延迟=当前并发文档跑完的时间。
  - **硬停（force=true 或 cancel）**：调 `DELETE /chunks` 立即取消当前 parse，resume 重跑。用于资源紧急/任务卡死。代价：当前进度作废 + 可能半截 chunks 需清理。
- 选默认软的理由：①行业惯例（Airflow/Celery/K8s 都 graceful default + force）②RAGFlow task 是原子单元，半截状态脏③GraphRAG 建图极贵硬停重跑浪费巨大。
- 难裁决一律按行业常见做法。

**重试 retry**：
- 普通 parse 失败：删旧 chunks（若有）+ 重 POST /chunks
- GraphRAG 失败：必须先 `DELETE /graph`（决策3，否则 "already merged" 跳过）+ 重 POST /index?type=graph
- retry_count 编排层自记
- 默认人工触发；可选"自动重试 N 次带退避"

**取消 cancel**：
- 编排层 task 标 cancelled + 调 `DELETE /chunks` 取消 RAGFlow 侧 parse（原生 API）
- GraphRAG 取消：调 DELETE /graph 清理（决策3）
- 不再涉及 SSH（修正之前错误假设）

**队列读取**：`GET /documents?run=...` 透传 + 编排层按 job/KB 聚合计数。

**优先级**：编排层 task.priority 字段，控制调度器提交顺序。当前不动 RAGFlow 内核的 `Task.priority`——因为提交顺序在编排层控制即可达到目的，不是因为不能改。

## 六、并发控制与失败隔离

- **单 worker 瓶颈**：RAGFlow task_executor 默认单 worker，GraphRAG 需另起 `-t graphrag`（坑#1）。编排层批量提交**必须限流**，否则 Redis 队列堆积 + OOM（Docker daemon 曾被 OOM 停，决策10）。并发上限可配（默认 3），按 1/10/100 阶梯压测标定。
  > 限流是**迁就当前部署形态**的措施，不是终局。M1 实测单份 embedding 占 60%+ 耗时且 131 无 GPU——提升吞吐的正解是二开候选 C2（GPU/多 worker/换 embedding 服务），限流只保证不压垮。
- **失败隔离**：每文档一 IngestTask 独立状态机，单份失败不影响其他文档（PM 原型"单份失败不影响批量 §72"）。
- **GraphRAG 特殊性**：单份 PTR 建图 1255s + merge 超时风险（坑#8，merge_timeout=900）。graph_build step 设长超时 + 失败可重试（先 DELETE /graph）。

## 七、对外接口契约（统一 REST，pipeline 类型无关）

前缀 `/ingest`。设计成**编排层接口不暴露 RAGFlow 内部 pipeline 类型**——换 /chunks↔/ingest 只改适配层（§八）。

### 7.1 Job
- `POST /ingest/jobs`：创建批量
  - 请求：`{ kb_id, files: [{name, path_or_url}], options: {build_graph: bool, parser_config?}, priority? }`
  - 响应：`{ job_id, tasks: [{task_id, doc_name}] }`
  - 行为：建 job + 每 file 一 task(pending)，不立即上传
- `GET /ingest/jobs/{id}`：总览 + 各 task 各 step 时间线
  - 响应：`{ job_id, kb_id, status, stats: {pending,running,failed,succeeded,cancelled}, tasks: [{task_id, doc_name, status, steps: [{name, status, started_at, finished_at, progress, duration, error}]}] }`

### 7.2 Task 控制
- `POST /ingest/tasks/{id}/pause`：暂停（默认硬暂停=DELETE /chunks，可选软暂停）
- `POST /ingest/tasks/{id}/resume`：从边界继续
- `POST /ingest/tasks/{id}/retry`：从 failed step 重试（GraphRAG 自动 DELETE /graph）
- `POST /ingest/tasks/{id}/cancel`：取消 + DELETE /chunks（+ GraphRAG 时 DELETE /graph）
- `PATCH /ingest/tasks/{id}`：改 status / priority

### 7.3 队列
- `GET /ingest/queue?kb_id=&job_id=&status=`：队列状态
  - 响应：`{ counts: {pending,running,failed,cancelled}, by_kb: {...}, tasks: [...] }`

## 八、灵活性设计（用户硬需求：PM 状态可变，编排层能适应）

三层抽象，状态/流程变化改配置不改接口：

1. **统一接口层**（§七）：对外只暴露 job/task/queue 语义，不暴露 RAGFlow pipeline 类型。换 /chunks↔/ingest 只改适配层。
2. **状态映射层**（配置化）：RAGFlow run ↔ PM 5 态 ↔ 编排层状态的映射表放配置/DB。PM 加状态或改口径，改映射表不改代码。映射规则（§4.2 progress_msg → 5 子步骤）也外置配置。
3. **pipeline 适配层**：封装 RAGFlow API 调用（upload/parse_start/parse_stop/graph_build 等），当前实现 /chunks 版本；后续迁 /ingest 只替换此层实现，上层接口与状态机不动。

> 这三层直接满足用户"灵活性"诉求：PM 状态变→改映射表；换解析路径→换适配层；对外接口契约稳定。

## 九、MySQL 表结构（编排层自有，与 RAGFlow 隔离）

> **选型依据（决策 16）**：规范书 p12/p17 只要求「关系型数据库」，全文无任何数据库产品名。此前文档写的 PostgreSQL 是我们自己继承来的、无依据。改用 131 已部署的 **MySQL 8.0.39**，建独立库 `gcn_ingest`，不混入 RAGFlow 的 `rag_flow`。DDL 见 `code/ingest/schema.sql`，已在 131 实测建表 + 验证外键级联/唯一约束/中文/JSON/调度索引。

```sql
CREATE TABLE ingest_job (
    id          BIGSERIAL PRIMARY KEY,
    kb_id       VARCHAR(32) NOT NULL,
    options     JSONB NOT NULL,
    status      VARCHAR(16) NOT NULL,    -- pending/running/succeeded/failed/partial/cancelled
    priority    INT DEFAULT 0,
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_job_status ON ingest_job(status);

CREATE TABLE ingest_task (
    id              BIGSERIAL PRIMARY KEY,
    job_id          BIGINT NOT NULL REFERENCES ingest_job(id),
    doc_name        VARCHAR(255) NOT NULL,
    doc_path_or_url TEXT NOT NULL,
    ragflow_doc_id  VARCHAR(32),            -- 上传后回填
    status          VARCHAR(16) NOT NULL,    -- pending/running/succeeded/failed/cancelled/paused
    priority        INT DEFAULT 0,
    retry_count     INT DEFAULT 0,
    current_step    VARCHAR(16),            -- ocr/struct/embed/entity/llm 或 graph_build
    error           TEXT,
    created_at      TIMESTAMP DEFAULT now(),
    updated_at      TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_task_status ON ingest_task(status);
CREATE INDEX idx_task_priority ON ingest_task(priority);

-- 5 子步骤 + graph_build 时间线
CREATE TABLE ingest_step (
    id                BIGSERIAL PRIMARY KEY,
    task_id           BIGINT NOT NULL REFERENCES ingest_task(id),
    step_name         VARCHAR(16) NOT NULL,    -- ocr/struct/embed/entity/llm/graph_build
    status            VARCHAR(16) NOT NULL,    -- pending/running/queued/failed/done/cancelled
    started_at        TIMESTAMP,
    finished_at       TIMESTAMP,
    progress          INT,                     -- 0-100（映射自 RAGFlow progress）
    duration_ms       INT,
    ragflow_progress  FLOAT,                   -- 原始 RAGFlow progress（映射线索）
    ragflow_progress_msg TEXT,                  -- progress_msg（映射线索）
    retry_count       INT DEFAULT 0,
    error             TEXT,
    created_at        TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_step_task ON ingest_step(task_id);
CREATE UNIQUE INDEX idx_step_task_name ON ingest_step(task_id, step_name);
```

> PBS/信息块表见 [pbs-and-layering.md](pbs-and-layering.md)。编排层 PG 与 RAGFlow MySQL/ES/Redis 当前仅通过 HTTP API 交互；若实测证明直读 Redis 队列水位/DB 状态收益显著，按决策 15 评估（二开候选 C5/C6）。

## 十、待验证项（不阻塞设计，阻塞精确实现）

1. **5 子步骤映射精度**：progress_msg 实际文本规律待 M1 实测校准（§4.2）。
2. **重跑幂等**：同内容文档重 POST /chunks，content_hash 是否跳过/重复 chunk？影响重试。需 1 份实测。
3. **DELETE /chunks 语义**：停止后已生成的 chunks 保留还是清空？影响 resume 语义。需实测。
4. **并发容量**：131 task_executor 实际并发 parse 上限。需 1/10/100 阶梯压测（决策10）；结果直接决定二开候选 C2 的优先级。
5. **/ingest 演进**：ingestion pipeline 是否支持 GraphRAG（HTTP 文档不答，需 UI/源码深挖）。非阻塞，作演进项。

## 十一、验收标准（里程碑，前置）

- **M1 单文档全链路**：1 份文档，POST /ingest/jobs → upload → 5 step 映射 → (graph_build) → succeeded，GET /jobs/{id} 返回含 5 step 时间戳的状态线。5 子步骤映射规则校准。
- **M2 批量与失败隔离**：10 份，1 份 parse 失败，其余 9 份不受影响；失败项 retry 成功。
- **M3 暂停/恢复/取消**：进行中 pause→当前处理完→resume 继续→cancel 丢弃（默认硬暂停=DELETE /chunks）。
- **M4 队列与优先级**：GET /ingest/queue 正确计数；PATCH 改优先级后高优先级先调度。
- **M5 GraphRAG 重试闭环**：graph_build failed→retry 自动 DELETE /graph→POST /index→succeeded（决策3）。
- **M6 灵活性验证**：改状态映射配置，PM 加一态或改口径，编排层接口与状态机不动即生效。

## 十二、执行顺序（开发）

1. PG 表结构 + 状态机迁移逻辑（不接 RAGFlow，纯逻辑自测）
2. pipeline 适配层 /chunks 版本（upload/parse_start/parse_stop + 轮询）
3. 5 子步骤映射层（配置化，M1 校准）
4. M1 单文档全链路
5. task 控制 pause/resume/cancel/retry（M3）
6. 队列与优先级（M4）
7. graph_build step + 重试闭环（M5）
8. M2 批量失败隔离 + 并发限流
9. M6 灵活性验证
10. 待验证项逐项实测闭环

---

## 附：本次重写修正的错误假设（v1 → v2）

| v1 错误假设 | v2 修正（依据） |
|---|---|
| 7 精确 stage | 5 子步骤对齐 PM 原型 + 映射自 progress（§4.2） |
| 无 cancel endpoint，要 SSH | 有 `DELETE /chunks`（api_reference line 2078） |
| 暂停=软停，硬取消运维级 | 默认软暂停（graceful）+ force 硬停（DELETE /chunks），行业惯例（§5.3） |
| /ingest 最灵活首选 | /ingest 不适配 PTR（GraphRAG 在内置路径），走 /chunks，/ingest 作演进项（§二） |
| 状态机自造 | 直接对齐 RAGFlow run 5 态（§3.1） |
| 无灵活性机制 | 三层抽象（统一接口/状态映射配置/pipeline 适配层，§八） |
