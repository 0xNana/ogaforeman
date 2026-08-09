#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:?Usage: infra/smoke-container.sh IMAGE}"
API_PORT="${API_SMOKE_PORT:-18080}"
WORKER_PORT="${WORKER_SMOKE_PORT:-18081}"
API_CONTAINER="oga-api-smoke-$$"
WORKER_CONTAINER="oga-worker-smoke-$$"

cleanup() {
  docker rm --force "${API_CONTAINER}" "${WORKER_CONTAINER}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_for_health() {
  local container="$1"
  local port="$2"
  local attempt
  for attempt in $(seq 1 30); do
    if curl --fail --silent "http://127.0.0.1:${port}/healthz" >/dev/null; then
      return 0
    fi
    if [[ "$(docker inspect --format '{{.State.Running}}' "${container}" 2>/dev/null || true)" != "true" ]]; then
      docker logs "${container}"
      return 1
    fi
    sleep 1
  done
  docker logs "${container}"
  return 1
}

docker run --detach --rm \
  --name "${API_CONTAINER}" \
  --publish "127.0.0.1:${API_PORT}:8080" \
  "${IMAGE}" >/dev/null
wait_for_health "${API_CONTAINER}" "${API_PORT}"
docker rm --force "${API_CONTAINER}" >/dev/null

docker run --detach --rm \
  --name "${WORKER_CONTAINER}" \
  --publish "127.0.0.1:${WORKER_PORT}:8080" \
  --entrypoint uvicorn \
  "${IMAGE}" \
  app.worker_http:app --host 0.0.0.0 --port 8080 >/dev/null
wait_for_health "${WORKER_CONTAINER}" "${WORKER_PORT}"
