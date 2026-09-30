# RAGFlow 源码全链路调研（部署版 v0.26.1 / 上游参考 v0.26.4）

> 目标：逐环节把全链路读到函数级，支撑面试深挖。一次填一个环节，不零碎。
> 源码：`f:\byh\ragflow-main`（GitHub v0.26.4，上游参考版）。**部署版是 v0.26.1 + 5 处本地补丁**，引用行号以本地 v0.26.4 为准，部署版 v0.26.1 行号有 10-30 行漂移（关键补丁行号已标注部署版实际值）。面试讲行号时统一口径："部署版 v0.26.1 的行号"。
> 方法：每环节 = 入口路由 → 调用链（文件:行号）→ 核心机制 → 数据结构 → 挂接我项目的实测数字 → 面试深挖预测。

## 环节地图（九环节）

| # | 环节 | 状态 | 面试热度 | 我的实测数字 |
|---|---|---|---|---|
| ① | 上传与元数据 | ✅ | ★★★ | 100 份上传 3.2s |
| ② | 解析触发与任务队列 | ✅ | ★★★★★ | 假死修复、取消实测、进度黑盒 |
| ③ | 文档解析（parser） | ✅ | ★★★★ | 三类文档、OCR |
| ④ | 分块（chunker） | ✅ | ★★★★★ | chunk_token_num=512、116 chunks |
| ⑤ | 向量化（embedding） | ✅ | ★★★★★ | 93.6% 占比、GPU ×5.7 |
| ⑥ | 索引写入（ES） | ✅ | ★★★ | index 占比 42.7%（新瓶颈） |
| ⑦ | GraphRAG 构建 | ✅ | ★★★★ | 979/719、空图根因 |
| ⑧ | 在线检索（retriever） | ✅ | ★★★★★ | KG +40%、相似度 0.331→0.464 |
| ⑨ | 问答生成（chat） | ✅ | ★★★★ | TTFT 0.9s、生成占 70~96% |

---

## 环节① 上传与元数据

**一句话**：上传只做三件事——文件落对象存储、建 MySQL 文档记录、生成缩略图；不触发任何解析（上传 ≠ 解析）。

**调用链**：
```
POST /api/v1/datasets/{kb}/documents  (multipart)
  → document_api.py:449 upload_document()      # type=local/web/empty 三种
  → FileService.upload_document()  file_service.py:542
      → STORAGE_IMPL.put(kb.id, location, blob)   # MinIO/S3，bucket=kb_id
      → DocumentService.insert(doc)               # MySQL
      → 缩略图 thumbnail_{doc_id}.png
```

**核心机制（深挖点）**：

1. **幂等与增量更新**（file_service.py:561-588）：同 doc_id 重复上传时，算 `content_hash`（xxhash128，:580/:630）与旧值对比——**hash 没变只覆盖文件不入解析流程；hash 变了才重新入队**。这就是「文档更新怎么办」的源码答案（T3 测试的机制基础）。跨 KB 的 doc_id 冲突直接跳过（:564-573）。
2. **同名去重**：`duplicate_name()` 自动加序号后缀；对象存储 location 冲突追加 `_`（:601-602）。
3. **文件健康检查**：`check_doc_health`（文件名层面）+ `filename_type` 判类型，不支持的类型直接拒绝。
4. **PDF 容错**：`read_potential_broken_pdf`（:606）预修复损坏 PDF。
5. **存储隔离维度不同**：对象存储按 **KB** 隔离（bucket=kb_id）；ES 索引按**租户**隔离（`ragflow_<tenant>`，KB 用字段过滤）——我实测建库时验证过（建 KB 只插表不 init ES）。

**document 记录字段**（MySQL，file_service.py:616-631）：
```json
{
  "id": "doc_id", "kb_id": "...", "parser_id": "按类型推断", 
  "parser_config": "KB 配置或 override 合并", "type/suffix/name/location/size",
  "thumbnail": "thumbnail_{id}.png", "content_hash": "xxhash128"
}
```

**挂接实测**：100 份批量上传仅 3.2s（上传本身快，慢在解析）——正因为上传只是落盘+插表。

**面试深挖预测**：
- 「上传后文档处于什么状态？」→ UNSTART，还没进队列
- 「同一份文档传两遍会怎样？」→ content_hash 没变不重解析（增量机制）
- 「文件存哪？按什么隔离？」→ MinIO bucket=kb_id；ES 是租户级索引——两级隔离维度不同，答出这个细节是加分项

---

## 环节② 解析触发与任务队列

