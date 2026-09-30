---
title: 中广核采购文件活化项目 · 全链路开发（需求分析+开发启动）
source: 工作项目
author: 项目经理（中广核需求）× 自研复现
collected: 2026-07-31
updated: 2026-08-11
stack: [RAGFlow, GraphRAG, MinerU, 知识图谱, 普通RAG, 内容解析, 手册生成, LLM私有化]
status: development_starting
---

# 项目描述

中广核「采购文件活化项目」——把核电工程文件（以设备运维手册 EOMM 为典型，约数十类、太平岭一期 30w+ 份）做成数字化闭环：**解析入库 → 治理 → 生成新文件**。

**当前阶段（2026-08-11 起更新）**：可行性评估已完成（结论：部分满足），项目已进入招投标后开发启动阶段。项目经理最新要求：按技术规范书（附件1，44页）进行正式开发，RAGFlow 作为后端服务交付，不满足的需求在 RAGFlow 基础上二开。

技术规范书定义了 7 个子系统：内容解析、知识库与知识图谱、规则梳理与建模、内容数据库、内容治理、手册生成、AI辅助编辑。RAGFlow 核心覆盖"知识库与知识图谱"子系统，其余子系统需新建或二开。详见 `doc/design/二次开发范围分析.md`。

项目经理的核心需求一句话：**按技术规范书开发完整系统，RAGFlow 作为知识库/图谱后端，不满足的部分二开或新建**。

**关键约束（甲方指定）**：
- 本次项目经理评估重点不是预设 GraphRAG 优于普通 RAG，而是给出文档规模、查询效率、RAGFlow 定开能力和新增文档更新方式的证据与可行性结论。
- 最终结论允许为“部分满足”；真实 PTR 材料无需脱敏；演示入口使用 RAGFlow Web 界面。
- 技术栈建议 **RAGFlow + MinerU**，三引擎协同（大模型 + 传统程序 + 知识库/知识图谱）。若换栈须证明核心指标不低于 RAGFlow/MinerU 并经甲方评审。→ **demo 直接用甲方已部署的 RAGFlow，不另起炉灶**。
- 已部署环境：`http://10.126.2.131:9388`（内网，本地 CLI 实测 HTTP 200 可达；账号见沟通记录，走 .env 不进 git）。

**GraphRAG 是本项目出彩点**：需求原文明确要「局部问题精准定位 / 全局问题用图的社区发现算法跨章节汇总」——这正是 GraphRAG 相对普通 RAG 的经典卖点，demo 里最能打动评审的对比。

# 与能力建设规划的对应（北极星对齐）
> 本项目对标 [4个月能力建设规划](../target/capability-building-plan.md) **阶段4：RAG 进阶（W12-W13）**，且是插队的真实工作项目（招投标有时限）。
- 训练能力维度：**可验**（普通 RAG vs GraphRAG 检索效果对比）、**成本/方案直觉**（RAGFlow 能否满足 = 选型决策）。
- 与规划的差异：规划里 RAG 进阶是"升级农业项目"，这里是"评估甲方指定平台 RAGFlow"——同一知识点（GraphRAG / 混合检索 / RAG 评测）的不同落地，沉淀时并入根 [learn/](../learn/)。
- **插队理由**：真实招投标项目、半个月硬时限，价值高于规划节奏，值得先做；不脱离北极星（仍是 RAG 能力建设）。

# 知识点清单（引用根 learn/，标注复现优先级）

**本次 demo 核心（P0）**
- [ ] [GraphRAG](../learn/graphrag.md)：局部检索（实体定位）+ 全局检索（社区发现跨章节汇总），本项目最核心卖点
- [ ] 普通 RAG（向量检索）：作为 GraphRAG 的对照组，同一批文档同一批问题对比效果
- [ ] RAGFlow 平台能力评估：文档解析（MinerU 版面分析）、知识库构建、GraphRAG 开关、检索问答——**评估它能否满足需求**（甲方核心诉求）

**理解原理用（P1，轻量自搭补充）**
- [ ] RAG vs GraphRAG 的原理差异：为什么全局性问题普通 RAG 召不回、GraphRAG 靠图社区能汇总（用极简自搭跑通一遍，吃透而非只会点 RAGFlow 界面）

**了解边界即可（P2，本 demo 不做，需求里有但非本次范围）**
- 内容解析入库 / 内容治理 / 手册生成 / AI 辅助编辑（需求 7 子系统的其余部分，招投标 demo 阶段不展开）
- 时序知识图谱、版本管理、术语标准化（远期，非检索演示核心）

