---
title: KAG: Boosting LLMs in Professional Domains via Knowledge Augmented Generation
source: https://arxiv.org/abs/2409.13731
date_published: 
collected: 2026-08-11
category: 8
tags: []
relevance: 中
maturity: 可复现
open_source: 是
repo: https://github.com/OpenSPG/KAG
---

## 核心方法
蚂蚁集团面向专业领域严谨问答的框架：Schema 约束 + 逻辑形式推理。用 LLMFriSPG 知识表示兼容无 Schema 抽取与有 Schema 约束，图谱-文本双向互索引。

## 关键创新点
- Schema 约束的领域建模 + 符号逻辑推理
- 逻辑形式引导的混合推理引擎
- 多跳问答基准上显著超过 GraphRAG

## 与本项目的关联
对应需求：时序知识图谱、语义推理。可借鉴：Schema 约束建模思路、规则推理方向。局限性：延迟高（~40s），双平台架构成本高，Java 技术栈。

## 实验数据/落地案例
HotpotQA F1 提升 19.6%，2WikiMultiHopQA 提升 33.5%。支付宝政务落地 1.1 万份文档。