**一句话**：解析接口把文档置 RUNNING、清旧数据，然后按规则把文档拆成 N 个 task 写进 Redis Stream；Task Executor 消费后**整个任务完成才 ACK**。

**调用链**：
```
POST /datasets/{kb}/documents/parse  (body: document_ids)
  → document_api.py:1549 parse_documents()
  → _run_sync (:1622) 逐文档：
      ① doc 已 DONE → clear_chunk_num_when_rerun + progress/chunk_num/token_num 清零 (:1633-1637)
      ② TaskService.filter_delete 删旧 task (:1640)
      ③ ES 删除该 doc 的旧 chunks (:1644-1645)
      ④ DocumentService.run()  (document_service.py:1226)
  → queue_tasks()  (task_service.py:439)
      → REDIS_CONN.queue_product(get_svr_queue_name(priority, suffix))  (:546)
         # 队列名 te.{0|1}.{common|graphrag|raptor|mindmap}
```

**核心机制（深挖点）**：

1. **任务拆分规则**（task_service.py:472-497）：
   - **PDF 按页拆**：`task_page_size` 默认 12 页一个 task（paper 22 页）；`one`/`knowledge_graph`/目录提取模式不拆（整文档单 task，:480-481）——这就是日志里 `Page(1~100000001)` 的来历（100000001 = MAXIMUM_TASK_PAGE_NUMBER 占位符）
   - Excel 按行拆（3000 行/task）
   - 普通文档单 task
   - **任务复用优化**：`reuse_prev_task_chunks`（:552）按 digest 对比复用历史 task 的 chunks（避免重复解析）
2. **队列命名**（部署版 v0.26.1 + 本地补丁）：`te.{priority}.{suffix}`，suffix 按任务类型分 common/graphrag/raptor/mindmap。**版本差异说明**：131 服务器部署版 v0.26.1 通过本地补丁（settings.py:136 `SPECIAL_TASK_QUEUE_SUFFIXES` + :139 `get_svr_queue_name` 按 suffix 分流）解决了重任务互抢问题（假死根因①）。补丁打在部署版 v0.26.1 上，未贡献上游，vanilla v0.26.4 是否已修复未考证。面试口径："补丁打在部署的 v0.26.1 上，未贡献上游"。
3. **消费侧**（task_executor.py）：
   - `collect()`（:220）：**优先恢复自己上次未 ACK 的消息**（`get_unacked_iterator`，:228-231）→ 再按队列顺序取新消息 → 空消息直接 ack → **collect 阶段就查 `has_canceled`**（:264，取消检查点之一，但只对"任务还没开始跑"有效）
   - `handle_task()`（:1737）主循环：无任务 sleep(5)；执行有三种模式（`TE_RUN_MODE`：0=重构版 `TaskManager.run_refactored_task`、1=dry-run 新旧对比、else 原版 `do_handle_task`）——代码里有三种执行模式的开关，我们用的是默认的原版。面试时不主动提"重构版执行器"，除非被追问 `TE_RUN_MODE`。
   - 异常路径：`set_progress(prog=-1)` 标记失败（:1784）
   - **`redis_msg.ack()` 在 finally 末尾（:1802）——ACK 只在整个任务（含所有异常处理）完成后执行。这就是假死根因③的源码位置：worker 中途僵死 → 消息永远未 ACK → 别人无法接管（v0.26.4 依然如此，接管要靠心跳过期 claim，即 redis_conn 的 pending 接管逻辑）**

**挂接实测**：
- 进度黑盒实证：536 次轮询只有 4 种 progress_msg 文本——进度就一个浮点+一条 msg（`set_progress`，task_executor.py:186），无分阶段时间戳（这是二开编排层的直接动因，ragflow-dev-research.md 2.1 的表格）
- 取消实测 0 份生效：软取消两个检查点（collect 入口 + 阶段边界轮询），串行 embedding 时检查点间文档已处理完
- 假死修复的三个点全部能在源码定位：队列 suffix（settings）、ACK 时机（:1802）、pending 接管（redis_conn）

**面试深挖预测**：
- 「PDF 为什么要拆成多个 task？」→ 并行解析（多 worker 各领一段页区间）+ 失败重试粒度小
- 「task 表和 Redis 消息什么关系？」→ task 先落 MySQL（可查状态），消息只带 id/type 轻量信息，执行时从 DB 取回完整 task（collect :261）
- 「为什么消息会积压/无法接管？」→ ack 在 finally 末尾；worker 僵死则消息停在 pending，需心跳过期后 claim
- 「重新解析做了哪些清理？」→ 三清：task 记录、ES 旧 chunks、进度/计数

