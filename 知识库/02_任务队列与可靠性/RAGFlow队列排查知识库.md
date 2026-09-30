# RAGFlow 队列与解析排查知识库（自留档）

> 用途：个人学习留档。通用知识 + RAGFlow 实例对照。紧凑排版，便于飞书/IDE 阅读。

---

## 一、消息队列通用知识

### 1.1 队列的作用

生产者把任务丢进队列就返回，消费者异步取走处理。作用：**削峰填谷、解耦、异步化**。Web 端上传后立即返回"已接收"，真正的重活儿（解析/向量化）由后台 worker 慢慢干。

### 1.2 常见队列技术对比

| 技术 | 特点 | 消息取走后 | 例子 |
|---|---|---|---|
| 普通 list（lpush/rpop） | 取走即删，无确认机制 | 消失，崩溃即丢 | 简单场景 |
| Redis Stream | 带收据，可重投、可追溯 | 保留，ACK 后才"签收" | RAGFlow 用这个 |
| Celery | Python 生态，封装好的任务框架 | 依赖 broker（Redis/RabbitMQ） | Django 常见 |
| NATS | 轻量高性能消息系统 | at-least-once 语义 | RAGFlow Go 版用 |
| Kafka | 高吞吐日志流，分区持久化 | 持久化、消费组管理 | 大数据场景 |

### 1.3 Redis Stream 核心概念（重点）

- **Stream**：消息按 ID 递增存储，`XADD` 投递、`XLEN` 看总数、`XRANGE` 看内容。
- **Consumer Group（消费者组）**：一组消费者共同消费同一个 Stream，消息在组内只投递给一个消费者。
- **XREADGROUP**：消费者从组里取消息，`>` 表示取新消息。
- **ACK（确认）**：消费者取走消息后，消息进入 **PEL（Pending Entries List，待确认清单）**；处理完调 `XACK` 才算"签收"。没 ACK 的消息下次会被重新投递。
- **XINFO**：查看 Stream/Group/Consumer 的元信息。
- **XPENDING**：查看 PEL 里哪些消息没 ACK、卡了多久。

### 1.4 判断队列是否积压（核心认知）

| 指标 | 含义 | 积压判据 |
|---|---|---|
| `XLEN` | Stream 历史消息总数（含已处理未清理） | ❌ **不等于积压** |
| `XINFO GROUPS` 的 `lag` | 消费者组还没读到的消息数 | ✅ >0 = 有积压 |
| `XINFO GROUPS` 的 `pending` | 已取走未 ACK 的数 | ⚠️ 看是否异常增长 |
| `XINFO CONSUMERS` 的 `idle` | 消费者多久没动（毫秒） | ⚠️ 异常大=卡死或僵尸 |

> **新手最大的坑**：看到 `XLEN` 很大以为积压，其实可能是已处理但没 `XTRIM` 清理的历史残留。判断积压只看 `lag` 和 `pending`。

### 1.5 僵尸消费者

消费者注册后进程崩了，但消费者记录还在 Redis 里。判别法：`XINFO CONSUMERS` 里有名字，但服务器 `ps` 里没对应进程。清理用 `XGROUP DELCONSUMER`。

### 1.6 消息至少消费一次 & 重投机制

- worker 取走消息没 ACK 就崩溃 → 消息留在 PEL → 下次 worker 启动优先重取（`XAUTOCLAIM` 或 `XPENDING` + `XCLAIM`）。
- 副作用：如果"写库完成"和"ACK"之间有窗口期崩溃，会导致**已完成的任务被重跑一遍**。

---

## 二、任务重试通用知识

### 2.1 两层重试模型

| 层次 | 触发 | 机制 |
|---|---|---|
| 消息层（自动） | worker 未 ACK 崩溃 | PEL 重投，下次 collect 优先取回 |
| 业务层（主动） | 任务执行失败 | retry_count 计数，超限放弃 |

### 2.2 重试的副作用

- **重复处理**：幂等性没做好会重复写入数据。
- **已完成被重跑**：ACK 时序缺陷导致已完成任务重跑，浪费算力。
- **死循环**：必坏任务反复重试占着 worker。需配合 retry_count 上限或死信队列。

### 2.3 ACK 时序缺陷（通用模式）

```
处理任务 → set_progress(1.0) 写库 → ack() 确认
                  ↑                   ↑
              中间崩溃 = 库里"完成" 但消息未 ACK = 会被重跑
```
正解：先写完成态，再 ACK；或加幂等保护（重跑时识别"已完成"直接跳过）。

