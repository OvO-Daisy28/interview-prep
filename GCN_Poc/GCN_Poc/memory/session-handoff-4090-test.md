# 会话交接：4090 RAGFlow + GPU bge 部署完成，转测试阶段

> 生成于 2026-09-11。新窗口读这份文档 + memory `4090-deploy-handoff.md` 恢复上下文，可直接在 4090 上继续测试。

## 一、一句话状态

4090（10.148.4.21）上的 **RAGFlow v0.26.1 + GPU bge-base + 本地 Qwen3.8-27B 已部署完成并通过验收**，问答链路跑通。下一步是在 4090 上跑 GPU 压测，对比 131 CPU 的吞吐（131 测试已收尾）。

## 二、4090 当前真实状态（2026-09-11 核实）

### 6 个容器全部 running + 自动重启

| 容器 | 镜像 | 用途 | restart |
|---|---|---|---|
| docker-ragflow-gpu-1 | infiniflow/ragflow:v0.26.1 | RAGFlow 主服务 | unless-stopped |
| docker-es01-1 | elasticsearch:8.11.3 | 文档存储检索 | unless-stopped |
| docker-mysql-1 | mysql:8.0.39 | 元数据（端口 5455） | unless-stopped |
| docker-minio-1 | pgsty/minio:RELEASE.2026-03-25 | 对象存储（端口 19000） | unless-stopped |
| docker-redis-1 | valkey/valkey:8 | 任务队列（端口 26379） | unless-stopped |
| **bge-gpu** | **bge-embedding:gpu-v2** | **GPU bge-base embedding（GPU2, cuda:0）** | unless-stopped |

- bge-gpu 镜像必须是 **v2**（含空文本修复），重建容器别用旧 gpu
- bge-gpu 启动参数：`docker run -d --name bge-gpu --gpus all -e CUDA_VISIBLE_DEVICES=2 --network docker_ragflow --restart unless-stopped bge-embedding:gpu-v2`

### 服务访问

| 服务 | 地址 |
|---|---|
| RAGFlow 网页 | http://10.148.4.21:9388 |
| RAGFlow API | http://10.148.4.21:9380 |
| bge embedding（容器内） | http://bge-gpu:18001/v1（只供 RAGFlow 容器调用） |
| 本地 Qwen3.8-27B | http://10.148.4.21:18003（int8，GPU2+3）/ http://10.148.4.21:18004（int4，GPU0） |

### 登录账号（密码已修复，浏览器可登）

| 邮箱 | 密码 | 权限 |
|---|---|---|
| 250515008@qq.com | 19108477225 | superuser |
| admin@ragflow.io | admin | superuser |
| 2689242493@qq.com | （用户自注册的） | 普通用户 |

> RAGFlow 登录密码坑：DB 里存的是 base64(密码) 的 werkzeug hash，不是明文 hash。改密码见 memory。

### LLM / embedding 配置（已配好）

| 实例名 | 类型 | base_url | 说明 |
|---|---|---|---|
| deepreasoning-gl-5.3flash | chat | https://aicoding.wenge.com/v1 | 公司 API，**有每日额度**，用完报 402 |
| qwen38-local | chat | http://172.22.0.1:18003/v1 | 本地 Qwen3.8-27B（int8），不受额度限制，兜底用 |
| bge-base | embedding | http://bge-gpu:18001/v1 | GPU bge-base，租户默认 embedding |

### GPU 分配

| GPU | 用途 | 显存 |
|---|---|---|
| 0 | 别人 VLLM + qwen38-vllm-lowlatency | 几乎占满 |
| 1 | 别人进程 | 17G 占用 |
| **2** | **我们的 bge-gpu（cuda:0）+ qwen38-27b-int8** | 16G 占用 / 8G 余 |
| 3 | qwen38-27b-int8 + 别人 | 19G 占用 |

### 知识库现状

- 知识库 `1e427314acf011f1850e49f1b996babd`（名「9.10??」，1 个文档）——测试用的，可删可留
- 租户 `8a0845faace211f1850e49f1b996babd`（admin's Kingdom）

## 三、关键路径和文件

### 4090 上的关键路径

| 路径 | 内容 |
|---|---|
| /root/ragflow/docker/ | RAGFlow 的 docker-compose 配置 + .env |
| /root/ragflow/ | 8 个 GraphRAG 补丁文件（compose 挂载） |
| bge 镜像 bge-embedding:gpu-v2 | 含 model 2.27G + torch + sentence-transformers + 空文本修复 |
| 131 上 /data/zwt/embedding_build/ | bge 镜像的 build context（Dockerfile + 脚本 + model） |

### 本地的关键产物（131 测试已收尾）