---

## 环节③ 文档解析（parser）

**一句话**：Task Executor 按 `parser_id` 从 FACTORY 表选模板（naive/paper/laws/manual/…，task_executor.py:111），模板的 `chunk()` 按文件后缀分发解析；**PDF 的解析引擎是运行时可插拔的**——`layout_recognize` 配置决定走 DeepDOC / MinerU / Docling / PaddleOCR / PlainText 等。

**调用链**：
```
do_handle_task (task_executor.py:1405)
  → build_chunks (:300)  →  FACTORY[parser_id] (:308)
      FACTORY = { naive, paper, book, manual, laws, qa, table, resume,
                  picture, one, audio, email, tag, knowledge_graph→naive }  (:111-128)
  → rag/app/naive.py chunk() (:952)  # 按后缀分发：
      .docx → Docx()(filename, binary)            # deepdoc DocxParser，:1025
      .pdf  → PARSERS.get(layout_recognizer)      # :1069 引擎选择！
              → by_deepdoc / by_mineru / by_docling / by_paddleocr /
                by_opendataloader / by_somark / by_mistral_ocr / by_plaintext
```

**核心机制（深挖点）**：

1. **解析引擎可插拔**（naive.py:1050-1086）：PDF 解析后端由 `parser_config["layout_recognize"]` 决定（默认 DeepDOC）。**MinerU 是 RAGFlow 的内置解析后端之一**——回答「MinerU 和 RAGFlow 什么关系」的源码证据：既可作为 RAGFlow 的解析引擎（配置切换），也可独立部署为解析服务（我们 4090 的形态，7 组性能实验测的就是它）。
2. **KG 模板 = naive**（FACTORY :126）：`knowledge_graph` 的 chunk_method 底层就是 naive 切块——**GraphRAG 是在 naive chunks 之上运行的**（源码级证实「GraphRAG 建立在普通 RAG chunk 之上」）。
3. **解析输出统一为三元结构**：sections = (text, image, tables)——后续分块、表格 tokenize、图片 vision 处理共用一套结构。
4. **两个隐藏能力**（naive.py:986-1019）：嵌入文件递归解析（`extract_embed_file`，如 docx 里的附件 docx）；`analyze_hyperlink` 开启时抓取文档内 URL 并递归解析网页。
5. MinerU/Docling/OCR 系后端允许 `chunk_token_num=0`（:1095-1097）——引擎已输出结构化单元时不再二次合并。

**挂接实测**：PTR 手册 docx → DeepDOC → 42.7s → 116 raw chunks（4090 实测）；MinerU 独立服务 7 阶段流水线（Layout/MFR/Table/OCR-det/OCR-rec/Seal/Processing）与 RAGFlow 内置形态是同一引擎的两种用法。

**面试深挖预测**：
- 「MinerU 和 RAGFlow 什么关系？」→ 可插拔后端 vs 独立服务，两种形态我都实测过
- 「扫描件怎么进链路？」→ layout_recognize 选 OCR 系引擎，或外置 MinerU 服务
- 「GraphRAG 和普通 RAG 的 chunk 是两套吗？」→ 不是，同一套 naive chunks（FACTORY:126）

---

## 环节④ 分块（chunker）

**一句话**：`naive_merge` 的算法是「按 delimiter 把 section 切成段落 → 按 chunk_token_num 聚合成块 → **超限段落独立成块不强切** → 可配置块间重叠」。

**调用链**：
```
naive.py chunk() → naive_merge_docx(sections, chunk_token_num, delimiter, ...)  (:1030)
  → rag/nlp/__init__.py:1360 naive_merge()
      ① 自定义分隔符模式（反引号包裹）：每段自成 chunk，绕过 chunk_token_num (:1377-1395)
      ② 默认：delimiter 切段 (:1406-1415)
         → _merge_paragraph_groups 按 token 数聚合 (:1417，策略=OVER_CAP)
         → 超限段落独立成块，"model layer truncates oversize units" (:1399-1400 注释)
         → overlapped_percent 块间重叠 (:1420)
  → tokenize_chunks（生成 content_ltks 分词——BM25 检索的索引基础）
```

**核心机制（深挖点）**：

1. **chunk_token_num 不是硬上限**（:1397-1400 注释原文）：段落超限时独立成块、由模型层截断——**没有二次切分**。这是「chunk 怎么切」最容易被追问的细节。
2. **自定义分隔符是逃生门**（:1374-1379）：delimiter 里用反引号包裹自定义分隔符时，每段自成 chunk，完全绕过 token 数控制。
3. **块间重叠可配**：`overlapped_percent`（:1420 无条件应用）——检索召回跨块边界内容时的经典手段。
4. **token 数怎么算**：`num_tokens_from_string`（common/token_utils，走 embedding 模型的 tokenizer 口径）。
5. 默认配置（naive.py:964）：`chunk_token_num=512、delimiter="\n!?。；！？"`（中文标点切分）。

