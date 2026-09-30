# 测试计划（批量导入编排接口）

> 定位：**什么算做对了、怎么验、谁来验**。开发前定验收标准（CLAUDE.md「验收标准前置」）。
> 现状见 [progress-board.md](progress-board.md)，设计见 [ingest-orchestration.md](ingest-orchestration.md)。
> 最后更新：2026-08-20

## 一、分层策略

五层，越往下越贵、越慢、越依赖环境，因此**越往下用例越少、目标越聚焦**：

| 层 | 跑在哪 | 依赖 | 频率 | 现状 |
|---|---|---|---|---|
| L1 单元 | 本地 | 无 | 每次改动 | ✅ 179 测 |
| L2 集成 | 本地 | 无（fake writer/embedder） | 每次改动 | ✅ 含在上面 |
| L3 契约 | 131 容器 | MinIO/MySQL/ES | 每次改写入层 | ✅ 13 测（`test/contract/`） |
| L4 批量 | 131 容器 | 全套 + embedding | 里程碑 | ✅ B1-B8 覆盖 |
| L5 性能 | 131 容器 | 全套 + **机器空闲** | 阶段性 | ✅ S1/S2 空闲重测完成 |

**L1/L2 是回归防线**（快、稳、必须全绿）；**L3-L5 是验证手段**（慢、需环境、按需跑）。

## 二、L1 单元层（195 测，已建立）

| 模块 | 用例 | 守住什么 |
|---|---|---|
| `test_ingest_state.py` | 37 | 状态机每条合法边、终态保护、非法迁移拒绝、retry/pause 闭环 |
| `test_selfrun_pipeline.py` | 27 | 切块边界、**14 字段契约**、**chunk_id 与 RAGFlow 一致**、阶段推送、取消 |
| `test_step_mapping.py` | 22 | 4 个真实 bug 的回归（关键词吃单/累积日志/漏 index/丢耗时），断言全用 131 实测原文 |
| `test_mineru_client.py` | 16 | zip/JSON/异步三种响应形态、表格保 HTML、错误可诊断 |
| `test_pipeline_adapter.py` | 10 | HTTP 后端调对 endpoint 和 body |
| `test_api.py` | 9 | REST 路由契约 |
| `test_orchestrator.py` | 9 | 编排全流程、失败标记、控制操作 |
| `test_selfrun_integration.py` | 8 | orchestrator + 自建流水线组合（L2） |
| `test_pause_and_mixed.py` | 10 | **B7 暂停真中断/恢复真续跑**、**B8 混合类型分派** |
| `test_l1_gaps.py` | 12 | 并发一致性（快照隔离/ensure_step 唯一）、warm_up 幂等、300+ chunk 大文档、乱码/超长行/空白 |
| `test_flexibility.py` | 4 | **F1**：改 PM_STEP_PROJECTION 加/删步骤，接口自动跟随，真实阶段记录不动 |
| `test_scheduler.py` | 6 | 优先级选取、FIFO 打破平局 |

### 判定标准
- **全绿才算通过**，不接受 skip 掩盖问题
- 新增功能必须带用例，修 bug 必须先写复现用例

### 缺口（已补齐 2026-08-20，`test_l1_gaps.py` 12 测）
| 缺口 | 验证方式 |
|---|---|
| 并发下 repository 一致性 | 8 线程锤 get_task，断言快照隔离（看不到他人 steps、改动不影响库内对象）；并发 ensure_step 只建一条记录 |
| `warm_up()` 幂等性 | 重复调用无害（计数 stub 验协议）；无 warm_up 的 writer 被容忍 |
| 超大文档 | 400 节文档完整入库；200 段切块全部在预算内；超预算单节保持整块（表格不被切断，契约显式固定） |
| 编码异常输入 | 乱码字节**响亮失败**而非静默存 U+FFFD（核电手册宁失败不存垃圾）；20 万字单行可入库；纯空白拒绝；空/垃圾 progress_msg 不崩映射 |

## 三、L3 契约层（关键，因为契约错了下游全废）

**验证目标**：我们写进 MinIO/MySQL/ES 的东西，RAGFlow 认。

这层不是测我们的代码，是测**双方对数据格式的理解是否一致**。RAGFlow 升级、schema 变更都可能悄悄打破它。

| 用例 | 怎么验 | 通过标准 |
|---|---|---|
| C1 文档可见 | 写入后调 `GET /api/v1/datasets/{kb}/documents` | 列表含该文档，`run=DONE`，`chunk_count` 正确 |
| C2 检索命中 | 调 `POST /api/v1/retrieval` 查文档内特征词 | 命中，且 `document_keyword` 为该文档 |
| C3 chunk 字段完整 | ES 直查该 doc_id | 恰好 14 字段，无多无少 |
| C4 chunk_id 规则一致 | 本地按 `xxh64(content+doc_id)` 算，与 ES `_id` 比对 | 完全相等 |
| C5 向量可用 | ES 直查 `q_1024_vec` | 长度 1024，非全零 |
| C6 file2document 关联 | MySQL 查 `file` / `file2document` | 三表关联完整（否则文档不可见，已踩过） |
| C7 GraphRAG 可读 | 对含我方 chunk 的 KB 触发建图 | 建图成功，图谱含我方文档实体 |

