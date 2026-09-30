# RAGFlow 任务队列机制原理（通用调研 + 源码级具体调研）

> 定位：内核修复故事的前置知识。先讲通用概念（为什么需要队列、Redis Stream 怎么工作、什么叫假死），再讲 RAGFlow 具体实现（怎么派活、怎么判活、怎么确认）。
> 源码：`f:\byh\ragflow-main`（vanilla v0.26.4 GitHub）。4090 部署版是 v0.26.1 + 团队 5 处本地补丁（未贡献上游）。
> 关键事实：vanilla v0.26.4 的 `get_svr_queue_name`（settings.py:157）硬编码 `.common`，所有任务类型挤同一队列——这是 vanilla 在重任务场景下的**设计局限**（轻负载合理、重任务互抢），团队在部署版打了补丁为 graphrag/raptor/mindmap 加专用队列。

---

# 第一部分：通用知识（没接触过后端的从这里读起）

## 1. 为什么需要消息队列

**问题**：API 收到"解析这份 500 页 PDF"的请求，如果同步处理（边收请求边解析），API 要等几十分钟才返回——期间这个 API 线程被占死，别的请求进不来。一份大文档就能把整个服务卡住。

**消息队列的解法**：把"收请求"和"干活"拆开——
- API 只负责：收请求 → 把任务写进队列 → 立即返回"已提交"
- 后台 worker：从队列取任务 → 慢慢干 → 干完标记完成
- 前端：轮询任务状态（"好没？""好没？""好了"）

**类比**：餐厅取号。前台收单子扔进队列（取号），后厨按顺序做（worker），你不用站后厨等，过一会儿来问"好了没"（轮询）。

**为什么 RAGFlow 必须用**：解析+OCR+embedding+图谱抽取都是重活（单份几十秒到几分钟），同步做会卡死 API，而且要多 worker 水平扩容、失败隔离——这些都需要队列。

---

## 2. Redis Stream 是什么

Redis Stream 是 Redis 5.0 引入的数据结构，专门做消息队列。可以理解成一个**持久化的日志列表**——消息按写入顺序排好，多个消费者可以各自读、互不干扰。

**几个核心命令**（面试可能被问，是 RAGFlow 队列的基础）：

| 命令 | 作用 | 类比 |
|---|---|---|
| `XADD` | 写一条消息进队列 | 往取号机塞一张号条 |
| `XLEN` | 队列里有多少条消息 | 取号机里还剩几张号 |
| `XREADGROUP` | 消费者组读消息 | 后厨从取号机拿一张号 |
| `XACK` | 确认这条消息处理完了 | 后厨做完这道菜，把号条扔进"已完成"盒 |
| `XINFO GROUPS` | 看消费者组状态 | 看后厨整体进度 |
| `XPENDING` | 看哪些消息被取走但没确认 | 看哪些号被拿了但菜还没做完 |
| `XTRIM` | 裁剪队列历史消息 | 清理取号机里旧号条 |
| `XGROUP DELCONSUMER` | 删一个消费者 | 开除一个厨师 |

**和普通 Redis List 的区别**：Stream 支持"消费者组"——同一份消息可以给不同消费者组各读一次，且每条消息有 ID、可持久化、可回溯。List 只能被一个消费者 pop 掉。

### 消息队列方案横向对比

| 方案 | 类型 | 持久化 | 消费者组 | ACK 机制 | 适用场景 | RAGFlow 选它的理由 |
|---|---|---|---|---|---|---|
| **Redis Stream** | Redis 内置 | ✅ 磁盘 | ✅ 原生 | ✅ XACK | 中小规模、已有 Redis | 已用 Redis 做缓存，不引入新组件 |
| **RabbitMQ** | 专用 MQ | ✅ | ✅ | ✅ 手动/自动 | 企业级消息路由、复杂路由规则 | 功能更强但多维护一个组件 |
| **Kafka** | 日志流 | ✅ 高吞吐 | ✅ consumer group | ✅ offset 提交 | 大数据流、日志、百万级吞吐 | 太重了，万级文档不需要 |
| **Celery** | Python 任务队列 | 依赖 broker | ✅ worker 并发 | ✅ 任务状态机 | Python 后台任务通用 | 和 FastAPI 集成好但多一层抽象 |
| **Python Queue** | 进程内 | ❌ 内存 | ❌ | ❌ | 单进程内通信 | 不适合分布式 |

