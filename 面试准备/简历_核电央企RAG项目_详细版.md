# 简历·详细版：核电央企采购文档知识库活化项目（全量工作底稿）

> 用途：面试弹药库 / 网申系统填写素材源 / 工作全量梳理。投递用版本见 `简历_核电央企RAG项目_精简版.md`。
> 事实来源：`实习记录/` 全部 7 份记录 + GCN_Poc 客户需求文档。所有数字可回溯核验。
> 口径：项目名脱敏为「核电央企」；自建批量导入管线（方案 B）按本人开发口径书写。

## 项目信息

- **项目**：核电央企采购文档知识库活化——采购/技术文档（Word、扫描版 PDF）数字化闭环：解析入库 → 知识库/图谱构建 → 检索问答。技术栈 RAGFlow v0.26.1 + MinerU
- **角色**：RAG 算法实习生，负责部署、链路调研、二次开发、性能压测、图谱实验与端到端评测
- **周期**：2026.08 – 至今
- **环境**：131 CPU 服务器（34 容器共享机）；4090 GPU 服务器（4×RTX 4090 24G，Docker，与 vLLM 共存）

## 时间线总览

| 时间 | 工作 |
|---|---|
| 第一周 | LangGraph 意图识别原型（PRD + 一版实现，方向调整后沉淀为编排经验，见 docs/PRD-MVP-意图路由.md） |
| 2026-08-14 | Task Executor 假死故障诊断 + RAGFlow 内核修复（5 处源码修改） |
| 2026-08-31~09-01 | LightRAG 多模型建图基线实验（实验 A~D） |
| 2026-09-02~09-05 | 后端队列治理、GLM 建图成功案例、正式问答测评 |
| 2026-09-07~09-11 | 批量导入：原生接口实测、自研导入服务开发与压测、万份稳定性测试、4090 部署启动 |
| 2026-09-11 之后 | 4090 GPU 压测（百份/千份）、MinerU 扫描件解析性能专项（7 组实验） |

## 一、系统部署与环境建设

- 独立部署 131 服务器 RAGFlow 全套（Docker：Quart API Server、Task Executor、Elasticsearch、MinIO、MySQL、Redis Stream 任务队列），供团队开发测试
- 4090 服务器部署：环境探测（4×4090 各 24G，vLLM 已占 GPU0/GPU3 各 22.6G，磁盘余 175G）→ 部署 RAGFlow 容器 + bge-gpu 容器（GPU Embedding，验证通过）+ MinerU 双 Worker + Router（GPU2）+ Qwen3.8-27B 接入
- 4090 网络结构性限制（pip/uv 下载卡死）的解法：docker relay 跨机搬包链路（131 容器 → 本机 → 4090 容器），用 `importlib.metadata.requires()` 一次查全依赖树（fastapi + annotated-doc）而非逐个 import 试错
- 端口暴露不动容器映射（避免重建容器中断 RAGFlow）：宿主机 stdlib 转发脚本（0.0.0.0:9800 → 容器 9800）
- 长任务与 ssh 会话解耦：`docker exec -d` 后台执行 + 日志文件 + `python3 -u` 解决输出缓冲
- 跨平台文件搬运可靠模式：Windows/PowerShell 引号嵌套不可行 → 本地写脚本 scp 传容器；Windows tar 与 GNU 格式不兼容 → Python zipfile 打包传输（顺带正确处理中文 UTF-8 文件名）

## 二、RAG 全链路源码级调研

