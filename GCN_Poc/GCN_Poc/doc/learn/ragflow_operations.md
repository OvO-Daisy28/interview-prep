# RAGFlow 操作手册 & 踩坑记录

> 本文档是 GCN_Poc 项目操作 RAGFlow 的唯一参考（SSOT）。所有环境信息、API 用法、踩坑根因、修复方案均落盘于此，避免重复踩坑。
> 最后更新：2026-08-04（完成 GraphRAG 业务链路修复与真实重建验收）

---

## 一、环境信息（不含真实凭据）

真实账号和密钥只能从受控秘密来源注入。本文只记录环境变量名、服务标识和获取方式，不保存可直接登录或调用的值。

### 1.1 RAGFlow 服务

| 项 | 值 |
|---|---|
| Web 界面 | http://10.126.2.131:9388 |
| API Base | http://10.126.2.131:9388 |
| 登录账号 | 见受控账号来源 |
| 登录密码 | 见受控秘密来源，不落盘 |
| API Key | 环境变量 `RAGFLOW_API_KEY` |
| RAGFlow 版本 | v0.26.1（docker 镜像 infiniFlow/ragflow:v0.26.1） |
| Docker 容器 | `docker-ragflow-cpu-1`（在 10.126.2.131 上） |

### 1.2 服务器 SSH（经 JumpServer）

| 项 | 值 |
|---|---|
| JumpServer 地址 | jumpserver.wengegroup.com:2222 |
| SSH 用户格式 | `lixiaotong@root@10.126.2.131`（用户@目标用户@目标IP） |
| SSH Key | 环境变量 `RAGFLOW_SSH_KEY` 指向受控私钥路径 |
| SSH 目标 | 环境变量 `RAGFLOW_SSH_TARGET`；端口用 `RAGFLOW_SSH_PORT` |

> JumpServer 详细用法见 [learn/jumpserver-kiro-claude-code-remote-development.md](../../../learn/jumpserver-kiro-claude-code-remote-development.md)

### 1.3 依赖服务（容器内）

| 服务 | 容器名 | 凭据 | 用途 |
|---|---|---|---|
| Redis | docker-redis-1 | 环境变量 `RAGFLOW_REDIS_PASSWORD` | 任务队列、checkpoint |
| Elasticsearch | docker-es01-1 | `RAGFLOW_ES_USER` / `RAGFLOW_ES_PASSWORD` | doc store（向量+全文+图谱） |
| MySQL | docker-mysql-1 | 见 service_conf.yaml | 任务表、KB 配置 |

### 1.4 LLM API

| 项 | 值 |
|---|---|
| Base URL | https://aicoding.wenge.com |
| API Key | 由 RAGFlow 模型供应商配置或受控秘密来源管理，不在本项目落盘 |
| PTR 当前可用模型 | `deepreasoning-ds-v4flash@deepreasoning-ds-v4flash@ModelScope` |
| 已失效模型实例 | 默认 OpenAI-Compatible 返回 `401 API_KEY_DISABLED`；Tongyi-Qianwen 返回 `overdue-payment`；`deepreasoning-gl-5.2` 同受上游密钥禁用影响 |
| 配置范围 | 仅 PTR GraphRAG 知识库、对应文档和 `demo_graph_v4` 切换到 ModelScope；租户默认模型和普通 RAG 库未修改 |
| 选择原则 | 以真实最小调用和结构化输出成功为准，不再按模型名称静态判断可用性 |

---

## 二、核心数据（KB / 文档 / 会话 ID）

### 2.1 知识库

| 名称 | KB ID | 类型 | 状态 |
|---|---|---|---|
| PTR_普通RAG | `4ec640408cc711f19f3f45f212d2b89e` | 普通向量检索 | ✅ 162 chunks |
| PTR_GraphRAG | `4ec8cbda8cc711f19f3f45f212d2b89e` | GraphRAG | ✅ 256 nodes / 128 edges；41 条有效社区报告；KG/Chat 接入已验收 |

### 2.2 文档

| 文档 | Doc ID | 所属 KB |
|---|---|---|
| PTR冷却泵设备运行与维修手册.docx（普通RAG） | `4ed0f9d68cc711f19f3f45f212d2b89e` | PTR_普通RAG |
| PTR冷却泵设备运行与维修手册.docx（GraphRAG） | `4ee267488cc711f19f3f45f212d2b89e` | PTR_GraphRAG |