**RAGFlow 选 Redis Stream 的理由**：已经在用 Redis 做缓存和状态存储，不想为队列再引入 RabbitMQ/Kafka——万级文档的吞吐量 Redis Stream 完全够用，运维简单。但代价是消费者组的 ACK 过期接管不如 RabbitMQ/Kafka 成熟——这就是假死修复要手工写 watchdog + claim 逻辑的原因。

### Task Executor 是什么

Task Executor 就是 RAGFlow 的后台 worker 进程——它不是 API Server 的一部分，而是独立的常驻进程，专门从 Redis Stream 队列里领任务干活。

| 维度 | API Server | Task Executor |
|---|---|---|
| 是什么 | FastAPI Web 服务 | Python asyncio 后台进程 |
| 职责 | 接收请求、路由分发、返回响应 | 领任务、解析、分块、向量化、写索引 |
| 对外暴露 | 有端口（9388），用户可调 | 无端口，内部进程 |
| 同步/异步 | 同步返回（毫秒级） | 异步处理（几十秒~几分钟） |
| 横向扩容 | 可多副本（无状态） | 可多 worker（各自领不同任务） |
| 崩了会怎样 | 用户请求失败（可重试） | 任务卡在 pending（需 watchdog 接管） |

**类比**：API Server 是前台接待——收单子、发号、告诉用户"好了来取"。Task Executor 是后厨——按号条做饭，做完按铃（ACK）。前台和后厨是分开的，前台不会被后厨的慢活堵住。

---

## 3. 消费者组模型（理解 lag/pending 的前提）

消费者组（Consumer Group）是 Redis Stream 的核心概念：**一组 worker 共享一个队列名，各自领活、各自确认**。

**三条消息的生命周期**：

```
新消息（new）
  ↓ XREADGROUP id=">"（某个消费者取走了）
pending（待确认）
  ↓ XACK（这个消费者说"我处理完了"）
已确认（acked，从 pending 列表移除，但消息还在 Stream 里）
```

**两个关键指标**（排查必看）：

- **lag**：还在队列里、**没有任何消费者取走**的消息数。lag 大 = worker 没启动、或 worker 都在忙、或 worker 假死（没来取活）。
- **pending**：已经被某个消费者取走、**但还没 ACK**（还没处理完）的消息数。pending 大 = 消费者取了活但卡住了、或处理慢、或僵死了没 ACK。

**一个消费者组里的 pending 是共享的**：所有消费者都能看到"哪些消息被取走没确认"。但一条消息的 pending 状态绑定在**取走它的那个消费者名下**——只有那个消费者能 ACK（除非用 XCLAIM 把它转移给别人）。

**类比**：餐厅三个厨师（消费者组）。号条在取号机里（lag）。厨师甲拿了 12 号条（pending，挂在甲名下）。甲做完菜按铃确认（ACK，12 号从 pending 移除）。如果甲拿着 12 号条突然不干了（僵死），12 号永远挂在甲名下——别的厨师要等甲被判定"失联"后才能把 12 号抢过来（XCLAIM）。

---

## 4. ACK 机制：为什么"确认"很重要

ACK（acknowledge，确认）是消息队列的核心保障：**消费者取了消息不等于处理完了，必须显式告诉队列"我做完了"**。

**为什么必须 ACK**：
- 如果取走就等于做完：消费者拿到消息后崩溃 → 消息丢失 → 任务永远没做
- 有 ACK 机制：消费者崩溃 → 消息还在 pending → 重启后（或别的消费者）可以重新处理

**ACK 的时机是个设计决策**：
- 取走就 ACK：最简单，但消息可能丢失（取走后崩溃就没了）
- 处理完才 ACK：最安全，但消费者僵死时消息永远卡 pending（RAGFlow 选的是这种）
- 阶段性 ACK：折中（RAGFlow 没选这种，所以有"僵死消息无法接管"的问题）

