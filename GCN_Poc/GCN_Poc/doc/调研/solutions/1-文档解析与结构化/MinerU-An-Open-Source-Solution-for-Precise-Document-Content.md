---
title: MinerU: An Open-Source Solution for Precise Document Content Extraction
source: https://arxiv.org/abs/2409.18894
date_published: 
collected: 2026-08-11
category: 1
tags: []
relevance: 高
maturity: 生产级
open_source: 是
repo: https://github.com/opendatalab/MinerU
---

## 核心方法
上海 AI Lab 开源的文档解析工具：版面分析 + OCR + 公式/表格识别，将 PDF/Word 转为结构化 Markdown/JSON。支持中文、多栏、复杂表格。

## 关键创新点
- 高精度版面分析模型（LayoutLMv3 改进）
- 表格结构识别（含合并单元格）
- 数学公式 OCR

## 与本项目的关联
对应需求：内容解析子系统。甲方指定工具，作为文档解析的基座。可借鉴：表格结构识别算法、版面分析模型。局限性：不直接输出参数级结构化数据，需在其上层开发参数提取。

## 实验数据/落地案例
在 PubTabNet 等基准上表格识别 F1 > 90%。
