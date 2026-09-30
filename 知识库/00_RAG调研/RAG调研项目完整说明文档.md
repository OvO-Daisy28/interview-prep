# RAG 调研项目完整说明文档

> ⚠️ 本文为早期完整项目叙述，路径引用已过时（指向旧的 Downloads/WorkBuddy 路径），技术数据以知识库各专题文档和测试报告为准。
> 简历和面试准备材料已迁移至 `面试准备/` 目录。

> 一篇文档讲清楚：为什么调研、调研了什么、怎么调研的、得出什么结论、最终产出什么。
> 读完这一篇即可全面了解本项目。
>
> **文件路径约定**：
> - 📝 实习记录：`C:\Users\zhuwenting\Downloads\daxin_bank_template_search-master\doc\实习记录文档\`
> - 📊 实验数据：`C:\Users\zhuwenting\Desktop\rag\`
> - 📄 产出文档：`C:\Users\zhuwenting\WorkBuddy\2026-09-22-14-24-47\`
> - 下文每节标题旁标注了对应的源文件，方便翻阅对照

---

## 一、项目背景与调研目的

### 1.1 业务背景

中广核「采购文件活化项目」需要对 **30 万+份核电工程采购文档**（Word 与扫描版 PDF 两类）进行结构化入库与检索。甲方指定 **RAGFlow + GraphRAG** 作为知识库/图谱后端。

实习周期 2026 年 8-9 月（4 周），岗位为 RAG 算法实习生。

### 1.2 调研要解决的三个核心问题

| 问题 | 说明 |
|---|---|
| **选什么 RAG 系统** | 市面上有 10+ 种 RAG 框架（LightRAG、GraphRAG、RAGFlow、Dify、WeKnora 等），需要客观评测数据支撑选型决策，不能凭感觉拍板 |
| **RAGFlow 能不能用** | 甲方指定了 RAGFlow，但它的工程成熟度、性能极限、踩坑深度未知，需要部署验证 + 压力测试 + 源码级排障 |
| **万级文档怎么跑通** | 30 万份文档的规模远超 Demo 级别，Embedding 瓶颈、队列堆积、Worker 假死等问题必须提前暴露和解决 |

### 1.3 调研策略

采用**"横向对比选型 + 纵向深入二开"双轨并行**的策略：

```
横向：9 种 RAG 系统横向评测（选型维度）
  ↓ 产出：评测报告 + 选型建议
纵向：RAGFlow 全链路部署→排障→调优→二次开发（工程维度）
  ↓ 产出：部署方案 + 性能数据 + 内核修复 + 批量导入服务