**RAGFlow 的选择**：整个任务（含所有异常处理）完成才 ACK。好处是不会丢消息；坏处是 worker 中途僵死，消息永远 pending，别人无法自动接管——这就是假死根因之一。

---

## 5. 心跳与存活检测

**问题**：worker 是个后台进程，怎么知道它还活着？进程存在不等于在工作（可能卡死了）。

**心跳机制**：worker 定期往 Redis 写一个"我还活着"的标记（时间戳）。别的进程看这个标记的时间——如果太久没更新，就判定这个 worker 失联了。

**RAGFlow 的实现**：
- 每个 worker 有个 Redis ZSET（有序集合），key 是 worker 名
- 每 30 秒 `ZADD` 写一条心跳（score=当前时间戳）
- 判活规则：`now - 最后心跳时间 > 120秒` → 判定失联
- 30 秒心跳、120 秒判死——4 次心跳没到才算死，留网络抖动余量

**心跳 vs 进程存在**：
- 进程存在（`ps aux` 能看到）≠ 在工作（可能事件循环僵死、CPU≈0）
- 心跳停了 = 事件循环不工作了
- 这就是"假死"：进程在但心跳停

---

## 6. 假死 vs 崩溃（面试必分清）

| | 崩溃（crash） | 假死（zombie/stuck） |
|---|---|---|
| 进程状态 | 不存在（`ps` 看不到） | 存在（`ps` 能看到） |
| 谁会发现 | 容器监督（Docker restart policy）自动重启 | 心跳停了才会发现 |
| 处理难度 | 简单——自动重启就好 | 难——进程还在，监督机制不触发，消息卡 pending |
| RAGFlow 的情况 | 容器监督会拉起新 worker | 无 watchdog → 永远卡住 → 需要手动修复 |

**为什么假死更可怕**：崩溃是显性的、系统有现成机制处理（容器重启）。假死是隐性的——进程还占着资源、消息还挂着 pending、别的 worker 不会自动接管——系统看起来"活着"但其实停摆了。

---

## 7. 事件循环（asyncio）为什么会僵死

RAGFlow 的 worker 用 Python asyncio（事件循环）。事件循环像一个单线程的调度器——所有异步任务排队执行。

**正常工作**：循环不断取任务→执行→取下一个。
**僵死**：某个任务卡在一个**阻塞调用**（比如网络请求超时不返回、死锁）——整个事件循环停在那一动不动，后面的任务全排队等。

**特点**：
- 进程还在（操作系统层面没崩溃）
- CPU 接近 0（没在算东西，在等）
- 心跳任务也在队列里排队——所以心跳停了
- 但进程不会自己退出——需要外部强制杀掉或 watchdog 检测后杀掉

**这就是为什么 RAGFlow 需要 watchdog**：vanilla 没有 watchdog，事件循环僵死就永久卡住。团队补丁加了 watchdog——300 秒没心跳就输出线程栈（看卡在哪）再退出，让容器监督拉起新进程。

### 并发模型横向对比：为什么 asyncio 会僵死

| 并发模型 | 怎么工作 | 优点 | 缺点 | RAGFlow 的情况 |
|---|---|---|---|---|
| **asyncio（异步）** | 单线程事件循环，任务间协作切换 | 轻量、高并发、省内存 | **一个阻塞调用卡死全部** | 用了这个 → 假死根因 |
| **多线程** | 多个线程各自执行 | 阻塞不影响其他线程 | GIL 限制、线程切换开销 | — |
| **多进程** | 多个进程各自独立 | 彻底隔离，一个崩了不影响其他 | 重、内存占用大 | Docker 多容器 ≈ 多进程 |
| **Go goroutine** | 轻量协程，运行时调度 | 高并发 + 阻塞不卡死 | 需要 Go 语言 | — |

asyncio 的风险就是"一个阻塞调用卡死全部"——这是单线程事件循环的固有缺陷。多线程/多进程不会这样（一个线程卡住不影响其他），但 asyncio 胜在轻量高并发——RAGFlow 选了它，代价就是要自己处理"阻塞调用导致僵死"的问题。

