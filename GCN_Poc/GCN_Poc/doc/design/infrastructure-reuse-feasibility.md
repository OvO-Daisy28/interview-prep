# RAGFlow 基础设施复用可行性查证结论

> 查证日期：2026-08-19
> 方式：SSH 进 131 实地查（源码 + MySQL + ES + 配置），全程只读
> 背景：用户提出"批量上传服务与 RAGFlow 代码解耦，只复用它的存储/模型套件"，本文回答这条路是否可行、耦合到哪一层
> 依据：[决策 15](../../memory/decisions.md)——交付好用的系统是目标，RAGFlow 是手段

## 一、结论先行

**这条路可行，而且比"调 RAGFlow API"和"改 RAGFlow 源码"都好。**

> ✅ **已由真实环境最小验证证实（2026-08-19）**，不再是分析推断。见 §七。

推荐**方案 B：复用存储 + 模型，自建元数据**。理由：五层契约全部查清，无一是黑盒；关键依赖（embedding、分词）都是可独立调用的外部服务/pip 包；GraphRAG 从 ES 读数据，只要 chunk 按契约写入就能正常建图。

## 二、五层契约查证结果

### Q1. MinIO 存储契约 ✅ 完全可自己写

| 项 | 实测结果 |
|---|---|
| bucket 命名 | **`bucket = kb_id`**（每个知识库一个 bucket），`file_service.py:524` `STORAGE_IMPL.put(kb.id, location, blob)` |
| 对象 key | **文件名**，重名后缀加 `_`（`file_service.py:517-519`） |
| 配置 | `service_conf.yaml`: `bucket: ''` `prefix_path: ''` → 走"每 KB 一 bucket"模式 |
| 单 bucket 模式 | 支持（配 `bucket` 后走 `<physical-bucket>/<kb_id>/<file>` 路径前缀） |
| 关联方式 | MySQL `document.location` 字段存对象 key，`document.kb_id` 定位 bucket |

**结论**：契约极简单，我们的服务可以直接用 minio SDK 写入，RAGFlow 能读到。

### Q2. ES 索引契约 ✅ 完全可自己写

| 项 | 实测结果 |
|---|---|
| 索引名 | **`ragflow_<tenant_id>`**（`rag/nlp/search.py:34`） |
| 字段类型 | 靠 `conf/mapping.json` 的 **dynamic_templates 按后缀推断**：`*_ltks`→text、`*_kwd`/`*_id`→keyword、`*_flt`→float、`*_1024_vec`→dense_vector、`*_at`/`*_time`→date |
| 一条 chunk | **仅 14 个字段**（真实样本，PTR 普通 RAG 库 648 条） |

真实 chunk 字段清单：
```
id                      chunk 唯一 ID（16 位 hex）
kb_id / doc_id          归属
docnm_kwd               文档名
content_with_weight     原文（表格保留 HTML 结构）
content_ltks            分词（大粒度）
content_sm_ltks         分词（小粒度）
title_tks / title_sm_tks 标题分词
q_1024_vec              向量（1024 维）
create_time             "2026-08-04 11:16:38"
create_timestamp_flt    1785813398.839397
doc_type_kwd            table / ...
img_id                  图片引用（可空）
```

**结论**：schema 简单且无隐藏必填项。唯一外部依赖是分词（Q5）和向量（Q4），两者都可独立获得。

### Q3. MySQL 元数据契约 ⚠️ 可写但不建议深度耦合

| 表 | 用途 | 我们的选择 |
|---|---|---|
| `document` | 文档元数据 + `run`/`progress`/`progress_msg` 状态 | 可写，但状态字段会被 RAGFlow worker 争抢 |
| `task` | 解析任务（含 `priority`/`retry_count`） | 不写——那是 RAGFlow worker 的调度单元 |
| `knowledgebase` | KB 配置（`embd_id`/`parser_id`/`parser_config`） | 只读——建 KB 仍走 RAGFlow |
| `file` / `file2document` | 文件树 + 文档关联 | 按需写（影响 Web 界面文件管理显示） |

**关键判断**：如果我们自己做解析和状态管理，就**不该**往 `document.run`/`progress` 里写——那是 RAGFlow worker 的状态机字段，双写会冲突。我们的状态存自己的 PG。