**挂接实测**：
- 我的 LightRAG 实验：chunk_token_num=512、batch_chunk_token_size=4096（116 chunks 合并成 17 个 GraphRAG 抽取单元——抽取批次是 4096 token 口径，和 512 的 chunk 口径是两层）
- MinerU 后端 chunk_token_num=0 的路径：引擎结构化输出直接成块

**面试深挖预测**：
- 「chunk_token_num 超了会强切吗？」→ 不会：OVER_CAP 独立成块+模型层截断
- 「块和块之间怎么避免边界丢上下文？」→ overlapped_percent 重叠
- 「表格为什么特殊处理？」→ 表格整表进一个 chunk（tokenize_table），table_context_size 可注入上下文说明
- 「你的 512 怎么选的？」→ 通用基线值；不同 chunk_method（laws/manual/qa）有各自模板逻辑（FACTORY 表的其他模块）

---

## 环节⑤ 向量化（embedding）

**一句话**：每个 chunk 的正文 truncate 到模型 max_length 后批量调 embedding 模型生成向量，写入 chunk 的 `q_{dim}_vec` 字段；**标题向量与正文向量按权重融合**为最终向量（文件名也是检索信号）。

**调用链**：
```
do_handle_task → build_chunks (task_executor.py:300)
  → embedding(docs, mdl, parser_config)  (task_executor.py:710)
      → title 单独编码（tts[0:1]，:727）→ tile 复制成全量
      → batch_encode 批量编码正文（:732，@timeout(60) 单批限 60s）
        → truncate(c, mdl.max_length - 10)  # 超长截断到模型上限
        → embed_limiter 并发限流（:738）
        → 按 EMBEDDING_BATCH_SIZE 分批（:737）
      → vects = title_w * tts + (1-title_w) * cnts  (:749，title_w 默认 0.1)
      → d["q_{dim}_vec"] = v  (:758，向量字段名带维度)
```

**核心机制（深挖点）**：

1. **标题参与向量**（:744-749）：文件名/标题单独编码后与正文向量按 `filename_embd_weight`（默认 0.1）加权融合——文件名也是检索信号。这是为什么"文件名起得规范有助于检索"的源码原因。
2. **单批 60 秒超时**（:731 `@timeout(60)`）：单批 embedding 超时即失败——131 CPU 共享机长尾的源头之一（排队+超时叠加）。GPU 独占后单批 1.46s，远低于 60s 阈值，所以长尾根治。
3. **并发限流**（:738 `embed_limiter`）：embedding 并发有上限——这是 `MAX_CONCURRENT_CHUNK_BUILDERS=1` 串行化的执行点，也是方案 A 慢的源码根源（并发 1 → batch）。
4. **超长截断**（:734 `truncate`）：超过 `max_length-10` 的正文硬截断——分块没切的超长段落在这里被模型层兜底（对应环节④"模型层截断"的承诺）。
5. **空内容占位**（:722）：纯空白 chunk 编码为 "None" 占位，避免 embedding 报错——脏数据兜底。
6. **向量字段名带维度**（:758 `q_{len(v)}_vec`）：字段名含维度，同一索引可存不同维度向量（切模型不重建索引的理论基础，但实际切换仍需重建）。

**挂接实测**：
- 131 CPU：embedding 占总耗时 93.6%、max 556s（超 60s 阈值的长尾来自排队，非单批慢）→ GPU：avg 15.3s→1.46s（×10.5）、max 8.9s
- `MAX_CONCURRENT_CHUNK_BUILDERS=1` 的串行点正是这里——方案 A 慢的根源

**面试深挖预测**：
- 「embedding 为什么慢/为什么是瓶颈？」→ 每个 chunk 一次模型调用+串行并发；CPU 共享机长尾
- 「为什么 GPU 后单条快 10.5 倍但吞吐只 5.7 倍？」→ 单条快但 index 写入没加速（环节⑥）
- 「换 embedding 模型要重建吗？」→ 向量空间变了必须全库重建

---

## 环节⑥ 索引写入（insert_chunks）

**一句话**：chunks 按 `DOC_BULK_SIZE` 批量写入文档引擎，**每个 chunk 是一条 ES 记录**，正文/分词/向量/元数据/页码位置/图谱类型字段共存；图谱数据（实体/关系/社区）也写同一索引，用 `knowledge_graph_kwd` 区分类型。