### 为什么修复后不再出现假死（实战经验）

假死不是单一原因，是**恶性循环**：

```
修复前：
  ① 队列未隔离 → 重任务（GraphRAG 合并几百秒）占住 worker → 普通任务积压
  ② 积压 → worker 高负载 → 偶发阻塞调用超时（网络/ES/Redis）
  ③ 超时 → asyncio 事件循环僵死 → 心跳停
  ④ 心跳停 → 消息卡 pending → 没有自动接管 → 永久卡住
  ⑤ 永久卡住 → 前端假死 → 人工重启 → 积压更严重

修复后（三个因素叠加）：
  ① 队列按 suffix 隔离 → 重任务不挤普通 worker → 普通任务不积压
  ② GPU 迁移（131→4090）→ embedding 从 556s 降到 8.9s → 网络等待大幅缩短
  ③ watchdog 兜底 → 偶发僵死 300 秒强制退出 → Docker 重启 → 自愈
```

**关键经验：代码修复 + 数据清理缺一不可**

改完代码后短暂还出现过问题，因为运行环境还是脏的：
- ES 索引里有大量孤儿 chunk（解析失败但索引没清理）→ 查询变慢
- MySQL 里有大量失败 task 记录、僵尸文档 → 查 task 列表变慢
- Redis pending 列表里有之前假死留下的僵尸消息 → worker 启动后先恢复 pending → 又是一堆旧消息 → 又堵

清理完数据库和 Redis 后，干净环境 + 修复代码，假死才真正根治。**生产环境故障修复不只改代码，还要清理运行时累积的脏状态**。

---

## 8. 软取消 vs 硬取消

**软取消（cooperative cancellation）**：不直接杀进程，而是在共享存储（Redis）写一个"请取消"的标志，worker 在**检查点**主动去查这个标志。好处是不丢数据（在安全点停），坏处是检查点之间没法停。

**硬取消（force cancellation）**：直接杀进程或调停止接口，立即生效但可能丢数据（处理到一半被掐）。

**RAGFlow 选的是软取消**：在 Redis 写 `{task_id}-cancel` 标志，worker 在 collect（取消息时）和 insert_chunks（每批写入后）检查。坏处：串行 embedding 时检查点之间文档已处理完——所以实测取消 0 份生效。

---

## 9. 分布式锁（为什么合并要加锁）

**问题**：多个 graphrag 任务可能同时合并同一个知识库的图。合并是"读旧图→改→写回"，如果两个任务同时读旧图、各自改、各自写——后写的覆盖前写的，丢数据。

**分布式锁**：合并前先抢一把锁（Redis 实现），抢到的才能合并，合并完释放。没抢到的等。

**RAGFlow**：`RedisDistributedLock(f"graphrag_task_{kb_id}")`——知识库级锁，同一 KB 的合并串行化，不同 KB 可并行。

---

## 10. 容器监督与自动重启

Docker 有 restart policy（`restart: always` 或 `unless-stopped`）：容器里的主进程退出（崩溃或被 watchdog 杀）→ Docker 自动拉起新容器/新进程。

**这和 watchdog 配合形成自愈闭环**：
1. 事件循环僵死（进程还在，不退出）
2. watchdog 检测 300 秒没心跳 → 输出线程栈 → `os._exit(70)` 强制退出
3. Docker 发现主进程退出 → 自动重启
4. 新 worker 启动 → 重新注册心跳 → 从 pending 恢复未完成的任务

**关键**：没有 watchdog 时，僵死进程不退出 → Docker 不重启 → 永久卡住。watchdog 的作用就是把"僵死不退出"变成"僵死能退出→被重启"。

---

# 第二部分：RAGFlow 具体实现（源码级）

## 一、四个角色

RAGFlow 的任务系统由四个角色协作：

| 角色 | 是什么 | 源码位置 |
|---|---|---|
| Redis Stream 队列 | 存放待处理任务的消息管道 | common/settings.py:139 `get_svr_queue_name` |
| 消费者组 | 一组共享队列名的 worker 集合 | SVR_CONSUMER_GROUP_NAME（common/constants.py） |
| Task Executor（worker） | 后台进程，从队列取任务执行 | rag/svr/task_executor.py |
| Redis 心跳 | worker 存活证明 | TASKEXE 集合 + 每个 worker 的 ZSET |

