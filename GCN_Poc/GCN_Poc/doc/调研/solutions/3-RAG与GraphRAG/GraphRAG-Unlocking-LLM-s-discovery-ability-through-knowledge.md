---
title: GraphRAG: Unlocking LLM 's discovery ability through knowledge graph-based retrieval
source: https://arxiv.org/abs/2404.16130
date_published: 
collected: 2026-08-11
category: 3
tags: []
relevance: 高
maturity: 可复现
open_source: 是
repo: https://github.com/microsoft/graphrag
---

## 核心方法
微软提出的 GraphRAG 方案：先用 LLM 从文档中抽取实体和关系构建知识图谱，再用 Leiden 算法进行社区发现，为每个社区生成摘要。查询时分 local（实体定位）和 global（社区摘要跨章节汇总）两种模式。

## 关键创新点
- 社区发现 + 社区摘要实现全局问题跨文档汇总
- 支持增量 update（仅对新增文档重新抽取和合并子图）
- Local/Global/DRIFT 三种查询模式

## 与本项目的关联
对应需求：知识库与知识图谱子系统。可借鉴：社区发现和社区摘要算法、增量更新思路。局限性：建图 Token 成本高，单文档建图耗时长。

## 实验数据/落地案例
微软在公开基准上验证了 global 查询对跨文档汇总问题的效果优势。
