#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
: "${GOOGLE_CLOUD_REGION:?Set GOOGLE_CLOUD_REGION}"
: "${API_SERVICE:?Set API_SERVICE}"
: "${WORKER_SERVICE:?Set WORKER_SERVICE}"
: "${API_REVISION:?Set API_REVISION to a verified prior revision}"
: "${WORKER_REVISION:?Set WORKER_REVISION to a verified prior revision}"

ROLLBACK_DRY_RUN="${ROLLBACK_DRY_RUN:-false}"

run() {
  if [[ "${ROLLBACK_DRY_RUN}" == "true" ]]; then
    printf 'DRY RUN:'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

run gcloud run revisions describe "${WORKER_REVISION}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}"
run gcloud run revisions describe "${API_REVISION}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}"

run gcloud run services update-traffic "${WORKER_SERVICE}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}" \
  --to-revisions "${WORKER_REVISION}=100"
run gcloud run services update-traffic "${API_SERVICE}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}" \
  --to-revisions "${API_REVISION}=100"

printf 'Rollback traffic shift requested. Run readiness, event-delivery, and approval-resume smoke checks before closing the incident.\n'