---

## 二、队列：Redis Stream 怎么存任务

### 2.1 队列命名（vanilla 设计：所有任务挤 .common）

```
队列名 = "te.{priority}.common"
        priority: 0=低优先级, 1=高优先级
```

**设计现状**（vanilla v0.26.4，settings.py:157）：函数签名 `get_svr_queue_name(priority, suffix="common")`，docstring 写"suffix: common/resume/graphrag/raptor/mindmap，Currently only 'common' is used"，**第 157 行直接 `return f"{SVR_QUEUE_NAME}.{priority}.common"`——suffix 参数被忽略，所有任务类型都走 .common 队列**。

**这不是 bug，是 vanilla 的设计选择**：对轻负载没问题，所有任务挤一条队列简单直接。但**重任务场景下是设计局限**——普通解析、graphrag、raptor、mindmap 全挤同一条 Stream，重任务（graphrag 合并要几百秒）会占住 worker、阻塞普通解析。团队在部署的 v0.26.1 上打了本地补丁：为 graphrag/raptor/mindmap 加专用队列（`SPECIAL_TASK_QUEUE_SUFFIXES`），普通任务继续走 common。**补丁未贡献上游**，vanilla v0.26.4 仍是原设计。

### 2.2 任务怎么进队列

`queue_product`（redis_conn.py:404）：
```
payload = {"message": json.dumps(message)}   # message 含 task_id/doc_id/task_type
REDIS.xadd(queue, payload)                    # 写入 Stream
```
- 重试 3 次，失败重连
- 消息只带轻量信息（id/type），完整 task 数据从 MySQL 取（collect 阶段）

### 2.3 队列里的消息怎么被取走

`queue_consumer`（redis_conn.py:415）：
```
XREADGROUP group={group} consumer={consumer} count=1 block=5 streams={queue} id=">"
```
- `id=">"` 表示只读**新消息**（未被任何 consumer 读过的）
- `block=5` 阻塞等 5 毫秒
- 返回 `RedisMsg` 对象，含 msg_id、payload、以及 ack 方法

---

## 三、消费：worker 怎么取任务

### 3.1 collect() 的两步取消息策略（task_executor.py:220）

worker 取消息有**优先级**：

```
① 优先恢复自己上次没 ACK 的消息
   UNACKED_ITERATOR = get_unacked_iterator(queues, group, consumer)  (:229)
   → 按 msg_id 顺序逐个 yield 自己 pending 的消息
   → 一旦拿到，先处理这个（断点续传语义）

② 没有未 ACK 的，才取新消息
   for queue in svr_queue_names:                (:233)
       redis_msg = queue_consumer(queue, group, consumer)  (:234)
       拿到就 break
```

**为什么这么设计**：worker 重启后，先把自己上次没干完的活干完（消息还在 pending 列表里），再接新活——避免任务丢失。但这也有副作用：**如果 worker 上次僵死时手里攥着消息没 ACK，重启后它会先去处理那条消息**，而不是让别的 worker 接手。

### 3.2 取到消息后的处理（handle_task, :1737）

```
collect() → 拿到 (redis_msg, task)
  → task_type 映射成 PipelineTaskType (:1745)
  → 三种执行模式（TE_RUN_MODE）：
     0 = 重构版 TaskManager.run_refactored_task
     1 = dry-run 新旧对比
     else = 原版 do_handle_task
  → 成功 DONE_TASKS++ / 取消 TaskCanceledException / 异常 FAILED_TASKS++
  → finally 末尾：redis_msg.ack()   (:1802)  ← 关键位置
```

**关键 bug（ACK 时机）**：`redis_msg.ack()` 在 `handle_task` 的 finally 末尾（:1802），意味着**整个任务（含所有异常处理、日志记录）全部完成后才 ACK**。如果 worker 在任务执行中途僵死（事件循环卡住、进程没退出），消息永远停在 pending 列表里，别的 worker 无法接管。