**调用链**：
```
do_handle_task → insert_chunks (task_executor.py:1289)
  → 计算 mom_id（去重用，xxhash64，:1306）
  → 批量插入 mothers（母子块去重结构，:1321，DOC_BULK_SIZE 一批）
  → 批量插入 chunks（:1334）
      → settings.docStoreConn.insert(chunks, index_name(tenant_id), kb_id)
  → 每批后检查 has_canceled（:1329/:1342）——取消检查点之一
  → 取消时回滚部分 RAPTOR 块（:1344-1360）
```

**索引名**：`search.index_name(tenant_id)`（search.py:35）——**租户级**，所有 KB 共用一个 ES index，按 kb_id 字段过滤。

**ES 字段全景**（search.py:146-171，检索默认返回字段）：
```
id                      # chunk ID
content_with_weight     # 正文原文（检索主体）
content_ltks            # 正文分词（BM25 全文检索用）
title_tks / title_sm_tks# 标题分词
q_{dim}_vec             # 向量（维度进字段名）
doc_id / kb_id / docnm_kwd  # 归属与文档名
page_num_int / position_int / top_int  # 页码与位置（引用溯源）
chunk_order_int         # 块序号
knowledge_graph_kwd     # 图谱类型标记（graph/subgraph/entity/relation/community_report）
entity_kwd / from_entity_kwd / to_entity_kwd  # 实体与关系端点
available_int           # 可用标记（0/1，可软删除）
important_kwd / question_kwd / question_tks    # 关键词与问答字段
PAGERANK_FLD / TAG_FLD  # PageRank 与标签
create_timestamp_flt    # 时间戳
mom_id                  # 母子块去重 ID
```

**核心机制（深挖点）**：

1. **图谱与普通 chunk 同索引**：`knowledge_graph_kwd` 字段区分类型——graph/subgraph/entity/relation/community_report。**主图不存 Neo4j**，序列化成特殊 chunk 写回 ES。这就是"图谱存哪"的源码答案。
2. **租户级索引共享**（search.py:35）：所有 KB 共用一个 `ragflow_<tenant>` 索引——建 KB 只插表不 init ES（实测验证过）。代价：跨 KB 查询要靠 kb_id 过滤，索引内数据量大时影响查询规划。
3. **取消检查点在批量间隙**（:1329/:1342）：每批 insert 后检查取消——所以取消生效粒度是"一批 DOC_BULK_SIZE 之后"，不是即时。这解释了取消实测为什么 0 份生效（串行 embedding 时检查点之间文档已处理完）。
4. **mom 母子块去重**（:1300-1319）：`mom_with_weight` 字段的块按 hash 去重存为 mother 块，子块引用——跨文档复用相同内容（如公共条款）时省存储。
5. **RAPTOR 部分回滚**（:1344-1360）：取消时删掉已写的 RAPTOR 摘要块，防止下次误判为已完成 checkpoint——RAPTOR 是另一套摘要索引机制。

**挂接实测**：
- GPU 后 index 写入成新瓶颈（37~52%）——三处写入：ES bulk + MinIO（图片/裁剪图）+ MySQL（document 状态更新）
- 万份 45h 失败率 0.06% 的稳定性：失败隔离在此层生效（单 chunk 失败不拖累整批）

**面试深挖预测**：
- 「图谱存哪？为什么不用 Neo4j？」→ 同索引 + 类型字段，统一检索链路，省一套运维
- 「为什么 index 成了新瓶颈？」→ ES bulk + MinIO + MySQL 三处写入，GPU 没加速这层
- 「取消为什么生效不了？」→ 检查点在批量间隙，串行场景文档已处理完
- 「建 KB 为什么不用 init ES？」→ 索引是租户级共享，按 kb_id 过滤

---

## 环节⑦ GraphRAG 构建

**一句话**：LLM 按 prompt 从 chunk 抽实体+关系（JSON，带 gleaning 补抽），文档级子图合并成全局图（同名实体合并、关系权重累加、PageRank 重算），可选实体消歧与 Leiden 社区发现；**实体类型清单决定抽什么、模型输出格式决定能不能成图**。

