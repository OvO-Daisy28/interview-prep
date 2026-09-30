# 解决方案收集器

> 用途：收集最新的、成熟的解决方案，供本项目开发借鉴参考
> 来源：优质论文（arXiv/ACL/EMNLP等）、公众号文章、技术博客、开源项目
> 维护方式：每条方案一个 .md 文件，按分类存放在子目录；本文件为索引

## 分类目录

### 1. 文档解析与结构化
论文/方案关于：版面分析、OCR、表格解析、章节识别、PDF/Word结构化提取
- 关键词：document parsing, layout analysis, table extraction, OCR, document AI
- 相关需求：内容解析子系统（3.2.1）

### 2. 知识图谱构建
论文/方案关于：实体抽取、关系抽取、实体消歧、社区发现、图谱合并
- 关键词：knowledge graph construction, entity extraction, entity disambiguation, community detection
- 相关需求：知识库与知识图谱子系统（3.2.2）

### 3. RAG 与 GraphRAG
论文/方案关于：检索增强生成、GraphRAG、LightRAG、混合检索、查询路由
- 关键词：RAG, GraphRAG, LightRAG, hybrid retrieval, query routing, reranking
- 相关需求：知识库与知识图谱子系统（3.2.2）、AI辅助编辑（3.2.7）

### 4. 信息抽取与参数提取
论文/方案关于：从非结构化文本中提取结构化参数、表格信息抽取
- 关键词：information extraction, parameter extraction, NER, table understanding
- 相关需求：参数提取（4.2.5）、表格解析（4.2.7）

### 5. 文档生成与模板引擎
论文/方案关于：结构化数据到文档的自动生成、模板渲染、条件化输出
- 关键词：document generation, template engine, NLG, data-to-text
- 相关需求：手册生成子系统（3.2.6）

### 6. 数据治理与质量管控
论文/方案关于：术语标准化、数据质量规则、变更管理、版本控制
- 关键词：data governance, terminology normalization, data quality, version control
- 相关需求：内容治理子系统（3.2.5）

### 7. LLM 工程与部署
论文/方案关于：LLM 私有化部署、推理优化、Prompt 工程、并发调度
- 关键词：LLM deployment, inference optimization, prompt engineering, vLLM, TGI
- 相关需求：通用技术要求（4.8.8）

### 8. 知识图谱推理与时序
论文/方案关于：时序知识图谱、知识推理、逻辑形式推理、多跳问答
- 关键词：temporal knowledge graph, knowledge reasoning, logical form, multi-hop QA
- 相关需求：时序知识构建（4.2.3.3）、语义检索与推理（4.2.3.4）

## 收录标准

1. **时效性**：优先收录 2024 年以后的方案；经典论文标注年份但保留
2. **成熟度**：有开源实现、有产业落地案例、或有详细实验数据的优先
3. **相关性**：与本项目需求（核电工程文件结构化、RAG/GraphRAG、文档生成）相关
4. **可操作性**：有具体方法描述、代码实现或架构设计的优先

## 条目模板

每条方案使用以下模板（见 `template.md`）：

```markdown
---
title: 方案标题
source: 论文/文章URL或出处
date_published: 发表日期
collected: 收录日期
category: 分类编号(1-8)
tags: [标签1, 标签2]
relevance: 高/中/低
maturity: 生产级/可复现/理论阶段
open_source: 是/否
repo: 开源仓库URL（如有）
---

## 核心方法
（3-5句话概括方案核心思路）

## 关键创新点
- 创新点1
- 创新点2

## 与本项目的关联
- 对应需求：XX子系统
- 可借鉴点：XX
- 局限性：XX

## 实验数据/落地案例
（如有实验数据或产业落地，简要记录）
```

## 使用方式

### 手工收录
1. 复制 `template.md` 到对应分类子目录
2. 填写 frontmatter 和正文
3. 更新本文件的索引表

### 工具辅助收录
使用 Python 脚本 `code/solution_collector.py` 从 URL 自动抓取元数据：

```bash
python code/solution_collector.py add <URL> --category <1-8> --relevance <高/中/低>
```

### 检索
```bash
# 按分类列出
python code/solution_collector.py list --category 3

# 按关键词搜索
python code/solution_collector.py search "GraphRAG"

# 导出索引
python code/solution_collector.py export
```
