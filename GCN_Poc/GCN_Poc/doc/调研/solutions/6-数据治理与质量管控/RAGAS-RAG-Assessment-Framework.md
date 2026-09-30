---
title: RAGAS: RAG Assessment Framework
source: https://arxiv.org/abs/2309.15217
date_published: 
collected: 2026-08-11
category: 6
tags: []
relevance: 中
maturity: 可复现
open_source: 是
repo: https://github.com/explodinggradients/ragas
---

## 核心方法
RAGAS 是 RAG 系统评估框架：从答案相关性、上下文相关性、忠实性（faithfulness）和上下文召回率四个维度评估 RAG 质量，无需人工标注。

## 关键创新点
- 无人工标注的自动评估
- 多维度指标（faithfulness, answer_relevancy, context_precision, context_recall）

## 与本项目的关联
对应需求：数据治理与质量管控。可借鉴：RAG 系统质量评估指标体系。局限性：LLM 评估本身有偏差，需要结合人工抽检。

## 实验数据/落地案例
在多个 RAG 基准上验证了指标与人工评分的相关性。
