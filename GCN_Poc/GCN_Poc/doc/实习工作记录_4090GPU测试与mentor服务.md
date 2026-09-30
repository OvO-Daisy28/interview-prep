# 实习工作记录：4090 GPU 压测与 mentor 批量上传服务

> 阶段：2026-09-11 · 前置：131 CPU 批量导入测试已收尾（5 次实验），4090 RAGFlow + GPU bge-base 部署已验收
> 本阶段目标：验证 GPU 消除 embedding 长尾后，吞吐能提多少、规模放大下是否退化

## 背景一句话

131 CPU 测试结论：embedding 是绝对瓶颈（占比 87%–96%），万份吞吐因 embedding 长尾（max 556s）堵塞并发槽崩塌至 0.046 份/s（比百份降 74%）。我在 4090 上用 GPU（bge-gpu 容器，GPU2 cuda:0）重跑同样口径的压测，并部署 mentor 批量上传服务做前端真实路径验证。

---

## 一、做了什么（按时间线）

### 1. 4090 GPU 压测（脚本路径，100 份并发3）

**先发现一个交接文档错误**：`mentor_b_bench.py` 是容器内 Python 模块直调，不走 RAGFlow HTTP API。交接文档说"改成 http://10.148.4.21:9388 + API key"是误导——真正要改的是 embedding 服务地址。脚本默认 `embed_url` 指向 131 的 CPU 服务（`http://192.168.80.1:18001/v1`），不改的话 4090 上跑的还是调 131 的 CPU。

**修复**：给 `mentor_b_bench.py` 加 `--embed-url` 参数（默认保留 131 兼容，4090 传 `http://bge-gpu:18001/v1`）。

**结果（100 份并发3，对比 131 bench_c3 50 份并发3）**：

| 指标 | 131 CPU | 4090 GPU | 变化 |
|---|---|---|---|
| 吞吐 | 0.180 份/s | **1.029 份/s** | **×5.7** |
| embed avg | 15.31s | 1.46s | ×10.5 |
| embed max | 72.80s | 8.90s | ×8.2（长尾根治） |
| embed 占比 | 93.6% | 51.2% | 瓶颈转移 |
| index 占比 | 6.1% | **42.7%** | 成新瓶颈 |

### 2. mentor 批量上传服务部署到 4090

把 mentor 的常驻服务（`service.py` + FastAPI REST + worker + demo 前端页）在 4090 RAGFlow 容器内跑起来，前端真实上传路径对比脚本压测：

- **模式选择**：`--in-memory`（MySQLRepository 有 `threading.local()` 并发 bug，并发3 下任务全失败，只能绕开）
- **依赖补齐**：4090 容器缺 fastapi，且 4090 pip 装包会卡死（网络结构性限制）→ 从 131 容器 docker relay fastapi 0.141.1 + annotated-doc（教训：先 `importlib.metadata.requires()` 查完整依赖树，不要逐个 import 踩坑）
- **端口暴露**：宿主机跑 `demo_forward.py`（stdlib 转发 0.0.0.0:9800 → 容器 172.22.0.6:9800），不动容器端口映射（重建容器会中断 RAGFlow）
- 前端入口：http://10.148.4.21:9800/demo

**前端上传 100 份 vs 脚本压测**：吞吐 0.786 vs 1.029 份/s（**服务层 -24%**，来自 worker 轮询 + ThreadPoolExecutor 反复创建 + 上传落地 /tmp）；embed 反而更快（1.21s vs 1.46s，服务启动时付了 warm-up）。**index 占 51.6%，是两种模式的共同绝对瓶颈**。

### 3. 知识库管理（踩污染坑后固化流程）

脚本压测的 100 份写进了已有 KB（变 101 份脏数据）→ 认识到**每次测试必须新建 KB**。写了 `create_kb.py`：复用 RAGFlow 自己的 service 层建库（`KnowledgebaseService.create_with_name` + 继承租户默认 embd_id + `save`），和 web 界面建库完全一致。

搞清了 RAGFlow 建 KB 的机制：**只需插 knowledgebase 表一行，无 init ES 步骤**——ES index 是 tenant 级别（`ragflow_<tenant>`），同租户所有 KB 共用，按 kb_id 字段过滤；MinIO bucket=kb_id 首次写数据时自动建。

### 4. 工作区文件按服务器分离整理

131 和 4090 的产出混在 `doc/design/` 和 `test/results/` 根目录，做了物理分离：