---

## 四、ACK 与 pending：消息确认机制

### 4.1 三种消息状态

Redis Stream 的消费者组模型里，一条消息有三个状态：

| 状态 | 含义 | 怎么进入 |
|---|---|---|
| 新消息（new） | 还没被任何 consumer 读过 | XADD 写入后、XREADGROUP id=">" 前 |
| pending（待确认） | 已被某 consumer 读走但未 ACK | XREADGROUP 后、XACK 前 |
| 已确认（acked） | 处理完成，从 pending 移除 | XACK 后 |

### 4.2 lag vs pending（排查最关键的两个指标）

```
XINFO GROUPS te.0.common
→ groups:
  - name: rag_flow_svr_task_broker
    consumers: 2
    pending: 3        ← 已被取走但没 ACK 的消息数
    lag: 1            ← 还没被任何 consumer 取走的新消息数
```

- **lag 大**：任务堆在队列里没人取 → worker 没启动、或 worker 都在忙、或 worker 假死
- **pending 大**：消息被取走了但没完成 → worker 卡住了、或 worker 僵死没 ACK
- **某 consumer 的 pending 多且 idle 大**：这个 worker 卡死了

### 4.3 ack 不 XDEL 的副作用（机制级发现）

`RedisMsg.ack()`（redis_conn.py:45）调用 `XACK`——**只从消费者组的 pending 列表移除，不从 Stream 删除消息**。消息永久留在 Stream 里，`XLEN` 越积越大。

这是上游设计（Stream 保留历史用于回溯），但长期运行会导致 Stream 膨胀。对策是定期 `XTRIM MAXLEN` 裁剪——但 XTRIM 不会删 pending 的，所以僵死 worker 的消息还是清不掉。

### 4.4 pending 接管（requeue_msg, :489）

```
def requeue_msg(queue, group, msg_id):
    messages = self.REDIS.xrange(queue, msg_id, msg_id)   # 读出原消息内容
    self.REDIS.xadd(queue, messages[0][1])                 # 重新写一条新消息
    self.REDIS.xack(queue, group, msg_id)                 # ACK 掉旧的
```
把僵死 worker 手里的消息"挪"给别的 worker——但要**先确认原 worker 真死了**（心跳过期），否则两个 worker 会同时处理。

---

## 五、心跳：worker 怎么证明自己活着

### 5.1 注册与心跳（report_status, task_executor.py:1816）

```
启动时：
  REDIS.sadd("TASKEXE", CONSUMER_NAME)              # 注册到 TASKEXE 集合
  CONSUMER_NAME = f"task_executor_{TASK_TYPE}_{TE_IDX}"   (:1970)

每 30 秒（:1894 sleep 30）：
  ① 读队列状态：PENDING_TASKS / LAG_TASKS  (:1833-1835)
  ② 打包心跳 JSON（ip/pid/now/pending/lag/done/failed/current）(:1838)
  ③ ZADD heartbeat ZSET，score=当前时间戳  (:1855)
     → 每个 worker 一个 ZSET，key=CONSUMER_NAME
  ④ 清理自己 30 分钟前的旧心跳  (:1864)
  ⑤ 清理其他过期 worker（分布式锁保护）(:1874-1893)
```

### 5.2 判活规则（:1886）

```
WORKER_HEARTBEAT_TIMEOUT = 120 秒（:175，环境变量可配）
if now_ts - last_heartbeat_ts > 120:
    worker 判死 → srem TASKEXE + delete ZSET
```

- 30 秒打一次心跳、120 秒判死——4 次心跳没到才算死，避免网络抖动误杀
- 清理别人时用 `RedisDistributedLock("clean_task_executor")`（:1827）——分布式锁，防止多个 worker 同时清理

### 5.3 假死的定义

**进程活着、心跳停了**：
- 操作系统层面 `ps aux` 能看到进程（python task_executor.py 还在）
- 但 `ZREVRANGE {worker_name}` 拿到的心跳时间戳超过 120 秒
- 进程 CPU 接近 0、事件循环僵住（线程数可能很高，卡在某个死锁或阻塞调用）