### 2.3 会话（Chat Assistant）

| 名称 | Chat ID | 关联 KB |
|---|---|---|
| demo_normal_v3 | `d3df2baa8f0d11f18512c56e2ff23bb9` | PTR_普通RAG |
| demo_graph_v4 | `2fc6e9e48f0e11f18512c56e2ff23bb9` | PTR_GraphRAG |

### 2.4 tenant_id

`56f78bf26ac611f187cd7db89d62ca74`（ES 索引名 `ragflow_<tenant_id>`）

---

## 三、RAGFlow API 速查

### 3.1 知识库 & 文档

```python
import os

BASE = os.environ.get("RAGFLOW_BASE_URL", "http://10.126.2.131:9388")
KEY = os.environ["RAGFLOW_API_KEY"]
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

# 查 KB 配置
GET /api/v1/datasets/{kb_id}

# 查文档列表
GET /api/v1/datasets/{kb_id}/documents?id={doc_id}

# 触发文档解析
POST /api/v1/datasets/{kb_id}/documents/parse
body: {"document_ids": [doc_id]}
```

### 3.2 GraphRAG

```python
# 触发 GraphRAG 构建
POST /api/v1/datasets/{kb_id}/index?type=graph

# 查 GraphRAG 构建进度
GET /api/v1/datasets/{kb_id}/index?type=graph
# 返回 data.progress (0~1), data.progress_msg

# 查图谱（可视化用，返回 nodes + edges）
GET /api/v1/datasets/{kb_id}/graph
# 返回 data.graph.{nodes, edges}，nodes 有 entity_type/description/pagerank

# ★ 删图谱（清 graph/subgraph/entity/relation/community_report + phase marker）
DELETE /api/v1/datasets/{kb_id}/graph
# 重跑 GraphRAG 前必须先调这个，否则会触发 "already merged" 跳过（见坑#5）
```

### 3.3 问答

```python
# 创建会话
POST /api/v1/chats
body: {"name": "xxx", "dataset_ids": [kb_id]}
# 返回 data.id = chat_id
# 注意：data 可能是 dict（含 id 字段），不是 list

# 列出会话
GET /api/v1/chats?page_size=20
# 返回 data.chats（list）

# 问答
POST /api/v1/chats/{chat_id}/completions
body: {"question": "xxx", "stream": false}
# 返回 data.answer

# 检索（不生成答案，只看召回的 chunk）
POST /api/v1/retrieval
body: {"question": "xxx", "dataset_ids": [kb_id], "page_size": 5, "use_kg": true}
# `/retrieval` 默认不启用 KG，必须显式传 use_kg=true。
# 修复后 PTR 实测：use_kg=false 返回 4 个普通 chunk；use_kg=true 返回 5 个 chunk，
# 首个为 document_keyword="Related content in Knowledge Graph" 的社区聚合块。
```

### 3.4 图谱数据结构

```
GET /graph 返回的 node:
{
  "id": "泵",              # 实体名（去重后）
  "entity_name": "泵",
  "entity_type": "设备",   # 9种之一
  "description": "...",    # LLM 生成的实体描述
  "pagerank": 0.023,       # 重要性
  "source_id": [doc_id]
}

edge:
{
  "source": "泵",
  "target": "叶轮",
  "weight": 1,
  "description": "..."     # 关系描述
}
```

---

## 四、踩坑记录（按严重程度排序）

### 坑 #1：task_executor 不消费 graphrag 队列

**现象**：触发 GraphRAG 构建后，progress 一直是 0，任务卡在 "created task graphrag"。

**根因**：RAGFlow 的 task_executor 默认只订阅 `common` 队列，不订阅 `graphrag` 队列。需要在启动 worker 时指定 `-t graphrag`。

**排查**：
```bash
# 进容器看 worker 日志
docker exec docker-ragflow-cpu-1 bash -c "tail -100 /ragflow/logs/task_executor*.log"

# 看 Redis 队列（容器内）
docker exec docker-redis-1 redis-cli -a "$RAGFLOW_REDIS_PASSWORD" LLEN ragflow_svr_task_queue
docker exec docker-redis-1 redis-cli -a "$RAGFLOW_REDIS_PASSWORD" LLEN ragflow_svr_task_queue_graphrag
```

