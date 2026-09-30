# 01 RAG 全链路

> → 深度版见 [QA问答_全链路口语版.md](../QA问答_全链路口语版.md) 环节⓪~①（全链路概览+离线链路）

## 一句话答案（电梯版）

RAG 分离线和在线两条链：离线把文档「解析→分块→向量化→写入索引」，在线把问题「向量化→混合检索→拼上下文→LLM 生成→引用回填」。我在项目里把两条链都跑通并压测过每个环节的耗时。

## 2 分钟展开版

**离线链路（ingest，我压测的主战场）**：
```
上传文件 → 对象存储保存原件 + MySQL 建元数据
→ 提交解析任务 → Redis Stream 队列
→ Task Executor 消费 → 解析器（DOCX/DeepDOC/OCR）→ 分块
→ Embedding 向量化 → chunk + 向量写入 ES → 文档状态 DONE
→ （GraphRAG：基于 chunk 做 LLM 实体关系抽取 → 子图 → 全局图合并）
```

**在线链路（检索问答）**：
```
用户问题 → 问题向量化 → 向量检索 + BM25 全文检索（混合）
→ 可选 Rerank → Top-K chunk → 拼 Prompt → LLM 生成 → 引用匹配回填
```

**关键分工**（很多人混淆的点）：
- API 服务只收请求、建任务、查状态；真正干活的是后台 Task Executor
- 上传成功 ≠ 解析完成；解析完成 ≠ 图谱完成——三个独立阶段
- Embedding 模型管「文本→向量」，LLM 管抽取和生成，indexing 是写索引不是模型

## 深挖自测（先遮住答案）

**Q1: chunk 怎么切的？**
A: RAGFlow 按 token 数切（我用 chunk_token_num=512），解析时带版面信息（标题/段落/表格），chunk 保留 page_num、position 等定位字段用于引用溯源。

**Q2: 混合检索怎么混合的？**
A: 向量相似度 + BM25 全文匹配加权融合（我测试时 vector_similarity_weight=0.3），再过 similarity_threshold 过滤，可选 rerank 模型精排。

**Q3: GraphRAG 建在哪一层之上？**
A: chunk 之上——不直接解析原文建图，而是读已入库的 chunk 做 LLM 抽取。所以解析失败必然导致建图失败（0 chunks 可用）。

**Q4: 前端进度卡住说明什么？**
A: 不能只看前端。要分层查：MySQL task 表状态 → Redis 队列 lag/pending → worker 心跳 → 日志。可能任务没被取走、可能取走卡住、可能 worker 假死、可能图谱任务启动时 chunk 还没就绪。

## 我项目里的数字

- 全链路各阶段耗时占比：Embedding 93.6%（131 CPU）→ 51.2%（4090 GPU）→ 瓶颈转移到 index 写入 42.7%
- 端到端延迟分解：检索 0.56~1.24s，LLM 生成占 70~96.5%

## 来源

- [更完整的实习记录.md](../../实习记录/更完整的实习记录.md)（链路架构详解）
- [RAGFlow队列机制原理.md](../../知识库/02_任务队列与可靠性/RAGFlow队列机制原理.md)（队列机制+排查附录）