**现状（2026-08-20 已固化）**：`test/contract/test_ragflow_contract.py`，**13 测全部在 131 上通过**。

| 用例 | 状态 |
|---|---|
| C1 文档可见（含 `get_by_kb_id` 的 INNER JOIN 路径） | ✅ |
| C2 检索命中（走公开 HTTP API） | ✅ |
| C3 恰好 14 字段，无漂移 | ✅ |
| C4 chunk_id = `xxh64(content+doc_id)` | ✅ |
| C5 向量 1024 维且非全零 | ✅ |
| C6 file/file2document 三表关联 | ✅ |
| MinIO 对象存在且内容可回读 | ✅ |
| refresh 权衡（两个方向都验） | ✅ |
| C7 GraphRAG 可读我方 chunk | ✅ M5 实跑：36 nodes/33 edges/8 社区/KG 检索命中 |

**跑法**（需 RAGFlow 运行时，默认 skip）：
```bash
docker exec -e RAGFLOW_API_KEY=<key> docker-ragflow-cpu-1 bash -c   "cd /tmp/ctest && PYTHONPATH=/ragflow GCN_CONTRACT_TESTS=1    /ragflow/.venv/bin/python -m pytest test_contract.py -q -c pytest.ini"
```

**踩坑记录**：
1. 容器内 pytest 会读到 RAGFlow 的 `pyproject.toml` 配置项而 INTERNALERROR，需 `-c pytest.ini` 隔离
2. 测试写入必须 `wait_for_refresh=True`，否则读自己的写会撞上 ES 刷新间隔（生产批量则相反，故意不等）
3. 检索依赖 embedding 服务；服务挂时应 **skip 而非 fail**——那不是契约问题

## 四、L4 批量层

**验证目标**：批量行为正确——不是快，是**对**。

| 用例 | 场景 | 通过标准 |
|---|---|---|
| B1 全成功 | 10 份正常文档 | 全部 succeeded，job 统计正确 |
| B2 失败隔离 | 10 份中混 1 份 .pdf（无 MinerU 时） | 1 失败 9 成功，错误信息指明原因 |
| B3 重试恢复 | B2 的失败项修复后重试 | succeeded，`retry_count=1` |
| B4 并发上限 | 设 max_concurrent=3 | `peak_in_flight ≤ 3` |
| B5 优先级 | 混合优先级提交 | 高优先级先被调度 |
| B6 取消 | 批量中途取消某任务 | 该任务 cancelled 且不再执行，其余不受影响 |
| B7 暂停恢复 | 软暂停后恢复 | 停在阶段边界，恢复后继续完成 |
| B8 混合类型 | docx + txt + pdf 混合批次 | 各走对应解析路径，全部成功 |

**现状（2026-08-20 补齐）**：B1-B6 在 `test_selfrun_integration.py`（mock）+ `m2_batch_run.py`（真机）；**B7/B8 新增 `test_pause_and_mixed.py`（10 测）**。

B7 验的不是状态标签，是**行为**：
- 在 embed 阶段暂停 → **写入阶段不执行**（不是只改个状态）
- 暂停的任务不被批量调度捡走
- resume 后**完成文档**，且**不重复上传**（是续跑不是重跑）
- pause → cancel 进终态

B8 混合批次：
- docx + txt + pdf 各走对应解析器，**只有 pdf 打到 MinerU**
- pdf 解析失败不拖累同批 txt
- 无 MinerU 时报错**指名缺什么**，不是笼统失败
- 未知扩展名明确拒绝，不猜测
- 每种类型都记录自己的阶段耗时

**这批测试抓到一个真 bug**（见下）。

## 五、L5 性能层

**前提（重要）**：131 当前 **load average 22（32 核）**，`my_bge_flask.py` 占 3263% CPU。**在此状态下测出的数不能作为基线**。

### 5.1 测量纪律（沿用决策 13/14）

1. **多轮取分位数**，不用单次值——同份 docx 三次跑差 30%（165.66s/132.11s/136.10s）
2. **报 p50/p90/p95，不只报均值**——长尾才是问题所在
3. **先记录机器负载**，负载不同的数据不可比
4. **失败/超时计入统计**，不能删掉失败样本只报成功分位数
5. **逐条落盘 + 可断点续跑**，长测不能因单点挂死丢全部证据

### 5.2 阶梯压测

| 级别 | 份数 | 回答什么 |
|---|---|---|
| S1 | 1 | 单份基线，各阶段耗时构成 |
| S2 | 10 | 并发是否有效、失败率 |
| S3 | 100 | 真实吞吐、队列堆积、内存增长 |
| S4 | 1000 | 稳定性、是否有累积泄漏 |
| S5 | 10000+ | 仅在 S4 通过后评估，不外推 |