---

## 三、文档解析流水线通用知识

### 3.1 典型 RAG 解析流水线

```
上传文件 → 下载文件 → 解析(OCR/抽取) → 分块(chunking) → 向量化(embedding) → 写向量库
```
每一步都可能是耗时大头，排查要逐段定位。

### 3.2 各阶段耗时特征

| 阶段 | 耗时特征 | 慢的原因 |
|---|---|---|
| 文件下载 | 通常快 | 大文件/对象存储慢 |
| OCR + 布局识别 | **最慢**，PDF 重灾区 | 逐页渲染图片+模型推理 |
| 表格识别 | 有表格才慢 | 深度学习模型推理 |
| 分块 | 快 | 纯文本处理 |
| Embedding | 中等，但波动大 | 调外部模型服务，网络/负载影响 |
| 写向量库 | 中等 | ES 索引刷新/磁盘 |

### 3.3 进度回写机制（通用模式）

- worker 每完成一步，把 `progress`（数值）和 `progress_msg`（文字日志）写回数据库。
- `progress_msg` 带时间戳追加，**相邻两行时间差 = 该步耗时**。
- 前端定时轮询（如 5 秒）读 `progress` 显示进度条。

### 3.4 找每步耗时的三种方法

| 方法 | 精度 | 成本 |
|---|---|---|
| progress_msg 时间戳差 | 秒级 | 零，直接看日志 |
| process_duration 字段 | 总耗时 | 零，数据库字段 |
| 分布式 trace（Jaeger/OTel） | 毫秒级 | 需部署，最精确 |

---

## 四、RAGFlow 实例对照

### 4.1 数据存放

| 数据 | 位置 | 容器 |
|---|---|---|
| 文件二进制 | MinIO，bucket=知识库ID | docker-minio-1 |
| 文档元数据+状态 | MySQL `document` 表 | docker-mysql-1 |
| 任务工单 | MySQL `task` 表 + Redis Stream | docker-mysql-1 / docker-redis-1 |
| 向量+全文索引 | Elasticsearch | docker-es01-1 |
| embedding 服务 | 宿主机 172.24.0.1:18001 | bge-base |

### 4.2 关键表与字段

**document 表**：
- `run`：0未启动/1运行中/2取消/3完成/4失败
- `progress`：0~1，-1 失败
- `progress_msg`：进度日志（带时间戳追加）
- `process_duration`：总耗时秒数

**task 表**：
- `doc_id`：关联文档
- `from_page`/`to_page`：页范围（PDF 按每 12 页拆 task）
- `progress`/`progress_msg`：同上
- `retry_count`：重试计数，上限 3
- `begin_at`：开始时间

### 4.3 队列实现

- 技术：Redis Stream（valkey 客户端），非 Celery。
- 队列 key：`te.0.common`（低优）、`te.1.common`（高优）。
- 消费者组：`rag_flow_svr_task_broker`。
- 生产：`queue_tasks()` 用 `XADD` 投递。
- 消费：`task_executor.py` 单进程 asyncio，`XREADGROUP` 取，`ack()` 确认。
- 容错：未 ACK 的消息 `get_unacked_iterator` 优先重取。

### 4.4 并发控制

| 限流器 | 默认值 | 环境变量 |
|---|---|---|
| worker 进程数 | 1（实测） | `--workers=N` 启动参数 |
| task_limiter | 5 | `MAX_CONCURRENT_TASKS` |
| chunk_limiter | 1 | `MAX_CONCURRENT_CHUNK_BUILDERS` |
| embed_limiter | 1 | 同上 |
| minio_limiter | 10 | `MAX_CONCURRENT_MINIO` |

### 4.5 进度区间对照

| progress | 含义 | 函数位置 |
|---|---|---|
| 0.0 | 入队 | — |
| 0.1 | 开始解析 | `build_chunks` task_executor.py:298 |
| 0.1~0.6 | OCR/布局 | naive.py:1049 / pdf_parser.py:1608 |
| 0.63 | 布局完成 | pdf_parser.py:877 |
| 0.65 | 表格完成 | pdf_parser.py:470 |
| 0.7~0.9 | Embedding | task_executor.py:709 |
| 0.8~0.9 | 写 ES | task_executor.py:1289 |
| 1.0 | 完成 | — |
| -1 | 失败/取消 | — |

