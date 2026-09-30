# RAGFlow 队列问题处置方案

> 配套《RAGFlow 文档解析卡死排查汇报》使用。对应"发现的问题"逐条给解法、收益、成本。

---

## 一、总览（按投入产出比排序）

| # | 问题 | 解决方案 | 收益 | 成本 | 优先级 |
|---|---|---|---|---|---|
| 1 | worker 只有 1 个 | 加 `--workers` | 批量卡死直接缓解 | 改配置重启 | ⭐⭐⭐⭐⭐ |
| 2 | 僵尸工单堆积 43 天 | 清理 task 表 progress=0 老工单 | 队列干净、不占坑 | SQL 删除 | ⭐⭐⭐⭐⭐ |
| 3 | 僵尸消费者 recovery2 | `XGROUP DELCONSUMER` | 消费者组干净 | 一条命令 | ⭐⭐⭐⭐ |
| 4 | 已完成消息不 ACK | 手动 ACK 残留 pending | 停止重跑、省算力 | Redis 命令 | ⭐⭐⭐⭐ |
| 5 | Redis 不 XTRIM | 定时清理 / 设 maxlen | 防内存满 | 脚本或定时 | ⭐⭐⭐ |
| 6 | mp4 缺 image2text | 配模型或不传视频 | 视频不再失败 | 配模型 | ⭐⭐⭐ |
| 7 | embedding 9 倍波动 | 查 embedding 服务负载 | 耗时可预测 | 排查 | ⭐⭐⭐ |
| 8 | ACK 时序缺陷 | 改源码加幂等 | 根除重跑 | 需开发 | ⭐⭐ |
| 9 | 缺可观测 | 开 Jaeger/OTel | 精确测耗时 | 部署配置 | ⭐⭐ |

---

## 二、立即可做（运维配置，不改代码）

### 1. 加 common worker（收益最高）
**问题**：common 队列只有 1 个 worker，批量上传全挤单车道。
**方案**：编辑部署目录 docker-compose.yml，command 里加 `--workers=3`，重启容器：
```bash
docker compose -f docker/docker-compose.yml up -d --force-recreate ragflow-cpu
```
**收益**：3 个 worker 并行消费，批量上传吞吐 ×3（理论），解决"批量卡死"最直接。
**风险**：需重启、短暂中断；OCR 是 CPU 密集，先看资源 `docker stats docker-ragflow-cpu-1`，建议从 2 个开始。

### 2. 清理 43 天僵尸工单
**问题**：progress=0 的老工单积压 43 天，占队列位置。
**方案**：先查后删：
```sql
-- 先看：对应哪些文档、积了多久
SELECT id, doc_id, begin_at, TIMESTAMPDIFF(MINUTE, begin_at, NOW()) AS age_min
FROM task WHERE progress=0 AND begin_at IS NOT NULL ORDER BY begin_at ASC;
-- 确认后删（只删积压超 7 天的）
DELETE FROM task WHERE progress=0 AND begin_at < DATE_SUB(NOW(), INTERVAL 7 DAY);
```
**收益**：队列干净，新工单不被僵尸挤。
**风险**：删除不可逆，务必先 SELECT 确认 + 跟 leader 对齐这些文档是否还需要。

### 3. 清理僵尸消费者 recovery2
**问题**：recovery2 进程已死但消费者记录残留。
**方案**：
```bash
docker exec docker-redis-1 redis-cli -a infini_rag_flow -n 1 XGROUP DELCONSUMER te.0.common rag_flow_svr_task_broker task_executor_common_recovery2
```
**收益**：消费者组干净，排查时不被干扰。
**风险**：零。recovery2 已无进程，删除纯清理。