```

---

## 二、调研过程：横向选型评测

> 📎 对应文件：
> - 📝 `更完整的实习记录.md`（LightRAG 实验部分，第1-3节）
> - 📝 `ragflow0831-0901.md`（3 模型对比实验，0/0 子图问题首次出现）
> - 📊 `Desktop\rag\law\legal_ragas_cn_50_balanced.csv`（50 道 RAGAS 评测结果）
> - 📊 `Desktop\rag\多跳数据集评估分析\`（三系统多跳对比：Lightrag/Ragflow/Weknora_wiki）
> - 📄 `简历项目_合并版最终稿.md`（Bullet 1，选型评测简历化）

### 2.1 评测对象（9 种 RAG 系统）

| 系统 | 类型 | 特点 |
|---|---|---|
| FAISS Top-K | 基础向量检索 | 最朴素的 RAG baseline |
| LightRAG hybrid | 混合检索 | 向量 + 图谱混合 |
| LightRAG mix | 混合模式 | hybrid + local |
| LightRAG local | 局部检索 | 实体邻域检索 |
| LightRAG global | 全局检索 | 社区报告检索 |
| GraphRAG-SDK (FalkorDB) | 图谱 RAG | 微软 GraphRAG 的 SDK 版本 |
| RAGFlow LightRAG | RAGFlow 内置 | RAGFlow 集成的 LightRAG |
| WeKnora Wiki | 知识库 Agent | Wiki 模式 + Agent 编排 |
| WeKnora Wiki_KG | 知识图谱 Agent | Wiki + 知识图谱混合 |
| GBrain | 企业级 RAG | 内部系统 |
| 智川 Agent | Agent RAG | Agent 编排式 RAG |

### 2.2 评测方法

**测试数据**：5 部中国劳动法，拆分 315 条款，构建 50 道平衡测试集（简单 15 + 中等 20 + 复杂 15），覆盖 1-5 hop 多跳问答。

**评测框架**：RAGAS v0.4.3，6 项标准指标：
- Faithfulness（忠实度）
- Answer Relevancy（答案相关性）
- Context Precision（上下文精度）
- Context Recall（上下文召回）
- Factual Correctness（事实正确性）
- Semantic Similarity（语义相似度）

**自定义指标**：针对 fragment 式标准答案（一个答案由多个不连续事实片段组成），基于 RAGAS NumericMetric 自定义「问题感知关键事实召回率」——将标准答案拆为关键事实集，计算 LLM 回答命中关键事实的比例。

**全链路追踪**：对 WeKnora Wiki/KG Agent 集成 Langfuse，追踪 Agent 轮次、模型调用、工具调用和延迟。

### 2.3 选型结论

| 维度 | 结论 |
|---|---|
| 纯向量检索 | FAISS Top-K 作为 baseline，简单问题够用，复杂多跳问题弱 |
| 图谱增强 | LightRAG global 和 GraphRAG-SDK 在多跳问题上优于纯向量 |
| Agent 模式 | WeKnora Wiki_KG Agent 准确率最高，但延迟最长（多轮 Agent 调用） |
| 生产可用性 | RAGFlow 作为甲方指定系统，工程成熟度最高（Docker 部署、ES+MinIO+MySQL+Redis 全栈），选为纵向深入对象 |

---

## 三、调研过程：纵向 RAGFlow 全链路

> 📎 对应文件总览：
> - 📝 `解决后端问题0902-0905.md`（阶段 2-3 上传/解析/队列排障，最详尽）
> - 📝 `解释后端卡住原因.md`（阶段 7 Worker 假活根因分析，精简版）
> - 📝 `批量上传接口开发0909-0911.md`（阶段 2 方案 A/B 对比 + 阶段 4 压测）
> - 📝 `4090上1000份测试0911.md`（阶段 4-5 GPU 迁移 + Amdahl 验证）
> - 📝 `更完整的实习记录.md`（阶段 6 GraphRAG 全链路 + 源码架构分析）
> - 📝 `ragflow0831-0901.md`（阶段 6 GraphRAG 0/0 子图 + 3 模型对比）
> - 📝 `自己写的实习进度.md`（4 周进度时间线，用户自记）
> - 📊 `Desktop\rag\`（选型评测全部实验数据：测试集/法律语料/RAGAS 评分/三系统多跳对比）
> - 📄 `简历项目_RAG全链路版.md`（8 阶段完整简历版）
> - 📄 `简历项目_合并版最终稿.md`（5 条 bullet 简历版 + 5 个面试故事）

### 3.1 RAG 全链路定义

本项目将 RAG 定义为 8 个阶段，每个阶段都有具体的工程问题需要解决：

```
选型评测 → 上传采集 → 解析分块 → Embedding → 索引写入 → 知识图谱 → 队列调度 → 检索问答
```

### 3.2 逐阶段工作与结论

#### 阶段 1：选型评测

**已在上文第二章详述。对应文件：📝 `更完整的实习记录.md`（第1-3节）、📝 `ragflow0831-0901.md`、📊 `Desktop\rag\law\` 目录下评测数据。**

**关键认知**：RAGAS 标准指标无法直接评分 fragment 式答案，需要自定义指标。这一发现影响了后续所有评测的指标选择。

---

#### 阶段 2：上传采集

> 📎 对应文件：📝 `批量上传接口开发0909-0911.md`（方案 A/B 对比实验全流程）、📝 `解决后端问题0902-0905.md`（RAGFlow 后端架构与 Redis 队列诊断）

**核心问题**：RAGFlow 原生批量上传接口能否满足 PM 的 5 项需求（进度可见、可取消、可重试、可暂停、并发可控）？

**调研方法**：设计 RAGFlow 原生 API（方案 A）vs 自建编排服务（方案 B）的对比实验。控制变量（同一批文档、同一编排层只换 pipeline）+ 三重证据交叉验证（源码 / 设计文档 / 实测数据）。

**发现的问题**：

| 问题 | 根因 | 实测证据 |
|---|---|---|
| 取消不生效 | RAGFlow 取消是软取消——写 Redis 标志，task_executor 在阶段边界轮询 `has_canceled`，但串行 embedding 场景下检查点之间文档已被处理完 | 跑到 30% 时发 `DELETE /chunks`，最终 0 份变 CANCEL，100 份全部 DONE |
| 进度不可见 | `progress_msg` 只有 4 种文本（"Task is queued..."/"N tasks are ahead..."），无 parse/chunk/embed 阶段信息 | 536 次轮询采样去重后仅 4 种文本 |
| 无暂停/重试 | 无 pause 状态，`retry_count` 字段存在但内核不消费 | 源码确认 |

**结论**：方案 A 满足 PM 5 项需求仅 1/5，方案 B 满足 5/5 且吞吐 2 倍（0.18 vs 0.091 份/s）。为 mentor 转自建路线提供实证依据。

**额外发现**：mentor 生产代码 `MySQLRepository` 使用 `threading.local()` 在 `ThreadPoolExecutor` 并发下连接断开——`--persist --concurrency 3` 万份任务 7 份成功后全卡死。建议改用连接池。

---

#### 阶段 3：解析分块

> 📎 对应文件：📝 `解决后端问题0902-0905.md`（解析链路梳理、DOCX 损坏检测）、📝 `更完整的实习记录.md`（源码级解析链路分析，DocxParser/DeepOCR/PlainParser）

**核心问题**：解析为什么慢？进度为什么卡住？

**调研方法**：源码追踪完整解析链路：
```
HTTP 上传 → 对象存储 → MySQL 元数据 → Redis 任务队列 → Worker → parser 解析 → chunker 分块 → Embedding → 文档引擎
```

**关键认知**：解析器不是独立 HTTP API，而是后台 Worker 调用的 Python 组件。DOCX 走 DocxParser（段落/图片/表格识别→JSON/Markdown），文本版 PDF 走 DeepOCR/PlainParser，扫描版 PDF 走 OCR/VisionParser。

**发现的问题**：

| 问题 | 定位方法 | 根因 |
|---|---|---|
| 89 个 DOCX 解析失败 | `unzip -t` 逐文件验证 | 文件损坏（输入质量问题），非系统 bug |
| 进度卡在 60%/80% | 同时检查任务状态+执行器进程+Redis pending+ES 结果 | 拆解为三类：①解析任务未完成 ②有 chunks 但实体抽取返回空 ③图谱全局合并仍在执行但前端不反映 |

**方法论沉淀**：不能只看前端百分比判断卡死，应同时检查任务状态、执行器进程、Redis pending、后端日志和 ES 结果。

---

#### 阶段 4：Embedding 向量化

> 📎 对应文件：📝 `批量上传接口开发0909-0911.md`（100/1000/10000 份阶梯压测、长尾分析、并发甜点区）、📝 `4090上1000份测试0911.md`（GPU 迁移全流程、bge-gpu 部署、吞吐对比）

**核心问题**：万级文档导入的性能瓶颈在哪？

**调研方法**：100→1000→10000 份阶梯压测 + p99/max 长尾分析（非均值）。

**发现**：

| 规模 | 吞吐 | embedding 占总耗时 | embedding max |
|---|---|---|---|
| 100 份 | 0.180 份/s | 93-95% | 72.8s |
| 1000 份 | — | — | — |
| 10000 份 | 0.046 份/s（崩塌 74%） | — | 556s（暴涨 7.6 倍） |

**关键洞察**：万份吞吐崩塌 74%，但 embedding **均值**只涨了 12%。如果只看均值会误判——问题在**长尾**。

**分析方法——墙钟差额法**：如果所有文档耗时都等于 avg，万份应该 2.3 小时跑完，实际 45 小时。差值的 69% 在等长尾。根因是 CPU 上 bge-base 与 34 个容器争抢资源，偶发长尾堵塞并发槽。

**解决**：迁移到 4090 GPU 服务器（4×RTX 4090），部署 bge-gpu 容器。

**结果**：

| 指标 | CPU (131) | GPU (4090) | 提升 |
|---|---|---|---|
| 吞吐 | 0.25 份/s | 1.406 份/s | ×5.7 |
| Embedding 均值 | 15.31s | 1.46s | ×10.5 |
| Embedding max | 72.8s | 5.4s | ×13.5 |
| Embedding p99 | — | 2.38s | — |
| 千份规模退化 | 有 | 无 | — |

---

#### 阶段 5：索引写入

> 📎 对应文件：📝 `4090上1000份测试0911.md`（瓶颈转移分析、Amdahl 定律验证，第5节"瓶颈转移"）

**核心问题**：Embedding 瓶颈解决后，新瓶颈在哪？

**发现——瓶颈转移**：GPU 把 embedding 从 93.6% 压到 45-53% 后，index 写入（ES bulk + MinIO + MySQL 三表）从 6% 升至 37-52%——成为新瓶颈。

**Amdahl 定律验证**：
- Embedding 占 93.6% 时，单条提速 10.5×
- 理论吞吐上限 = 1 / (0.064 + 0.936/10.5) = 6.5×
- 实测 5.7×
- 差值 = 0.8× 在 index 阶段

**结论**：下一阶段优化方向从 embedding 转向 index（ES bulk 批量写入优化 / MinIO 存储分层 / MySQL 批量插入）。

---

#### 阶段 6：知识图谱（GraphRAG）

> 📎 对应文件：📝 `ragflow0831-0901.md`（LightRAG 4 模式实验、0/0 子图首次出现、3 模型对比）、📝 `更完整的实习记录.md`（GraphRAG 全链路源码分析、二开边界、图数据 ES 存储机制）

**核心问题**：多文档 GraphRAG 建图出现空图（0 nodes, 0 edges）和抽取失败。

**GraphRAG 全链路理解**：
```
普通 chunk → batch 合并 → LLM 实体/关系抽取 → 文档级子图（NetworkX）
→ 全局图合并（PageRank 重算）→ 可选实体消歧 → 可选社区发现（Leiden）
→ 社区报告 → 图谱检索
```

图数据不存 Neo4j，而是序列化为特殊 chunk 写回 ES（`knowledge_graph_kwd: graph/subgraph/entity/relation/community_report`）。

**排查过程**：10 份法律 DOCX 生成图谱后，5 份显示 0/0。拆解为 4 种可能：
1. 模型返回空
2. 输出格式不被解析器识别
3. 抽取调用超时
4. 原文缺少可抽取信息

**对比 3 个模型**：

| 模型 | 成功率 | 节点数 | 稳定性 |
|---|---|---|---|
| qwen-plus | 可抽 | 470 | — |
| DeepSeek Flash | 3/10 有子图 | — | 不稳定 |
| GLM-5.2 | 10/10 成功 | — | 最稳定 |

**根因**：不是文档问题，是 **LLM 结构化输出稳定性**问题——GraphRAG/light 方法依赖 LLM 按提示词输出结构化 JSON，不同模型对格式遵循能力差异很大。

**解决**：模型选型先做单请求连通性 + 格式遵循测试，不用"页面显示已添加"判断可用。GLM-5.2 最终达到 10/10 准确率，P95=5.464s。

---

#### 阶段 7：队列调度

> 📎 对应文件：📝 `解释后端卡住原因.md`（Worker 假活根因分析精简版，4 项设计缺陷 + 6 文件修复）、📝 `解决后端问题0902-0905.md`（Redis 诊断全流程、TASKEXE ZSET 心跳机制、成功 QA 验证案例）

**核心问题**：GraphRAG 任务提交后前端显示 0%，长时间不动，重启多次仍"又卡住"。

**调研方法**：Redis 队列状态 + Worker 心跳交叉验证。

**诊断过程**：

| 检查项 | 结果 | 结论 |
|---|---|---|
| Redis XLEN | 消息存在 | 任务已入队 |
| Redis lag | lag=1 | 任务未被任何 Worker 领取 |
| Redis pending | pending=3 | 3 条旧任务被领取但没 ACK |
| Worker 心跳（TASKEXE ZSET） | 两个 Worker 心跳停在昨天 | Worker 可能已死 |
| `ps aux` | 进程还在，CPU≈0 | **进程活但事件循环已死——"假活"** |

**识别 4 项设计缺陷**：

| 缺陷 | 说明 |
|---|---|
| 队列未隔离 | `settings.py` 把队列后缀写死成 `.common`，common/graphrag/raptor Worker 实际抢同一条 Stream |
| 固定超时 | 图谱合并固定 180s 超时，但实际任务需要 ~215s；超时后底层 embedding 线程无法真正取消 |
| 重试重复计算 | 超时后会重试，但原任务底层线程还在跑 |
| 末尾 ACK | Redis 消息只在整个任务完成后 ACK，Worker 中途僵死时消息无法被接管 |

**修复方案（修改 6 个文件）**：

| 文件 | 修改内容 |
|---|---|
| `settings.py` | 队列拆分：graphrag/raptor/mindmap 各自独立 Stream |
| `entrypoint.sh` | 专用重任务 Worker：单次执行 + 线程池限制 16 + 异常退出自动重启 |
| `task_executor.py` | 看门狗：300s 无心跳→dump 线程栈→退出→容器重启 |
| `redis_conn.py` | Pending 接管修正：原 Worker 心跳过期后才允许 claim |
| `index.py` | 动态合并超时计算（根据节点和边的 embedding 工作量） |
| `utils.py` | 辅助函数调整 |

**验证结果**：任务 215s 完成，187 节点 / 200 边 / 389 图块，pending=0、lag=0。

---

#### 阶段 8：检索问答

> 📎 对应文件：📝 `解决后端问题0902-0905.md`（GLM-5.2 10/10 准确率 P95=5.464s 成功案例）、📝 `ragflow0831-0901.md`（QW 知识库 9/10 准确率 P95=10.097s）

**核心问题**：端到端链路是否可用？性能指标如何？

**检索链路**：
```
问题 Embedding → 向量检索 + BM25 全文检索 → 混合相似度
→ 可选 Rerank → Top-K chunk → Prompt 拼接 → LLM 生成 → 引用匹配
```

**GraphRAG 检索**：
```
KGSearch → LLM 分析查询实体 → entity/relation/community_report chunk 检索
→ N-hop 扩展 → 虚拟 chunk 拼入 Prompt
```

**端到端验证结果**：

| 测试集 | 准确率 | P95 | 备注 |
|---|---|---|---|
| 3 份地方法规（GLM-5.2） | 10/10 | 5.464s | 验证修复后端到端链路可用 |
| QW 知识库（10 份法律 DOCX） | 9/10（90%） | 10.097s | 平均 8.028s |

**关键认知**：准确率测试应基于预设问题和人工标准答案，不是看模型回答"看起来对不对"。

---

## 四、最终端到端验证

在 4090 GPU 环境下以真实核电设备手册打通全链路：

| 指标 | 结果 |
|---|---|
| 图谱规模 | 979 节点 / 719 边 |
| 图谱检索 vs 纯向量检索 | 相似度提升 40%（局部问题） |
| 简单问答完整响应 | 1.0s（≤2s 达标） |
| 流式首字延迟 | 0.9s（≤2s/5s 双达标） |
| 复杂问答瓶颈 | 27B 模型生成速度（75 tok/s），非检索 |

---

## 五、调研产出物清单

> ⚠️ 本节路径引用已过时。简历和面试准备材料已迁移至 `面试准备/` 目录。

### 5.1 简历

简历见 [`面试准备/简历_核电央企RAG项目_精简版.md`](../../面试准备/简历_核电央企RAG项目_精简版.md)（投递用）和 [`面试准备/简历_核电央企RAG项目_详细版.md`](../../面试准备/简历_核电央企RAG项目_详细版.md)（弹药库）。

### 5.2 面试准备材料

面试准备完整资料见 [`面试准备/`](../../面试准备/) 目录（INDEX.md 学习地图 + QA问答 + 自测题库 + 核心故事 + 知识点卡片）。

---

## 六、关键技术数字速查

面试时最常被追问的数字，集中备查：

| 数字 | 含义 | 出处 |
|---|---|---|
| 9 种 | 横向评测的 RAG 系统数量 | 选型阶段 |
| 50 道 | 评测测试集规模（简单15+中等20+复杂15） | 选型阶段 |
| 93% | Embedding 占总耗时比例（CPU 环境） | 性能优化 |
| 556s → 5.4s | Embedding 长尾延迟（CPU→GPU） | 性能优化 |
| ×5.7 | GPU 迁移后吞吐提升倍数 | 性能优化 |
| 74% | 万份规模吞吐崩塌幅度（0.180→0.046 份/s） | 性能优化 |
| 6.5× vs 5.7× | Amdahl 理论上限 vs 实测 | 索引写入 |
| 37-52% | Index 写入成为新瓶颈的占比 | 索引写入 |
| 4 项 | Task Executor 设计缺陷数量 | 内核修复 |
| 6 个 | 修改的源码文件数 | 内核修复 |
| 215s | 修复后 GraphRAG 任务完成时间 | 内核修复 |
| 187 节点/200 边/389 图块 | 修复后图谱规模 | 内核修复 |
| 979 节点/719 边 | 最终端到端验证图谱规模 | 端到端验证 |
| 40% | 图谱检索 vs 纯向量相似度提升 | 端到端验证 |
| 1.0s / 0.9s | 简单问答完整响应 / 流式首字延迟 | 端到端验证 |
| 75 tok/s | 复杂问答瓶颈（27B 模型生成速度） | 端到端验证 |

---

## 七、面试叙述策略

> 📎 对应文件：📝 `解决后端问题0902-0905.md`（成功 QA 案例叙述）、📝 `解释后端卡住原因.md`（假活根因叙述）、📝 `4090上1000份测试0911.md`（GPU 迁移叙述）、📄 `简历项目_合并版最终稿.md`（5 个困难故事完整版）

### 7.1 回答"你了解 RAG 吗"

> "我对 RAG 全链路的理解是从选型评测和 RAGFlow 二开两个维度建立的。选型阶段我对比了 9 种 RAG 系统的评测，从文档解析到检索生成的每个环节都看过差异。工程阶段我在 RAGFlow 上遇到了每个环节的具体问题：上传阶段发现了原生取消不生效，解析阶段处理了 DOCX 损坏数据质量，Embedding 阶段定位了长尾瓶颈并迁移 GPU，知识图谱阶段排查了模型抽取失败，队列调度阶段修复了 Worker 假活。每个问题都是通过源码追踪 + 分层排查定位的。"

### 7.2 按链路阶段展开追问

| 阶段 | 展开要点 |
|---|---|
| 上传采集 | 方案 A vs B 对比 → 取消不生效根因（软取消+串行 checkpoint）→ mentor 代码并发 bug |
| 解析分块 | DOCX 损坏检测 → 进度卡住三类状态拆解 → 解析器是 Worker 组件不是 HTTP API |
| Embedding | p99 而非 avg → 墙钟差额法 → GPU 迁移 → Amdahl 验证 |
| 索引写入 | 瓶颈从 embedding 转到 index → ES bulk + MinIO + MySQL 三表 |
| 知识图谱 | GraphRAG 全链路 → 0/0 子图 4 种可能 → 模型格式遵循能力差异 |
| 队列调度 | Redis Stream lag/pending → Worker 心跳假活 → 4 项设计缺陷 → 6 文件修复 |
| 检索问答 | 混合检索（向量+BM25）→ Rerank → GraphRAG 检索（KGSearch+N-hop） |

### 7.3 5 个核心困难故事

1. **Embedding 瓶颈**——万份吞吐崩塌 74%，p99 长尾分析 + 墙钟差额法 + GPU 迁移 ×5.7
2. **Worker 假活**——进程活但事件循环死，Redis 诊断 + 4 项设计缺陷 + 6 文件修复
3. **GraphRAG 空图**——5/10 文档 0/0 子图，4 种可能拆解 + 3 模型对比 + 格式遵循根因
4. **取消不生效**——跑到 30% 发 DELETE，100 份全 DONE，软取消机制 + PM 需求满足度 1/5
5. **跨机工程陷阱**——PowerShell 引号/tar 差异/pip relay/文件名 255 字节/浏览器 fetch 万文件

---

## 八、不写进简历的内容

1. 意图识别（LangGraph 编排）——只做了一版就被叫停，没有产出
2. 89 个损坏 DOCX 修复——属于数据预处理细节
3. 模型 Access Denied / qwen-plus 权限问题——太基础
4. Redis 诊断命令清单——面试时口头补充
5. 原始调试日志和中间过程——简历用陈述式
6. MinerU 测试——无实验文档记录，不建议写（除非补充数据）

---

## 九、与其他项目的关系

本项目可与 GCN_Poc 项目（中广核采购文件活化 POC）关联但区分：

| 项目 | 定位 | 侧重 |
|---|---|---|
| 本项目（RAG 全链路） | RAGFlow 的选型评测、性能调优、源码修复、批量导入开发 | 工程实践深度 |
| GCN_Poc 项目 | POC 评估、7 子系统架构设计、满意度矩阵、规模实验设计 | 架构设计思维 |

两者可共存于简历，一个体现工程深度，一个体现架构思维。

---

## 十、源文件索引（翻阅对照表）

> **三个目录约定**：
> - 📝 实习记录：`C:\Users\zhuwenting\Downloads\daxin_bank_template_search-master\doc\实习记录文档\`
> - 📊 实验数据：`C:\Users\zhuwenting\Desktop\rag\`
> - 📄 产出文档：`C:\Users\zhuwenting\WorkBuddy\2026-09-22-14-24-47\`

### 10.1 实习记录文件（📝）

目录：`C:\Users\zhuwenting\Downloads\daxin_bank_template_search-master\doc\实习记录文档\`

| 文件名 | 大小 | 时间范围 | 对应章节 | 核心内容 |
|---|---|---|---|---|
| `ragflow0831-0901.md` | 11KB | 0831-0901 | 二、横向选型 + 阶段 6 GraphRAG | LightRAG 4 模式实验、3 模型对比（qwen-plus/DeepSeek Flash/DeepSeek QW）、0/0 子图问题首次出现、QW 知识库 9/10 准确率 |
| `解决后端问题0902-0905.md` | 17KB | 0902-0905 | 阶段 2-3 上传/解析 + 阶段 7 队列 + 阶段 8 检索 | RAGFlow 后端架构、Redis 队列诊断（XLEN/XINFO/XPENDING）、TASKEXE ZSET 心跳机制、解析链路梳理、GLM-5.2 10/10 成功案例 P95=5.464s |
| `解释后端卡住原因.md` | 5.5KB | 0905 | 阶段 7 队列调度 | Worker 假活根因分析精简版、4 项设计缺陷、6 文件修复清单、修复后 187 节点/200 边/389 图块 |
| `批量上传接口开发0909-0911.md` | 12KB | 0909-0911 | 阶段 2 上传 + 阶段 4 Embedding | 方案 A vs B 对比（PM 5 需求 1/5 vs 5/5）、100/1000/10000 份阶梯压测、embedding 瓶颈 93-95%、并发 3 甜点区、mentor MySQLRepository threading.local() bug |
| `4090上1000份测试0911.md` | 11KB | 0911 | 阶段 4 Embedding + 阶段 5 索引 | GPU vs CPU 全面对比（吞吐 ×5.7）、embedding max 72.8s→5.4s、p99=2.38s、瓶颈转移 embedding 93.6%→45-53% index 6%→37-52%、Amdahl 定律验证 |
| `更完整的实习记录.md` | 36KB | 全周期 | 二、横向选型 + 阶段 3 解析 + 阶段 6 GraphRAG | LightRAG 实验 + 源码架构分析（Quart 非 FastAPI）+ 二开边界、GraphRAG 全链路（chunk→抽取→子图→全局图→消歧→社区→检索）、图数据 ES 存储机制 |
| `自己写的实习进度.md` | 893B | 全周期 | 一、项目背景 | 用户自记 4 周进度：第一周意图识别（LangGraph 一版叫停）、第二周后端修复、第三周批量+4090、第四周 MinerU（无文档） |

### 10.2 实验数据文件（📊）

目录：`C:\Users\zhuwenting\Desktop\rag\`

#### 根目录文件

| 文件名 | 大小 | 对应章节 | 核心内容 |
|---|---|---|---|
| `周报.xlsx` | 10KB | 全周期 | 实习周报 |
| `RAG_lightrag_wiki回答对比_41_48_49.xlsx` | 32KB | 二、横向选型 | LightRAG vs WeKnora Wiki 回答对比（题号 41/48/49） |
| `ragflow_multihop_ragas_detail.csv` | 309KB | 二、横向选型 | RAGFlow 多跳问答 RAGAS 评测明细 |
| `ragflow_multihop_ragas_hop_avg.csv` | 1.1KB | 二、横向选型 | RAGFlow 多跳问答按 hop 平均分 |
| `ragflow_question_aware_key_fact_recall_detail.csv` | 36KB | 二、横向选型 | RAGFlow 自定义指标（问题感知关键事实召回率）明细 |
| `weknora_question_aware_key_fact_recall_detail.csv` | 132KB | 二、横向选型 | WeKnora 自定义指标（问题感知关键事实召回率）明细 |

#### `Data/` 子目录 — 测试数据集

| 文件名 | 大小 | 对应章节 | 核心内容 |
|---|---|---|---|
| `RAG多跳问答集.xlsx` | 13KB | 二、横向选型 | 50 道多跳问答测试集（简单15+中等20+复杂15） |
| `RAG多跳问答集_带标准上下文.xlsx` | 63KB | 二、横向选型 | 带标准上下文版本的测试集 |
| `文档1-股权转让协议.docx` | 57KB | 二、横向选型 | 测试文档1 |
| `文档2-公司章程.docx` | 53KB | 二、横向选型 | 测试文档2 |
| `文档3-借款合同.docx` | 55KB | 二、横向选型 | 测试文档3 |
| `文档4-民事判决书.docx` | 55KB | 二、横向选型 | 测试文档4 |
| `文档5-法律条文摘录.docx` | 50KB | 二、横向选型 | 测试文档5 |

#### `law/` 子目录 — 法律语料 + 各系统评测结果

| 文件名 | 大小 | 对应章节 | 核心内容 |
|---|---|---|---|
| `中华人民共和国劳动法_20181229.txt` | 25KB | 二、横向选型 | 5 部劳动法之一（315 条款拆分来源） |
| `中华人民共和国劳动合同法_20121228.txt` | 35KB | 二、横向选型 | 5 部劳动法之二 |
| `中华人民共和国劳动争议调解仲裁法_20071229.txt` | 16KB | 二、横向选型 | 5 部劳动法之三 |
| `中华人民共和国社会保险法_20181229.txt` | 31KB | 二、横向选型 | 5 部劳动法之四 |
| `工伤保险条例_20101220.txt` | 28KB | 二、横向选型 | 5 部劳动法之五 |
| `legal_ragas_cn_50_balanced.csv` | 76KB | 二、横向选型 | 50 道平衡测试集 RAGAS 评测结果 |
| `simple_rag_rerank_answers_balanced.jsonl` | 497KB | 二、横向选型 | FAISS Top-K（baseline）回答结果 |
| `lightrag_hybrid_rerank_single_latency_balanced.jsonl` | 232KB | 二、横向选型 | LightRAG hybrid 模式回答+延迟 |
| `weknora_wiki_kg_answers_balanced_ragas_ready.jsonl` | 590KB | 二、横向选型 | WeKnora Wiki_KG Agent 回答（RAGAS 格式） |
| `weknora_wiki_kg_low_score_top5_detail.xlsx` | 52KB | 二、横向选型 | WeKnora 低分题 Top5 详情 |
| `weknora_wiki_low_faithfulness_correctness.xlsx` | 283KB | 二、横向选型 | WeKnora 低 Faithfulness/Correctness 详情 |

#### `多跳数据集评估分析/` 子目录 — 三系统多跳对比

| 子目录/文件 | 大小 | 对应章节 | 核心内容 |
|---|---|---|---|
| `RAG多跳问答集_带标准上下文.xlsx` | 63KB | 二、横向选型 | 测试集副本 |
| **`Lightrag/`** | — | 二、横向选型 | LightRAG 多跳评测结果 |
| ├ `lightrag_hybrid_rerank_multihop_answers.jsonl` | 5.3MB | — | LightRAG hybrid 多跳回答原始结果 |
| ├ `lightrag_multihop_ragas_detail.csv` | 5.2MB | — | LightRAG 多跳 RAGAS 评测明细 |
| └ `lightrag_multihop_ragas_detail.xlsx` | 1.4MB | — | LightRAG 多跳 RAGAS 评测 Excel 版 |
| **`Ragflow/`** | — | 二、横向选型 | RAGFlow 多跳评测结果 |
| ├ `ragflow_multihop_answers.jsonl` | 616KB | — | RAGFlow 多跳回答原始结果 |
| ├ `ragflow_multihop_ragas_detail.csv` | 443KB | — | RAGFlow 多跳 RAGAS 评测明细 |
| ├ `ragflow_multihop_ragas_hop_avg.csv` | 1.1KB | — | RAGFlow 多跳按 hop 平均分 |
| └ `ragflow_多跳数据集_对比分析.xlsx` | 158KB | — | RAGFlow 多跳对比分析 Excel |
| **`Weknora_wiki/`** | — | 二、横向选型 | WeKnora Wiki 多跳评测结果 |
| ├ `weknora_wiki_multihop_answers.jsonl` | 3.1MB | — | WeKnora Wiki 多跳回答原始结果 |
| ├ `weknora_ragas_detail.csv` | 2.9MB | — | WeKnora RAGAS 评测明细 |
| ├ `weknora_ragas_hop_avg.csv` | 629B | — | WeKnora 多跳按 hop 平均分 |
| └ `WeKnora_多跳数据集_对比分析.xlsx` | 718KB | — | WeKnora 多跳对比分析 Excel |
| `多跳数据集评估分析.zip` | 6.3MB | — | 以上全部的压缩包 |

### 10.3 产出文档（📄）

目录：`C:\Users\zhuwenting\WorkBuddy\2026-09-22-14-24-47\`

| 文件名 | 大小 | 对应章节 | 核心内容 |
|---|---|---|---|
| `RAG调研项目完整说明文档.md` | 20KB | 全文 | 本文档，一篇通览 |
| `简历项目_合并版最终稿.md` | 11KB | 五、产出物 | 5 条 bullet + 5 个面试困难故事 + 技术栈关键词 + 不写清单 + GCN_Poc 关系 |
| `简历项目_RAG全链路版.md` | 15KB | 三、纵向全链路 | 按 8 个 RAG 阶段组织的简历版，每阶段含理解+问题+解决+结果 + 面试叙述策略 |
| `岗位技能需求调研报告.md` | 15KB | （独立调研） | 20+ 份 JD 分析、技能匹配度矩阵、P0/P1/P2 差距优先级、投递策略 |
| `优秀简历模板调研.md` | 12KB | （独立调研） | 15+ 份简历范文分析、Agent/FDE/大模型方向写法要点、通用公式 |
| `Agent开源项目与学习资料推荐.md` | 11KB | （独立调研） | 5 个开源项目 + 6 份学习资料 + 10 天学习路径 + 技能覆盖矩阵 |
| `DeerFlow项目系统分析.md` | 27KB | （独立调研） | DeerFlow 2.0 架构解析、v1 vs v2 对比、技能覆盖矩阵、学习路径 |
| `DeerFlow落地可行性分析.md` | 21KB | （独立调研） | 劳动纠纷 Agent 系统用 DeerFlow 的逐条映射可行性分析 |

### 10.4 快速翻阅指南

| 你想看什么 | 去哪个目录 | 翻哪个文件 | 看哪一节 |
|---|---|---|---|
| **选型评测的原始实验数据** | 📊 Desktop\rag\law\ | `legal_ragas_cn_50_balanced.csv` | 50 道 RAGAS 评测结果 |
| **三系统多跳对比数据** | 📊 Desktop\rag\多跳数据集评估分析\ | `Lightrag/` `Ragflow/` `Weknora_wiki/` 各自的 `*_hop_avg.csv` | 按 hop 平均分 |
| **50 道测试题** | 📊 Desktop\rag\Data\ | `RAG多跳问答集.xlsx` | 测试集 |
| **5 份测试文档** | 📊 Desktop\rag\Data\ | `文档1~5-*.docx` | 法律文档 |
| **5 部劳动法原文** | 📊 Desktop\rag\law\ | `中华人民共和国*.txt` | 法律语料 |
| **自定义指标评测明细** | 📊 Desktop\rag\ | `*_key_fact_recall_detail.csv` | 问题感知关键事实召回率 |
| **LightRAG vs WeKnora 回答对比** | 📊 Desktop\rag\ | `RAG_lightrag_wiki回答对比_41_48_49.xlsx` | 题号 41/48/49 对比 |
| **WeKnora 低分题分析** | 📊 Desktop\rag\law\ | `weknora_wiki_kg_low_score_top5_detail.xlsx` | Top5 低分详情 |
| **0/0 子图问题排查** | 📝 实习记录 | `ragflow0831-0901.md` | 3 模型对比部分 |
| **Worker 假活完整诊断** | 📝 实习记录 | `解决后端问题0902-0905.md` | Redis 队列诊断 + 心跳部分 |
| **Worker 假活精简版** | 📝 实习记录 | `解释后端卡住原因.md` | 全文（仅 5.5KB） |
| **方案 A vs B 对比** | 📝 实习记录 | `批量上传接口开发0909-0911.md` | 方案对比 + PM 5 需求满足度 |
| **百/千/万份压测数据** | 📝 实习记录 | `批量上传接口开发0909-0911.md` | 阶梯压测部分 |
| **GPU 迁移完整数据** | 📝 实习记录 | `4090上1000份测试0911.md` | 全文（GPU vs CPU 全对比） |
| **GraphRAG 全链路源码分析** | 📝 实习记录 | `更完整的实习记录.md` | GraphRAG 数据流部分 |
| **成功 QA 验证案例** | 📝 实习记录 | `解决后端问题0902-0905.md` | GLM-5.2 10/10 案例 |
| **周报** | 📊 Desktop\rag\ | `周报.xlsx` | 实习周报 |
| **简历直接复制版** | 📄 WorkBuddy | `简历项目_合并版最终稿.md` | 5 条 bullet 部分 |
| **简历全链路版** | 📄 WorkBuddy | `简历项目_RAG全链路版.md` | 8 阶段部分 |
| **本说明文档的某一章** | 📄 WorkBuddy | `RAG调研项目完整说明文档.md` | 按章节号翻 |