**调用链**：
```
graphrag 任务 → general/index.py __call__
  → per-doc：GraphExtractor.__call__ (extractor.py:131)
      → extract_all 并发处理 chunks (:135，Semaphore 限并发)
        → _process_single_content：调 LLM 抽取 → _entities_and_relations 解析 JSON (:114)
        → gleaning：_continue_prompt 问"还有遗漏吗"补抽一轮（max_gleanings 控制次数）
      → 错误容忍：max_errors=3（:138），超阈值才整批失败
  → merge_subgraph (index.py:488)：文档子图 → 全局图
      → 知识库级锁 + 同名实体合并 + 关系权重累加 + PageRank 重算
  → 可选：entity_resolution.py 实体消歧（默认关）
  → 可选：leiden.py + community_reports_extractor.py 社区发现+报告（默认关）
  → phase_markers.py 记录阶段完成（断点恢复用）
```

**核心机制（深挖点）**：

1. **实体类型决定抽什么**（extractor.py:46/62）：`DEFAULT_ENTITY_TYPES = ["organization", "person", "geo", "event", "category"]`——通用类型，不匹配核电业务（设备/参数/部件）。这就是 PBS 二开需求的根源：要换类型清单才能抽业务实体。
2. **空图的源码根因**（extractor.py:117-128）：LLM 输出按分隔符切 record → `handle_single_entity_extraction` 解析 → **entity_type 不在清单里的直接丢弃**（:122 `if ... in ent_types`）。所以"模型输出格式漂移 → 解析不出 → 0 nodes"和"类型不匹配 → 被过滤 → 0 nodes"是两条空图路径。我的模型对比结论（GLM 成功/Flash 空图）走的是第一条。
3. **gleaning 成本**（extractor.py:44 `ENTITY_EXTRACTION_MAX_GLEANINGS`）：每 chunk 抽完问一遍"是否遗漏"再补抽——我实测每单元 1 次、90 万 tokens 的成本主要在这里。
4. **并发抽取**（extractor.py:140 Semaphore）：`MAX_CONCURRENT_PROCESS_AND_EXTRACT_CHUNK` 限并发，不是全串行——但 131 CPU 上 LLM 调用本身慢。
5. **社区报告默认关**（index.py:464 `PHASE_COMMUNITY` + `with_community` 配置）：全局问题依赖社区报告，**测试全局题前必须确认开启**（T1 测试前置陷阱的源码位置）。
6. **图谱不落 Neo4j**（merge 写回 ES，环节⑥已述）：graph/subgraph/entity/relation/community_report 五种特殊 chunk。

**挂接实测**：
- PTR 手册 116 chunks → 17 抽取单元 → 979 nodes / 719 edges / 90 万 tokens / 1310s
- 空图案例：qwen-plus 成图（慢）/ DeepSeek Flash 空图 / GLM-5.2 稳定；4090 上模型实例名错导致 CONNECTION_ERROR 全失败
- ES 核验：`knowledge_graph_kwd=graph` 直查，不信任前端上限

**面试深挖预测**：
- 「实体类型清单能改吗？」→ 能，换业务类型才能抽设备/参数（PBS 二开）
- 「空图怎么排查？」→ 分两条路径：格式解析失败 vs 类型被过滤；看后端日志的 entity 抽取记录
- 「社区报告为什么默认关？」→ 成本高（LLM 生成摘要），按需开启
- 「gleaning 值得吗？」→ 提高召回但翻倍 token 成本，我实测每单元 1 次是默认折中

---

## 环节⑧ 在线检索（retriever）——面试最热

**一句话**：普通 RAG 走 Dealer——向量+BM25 混合检索融合打分；KG 检索走 KGSearch——query 改写找实体 → 实体/关系/N-hop/社区报告四路召回 → 按相似度×PageRank 排序 → 拼成虚拟 chunk 进 prompt。两条路可共存。

**检索 API 端点**：`POST /api/v1/retrieval`，body 传 `dataset_ids: [kb_id]` + `question` + `use_kg: true/false`。注意不是 `POST /api/v1/datasets/{id}/retrieve`（返回 code:100, chunks:0）。

**普通 RAG 检索链**（nlp/search.py:39 Dealer）：
```
问题 → qryr.question(qst, min_match=0.3) 生成 BM25 matchText + keywords (:192)
     → get_vector(qst, emb_mdl, topk, similarity=0.1) 向量召回 (:199)
     → dataStore.search(matchText + matchDense 混合) (:200)
     → 空结果时降阈值重试（min_match 0.3→0.1，similarity 0.1→0.17）(:217-224)
     → hybrid_similarity 融合打分 (:304)
     → top_n 截断进 prompt
```
- **混合打分**：`sim = hybridSimilarity(ans_embd, ins_embd, ans, inst)`（:304），`sim = vtweight × 向量相似度 + tkweight × BM25词权重`。`vtweight = vector_similarity_weight`（用户可配，RAGFlow 默认 0.3），`tkweight = 1 - vtweight`。实际配置 vtweight=0.3 / tkweight=0.7
- **min_match 自适应**（:217-224）：召回为空时自动放宽阈值——我项目里 vector_similarity_weight=0.3 / similarity_threshold=0.1 的配置走的就是这条路径
- **rerank 窗口**（:524 `_rerank_window`）：候选块按 window 分批取，可插 rerank