### 4. 手动 ACK 残留 pending 消息
**问题**：已 progress=1 但 Redis 消息没 ACK，会被重投重跑。
**方案**：
```bash
# 看 pending 列表
docker exec docker-redis-1 redis-cli -a infini_rag_flow -n 1 XPENDING te.0.common rag_flow_svr_task_broker - + 10
# 对已完成的逐条 ACK
docker exec docker-redis-1 redis-cli -a infini_rag_flow -n 1 XACK te.0.common rag_flow_svr_task_broker <消息ID>
```
**收益**：停止已完成任务被重跑，省 OCR+embedding 算力。
**风险**：ACK 前先确认对应 task 在 MySQL 里 progress=1，别 ACK 正在跑的（会丢）。

### 5. 定期清理 Redis Stream
**问题**：RAGFlow 不主动 XTRIM，XLEN 持续涨，maxmemory 128mb 迟早满。
**方案**：定期跑或加 crontab：
```bash
docker exec docker-redis-1 redis-cli -a infini_rag_flow -n 1 XTRIM te.0.common MAXLEN 10000
```
更稳妥是同时调大 Redis maxmemory（改 docker-compose-base.yml 的 --maxmemory）。
**收益**：防 Redis 内存满导致写入失败。
**风险**：MAXLEN 不会删 pending（未 ACK 的），只删已处理的历史消息，安全。

### 6. 修 mp4 视频失败
**问题**：视频文档因缺 image2text 模型必然失败。
**方案**：二选一——
- 需要解析视频/图片：web 系统设置配多模态模型（如 Qwen-VL）作 image2text。
- 不需要：上传规范禁止 mp4，或上传前转文本。
**收益**：视频文档不再 100% 失败。
**风险**：配模型需可用多模态服务。

---

## 三、需开发/协调（投入大但治本）

### 7. 排查 embedding 服务 9 倍波动
**问题**：同样 17 chunks，embedding 6.4s↔57.66s，波动 9 倍。
**方案**：查 172.24.0.1:18001 这个 embedding 服务——
- 看日志、并发能力、是否有排队。
- 看 GPU/CPU 利用率，是否被别的任务抢占。
- 看 batch size 配置，可能小 batch 快、大 batch 排队慢。
- 必要时单独加资源或换更稳的部署。
**收益**：耗时可预测，批量时不至于某几个文档突然拖几十秒。
**风险**：需进 embedding 服务运维，可能涉及资源扩容。

### 8. 修 ACK 时序缺陷（治本，需改源码）
**问题**：set_progress(1.0) 写库后、ack() 前崩溃 → 已完成任务被重跑。
**方案**（由轻到重）——
- 最轻：do_handle_task 开头加幂等检查，取到任务时若 progress 已=1 则直接 ack 跳过。
- 中等：调整时序先 ack 再处理（失去重试保证，不推荐）。
- 重：改成"处理前 ACK + 失败重投"模型，需重构。
**收益**：根除已完成任务被重跑，省算力、状态一致。
**风险**：需改 RAGFlow 源码，影响核心流程，建议提 issue 给官方而非自己改（改了不好升级）。

### 9. 开 Jaeger/OTel 可观测
**问题**：现在靠手工看 progress_msg 时间戳，精度秒级、费眼。
**方案**：改 service_conf.yaml 的 otel.enable: true，起 jaeger 容器（compose 已有定义），看 http://服务器:16686 的 trace。
**收益**：毫秒级看每一步耗时，长期可观测，不用每次手敲 SQL。
**风险**：部署配置工作量中等；OTel 有采样性能开销（sample_ratio 可调低）。

---

## 四、建议执行顺序

```
第一批（今天，零成本高收益）：
  2 清僵尸工单 → 3 清僵尸消费者 → 4 手动ACK残留
第二批（本周，需协调重启）：
  1 加 worker 到 2~3 个
第三批（持续）：
  5 定期XTRIM、6 配image2text、9 开Jaeger
第四批（治本，提issue）：
  7 查embedding服务、8 报ACK缺陷给官方
```

第一批全是清理操作、风险最低、立刻见效，建议今天就申请做。第二批是解决批量卡死的关键，需重启挑低峰。第四批给官方的改进建议，提了就算贡献。