**修复**：以模块方式启动专用 GraphRAG worker
```bash
docker exec docker-ragflow-cpu-1 bash -c "cd /ragflow && nohup python -m rag.svr.task_executor -t graphrag >/ragflow/logs/task_executor_graphrag_manual.log 2>&1 &"
```

**队列注意**：v0.26.1 当前运行代码的 `get_svr_queue_name()` 忽略 suffix，普通任务与 GraphRAG 可能共用 Redis Stream `te.0.common`。排查时使用 `XINFO GROUPS`、`XINFO CONSUMERS` 和 pending/unacked 信息，不要只查旧版 list 队列名。

**预防**：每次重启容器后，检查 GraphRAG worker 进程和 Redis 心跳；恢复 pending 任务时优先启动同名 consumer 接管原消息，不重复触发任务。

---

### 坑 #2：reasoning 模型 max_tokens 不足导致 content 为空

**现象**：GraphRAG 抽取实体/关系为空（0 nodes, 0 edges），但 LLM 确实被调用了。

**根因**：`deepreasoning-ds-v4*` 是 reasoning 模型，会先输出 `reasoning_content`（思考过程），再输出 `content`（最终答案）。RAGFlow 默认 `max_tokens=1024`，reasoning_content 占满后 content 为空。

**排查**：
```bash
# 看日志里的 token 统计
docker exec docker-ragflow-cpu-1 bash -c "grep 'tokens' /ragflow/logs/task_executor_graphrag_*.log | tail -20"
# 如果 tokens 接近 max_tokens 但 nodes=0，就是这个坑
```

**修复**：改 RAGFlow 源码注入大 max_tokens
- 文件：`/ragflow/rag/llm/chat_model.py`
- 位置：`Base.async_chat` 方法里 `gen_conf = self._clean_conf(gen_conf)` 之后
- 插入：`gen_conf.setdefault("max_tokens", 16000)`

**替代方案**：用非 reasoning 模型（如 deepseek-chat、qwen-plus），但抽取质量可能下降。

---

### 坑 #3：reasoning 模型破坏结构化输出格式

**现象**：reasoning 模型输出的 `reasoning_content` 包含思考过程，破坏了 GraphRAG 要求的严格 JSON 格式，导致实体/关系解析失败。

**根因**：GraphRAG 的 `handle_single_entity_extraction` / `handle_single_relationship_extraction` 用正则解析 LLM 输出，reasoning_content 的 `<think>...</think>` 标签干扰解析。

**缓解**：
- 优先用 `deepreasoning-ds-v4pro`（比 v4flash 稳定）
- max_tokens 设大（16000+）让 content 有空间输出完整 JSON
- 接受部分 chunk 抽取为空（16 个 chunk 里可能有 7 个为空），靠总量补

**教训**：GraphRAG 任务**不要用 reasoning 模型**，用非 reasoning 的 chat 模型（deepseek-chat、qwen-plus、gpt-4o-mini）。reasoning 模型的思考过程破坏严格格式解析。这条已写入 project_memory。

---

### 坑 #4：checkpoint 机制导致跳过重新抽取

**现象**：改了模型/参数后重跑 GraphRAG，结果不变。

**根因**：RAGFlow 有 checkpoint 机制：
- `does_graph_contains(kb_id)` 检查是否已有图谱 → 有则跳过
- `load_subgraph_from_store(doc_id)` 加载已有 subgraph → 有则复用

**修复**（二选一）：
1. **推荐**：调 `DELETE /api/v1/datasets/{kb_id}/graph` 清掉旧图谱（含 phase marker），重跑
2. 暴力改源码：`does_graph_contains` 返回 False，`load_subgraph_from_store` 返回 None

---

### 坑 #5：★ 补丁不完整导致 edges 丢失（最严重）

**现象**：progress_msg 报 "225 edges"，但 `/graph` API 返回 0 edges，0 社区，可视化看不到边。