- 建立源码追踪方法：HTTP 路由 → Service 层 → 任务创建 → Redis Stream 队列 → Task Executor → 解析器/检索器 → 数据存储，可解释系统任意行为
- 梳理三类文档解析路径：DOCX（DocxParser：段落/图片/表格）、文本 PDF（DeepDOC/PlainParser：版面/bbox）、扫描版 PDF（OCR/VisionParser/PaddleOCR）
- 梳理存储拓扑：原始文件→对象存储（bucket=kb_id）；元数据→MySQL（document/task 表：run/progress/progress_msg）；chunk→ES（content_with_weight/content_ltks/q_1024_vec 等字段）
- GraphRAG 全数据流：普通 chunk → LLM 实体关系抽取（light/general/ner 三路）→ 文档子图（node-link JSON）→ 全局图合并（知识库级锁、同名实体合并、关系权重累加、PageRank 重算）→ 可选实体消歧（默认关闭）/Leiden 社区发现 → graph/subgraph/entity/relation/community_report 特殊 chunk 写回文档引擎（主图不落 Neo4j）
- 在线检索链路：问题 embedding → 向量+BM25 混合检索 → 可选 rerank → KGSearch（实体/关系/社区报告、N-hop 扩展）→ 上下文组装 → LLM 生成 → 引用回填
- 二开边界分析（对照技术规范书）：确认参数结构化提取、PBS/SNS 设备层级、表格语义解析、信息块模型、人工审核闭环、来源精确追溯（章节/页码/单元格）均属二开范围，输出原生/扩展/新建三级能力清单
- 架构级结论：解析器不是独立 HTTP API 而是后台 Worker 调用的内部组件；`async def` ≠ 后台任务，耗时工作必须走任务队列

## 三、LightRAG / GraphRAG 建图实验

- **脏数据治理**：原始目录 451 个 DOCX 经 `unzip -t` 逐文件核验，89 个损坏剔除（362 有效）；万份测试集扫描 12184 份、python-docx 预筛出 10000 份纯真 docx（约 20% 为 .doc 改名的假 docx），排除脏数据对失败率的干扰
- **实验 A（qwen-plus 基线）**：10 份法规 DOCX，10/10 解析完成、92 chunks，图谱抽取合并 567s，ES 核验全局图 470 节点/436 边；问答 9/10（90%）、平均 9.8s、P95 13.2s（问答实际走 DeepSeek Flash——qwen-plus 请求 10 次均 `Access to model denied`，定位为模型权限问题并固化「先单请求连通性测试」流程）
- **实验 B/C/D**：DeepSeek Flash 同批实验因 Redis pending 重放产生重复 chunks 被判定不可比（识别实验公平性破坏因素）；QW 干净知识库完整结果：479 实体/436 关系、问答 9/10、平均 8.0s、P95 10.1s
- **空图根因方法论**：「0 nodes, 0 edges」不能归因于文档量——区分模型返回空、输出格式不被解析器识别、抽取调用失败、原文无信息四类；实测 qwen-plus 可建图但慢、DeepSeek Flash 空图、GLM-5.2 稳定抽取成功 → 根因为 LLM 结构化输出稳定性
- **成功案例**：3 份地方法规库（GLM-5.2 抽取 + DeepSeek Flash 问答）完成解析入库、图谱生成、正式问答测评全流程
- **核验习惯**：图谱规模以 ES `knowledge_graph_kwd=graph` 直查为准（页面/API 有返回上限），不信任前端展示

## 四、后端可靠性工程

- **假死 worker 诊断（2026-08-14）**：前端图谱任务 0% → 交叉验证 MySQL（任务已创建）、Redis（写入成功、lag=1 未被领取）、worker 心跳（两 executor 心跳停在前一日、进程存活但 CPU≈0、线程数 216/329）→ 判定「进程活着、worker 失联」的假活状态
- **根因定位（4 条）**：队列后缀写死 `.common` 导致 common/graphrag/raptor 重任务互抢同一 Stream；图谱合并固定 180s 超时但实际需 215s，超时只包协程、底层 embedding 线程不可取消；ACK 仅在整个任务完成后执行，僵死 worker 的消息无法被接管；事件循环僵死无 watchdog
- **RAGFlow 内核修复（5 处源码）**：`common/settings.py` 队列按任务类型拆分（graphrag/raptor/mindmap 独立）；`docker/entrypoint.sh` 增加重任务专用 worker（单任务执行、embedding 并发限 4、线程池限 16、异常退出自动重启）；`task_executor.py` 独立 watchdog（事件循环 300s 无心跳输出线程栈并退出，由容器监督拉起）；`redis_conn.py` pending 接管（仅原 worker 心跳过期后可 claim）；`graphrag/general/index.py + utils.py` 合并超时按 embedding 工作量动态计算、单 embedding 请求限 120s、超时后取消清理
- **修复验证**：原卡住任务完成（187 节点/200 边/389 图谱 chunk 入库，合并 215s），Redis pending=0、lag=0，容器监督、Redis 接管测试通过；卡住消息从 common 原子迁移至 graphrag 队列并清理 3 条旧 pending
- **日常排查体系（命令级）**：Redis Stream 诊断（XLEN/XINFO GROUPS/XINFO CONSUMERS/XPENDING：lag 大=未被取走、pending 大=取走未 ACK、consumer idle 大=卡死）；worker 注册与心跳（SMEMBERS TASKEXE、ZREVRANGE 心跳 ZSET，30s 心跳/120s 死亡阈值）；MySQL document/task 表（run 状态、progress_msg 定位卡点阶段）；按 doc_id/task_id grep task_executor 日志
- **队列治理原则**：取消任务后 pending 残留需先确认任务真取消、只处理异常 executor 不随意重启全套；失败只重试失败文档不重提交整批；测试前确认队列健康