**KG 检索链**（graphrag/search.py:35 KGSearch，继承 Dealer）：
```
问题 → query_rewrite（LLM 改写：抽取查询实体 + 推断实体类型）(:161)
     → 四路并发召回：
        a. get_relevant_ents_by_keywords (:110)：实体向量召回（filters: knowledge_graph_kwd="entity"）
        b. get_relevant_ents_by_types (:128)：按类型筛实体（entity_type_kwd，按 PageRank 排）
        c. get_relevant_relations_by_txt (:119)：关系向量召回（knowledge_graph_kwd="relation"）
        d. N-hop 扩展 (:172-186)：从命中实体沿关系图扩展邻居路径
     → 打分公式（:193 注释原文）：P(E|Q) = P(E) * P(Q|E) = pagerank * sim
        实体：sim *= 2 若同时被类型命中 (:197)
        关系：sim *= (类型命中加分 + N-hop 加分 + 1) (:199-209)
     → 排序：sim * pagerank 降序 (:220/:221)，ent_topn=6 / rel_topn=6 截断
     → 社区报告召回 (_community_retrieval_ :277)：按命中实体的 entities_kwd 匹配 community_report
     → 拼成虚拟 chunk：content = Entities CSV + Relations CSV + Community Report (:253-264)
        docnm_kwd = "Related content in Knowledge Graph" (:266)
```

**核心机制（深挖点）**：

1. **KG 检索的"虚拟 chunk"**（:261-275）：四路结果拼成一个伪 chunk（similarity=1.0、doc_id=空），和普通 chunk 一起进 prompt——**这就是"KG 与普通检索共存"的机制**：不是两套 prompt，是召回阶段混合。
2. **打分核心公式**（:193）：`score = sim × pagerank`——实体的重要性（PageRank）和相关性（向量相似度）相乘。N-hop 邻居路径按距离衰减（:183 `sim / (2+i)`）。
3. **query_rewrite 是 KG 检索第一步**（:161）：LLM 先分析问题抽实体和类型——这一步失败（:163-166）会退化成 ents=[原始问题]，KG 检索质量直接下降。模型能力影响从这里开始，不只是抽取阶段。
4. **社区报告按实体匹配**（:284 `entities_kwd`）：社区报告里包含哪些实体，命中查询实体才被召回——全局问题的汇总能力依赖社区报告质量。
5. **sim_threshold=0.3**（:150）：KG 检索默认相似度阈值 0.3，比普通 RAG 的 0.1 高——实体匹配要求更严。

**挂接实测**：
- vector_similarity_weight=0.3、similarity_threshold=0.1、top_k=1024、top_n=6（4090 PTR 配置）
- 纯向量最高相似度 0.331 / KG 0.464（+40%）——KG 精准命中供货边界表
- 检索延迟：向量 563ms / KG 1240ms，均非瓶颈

**面试深挖预测**（这是最热环节，QA 已备 6 题）：
- 「混合检索怎么打分？」→ 向量+BM25 加权融合，权重可配（我 0.3）；空结果自动降阈值重试
- 「KG 检索怎么和普通共存？」→ KG 结果拼成虚拟 chunk，similarity=1.0，和普通 chunk 一起进 prompt
- 「KG 打分公式？」→ sim × pagerank，N-hop 按距离衰减
- 「top_k vs top_n？」→ 1024 召回 → 6 进 prompt，中间可 rerank
- 「检索效果差怎么调？」→ 分层诊断：召回差调 chunk/权重/阈值，排序差上 rerank，生成差调 prompt——我有 KG 对照数据，参数级调优是下一步

---

## 环节⑨ 问答生成（chat）

**一句话**：检索回的 chunks 经 `kb_prompt` 拼成知识上下文（每块带 ID/标题/内容，按 max_tokens 截断），填进 system prompt 的 `{knowledge}` 占位符 → LLM 生成 → `insert_citations` 按句子切分回填引用编号；KG 结果作为虚拟 chunk 插在 chunks 列表最前。