但要让 RAGFlow Web 界面能看到文档（以及 GraphRAG 能按 doc 组织），`document` 表的**静态元数据**（id/kb_id/name/location/size/type/chunk_num）还是要写。

### Q4. Embedding 模型 ✅ 独立 HTTP 服务，可直接调用

| 项 | 实测结果 |
|---|---|
| 模型 | `bge-base@local-bge-v2@OpenAI-API-Compatible` |
| 部署形态 | **独立 OpenAI 兼容服务**，非嵌入 RAGFlow 进程 |
| endpoint | `http://192.168.80.1:18001/v1`（`tenant_model_instance.extra`） |
| 向量维度 | **1024**（对应 ES 字段 `q_1024_vec`） |
| 配置位置 | v0.26 用 `tenant_model_instance` 表（`tenant_llm` 已空废弃） |

**结论**：这是最关键的好消息——embedding 服务本来就是外部的，我们的服务直接 HTTP 调用即可，向量与 RAGFlow 完全一致。

### Q5. 解析与分词 ✅ 均可独立使用

| 能力 | 实现 | 可复用性 |
|---|---|---|
| 分词 | `infinity.rag_tokenizer`（**pip 包**，`.venv/lib/python3.13/site-packages/infinity/rag_tokenizer.py`） | ✅ pip 安装即用，实测 `tokenize("PTR冷却泵额定流量640立方米每小时")` → `ptr 冷却 泵 额定 流量 640 立方米 每 小时` |
| docx 解析 | `python-docx` 遍历 XML（`rag/app/naive.py`），不跑模型 | ✅ 标准库，自己实现无障碍 |
| PDF 解析 | DeepDoc（版面模型）/ MinerU / PlainText，`PARSERS` 可选 | ⚠️ DeepDoc 在 RAGFlow 代码内；MinerU 有独立服务（131 上有 `mineru-web` 容器） |
| OCR | DeepDoc 内置 / MinerU | ⚠️ 同上 |

**结论**：分词零障碍。docx/txt/xlsx 自己解析没问题。PDF/扫描件若要完全对齐 RAGFlow 效果，需调 MinerU 服务或引入 DeepDoc。

### Q6. 下游依赖（GraphRAG / 检索）✅ 只依赖 ES

**GraphRAG 建图数据来源**（`rag/graphrag/general/index.py:319,376`）：
```python
fields_for_chunks = ["content_with_weight", "doc_id"]
raw_chunks = list(settings.retriever.chunk_list(...))   # 从 ES 读
```

**结论（决定性）**：GraphRAG **从 ES 读 chunk 建图**，只要 chunk 按 §Q2 契约写进 `ragflow_<tenant_id>` 索引，GraphRAG 照常能建图，与 chunk 是谁写的无关。

检索链路（`rag/nlp/search.py`）同理，全部基于 ES 索引 + `kb_id` 过滤。

## 三、三种耦合方案对比

### 方案 A：深度复用（连 MySQL 状态一起写）

我们写 MinIO + ES + MySQL 全部表，包括 `document.run/progress`。

- ✅ RAGFlow Web 界面完全一致，用户看不出区别
- ❌ 与 RAGFlow worker 争抢状态字段，双写冲突
- ❌ 强绑定其 schema，升级易碎
- **不推荐**

### 方案 B：复用存储 + 模型，自建元数据 ★推荐

| 组件 | 归属 |
|---|---|
| 原文件 → **MinIO**（bucket=kb_id） | 复用 |
| chunk + 向量 → **ES**（`ragflow_<tenant>`，14 字段契约） | 复用 |
| embedding → **`http://192.168.80.1:18001/v1`** | 复用 |
| 分词 → **`infinity.rag_tokenizer`** pip 包 | 复用 |
| MySQL `document` 静态元数据（id/kb_id/name/location/size/chunk_num） | 写入（让 RAGFlow 认得这份文档） |
| MySQL `document.run/progress` 状态字段 | **不写**（避免与 worker 冲突） |
| 任务状态/阶段/耗时/重试/暂停 → **我们自己的 PG** | 自建 |
| 解析、切块、并发、调度、重试、暂停逻辑 | **自建** |