## 五、批量导入服务二次开发（自研导入管线）

- **需求（项目经理 2026-08-13）**：批量导入支持每阶段计时、随时开始/停止/重试、读写队列状态、提供接口——共 5 项可控性需求
- **原生接口实测（方案 A，100 份纯真 docx）**：上传 3.2s、解析墙钟 1104s、吞吐 0.091 份/s、成功率 100/100；**进度黑盒实证**：全程 536 次轮询 progress_msg 去重仅 4 种文本（排队类），前 483s 进度几乎不动；**取消实测**：整体 30% 时发取消，最终 0 份 CANCEL 全部 DONE（软取消只在阶段边界轮询，串行 embedding 检查点间文档已处理完）；无暂停、无单份重试、retry_count 字段存在但内核不消费 → 5 项需求满足度 1/5
- **自研导入服务开发（方案 B）**：设计 IngestPipeline 协议 + Orchestrator 编排（与 RAGFlow 原生 pipeline 同协议，保证 A/B 对比公平性）；四阶段（parse→chunk→embed→index）`time.time()` 精确计时写库；`Scheduler(max_concurrent=N)` 并发调度；失败隔离（单文档失败不拖累批次）；阶段级进度可视化（REST API + demo 前端页）；复用 RAGFlow 的 MinIO/ES/MySQL 存储；常驻服务形态（service.py + FastAPI REST + worker）
- **并发标定（1/3/6 × 50 份）**：吞吐 0.084/0.180/0.182 份/s → 并发 3 最优（较串行 2.1×，接近理论上限）；并发 6 无收益（+1%）但 embed avg 翻倍、长尾暴涨 60%（纯争抢开销）；embedding 占总耗时 93~95%，编排层无优化空间
- **自研服务并发 bug 定位**：MySQLRepository 用 `threading.local()` 每线程一连接，在 ThreadPoolExecutor 并发下连接断开（`'NoneType' object has no attribute 'status'`），`--persist --concurrency 3` 万份任务 7 份成功后全卡死；定位为连接非线程安全，测试期改 InMemory 模式绕开完成万份测试，给出连接池/per-task 连接修复方向
- **线上 500 修复**：上传暂存名 `{uuid8}_{原文件名}` 遇法律文档超长文件名超 Linux 255 字节上限（OSError Errno 36）导致整请求 500 → 暂存名改纯 uuid（32 字符），原文件名仅存 job 元数据
- **知识库管理**：脚本压测污染共享 KB（101 份脏数据）的教训 → 开发 `create_kb.py`（复用 RAGFlow service 层 `KnowledgebaseService` 建库，与 Web 建库完全一致；确认 ES index 为 tenant 级共用、MinIO bucket 首写自动建）→ 固化「每次测试新建 KB」流程
- **测试规范制定（与导师确认落档）**：100→1000→1万阶梯、全部走前端真实上传路径（测交付形态而非流水线极限）、阶段耗时从 `GET /ingest/jobs/{id}` 的 stages.duration_ms 提取、KB 命名规范
- **数据源核验**：定位「RAGFlow 页面显示 1.3 万份已解析」之谜——自研 writer 四阶段完成后直写 document 表 run=DONE（绕过 task_executor），叠加历史测试残留 → 确认 demo 页/服务/脚本三处数据源不同口径属正常

