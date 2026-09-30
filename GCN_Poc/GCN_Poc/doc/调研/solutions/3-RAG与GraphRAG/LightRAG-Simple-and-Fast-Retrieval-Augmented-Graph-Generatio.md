---
title: LightRAG: Simple and Fast Retrieval-Augmented Graph Generation
source: https://arxiv.org/abs/2410.05779
date_published: 
collected: 2026-08-11
category: 3
tags: []
relevance: 高
maturity: 可复现
open_source: 是
repo: https://github.com/HKUDS/LightRAG
---

## 核心方法
港大提出的轻量级 GraphRAG：用双层检索（entity-level + relation-level）+ 低成本图构建。支持增量插入和按文档删除，多种图存储后端。

## 关键创新点
- 图+文本双层检索，local/global/hybrid/mix 模式
- 增量插入和按文档删除
- GraphML 可视化，source_id 来源字段

## 与本项目的关联
对应需求：知识库与知识图谱子系统。可借鉴：增量更新和按文档删除链路、双层检索模式。局限性：独立框架，与 RAGFlow 集成需要适配层。

## 实验数据/落地案例
在多个基准上比 GraphRAG 更快且效果相当或更好。