**根因**：之前打了 `[GCN_Poc]` 补丁强制重新抽取（坑#4的方案2），但**没改 `merge_subgraph_attempt` 的 "already merged" 检查**：
```python
# index.py:496
current_graph = await get_graph(tenant_id, kb_id)
if current_graph and doc_id in current_graph.graph.get("source_id", []):
    callback("already merged, skipping retry.")
    return current_graph  # ← 直接返回旧 graph，新 subgraph 白抽了
```
第一次运行（0 edges）把 doc_id 写入 graph.source_id，第二次运行（225 edges）被判定"已合并"跳过，225 edges 的 subgraph 白抽，set_graph 把 0-edges 覆盖写回。

**ES 实际数据**（直查确认）：
| 类型 | 数量 | 说明 |
|---|---|---|
| entity | 87 | 第一次运行写的，残留 |
| relation | **0** | 从未成功写入 |
| graph | 1 | 87 nodes, **0 edges** |
| subgraph | 1 | 87 nodes, **0 edges**（被覆盖） |
| community_report | 0 | 历史失败运行：0 edges → 0 communities；当前成功运行日志显示生成/写入 24 个，但 ES 精确查询命中 8 条且内容存在跨领域污染，不能只看数量 |

**修复**：
1. 调 `DELETE /api/v1/datasets/{kb_id}/graph` 清旧图谱（清掉 phase marker + source_id 标记）
2. 重新 `POST /index?type=graph`（无需打任何补丁）
3. 确保 graphrag worker 在跑（坑#1）

**教训**：改 RAGFlow 源码要完整追踪调用链，不能只改一处。优先用官方 API（DELETE /graph）而非改源码。

---

### 坑 #6：PowerShell 引号转义问题

**现象**：在 PowerShell 里用 `python -c "..."` 执行内联脚本时，引号嵌套导致 SyntaxError。

**根因**：PowerShell 对单引号/双引号的处理与 bash 不同，`f'...{x.get("key")}'` 里的双引号会被 PowerShell 解析。

**修复**：不要用 `python -c`，改用 Write 写脚本文件再 `python script.py`。

---

### 坑 #7：容器重启后 task_executor 挂掉

**现象**：重启 docker-ragflow-cpu-1 后，文档解析任务卡住。

**根因**：task_executor 进程没随容器自动启动，或启动后崩了。

**排查**：
```bash
docker exec docker-ragflow-cpu-1 bash -c "ps aux | grep task_executor"
# 如果没有进程，就是挂了
```

**修复**：重启容器 `docker restart docker-ragflow-cpu-1`，或手动启动 worker。

---

### 坑 #8：GraphRAG 合并子图超时导致最终图谱为空

**现象**：抽取阶段已有大量实体，日志显示 `Get embedding of nodes: .../747`，但最终进度为 `-1`，`GET /graph` 返回 0 nodes / 0 edges。

**根因证据（2026-08-03）**：当前数据集配置 `merge_timeout_seconds=180`、`retry_attempts=2`。`merge_subgraph` 第一次在 180 秒超时，重试后第二次仍在 180 秒超时，任务最终失败。这里不是坑 #5 的 `already merged`，也不是 0 实体抽取。

**修复结果（2026-08-04）**：将知识库级 `merge_timeout_seconds` 提升到 900，并修复模型、社区报告和 Chat KG 链路后，原任务成功完成：`progress=1.0`、`ok=1`、总耗时 1255.08 秒、256 nodes / 128 edges。运行时会重新读取知识库 parser_config，因此实际使用 900 秒，而不是 Redis 消息旧文档快照中的 180 秒。

**结论**：`DELETE /graph → POST /index` 不是充分修复；必须先定位 worker、模型、合并超时、社区落库和 Chat 接入中的具体根因。验收至少包含任务、图主体、社区落库和 KG 检索四层。

---

### 坑 #9：会话创建 API 返回格式不一致

**现象**：`POST /api/v1/chats` 偶发返回的 data 结构不一致，有时是 dict（含 id），有时解析失败。

**修复**：代码里兼容处理
```python
d = r.json().get("data", {})
if isinstance(d, dict):
    cid = d.get("id") or d.get("chat_id")
```

---

## 五、操作 SOP

### 5.1 从零搭建 demo（完整流程）

```
1. 上传文档到 RAGFlow（Web 界面或 API）
2. 建普通 RAG 库：解析文档 → embedding → 索引
3. 建 GraphRAG 库：同文档，parser_config.graphrag.use_graphrag=true
4. 触发 GraphRAG：POST /index?type=graph
5. 确保 graphrag worker 在跑（坑#1）
6. 等待构建完成（GET /index?type=graph 查进度，~11分钟）
7. 验证图谱：GET /graph 看 nodes/edges 数量
8. 创建会话：POST /chats
9. 跑对比问答：POST /chats/{id}/completions
```

