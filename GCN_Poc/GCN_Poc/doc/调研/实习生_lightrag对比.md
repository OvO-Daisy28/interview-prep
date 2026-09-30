---
title: 实习生 RAG 系统对比调研（飞书文档存档）
source: https://ecny5mm0vkde.feishu.cn/wiki/OCtnwtRkoiGMiXk8z0OcXi1PnnM
author: 雯婷（zwt）
collected: 2026-07-31
status: 已完成（法律域，50条balanced测试集，6+系统对比）
---

# LightRAG进一步调研

> 本文档是从飞书知识库原样提取的实习生调研报告，包含完整的实验设计、脚本路径、结果数据和结论分析。
> 原文嵌入的6个电子表格已展开为markdown表格，数据无省略。

## 一、背景

目前已完成普通 RAG、LightRAG、GraphRAG-SDK 三套方案的初步部署和对比实验。现在仍需要继续确认两个问题：

1. LightRAG 在当前业务数据上是否真的能带来更好的问答准确度；
2. 如果效果和速度可接受，是否具备系统化改造为产品级知识库系统的可行性。

需要评估的系统化改造方向包括：

1. 支持多并发；
2. 支持多租户、多知识库检索（知识库分开）；
3. 支持源文件查看、引用溯源、上传删除后同步更新图谱；
4. 支持全过程可观测，包括文档解析、分块、实体关系抽取、检索过程等。

## 二、当前阶段结论分析

- LightRAG 在复杂知识检索、跨文档关系、上下文召回方面可能有优势；
- 我做的 普通 RAG 当前只是 FAISS Top-K baseline，尚未加入 rerank，因此还不是强基线。graphrag-sdk 的对比模型是强基线rag所以比较高；
- 当前 LightRAG 只主要验证了 hybrid 模式，还没有验证官方支持的 mix、naive、local、global 等模式（这些是 LightRAG 查询时采用的不同检索策略：naive 更接近普通 RAG，主要做原文 chunk 向量检索；local 偏具体实体及其局部关系检索；global 偏全局主题和跨文档关系检索；hybrid 是 local+global；mix 是 local+global+naive。不同模式适合的问题类型不同，因此只了测 hybrid ；
- 当前 LightRAG 的耗时统计来自 RAGAS 评估脚本。为了让 RAGAS 评分，对同一个问题调用了两次 LightRAG：第一次使用 `only_need_context=True` 单独获取检索上下文，第二次使用 `only_need_context=False` 获取最终回答。因此当前统计的总耗时是两次调用耗时之和，可能高于真实产品场景下的一次问答耗时。后续需要单独补测产品模式下"一次 query 返回答案"的实际耗时。

### LightRAG 查询模式说明

| 模式 | 含义 | 适合问题 |
| --- | --- | --- |
| naive | 类似传统向量 RAG，只检索文本 chunk，不使用图谱 | 单条事实、明确条文类问题 |
| local | 围绕具体实体及其局部关系检索 | 某个概念、主体、条款相关问题 |
| global | 偏全局主题、跨文档关系和总结 | 跨法规比较、总结归纳类问题 |
| hybrid | local + global | 既有实体又需要综合关系的问题 |
| mix | local + global + naive | 更完整的混合检索，适合通用问答 |
| mix + rerank | 多路召回后再重排 | 可能是 LightRAG 的更强配置，但会增加耗时 |

## 三、当前实验结果解读

### 当前对比普通 RAG

当前普通 RAG 是自定义实现的 FAISS Top-K 检索流程：

文档读取 → chunk 切分 → embedding → FAISS 向量索引 → Top-K 检索 → 拼接上下文 → qwen-plus 生成回答。

当前普通 RAG 没有 reranker，不是外部 benchmark 中常见的 "RAG with rerank"。

FalkorDB/GraphRAG-SDK benchmark 里提到的普通 RAG 是带 rerank 的 Vector RAG 强基线，而当前普通 RAG 是基础 FAISS Top-K baseline，两者不能直接等同。

### LightRAG 当前结果

已有 50 条中文法律法规测试中，LightRAG 的表现可以拆成两部分看：

优势：
- answer relevancy 较高，说明回答更贴近用户问题；
- context precision 较高，说明检索出的上下文更精准；
- context recall 较高，说明检索结果对参考答案的覆盖较完整；
- semantic similarity 较高，说明回答与参考答案语义接近。

问题：
- factual correctness 较低，说明最终回答中的事实点和参考答案还不够一致；
- faithfulness 没有超过普通 RAG，说明回答对检索上下文的忠实度还需提升；
- 平均耗时较高，目前统计的 LightRAG 总耗时明显高于普通 RAG。

