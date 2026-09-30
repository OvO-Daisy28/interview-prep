# doc/design 文档索引

> 按 131 / 4090 / 共用 三类组织。测试报告分服务器放子目录，设计文档留根。

## 131_测试/（131 服务器 CPU 测试报告，7 个）

131（10.126.2.131）RAGFlow v0.26.1 CPU bge-base 的批量导入测试产出。

| 文件 | 内容 |
|---|---|
| [实验数据汇总_20260911.md](131_测试/实验数据汇总_20260911.md) | 5 次实验汇总 + 万份变慢根因分析（CSV + Markdown，脚本 `experiments_summary.py` 生成） |
| [批量上传测试总索引_20260908.html](131_测试/批量上传测试总索引_20260908.html) | 09-07~08 两天测试全过程索引页，含时间线 + 4 份子报告链接 |
| [RAGFlow原生批量上传测试_20260908.html](131_测试/RAGFlow原生批量上传测试_20260908.html) | 方案A（原生 API）100 份：吞吐 0.091 份/s、取消不生效 |
| [方案B并发压测_20260908.html](131_测试/方案B并发压测_20260908.html) | 方案B（mentor 自建）并发 1/3/6：并发3 最优 0.180 份/s |
| [RAGFlow原生局限与mentor方案结论_20260908.html](131_测试/RAGFlow原生局限与mentor方案结论_20260908.html) | 原生六大局限 + 方案B解决矩阵 + 选型建议 |
| [批量导入规模验证_20260907.html](131_测试/批量导入规模验证_20260907.html) | mentor 千份 baseline（job 35/37）：0.25 份/s，失败 20.4% |
| [万份稳定性压测_20260911.html](131_测试/万份稳定性压测_20260911.html) | 1 万份长跑：0.046 份/s（降 74%），59.7h，embedding 长尾根因 |

> 6 个 HTML 顶部导航栏互链（同目录相对路径），从总索引页可跳转全部子报告。

## 4090_测试/（4090 服务器 GPU 测试，2 个）

4090（10.148.4.21）RAGFlow v0.26.1 GPU bge-base（bge-gpu 容器，GPU2 cuda:0）的测试产出。

| 文件 | 内容 |
|---|---|
| [4090_GPU压测_20260911.md](4090_测试/4090_GPU压测_20260911.md) | 100 份并发3：吞吐 1.029 份/s（比 131 快 5.7×），embed 瓶颈消除，index 成新瓶颈；含 mentor 服务 vs 脚本对比 |
| [4090_决策与踩坑记录_20260911.md](4090_测试/4090_决策与踩坑记录_20260911.md) | 部署 mentor 服务的 6 项决策 + 9 个踩坑 + 命令速查 |

## 共用设计文档（留根，11 个）

不特定于某台服务器，跨 131/4090 的架构/范围/接口设计。

| 文件 | 内容 |
|---|---|
| [architecture.md](architecture.md) | 系统架构蓝图：7 子系统 + RAGFlow 定位 |
| [demo-scope-and-acceptance.md](demo-scope-and-acceptance.md) | Demo 范围与验收基线 |
| [二次开发范围分析.md](二次开发范围分析.md) | 技术规范书 vs RAGFlow 原生能力逐条对照 |
| [ingest-orchestration.md](ingest-orchestration.md) | 批量导入编排接口设计 |
| [interface-inventory.md](interface-inventory.md) | 接口与数据库清单 |
| [pbs-and-layering.md](pbs-and-layering.md) | 分层组织与 PBS 设计 |
| [progress-board.md](progress-board.md) | 开发进度看板 |
| [ragflow-dev-research.md](ragflow-dev-research.md) | RAGFlow 二开研究计划 |
| [test-plan.md](test-plan.md) | L1-L5 五层测试策略 |
| [infrastructure-reuse-feasibility.md](infrastructure-reuse-feasibility.md) | RAGFlow 基础设施复用可行性查证（131 实地） |
| [ragflow-modification-candidates.md](ragflow-modification-candidates.md) | RAGFlow 二开候选清单 C1-C5（含 131 数据） |

## 关联的测试数据

测试报告引用的 JSON 产出在 `test/results/` 下同样按服务器分：
- `test/results/131_测试/`：bench_c1/c3/c6/10k.json、native_r1/cancel.json + 日期/功能子目录
- `test/results/4090_测试/`：bench_gpu_c3.json
- 留根：`ab_doc_list*.json`（文档清单，两台共用）、`experiments_summary.csv`（131 专属汇总）