### 5.2 GraphRAG 构建失败的修复流程

```
1. 查进度：GET /index?type=graph → 看 progress_msg
2. 如果 progress=0 卡住 → 坑#1（graphrag worker）
3. 如果 0 nodes → 坑#2（max_tokens）或坑#3（reasoning 模型）
4. 如果 0 edges 且任务显示完成 → 坑#5（补丁不完整 / already merged）
5. 如果 progress=-1 且日志含 `merge_subgraph ... timeout after 180s` → 坑#8（合并超时）
6. 修复前先确认具体根因；只有坑#5可直接按 DELETE /graph → POST /index?type=graph 重跑，坑#8还需先调整超时或构建策略
```

### 5.3 查看每一步骤的效果

| 步骤 | 在哪看 | 看什么 |
|---|---|---|
| 文档解析 | Web → 知识库 → 文档列表 | run=DONE, progress=1.0, chunk_count>0 |
| 普通 RAG 检索 | `POST /retrieval` | chunks 数量、content 相关性 |
| GraphRAG 实体抽取 | `GET /graph` | nodes 数量、entity_type 分布 |
| GraphRAG 关系抽取 | `GET /graph` | edges > 0；“应为 nodes 的 1-3 倍”仅作经验观察，不作为硬验收阈值 |
| 社区发现 | `GET /graph` + ES 直查 community_report | 数量、`kb_id`/`source_id`、报告正文领域一致性；当前不能只用 `mind_map` 判定 |
| 图谱可视化 | Web → 知识库 → 知识图谱页面 | 节点+边的图形化展示 |
| 问答对比 | `POST /chats/{id}/completions` | answer 内容、引用来源 |

### 5.4 服务器直查 ES（高级排查）

> 修复后终态：Leiden 发现 43 个候选社区，其中 41 条报告成功生成并索引；ES 精确命中 41 条、唯一 ID 41 个、来源字段全部正确，`Unity March`、`Verdant Oasis Plaza`、`Harmony Assembly` 命中为 0。43 是候选社区口径，41 是最终有效报告口径，不得混用。

```bash
# 进容器
docker exec docker-es01-1 bash

# 按 knowledge_graph_kwd 统计
curl -u "$RAGFLOW_ES_USER:$RAGFLOW_ES_PASSWORD" -X GET "localhost:9200/ragflow_56f78bf26ac611f187cd7db89d62ca74/_count?q=knowledge_graph_kwd:relation"
curl -u "$RAGFLOW_ES_USER:$RAGFLOW_ES_PASSWORD" -X GET "localhost:9200/ragflow_56f78bf26ac611f187cd7db89d62ca74/_count?q=knowledge_graph_kwd:entity"
curl -u "$RAGFLOW_ES_USER:$RAGFLOW_ES_PASSWORD" -X GET "localhost:9200/ragflow_56f78bf26ac611f187cd7db89d62ca74/_count?q=knowledge_graph_kwd:community_report"

# 查 graph chunk 内容
curl -u "$RAGFLOW_ES_USER:$RAGFLOW_ES_PASSWORD" -X GET "localhost:9200/ragflow_56f78bf26ac611f187cd7db89d62ca74/_search?q=knowledge_graph_kwd:graph" -H "Content-Type: application/json"
```

### 5.5 查 Redis 队列

```bash
# 队列长度
docker exec docker-redis-1 redis-cli -a "$RAGFLOW_REDIS_PASSWORD" LLEN ragflow_svr_task_queue
docker exec docker-redis-1 redis-cli -a "$RAGFLOW_REDIS_PASSWORD" LLEN ragflow_svr_task_queue_graphrag

# 看 checkpoint
docker exec docker-redis-1 redis-cli -a "$RAGFLOW_REDIS_PASSWORD" KEYS "*graphrag*"
```

---

## 六、2026-08-04 业务链路修复记录

### 6.1 社区 Prompt 示例污染

**现象**：PTR 社区报告出现 `Unity March`、`Verdant Oasis Plaza` 等无关领域文本。