因此，当前结果说明 LightRAG 的"检索阶段"有优势，但这些优势还没有稳定转化为"最终事实正确性"的优势。

### 实验结果和 FalkorDB/GraphRAG-SDK 官网 benchmark 对比

1. 数据集不同：FalkorDB benchmark 使用 GraphRAG-Bench 的 Novel 和 Medical 数据集；我们当前使用的是中文劳动法律法规数据集。
2. 普通 RAG 强度不同：benchmark 里的普通 RAG 是 RAG with rerank；我们当前普通 RAG 是 FAISS Top-K，尚未加入 rerank。
3. 评估指标不同：GraphRAG-SDK benchmark 中的核心准确性指标是 ACC，可以理解为"最终答案正确性分数"。它不是单纯看检索上下文，也不是只看语义相似度，而是综合评估系统回答和标准答案在事实点和语义上的一致程度。根据其 benchmark 文档，ACC 主要由两部分组成：75% 来自 factuality F1，即系统回答和标准答案的事实点是否一致；25% 来自 semantic similarity，即系统回答和标准答案整体语义是否接近。因此，GraphRAG-SDK 的 ACC 更接近实验 RAGAS 中的 factual_correctness 和 semantic_similarity 的组合，其中更偏向 factual_correctness。从实验结果来看（第一行是simplerag 第二行是lightrag 第三行是graph-sdk）只看这两个指标的话确实lightrag的hybrid模式表现的确实没有强基线rag好。

| 系统 | avg_factual_correctness | avg_semantic_similarity |
| --- | --- | --- |
| SimpleRAG | 0.5240 | 0.7982 |
| LightRAG | 0.3028 | 0.8761 |
| GraphRAG-SDK | 0.5878 | 0.8823 |

4. LightRAG 配置不同：LightRAG 的效果受 query mode、embedding、LLM、chunk 策略、rerank、prompt、上下文 token 限制等因素影响。当前验证的是 hybrid 模式，还没有完整验证 mix、naive、local、global 等模式。

## 四、当前补充实验进展

### 重新设计并生成 balanced 测试集

旧测试集虽然有 50 条中文法律法规问题，但问题结构偏简单（simple 56%、medium 26%、complex 18%），且全部来自 single-hop 问题生成方式，不能充分体现 LightRAG / GraphRAG 在复杂知识检索场景下的优势。

重新设计为 balanced 测试集：simple 15条 / medium 20条 / complex 15条。

- 生成脚本：`/data/zwt/rag_eval/scripts/generate_balanced_ragas_testset.py`
- 新测试集：`/data/zwt/rag_eval/data/testsets/legal_ragas_cn_50_balanced.jsonl`
- 基于5个法律法规文本按法条级切分，共315个article

### 补充普通 RAG baseline 与普通 RAG + rerank 强基线实验

**普通 RAG baseline**：FAISS Top-K=3，无reranker
- 脚本：`/data/zwt/simple_rag/batch_eval_legal_balanced.py`
- 输出：`/data/zwt/rag_eval/outputs/simple_rag_answers_balanced.jsonl`

**普通 RAG + rerank**：FAISS初筛Top-20 → bge-reranker-v2-m3重排 → 取Top-3
- 脚本：`/data/zwt/simple_rag/batch_eval_legal_rerank_balanced.py`
- reranker模型：`/data/zwt/models/bge-reranker-v2-m3`
- 输出：`/data/zwt/rag_eval/outputs/simple_rag_rerank_answers_balanced.jsonl`
- 踩坑：服务器无法访问HuggingFace，改用ModelScope下载；FlagReranker加载bge-reranker-v2-m3有tokenizer兼容问题，改用transformers直接加载

### 补充 LightRAG hybrid 模式实验

**双调用评估**（RAGAS质量评估用）：
- 脚本：`/data/zwt/rag_eval/scripts/run_lightrag_hybrid_balanced.py`
- 输出：`/data/zwt/rag_eval/outputs/lightrag_hybrid_answers_balanced.jsonl`

**单次问答耗时评估**（产品模式耗时统计）：
- 脚本：`/data/zwt/rag_eval/scripts/run_lightrag_hybrid_single_latency_balanced.py`
- 输出：`/data/zwt/rag_eval/outputs/lightrag_hybrid_single_latency_balanced.jsonl`
- 注意：运行前需清理LLM response cache（`kv_store_llm_response_cache.json`清空为`{}`）

### 补充 LightRAG hybrid + rerank 实验

