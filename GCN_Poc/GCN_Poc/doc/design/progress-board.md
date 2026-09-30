# 开发进度看板（批量导入编排接口）

> 定位：**当前在做什么、做到哪、下一步做什么**的一页纸现状图。随进度更新。
> 设计蓝图见 [ingest-orchestration.md](ingest-orchestration.md)（要长成什么样），本文只回答"现在到哪了"。
> 最后更新：2026-08-21

## 一、我们在做的事，一句话

PM 提了 4 件事（`doc/客户/原始需求/项目经理沟通记录.md` 20260813），**我们在做第 1 件**：

> 让批量上传文档这件事变得可管理——能看见传到哪了、哪份失败了、能暂停能重试能调优先级，最后给出一个接口。

## 二、边界：我们做什么，不做什么

**架构已于 2026-08-19 转向方案 B（复用基础设施，不走 RAGFlow 解析流程）**：

```
        我们的批量上传服务（自己的代码，全程自控）
   ┌──────────────────────────────────────────────┐
   │ 排队/状态机/时间记录/暂停/重试/优先级/REST接口 │
   │ 解析 → 切块 → 分词 → 向量化 → 写入            │
   └───────┬──────────┬──────────┬────────────────┘
           ▼          ▼          ▼
       MinIO        ES      embedding服务    ← 复用 RAGFlow 的基础设施
    (bucket=kb_id) (14字段)  (bge-base/1024)
           │          │
           └────┬─────┘
                ▼
     RAGFlow 照常能检索 / 建图（已实测命中 sim=0.476）

```

  ✗ 不做：LLM 抽参数 / 复合参数拆分 / 信息块 / PBS 关联 / AI 审核界面
     → 属"内容解析子系统"（需新建），不在本接口
     → 依据：项目经理沟通记录 line 38、项目经理汇报结论 P0"导入编排"

**关键澄清**：我们**不改 RAGFlow 内核，也不调它的解析 API**——而是自己跑完整条流水线，把产物写进它认识的存储里。

这样一来之前所有憋屈的地方一次解决：进度不用猜（阶段由我们定义）、真暂停能做（自己的循环）、性能可优化（自己控并发/批大小）、RAGFlow 升级不影响（只依赖存储契约）。可行性已实测证明，见 [infrastructure-reuse-feasibility.md](infrastructure-reuse-feasibility.md) §七。

## 三、当前进度

### ✅ 已完成（commit d6e5fc6 起，均已推送）

| 模块 | 文件 | 作用 | 测试 |
|---|---|---|---|
| 状态机 | `code/ingest/state.py` | 任务 6 态流转（排队/进行中/完成/失败/停止/暂停），终态保护 | 37 |
| 阶段映射 | `code/ingest/step_mapping.py` | RAGFlow 进度 → 真实阶段 + PM 5 步投影 | 22 |
| 适配层 | `code/ingest/pipeline_adapter.py` | 封装 RAGFlow API（上传/解析/停止/建图） | 10 |
| 仓储 | `code/ingest/repository.py` | 数据存取抽象 + 内存实现（后被 MySQL 实现替换，见下） | — |
| 编排器 | `code/ingest/orchestrator.py` | 串联全流程 + 暂停/重试/取消 | 9 |
| 调度器 | `code/ingest/scheduler.py` | 按优先级选任务（priority desc + FIFO） | 6 |
| REST 接口 | `code/ingest/rest_api.py` | 对外 endpoint（jobs/tasks/queue），**不能叫 api.py**，见认知 6 | 9 |
| 表结构 | `code/ingest/schema.sql` | 三表 DDL（**MySQL**，见决策 16；早期草案误写 PG） | — |
| 冒烟脚本 | `code/ingest/e2e_smoke.py` | 接真 RAGFlow 跑单份验证 | — |

**合计 118 测全绿。**

### ✅ 真实环境验证（2026-08-19，131 实跑）

| 场景 | 结果 |
|---|---|
| docx 成功路径 | received(-) → chunk(83.9s) → embed(85.9s) → index(41.8s)，任务 succeeded |
| xlsx/txt 失败路径 | received(done) → chunk(**failed**) → 后续 queued，失败阶段定位准确 |
| 4 个映射 bug | 已全部修复并用真实数据回归 |

### ✅ 方案 B 最小验证（2026-08-19）

自己解析+切块+向量化+写入，**完全不经过 RAGFlow 解析流程**，验证它照常认：