| 文件 | 说明 |
|---|---|
| doc/design/131_测试/实验数据汇总_20260911.md | 5 次实验数据汇总 + 万份变慢根因分析（给 workbuddy 导入企微） |
| test/results/131_测试/experiments_summary.csv | 同上 CSV 版 |
| test/results/131_测试/bench_10k.json | 131 一万份压测原始数据（9994/10000 成功，0.046 份/s） |
| test/results/131_测试/bench_c3.json | 131 50 份并发3 baseline（0.180 份/s）——**4090 GPU 压测的对比基准** |
| code/ingest/mentor_b_bench.py | 压测脚本，4090 上复用 |
| code/ingest/bench_10k_report.py | 万份报告生成脚本 |

## 四、131 的结论（4090 要对比的）

- 131 CPU embedding：单份 avg **17.1s**，max **556s**（长尾）
- 131 万份吞吐：**0.046 份/s**（比 50 份降 74%）
- 万份变慢主因：**embedding 长尾堵塞并发槽**（墙钟 69% 在等长尾），不是单份变慢
- 4090 GPU 单条 embedding：**0.030s**（131 的 ~500 倍）
- **4090 要测的**：端到端 GPU 吞吐，证明 GPU 消除长尾后吞吐能提多少

## 五、新窗口下一步：4090 GPU 压测

### 目标
在 4090 上用 `mentor_b_bench.py` 跑 100 份（快速）和 1 万份（全量），对比 131 CPU：
- GPU 端到端吞吐 vs 131 的 0.046 份/s
- GPU embedding 长尾是否消除（max 还是不是 556s）

### 执行要点（避坑）

1. **压测脚本要改指向 4090 的 RAGFlow**：`mentor_b_bench.py` 默认连 131 的 API（10.126.2.131:9388），4090 上跑要改成 `http://10.148.4.21:9388` + 4090 的 API key（在网页生成）。

2. **测试数据搬运**：1 万份 docx 在本地 `test/_abtest_docs_10k/`（约 1-2GB），要传到 4090。4090 大文件下载卡死，用 **docker save relay 或 ssh 管道**（见 memory「4090 网络结构性限制」）。先跑 100 份快速验证。

3. **4090 网络坑（重要）**：
   - 4090 容器+宿主机对持续大文件下载**普遍卡死**（pip/uv/PyPI 都卡）
   - 唯一能搬大文件的路径：①docker pull（走 daemon daocloud mirror）②docker save relay（131→本机→4090）
   - **不要在 4090 上直接 pip/uv 装大包**

4. **bge-gpu 容器**：跑压测前确认还在跑（`docker ps | grep bge-gpu`），device=cuda:0。

5. **LLM 额度**：公司 API（gl-5.3flash）有每日额度，用完报 402。压测 ingest 只用 embedding（不走 LLM），不受影响；问答测试才用 LLM，可切 qwen38-local 兜底。

### 命令速查

```bash
# 登录 4090
ssh root@10.148.4.21

# 查所有服务状态
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -iE 'ragflow|bge-gpu|es01|mysql|minio|redis'

# 查 bge 是否在 GPU 上
docker exec bge-gpu python3 -c 'import urllib.request;print(urllib.request.urlopen("http://127.0.0.1:18001/health").read().decode()[:90])'
# 期望 device:cuda:0

# 测试 bge（从 RAGFlow 容器）
docker exec docker-ragflow-gpu-1 python3 -c '
import urllib.request,json
r=urllib.request.urlopen(urllib.request.Request("http://bge-gpu:18001/v1/embeddings",data=json.dumps({"model":"bge-base","input":["测试"]}).encode(),headers={"Content-Type":"application/json"}))
print("OK",r.status,"dim",len(json.load(r)["data"][0]["embedding"]))'
# 期望 OK 200 dim 1024

# 查 GPU 显存
nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader

# 重启 bge（如需）
docker restart bge-gpu

# RAGFlow 网页登录
# http://10.148.4.21:9388  账号 250515008@qq.com / 19108477225
```

## 六、memory 引用

详细部署细节、踩坑、命令都在 memory：
- `C:\Users\zhuwenting\.claude\projects\f--byh\memory\4090-deploy-handoff.md` —— 4090 部署全程 + 坑 + 命令
- 本文件 `f:\byh\GCN_Poc\GCN_Poc\memory\session-handoff-4090-test.md` —— 本交接

新窗口先 `Read` 这两个文件，再开始。

## 七、未完成 / 待办

1. **4090 GPU 压测对比**（主任务）：100 份快速 + 1 万份全量，出 GPU vs CPU 对比报告
2. **清理 131 测试脏数据**（可选）：131 的 KB `2f84a97aab4811f1a5be33e6206585a1` + gcn_ingest 三表（含残留 job 39）
3. **4090 部署报告更新**：补上问答跑通、本地 Qwen、登录修复等新进展（现有报告在 doc/design/，之前那份部署报告要更新）
