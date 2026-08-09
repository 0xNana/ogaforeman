#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
: "${API_SERVICE:?Set API_SERVICE}"
: "${WORKER_SUBSCRIPTION:?Set WORKER_SUBSCRIPTION}"
: "${DEAD_LETTER_SUBSCRIPTION:?Set DEAD_LETTER_SUBSCRIPTION}"

MONITORING_DRY_RUN="${MONITORING_DRY_RUN:-false}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run() {
  if [[ "${MONITORING_DRY_RUN}" == "true" ]]; then
    printf 'DRY RUN:'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

for template in "${SCRIPT_DIR}"/*.json; do
  rendered="$(mktemp)"
  sed \
    -e "s/\${API_SERVICE}/${API_SERVICE}/g" \
    -e "s/\${WORKER_SUBSCRIPTION}/${WORKER_SUBSCRIPTION}/g" \
    -e "s/\${DEAD_LETTER_SUBSCRIPTION}/${DEAD_LETTER_SUBSCRIPTION}/g" \
    "${template}" >"${rendered}"
  display_name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["displayName"])' "${rendered}")"
  if [[ "${MONITORING_DRY_RUN}" == "true" ]]; then
    policy_name=""
  else
    policy_name="$(
      gcloud alpha monitoring policies list \
        --project "${GOOGLE_CLOUD_PROJECT}" \
        --format=json | \
        python3 -c '
import json
import sys

target = sys.argv[1]
matches = [
    item.get("name", "")
    for item in json.load(sys.stdin)
    if item.get("displayName") == target
]
if len(matches) > 1:
    raise SystemExit(f"multiple alert policies matched {target!r}")
print(matches[0] if matches else "")
' "${display_name}"
    )"
  fi
  if [[ -n "${policy_name}" ]]; then
    run gcloud alpha monitoring policies update "${policy_name}" \
      --project "${GOOGLE_CLOUD_PROJECT}" \
      --policy-from-file "${rendered}"
  else
    run gcloud alpha monitoring policies create \
      --project "${GOOGLE_CLOUD_PROJECT}" \
      --policy-from-file "${rendered}"
  fi
  rm -f "${rendered}"
done