**这就是"假死"**：不是进程崩溃（崩溃反而会被容器监督重启），是进程还活着但事件循环不工作了——最隐蔽的故障形态。

---

## 六、取消：软取消与检查点

### 6.1 软取消机制（has_canceled, task_service.py:610）

```
def has_canceled(task_id):
    if REDIS.get(f"{task_id}-cancel"):   # Redis 里有个 {task_id}-cancel 的 key
        return True
```

取消 = 在 Redis 写一个 `{task_id}-cancel` 标志，worker 在**检查点**主动去查这个标志。

### 6.2 检查点位置（不是即时的）

- `collect()` 取消息时检查（:264）——任务还没开始跑
- `insert_chunks` 每批 insert 后检查（:1329/:1342）——索引写入的批次间隙
- GraphRAG 抽取 worker 里检查（extractor.py:145）

**为什么取消实测 0 份生效**：串行 embedding 场景下，检查点之间文档已经处理完。30% 时发取消，文档早已跑过检查点进了下一阶段——软取消对"已经在途"的任务无效。

---

## 七、8-14 本地补丁对照表（提前剧透，详见故事 2）

> 以下为团队在部署的 v0.26.1 上打的本地补丁（未贡献上游）。vanilla v0.26.4 仍是原设计。框架是"vanilla 设计局限 + 团队改进"，不是"修 bug"。

| vanilla 设计局限 | 源码位置 | 团队补丁 |
|---|---|---|
| 所有任务挤 .common 队列、重任务互抢 | settings.py:157 硬编码 | 为 graphrag/raptor/mindmap 加专用队列（SPECIAL_TASK_QUEUE_SUFFIXES） |
| ACK 在任务完成才执行、僵死时消息无法接管 | task_executor.py:1779（finally 之后） | 加 watchdog + pending 接管兜底 |
| 事件循环僵死无自愈机制 | vanilla 无 watchdog | 新增 watchdog（300s 无心跳→输出线程栈→退出→容器监督拉起） |
| 僵死 worker 的 pending 消息无法被接管 | 只靠心跳过期手动 requeue | 心跳过期后自动 claim（get_stale_unacked_iterator） |
| 合并超时固定 180s、重任务实际需更久 | index.py 固定超时 | 按 embedding 工作量动态计算（_effective_merge_timeout_seconds） |

---

## 八、一句话原理总结（背下来）

RAGFlow 用 Redis Stream 做任务队列，消费者组 `rag_flow_svr_task_broker` 里多个 worker 抢消息：worker 启动时注册到 TASKEXE 集合、每 30 秒往自己的 ZSET 打心跳，120 秒没心跳判死。worker 取消息优先恢复自己 pending 的、再取新的，整个任务处理完才 ACK。vanilla 设计把所有任务放 .common 队列、ACK 在任务完成后才执行、无 watchdog 自愈——轻负载没问题，重任务场景下会出现"假死"（进程活、心跳停、消息卡 pending）。团队在部署版本上打了本地补丁：重任务队列隔离、watchdog 自愈、pending 自动接管、动态超时——补丁未贡献上游。

---

# 附录 A：进度区间对照表

> 来源：合并自原《RAGFlow队列排查知识库.md》独有内容。

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

---

# 附录 B：重试机制实测

- 第一层：Redis PEL，worker 未 ACK 自动重投（task_executor.py:228）。
- 第二层：`get_task()` 里 `retry_count+1`，`>=3` 放弃标记 -1（task_service.py:221）。
- 实测：45 页 PDF 有 3 个页段 retry_count=2，其中 25~37 段第一轮卡 Table analysis 崩溃、重投后完成；13~25 段第一轮已 Task done 仍被重投（ACK 丢失）。

---

# 附录 C：实测耗时画像

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

# 附录 D：问题→方案→收益对照表

> 来源：合并自原《RAGFlow队列问题处置方案.md》。
> 配套《RAGFlow 文档解析卡死排查报告_2026-09-03.md》使用。对应"发现的问题"逐条给解法、收益、成本。

## 总览（按投入产出比排序）