| 验证项 | 结果 |
|---|---|
| 写 MinIO / MySQL / ES | ✅ 三处全成功 |
| RAGFlow 文档列表 | ✅ 显示我们的文档 run=DONE |
| RAGFlow 检索 | ✅ 命中，sim=0.476 排第一 |
| 关键坑 | `document` 表须配 `file`+`file2document`（INNER JOIN），否则文档不可见 |

### ✅ 方案 B 落地（2026-08-20）

| 模块 | 文件 | 说明 |
|---|---|---|
| 后端协议 | `code/ingest/pipeline.py` | 统一契约，两种后端都满足；换后端不动上层 |
| 自建流水线 | `code/ingest/selfrun_pipeline.py` | 自己 parse→chunk→embed→index，**推送真实阶段**不再猜 |
| 写入层 | `code/ingest/selfrun_writer.py` | MinIO + MySQL(document/file/file2document) + ES |
| 集成测试 | `test/test_selfrun_integration.py` | orchestrator + 自建流水线组合 |

**M2 批量目标已在新架构下达成**（`test_selfrun_integration.py`）：10 份并发跑通、1 份失败其余不受影响、失败项可重试成功、优先级生效、并发数不超上限、job 状态聚合正确。

### ✅ M2 真机验证（2026-08-20，131 实跑，无 mock）

`code/ingest/m2_batch_run.py` 跑在容器内，真写 MinIO/MySQL/ES + 真调 embedding：

| 验收项 | 结果 |
|---|---|
| 批量成功 | ✅ 3 份 / 6 份批次全部 succeeded |
| 失败隔离 | ✅ 5 份中 1 份真实失败（.pdf 不支持），其余 4 份不受影响 |
| 错误可诊断 | ✅ `unsupported file type: .pdf (needs MinerU)` |
| 并发受控 | ✅ peak_in_flight 不超设定值 |

**真实性能数据（每份约 1.5KB 文本，5 chunks）**

| 阶段 | p50 | 占比 | 说明 |
|---|---|---|---|
| parse | ~0ms | 0% | 我们自己做，纯本地 |
| chunk | ~0ms | 0% | 同上 |
| embed | 6.9–8.4s | ~25% | 调共享 embedding 服务 |
| **index** | **23.7–27.0s** | **~75%** | **写 MinIO+MySQL+ES，新瓶颈** |

**并发提升有限**（6 份文档）：

| 并发 | 墙钟 | 吞吐 |
|---|---|---|
| 1 | 49.7s | 0.12 docs/s |
| 6 | 45.1s | 0.13 docs/s |

→ 6 倍并发只快 9%，**瓶颈在共享下游（ES/embedding），不在调度**。加并发无用，要优化 index 阶段本身（批量写 ES、连接复用、异步刷新）。

### ✅ index 瓶颈定位并优化（2026-08-20）

`code/ingest/index_profile.py` 拆解 index 阶段（3 轮取中位数）：

| chunks | MinIO | MySQL | ES | ES/chunk |
|---|---|---|---|---|
| 1 | 8ms | 26ms | 946ms | 946ms |
| 50 | 9ms | 23ms | 896ms | **18ms** |

**ES 占 96.6%，且是固定开销**（1 个和 50 个 chunk 都是 ~900ms）——不是数据量问题。

**根因**：`ESConnection.insert` 硬编码 `refresh="wait_for"`（es_conn.py:320），每次 bulk 都同步等 ES 刷新索引。

**实测对比**：`wait_for` 719ms vs `refresh=False` 14.3ms —— **50 倍差距**。

**优化后**（6 份批量真机）：index p50 **23.7s → 8.5s（-64%）**，吞吐 0.13 → 0.16 docs/s。
默认不等刷新（批量导入不需要读己之写），需要立即可搜时传 `wait_for_refresh=True`。

### ✅ PDF 支持接入 MinerU（2026-08-20）

| 项 | 结论 |
|---|---|
| 形态 | **独立 FastAPI 服务**，非 RAGFlow 内部模块，`10.126.2.131:8010` |
| 接口 | 用异步 `/tasks`（提交→轮询→取结果）；同步 `/file_parse` 在此部署返回 503 |
| 网络 | 两容器不同 docker 网络，走宿主网关 `172.17.0.1:8010` |
| backend | 必须用 `pipeline`；默认的 `hybrid-auto-engine`/`vlm-*` 报 `repo_mode 'vlm' is not configured`（未装 VLM 权重） |
| 响应 | `results` 按**文件名**索引：`{"results": {"t": {"md_content": ...}}}` |
| 实测 | MinerU 解析 5.0s → 整条流水线 36.5s → run=DONE，真写入成功 |