- ✅ 进度/暂停/重试/并发**完全自主**，不再猜单浮点、不再受制于无暂停
- ✅ 性能可自主优化（并发模型、批大小、GPU）
- ✅ RAGFlow 升级不影响我们（只依赖存储契约，不依赖其代码）
- ✅ 下游 GraphRAG / 检索照常可用
- ✅ 交付的是 PM 设计的系统，后端是我们的服务
- ⚠️ 要自己实现解析（PDF/扫描件需调 MinerU 服务或引入 DeepDoc）
- ⚠️ ES chunk 契约若随 RAGFlow 升级变化，需跟进（但字段少、变更慢）

### 方案 C：只复用模型（存储也自建）

只调 embedding 服务，chunk 存自己的库。

- ✅ 最自由
- ❌ **下游 GraphRAG / RAGFlow 检索全部用不了**（数据不在它认识的地方）
- ❌ 违背"方便在别的地方串起来"的初衷
- **不推荐**（除非确定完全不用 RAGFlow 的检索与图谱）

## 四、推荐方案 B 下，我们要自己实现什么

| 模块 | 说明 | 现有代码可复用性 |
|---|---|---|
| 文件上传 → MinIO | minio SDK，bucket=kb_id | 新写（简单） |
| 文档解析 | docx/xlsx/txt 自己解析；PDF/扫描件调 MinerU 服务 | 新写 |
| 切块（chunking） | 按 token 数切，对齐 `chunk_token_num` 配置 | 新写 |
| 分词 | `infinity.rag_tokenizer` | 直接用 |
| 向量化 | HTTP 调 `http://192.168.80.1:18001/v1` | 新写（简单） |
| 写 ES | 按 14 字段契约 bulk 写入 | 新写 |
| 写 MySQL document 静态元数据 | 让 RAGFlow 认得 | 新写 |
| **任务编排 / 状态机 / 并发 / 重试 / 暂停** | **已有代码 100% 可复用** | ✅ `state.py` / `repository.py` / `scheduler.py` / `api.py` 完全不用改 |
| 阶段映射 | **不再需要猜**——阶段由我们自己的流程定义 | `step_mapping.py` 大幅简化 |
| pipeline 适配层 | 从"调 RAGFlow API"换成"自己执行" | `pipeline_adapter.py` 换实现，接口不变 |

**关键**：设计 §8 的三层抽象（统一接口 / 状态映射 / pipeline 适配）此刻显出价值——**换后端只需替换适配层，上层状态机、调度、REST 接口一行不动**。已有 118 个测试大部分仍然有效。

## 五、待确认项（不阻塞决策，但影响实现）

1. **PDF/扫描件解析**：131 上的 `mineru-web` 容器能否被我们直接调用？接口是什么？（若不能，PDF 支持需引入 DeepDoc 代码或另找方案）
2. **chunk_id 生成规则**：RAGFlow 用什么算法生成 16 位 hex chunk id？需对齐以免冲突（`xxhash(content + kb_id)`？待查 `rag/nlp/__init__.py`）
3. **`document` 表写入后 RAGFlow 是否会自动接管**：写了 document 记录但 `run=UNSTART`，RAGFlow worker 会不会主动去解析它？（需确认调度触发条件）
4. **多租户/权限**：tenant_id 目前单租户，未来多租户时 ES 索引按租户隔离，需确认我们的写入路径同样隔离

## 六、下一步建议

1. 用户确认方案 B
2. 补查 §五 的 4 个待确认项（尤其 chunk_id 规则和 MinerU 可用性）
3. 写一个**最小验证**：自己上传一份 docx → 自己解析切块 → 调 embedding → 写 ES + MinIO + document 元数据 → 验证 RAGFlow Web 能看到、检索能命中、GraphRAG 能建图
4. 验证通过后，把 `pipeline_adapter.py` 换成自建实现，M2 继续

---

## 七、最小验证结果（2026-08-19，131 实跑）✅ 全部通过

用 `code/ingest/selfrun_probe.py` + `selfrun_writer.py` 在 131 容器内实跑，**完全绕过 RAGFlow 的解析流程**：

