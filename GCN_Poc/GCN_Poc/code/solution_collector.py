#!/usr/bin/env python
"""Solution Collector — 收集和管理解决方案参考条目。

Usage:
    python solution_collector.py add <URL> [--category <1-8>] [--relevance <高/中/低>] [--tags tag1,tag2]
    python solution_collector.py list [--category <1-8>]
    python solution_collector.py search <keyword>
    python solution_collector.py export
    python solution_collector.py seed  # 初始化种子条目
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# fmt: off
CATEGORIES = {
    1: "1-文档解析与结构化",
    2: "2-知识图谱构建",
    3: "3-RAG与GraphRAG",
    4: "4-信息抽取与参数提取",
    5: "5-文档生成与模板引擎",
    6: "6-数据治理与质量管控",
    7: "7-LLM工程与部署",
    8: "8-知识图谱推理与时序",
}

CATEGORY_NAMES = {
    1: "文档解析与结构化",
    2: "知识图谱构建",
    3: "RAG与GraphRAG",
    4: "信息抽取与参数提取",
    5: "文档生成与模板引擎",
    6: "数据治理与质量管控",
    7: "LLM工程与部署",
    8: "知识图谱推理与时序",
}
# fmt: on

BASE_DIR = Path(__file__).resolve().parent.parent / "doc" / "调研" / "solutions"
TEMPLATE = BASE_DIR / "template.md"


@dataclass
class SolutionEntry:
    title: str = ""
    source: str = ""
    date_published: str = ""
    collected: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    category: int = 3
    tags: list[str] = field(default_factory=list)
    relevance: str = "中"
    maturity: str = "可复现"
    open_source: str = "否"
    repo: str = ""
    core_method: str = ""
    innovations: list[str] = field(default_factory=list)
    project_relevance: str = ""
    experiment_data: str = ""


def slugify(text: str, max_len: int = 60) -> str:
    """生成文件安全的 slug。"""
    text = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text.strip())
    return text[:max_len].strip("-")


def fetch_url_title(url: str) -> str:
    """从 URL 抓取页面标题。"""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read(65536).decode("utf-8", errors="ignore")
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return url.split("/")[-1][:60] or url


def parse_frontmatter(content: str) -> dict:
    """解析 Markdown frontmatter。"""
    m = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.S)
    if not m:
        return {}
    fm_text = m.group(1)
    result = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                val = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",") if x.strip()]
            result[key] = val
    return result


def format_entry(entry: SolutionEntry) -> str:
    """格式化条目为 Markdown。"""
    tags_str = ", ".join(entry.tags) if entry.tags else ""
    innovations = "\n".join(f"- {i}" for i in entry.innovations) if entry.innovations else "- "

    return f"""---
title: {entry.title}
source: {entry.source}
date_published: {entry.date_published}
collected: {entry.collected}
category: {entry.category}
tags: [{tags_str}]
relevance: {entry.relevance}
maturity: {entry.maturity}
open_source: {entry.open_source}
repo: {entry.repo}
---

## 核心方法
{entry.core_method or ''}

## 关键创新点
{innovations}

## 与本项目的关联
{entry.project_relevance or ''}