### ✅ p90 长尾定位（2026-08-20）—— 是冷启动，不是竞争

`code/ingest/tail_probe.py` 串行 vs 并发对比：

| | minio p50 | mysql p50 | es p50 | 备注 |
|---|---|---|---|---|
| 串行 | 8.8ms | **41.6ms（首次 14341ms）** | 10.9ms | 首次 345 倍 |
| 并发×3 | 17.1ms | 39.4ms | 10.0ms | 全平稳，无长尾 |

并发竞争因子全部 ≈1.0（minio 1.93x 但绝对值仅 17ms），12 份并发只用 **0.3s**。

**根因**：一次性冷启动被第一个文档全额承担
- `init_settings()` 首次 **18.2s**（建全部存储客户端 + 模型注册表）
- 首次 `insert_document_row` **14.7s**（peewee 建连接 + 加载表元数据）
- 之后稳定 **60–80ms**

**修法**：加 `warm_up()`，服务启动时付这笔钱，不让第一个文档买单。已接入批量脚本，实测预热耗时 settings=18.2s / mysql=1.1s / docstore=3ms，之后批量内无冷启动。

### ⚠️ 131 机器过载（2026-08-20，非我方问题）

验证预热效果时 embedding 服务全部超时，排查发现：

| 项 | 值 |
|---|---|
| 宿主 load average | **22.11**（32 核） |
| `my_bge_flask.py` | **3263% CPU**（embedding 模型本体，已跑 36 天） |
| `embedding_proxy.py` | 18001 端口代理，因后端过载无响应（HTTP 000） |
| 我方任务残留 | 无 |

131 同时跑着 openspg×4、dbgpt、mineru、WeKnora、RAGFlow 等。**性能测试需在机器空闲时重做**，当前数据受此干扰。

### ✅ 测试计划落地（2026-08-20，见 [test-plan.md](test-plan.md)）

| 层 | 状态 | 说明 |
|---|---|---|
| L1/L2 单元+集成 | ✅ 195 测 | 含并发一致性、warm_up 幂等、大文档、乱码输入 |
| L3 契约 | ✅ 13 测（131 真机过） | 文档可见/检索命中/14字段/chunk_id/向量/三表/MinIO/refresh权衡 |
| L4 批量 B1-B8 | ✅ | B7 暂停真中断+恢复真续跑（抓到 2 个真 bug 已修）、B8 混合类型分派 |
| L6 灵活性 F1 | ✅ 4 测 | 改 PM 投影配置接口自动跟随，真实阶段记录不动 |

### ✅ M5 完成（2026-08-20）——方案 B 最后一个假设已证实

**GraphRAG 完全能对我们自己写入的 chunk 建图**，它从 ES 读数据，不关心 chunk 是谁写的。

专用 KB `238d344e9c7411f1a30353b77a78806f`（3 条自研摄入的 chunk），按[决策 9](../../memory/decisions.md) 四层验收：

| 层 | 结果 |
|---|---|
| 生成层 | `progress=1.0`，`Knowledge Graph done (183.68s)` |
| 图主体 | **36 nodes / 33 edges**；ES: entity=36 / relation=33 / graph=1 / subgraph=1 |
| 社区层 | **8 条 community_report**，ID 唯一，正文为真实领域内容（叶轮结构、检修周期），**无 prompt 示例污染** |
| 检索层 | `use_kg=false` → 2 chunk / 0 社区块；`use_kg=true` → 3 chunk / **社区报告排第一** |

实体抽取质量（全部来自我们写的正文）：
- 类型分布贴合配置的 7 类：参数 10 / 部件 7 / 处理措施 6 / 标准 4 / 故障原因 4 / 设备 3 / 故障现象 2
- 关系正确：`PTR冷却泵 → 叶轮/泵壳/轴承/机械密封/联轴器`（组成）、`PTR冷却泵 → 额定流量`（参数）

前置条件（复现时注意）：graphrag worker 必须单独启动（坑#1），`docker exec -d docker-ragflow-cpu-1 bash -c "cd /ragflow && nohup python -m rag.svr.task_executor -t graphrag > /tmp/graphrag_worker.log 2>&1"`

