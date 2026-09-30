#!/bin/bash
# Keep the ingest service alive inside the RAGFlow container.
#
# The service has to run inside docker-ragflow-cpu-1: that is where MySQL,
# Elasticsearch, MinIO and the embedding service are reachable. But a process
# started with `docker exec` does not come back when the container restarts,
# and the container does restart on its own (restart=unless-stopped). So
# something on the host has to notice and start it again — that is this loop.
#
# It only ever runs `docker exec`. It never restarts, recreates, or otherwise
# touches the container: RAGFlow is running in there and is not ours to
# interrupt.

set -u

CONTAINER="${GCN_CONTAINER:-docker-ragflow-cpu-1}"
PORT="${GCN_PORT:-9800}"
INTERVAL="${GCN_CHECK_INTERVAL:-15}"

container_up() {
  [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ]
}

service_up() {
  docker exec "$CONTAINER" pgrep -f 'ingest\.service' >/dev/null 2>&1
}

echo "watching ${CONTAINER} for the ingest service on port ${PORT}, every ${INTERVAL}s"

while true; do
  if ! container_up; then
    echo "${CONTAINER} is not running; waiting (not starting it — not ours)"
  elif ! service_up; then
    echo "ingest service is down; starting it"
    docker exec -d \
      -e GCN_TENANT_ID="${GCN_TENANT_ID}" \
      -e GCN_DB_HOST="${GCN_DB_HOST}" \
      -e GCN_DB_PORT="${GCN_DB_PORT:-3306}" \
      -e GCN_DB_USER="${GCN_DB_USER:-root}" \
      -e GCN_DB_PASSWORD="${GCN_DB_PASSWORD}" \
      -e GCN_DB_NAME="${GCN_DB_NAME:-gcn_ingest}" \
      -e GCN_WARM_KB="${GCN_WARM_KB:-}" \
      -e GCN_MAX_CONCURRENT="${GCN_MAX_CONCURRENT:-3}" \
      -e MINERU_URL="${MINERU_URL:-}" \
      -e PYTHONPATH=/ragflow \
      "$CONTAINER" \
      bash -c "cd /ragflow && exec python -m ingest.service --port ${PORT} >> /tmp/ingest_service.log 2>&1"
  fi
  sleep "$INTERVAL"
done
