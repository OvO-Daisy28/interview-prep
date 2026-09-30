---
title: RAGFlow: RAG-Focused Open-Source Engine
source: https://github.com/infiniflow/ragflow
date_published: 
collected: 2026-08-11
category: 3
tags: []
relevance: 高
maturity: 生产级
open_source: 是
repo: https://github.com/infiniflow/ragflow
---

## 核心方法
RAGFlow 是开源的 RAG 引擎，集成 DeepDoc 文档解析、MinerU 版面分析、向量/全文混合检索、GraphRAG 知识图谱、社区发现和问答。支持 Apache-2.0 二开。

## 关键创新点
- DeepDoc + MinerU 双解析引擎
- 内置 GraphRAG（实体/关系抽取、社区发现、社区报告）
- 知识图谱可视化

## 与本项目的关联
对应需求：知识库与知识图谱子系统。甲方指定主平台。可借鉴：完整 RAG + GraphRAG 链路。局限性：原生不支持版本治理、时序图谱、增量删除、2秒性能目标。

## 实验数据/落地案例
本项目 PTR 手册已验证：256 节点/128 边/41 社区报告；E2E P50=15-23秒。