### ✅ 服务化 + MySQL 落地（2026-08-20）

从"脚本"变成"服务"：状态进 MySQL，重启不丢；REST 提交立即返回，worker 后台常驻处理。

| 项 | 结果 |
|---|---|
| MySQL 仓储 | `code/ingest/mysql_repository.py`，15 测在 131 真库通过 |
| 行为一致性 | 与内存仓储**逐字段对比全等**（可互换，验证了 §8 抽象） |
| 服务入口 | `code/ingest/service.py`，8 测通过 |
| 真机启动 | MySQL 连上 / MinerU healthy / 预热 16.6s 启动时付掉 / worker 就绪 / 监听 9800 |
| 端到端 | REST 提交 **0.06s 返回**，worker 后台 15.1s 完成，阶段耗时齐全 |
| **重启不丢状态** | 杀进程重启后，job 30 的状态与四阶段耗时（11/14/173/13424ms）**一字不差读回** |

踩坑：`ensure_schema` 原用 `split(";")` 切语句，把**中文注释里的分号**当分隔符，导致 DDL 被劈成非法 SQL。改为先剥离注释行再切。

### ✅ L5 性能重测（2026-08-20 空闲机器，load 1.33）——推翻旧结论

10 份文档 × 3 档并发：

| 并发 | 墙钟 | 吞吐 | index p50 |
|---|---|---|---|
| 1 | 19.7s | 0.51 docs/s | 59ms |
| **3** | **17.1s** | **0.58 docs/s** | **71ms** |
| 6 | 31.1s | 0.32 docs/s | **27488ms** |

**旧结论"并发无效、只快 9%"作废**——那是 load 22 时测的。真相是**并发有最优点**：并发 3 最快，**并发 6 比并发 1 还慢 58%**，index p50 暴涨 387 倍（下游争抢，排队代价压倒并行收益）。默认值 3 恰在最优点，但属巧合，换环境需重新标定。

**新待查项**：index p50 与 p90 差 200 倍（71ms vs 14.1s），冷启动已排除，说明另有偶发长等待。

### ✅ 汇报页 + 混合类型并发实测（2026-08-21）

服务自带 `GET /demo` 评审页（`code/ingest/demo_page.py`，6 个页签：接口实况 / 方案与取舍 / 技术栈 / 数据存储 / 实测数据 / 瓶颈与下一步），支持真实拖拽上传、知识库下拉、表结构实时读自 `information_schema`。宿主访问走 `demo_forward.py`（stdlib TCP 转发 9800 → 容器 192.168.80.6:9800，不重建容器）。

**混合类型并发实测**（job 33，task 42/43，一次提交两份）：

| 阶段 | docx | 扫描 PDF | 说明 |
|---|---|---|---|
| 开始时刻 | **02:22:17** | **02:22:17** | 同一秒开始 —— 并发是真的 |
| parse | 0.18s（194 段） | **96.8s**（626 段） | docx 直接遍历；PDF 走 MinerU 版面识别+OCR，差 530 倍 |
| chunk | 28ms（90 块） | 16ms（252 块） | 可忽略 |
| embed | 16.5s | **68.8s** | 块多 2.8 倍、耗时多 4.2 倍（共享 CPU 推理，两份互相排队） |
| index | 9.1s（90 块） | 1.3s（252 块） | 块更少反而慢 7 倍 → **长尾问题的一次现场** |
| 合计 | 25.9s | 166.9s | **快慢差 6.4 倍** |

批次墙钟 167s（= 最慢那份），串行需 193s，**并发省 13%**——收益受限于最慢的一份。
**耗时大头是两个 CPU 推理环节**：MinerU 96.8s + embed 68.8s = 99%。**要更快的方向是给这两处配 GPU，不是继续加并发。**

**认知**：并发在界面上"看不出来"是因为快慢差 6 倍，不是没并发。已在页面加「开始时刻」列作为直接证据。

**队列选型说明已成文**（[决策 17](../../memory/decisions.md)）：当前 MySQL 表 + 2s 轮询 + `ThreadPoolExecutor(3)`；代价是空转轮询、最长 2s 延迟、**只能单实例**。Redis 是明确的演进方向（队列归队列、账本归账本），触发条件是千份级压测暴露单机吞吐不足，改动集中在 `scheduler.py` 一层。

