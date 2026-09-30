# GCN_Poc RAGFlow 工具

本目录只保留可复用的客户端、监控、受控重建和服务器运维工具。固定题集、验收脚本和运行结果在 `../test/`。

## 环境

使用项目指定的 uv：

```bash
"D:/Program Files/uv/uv.exe" sync --project "D:/lxt/learn/Best_Practices/GCN_Poc/code"
```

必需的 RAGFlow API 环境变量：

```text
RAGFLOW_API_KEY
```

可选覆盖：

```text
RAGFLOW_BASE_URL
RAGFLOW_KB_NORMAL
RAGFLOW_KB_GRAPH
RAGFLOW_DOC_NORMAL
RAGFLOW_DOC_GRAPH
RAGFLOW_CHAT_NORMAL
RAGFLOW_CHAT_GRAPH
RAGFLOW_KB_LIGHT
RAGFLOW_CHAT_LIGHT
```

服务器检查和 GraphRAG 三层验收还需要：

```text
RAGFLOW_SSH_KEY
RAGFLOW_SSH_TARGET
RAGFLOW_SSH_PORT
RAGFLOW_REDIS_PASSWORD
RAGFLOW_ES_PASSWORD
```

不要把真实值写入代码、Markdown 或提交记录；从受控秘密来源注入。

## 常用命令

```bash
# 只读 RAGFlow 健康检查
"D:/Program Files/uv/uv.exe" run --project "D:/lxt/learn/Best_Practices/GCN_Poc/code" python "D:/lxt/learn/Best_Practices/GCN_Poc/code/ragflow_client.py"

# 只读 GraphRAG 进度监控
"D:/Program Files/uv/uv.exe" run --project "D:/lxt/learn/Best_Practices/GCN_Poc/code" python "D:/lxt/learn/Best_Practices/GCN_Poc/code/monitor_graphrag.py"

# 固定题集；结果应写入 test/results/<date>/
"D:/Program Files/uv/uv.exe" run --project "D:/lxt/learn/Best_Practices/GCN_Poc/code" python "D:/lxt/learn/Best_Practices/GCN_Poc/test/run_demo.py" --systems graph

# 三系统性能基准；默认 12 题 × 2 轮 × 3 系统，逐条落盘；Windows 子进程用临时 JSON 原子文件回传，单次测量硬超时 180 秒
"D:/Program Files/uv/uv.exe" run --project "D:/lxt/learn/Best_Practices/GCN_Poc/code" python "D:/lxt/learn/Best_Practices/GCN_Poc/test/benchmark_ragflow_modes.py" --rounds 2 --hard-timeout 180 --save "D:/lxt/learn/Best_Practices/GCN_Poc/test/results/<date>/ragflow_modes_benchmark.jsonl" --summary "D:/lxt/learn/Best_Practices/GCN_Poc/test/results/<date>/ragflow_modes_summary.json"

# 中断后按 (round, question_id, system) 唯一键续跑
"D:/Program Files/uv/uv.exe" run --project "D:/lxt/learn/Best_Practices/GCN_Poc/code" python "D:/lxt/learn/Best_Practices/GCN_Poc/test/benchmark_ragflow_modes.py" --rounds 2 --hard-timeout 180 --resume --save "D:/lxt/learn/Best_Practices/GCN_Poc/test/results/<date>/ragflow_modes_benchmark.jsonl" --summary "D:/lxt/learn/Best_Practices/GCN_Poc/test/results/<date>/ragflow_modes_summary.json"

# 正式 72 条基准已完成，无需再单独跑普通 RAG 14 次重复测试（normal 24/24 成功已等效覆盖）
# 正式 JSONL 完成后生成按题型性能（P50/P90/P95/P99、失败率、超时率）、规则覆盖和人工复核清单
"D:/Program Files/uv/uv.exe" run --project "D:/lxt/learn/Best_Practices/GCN_Poc/code" python "D:/lxt/learn/Best_Practices/GCN_Poc/test/analyze_ragflow_modes.py" "D:/lxt/learn/Best_Practices/GCN_Poc/test/results/<date>/ragflow_modes_benchmark.jsonl" --performance "D:/lxt/learn/Best_Practices/GCN_Poc/test/results/<date>/ragflow_modes_by_type.json" --quality-json "D:/lxt/learn/Best_Practices/GCN_Poc/test/results/<date>/quality_details.json" --markdown "D:/lxt/learn/Best_Practices/GCN_Poc/test/results/<date>/quality_summary.md"

# 受控重建：会删除当前图谱，必须显式确认
"D:/Program Files/uv/uv.exe" run --project "D:/lxt/learn/Best_Practices/GCN_Poc/code" python "D:/lxt/learn/Best_Practices/GCN_Poc/code/rebuild_graph.py" --confirm-delete DELETE_AND_REBUILD_PTR_GRAPH
```

`code/patches/ragflow-v0.26.1-2026-08-04/` 保存 131 运行时修复前后源码、diff 和哈希。它是审计与后续镜像化输入，不表示自定义镜像已经构建完成。
