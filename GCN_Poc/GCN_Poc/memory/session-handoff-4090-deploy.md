# 会话交接：1万份测试 + 4090 部署 RAGFlow

> 生成于 2026-09-09。新窗口继续用这份文档恢复上下文。

## 一、当前正在跑的任务（131 服务器）

### 1 万份稳定性测试（后台跑着，不要动）

- **服务器**：131（10.126.2.131，root 免密直连）
- **容器**：docker-ragflow-cpu-1
- **脚本**：`/ragflow/ingest/mentor_b_bench.py`（InMemory 模式，并发3）
- **启动时间**：2026-09-08 17:25
- **日志**：`/tmp/bench_10k.log`
- **结果文件**：`/tmp/bench_10k.json`（跑完才写）
- **进度查看**：
  ```bash
  ssh root@10.126.2.131 "docker exec docker-ragflow-cpu-1 tail -5 /tmp/bench_10k.log"
  ```
- **最新进度**（09-09 11:42）：`wall=63645s succeeded=5324 failed=6`，吞吐 0.084 份/s
- **预计完成**：09-09 深夜/09-10 凌晨（按 0.084 份/s，剩 4667 份约 15 小时）
- **跑完标志**：日志出现 `RESULT` + `saved -> /tmp/bench_10k.json`

### 跑完后要做的

1. 拉 JSON：`scp root@10.126.2.131:/tmp/bench_10k.json` → 注意 JSON 在容器里，先 `docker cp` 到 131 宿主再 scp
2. 生成 1 万份稳定性报告（脚本 `code/ingest/bench_report.py` 可复用，或新写）
3. 把 1 万份报告加进导航栏（`code/ingest/inject_navbar.py` 的 NAV_ITEMS 加一项，重跑注入）
4. 清理 131 KB 2f84... 的 13189 份脏数据 + gcn_ingest 三表

## 二、新任务：4090 服务器部署 RAGFlow（mentor 安排）

### 4090 服务器信息

- **IP**：10.148.4.21
- **SSH**：port 22, root, 密码 `szwg%2024`
- **从本机直连**：✅ 可连（`ssh root@10.148.4.21`，输密码即可）
- **hostname**：dubhe-master-1（Ubuntu 22.04.5）

### 4090 环境状态（已探测）

| 项 | 值 |
|---|---|
| GPU | **4 × RTX 4090**（各 24GB），驱动 580.173.02，CUDA 13.0 |
| Docker | ✅ 29.7.2 + Compose v5.4.0 |
| RAGFlow | ❌ 无（干净环境） |
| 磁盘 | `/` 1.7T 用了 1.5T，剩 175G（⚠️ 偏紧） |
| 内存 | 251GB（剩 201GB） |
| nvcc | CUDA 11.8 编译工具 |
| GPU 当前占用 | ⚠️ 4 张卡各用了 22G/17G/11G/19G（有 VLLM 等进程在跑，是共享机） |

### mentor 的要求

- "把 131 上的配置搬过去"——指 RAGFlow 的部署配置（docker-compose.yml + .env）
- "bge-base 用 GPU 跑"——embedding 服务从 CPU 换 GPU

### 部署前需搞清楚的（下一步）