- 脚本：`/data/zwt/rag_eval/scripts/run_lightrag_hybrid_rerank_balanced.py`
- 支持两种任务模式：`--task eval`（质量评估）/ `--task single`（耗时统计）
- reranker运行在CPU上，每条问题额外增加约2秒
- 输出：
  - 质量评估：`/data/zwt/rag_eval/outputs/lightrag_hybrid_rerank_answers_balanced.jsonl`
  - 耗时统计：`/data/zwt/rag_eval/outputs/lightrag_hybrid_rerank_single_latency_balanced.jsonl`

### 补充 LightRAG mix 模式实验

mix模式 = local + global + naive，比hybrid更综合。

- 双调用评估脚本：`/data/zwt/rag_eval/scripts/run_lightrag_mix_balanced.py`
- 单次耗时脚本：`/data/zwt/rag_eval/scripts/run_lightrag_mix_single_latency_balanced.py`
- 输出：
  - `/data/zwt/rag_eval/outputs/lightrag_mix_answers_balanced.jsonl`
  - `/data/zwt/rag_eval/outputs/lightrag_mix_single_latency_balanced.jsonl`

### 补充 LightRAG mix + rerank 实验

- 脚本：`/data/zwt/rag_eval/scripts/run_lightrag_mix_rerank_balanced.py`（支持`--task eval`和`--task single`）
- 输出：
  - `/data/zwt/rag_eval/outputs/lightrag_mix_rerank_answers_balanced.jsonl`
  - `/data/zwt/rag_eval/outputs/lightrag_mix_rerank_single_latency_balanced.jsonl`

### 关键路径汇总

| 组件 | 路径 |
| --- | --- |
| LightRAG服务目录 | `/data/zwt/lightrag_my_bge` |
| LightRAG工作目录 | `/data/zwt/lightrag_my_bge/rag_storage` |
| LightRAG服务地址 | `http://127.0.0.1:9622/query` |
| 评测脚本目录 | `/data/zwt/rag_eval/scripts/` |
| balanced测试集 | `/data/zwt/rag_eval/data/testsets/legal_ragas_cn_50_balanced.jsonl` |
| 评测输出目录 | `/data/zwt/rag_eval/outputs/` |
| reranker模型 | `/data/zwt/models/bge-reranker-v2-m3` |
| LLM cache清理 | `/data/zwt/lightrag_my_bge/rag_storage/kv_store_llm_response_cache.json` |

## 五、实验结果数据

### 六种系统真实一次查询耗时对比

| 系统 | 样本数 | 平均耗时/s | 中位数/s | P90/s | P95/s | P99/s | 最小耗时/s | 最大耗时/s | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rag | 50 | 1.51 | 1.22 | 2.03 | 2.95 | 6.21 | 0.79 | 7.81 | ok |
| rag_rerank | 50 | 8.25 | 7.94 | 9.45 | 10.29 | 13.82 | 6.85 | 16.67 | ok |
| lightrag_mix | 50 | 15.1 | 13.67 | 25.01 | 26.06 | 28.56 | 7.35 | 29.63 | ok |
| lightrag_hybrid | 50 | 16.25 | 12.81 | 27.11 | 31.27 | 33.89 | 6.01 | 35.06 | ok |
| lightrag_hybrid_rerank | 50 | 19.99 | 15.24 | 35.32 | 43.58 | 49.44 | 8.7 | 49.48 | ok |
| lightrag_mix_rerank | 50 | 21.24 | 15 | 36.28 | 41.24 | 48.36 | 7.99 | 48.64 | ok |

### 三系统 RAGAS 评估结果对比

| 系统 | 样本数 | 平均检索上下文数 | 平均参考上下文数 | 平均总耗时/s | Faithfulness | Answer Relevancy | Context Precision | Context Recall | Factual Correctness | Semantic Similarity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rag | 50 | 3 | 2 | 1.51 | 0.6471 | 0.573 | 0.6017 | 0.5877 | 0.2914 | 0.7526 |
| rag_rerank | 50 | 3 | 2 | 8.25 | 0.6741 | 0.6357 | 0.7417 | 0.6673 | 0.3856 | 0.7956 |
| lightrag_hybrid | 50 | 6 | 2 | 16.89 | 0.7901 | 0.9068 | 0.808 | 0.8998 | 0.3454 | 0.8689 |

### 四系统 RAGAS 评估结果对比