- `doc/design/`：`131_测试/`（7 个：实验数据汇总 + 6 个 HTML 报告）、`4090_测试/`（2 个）、共用设计文档留根（11 个）+ 新建 INDEX.md 导航
- `test/results/`：`131_测试/`（6 个压测 JSON + 6 个日期/功能子目录）、`4090_测试/`（bench_gpu_c3.json）、共用清单留根
- 6 个 HTML 报告互链用同目录相对路径，整体移动后互链不失效（无需改导航栏）
- 同步更新了 7 个报告脚本的硬编码路径、memory 引用、CLAUDE.md 目录规则
- 补齐了总索引 HTML 的过期内容（万份已完成、加 4090 GPU 对照条目）

**关键判断**：`infrastructure-reuse-feasibility.md`、`ragflow-modification-candidates.md` 虽含 131 数据，但被共用设计文档用相对路径引用，移走会断链 → 留根。

### 5. 制定 4090 测试规范（与导师确认后落成文档）

规范核心（`doc/design/4090_测试/4090_测试规范.md`）：
- **阶梯**：100 份 → 1000 份 → 1 万份（30 万不规划）
- **路径**：全部走 mentor 批量上传接口前端上传，不写脚本压测（验证真实用户路径）
- **报告**：Markdown
- **分工**：我建 KB/确认服务，导师前端上传，我盯进度 + 统计各阶段时长（从 `GET /ingest/jobs/{id}` 的 stages.duration_ms 提取）
- **每次测试必做**：新建 KB，命名 `GPU测试_<档位>_<日期>`

### 6. 千份测试（含一个 500 错误的修复）

前端上传 1000 份时报 HTTP 500。**追根因**：`rest_api.py` 上传暂存用 `{uuid前8}_{原文件名}` 做磁盘名，法律文档文件名常超 Linux 255 字节上限（如「1994-11-07_最高人民法院、最高人民检察院…撤销问题的答复.docx」），触发 `OSError [Errno 36] File name too long`，单份文件名超长让整个请求 500。

**修复**：暂存名只用纯 uuid（32 字符），原文件名只存进 job 的 name 字段（pipeline 用 name 做 doc_name，不依赖磁盘路径）。修复后传容器 + 重启服务。

**千份结果（mentor 服务前端上传，1000/1000 成功，0 失败）**：

| 指标 | 4090 百份 | 4090 千份 | 131 千份 | 131 万份 |
|---|---|---|---|---|
| 吞吐 | 0.786 份/s | **1.406 份/s** | 0.25 份/s | 0.046 份/s |
| embed avg | 1.21s | 0.65s | 7.67s | 17.11s |
| embed max | 5.74s | 5.43s | — | 555.99s |
| embed p99 | — | 2.38s | — | 74.51s |
| embed 占比 | 45.4% | 53.4% | 96.0% | 86.7% |
| index 占比 | 51.6% | 37.2% | 3.6% | 4.1% |

### 7. 万份测试尝试（未完成）

前端上传 1 万个文件失败（`Failed to fetch`，请求根本没到服务端——浏览器单次 fetch 的文件数/请求体上限）。预案已定：分批上传（2000 份 × 5 批，同一 KB），未执行。

---

## 二、验证过的核心结论（数据支撑）

1. **GPU 吞吐 5.6–5.7 倍**：百份 1.029/0.786 vs 131 的 0.180；千份 1.406 vs 131 千份 0.25。加速比在百份和千份规模稳定一致。

2. **embedding 长尾被根治**：131 embed max 72.8s（百份）→ 556s（万份）；4090 全程 5.4–8.9s，p99 2.38s。GPU 独占无争抢，长尾不随规模放大。

3. **瓶颈发生了转移**：GPU 把 embedding 从 93.6% 压到 45–53% 后，**index 写入（ES bulk + MinIO + MySQL 三表）成了新瓶颈（37–52%）**。下一阶段优化方向从 embedding 转向 index。

4. **131 的规模退化在 4090 上不存在**：131 从百份 0.180 退到万份 0.046（降 74%）；4090 百份 0.786 → 千份 1.406 反升（warm-up 摊薄），长尾稳定。

5. **Amdahl 定律实测吻合**：embed 占 93.6% 时提速 10.5×，理论吞吐上限 6.5×，实测 5.7×——解释了"单条快 10.5 倍但吞吐只快 5.7 倍"，差值在 index。