**当前到 S2（10 份）**，空闲机器数据可信。S3（100 份）未做。

### 5.3 性能基线（2026-08-20 空闲机器实测，load 1.33）

**⚠️ 此前所有性能数据作废**——都是在 load 22 的过载机器上测的，结论被干扰。以下是 32 核空闲（load 1.33、embedding 100ms）时的重测结果，10 份文档 × 3 个并发档：

| 并发 | 墙钟 | 吞吐 | index p50 | index p90 | embed p50 |
|---|---|---|---|---|---|
| 1 | 19.7s | 0.51 docs/s | 59ms | 13895ms | 494ms |
| **3** | **17.1s** | **0.58 docs/s** | **71ms** | 14144ms | 1008ms |
| 6 | 31.1s | 0.32 docs/s | **27488ms** | 29087ms | 1273ms |

**推翻的旧结论**：之前说"并发从 1 提到 6 只快 9%，加并发无效"。空闲机器上真相是——**并发有最优点，超过就急剧变差**：
- 并发 3 是当前最优（吞吐比 1 高 14%）
- **并发 6 比并发 1 还慢 58%**，index p50 从 71ms 暴涨到 27.5s（387 倍）——下游（ES/MySQL 连接、embedding 服务）开始争抢，排队代价超过并行收益
- 默认 `max_concurrent=3` 恰好落在最优点，但这是**巧合而非标定**，换机器/换文档大小需重新标定

**仍然成立的结论**：
| 项 | 观测值 | 状态 |
|---|---|---|
| ES refresh | `wait_for` 719ms vs `false` 14ms | ✅ 已优化，50 倍 |
| 冷启动 | 首次 33s（settings 18s + mysql 15s） | ✅ 已加 warm_up，服务启动时付掉 |
| index p90 长尾 | 各并发档 p90 都在 14s 左右 | ⚠️ 仍在，见下 |

**新发现的待查项**：index **p50 与 p90 差 200 倍**（71ms vs 14144ms）。冷启动已被 warm_up 消除，说明还有另一个偶发的长等待——10 份里总有 1 份要 14 秒。下一步排查方向：MySQL 连接池竞争、ES bulk 偶发重试、MinIO 写入抖动。

原始数据：`test/results/perf/idle_c{1,3,6}.json`

**不能承诺**：30 万份规模、2秒/5秒端到端目标（决策 7/10 已明确）。

## 六、L6 灵活性验证（M6）

**验证目标**：设计 §8 三层抽象不是纸面架构。

| 用例 | 怎么验 | 通过标准 |
|---|---|---|
| F1 换状态口径 | 改 `PM_STEP_PROJECTION` 加一步 | 接口自动带出新步骤，orchestrator/state 不改一行 |
| F2 换解析后端 | orchestrator 注入 `ChunksPipelineAdapter` 而非 `SelfRunPipeline` | 全流程跑通，上层无改动 |
| F3 换存储 | 注入 fake repository | 全流程跑通 |

**现状（2026-08-20 全部落地）**：
- **F1** ✅ `test_flexibility.py` 4 测：改 `PM_STEP_PROJECTION` 加第 6 步"合规审查"/删到 2 步，接口输出自动跟随，orchestrator/state 一行未动；**真实阶段记录（parse/chunk/embed/index）与投影无关**——展示层可随便改，记录的事实不动；投影默认值本身有守卫测试（PM 已批准的基线不被悄悄改掉）。
- F2/F3 ✅ 由现有套件证明（同一 orchestrator 跑 HTTP 适配器与自建流水线两种后端；内存/fake repository）。

## 七、执行节奏

| 时机 | 跑什么 |
|---|---|
| 每次改动 | L1+L2（195 测，8 秒） |
| 改写入层/契约相关 | + L3 契约（131） |
| 里程碑完成 | + L4 批量（131） |
| 阶段性 / 机器空闲 | + L5 性能阶梯 |
| 架构变更 | + L6 灵活性 |

## 八、下一步（按优先级）

1. ~~固化 L3 契约测试~~ ✅ 2026-08-20 完成，13 测通过
2. ~~补 L4 的 B7/B8~~ ✅ 2026-08-20 完成，10 测通过，修掉 2 个 bug：
   - **`paused → fail` 非法迁移崩溃**：自建流水线在内部抛异常中止，orchestrator 当普通失败处理，试图从 paused 转 fail 而抛 `InvalidTransition`。改为失败前先检查是否已暂停。
   - **暂停标记不清除**：force-pause 会在后端置中止标记，resume 没清 → 恢复后立刻又被中断。新增 `clear_stop()`，resume 时调用。
3. ~~补 L1 缺口~~ ✅ 2026-08-20 完成，12 测通过
4. ~~等机器空闲重测 L5~~ ✅ 2026-08-20 完成，推翻旧结论：并发有最优点（3），并发 6 反而慢一倍
5. ~~F1 灵活性验证~~ ✅ 2026-08-20 完成，4 测通过