# 落地顺序（1 天 demo，RAGFlow 为主 + 轻量自搭理解原理）
```
前置（待客户/项目经理提供）
  ├─ 真实文档：1-2 份设备运维手册 EOMM（见 doc/客户/需求分析/文档清单）
  └─ RAGFlow API Key：web 界面登录后生成（自动化建库/问答用）
      ↓
① RAGFlow 建库：上传文档 → MinerU 解析 → 建普通 RAG 知识库
② 开 GraphRAG：同批文档建 GraphRAG 库（RAGFlow 内置开关）
③ 设计对比问题集：局部问题（某设备参数）+ 全局问题（跨章节汇总）各几条
④ 跑问答 + 截图：普通 RAG vs GraphRAG 同问题对比，凸显 GraphRAG 全局优势
⑤ 轻量自搭（时间够则做）：极简 RAG/GraphRAG 代码跑通一遍，吃透原理
      ↓
对照 demo 与项目经理做业务沟通（RAGFlow 能否满足、缺口在哪）
```
原则：**先用已部署 RAGFlow 快速出可截图的效果对比**（招投标要的是演示），自搭只为吃透原理，不喧宾夺主。真实文档要不到就用公开设备手册 PDF 兜底（见文档清单）。

# 复现状态
- [x] 需求消化（docx 提取全文 + 项目经理沟通记录）
- [x] RAGFlow 连通性探测（本地 CLI HTTP 200 可达，API 需 Key）
- [x] 需求文档清单整理（doc/客户/需求分析/，供索取真实样本）
- [x] 前置：真实文档（PTR冷却泵手册）+ RAGFlow API Key 已拿到
- [x] RAGFlow 普通 RAG 库建成（162 chunks，run=DONE）
- [x] GraphRAG 业务链路修复：Prompt 示例污染、社区稳定 ID、worker 模型覆盖、Chat KG 模型复用
- [x] GraphRAG 真实重建完成：`progress=1.0`，256 nodes / 128 edges，41 条有效社区报告
- [x] 社区三层验收：41/41 唯一 ID、来源正确、污染词 0、显式 KG retrieval 成功
- [x] 修复后固定题集：7/7 API/答案级成功，Q5/Q6 有效，首条引用均为 KG 聚合块
- [x] 踩坑文档、验收 SSOT、规模评估、ADR 和修复证据落盘
- [x] RAGFlow Web 根入口可达（HTTP 200）
- [ ] Web 现场终验：图谱/社区渲染、Q5/Q6、引用展开
- [ ] 1/10/100 份阶梯压测；当前不得外推百份、万份或 30 万份能力
- [ ] 与项目经理业务沟通：结论为“部分满足”

# 目录说明（本项目专属）

```text
GCN_Poc/
├── CLAUDE.md
├── doc/
│   ├── design/      # 现在时架构、范围与验收蓝图（architecture / demo-scope-and-acceptance / 二次开发范围分析）
│   ├── learn/       # 项目专属：ragflow_operations（SSOT 运维/故障手册）+ RAGFlow 学习计划草案（2周指南、实习生3天计划，HTML）
│   ├── 客户/        # 原始需求、沟通记录和真实测试材料
│   └── 调研/        # 131 资产、历史方案、规模可行性评估、solutions 参考条目库
├── code/
│   ├── README.md
│   ├── pyproject.toml / uv.lock / .python-version
│   ├── ragflow_client.py      # API 客户端
│   ├── rebuild_graph.py       # 有破坏性的受控重建
│   ├── monitor_graphrag.py    # 只读任务监控
│   ├── ssh_ops.py             # 服务器检查与 worker 运维
│   ├── solution_collector.py  # 解决方案参考条目收集器（add/list/search/export/seed，落 doc/调研/solutions/）
│   └── patches/               # RAGFlow 服务器源码补丁、前后版本、diff 和哈希
├── test/
│   ├── run_demo.py            # 固定题集问答与答案级错误识别
│   ├── validate_graphrag.py   # 任务、图主体、社区落库和污染检查
│   ├── compare_kg_retrieval.py# use_kg=false/true 检索对照
│   └── results/               # 按 131_测试/ 4090_测试/ 分服务器保存 JSON/JSONL；共用清单留根
└── memory/
    └── decisions.md           # 关键决策 ADR，只增补决策，不写流水账
```

目录边界：

- 项目根不设 `outputs/`；运行证据按服务器分入 `test/results/131_测试/` 或 `test/results/4090_测试/`，早期 GraphRAG 评测在 `131_测试/2026-08-04/` 等日期子目录；共用清单（`ab_doc_list*.json`）留根。
- `doc/design/` 下按服务器分 `131_测试/` `4090_测试/` 子目录放测试报告，共用设计文档留根；`doc/design/INDEX.md` 是导航索引。
- 服务器源码快照和补丁是可复用代码资产，进入 `code/patches/<版本-日期>/`，不与测试输出混放。
- `doc/design/` 只写当前系统状态和目标蓝图；历史选择及其理由进入 `memory/decisions.md`。
- `doc/learn/ragflow_operations.md` 是环境变量名、API、SOP、故障根因与回滚边界的 SSOT，不保存真实密钥。
- 一次性 debug 脚本和 `__pycache__` 不保留；可复用脚本必须在本节登记。