## 六、性能压测与 GPU 迁移优化

- **阶梯压测（Word，100/1000/10000 份）**：万份吞吐较百份下降 74%（0.18→0.046 份/s）；45 小时跑完、仅 6 份失败（0.06%）、失败隔离生效、进程零崩溃；观察到共享机吞吐随负载衰减（0.12→0.05 份/s）→ 结论「单次测量在共享机不可信」
- **瓶颈定位（长尾分析法）**：embedding 占总耗时 93.6%；万份 embed avg 仅涨 12% 但吞吐崩 74%，靠 p99/max 长尾分析（max 556s、p99 74.5s）+「墙钟 69% 时间在等长尾」差额法定位真凶为长尾阻塞并发槽——而非均值所暗示的均匀变慢
- **4090 GPU 迁移**：部署 RAGFlow + bge-gpu 后重跑同口径压测：吞吐 1.029 份/s（×5.7）、embed avg 15.3s→1.46s（×10.5）、max 72.8s→8.9s（长尾根治）；千份（服务前端路径）1000/1000 成功、吞吐 1.406 份/s、embed p99 2.38s、max 5.43s——GPU 独占下长尾不随规模放大，131 的规模退化在 4090 不存在
- **Amdahl 定律验证**：embed 占 93.6% 时单条提速 10.5×，理论吞吐上限 6.5×，实测 5.7×——差值定位为 index 写入；GPU 后瓶颈转移：embed 占比 93.6%→51.2%，index（ES bulk + MinIO + MySQL 三表）升至 42.7% 成为新瓶颈，明确下一阶段优化方向
- **两条口径**：脚本直调 1.029 vs 服务前端上传 0.786 份/s（-24%，worker 轮询 + 线程池反复创建 + /tmp 落地成本）——真实用户路径与极限压测分开度量
- **万份前端上传预案**：浏览器单次 fetch 文件数上限（1 万文件请求未达服务端）→ 分批上传预案（2000×5 批同 KB）

## 七、MinerU 扫描版 PDF 解析性能专项

- **任务**：生产投入前回答解析速度、瓶颈环节、不加机器的提速手段三个问题
- **实验设计（7 组，科学方法论）**：控制变量法（单文档类型/页数/并发/批量各为自变量）；重复测量（每组 ≥3 轮、首轮丢弃当预热、取中位数）；预设假设 H1~H7 明确接受/拒绝标准；最小二乘线性回归并报告 R²
- **测试数据**：基于 OmniDocBench v1.6 公开集构建 7 份单文档（D1~D7：1~100 页、纯文字/表格/公式/手写）+ 100 份异构单页 PDF
- **基线 Profiling**：单份 10 页纯文字 14.13s；页数近线性扩展；文档类型影响显著（表格 +46%、公式 +78%）
- **瓶颈定位（反直觉发现）**：OCR 仅占 <3% 不是瓶颈；真瓶颈为 API 通信固定开销（单份 42%，~6s/份）+ Layout/MFR 推理
- **批量队列建模**：T(N)=7.89+10.39×N（R²=0.9999），队列调度开销 <1%；批量提交较逐份快 26%（固定开销摊薄）；异构批量 1.39s/份（较单份快 5.2×），验证无跨文档缓存作弊
- **并发验证**：双 Worker 共享单卡加速 1.62~2.01×；加速比随页数增大不降反升（1.71→1.86→2.01，H5 被拒——pipeline 显存占用仅 ~2.5G/Worker，瓶颈在计算单元时分复用，页数越多并行重叠越长）；2×100 页无 OOM
- **优化交付**：批量提交 + Router 并发组合，100 份 10 页 PDF 解析约 24 分钟→约 9 分钟，零代码改动、无需额外 GPU；输出容量规划公式（按页数/份数预测任意规模耗时）
- **踩坑沉淀**：`--api-url` 模式 tqdm 在 docker logs 而非 CLI stderr；容器缺 bc 改整数运算；Router 端口需 host IP；hybrid-engine 需运维补配 VLM 路径；HuggingFace 网络超时用已缓存图片离线构建测试集
- **产出**：性能报告（面向领导）、实验记录、复现指南、术语对照表、源码级架构理解文档（760 行）、全部脚本与数据

