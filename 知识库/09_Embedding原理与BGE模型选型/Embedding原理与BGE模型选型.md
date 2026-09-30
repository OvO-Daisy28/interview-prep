# Embedding 原理与模型选型（BGE-M3 + Qwen3-Embedding）

> 定位：把 embedding 模型的训练原理、公式、选型依据讲清楚。引用官方论文和文档。
> 引用来源：
> - [C-Pack: Packed Resources For General Chinese Embeddings](https://arxiv.org/abs/2309.07597)（BGE 原始论文，SIGIR 2024）
> - [M3-Embedding: Multi-Linguality, Multi-Functionality, Multi-Granularity](https://arxiv.org/abs/2402.03216)（BGE-M3 论文）
> - [FlagEmbedding GitHub](https://github.com/FlagOpen/FlagEmbedding)
> - [Qwen3-Embedding 官方博客](https://qwenlm.github.io/blog/qwen3-embedding/)
> - [Qwen3-Embedding-0.6B HuggingFace](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
>
> 阅读顺序：文本变向量 → 对比学习与 InfoNCE → BGE 三阶段训练 → BGE-M3 三合一检索 → Qwen3-Embedding → 模型对比 → 选型决策 → 面试答法

---

## 一、文本怎么变成向量

### 编码过程

Embedding 模型本质是一个神经网络，输入一段文本，输出一个固定长度的向量：

```
文本 → Tokenizer 切成 token 序列
     → Transformer Encoder（多层）
     → 每个 token 输出一个隐状态向量
     → 取池化输出（[CLS] 或 [EOS] 或 mean pooling）作为整段文本的向量表示
     → 固定维度向量
```

### 不同模型的池化方式

| 模型 | 基础架构 | 池化方式 |
|---|---|---|
| BGE-base/large-zh | BERT Encoder | [CLS] token 输出 |
| BGE-M3 | XLM-RoBERTa large | [CLS] token 输出（dense）/ 全 token 输出（multi-vector） |
| Qwen3-Embedding | Qwen3 LLM 基础模型 | **[EOS] token 隐藏状态**（最后一个 [EOS] 对应的隐藏状态） |

> 来源：C-Pack 论文 §3；M3-Embedding 论文 §3；Qwen3-Embedding 官方博客。

**关键区别**：BGE 系列基于 BERT（Encoder-only），Qwen3-Embedding 基于 LLM（Decoder-only，用 [EOS] 的隐藏状态而非 [CLS]）。这是传统 embedding 和 LLM-based embedding 的架构分歧。

---

## 二、对比学习与 InfoNCE Loss

### 核心思想

对比学习的本质：**正样本对拉近、负样本对推远**。

- **正样本对**：语义相似的 query 和 doc → 训练时拉近它们的向量距离
- **负样本对**：语义不相关的 query 和 doc → 推远它们的向量距离
- **困难负样本**：看起来相似但语义不同的 → 教模型做细粒度区分

### InfoNCE Loss 公式

BGE 和 BGE-M3 都使用 InfoNCE 损失函数（C-Pack 论文原文）：

$$\min.\sum_{(p,q)}-\log\frac{e^{\langle\mathbf{e}_{p},\mathbf{e}_{q}\rangle/\tau}}{e^{\langle\mathbf{e}_{p},\mathbf{e}_{q}\rangle/\tau}+\sum_{Q^{\prime}}e^{\langle\mathbf{e}_{p},\mathbf{e}_{q^{\prime}}\rangle/\tau}}$$

| 符号 | 含义 | 直觉 |
|---|---|---|
| $p, q$ | 正样本对（语义相关的文本对） | "这段描述"和"这个问题"是对应的 |
| $q^{\prime} \in Q^{\prime}$ | 负样本 | 其他不相关的问题 |
| $\mathbf{e}_p, \mathbf{e}_q$ | 文本的 embedding 向量 | 固定维度向量 |
| $\langle\mathbf{e}_p, \mathbf{e}_q\rangle$ | 向量内积（点积） | 越相似越大 |
| $\tau$ | 温度参数 | 控制分数锐度——越小越挑剔 |

**公式在说什么**：分子是正样本对的相似度分数，分母是正样本 + 所有负样本的分数之和。取 $-\log$ 后：正样本分数越高、负样本分数越低，loss 越小。模型被迫学会区分语义相似性。

### Batch Size 的影响

InfoNCE 的效果和负样本数量强相关。BGE 把 batch size 推到 **19,200**（通过 gradient checkpointing + cross-device embedding sharing）：

| Batch Size | Retrieval | Average |
|---|---|---|
| 256 | 57.25 | 56.43 |
| 2,048 | 60.96 | 57.92 |
| **19,200** | **63.90** | **59.00** |

> 来源：C-Pack 论文 Table 4。负样本越多，模型见过越多"长什么样但语义不同"的例子，区分更精细。

BGE-M3 进一步优化了 batching 策略（见后文）。

---

## 三、BGE 三阶段训练（base/large 系列）

> 适用于 bge-base-zh / bge-large-zh。BGE-M3 的训练流程见下一节。

| 阶段 | 数据 | 方法 | 核心贡献 |
|---|---|---|---|
| 1. 预训练 | Wudao 纯文本 | RetroMAE（掩码自编码） | 学会从文本提取信息压缩到向量（+1.34 检索） |
| 2. 通用微调 | 100M 无标签对 | InfoNCE, batch=19200, in-batch negatives | 学会区分语义相似性 |
| 3. 任务微调 | 838K 有标签对 | 指令微调 + ANN 硬负样本 | 适配检索任务（+4.96 平均） |

### C-MTEB 对比（BGE base/large vs 其他）

| 模型 | 维度 | Retrieval | Average |
|---|---|---|---|
| Text2Vec (base) | 768 | 38.79 | 48.59 |
| M3E (base) | 768 | 56.91 | 57.79 |
| OpenAI-Ada-002 | 1536 | 52.00 | 53.02 |
| **BGE (base)** | **768** | **69.53** | **62.80** |
| **BGE (large)** | **1024** | **71.53** | **63.96** |

> 来源：C-Pack 论文 Table 2。

---

## 四、BGE-M3：三合一检索（实际部署模型）

### 为什么 M3 叫 M3

**M3 = Multi-Linguality + Multi-Functionality + Multi-Granularity**（三多）。

> 来源：[M3-Embedding 论文](https://arxiv.org/abs/2402.03216)（Chen et al., 2024）。

| M | 含义 | 具体能力 |
|---|---|---|
| **Multi-Linguality** | 多语言 | 支持 100+ 种语言，2655 种跨语言对应 |
| **Multi-Functionality** | 多功能 | 同时支持 dense / sparse / multi-vector 三种检索 |
| **Multi-Granularity** | 多粒度 | 支持短句子到 8192 token 长文档 |

### 模型架构

| 属性 | 值 |
|---|---|
| 基础架构 | XLM-RoBERTa (large) |
| 参数量 | ~568M（567,754,752） |
| 最大输入长度 | **8192 token**（从原始 512 扩展） |
| 预训练数据 | 1.84 亿文本样本，Pile/Wudao/mC4，覆盖 105 种语言 |

### 三种检索功能

BGE-M3 的核心创新：**一个模型同时输出三种检索表示**。

#### 4.1 稠密检索（Dense Retrieval）

和传统 embedding 一样：取 [CLS] token 的归一化隐藏状态做向量。

$$e_q = \text{norm}(\mathbf{H_q}[0]), \quad e_p = \text{norm}(\mathbf{H_p}[0])$$
$$s_{dense} = \langle e_p, e_q \rangle$$

**适用**：语义相似检索——"泵的出力参数"和"额定流量扬程"字面不同但语义相近。

#### 4.2 稀疏/词法检索（Sparse Retrieval）

每个 token 经一个可学习线性层 $\mathbf{W}_{lex}$ 映射成一个权重值：

$$w_{q_t} = \text{ReLU}(\mathbf{W}_{lex}^T \mathbf{H_q}[i])$$

相关性分数基于 query 和 doc 共有词项的权重乘积之和：

$$s_{lex} = \sum_{t \in q \cap p} (w_{q_t} \cdot w_{p_t})$$

**这本质是"学习版 BM25"**——BM25 的 IDF/TF 是人工公式，sparse retrieval 的词项权重是模型学出来的。同一 term 出现多次只保留最大权重（类似 TF 饱和）。

**适用**：精确术语匹配——设备编号"HTJ300-400C"、参数值"640m³/h"这种精确值。

#### 4.3 多向量检索（Multi-Vector / ColBERT 式）

不是取一个 [CLS] 向量，而是用**整个序列的输出**经投影矩阵 $\mathbf{W}_{mul}$ 变换后，做 ColBERT 式后交互打分：

$$E_q = \text{norm}(\mathbf{W}_{mul}^T \mathbf{H_q}), \quad E_p = \text{norm}(\mathbf{W}_{mul}^T \mathbf{H_p})$$
$$s_{mul} = \frac{1}{N} \sum_{i=1}^{N} \max_{j=1}^{M} E_q[i] \cdot E_p^T[j]$$

**直觉**：query 的每个 token 都去 doc 里找最相似的 token 做点积，取平均。比 dense（整段一个向量）更精细——能捕捉 token 级别的匹配。

**适用**：需要细粒度匹配的场景——query 中某些关键词需要和 doc 中特定位置对应。

#### 混合检索最终打分

$$s_{rank} = w_1 \cdot s_{dense} + w_2 \cdot s_{lex} + w_3 \cdot s_{mul}$$

不同任务权重不同：

| 任务 | $w_1$ (dense) | $w_2$ (sparse) | $w_3$ (multi-vec) |
|---|---|---|---|
| MIRACL（多语言短文本） | 1 | 0.3 | 1 |
| MLDR（长文档检索） | 0.15 | 0.5 | 0.35 |

> 来源：M3-Embedding 论文 公式 1 及实验配置。

### 自知识蒸馏（Self-Knowledge Distillation）

BGE-M3 的训练创新：三种检索方法互相当老师。

**核心思想**：三种检索方式各有强弱，把它们的相关性分数集成起来作为"教师信号"，让每种方式都向集成分数学习。

**集成分数（教师）**：
$$s_{inter} = w_1 \cdot s_{dense} + w_2 \cdot s_{lex} + w_3 \cdot s_{mul}$$

**蒸馏损失**：每个检索方法以 $s_{inter}$ 为教师：
$$\mathcal{L}'_* = -p(s_{inter}) \cdot \log p(s_*)$$

**蒸馏权重**：sparse 初始精度差（$\mathbf{W}_{lex}$ 随机初始化），所以权重设低：

| 参数 | 值 | 理由 |
|---|---|---|
| $w_1$ (dense) | 1 | 初始精度好 |
| $w_2$ (sparse) | 0.3 | 初始精度差，不信任 |
| $w_3$ (multi-vec) | 1 | 初始精度好 |

**消融实验**（蒸馏效果）：

| 检索方式 | 有蒸馏 | 无蒸馏 | 差值 |
|---|---|---|---|
| Dense | 69.2 | 68.7 | +0.5 |
| **Sparse** | **53.9** | **36.7** | **+17.2** |
| Multi-vec | 70.5 | 69.3 | +1.2 |

> 来源：M3-Embedding 论文消融实验。**蒸馏对 sparse 检索提升最大**（+17.2），因为 sparse 初始差，dense 和 multi-vec 的集成分数给了它好的教师信号。

### BGE-M3 性能基准

#### 多语言检索（MIRACL，18 种语言）

| 方法 | nDCG@10 |
|---|---|
| BM25 | 31.9 |
| mE5-large | 66.6 |
| E5-mistral-7b | 63.4 |
| OpenAI-3 | 54.9 |
| **M3 Dense** | **69.2** |
| M3 Sparse | 53.9 |
| M3 Multi-vec | 70.5 |
| **M3 All（三合一）** | **71.5** |

#### 长文档检索（MLDR）

| 方法 | nDCG@10 |
|---|---|
| BM25 | 53.6 |
| mE5-large | 34.2 |
| text-embedding-ada-002 | 32.5 |
| E5-mistral-7b | 42.6 |
| **M3 Dense** | **52.5** |
| **M3 Sparse** | **62.2** |
| M3 Multi-vec | 57.6 |
| **M3 All** | **65.0** |

> 来源：M3-Embedding 论文 Table 2-5。

**关键发现**：长文档检索中 **sparse（62.2）显著优于 dense（52.5）**——长文档里精确词项匹配比语义匹配更有效，这与 BM25 的优势场景一致。三种方法结合（All）在所有基准上都是最佳。

### Batch 优化策略

BGE-M3 的训练工程突破：处理 8192 token 长文本时 batch size 提升 20 倍以上。

| 序列长度范围 | 无监督 Batch Size | 微调 Batch Size |
|---|---|---|
| 0-500 | 67,200 | 1,152 |
| 500-1000 | 54,720 | 768 |
| 7000-8192 | 9,984 | 192 |

技术手段：按序列长度分组（减少 padding）+ 固定随机种子（负载均衡）+ Split-batch + Gradient checkpointing + 跨 GPU 广播（扩展 in-batch 负样本）。

---

## 五、Qwen3-Embedding（RAGFlow 默认配置）

### 模型规格

| 属性 | Qwen3-Embedding-0.6B | Qwen3-Embedding-4B | Qwen3-Embedding-8B |
|---|---|---|---|
| 基础模型 | Qwen3 基础模型 | Qwen3 基础模型 | Qwen3 基础模型 |
| 参数量 | 0.6B | 4B | 8B |
| 层数 | 28 | 36 | 36 |
| 嵌入维度 | 1024 | 2560 | 4096 |
| 最大序列长度 | **32K** | **32K** | **32K** |
| MRL 自定义维度 | ✅ | ✅ | ✅ |
| 指令感知 | ✅ | ✅ | ✅ |
| 多语言 | 100+ 语言含编程语言 | 同左 | 同左 |

> 来源：Qwen3-Embedding 官方博客。

### 架构特点

**与传统 BGE 的关键区别**：

| 维度 | BGE 系列 | Qwen3-Embedding |
|---|---|---|
| 基础架构 | BERT（Encoder-only） | **Qwen3 LLM（Decoder-only）** |
| 池化方式 | [CLS] token 输出 | **[EOS] token 隐藏状态** |
| 微调方式 | 全量微调 | **LoRA 微调**（保留基础模型能力） |
| 最大输入 | BGE-base 512 / BGE-M3 8192 | **32K** |
| 参数量 | 24M~568M | 600M~8B |

**LoRA 微调的意义**：不全量训练，只训练低秩适配矩阵——保留 Qwen3 基础模型预训练时学到的文本理解能力，只在上面"轻调"适配 embedding 任务。这与 BGE 的"从头训练 BERT Encoder"是完全不同的路线。

### 三阶段训练

| 阶段 | 方法 | 创新点 |
|---|---|---|
| 1. 对比预训练 | 大规模弱监督数据 | **多任务自适应提示系统**：利用 Qwen3 基础模型的文本生成能力，动态生成不同任务/语言的弱监督文本对 |
| 2. 监督训练 | 高质量标注数据 | — |
| 3. 模型合并 | 整合多个候选模型 | 增强整体性能和泛化能力 |

**多任务自适应提示系统**是 Qwen3-Embedding 的核心创新：传统方法依赖社区论坛或开源数据收集文本相关性对（如 BGE 用 Wudao/Zhihu 的标题-正文对），Qwen3 直接用 Qwen3 基础模型的生成能力**动态合成弱监督训练对**——可以按任务类型和语言定制，不受限于现有数据分布。

### 性能基准

#### Qwen3-Embedding-0.6B

| 基准 | 分数 |
|---|---|
| MTEB-R（英文检索） | **61.82** |
| CMTEB-R（中文检索） | **71.02** |
| MMTEB-R（多语言检索） | **64.64** |
| MLDR（长文档） | 50.26 |
| MTEB-Code（代码检索） | 75.41 |

#### Qwen3-Embedding-8B

> "The 8B size embedding model ranks No.1 in the MTEB multilingual leaderboard (as of June 5, 2025, score **70.58**)"
> —— Qwen3-Embedding 官方博客

8B 模型在 MTEB 多语言排行榜排名第一（截至 2025-06-05）。

#### 与 BGE-reranker-v2-m3 对比（0.6B 级别）

| 模型 | MTEB-R | CMTEB-R | MMTEB-R | MTEB-Code |
|---|---|---|---|---|
| BGE-reranker-v2-m3 | 57.03 | 72.16 | 58.36 | 41.38 |
| **Qwen3-Embedding-0.6B** | **61.82** | 71.02 | **64.64** | **75.41** |

> 来源：Qwen3-Embedding 官方博客评估表。注意：BGE-reranker 是 rerank 模型，Qwen3-Embedding-0.6B 是 embedding 模型，这里对比的是 Qwen3-Embedding 作为检索基线的分数。

---

## 六、模型对比总表

### Embedding 模型横向对比

| 模型 | 架构 | 参数量 | 维度 | 最大输入 | 中文检索(C-MTEB) | 多语言 | 关键特性 |
|---|---|---|---|---|---|---|---|
| BGE-base-zh-v1.5 | BERT Encoder | 102M | 768 | 512 | 69.53 | ❌ 中文 | 性价比最优 |
| BGE-large-zh-v1.5 | BERT Encoder | 326M | 1024 | 512 | 71.53 | ❌ 中文 | BGE 系列最高 |
| **BGE-M3** | XLM-RoBERTa large | ~568M | 1024 | **8192** | — | ✅ 100+ | **dense+sparse+multi-vector 三合一** |
| OpenAI-Ada-002 | 未知 | 未知 | 1536 | 8191 | 52.00 | ✅ | 公有云 API |
| Qwen3-Embedding-0.6B | **Qwen3 LLM** | 600M | 1024 | **32K** | **71.02** | ✅ 100+ | LoRA 微调、MRL、指令感知 |
| Qwen3-Embedding-4B | Qwen3 LLM | 4B | 2560 | 32K | — | ✅ 100+ | 更大规模 |
| Qwen3-Embedding-8B | Qwen3 LLM | 8B | 4096 | 32K | — | ✅ 100+ | **MTEB 多语言 #1 (70.58)** |

### 为什么 BGE-M3 vs Qwen3-Embedding 不是简单的替代关系

| 维度 | BGE-M3 | Qwen3-Embedding-0.6B |
|---|---|---|
| 三种检索 | ✅ dense+sparse+multi-vector | ❌ 仅 dense（需配 reranker） |
| 输入长度 | 8192 | 32K |
| 架构 | BERT（Encoder-only，推理快） | LLM（Decoder-only，推理更重） |
| 参数量 | ~568M（567,754,752） | 600M |
| 训练方法 | 自知识蒸馏（三路互教） | 多任务自适应提示 + LoRA |
| 中文检索 | — | 71.02 |
| 多语言检索(MIRACL) | 69.2（dense）/ 71.5（all） | 64.64（MMTEB-R） |

**BGE-M3 的独特优势**：一个模型同时输出三种检索表示，不需要额外配 BM25 或 reranker——sparse 检索已经内嵌了"学习版 BM25"。

**Qwen3-Embedding 的独特优势**：32K 超长上下文、基于 LLM 的更强文本理解、MRL 自定义维度、指令感知。

---

## 五补、深入理解：三合一检索 vs Reranker、Encoder vs Decoder 架构

### 5.1 为什么 BGE-M3 三合一检索可以不配 Reranker？

#### 先搞清楚：Reranker 解决什么问题

传统两阶段检索流程：

```
Stage 1: 召回（Recall）—— 双塔模型（Bi-Encoder）
  query → embedding → 向量    doc → embedding → 向量
  两向量算余弦相似度，快速从百万文档中筛出 top-k 候选

Stage 2: 精排（Rerank）—— 交叉编码器（Cross-Encoder）
  [query; doc] 拼一起 → 同一个 Transformer → 输出一个相关性分数
  对 top-k 候选逐个精排，慢但准
```

**为什么需要 Reranker？** 因为双塔模型有结构性缺陷：

- query 和 doc **各自独立编码**，在编码阶段没有任何交互
- 两个向量只通过余弦相似度做一次"事后比较"
- query 中的"额定流量"和 doc 中的" Rated Flow "在各自编码时不知道对方存在
- 结果：召回率高但精准度有限——语义相近的能召回，但哪个最相关排不准

Cross-Encoder（Reranker）解决这个问题的方式：query 和 doc 拼一起过同一个 Transformer，**在 Attention 层里每个 token 都能看到对方的 token**，交互充分，打分更准。

#### BGE-M3 三合一怎么覆盖了 Reranker 的功能

BGE-M3 的三种检索恰好覆盖了传统两阶段流程的不同层面：

| 检索方式 | 对应传统流程的角色 | 交互级别 | 原理 |
|---|---|---|---|
| Dense | Bi-Encoder 召回 | 无交互（向量级） | [CLS] 向量余弦相似度 |
| Sparse | BM25 召回 | 无交互（词项级） | 共有词项权重乘积和 |
| **Multi-vector** | **接近 Cross-Encoder** | **延迟交互（token 级）** | query 每个 token 去 doc 里找最相似的 token |

关键在 **Multi-vector（ColBERT 式）检索**：

- Dense 检索：整个 query 压成一个向量，整个 doc 压成一个向量，一个余弦——信息严重压缩
- Multi-vector：query 的**每个 token** 都有一个向量，doc 的**每个 token** 都有一个向量
- 打分时 query 的每个 token 去和 doc 所有 token 算相似度，取 max（最匹配的那个 doc token），再对所有 query token 取平均

```
Dense:     [Q整体向量] · [D整体向量]              → 1 次点积
Multi-vec: avg( max(Q_token_i · D_token_j) )      → N×M 次点积
Cross-enc: Transformer([Q; D]) → score            → 全序列 Self-Attention
```

Multi-vector 介于 Dense 和 Cross-Encoder 之间——**不是事前全交互（Cross-Encoder），而是事后 token 级交互（Late Interaction）**。query 和 doc 在编码阶段仍然独立（所以 doc 端可以离线编码入库，和双塔一样快），但打分阶段不是粗暴的向量余弦，而是 token 级别的精细匹配。

**所以三合一为什么不需要 Reranker？**

1. Dense 负责语义召回（和 Bi-Encoder 一样）
2. Sparse 负责精确术语匹配（和 BM25 一样）
3. Multi-vector 负责精细排序（接近 Cross-Encoder 的效果）
4. 三路分数加权融合，一个模型一次推理全出——不需要再跑一遍 Reranker

**但注意边界**：Multi-vector 是 Late Interaction，不是 Cross-Encoder 的全交互。极端 case 下（需要 query 和 doc 深度逻辑推理才能判断相关性），Cross-Encoder 仍更准。BGE-M3 三合一的定位是**在召回阶段就做到了接近精排的效果**，对大多数检索场景足够，但不等于在所有场景都能替代独立 Reranker。

> **面试口径**：BGE-M3 的 multi-vector 检索是 ColBERT 式的 Late Interaction——query 和 doc 编码时独立（保持双塔的离线编码优势），打分时做 token 级别的 max-match-average。这介于 Dense（向量级无交互）和 Cross-Encoder（全序列 Attention 交互）之间。三路融合后，召回阶段就接近精排效果，大多数场景不需要额外 Reranker。但 Late Interaction ≠ Full Interaction，极端推理型相关性判断仍可能需要独立 Reranker。

#### 三种交互级别对比

```
Dense (Bi-Encoder):
  Q: [CLS] → q_vec          D: [CLS] → d_vec
  打分: q_vec · d_vec                    → 1 次点积，零交互

Multi-vector (ColBERT Late Interaction):
  Q: token1→q1, token2→q2...  D: token1→d1, token2→d2...
  打分: avg(max(qi · dj))               → N×M 次点积，延迟交互

Cross-Encoder (Reranker):
  [Q_token1, Q_token2, ..., D_token1, D_token2, ...] → Transformer
  打分: Self-Attention 全序列交互 → score  → 全交互，但不可离线编码
```

| 维度 | Dense | Multi-vector | Cross-Encoder |
|---|---|---|---|
| 编码方式 | query/doc 独立 | query/doc 独立 | query/doc 拼一起 |
| 离线编码 | ✅ doc 可预计算 | ✅ doc 可预计算 | ❌ 必须在线拼计算 |
| 交互时机 | 无 | 打分时（延迟） | 编码时（即时） |
| 交互粒度 | 向量级 | token 级 | token 级 + Attention |
| 精度 | 低 | 中 | 高 |
| 速度 | 快 | 中 | 慢 |
| 适用阶段 | 召回 | 召回+精排 | 精排 |

### 5.2 BERT 架构（Encoder-only）vs LLM 架构（Decoder-only）原理

#### Transformer 基础：Self-Attention

两种架构都基于 Transformer，核心区别在 **Attention Mask 的方向**。

Transformer 的核心操作是 Self-Attention：

```
每个 token 都和其他 token 计算注意力权重：
Attention(Q, K, V) = softmax(QK^T / √d) · V

Q = 当前 token 的 Query 矩阵
K = 所有 token 的 Key 矩阵
V = 所有 token 的 Value 矩阵
```

**关键问题：每个 token 能看到哪些其他 token？** 这由 Attention Mask 决定，也是 Encoder 和 Decoder 的根本区别。

#### BERT（Encoder-only）：双向注意力

```
输入: "泵 的 额定 流量"

Attention Mask（全可见）:
      泵   的   额定  流量
泵    ✓    ✓    ✓    ✓
的    ✓    ✓    ✓    ✓
额定  ✓    ✓    ✓    ✓
流量   ✓    ✓    ✓    ✓

→ 每个 token 都能看到左右所有 token
→ "额定" 同时知道左边是"泵的"、右边是"流量"
→ 上下文信息完全融合
```

BERT 的 Encoder 做的是**双向编码**：每个位置的 token 都和序列中所有其他 token 互相 Attend。这意味着：

- "额定"这个词的向量表示，融合了左边"泵的"和右边"流量"的信息
- 输出的每个 token 向量都是**完整上下文的表示**
- 取 [CLS] token（第一个特殊 token）的输出，就是整段文本的全局表示

**为什么适合做 Embedding？** 因为文本表示需要完整上下文——"额定"单独看是模糊的，"泵的额定流量"才有明确语义。双向 Attention 让每个 token 都带上完整上下文信息，池化后的向量语义更丰富。

**BGE-M3 具体**：基于 XLM-RoBERTa large（多语言版 BERT），24 层 Transformer Encoder，双向 Attention，取 [CLS] 输出做 dense 向量、全 token 输出做 multi-vector。

#### LLM（Decoder-only）：单向因果注意力

```
输入: "泵 的 额定 流量"

Attention Mask（因果遮罩，只看左边）:
      泵   的   额定  流量
泵    ✓    ✗    ✗    ✗        ← "泵" 只能看到自己
的    ✓    ✓    ✗    ✗        ← "的" 能看到 "泵" 和自己
额定  ✓    ✓    ✓    ✗        ← "额定" 能看到前面三个
流量   ✓    ✓    ✓    ✓        ← "流量" 能看到所有

→ 每个 token 只能看到左边的 token（包括自己）
→ "额定" 知道左边是"泵的"，但不知道右边是"流量"
→ 信息从左到右单向流动
```

LLM（GPT/Qwen 系列）做的是**因果语言建模（Causal LM）**：每个 token 只能看到前面的 token，预测下一个 token。这是为了**自回归生成**——生成时一个个 token 往后写，不能偷看后面的。

**为什么 LLM 也能做 Embedding？** Qwen3-Embedding 取的是 **[EOS] token（序列结束符）的隐藏状态**：

```
输入: "泵 的 额定 流量 [EOS]"
                              ↑
                         取这个位置的隐藏状态

[EOS] 在序列最后，因果 Attention 下它能看到前面所有 token
→ [EOS] 的隐藏状态 = 整个序列信息的"汇总点"
```

这很巧妙：因果 Attention 下，最后一个 token 是唯一能看到全部输入的 token。所以取 [EOS] 的隐藏状态，相当于取了"模型读完整段文本后的理解"——效果上接近双向编码的全局表示。

**但代价是**：
- Decoder-only 架构的注意力是单向的，中间 token 的表示不如 BERT 丰富（中间 token 看不到后面的 token）
- 只有 [EOS] 位置有完整信息，其他位置信息不完整
- 参数量通常更大（Qwen3-Embedding 0.6B vs BGE-M3 568M），推理更重
- 优势是 LLM 预训练数据量远大于 BERT，文本理解能力更强，LoRA 微调保留了基础模型的泛化能力

#### 两种架构对比

| 维度 | BERT (Encoder-only) | LLM (Decoder-only) |
|---|---|---|
| Attention 方向 | **双向**（全可见） | **单向因果**（只看左） |
| 每个位置的上下文 | 完整（左+右） | 部分（只左） |
| 全局信息位置 | [CLS] 或任意位置（都含全文信息） | **只有 [EOS]** 位置含全文信息 |
| 训练目标 | 掩码语言建模（MLM）：猜被遮住的词 | 因果语言建模（CLM）：预测下一个词 |
| 适合任务 | 理解型（分类、检索、embedding） | 生成型（对话、续写） |
| 做 Embedding 的方式 | [CLS] token 输出 / mean pooling | **[EOS] token 隐藏状态** |
| 参数量 | 小（102M~568M） | 大（600M~8B） |
| 推理速度 | 快（一次前向） | 慢（模型更大） |
| 文本理解能力 | 强（但受限于预训练数据量） | 更强（LLM 预训练数据量远大） |
| 代表模型 | BGE 系列、BERT、RoBERTa | Qwen3-Embedding、GPT、LLaMA |

> **面试口径**：BERT 是 Encoder-only，双向 Attention——每个 token 都能看到左右所有 token，输出的每个位置都带完整上下文，取 [CLS] 做向量。LLM 是 Decoder-only，因果 Attention——每个 token 只能看到左边，只有最后的 [EOS] 能看到全部输入，取它的隐藏状态做向量。BERT 做 embedding 更自然（双向编码天生适合理解任务），LLM 做 embedding 是"借力"——预训练数据量大、文本理解强，但只有 [EOS] 位置有完整信息，且推理更重。

#### 一句话总结

```
Encoder-only（BERT/BGE）: 双向看 → 每个位置都懂全文 → 取 [CLS] 做向量 → 天生适合 embedding
Decoder-only（LLM/Qwen3）: 从左到右 → 只有最后 [EOS] 懂全文 → 取 [EOS] 做向量 → 借 LLM 的理解力做 embedding
```

---

## 七、选型决策

### 实际部署：BGE-M3

| 维度 | 理由 |
|---|---|
| 三合一检索 | dense + sparse + multi-vector 一个模型全包，不需要额外配 BM25 引擎或 reranker |
| 多语言 | 支持中英文混合文档（核电文档有英文设备型号和中文描述混排） |
| 长文档 | 8192 token 支持，部分手册章节超 512 token 不需要截断 |
| 本地部署 | 开源（MIT License），可本地部署，满足核电私密性 |
| 效果 | 多语言检索 M3 All 71.5（MIRACL），长文档检索 65.0（MLDR），均为 SOTA |

### RAGFlow 默认：Qwen3-Embedding-0.6B

| 维度 | 理由 |
|---|---|
| 中文检索强 | CMTEB-R 71.02，与 BGE-large-zh 的 71.53 接近 |
| 超长上下文 | 32K，远超 BGE-M3 的 8192 |
| 参数效率 | 0.6B 参数，1024 维，推理可控 |
| 生态 | Qwen3 系列（embedding + reranker + LLM）无缝组合，RAGFlow 原生支持 |
| 灵活性 | MRL 自定义维度 + 指令感知 |

### 面试选型答法

> 我们实际部署的是 BGE-M3，来自智源研究院（BAAI）的 FlagEmbedding 项目。选它主要因为三合一检索——一个模型同时输出 dense、sparse、multi-vector 三种表示，不需要额外配 BM25 引擎或 reranker。sparse 检索本质是"学习版 BM25"，词项权重是模型学出来的而不是人工公式。训练上用自知识蒸馏，三种检索方法互相当教师，消融实验显示对 sparse 检索提升最大（+17.2）。
>
> RAGFlow 官方默认配的是 Qwen3-Embedding-0.6B，它走的是另一条路线——基于 Qwen3 LLM 用 LoRA 微调，取 [EOS] token 的隐藏状态做 embedding，支持 32K 超长上下文和 MRL 自定义维度，8B 版本在 MTEB 多语言排行榜第一（70.58）。两者的核心区别是：BGE-M3 用 BERT 架构做三合一，Qwen3-Embedding 用 LLM 架构做纯 dense 但更强更长。

---

## 八、面试答法

### "embedding 模型怎么选的？"

> 选了 BGE-M3。核心原因是三合一检索——一个模型同时支持 dense（语义）、sparse（词法，学习版 BM25）、multi-vector（ColBERT 式 token 级匹配），不需要额外配 BM25 引擎或 reranker。还支持 100+ 语言和 8192 token 长文档。

### "BGE-M3 怎么训练的？"

> 基于 XLM-RoBERTa large 架构，三阶段训练：RetroMAE 预训练（学会压缩信息到向量）→ 无监督对比预训练（1.2B 文本对，InfoNCE）→ 微调阶段。核心创新是自知识蒸馏——三种检索方法（dense/sparse/multi-vector）的相关性分数集成起来当教师信号，让每种方法都向集成分数学习。消融实验显示蒸馏对 sparse 检索提升最大（+17.2），因为 sparse 初始精度差，dense 和 multi-vec 给了它好的教师。

### "InfoNCE loss 在做什么？"

> 公式核心是正样本对的内积尽量大、负样本对尽量小。$\frac{e^{正样本相似度/\tau}}{e^{正样本相似度/\tau} + \sum e^{负样本相似度/\tau}}$——正样本在所有候选中占比尽量大。温度参数 τ 控制锐度。

### "sparse 检索和 BM25 什么关系？"

> sparse 检索是"学习版 BM25"。BM25 的 IDF（词稀有度）和 TF（词频饱和）是人工公式，BGE-M3 的 sparse 检索把每个 token 的权重用神经网络学出来，再用 ReLU 映射成权重值。同一 term 出现多次只保留最大权重（类似 TF 饱和）。相关性分数是 query 和 doc 共有词项的权重乘积之和。本质是把 BM25 的人工公式换成可学习的参数。

### "BGE-M3 和 Qwen3-Embedding 有什么区别？"

> 两条路线。BGE-M3 用 BERT 架构（Encoder-only），一个模型同时输出 dense+sparse+multi-vector 三种检索表示，8192 token 输入，靠自知识蒸馏训练三路。Qwen3-Embedding 用 Qwen3 LLM 架构（Decoder-only），LoRA 微调只训练低秩矩阵保留基础模型能力，取 [EOS] token 做向量，支持 32K 超长上下文和 MRL 自定义维度。BGE-M3 胜在三合一，Qwen3 胜在 LLM 的文本理解能力和超长上下文。

### "换 embedding 模型要重建吗？"

> 必须全库重建。不同模型的向量空间完全不同——同一句话在 BGE-M3 和 Qwen3-Embedding 里编码出的向量维度和空间都不同，不在同一个空间里相似度没有意义。

### "硬负样本是什么？为什么重要？"

> 普通负样本随机采，太容易区分——"泵的额定流量"和"劳动法第三条"一看就不相关。硬负样本是"看起来相关但实际不相关"的——"泵的额定流量"和"泵的外观尺寸"。BGE 用 ANN-style sampling 挖硬负样本，逼模型学会细粒度区分。BGE-M3 进一步用自知识蒸馏，让 dense 和 multi-vec 的好分数教 sparse 检索做区分。

### "BGE-M3 三合一为什么不需要 Reranker？"

> 传统流程是 Bi-Encoder 召回（快但粗）+ Cross-Encoder 精排（慢但准）。Cross-Encoder 之所以准，是因为 query 和 doc 拼一起过 Transformer，Attention 层里每个 token 都能看到对方——全交互。
>
> BGE-M3 的 multi-vector 检索是 ColBERT 式的 Late Interaction——query 和 doc 编码时仍然独立（doc 可离线预计算），但打分时不做粗暴的向量余弦，而是 query 每个 token 去和 doc 所有 token 算相似度取 max 再平均。这是 token 级的延迟交互，介于 Dense（向量级零交互）和 Cross-Encoder（全序列 Attention 交互）之间。
>
> 三路融合后：dense 管语义召回，sparse 管精确术语，multi-vector 管精细排序——一个模型一次推理就把召回和接近精排的效果都做了。但注意边界：Late Interaction ≠ Full Interaction，极端推理型相关性判断仍可能需要独立 Reranker。

### "BERT 和 LLM 做 Embedding 有什么区别？"

> 本质区别在 Attention 方向。BERT 是 Encoder-only，双向 Attention——每个 token 都能看到左右所有 token，输出的每个位置都带完整上下文，取 [CLS] 做向量。LLM 是 Decoder-only，因果 Attention——每个 token 只能看到左边，只有最后的 [EOS] 能看到全部输入，取它的隐藏状态做向量。
>
> BERT 做 embedding 更自然——双向编码天生适合理解任务，每个位置都是完整语义表示。LLM 做 embedding 是"借力"——预训练数据量远大于 BERT，文本理解更强，但只有 [EOS] 位置有完整信息，且推理更重。Qwen3-Embedding 走这条路线，用 LoRA 微调保留 LLM 基础能力，取 [EOS] 隐藏状态做向量。

---

## 来源

- [C-Pack: Packed Resources For General Chinese Embeddings](https://arxiv.org/abs/2309.07597)（SIGIR 2024）—— BGE base/large 原始论文
- [M3-Embedding 论文](https://arxiv.org/abs/2402.03216)—— BGE-M3 原始论文
- [FlagEmbedding GitHub](https://github.com/FlagOpen/FlagEmbedding)—— 模型列表和文档
- [Qwen3-Embedding 官方博客](https://qwenlm.github.io/blog/qwen3-embedding/)—— Qwen3 系列技术博客
- [Qwen3-Embedding-0.6B HuggingFace](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)—— 模型卡片
- RAGFlow 源码：task_executor.py:710-758（embedding 实现）
