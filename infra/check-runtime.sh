#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-${ROOT_DIR}/.env}"
PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"
CHECK_CONFIG_SCRIPT="${CHECK_CONFIG_SCRIPT:-${SCRIPT_DIR}/check-config.sh}"
RUNTIME_CHECK_HELPER="${RUNTIME_CHECK_HELPER:-${ROOT_DIR}/scripts/check_adk_runtime.py}"
CHECK_RUNTIME_TIMEOUT_SECONDS="${CHECK_RUNTIME_TIMEOUT_SECONDS:-300}"

if [[ ! "${CHECK_RUNTIME_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]]; then
  printf 'CHECK_RUNTIME_TIMEOUT_SECONDS must be a positive integer.\n' >&2
  exit 2
fi
if [[ ! -x "${PYTHON_BIN}" ]]; then
  printf 'Python executable not found: %s\n' "${PYTHON_BIN}" >&2
  exit 2
fi
if [[ ! -x "${CHECK_CONFIG_SCRIPT}" ]]; then
  printf 'Configuration checker is not executable: %s\n' "${CHECK_CONFIG_SCRIPT}" >&2
  exit 2
fi
if [[ ! -f "${RUNTIME_CHECK_HELPER}" ]]; then
  printf 'ADK runtime checker not found: %s\n' "${RUNTIME_CHECK_HELPER}" >&2
  exit 2
fi

export DEPLOY_ENV_FILE PYTHON_BIN
"${CHECK_CONFIG_SCRIPT}"

runtime_state_file="$(mktemp "${TMPDIR:-/tmp}/oga-adk-runtime.XXXXXX")"
cleanup_needed=true

run_runtime_phase() {
  local phase="$1" status=0
  printf 'runtime_phase=%s\n' "${phase}"
  timeout "${CHECK_RUNTIME_TIMEOUT_SECONDS}" "${PYTHON_BIN}" \
    "${RUNTIME_CHECK_HELPER}" "${phase}" \
    --env-file "${DEPLOY_ENV_FILE}" \
    --state-file "${runtime_state_file}" || status=$?
  if [[ "${status}" -eq 124 ]]; then
    printf 'ADK runtime phase timed out: %s (%ss).\n' \
      "${phase}" "${CHECK_RUNTIME_TIMEOUT_SECONDS}" >&2
  elif [[ "${status}" -ne 0 ]]; then
    printf 'ADK runtime phase failed: %s (exit %s).\n' "${phase}" "${status}" >&2
  fi
  return "${status}"
}

best_effort_cleanup() {
  local cleanup_status=0
  if [[ "${cleanup_needed}" == true && -s "${runtime_state_file}" ]]; then
    printf 'runtime_phase=cleanup_after_failure\n' >&2
    timeout "${CHECK_RUNTIME_TIMEOUT_SECONDS}" "${PYTHON_BIN}" \
      "${RUNTIME_CHECK_HELPER}" cleanup \
      --env-file "${DEPLOY_ENV_FILE}" \
      --state-file "${runtime_state_file}" || cleanup_status=$?
    if [[ "${cleanup_status}" -eq 0 ]]; then
      rm -f "${runtime_state_file}"
    else
      printf 'Warning: temporary ADK runtime session cleanup failed (exit %s).\n' \
        "${cleanup_status}" >&2
      printf 'Runtime state retained for cleanup: %s\n' "${runtime_state_file}" >&2
    fi
  else
    rm -f "${runtime_state_file}"
  fi
}
trap best_effort_cleanup EXIT

run_runtime_phase pause

# A separate interpreter reconstructs the Runner and Vertex session service.
run_runtime_phase resume

run_runtime_phase cleanup

cleanup_needed=false
rm -f "${runtime_state_file}"
trap - EXIT
printf 'ADK_RUNTIME_E2E_VERIFIED=true\n'
