# 03 GraphRAG 原理与空图问题

> → 深度版见 [QA问答_全链路口语版.md](../QA问答_全链路口语版.md) 环节⑦（GraphRAG建图全流程，含T6实测数据）

## 一句话答案（电梯版）

GraphRAG 把 chunk 喂给 LLM 抽成实体和关系，先形成文档级子图再合并为知识库级全局图，检索时用实体/关系/社区报告补充上下文——它解决普通 RAG「全局问题召回不了」的缺陷。我定位过它的空图问题：根因是 LLM 结构化输出稳定性，不是文档规模。

## 2 分钟展开版

**构建链**：
```
chunk（按 token 合并成抽取单元）
→ LLM 按 prompt 要求输出 JSON：实体（名称/类型/描述）+ 关系（源/目标/描述/权重）
→ gleaning：抽完问一遍"有遗漏吗"再补一轮（我实测每单元 1 次，成本计入 90 万 tokens）
→ 文档子图（node-link JSON，作为特殊 chunk 入 ES）
→ 全局合并：知识库级锁 → 同名实体合并 → 关系权重累加 → PageRank 重算
→ 可选：实体消歧（默认关）、Leiden 社区发现（默认关！）
```

**检索链**：问题 → LLM 分析查询实体 → entity/relation chunk 检索 → N-hop 扩展 → 社区报告 → 组装上下文。

**关键事实**（读源码确认的）：
- 主图不存 Neo4j，是序列化成特殊 chunk 写回同一个文档引擎（`knowledge_graph_kwd` 区分 graph/subgraph/entity/relation/community_report）
- **社区报告和实体消歧默认关闭**——全局问题测试前必须确认开启，否则测出"KG 无优势"是配置假阴性
- 社区报告是 LLM 摘要，适合主题概括，不能替代工程参数原文

## 空图根因（我实际踩过的坑）

「0 nodes, 0 edges」四类可能：模型返回空 / 输出格式不被解析器识别 / 调用失败 / 原文无信息。我的实测结论：
- qwen-plus：能建图但慢
- DeepSeek Flash：空图（格式遵循差）
- GLM-5.2：稳定成功 → **根因 = 模型结构化输出稳定性，与文档量无关**
- 4090 上又一次实证：模型实例名配错（qwen38-local 未找到）→ 全部 CONNECTION_ERROR，修复后成功

## 深挖自测（先遮住答案）

**Q1: 实体定义为什么重要？**
A: prompt 里的实体类型清单决定模型抽什么。RAGFlow 默认通用类型（人/地/组织），不匹配核电业务（设备/参数/部件）——这就是二开边界里 PBS 层级问题的根源。类型太窄漏抽、太宽噪声。

**Q2: 怎么核验图谱真实规模？**
A: 直查 ES `knowledge_graph_kwd=graph` 的记录——页面/API 有返回上限，前端展示不可信。

**Q3: 我的量化证据？**
A: 4090 PTR 真实手册：KG 检索最高相似度 0.464 vs 纯向量 0.331（+40%），精准命中设备供货边界表（额定流量 640m³/h、扬程 36m）。T1 全局问题对比已完成（8 题：局部 +40% / 全局无优势）。T6 Light vs General 对比已完成：General 模式生成 121 社区报告，KG 检索 delta avg +0.61（10 题相似度全部从 ~0.37→1.0），Light 模式 delta=0。详见 [T6报告](../../测试报告/T6_Light_vs_General_GraphRAG对比报告.md)。

## 我项目里的数字

- 1 份 PTR 手册（116 chunks → 17 个抽取单元 + gleaning）→ 979 nodes / 719 edges，1310.67s，约 90 万 tokens
- 131 上 10 份法规库（qwen-plus）→ 470 nodes / 436 edges

## 来源

- [更完整的实习记录.md §15](../../实习记录/更完整的实习记录.md)（GraphRAG 数据流源码级）
- [解决后端问题0902-0905.md §2.4](../../实习记录/解决后端问题0902-0905.md)（空图模型对比）
- [GraphRAG全流程原理.md](../../知识库/03_GraphRAG/GraphRAG全流程原理.md)（六阶段源码级）
- [T6_Light_vs_General_GraphRAG对比报告.md](../../测试报告/T6_Light_vs_General_GraphRAG对比报告.md)（Light vs General 实测）
- 源码：`ragflow-main/rag/graphrag/light/graph_prompt.py`（提示词）、`graph_extractor.py`（解析）、`general/index.py`（合并）