**调用链**：
```
dialog_service.py async_chat (:665)
  → retriever.retrieval (普通 RAG 召回，:764)
  → use_kg 开启时：kg_retriever.retrieval → 虚拟 chunk insert(0, ck) (:789-795)
  → kb_prompt(kbinfos, max_tokens) (generator.py:139) 拼知识上下文
      → 逐块累加 token，超 97% max_tokens 截断 (:149)
      → 每块格式：ID + Title + Content（ID 用于引用回填）(:163)
  → system prompt 替换 {knowledge} → LLM 生成
  → insert_citations (search.py:251) 按句子切分答案，匹配 chunk 回填引用
  → 流式：yield 增量返回
```

**核心机制（深挖点）**：

1. **知识拼接的 token 预算**（generator.py:149）：检索回的 chunks 按顺序累加 token，超 max_tokens 97% 就截断——所以 top_n=6 召回但 max_tokens 不够时实际进 prompt 的可能更少。这是 `top_n` 和 `max_tokens` 两个参数的协作关系。
2. **每块带 ID 是引用回填的钥匙**（generator.py:163）：每块格式 `ID: {i}\n├── Title: ...\n├── Content: ...`，LLM 输出引用 `[ID:0]` 时前端按 ID 映射回 chunk——这就是我实测 `[ID:1][ID:2]` 引用的来源机制。
3. **KG 虚拟 chunk 插在最前**（dialog_service.py:795 `kbinfos["chunks"].insert(0, ck)`）：KG 检索结果作为虚拟 chunk 插在 chunks 列表第 0 位——**优先级最高，token 预算不够时普通 chunk 先被截断**。这是 KG 与普通检索共存的最终落点：不是两路答案合并，是 KG 上下文优先占 prompt。
4. **多轮问题改写**（dialog_service.py:704 `full_question`）：多轮对话时先用 LLM 把上下文压缩成完整问题再检索——`refine_multiturn` 开关控制。
5. **引用回填按句子切**（search.py:251 `insert_citations`）：答案按句子边界切分，每句匹配最相似的 chunk 编号——不是整段匹配，是句级引用。`tkweight/vtweight`（默认 0.1/0.9）控制词权重 vs 向量权重。
6. **空结果兜底**（dialog_service.py:809 `empty_response`）：检索为空时返回配置的 empty_response 文案，不强行让 LLM 编。

**挂接实测**：
- T2 优化落地：max_tokens 256 + 简化 system prompt + top_n 4 → 简单问答 1016ms（达标）、流式 TTFT 859ms
- prompt 简化效果（-37%）：system 从"详细列举"改"简洁直接"，答案从 200 字降到 33 字——这是 generator.py 拼接后的 LLM 行为，prompt 控制生成量
- 引用回填：PTR 答案 `[ID:1][ID:2]` 可溯源到具体 chunk（含 640m³/h、36m 的供货边界表）

**面试深挖预测**：
- 「知识怎么拼进 prompt？」→ kb_prompt 逐块带 ID+标题+内容，按 max_tokens 97% 截断
- 「引用怎么回填？」→ 句级切分匹配 chunk ID，不是整段
- 「KG 和普通检索结果怎么排？」→ KG 虚拟 chunk insert(0) 最前，token 预算不够时普通 chunk 先截断
- 「top_n 和 max_tokens 什么关系？」→ top_n 控召回数，max_tokens 控实际进 prompt 数——召回多但预算不够会截断
- 「多轮对话怎么处理？」→ full_question 改写，把上下文压成完整问题再检索

---

## 全链路调研完成 ✅

九环节全部完成，函数级调用链 + 核心机制 + 实测数字 + 面试深挖预测齐全。

**全链路一句话总结**（面试电梯版）：
上传文件落对象存储+建元数据 → 解析接口拆 task 进 Redis Stream 队列 → Task Executor 按 parser_id 选模板（naive/paper/laws…），PDF 按配置选解析引擎（DeepDOC/MinerU/OCR）→ 分块（按 delimiter 切段+chunk_token_num 聚合，超限不硬切）→ embedding 批量向量化（标题+正文加权融合）→ 写入 ES（图谱同索引用 knowledge_graph_kwd 区分）→ GraphRAG 在 chunks 上抽实体关系建图（可选消歧+社区）→ 在线检索向量+BM25 混合打分（KG 开启时四路召回拼虚拟 chunk 插最前）→ kb_prompt 拼知识进 system prompt → LLM 生成 → insert_citations 句级回填引用。

**面试时沿这条链随机抽问的防守能力**：每个环节都有函数级调用链、源码行号、实测数字、深挖预测四层弹药——这是"全链路理解"最硬的形态。
