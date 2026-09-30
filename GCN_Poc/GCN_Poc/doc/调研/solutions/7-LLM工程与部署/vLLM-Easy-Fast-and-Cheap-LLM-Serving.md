---
title: vLLM: Easy, Fast, and Cheap LLM Serving
source: https://arxiv.org/abs/2309.06180
date_published: 
collected: 2026-08-11
category: 7
tags: []
relevance: 高
maturity: 生产级
open_source: 是
repo: https://github.com/vllm-project/vllm
---

## 核心方法
UC Berkeley 开源的 LLM 推理引擎：PagedAttention 内存管理 + 连续批处理，大幅提升 GPU 利用率和吞吐量。支持主流开源模型。

## 关键创新点
- PagedAttention 减少 KV Cache 内存碎片
- 连续批处理（continuous batching）提升吞吐
- 支持张量并行和流水线并行

## 与本项目的关联
对应需求：LLM 私有化部署（4.8.8）。可借鉴：本地 LLM 推理服务，解决外部 API 延迟瓶颈。局限性：需要 GPU 资源。

## 实验数据/落地案例
比 HuggingFace Transformers 吞吐高 24x（A100 基准）。