6. **mentor 服务层 -24% 开销**：0.786 vs 1.029 份/s（worker 2s 轮询 + run_batch 反复建线程池 + 上传落地 /tmp）；embed 本身不变慢甚至更快。

---

## 三、学到的工程知识（被验证过的）

| 知识点 | 来源 |
|---|---|
| Amdahl 定律在真实压测中的验证：加速比受非瓶颈阶段占比封顶 | GPU 压测数据分析 |
| RAGFlow ES index 是 tenant 级共用（`ragflow_<tenant>`），KB 建库只插表不 init ES | create_kb.py 开发 |
| `MySQLRepository` 的 `threading.local()` 在 ThreadPoolExecutor 并发下连接断开——连接不是线程安全的要在池化层解决 | mentor 服务模式选择 |
| 用户上传文件名不可控，磁盘暂存名必须用 uuid 隔离（255 字节上限） | ENAMETOOLONG 修复 |
| 4090 网络结构性限制：pip/uv 持续下载卡死，唯一搬包路径是 docker relay（131→本机→4090） | fastapi relay |
| 查依赖树用 `importlib.metadata.requires()`，不要逐个 import 试错 | relay 时少踩一轮坑 |
| ssh + nohup 后台进程持有 stdout 会让 ssh 挂起，用 `</dev/null` 或分步启动 | demo_forward 启动 |
| RAGFlow 的 `TenantService` 在 `api.db.services.user_service`（不是 tenant_service）；`api_token` 表主键是 token 无 id 列 | create_kb 开发 |
| 浏览器单次 fetch 有文件数上限，1 万文件直接 Failed to fetch（请求未达服务端） | 万份尝试 |
| HTML 报告互链用同目录相对路径，整目录移动不破坏引用链 | 文件整理 |

---

## 四、产物清单

| 类型 | 产物 |
|---|---|
| 测试数据 | `test/results/4090_测试/bench_gpu_c3.json`（脚本 100 份）、`bench_gpu_service_1k.json`（服务千份，1000/1000） |
| 报告 | `doc/design/4090_测试/4090_GPU压测_20260911.md`（含 GPU vs CPU、服务 vs 脚本、千份结果） |
| 决策与踩坑 | `doc/design/4090_测试/4090_决策与踩坑记录_20260911.md`（6 决策 + 10 坑 + 命令速查） |
| 测试规范 | `doc/design/4090_测试/4090_测试规范.md`（100→1000→1万阶梯、前端上传口径） |
| 代码改动 | `mentor_b_bench.py` 加 `--embed-url`；`rest_api.py` 暂存名改 uuid；新增 `create_kb.py` |
| 测试集 | `test/_abtest_docs_1k/`（1000 份干净测试集，可复现：按文件名排序前 1000） |

---

## 五、未完成 / 下一步

- [ ] **万份测试**：前端单次上传 1 万文件不可行，按预案分批（2000 × 5 批同 KB）后合并统计；这是验证 GPU 规模退化假设的最后一档（千份已证明不退化）
- [ ] 清理脏 KB「9.10测试」（`1e427314…`，101 份残留）
- [ ] `MySQLRepository` 并发 bug 若需万份断点恢复，要先修（改成连接池或 per-task 连接）

---

## 六、收获总结

1. **完整走了"发现瓶颈 → 提出假设 → 换环境验证 → 数据证明"的闭环**：131 的结论是"embedding 长尾是万份崩塌真凶"，4090 的 GPU 压测用 embed max 5.4s、吞吐不退化、长尾 p99 稳定这组数据闭环验证了这个根因判断——GPU 不只是快，是根治。

2. **学会了用统计分布而不是平均值看性能**：131 万份 embed avg 只涨 12% 但吞吐崩 74%，靠 p99/max 长尾分析和"墙钟 69% 在等长尾"的差额法才定位到真凶；4090 的验证也全程盯 p99/max 而不是只看 avg。

3. **真实用户路径和极限压测是两条口径**：脚本 1.029 vs 服务前端上传 0.786，-24% 是 REST + worker 模型的真实成本；给导师的测试规范因此定成"全部前端上传"——测的是交付形态，不是流水线极限。

4. **踩坑 → 修根因 → 沉淀**：每次报错都追到根因（500 错误追到文件名 255 字节上限、fetch 失败确认请求未达服务端），修复同时写进踩坑记录和决策记录，可复用。