### 4.6 重试机制（RAGFlow 实例）

- 第一层：Redis PEL，worker 未 ACK 自动重投（task_executor.py:228）。
- 第二层：`get_task()` 里 `retry_count+1`，`>=3` 放弃标记 -1（task_service.py:221）。
- 实测：45 页 PDF 有 3 个页段 retry_count=2，其中 25~37 段第一轮卡 Table analysis 崩溃、重投后完成；13~25 段第一轮已 Task done 仍被重投（ACK 丢失）。

### 4.7 实测耗时画像

**docx（无 OCR）**：总 6.36s，embedding 占 55%。
**PDF（45 页）**：

| 页段 | OCR | 布局 | 表格 | Embedding | 写ES | 总 | retry |
|---|---|---|---|---|---|---|---|
| 1~13 | 6.19 | 7.13 | 7.57 | 41.86 | 3.38 | 72.42 | 1 |
| 13~25轮2 | 6.60 | 8.48 | 0.00 | 57.66 | 4.42 | 83.19 | 2 |
| 25~37轮2 | 14.03 | 31.19 | 31.07 | 46.90 | 8.11 | 157.37 | 2 |
| 37~45轮2 | 4.13 | 4.83 | 5.24 | 4.51 | 3.15 | 27.71 | 2 |

洞察：embedding 同 17 chunks 波动 6.40s↔57.66s（9 倍）；表格有无差异 0↔31s。

---

## 五、排查命令速查

### 5.1 Redis（队列视角）

```bash
# 队列积压
docker exec docker-redis-1 redis-cli -a infini_rag_flow -n 1 XINFO GROUPS te.0.common
# 消费者健康
docker exec docker-redis-1 redis-cli -a infini_rag_flow -n 1 XINFO CONSUMERS te.0.common rag_flow_svr_task_broker
# pending 详情
docker exec docker-redis-1 redis-cli -a infini_rag_flow -n 1 XPENDING te.0.common rag_flow_svr_task_broker
# Stream 概览（含首尾消息内容）
docker exec docker-redis-1 redis-cli -a infini_rag_flow -n 1 XINFO STREAM te.0.common
```

### 5.2 MySQL（业务视角）

```sql
-- 找卡住的工单
SELECT id,doc_id,progress,LEFT(progress_msg,300) AS msg,begin_at,
       TIMESTAMPDIFF(SECOND,begin_at,NOW()) AS elapsed_sec
FROM task WHERE progress<1 AND progress>=0 AND begin_at IS NOT NULL
ORDER BY begin_at DESC;

-- 找失败工单
SELECT id,doc_id,progress_msg,begin_at FROM task
WHERE progress=-1 ORDER BY begin_at DESC LIMIT 20;

-- 看某文档所有 task + 重试次数
SELECT id,from_page,to_page,retry_count,progress,begin_at
FROM task WHERE doc_id='xxx' ORDER BY from_page;

-- 找积压多久的工单
SELECT doc_id,begin_at,TIMESTAMPDIFF(MINUTE,begin_at,NOW()) AS age_min,progress
FROM task WHERE progress=0 AND begin_at IS NOT NULL ORDER BY begin_at ASC;
```

### 5.3 进程视角

```bash
# 看 worker 进程数
docker exec docker-ragflow-cpu-1 bash -c "ps aux | grep task_executor | grep -v grep"
# 当天日志找异常
docker exec docker-ragflow-cpu-1 bash -c "grep '2026-09-03' /ragflow/logs/*.log | grep -iE 'exception|error|ack|timeout' | head -30"
```

### 5.4 embedding 服务连通性

```bash
docker exec docker-ragflow-cpu-1 curl -s -X POST http://172.24.0.1:18001/v1/embeddings \
  -H "Authorization: Bearer sk-empty" -H "Content-Type: application/json" \
  -d '{"model":"bge-base","input":"hello"}' | head -c 200
```

---

## 六、排查流程（遇到卡死照此走）

1. `XINFO GROUPS` 看 lag——判断是"没人取"还是"取了没完成"。
2. `XINFO CONSUMERS` + `ps` 看 worker 健不健康——找僵尸。
3. MySQL `task` 表看 progress 停在哪步——定位卡点。
4. `progress_msg` 时间戳算各步耗时。
5. `retry_count` 看是否反复重试——找坏任务。
6. 失败的看 `progress=-1` 的 msg 找根因。
7. 日志找对应时间点的异常——闭环崩溃点。