**根因**：`community_report_prompt.py` 内置完整示例，模型逐字复制示例，不是已证实的 Elasticsearch 跨知识库串库。

**修复**：删除具体领域示例，要求严格 JSON、只使用 Real Data 中实体并保留证据约束。重建后 41 条报告的三个已知污染词命中均为 0。

### 6.2 社区报告标题 ID 覆盖

**现象**：旧日志显示生成/索引 24 条，ES 仅有 8 条。

**根因**：旧 `_id` 仅由 LLM 标题和 `kb_id` 生成；重复标题产生相同 ID，写入时互相覆盖。

**修复**：用 `community_level + community_id + sorted entities` 生成稳定身份，并在写入前断言 `generated == unique_ids`。重建后 41 条报告对应 41 个唯一 ID。

### 6.3 GraphRAG worker 硬编码覆盖模型

**现象**：知识库和文档虽已切换模型，运行时仍调用失效模型实例。

**根因**：容器 `/ragflow/rag/svr/task_executor.py` 中存在硬编码 `api_key` 和 `llm_name` 覆盖。

**修复**：删除覆盖逻辑，按知识库配置加载模型。修复前后源码、哈希和 diff 已保存；正式环境必须合入源码分支并构建固定镜像。

### 6.4 Chat KG 检索错误使用租户默认模型

**现象**：Chat 普通生成模型可用，但 KG 检索仍因租户默认模型失效而返回模型错误。

**根因**：`dialog_service.py` 调用 KG retriever 时重新使用租户默认模型。

**修复**：让 KG retrieval 复用当前 Chat 已初始化的 `chat_mdl`。同时将 `demo_graph_v4.prompt_config.use_kg` 设置为 `true` 并回读确认。

### 6.5 Docker daemon 重启和 pending 任务恢复

**现象**：RAGFlow 容器退出码 137，MySQL/Elasticsearch 重启时报 `task already exists`，GraphRAG 任务停在 Redis pending。

**根因**：systemd 日志显示 Docker daemon 被整体停止并重启；`OOMKilled=false`，不是 GraphRAG OOM。daemon 重启后 MySQL/ES 留下孤儿 `containerd-shim`。

**恢复步骤**：

1. 确认宿主内存、容器 inspect 和 systemd Docker 日志，排除 OOM。
2. 确认 Docker/`ctr` 不登记对应任务且孤儿 shim 下无数据库子进程。
3. 只终止已确认的孤儿 shim，恢复原 MySQL、ES、Redis、MinIO 和 RAGFlow 容器及原数据。
4. 等待 RAGFlow 日志出现 `RAGFlow server is ready`；初始化期间短时 502 不作为永久失败。
5. 回读运行时补丁、模型和 `use_kg=true`。
6. 精确读取 `te.0.common` 的 pending 消息，启动同名 GraphRAG consumer，通过 unacked iterator 接管原任务；不要再次调用 `POST /index`。

本次接管原任务：`task_id=b282becc8fda11f1b55ebf95e1cda599`，最终成功完成，未产生重复任务。

### 6.6 修复后验收基线

```text
GraphRAG task: progress=1.0, ok=1, failed=0, total_time=1255.08s
Graph API:      nodes=256, edges=128
Elasticsearch:  entity=614, relation=292, community_report=41, graph=1, subgraph=1
Community:      41 reports / 41 unique IDs / source correct / pollution terms=0
KG retrieval:   use_kg=false -> 0 community blocks
                use_kg=true  -> 1 community block at first position
Chat fixed set: 7/7 API and answer success, P50=13.381s, P90=26.971s
Three-system benchmark (2026-08-05): 72/72 success (12Q x 2 rounds x normal/general/light)
  normal:   E2E P50=15.61s, P99=40.12s, retrieval P50=1.58s, rule_coverage=99.2%
  general:  E2E P50=23.16s, P99=50.21s, retrieval P50=1.97s, rule_coverage=99.0%
  light:     E2E P50=22.56s, P99=76.23s, retrieval P50=2.38s, rule_coverage=88.3%
Quality caveat: P1 long answer is truncated after the electric-motor-overload section
```

证据文件：