| 系统 | 平均总耗时/s | 平均回答耗时/s | 平均上下文获取耗时/s | 平均重排耗时/s | 忠实度 | 回答相关性 | 上下文精确率 | 上下文召回率 | 事实正确性 | 语义相似度 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RAG | 1.5145 | 1.5145 | 0 | 0 | 0.6471 | 0.573 | 0.6017 | 0.5877 | 0.2914 | 0.7526 |
| RAG + Rerank | 8.253 | 8.253 | 0 | 0 | 0.6741 | 0.6357 | 0.7417 | 0.6673 | 0.3856 | 0.7956 |
| LightRAG Hybrid | 16.893 | 14.0345 | 2.8586 | 0 | 0.7901 | 0.9068 | 0.808 | 0.8998 | 0.3454 | 0.8689 |
| LightRAG Hybrid + Rerank | 21.8351 | 18.5477 | 1.2245 | 2.0629 | 0.781 | 0.9298 | 0.9121 | 0.8941 | 0.3822 | 0.8768 |

### 五系统 RAGAS 评估结果对比

| 系统 | 平均总耗时/s | 平均回答耗时/s | 平均上下文获取耗时/s | 平均重排耗时/s | 忠实度 | 回答相关性 | 上下文精确率 | 上下文召回率 | 事实正确性 | 语义相似度 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RAG | 1.5145 | 1.5145 | 0 | 0 | 0.6471 | 0.573 | 0.6017 | 0.5877 | 0.2914 | 0.7526 |
| RAG + Rerank | 8.253 | 8.253 | 0 | 0 | 0.6741 | 0.6357 | 0.7417 | 0.6673 | 0.3856 | 0.7956 |
| LightRAG Hybrid | 16.893 | 14.0345 | 2.8586 | 0 | 0.7901 | 0.9068 | 0.808 | 0.8998 | 0.3454 | 0.8689 |
| LightRAG Hybrid + Rerank | 21.8351 | 18.5477 | 1.2245 | 2.0629 | 0.781 | 0.9298 | 0.9121 | 0.8941 | 0.3822 | 0.8768 |
| RAGFlow | 16.9724 | 16.9724 | 0 | 0 | 0.6311 | 0.8339 | 0.7235 | 0.562 | 0.4516 | 0.9038 |

### RAGFlow 评估结果对比（含Tongyi Rerank）

| 系统 | 平均总耗时/s | 忠实度 | 回答相关性 | 上下文精确率 | 上下文召回率 | 事实正确性 | 语义相似度 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RAGFlow | 16.9724 | 0.6311 | 0.8339 | 0.7235 | 0.562 | 0.4516 | 0.9038 |
| RAGFlow + Tongyi Rerank | 12.7382 | 0.6303 | 0.7733 | 0.797 | 0.5803 | 0.4024 | 0.8951 |

> RAGFlow配置：top_n=8, Top-K=80, 向量相似权重=0.30, 全文权重=0.70, **知识图谱未开启**

## 六、结论分析

### RAGFlow 分析

RAGFlow 的事实正确性（0.4516）和语义相似度（0.9038）在六个系统中表现最好，说明 RAGFlow 在答案事实匹配和语义接近程度上有优势。但上下文召回率（0.562）和忠实度（0.6311）相比 LightRAG 系列偏低，说明检索上下文覆盖度还有提升空间。

接入 Tongyi Rerank 后，上下文精确率从 0.7235 提升到 0.797，但最终答案质量没有同步提升（事实正确性从0.4516降到0.4024，回答相关性从0.8339降到0.7733）。

### 各系统定位

| 系统 | 优势 | 劣势 | 适合场景 |
| --- | --- | --- | --- |
| 普通 RAG | 速度最快（1.51s） | 质量指标最低 | 低延迟场景 |
| RAG + Rerank | 检索质量明显提升 | 耗时增加5倍 | 需要检索精度的场景 |
| LightRAG Hybrid | 上下文召回率最高（0.90） | 耗时高（17s） | 答案质量和上下文覆盖要求高 |
| LightRAG Hybrid + Rerank | 上下文精确率最高（0.91） | 耗时最高（22s） | 兼顾精度和召回 |
| RAGFlow | 事实正确性最高（0.45） | 上下文召回率低（0.56） | 事实匹配要求高 |
| RAGFlow + Rerank | 检索精确率提升 | 答案质量未提升 | 当前参数下不建议 |

### 关键Gap（本demo要补的）

1. **RAGFlow 知识图谱未开启** —— 实习生测的RAGFlow没开GraphRAG，这正是demo要验证的核心
2. **测试域是法律问答** —— demo需要换到核电设备手册域
3. **GraphRAG全局检索能力未验证** —— 需求里明确要"全局问题用社区发现跨章节汇总"