### ⬜ 未完成

| 里程碑 | 内容 | 状态 |
|---|---|---|
| index p90 长尾 | 10 份里总有 1 份 14s（p50 71ms vs p90 14.1s，差 200 倍）。冷启动已排除。2026-08-21 混合批次再现（90 块耗 9.1s）。排查方向：MySQL 连接池竞争 / ES bulk 偶发重试 / MinIO 写入抖动。**不阻塞交付，但规模化前必须查清** | 待做 |
| S3 阶梯 | 100 份压测（S1/S2 已完成） | 待做 |
| M3/M4 真机 | 暂停/恢复/取消、队列/优先级的真机验证（mock 已覆盖） | 待做 |
| 队列换 Redis | 支持多机消费，解除单实例限制。触发条件见决策 17 | 待做（有条件） |
| 服务开机自启 | 当前 `setsid` 手启，需 systemd/Supervisor | 待做 |
| 接口鉴权 | 当前内网无鉴权 | 待做 |

> M6 灵活性、PDF/MinerU 支持已完成，见上文。

## 四、关键认知（这轮学到的，别忘）

1. **RAGFlow 的 progress_msg 是累积日志**，不是当前状态快照——每次轮询返回从头到现在的全部日志。所以判断"现在在哪一步"要取**最靠后**的阶段标记，不能用包含匹配。

2. **RAGFlow 自报精确耗时**：`Embedding chunks (85.88s)`、`Indexing done (41.82s)`。直接解析这些比自己掐表准（不含轮询延迟）。

3. **PM 原型 5 步 ≠ RAGFlow 实际阶段**，需要翻译层：
   - 真实阶段：`received → chunk → embed → index`（普通 RAG）
   - PM 5 步：`OCR / 结构化 / Embedding / 实体关系 / LLM抽取`
   - `LLM抽取` = 参数提取 → **本接口无数据源，标 not_applicable**

4. **性能波动大**：同一份 docx 三次跑 165.66s / 132.11s / 136.10s，embedding 从 114.90s 波动到 81.43s。131 上还跑着 dbgpt/WeKnora/mineru 等一堆容器。**单次测量不可信，性能结论必须多轮取分位数**（决策13）。

5. **自建流水线后瓶颈转移**：不再是 RAGFlow 的 embedding（那是它的 CPU 推理），而是 **index 写入占 74%**。且并发从 1 提到 6 只快 9%——瓶颈在共享下游服务，加并发无效，要优化写入本身。

6. **模块名不能叫 `api.py`**：服务与 RAGFlow 同机部署时，`ingest/api.py` 会遮蔽 RAGFlow 的 `api` 包，导致 worker 内所有 `import api.db...` 报 `'api' is not a package`。已改名 `rest_api.py`。

7. **文件类型决定解析成本**：docx/xlsx 是 zip+XML，直接遍历不跑模型（快）；PDF 要跑版面分析模型；扫描件还要 OCR（CPU 上极慢）。30w 份里扫描件占比直接决定总耗时量级。

## 五、环境速查

| 项 | 值 |
|---|---|
| RAGFlow Web/API | `http://10.126.2.131:9388`（v0.26.1，已实测 `/api/v1/system/version`） |
| 凭据 | `GCN_Poc/.env`（已 gitignore，含 API Key / 登录 / SSH 配置） |
| SSH 进 131 | `ssh wenge-ragflow-131 'docker ps'`（走 JumpServer 网关，别名已配 `~/.ssh/config`） |
| 登录 endpoint | `POST /api/v1/auth/login`（密码需 RSA 加密，公钥 `/ragflow/conf/public.pem`） |
| API Key 管理 | `GET|POST /api/v1/system/tokens`（带登录返回的 authorization 头） |
| 跑冒烟 | `source .env && uv run --project code python code/ingest/e2e_smoke.py --file <path>` |

## 六、下一步

PM 第 1 点的功能已全部实现并在 131 上跑通（8 个接口、状态落库重启不丢、231 测通过），当前重点转向**规模验证与汇报**：

1. **百份级压测（S3）**——当前只到 10 份，容量判断不能由此外推；
2. **定位 index p90 长尾**——规模化前必须查清，百份级会被放大；
3. **真实核电扫描件端到端**——MinerU 已通，但未用甲方真实扫描件跑过。

Redis 队列、开机自启、接口鉴权列为有条件项，触发条件见「未完成」表。