## 实验数据/落地案例
{entry.experiment_data or ''}
"""


def get_category_dir(category: int) -> Path:
    return BASE_DIR / CATEGORIES.get(category, CATEGORIES[3])


def add_entry(url: str, category: int, relevance: str, tags: list[str], title: str | None = None) -> Path:
    """添加新条目。"""
    if title is None:
        title = fetch_url_title(url)

    entry = SolutionEntry(
        title=title,
        source=url,
        category=category,
        relevance=relevance,
        tags=tags,
    )

    cat_dir = get_category_dir(category)
    cat_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(title)
    if not slug:
        slug = hashlib.md5(url.encode()).hexdigest()[:8]

    filepath = cat_dir / f"{slug}.md"

    if filepath.exists():
        print(f"  已存在: {filepath}")
        return filepath

    filepath.write_text(format_entry(entry), encoding="utf-8")
    print(f"  已创建: {filepath}")
    return filepath


def list_entries(category: int | None = None) -> list[dict]:
    """列出所有条目。"""
    entries = []
    if category:
        dirs = [get_category_dir(category)]
    else:
        dirs = [BASE_DIR / CATEGORIES[c] for c in CATEGORIES]

    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md")):
            if f.name == "template.md":
                continue
            content = f.read_text(encoding="utf-8")
            fm = parse_frontmatter(content)
            if fm:
                entries.append({**fm, "file": str(f), "category_name": CATEGORY_NAMES.get(int(fm.get("category", 0)), "")})
    return entries


def search_entries(keyword: str) -> list[dict]:
    """搜索条目。"""
    entries = list_entries()
    keyword_lower = keyword.lower()
    results = []
    for e in entries:
        searchable = " ".join([
            e.get("title", ""),
            e.get("source", ""),
            e.get("tags", "") if isinstance(e.get("tags"), str) else " ".join(e.get("tags", [])),
            e.get("category_name", ""),
        ]).lower()
        if keyword_lower in searchable:
            results.append(e)
    return results


def export_index() -> str:
    """导出索引表为 Markdown。"""
    entries = list_entries()
    if not entries:
        return "暂无条目。"

    lines = ["# 解决方案索引", ""]
    lines.append(f"共 {len(entries)} 条 | 更新于 {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    for cat_id in sorted(CATEGORIES.keys()):
        cat_entries = [e for e in entries if int(e.get("category", 0)) == cat_id]
        if not cat_entries:
            continue
        lines.append(f"## {cat_id}. {CATEGORY_NAMES[cat_id]} ({len(cat_entries)}条)")
        lines.append("")
        lines.append("| 标题 | 来源 | 相关度 | 成熟度 | 开源 | 收录日期 |")
        lines.append("|---|---|---|---|---|---|")
        for e in cat_entries:
            title = e.get("title", "")
            source = e.get("source", "")
            relevance = e.get("relevance", "")
            maturity = e.get("maturity", "")
            open_source = e.get("open_source", "")
            collected = e.get("collected", "")
            lines.append(f"| {title} | {source} | {relevance} | {maturity} | {open_source} | {collected} |")
        lines.append("")

    return "\n".join(lines)


# ─── 种子数据 ──────────────────────────────────────────────

SEED_ENTRIES = [
    {
        "title": "GraphRAG: Unlocking LLM 's discovery ability through knowledge graph-based retrieval",
        "source": "https://arxiv.org/abs/2404.16130",
        "category": 3,
        "relevance": "高",
        "maturity": "可复现",
        "open_source": "是",
        "repo": "https://github.com/microsoft/graphrag",
        "core_method": "微软提出的 GraphRAG 方案：先用 LLM 从文档中抽取实体和关系构建知识图谱，再用 Leiden 算法进行社区发现，为每个社区生成摘要。查询时分 local（实体定位）和 global（社区摘要跨章节汇总）两种模式。",
        "innovations": [
            "社区发现 + 社区摘要实现全局问题跨文档汇总",
            "支持增量 update（仅对新增文档重新抽取和合并子图）",
            "Local/Global/DRIFT 三种查询模式",
        ],
        "project_relevance": "对应需求：知识库与知识图谱子系统。可借鉴：社区发现和社区摘要算法、增量更新思路。局限性：建图 Token 成本高，单文档建图耗时长。",
        "experiment_data": "微软在公开基准上验证了 global 查询对跨文档汇总问题的效果优势。",
    },
    {
        "title": "LightRAG: Simple and Fast Retrieval-Augmented Graph Generation",
        "source": "https://arxiv.org/abs/2410.05779",
        "category": 3,
        "relevance": "高",
        "maturity": "可复现",
        "open_source": "是",
        "repo": "https://github.com/HKUDS/LightRAG",
        "core_method": "港大提出的轻量级 GraphRAG：用双层检索（entity-level + relation-level）+ 低成本图构建。支持增量插入和按文档删除，多种图存储后端。",
        "innovations": [
            "图+文本双层检索，local/global/hybrid/mix 模式",
            "增量插入和按文档删除",
            "GraphML 可视化，source_id 来源字段",
        ],
        "project_relevance": "对应需求：知识库与知识图谱子系统。可借鉴：增量更新和按文档删除链路、双层检索模式。局限性：独立框架，与 RAGFlow 集成需要适配层。",
        "experiment_data": "在多个基准上比 GraphRAG 更快且效果相当或更好。",
    },
    {
        "title": "KAG: Boosting LLMs in Professional Domains via Knowledge Augmented Generation",
        "source": "https://arxiv.org/abs/2409.13731",
        "category": 8,
        "relevance": "中",
        "maturity": "可复现",
        "open_source": "是",
        "repo": "https://github.com/OpenSPG/KAG",
        "core_method": "蚂蚁集团面向专业领域严谨问答的框架：Schema 约束 + 逻辑形式推理。用 LLMFriSPG 知识表示兼容无 Schema 抽取与有 Schema 约束，图谱-文本双向互索引。",
        "innovations": [
            "Schema 约束的领域建模 + 符号逻辑推理",
            "逻辑形式引导的混合推理引擎",
            "多跳问答基准上显著超过 GraphRAG",
        ],
        "project_relevance": "对应需求：时序知识图谱、语义推理。可借鉴：Schema 约束建模思路、规则推理方向。局限性：延迟高（~40s），双平台架构成本高，Java 技术栈。",
        "experiment_data": "HotpotQA F1 提升 19.6%，2WikiMultiHopQA 提升 33.5%。支付宝政务落地 1.1 万份文档。",
    },
    {
        "title": "MinerU: An Open-Source Solution for Precise Document Content Extraction",
        "source": "https://arxiv.org/abs/2409.18894",
        "category": 1,
        "relevance": "高",
        "maturity": "生产级",
        "open_source": "是",
        "repo": "https://github.com/opendatalab/MinerU",
        "core_method": "上海 AI Lab 开源的文档解析工具：版面分析 + OCR + 公式/表格识别，将 PDF/Word 转为结构化 Markdown/JSON。支持中文、多栏、复杂表格。",
        "innovations": [
            "高精度版面分析模型（LayoutLMv3 改进）",
            "表格结构识别（含合并单元格）",
            "数学公式 OCR",
        ],
        "project_relevance": "对应需求：内容解析子系统。甲方指定工具，作为文档解析的基座。可借鉴：表格结构识别算法、版面分析模型。局限性：不直接输出参数级结构化数据，需在其上层开发参数提取。",
        "experiment_data": "在 PubTabNet 等基准上表格识别 F1 > 90%。",
    },
    {
        "title": "RAGFlow: RAG-Focused Open-Source Engine",
        "source": "https://github.com/infiniflow/ragflow",
        "category": 3,
        "relevance": "高",
        "maturity": "生产级",
        "open_source": "是",
        "repo": "https://github.com/infiniflow/ragflow",
        "core_method": "RAGFlow 是开源的 RAG 引擎，集成 DeepDoc 文档解析、MinerU 版面分析、向量/全文混合检索、GraphRAG 知识图谱、社区发现和问答。支持 Apache-2.0 二开。",
        "innovations": [
            "DeepDoc + MinerU 双解析引擎",
            "内置 GraphRAG（实体/关系抽取、社区发现、社区报告）",
            "知识图谱可视化",
        ],
        "project_relevance": "对应需求：知识库与知识图谱子系统。甲方指定主平台。可借鉴：完整 RAG + GraphRAG 链路。局限性：原生不支持版本治理、时序图谱、增量删除、2秒性能目标。",
        "experiment_data": "本项目 PTR 手册已验证：256 节点/128 边/41 社区报告；E2E P50=15-23秒。",
    },
    {
        "title": "vLLM: Easy, Fast, and Cheap LLM Serving",
        "source": "https://arxiv.org/abs/2309.06180",
        "category": 7,
        "relevance": "高",
        "maturity": "生产级",
        "open_source": "是",
        "repo": "https://github.com/vllm-project/vllm",
        "core_method": "UC Berkeley 开源的 LLM 推理引擎：PagedAttention 内存管理 + 连续批处理，大幅提升 GPU 利用率和吞吐量。支持主流开源模型。",
        "innovations": [
            "PagedAttention 减少 KV Cache 内存碎片",
            "连续批处理（continuous batching）提升吞吐",
            "支持张量并行和流水线并行",
        ],
        "project_relevance": "对应需求：LLM 私有化部署（4.8.8）。可借鉴：本地 LLM 推理服务，解决外部 API 延迟瓶颈。局限性：需要 GPU 资源。",
        "experiment_data": "比 HuggingFace Transformers 吞吐高 24x（A100 基准）。",
    },
    {
        "title": "RAGAS: RAG Assessment Framework",
        "source": "https://arxiv.org/abs/2309.15217",
        "category": 6,
        "relevance": "中",
        "maturity": "可复现",
        "open_source": "是",
        "repo": "https://github.com/explodinggradients/ragas",
        "core_method": "RAGAS 是 RAG 系统评估框架：从答案相关性、上下文相关性、忠实性（faithfulness）和上下文召回率四个维度评估 RAG 质量，无需人工标注。",
        "innovations": [
            "无人工标注的自动评估",
            "多维度指标（faithfulness, answer_relevancy, context_precision, context_recall）",
        ],
        "project_relevance": "对应需求：数据治理与质量管控。可借鉴：RAG 系统质量评估指标体系。局限性：LLM 评估本身有偏差，需要结合人工抽检。",
        "experiment_data": "在多个 RAG 基准上验证了指标与人工评分的相关性。",
    },
]


def seed_entries() -> None:
    """初始化种子条目。"""
    print("初始化种子条目...")
    for seed in SEED_ENTRIES:
        title = seed["title"]
        url = seed["source"]
        category = seed["category"]
        relevance = seed["relevance"]

        cat_dir = get_category_dir(category)
        cat_dir.mkdir(parents=True, exist_ok=True)

        slug = slugify(title)
        filepath = cat_dir / f"{slug}.md"

        if filepath.exists():
            print(f"  跳过(已存在): {filepath.name}")
            continue

        entry = SolutionEntry(
            title=title,
            source=url,
            category=category,
            relevance=relevance,
            maturity=seed.get("maturity", "可复现"),
            open_source=seed.get("open_source", "否"),
            repo=seed.get("repo", ""),
            core_method=seed.get("core_method", ""),
            innovations=seed.get("innovations", []),
            project_relevance=seed.get("project_relevance", ""),
            experiment_data=seed.get("experiment_data", ""),
        )

        filepath.write_text(format_entry(entry), encoding="utf-8")
        print(f"  已创建: {filepath.name}")

    # 导出索引
    index = export_index()
    index_path = BASE_DIR / "INDEX.md"
    index_path.write_text(index, encoding="utf-8")
    print(f"  索引已导出: {index_path}")


# ─── CLI ───────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="解决方案收集器")
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="从 URL 添加条目")
    p_add.add_argument("url", help="论文/文章 URL")
    p_add.add_argument("--category", type=int, default=3, choices=list(CATEGORIES.keys()))
    p_add.add_argument("--relevance", default="中", choices=["高", "中", "低"])
    p_add.add_argument("--tags", default="", help="逗号分隔的标签")
    p_add.add_argument("--title", default=None, help="手动指定标题")

    p_list = sub.add_parser("list", help="列出条目")
    p_list.add_argument("--category", type=int, default=None, choices=list(CATEGORIES.keys()))

    p_search = sub.add_parser("search", help="搜索条目")
    p_search.add_argument("keyword", help="搜索关键词")

    sub.add_parser("export", help="导出索引")

    sub.add_parser("seed", help="初始化种子条目")

    args = parser.parse_args()

    if args.command == "add":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        add_entry(args.url, args.category, args.relevance, tags, args.title)
        # 重新导出索引
        index = export_index()
        (BASE_DIR / "INDEX.md").write_text(index, encoding="utf-8")
        return 0

    elif args.command == "list":
        entries = list_entries(args.category)
        if not entries:
            print("暂无条目。")
            return 0
        for e in entries:
            print(f"  [{e.get('category', '')}] {e.get('title', '')} — {e.get('source', '')}")
        print(f"\n共 {len(entries)} 条")
        return 0

    elif args.command == "search":
        results = search_entries(args.keyword)
        if not results:
            print(f"未找到包含 '{args.keyword}' 的条目。")
            return 0
        for r in results:
            print(f"  [{r.get('category', '')}] {r.get('title', '')} — {r.get('source', '')}")
        print(f"\n共 {len(results)} 条匹配")
        return 0

    elif args.command == "export":
        index = export_index()
        index_path = BASE_DIR / "INDEX.md"
        index_path.write_text(index, encoding="utf-8")
        print(index)
        print(f"\n索引已导出到: {index_path}")
        return 0

    elif args.command == "seed":
        seed_entries()
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