- `code/patches/ragflow-v0.26.1-2026-08-04/`：131 当前运行源码、修复前脱敏版本、宿主同步范围、统一 diff、镜像元数据和 SHA-256
- `code/patches/ragflow-v0.26.1-2026-08-04/README.md`：归档范围、完整性、安全处理和回滚边界
- `test/results/2026-08-04/validation_snapshot.json`
- `test/results/2026-08-04/kg_retrieval_comparison.json`
- `test/results/2026-08-04/demo_graph_after_repair.jsonl`
- `test/results/2026-08-04/qa_comparison_summary.md`

## 七、GraphRAG 配置参考

当前 PTR_GraphRAG 的 parser_config.graphrag：

```json
{
  "use_graphrag": true,
  "method": "general",
  "entity_types": ["设备","部件","参数","故障现象","故障原因","处理措施","备件","操作步骤","标准"],
  "community": true,
  "resolution": true,
  "batch_chunk_token_size": 4096
}
```

- `method`：`general`（默认，Microsoft GraphRAG 风格）/ `light`（LightRAG 风格）/ `ner`（仅命名实体识别）
- `entity_types`：软约束（prompt 层面），9 种覆盖核电设备域
- `community`：是否做社区发现（Leiden 算法）
- `resolution`：是否做实体消歧（合并同义实体）

### 7.1 Light 模式假成功与强制验收（2026-08-05）

Light A/B 首次任务约 5.05 秒即显示 `progress=1.0`，但 `/graph` 为 0 nodes / 0 edges。worker 日志实际记录 `API_KEY_DISABLED`，说明文档实体抽取全部失败后任务仍可能被 RAGFlow 汇总成完成状态。

处理步骤：

1. 查 `progress_msg` 和 worker 日志，确认是否有 `error processing chunk`、`maximum error count`、`API_KEY_DISABLED` 等失败标记。
2. 调用 `GET /graph` 核对实际节点数，禁止只看 `progress=1.0`。
3. 仅将隔离的 Light PoC 数据集和文档绑定到已验证可用模型，不修改租户全局默认配置。
4. 使用官方 `DELETE /api/v1/datasets/{kb_id}/graph` 清除 0 节点资产和任务标记，再触发一次重建；不要在旧失败任务上叠加触发。
5. 最终通过条件必须同时满足：`progress=1.0`、失败标记为空、`nodes>0`。社区模式还应继续核对边和社区报告。

本次重跑结果：831.47 秒，36 nodes / 27 edges / 3 communities；General 基线为 1255.11 秒，256 nodes / 128 edges / 41 communities。Light 建图快约 33.76%，但图明显更稀疏，不能只凭建图速度判定质量更优。

注意：RAGFlow 的 `method=light` 只是使用 LightRAG 风格的抽取 Prompt；图存储、KG retrieval 和 Chat 仍是 RAGFlow 自有实现，不等同于独立 LightRAG 全链路。

### 7.2 长问答的墙钟超时与断点续跑

`requests` 的 `timeout=240` 是连接/读超时，不是整个请求的 240 秒硬墙钟上限。如果服务端持续发送保活或分段数据，读超时会不断重置，非流式 Chat 仍可能挂住几十分钟。

性能基准必须同时具备：

1. 每完成一行 JSONL 就 `flush + fsync`，中断不丢已完成结果。
2. 用 `(round, question_id, system)` 作为唯一键，`--resume` 只跳过已完成键，不重复调用。
3. 每次测量放到独立子进程，用 `--hard-timeout` 施加墙钟上限；超时后终止子进程并继续下一题。
4. retrieval 完成后先发送阶段结果；若 Chat 超时，仍保留真实检索耗时，只把 e2e 标为 `hard_timeout`。
5. 超时和模型错误必须进入失败率，不能删除该题后只统计成功样本。
6. Windows `spawn` 模式下不要用 `multiprocessing.Queue` 回传大段答案：队列 feeder 线程在终止或退出时可能死锁，使父进程的硬超时收尾也卡住。本项目改为临时目录中的 `retrieval.json` / `complete.json` 原子文件回传，父进程只轮询文件与子进程状态；超时后 `terminate`，必要时 `kill`，最后 `join` 回收句柄。

本次二次故障表现为第二轮 Q4 General 在设置 `--hard-timeout 180` 后仍停留约 59 分钟，JSONL 保持 47 条。停止旧进程后保留断点，文件回传实现通过正常完成和 1 秒硬超时两类单元测试，再从第 48 条续跑。
