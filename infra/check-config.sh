#!/usr/bin/env bash
set -euo pipefail

DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-.env}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
CHECK_CONFIG_TIMEOUT_SECONDS="${CHECK_CONFIG_TIMEOUT_SECONDS:-60}"
CHECK_CONFIG_ENV_KEYS='^(GOOGLE_CLOUD_PROJECT|GOOGLE_CLOUD_REGION|ADK_AGENT_ENGINE_ID)$'

trim_whitespace() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

load_check_env() {
  local env_file="$1"
  local line line_number=0 key value first_character last_character

  [[ -f "${env_file}" ]] || return 0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line_number=$((line_number + 1))
    line="${line%$'\r'}"
    line="$(trim_whitespace "${line}")"
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    if [[ "${line}" == export[[:space:]]* ]]; then
      line="$(trim_whitespace "${line#export}")"
    fi
    if [[ "${line}" != *=* ]]; then
      printf '%s:%s: expected KEY=VALUE\n' "${env_file}" "${line_number}" >&2
      exit 2
    fi

    key="$(trim_whitespace "${line%%=*}")"
    if [[ ! "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      printf '%s:%s: invalid environment variable name\n' "${env_file}" "${line_number}" >&2
      exit 2
    fi
    [[ "${key}" =~ ${CHECK_CONFIG_ENV_KEYS} ]] || continue
    [[ -v "${key}" ]] && continue

    value="$(trim_whitespace "${line#*=}")"
    if [[ -n "${value}" ]]; then
      first_character="${value:0:1}"
      last_character="${value: -1}"
      if [[ "${first_character}" == "'" || "${first_character}" == '"' ]]; then
        if [[ "${last_character}" != "${first_character}" ]]; then
          printf '%s:%s: unterminated quoted value for %s\n' \
            "${env_file}" "${line_number}" "${key}" >&2
          exit 2
        fi
        value="${value:1:${#value}-2}"
      fi
    fi
    printf -v "${key}" '%s' "${value}"
    export "${key}"
  done <"${env_file}"
}

load_check_env "${DEPLOY_ENV_FILE}"

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
: "${GOOGLE_CLOUD_REGION:?Set GOOGLE_CLOUD_REGION}"
: "${ADK_AGENT_ENGINE_ID:?Set ADK_AGENT_ENGINE_ID}"

if [[ ! "${ADK_AGENT_ENGINE_ID}" =~ ^[0-9]+$ ]]; then
  printf 'ADK_AGENT_ENGINE_ID must be the numeric Reasoning Engine resource ID.\n' >&2
  exit 2
fi
if [[ ! "${CHECK_CONFIG_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]]; then
  printf 'CHECK_CONFIG_TIMEOUT_SECONDS must be a positive integer.\n' >&2
  exit 2
fi
if [[ ! -x "${PYTHON_BIN}" ]]; then
  printf 'Python executable not found: %s\n' "${PYTHON_BIN}" >&2
  exit 2
fi

export GOOGLE_CLOUD_QUOTA_PROJECT="${GOOGLE_CLOUD_PROJECT}"

timeout "${CHECK_CONFIG_TIMEOUT_SECONDS}" "${PYTHON_BIN}" - <<'PY'
import os

import vertexai
from vertexai import agent_engines


project = os.environ["GOOGLE_CLOUD_PROJECT"]
location = os.environ["GOOGLE_CLOUD_REGION"]
engine_id = os.environ["ADK_AGENT_ENGINE_ID"]

vertexai.init(project=project, location=location)
engine = agent_engines.get(engine_id)
expected_suffix = f"/locations/{location}/reasoningEngines/{engine_id}"
if not engine.resource_name.endswith(expected_suffix):
    raise SystemExit(
        "Agent Engine resource mismatch: "
        f"expected suffix {expected_suffix!r}, got {engine.resource_name!r}"
    )

print(f"project={project}")
print(f"location={location}")
print(f"engine_id={engine_id}")
print(f"display_name={engine.display_name!r}")
print(f"resource={engine.resource_name}")
print(f"created={engine.create_time}")
print("AGENT_ENGINE_VERIFIED=true")
PY