| # | 问题 | 解决方案 | 收益 | 成本 | 优先级 |
|---|---|---|---|---|---|
| 1 | worker 只有 1 个 | 加 `--workers` | 批量卡死直接缓解 | 改配置重启 | ⭐⭐⭐⭐⭐ |
| 2 | 僵尸工单堆积 43 天 | 清理 task 表 progress=0 老工单 | 队列干净、不占坑 | SQL 删除 | ⭐⭐⭐⭐⭐ |
| 3 | 僵尸消费者 recovery2 | `XGROUP DELCONSUMER` | 消费者组干净 | 一条命令 | ⭐⭐⭐⭐ |
| 4 | 已完成消息不 ACK | 手动 ACK 拋留 pending | 停止重跑、省算力 | Redis 命令 | ⭐⭐⭐⭐ |
| 5 | Redis 不 XTRIM | 定时清理 / 设 maxlen | 防内存满 | 脚本或定时 | ⭐⭐⭐ |
| 6 | mp4 缺 image2text | 配模型或不传视频 | 视频不再失败 | 配模型 | ⭐⭐⭐ |
| 7 | embedding 9 倍波动 | 查 embedding 服务负载 | 耗时可预测 | 排查 | ⭐⭐⭐ |
| 8 | ACK 时序缺陷 | 改源码加幂等 | 根除重跑 | 需开发 | ⭐⭐ |
| 9 | 缺可观测 | 开 Jaeger/OTel | 精确测耗时 | 部署配置 | ⭐⭐ |

## 建议执行顺序

```
第一批（今天，零成本高收益）：
  2 清僵尸工单 → 3 清僵尸消费者 → 4 手动ACK残留
第二批（本周，需协调重启）：
  1 加 worker 到 2~3 个
第三批（持续）：
  5 定期XTRIM、6 配image2text、9 开Jaeger
第四批（治本，提issue）：
  7 查embedding服务、8 报ACK缺陷给官方
```

---

# 附录 E：排查命令速查

> 来源：合并自原《RAGFlow队列排查知识库.md》。

## Redis（队列视角）

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

## MySQL（业务视角）

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

## 进程视角

```bash
# 看 worker 进程数
docker exec docker-ragflow-cpu-1 bash -c "ps aux | grep task_executor | grep -v grep"
# 当天日志找异常
docker exec docker-ragflow-cpu-1 bash -c "grep '2026-09-03' /ragflow/logs/*.log | grep -iE 'exception|error|ack|timeout' | head -30"
```

## embedding 服务连通性

```bash
docker exec docker-ragflow-cpu-1 curl -s -X POST http://172.24.0.1:18001/v1/embeddings \
  -H "Authorization: Bearer sk-empty" -H "Content-Type: application/json" \
  -d '{"model":"bge-base","input":"hello"}' | head -c 200
```

## 排查流程（遇到卡死照此走）

1. `XINFO GROUPS` 看 lag——判断是"没人取"还是"取了没完成"。
2. `XINFO CONSUMERS` + `ps` 看 worker 健不健康——找僵尸。
3. MySQL `task` 表看 progress 停在哪步——定位卡点。
4. `progress_msg` 时间戳算各步耗时。
5. `retry_count` 看是否反复重试——找坏任务。
6. 失败的看 `progress=-1` 的 msg 找根因。
7. 日志找对应时间点的异常——闭环崩溃点。

---

## 来源

- settings.py:139-162（队列命名，vanilla v0.26.4 硬编码 .common；部署版 v0.26.1 已打补丁加 SPECIAL_TASK_QUEUE_SUFFIXES）
- redis_conn.py:404-499（queue_product/queue_consumer/get_unacked/requeue）
- task_executor.py:1816-1894（report_status 心跳）、:1737-1779（handle_task + ACK）、:220-291（collect）、:167（executor_watchdog，补丁）
- task_service.py:610-616（has_canceled 软取消）
- 注：行号以 vanilla v0.26.4 本地源码为准，部署版 v0.26.1（含补丁）行号略有漂移（差 10-30 行）
- 附录 A~E 合并自原《RAGFlow队列排查知识库.md》和《RAGFlow队列问题处置方案.md》（已删除，内容并入本文件）
