#!/bin/bash
# 1 万份稳定性测试 watchdog：进程崩了自动重启。
# 用法：nohup bash /ragflow/ingest/watchdog_10k.sh > /tmp/watchdog.log 2>&1 &
#
LOG=/tmp/bench_10k.log
RESULT_JSON=/tmp/bench_10k.json
CMD="python3 -u /ragflow/ingest/mentor_b_bench.py --kb-id 2f84a97aab4811f1a5be33e620658a1 --docs-dir /ragflow/ingest/_abtest_docs_10k --docs-json /ragflow/ingest/ab_doc_list_10k.json --count 10000 --concurrency 3 --label 10k-c3 --out /tmp/bench_10k.json"
RESTART_FLAG="/tmp/.bench_10k_restarted"

while true; do
  # 1. 检查进程在不在
  PID=$(docker exec docker-ragflow-cpu-1 pgrep -f mentor_b_bench | head -1)
  if [ -n "$PID" ]; then
    # 进程没了，看是否跑完了
    if docker exec docker-ragflow-cpu-1 grep -q "RESULT" "$LOG" || docker exec docker-ragflow-cpu-1 grep -q "saved ->" "$LOG"; then
      echo "$(date) '[watchdog] DONE: 1万份跑完'" >> /tmp/watchdog.log
      exit 0
    fi
    # 没跑完 = 崩了 → 重启
    if [ -f "$RESTART_FLAG" ]; then
      echo "$(date) '[watchdog] already restarted, skip'" >> /tmp/watchdog.log
    else
      touch "$RESTART_FLAG"
      echo "$(date) '[watchdog] CRASH detected, restarting...'" >> /tmp/watchdog.log
      # 拿最后几行日志存证
      docker exec docker-ragflow-cpu-1 tail -3 "$LOG" >> /tmp/watchdog.log
prev
      # 重启
      docker exec -d docker-ragflow-cpu-1 bash -c "cd /ragflow && PYTHONPATH=/ragflow python3 -u /ragflow/ingest/mentor_b_bench.py --kb-id 2f84a97aab4811f1a5be33e6206585a1 --docs-dir /ragflow/ingest/_abtest_docs_10k --docs-json /ragflow/ingest/ab_doc_list_10k.json --count 10000 --concurrency 3 --label 10k-c3-retry --out /tmp/bench_10k.json > /tmp/bench_10k.log 2>&1"
      echo "$(date) '[watchdog] restarted'" >> /tmp/watchdog.log
      # 重启后等 5 分钟再继续监控
    fi
  fi
  echo "$(date) '[watchdog] alive, succeeded log line:" $(docker exec docker-ragflow-cpu-1 grep -c succeeded /tmp/bench_10k.log | wc --l)" >> /tmp/watchdog.log
prev
  sleep 300
done