1. **131 的 RAGFlow 是怎么部署的**——docker-compose.yml 在哪、.env 配了什么。需要看 131 容器的 docker-compose 配置。
2. **131 的 RAGFlow 版本**——v0.26.1，源码在 `f:\byh\GCN_Poc\GCN_Poc\code\ragflow\`（本地检出）
3. **bge-base GPU 怎么跑**——RAGFlow 的 embedding 服务配置，`.env` 里 `DEVICE=gpu`（README.md:209）
4. **磁盘够不够**——175G 剩余，RAGFlow + ES + 1万份文档可能要 50-100G
5. **GPU 显存够不够**——4 张 4090 显存已用大半，bge-base 是小模型但要确认能挤进去
6. **要搬哪些配置**——docker-compose.yml、.env（改 DEVICE=gpu）、MySQL/ES/Redis/MinIO 配置、mentor 的 ingest 服务

## 三、已完成的工作（这两天）

### 4 份报告（都有共享顶部导航栏，可互相跳转）

位于 `f:\byh\GCN_Poc\GCN_Poc\doc\design\`：

1. `RAGFlow原生批量上传测试_20260908.html` — 方案A 100份测试
2. `方案B并发压测_20260908.html` — 并发1/3/6 三档
3. `RAGFlow原生局限与mentor方案结论_20260908.html` — 结论报告
4. `批量导入规模验证_20260907.html` — mentor 千份 baseline
5. `批量上传测试总索引_20260908.html` — 总索引页

### 关键结论

- **方案A（RAGFlow原生）**：100份 1104s，0.091份/s，取消实测不生效（0/70变CANCEL），进度只有单浮点+排队文本，满足PM 5项需求中的1项
- **方案B（mentor自建）**：并发3最优（0.180份/s），并发6无收益（争抢开销），embedding占93-95%
- **方案B MySQL并发bug**：`MySQLRepository` threading.local 在 ThreadPoolExecutor 并发下连接断开，task全失败（NoneType error）。InMemory 不受影响。
- **embedding是绝对瓶颈**：131 CPU bge-base，长尾严重（avg 11s并发1 → 30s并发6）

### 可复用脚本（在 code/ingest/）

- `native_upload_test.py` — 方案A纯原生API测试
- `mentor_b_bench.py` — 方案B并发压测（支持 --persist）
- `ab_prepare_docs.py` — 筛纯真.docx（从zip）
- `_clear_kb.py` — 清空RAGFlow KB
- `inject_navbar.py` — 给报告HTML注入导航栏
- `bench_report.py` / `native_report.py` / `conclusion_report.py` / `index_report.py` — 报告生成

### 测试数据

- `test/_abtest_docs/` — 100份纯真.docx（筛选后）
- `test/_abtest_docs_10k/` — 10000份纯真.docx
- `test/results/ab_doc_list.json` — 100份清单
- `test/results/ab_doc_list_10k.json` — 10000份清单
- `test/results/131_测试/native_r1.json` — 方案A 100份结果
- `test/results/131_测试/native_cancel.json` — 方案A取消测试结果
- `test/results/131_测试/bench_c1.json` / `bench_c3.json` / `bench_c6.json` — 并发压测三档结果

## 四、环境与凭据

### 131 服务器（RAGFlow 现环境）

- SSH：`ssh root@10.126.2.131`（免密，本机 ~/.ssh/id_ed25519）
- RAGFlow Web/API：http://10.126.2.131:9388
- 容器内 API：localhost:9380（不是9388）
- 容器：docker-ragflow-cpu-1
- API Key：`ragflow-jViws3pYe3tAxCiLQ7LgjsJ-SRYF730cGMDXKptJk98`（tenant 56f78bf26ac611f187cd7db89d62ca74）
- MySQL密码：`infini_rag_flow`（环境变量 MYSQL_PASSWORD）
- mentor服务：http://10.126.2.131:9800/demo
- 测试KB：`2f84a97aab4811f1a5be33e6206585a1`（AB测试_原生，需清理）

### 4090 服务器（新部署目标）

- SSH：`ssh root@10.148.4.21`（密码 szwg%2024）
- 4×RTX 4090，Docker已装，干净环境

## 五、新窗口继续的下一步

### 优先级1：等1万份跑完 → 出报告
```bash
ssh root@10.126.2.131 "docker exec docker-ragflow-cpu-1 tail -5 /tmp/bench_10k.log"
```
看到 `RESULT` + `saved` → 拉JSON → 生成报告 → 加导航栏

### 优先级2：4090 部署 RAGFlow
1. 先搞清 131 的 RAGFlow 部署方式（docker-compose.yml 位置、.env 配置）
2. 看 RAGFlow 源码 `f:\byh\GCN_Poc\GCN_Poc\code\ragflow\` 的 docker-compose.yml
3. 把配置搬到 4090，改 `DEVICE=gpu`
4. 起服务，验证 bge-base 在 GPU 跑
5. 跑同样的1万份压测对比 GPU vs CPU 吞吐