| 环节 | 我们的实现 | 结果 |
|---|---|---|
| 解析 | python-docx 遍历 XML / 文本切分 | ✅ PTR docx → 889 sections，0.77s（无模型） |
| 切块 | 自己按 token 预算合并 | ✅ 251 chunks，0.01s |
| 分词 | 复用 `rag.nlp.rag_tokenizer` | ✅ 真实中文分词（`gcn 自 研 摄入 服务 验证 文档`） |
| 向量化 | 直接 HTTP 调 `192.168.80.1:18001/v1` | ✅ 1024 维，0.79s/chunk |
| 写 MinIO | bucket=kb_id，key=filename | ✅ |
| 写 MySQL | document + **file + file2document** | ✅ |
| 写 ES | 14 字段契约 + xxh64 chunk id | ✅ |
| **RAGFlow 文档列表** | 未调用其任何解析 API | ✅ **显示我们的文档，run=DONE，chunks=1** |
| **RAGFlow 检索** | 其原生检索链路 | ✅ **命中，sim=0.476 排第一** |

检索实测输出（131 内网调用，绕开本地终端编码问题）：
```
code: 0 | total: 10 | chunks: 3
  sim=0.476 doc=probe_doc.txt
      GCN自研摄入服务验证文档
      本文档由 GCN 批量上传服务自行解析、切块、向量化并写入，未经过 RAGFlow 的解析流程。
```

### 验证中发现的关键契约细节（§二 未覆盖，踩坑后补）

1. **`document` 表单独写不够**：`DocumentService.get_by_kb_id` 用 **INNER JOIN `file2document` + `file`**（`document_service.py:140-142`）。只写 document 行，文档对 List API 和 Web UI **完全不可见**（实测 MySQL 有 8 行、API 只返回 6 行）。必须同时写 `file` + `file2document`。
2. **chunk_id 规则**（`task_executor.py:406`）：
   `xxhash.xxh64((content_with_weight + str(doc_id)).encode("utf-8","surrogatepass")).hexdigest()`
   ——必须一致，否则去重/覆盖语义会错乱。
3. **RAGFlow worker 不会抢我们的文档**：`task_executor.collect()` 只从 **Redis 消费**，从不扫 MySQL。写 document 行不会被自动接管，`run`/`progress` 由我们自己定，无双写冲突。
4. **v0.26 模块位置变更**（易踩）：`STORAGE_IMPL`/`docStoreConn` 在 `common.settings`（非 `api.settings`）且需 `init_settings()`；`TaskStatus` 在 `common.constants`；`get_uuid` 在 `common.misc_utils`；`ESConnection` 无 `indexExist`（是基类的 `index_exist`）。
5. **embedding 服务在 131 内网**（`192.168.80.1`），本地开发机访问不到 → 我们的服务将来要部署在 131 或同内网；本地只能开发+单测，端到端验证需在服务器跑。

### GraphRAG 验证（2026-08-20 完成，M5）✅

**已实跑证实**：对完全由我们写入的 chunk 触发建图，四层验收全过——36 nodes / 33 edges / 8 条社区报告 / `use_kg=true` 时社区块排第一。源码推断（`index.py:319,376` 只取 `content_with_weight` + `doc_id`）得到实证：**GraphRAG 只认 ES 里的 chunk，不关心是谁写的**。详见 [progress-board.md](progress-board.md) M5 段。
- **MinerU 服务调用方式**：`mineru-web` 容器在 `10.126.2.131:8010`，接口未验证。PDF/扫描件解析需要它。

## 八、下一步

1. ~~用户确认方案 B~~ ✅ 已确认
2. ~~最小验证~~ ✅ 已通过
3. 把 `pipeline_adapter.py` 换成自建实现（`SelfRunPipeline`），保留接口不变——上层状态机/调度器/REST 接口/118 个测试全部复用
4. 继续 M2 批量（并发 + 失败隔离），此时并发不再受 RAGFlow 单 worker 限制，由我们自己控制
5. M5 时验证 GraphRAG 对自写 chunk 建图
6. PDF 支持时验证 MinerU 调用