## 八、端到端验证与交付物

- **4090 PTR 真实手册端到端验证（2026-09-26，简历新口径）**
  - 环境：4090 本地（排除网络 RTT）；Qwen3.8-27B-AWQ-INT4 + vLLM TP2（max_num_seqs=8、prefix_caching/chunked_prefill on、enable_thinking=false）；RAGFlow Chat top_k=1024 / top_n=6 / 相似度阈值 0.1 / 向量权重 0.3；bge-base embedding；文档为 PTR 冷却泵设备运行与维修手册（真实核电设备文档）
  - 建图：DeepDOC 解析 42.7s → 116 raw chunks 入 ES；第一次 GraphRAG 因模型实例名 qwen38-local 未找到全部失败（CONNECTION_ERROR），修复后 116 chunks 合并为 17 个抽取单元、每 chunk 1 次 gleaning，1310.67s（21.8 分钟）完成 **979 nodes / 719 edges**、约 90 万 tokens；图转换 1700 chunks（90s）写入 ES（8.5s）
  - 检索对比：纯向量检索最高相似度 0.331；KG 检索（use_kg=true）0.464（**+40%**），精准命中设备供货边界表（额定流量 640m³/h、扬程 36m）
  - 端到端 QA：7.1s（含网络往返），答案准确（640m³/h、36m、型号 HTJ300-400C、转速 1480r/min），带 [ID:1][ID:2] 引用可溯源
  - 延迟基准（多次实测）：纯 LLM 短回答 470~527ms、流式 TTFT 136~174ms；向量检索 avg 563ms、KG 检索 avg 1240ms；**E2E 流式 TTFT 简单 0.9s（≤2s ✅）/ 复杂 0.94s（≤5s ✅）**；E2E 非流式简单 avg 5.79s（2.9× 超标）/ 复杂 avg 15.4s（3.1× 超标）
  - 耗时分解：简单问答 LLM 生成占 70%、复杂占 96.5%（检索仅 2~19%）——瓶颈为 LLM 生成（72~75 tok/s 属正常，问题是生成 token 量大），非检索
  - 优化方案（P0~P3，方案未落地）：P0 启用流式 + 限制 max_tokens（128~256）；P1 简化 system prompt、top_n 6→3~4；P2 vLLM max_num_seqs 8→16、小模型处理简单问答；P3 GPU1+2 部署第二模型做大小分流（简单 14B / 复杂 27B）。预估三管齐下简单 ~2~2.5s、复杂 ~5~6s
- **端到端评测（131 环境旧口径，口头弹药）**：固定题集（10 题）+ 人工标准答案，问答 10/10 全对、平均响应 3.7s、P95 5.5s；对照项目「常规问答 ≤2s / 复杂 ≤5s」采购要求提供效果基线（团队基准结论：独立检索 P50 1.58~2.38s 达标，端到端瓶颈在外部 LLM 生成，占 86~91%）
- **评测规范**：严格区分抽取模型与问答模型变量（qwen-plus 问答被拒后切 DeepSeek Flash 的事例固化为「先单请求连通性/权限验证」流程）；准确率基于预设问题+人工标准答案而非「看起来对」
- **交付物清单**：6 份 HTML 测试报告（含总索引与互链导航）+ Markdown 压测/决策/踩坑/测试规范文档 + 全部压测 JSON 源数据（万份 3MB）+ 可复用脚本（原生接口测试、并发压测、数据预筛、建库、报告生成、端口转发）+ 1000 份干净可复现测试集 + 4090 部署交接文档

## 技能栏（详细版口径）

RAGFlow（源码级）/ GraphRAG·LightRAG / MinerU / LangGraph / bge / FastAPI / Redis Stream / Elasticsearch / MinIO / MySQL / Docker / GPU 部署与资源规划（4×4090，与 vLLM 共存）/ 性能压测与长尾分析（p99/max、控制变量、假设检验、线性回归建模）/ 分布式任务队列排障
