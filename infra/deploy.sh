#!/usr/bin/env bash
set -euo pipefail

DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-.env}"
DEPLOY_ENV_KEYS='^(GOOGLE_CLOUD_PROJECT|GOOGLE_CLOUD_REGION|FIRESTORE_DATABASE|FIRESTORE_LOCATION|MEDIA_BUCKET|BACKUP_BUCKET|GEMINI_MODEL_ID|GEMINI_LOCATION|AUTH_ISSUER|AUTH_AUDIENCE|CORS_ALLOWED_ORIGINS|NEXT_PUBLIC_API_BASE_URL|NEXT_PUBLIC_FIREBASE_API_KEY|NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN|NEXT_PUBLIC_FIREBASE_PROJECT_ID|NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET|NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID|NEXT_PUBLIC_FIREBASE_APP_ID|DEPLOY_ENVIRONMENT|DEPLOY_DRY_RUN|FIREBASE_CLI_VERSION|API_SERVICE|WORKER_SERVICE|WEB_SERVICE|API_CPU|API_MEMORY|WORKER_CPU|WORKER_MEMORY|WEB_CPU|WEB_MEMORY|ARTIFACT_REPOSITORY|IMAGE_TAG|PUBSUB_SITE_EVENTS_TOPIC|PUBSUB_DEAD_LETTER_TOPIC|PUBSUB_WORKER_SUBSCRIPTION|DEAD_LETTER_SUBSCRIPTION|API_SERVICE_ACCOUNT|WORKER_SERVICE_ACCOUNT|WEB_SERVICE_ACCOUNT|PUSH_SERVICE_ACCOUNT|SCHEDULE_PROJECT_ID|SCHEDULE_TIMEZONE|SCHEDULE_CRON|SCHEDULE_JOB|BUILD_SERVICE_ACCOUNT_EMAIL)$'

trim_whitespace() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

load_deploy_env() {
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
    [[ "${key}" =~ ${DEPLOY_ENV_KEYS} ]] || continue
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

load_deploy_env "${DEPLOY_ENV_FILE}"

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
: "${GOOGLE_CLOUD_REGION:?Set GOOGLE_CLOUD_REGION}"
: "${FIRESTORE_DATABASE:=(default)}"
: "${FIRESTORE_LOCATION:?Set FIRESTORE_LOCATION}"
: "${MEDIA_BUCKET:?Set MEDIA_BUCKET}"
: "${GEMINI_MODEL_ID:?Set GEMINI_MODEL_ID}"
: "${GEMINI_LOCATION:?Set GEMINI_LOCATION}"
: "${AUTH_ISSUER:?Set AUTH_ISSUER}"
: "${AUTH_AUDIENCE:?Set AUTH_AUDIENCE}"
: "${CORS_ALLOWED_ORIGINS:?Set CORS_ALLOWED_ORIGINS as a JSON origin list}"
: "${NEXT_PUBLIC_API_BASE_URL:?Set NEXT_PUBLIC_API_BASE_URL}"
: "${NEXT_PUBLIC_FIREBASE_API_KEY:?Set NEXT_PUBLIC_FIREBASE_API_KEY}"
: "${NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN:?Set NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN}"
: "${NEXT_PUBLIC_FIREBASE_PROJECT_ID:?Set NEXT_PUBLIC_FIREBASE_PROJECT_ID}"
: "${NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET:?Set NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET}"
: "${NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID:?Set NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID}"
: "${NEXT_PUBLIC_FIREBASE_APP_ID:?Set NEXT_PUBLIC_FIREBASE_APP_ID}"
export GOOGLE_CLOUD_QUOTA_PROJECT="${GOOGLE_CLOUD_PROJECT}"
BACKUP_BUCKET="${BACKUP_BUCKET:-${GOOGLE_CLOUD_PROJECT}-oga-backups}"

DEPLOY_ENVIRONMENT="${DEPLOY_ENVIRONMENT:-staging}"
DEPLOY_DRY_RUN="${DEPLOY_DRY_RUN:-false}"
ALLOW_DIRTY_DEPLOY="${ALLOW_DIRTY_DEPLOY:-false}"
FIREBASE_CLI_VERSION="${FIREBASE_CLI_VERSION:-15.26.0}"
API_SERVICE="${API_SERVICE:-oga-api-${DEPLOY_ENVIRONMENT}}"
WORKER_SERVICE="${WORKER_SERVICE:-oga-worker-${DEPLOY_ENVIRONMENT}}"
WEB_SERVICE="${WEB_SERVICE:-oga-web}"
API_CPU="${API_CPU:-1}"
API_MEMORY="${API_MEMORY:-1Gi}"
WORKER_CPU="${WORKER_CPU:-1}"
WORKER_MEMORY="${WORKER_MEMORY:-1Gi}"
WEB_CPU="${WEB_CPU:-1}"
WEB_MEMORY="${WEB_MEMORY:-512Mi}"
ARTIFACT_REPOSITORY="${ARTIFACT_REPOSITORY:-oga-foreman}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short=12 HEAD)}"
SITE_EVENTS_TOPIC="${PUBSUB_SITE_EVENTS_TOPIC:-oga-site-events-${DEPLOY_ENVIRONMENT}}"
DEAD_LETTER_TOPIC="${PUBSUB_DEAD_LETTER_TOPIC:-oga-dead-letter-${DEPLOY_ENVIRONMENT}}"
WORKER_SUBSCRIPTION="${PUBSUB_WORKER_SUBSCRIPTION:-oga-worker-${DEPLOY_ENVIRONMENT}}"
DEAD_LETTER_SUBSCRIPTION="${DEAD_LETTER_SUBSCRIPTION:-oga-dead-letter-inspection-${DEPLOY_ENVIRONMENT}}"
API_SERVICE_ACCOUNT="${API_SERVICE_ACCOUNT:-oga-api-${DEPLOY_ENVIRONMENT}}"
WORKER_SERVICE_ACCOUNT="${WORKER_SERVICE_ACCOUNT:-oga-worker-${DEPLOY_ENVIRONMENT}}"
WEB_SERVICE_ACCOUNT="${WEB_SERVICE_ACCOUNT:-oga-web-${DEPLOY_ENVIRONMENT}}"
PUSH_SERVICE_ACCOUNT="${PUSH_SERVICE_ACCOUNT:-oga-push-${DEPLOY_ENVIRONMENT}}"
SCHEDULE_PROJECT_ID="${SCHEDULE_PROJECT_ID:-}"
SCHEDULE_TIMEZONE="${SCHEDULE_TIMEZONE:-Africa/Accra}"
SCHEDULE_CRON="${SCHEDULE_CRON:-0 6 * * *}"
SCHEDULE_JOB="${SCHEDULE_JOB:-oga-daily-brief-${DEPLOY_ENVIRONMENT}}"

API_SERVICE_ACCOUNT_EMAIL="${API_SERVICE_ACCOUNT}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
WORKER_SERVICE_ACCOUNT_EMAIL="${WORKER_SERVICE_ACCOUNT}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
WEB_SERVICE_ACCOUNT_EMAIL="${WEB_SERVICE_ACCOUNT}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
PUSH_SERVICE_ACCOUNT_EMAIL="${PUSH_SERVICE_ACCOUNT}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
IMAGE_URI="${GOOGLE_CLOUD_REGION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/${ARTIFACT_REPOSITORY}/oga-foreman:${IMAGE_TAG}"
WEB_IMAGE_URI="${GOOGLE_CLOUD_REGION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/${ARTIFACT_REPOSITORY}/oga-web:${IMAGE_TAG}"

if [[ "${FIRESTORE_DATABASE}" != "(default)" ]]; then
  printf 'infra/deploy.sh currently deploys Firebase rules for the (default) Firestore database only.\n' >&2
  exit 2
fi
if [[ "${DEPLOY_DRY_RUN}" != "true" && "${ALLOW_DIRTY_DEPLOY}" != "true" ]] && \
  [[ -n "$(git status --porcelain)" ]]; then
  printf 'Refusing cloud deployment from a dirty worktree. Commit the reviewed revision first.\n' >&2
  exit 2
fi

run() {
  if [[ "${DEPLOY_DRY_RUN}" == "true" ]]; then
    printf 'DRY RUN:'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

run_with_transient_retry() {
  if [[ "${DEPLOY_DRY_RUN}" == "true" ]]; then
    run "$@"
    return 0
  fi

  local attempt=1 delay_seconds=2 output status
  while true; do
    if output="$("$@" 2>&1)"; then
      [[ -z "${output}" ]] || printf '%s\n' "${output}"
      return 0
    else
      status=$?
    fi
    if ((attempt >= 6)) || \
      [[ "${output}" != *conflict* && "${output}" != *ABORTED* && "${output}" != *ETag* ]]; then
      printf '%s\n' "${output}" >&2
      return "${status}"
    fi
    printf 'Transient IAM conflict; retrying in %ss (attempt %s/6).\n' \
      "${delay_seconds}" "${attempt}" >&2
    sleep "${delay_seconds}"
    attempt=$((attempt + 1))
    delay_seconds=$((delay_seconds * 2))
  done
}

exists() {
  if [[ "${DEPLOY_DRY_RUN}" == "true" ]]; then
    return 1
  fi
  "$@" >/dev/null 2>&1
}

create_service_account() {
  local account="$1"
  local display_name="$2"
  if ! exists gcloud iam service-accounts describe \
    "${account}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com" \
    --project "${GOOGLE_CLOUD_PROJECT}"; then
    run gcloud iam service-accounts create "${account}" \
      --project "${GOOGLE_CLOUD_PROJECT}" \
      --display-name "${display_name}"
  fi
}

grant_project_role() {
  local member="$1"
  local role="$2"
  run_with_transient_retry gcloud projects add-iam-policy-binding "${GOOGLE_CLOUD_PROJECT}" \
    --member "${member}" \
    --role "${role}" \
    --condition=None \
    --quiet
}

create_topic() {
  local topic="$1"
  if ! exists gcloud pubsub topics describe "${topic}" --project "${GOOGLE_CLOUD_PROJECT}"; then
    run gcloud pubsub topics create "${topic}" --project "${GOOGLE_CLOUD_PROJECT}"
  fi
}

firebase_project_exists() {
  if [[ "${DEPLOY_DRY_RUN}" == "true" ]]; then
    return 1
  fi
  npx --yes "firebase-tools@${FIREBASE_CLI_VERSION}" projects:list --json | \
    python3 -c '
import json
import sys

project_id = sys.argv[1]
payload = json.load(sys.stdin)
projects = payload.get("result", []) if isinstance(payload, dict) else []
raise SystemExit(0 if any(item.get("projectId") == project_id for item in projects) else 1)
' "${GOOGLE_CLOUD_PROJECT}"
}

run gcloud config set project "${GOOGLE_CLOUD_PROJECT}"
run gcloud services enable \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com \
  firebase.googleapis.com \
  firebaserules.googleapis.com \
  firestore.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  identitytoolkit.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  pubsub.googleapis.com \
  run.googleapis.com \
  storage.googleapis.com \
  cloudtrace.googleapis.com \
  --project "${GOOGLE_CLOUD_PROJECT}"

if ! firebase_project_exists; then
  run npx --yes "firebase-tools@${FIREBASE_CLI_VERSION}" projects:addfirebase \
    "${GOOGLE_CLOUD_PROJECT}" \
    --non-interactive
fi

if [[ "${DEPLOY_DRY_RUN}" == "true" ]]; then
  PROJECT_NUMBER="000000000000"
else
  PROJECT_NUMBER="$(gcloud projects describe "${GOOGLE_CLOUD_PROJECT}" \
    --format='value(projectNumber)')"
fi

if [[ -z "${BUILD_SERVICE_ACCOUNT_EMAIL:-}" ]]; then
  if [[ "${DEPLOY_DRY_RUN}" == "true" ]]; then
    BUILD_SERVICE_ACCOUNT_EMAIL="000000000000-compute@developer.gserviceaccount.com"
  else
    BUILD_SERVICE_ACCOUNT_EMAIL="$(gcloud builds get-default-service-account \
      --project "${GOOGLE_CLOUD_PROJECT}" \
      --format='value(serviceAccountEmail)')"
  fi
fi
if [[ -z "${BUILD_SERVICE_ACCOUNT_EMAIL}" ]]; then
  printf 'Cloud Build did not return a default service account.\n' >&2
  exit 2
fi
for role in roles/storage.objectViewer roles/artifactregistry.writer roles/logging.logWriter; do
  grant_project_role "serviceAccount:${BUILD_SERVICE_ACCOUNT_EMAIL}" "${role}"
done

create_service_account "${API_SERVICE_ACCOUNT}" "Oga Foreman API ${DEPLOY_ENVIRONMENT}"
create_service_account "${WORKER_SERVICE_ACCOUNT}" "Oga Foreman worker ${DEPLOY_ENVIRONMENT}"
create_service_account "${WEB_SERVICE_ACCOUNT}" "Oga Foreman web ${DEPLOY_ENVIRONMENT}"
create_service_account "${PUSH_SERVICE_ACCOUNT}" "Oga Foreman push invoker ${DEPLOY_ENVIRONMENT}"

for role in roles/datastore.user roles/storage.objectAdmin roles/pubsub.publisher roles/logging.logWriter roles/cloudtrace.agent; do
  grant_project_role "serviceAccount:${API_SERVICE_ACCOUNT_EMAIL}" "${role}"
done
for role in roles/datastore.user roles/storage.objectViewer roles/pubsub.publisher roles/aiplatform.user roles/logging.logWriter roles/cloudtrace.agent; do
  grant_project_role "serviceAccount:${WORKER_SERVICE_ACCOUNT_EMAIL}" "${role}"
done

run_with_transient_retry gcloud iam service-accounts add-iam-policy-binding "${API_SERVICE_ACCOUNT_EMAIL}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --member "serviceAccount:${API_SERVICE_ACCOUNT_EMAIL}" \
  --role roles/iam.serviceAccountTokenCreator \
  --quiet

if ! exists gcloud firestore databases describe \
  --database "${FIRESTORE_DATABASE}" \
  --project "${GOOGLE_CLOUD_PROJECT}"; then
  run gcloud firestore databases create \
    --database "${FIRESTORE_DATABASE}" \
    --location "${FIRESTORE_LOCATION}" \
    --type firestore-native \
    --delete-protection \
    --project "${GOOGLE_CLOUD_PROJECT}"
else
  run gcloud firestore databases update \
    --database "${FIRESTORE_DATABASE}" \
    --delete-protection \
    --project "${GOOGLE_CLOUD_PROJECT}"
fi

run npx --yes "firebase-tools@${FIREBASE_CLI_VERSION}" deploy \
  --only firestore \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --non-interactive

if [[ "${DEPLOY_DRY_RUN}" == "true" ]] || ! gcloud firestore backups schedules list \
  --database "${FIRESTORE_DATABASE}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --format='value(name)' 2>/dev/null | grep -q .; then
  run gcloud firestore backups schedules create \
    --database "${FIRESTORE_DATABASE}" \
    --recurrence daily \
    --retention 30d \
    --project "${GOOGLE_CLOUD_PROJECT}"
fi

if ! exists gcloud storage buckets describe "gs://${MEDIA_BUCKET}" --project "${GOOGLE_CLOUD_PROJECT}"; then
  run gcloud storage buckets create "gs://${MEDIA_BUCKET}" \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --location "${GOOGLE_CLOUD_REGION}" \
    --uniform-bucket-level-access
fi
run gcloud storage buckets update "gs://${MEDIA_BUCKET}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --versioning \
  --soft-delete-duration 30d
STORAGE_CORS_FILE="$(mktemp)"
trap 'rm -f "${STORAGE_CORS_FILE}"' EXIT
python3 infra/render_storage_cors.py \
  --origins-json "${CORS_ALLOWED_ORIGINS}" \
  --output "${STORAGE_CORS_FILE}"
run gcloud storage buckets update "gs://${MEDIA_BUCKET}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --cors-file="${STORAGE_CORS_FILE}"
rm -f "${STORAGE_CORS_FILE}"
trap - EXIT

if ! exists gcloud storage buckets describe "gs://${BACKUP_BUCKET}" --project "${GOOGLE_CLOUD_PROJECT}"; then
  run gcloud storage buckets create "gs://${BACKUP_BUCKET}" \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --location "${GOOGLE_CLOUD_REGION}" \
    --uniform-bucket-level-access
fi
run gcloud storage buckets update "gs://${BACKUP_BUCKET}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --versioning \
  --soft-delete-duration 30d
run_with_transient_retry gcloud storage buckets add-iam-policy-binding "gs://${BACKUP_BUCKET}" \
  --member "serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-firestore.iam.gserviceaccount.com" \
  --role roles/storage.admin

create_topic "${SITE_EVENTS_TOPIC}"
create_topic "${DEAD_LETTER_TOPIC}"

if ! exists gcloud artifacts repositories describe "${ARTIFACT_REPOSITORY}" \
  --location "${GOOGLE_CLOUD_REGION}" \
  --project "${GOOGLE_CLOUD_PROJECT}"; then
  run gcloud artifacts repositories create "${ARTIFACT_REPOSITORY}" \
    --location "${GOOGLE_CLOUD_REGION}" \
    --repository-format docker \
    --description "Oga Foreman service images" \
    --project "${GOOGLE_CLOUD_PROJECT}"
fi
run gcloud builds submit \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --service-account "projects/${GOOGLE_CLOUD_PROJECT}/serviceAccounts/${BUILD_SERVICE_ACCOUNT_EMAIL}" \
  --config cloudbuild.yaml \
  --substitutions "_IMAGE_URI=${IMAGE_URI}" \
  .
run gcloud builds submit \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --service-account "projects/${GOOGLE_CLOUD_PROJECT}/serviceAccounts/${BUILD_SERVICE_ACCOUNT_EMAIL}" \
  --config frontend/cloudbuild.yaml \
  --substitutions "_IMAGE_URI=${WEB_IMAGE_URI},_NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL},_NEXT_PUBLIC_FIREBASE_API_KEY=${NEXT_PUBLIC_FIREBASE_API_KEY},_NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=${NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN},_NEXT_PUBLIC_FIREBASE_PROJECT_ID=${NEXT_PUBLIC_FIREBASE_PROJECT_ID},_NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=${NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET},_NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=${NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID},_NEXT_PUBLIC_FIREBASE_APP_ID=${NEXT_PUBLIC_FIREBASE_APP_ID}" \
  .

ENV_FILE="$(mktemp)"
trap 'rm -f "${ENV_FILE}" "${HOSTING_CONFIG:-}"' EXIT
cat >"${ENV_FILE}" <<EOF
OGA_ENV: '${DEPLOY_ENVIRONMENT}'
DEMO_MODE: 'false'
USE_FAKE_MODEL: 'false'
DEFAULT_PROJECT_TIMEZONE: '${SCHEDULE_TIMEZONE}'
GOOGLE_CLOUD_PROJECT: '${GOOGLE_CLOUD_PROJECT}'
GOOGLE_CLOUD_REGION: '${GOOGLE_CLOUD_REGION}'
FIRESTORE_DATABASE: '${FIRESTORE_DATABASE}'
MEDIA_BUCKET: '${MEDIA_BUCKET}'
STORAGE_SIGNING_SERVICE_ACCOUNT: '${API_SERVICE_ACCOUNT_EMAIL}'
PUBSUB_SITE_EVENTS_TOPIC: '${SITE_EVENTS_TOPIC}'
PUBSUB_DEAD_LETTER_TOPIC: '${DEAD_LETTER_TOPIC}'
PUBSUB_WORKER_SUBSCRIPTION: '${WORKER_SUBSCRIPTION}'
GEMINI_MODEL_ID: '${GEMINI_MODEL_ID}'
GEMINI_LOCATION: '${GEMINI_LOCATION}'
AUTH_ISSUER: '${AUTH_ISSUER}'
AUTH_AUDIENCE: '${AUTH_AUDIENCE}'
CORS_ALLOWED_ORIGINS: '${CORS_ALLOWED_ORIGINS}'
EOF

run gcloud run deploy "${WORKER_SERVICE}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}" \
  --image "${IMAGE_URI}" \
  --service-account "${WORKER_SERVICE_ACCOUNT_EMAIL}" \
  --command uvicorn \
  --args app.worker_http:app,--host,0.0.0.0,--port,8080 \
  --env-vars-file "${ENV_FILE}" \
  --ingress internal \
  --no-allow-unauthenticated \
  --execution-environment gen2 \
  --cpu "${WORKER_CPU}" \
  --memory "${WORKER_MEMORY}" \
  --cpu-boost \
  --startup-probe=initialDelaySeconds=0,timeoutSeconds=5,periodSeconds=5,failureThreshold=12,httpGet.port=8080,httpGet.path=/health/ready \
  --liveness-probe=initialDelaySeconds=30,timeoutSeconds=5,periodSeconds=30,failureThreshold=3,httpGet.port=8080,httpGet.path=/health/live \
  --min 0 \
  --max 20 \
  --concurrency 20 \
  --timeout 300
run gcloud run services update-traffic "${WORKER_SERVICE}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}" \
  --to-latest

if [[ "${DEPLOY_DRY_RUN}" == "true" ]]; then
  WORKER_URL="https://${WORKER_SERVICE}.invalid"
else
  WORKER_URL="$(gcloud run services describe "${WORKER_SERVICE}" \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --region "${GOOGLE_CLOUD_REGION}" \
    --format='value(status.url)')"
fi

run_with_transient_retry gcloud run services add-iam-policy-binding "${WORKER_SERVICE}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}" \
  --member "serviceAccount:${PUSH_SERVICE_ACCOUNT_EMAIL}" \
  --role roles/run.invoker \
  --quiet

PUBSUB_SERVICE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
run_with_transient_retry gcloud iam service-accounts add-iam-policy-binding "${PUSH_SERVICE_ACCOUNT_EMAIL}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --member "serviceAccount:${PUBSUB_SERVICE_AGENT}" \
  --role roles/iam.serviceAccountTokenCreator \
  --quiet
run_with_transient_retry gcloud pubsub topics add-iam-policy-binding "${DEAD_LETTER_TOPIC}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --member "serviceAccount:${PUBSUB_SERVICE_AGENT}" \
  --role roles/pubsub.publisher \
  --quiet

if exists gcloud pubsub subscriptions describe "${WORKER_SUBSCRIPTION}" --project "${GOOGLE_CLOUD_PROJECT}"; then
  run gcloud pubsub subscriptions update "${WORKER_SUBSCRIPTION}" \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --push-endpoint "${WORKER_URL}/pubsub/push" \
    --push-auth-service-account "${PUSH_SERVICE_ACCOUNT_EMAIL}" \
    --dead-letter-topic "${DEAD_LETTER_TOPIC}" \
    --max-delivery-attempts 5 \
    --ack-deadline 60
else
  run gcloud pubsub subscriptions create "${WORKER_SUBSCRIPTION}" \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --topic "${SITE_EVENTS_TOPIC}" \
    --push-endpoint "${WORKER_URL}/pubsub/push" \
    --push-auth-service-account "${PUSH_SERVICE_ACCOUNT_EMAIL}" \
    --dead-letter-topic "${DEAD_LETTER_TOPIC}" \
    --max-delivery-attempts 5 \
    --ack-deadline 60 \
    --message-retention-duration 7d
fi
run_with_transient_retry gcloud pubsub subscriptions add-iam-policy-binding "${WORKER_SUBSCRIPTION}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --member "serviceAccount:${PUBSUB_SERVICE_AGENT}" \
  --role roles/pubsub.subscriber \
  --quiet

if ! exists gcloud pubsub subscriptions describe "${DEAD_LETTER_SUBSCRIPTION}" --project "${GOOGLE_CLOUD_PROJECT}"; then
  run gcloud pubsub subscriptions create "${DEAD_LETTER_SUBSCRIPTION}" \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --topic "${DEAD_LETTER_TOPIC}" \
    --message-retention-duration 14d
fi

run gcloud run deploy "${API_SERVICE}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}" \
  --image "${IMAGE_URI}" \
  --service-account "${API_SERVICE_ACCOUNT_EMAIL}" \
  --env-vars-file "${ENV_FILE}" \
  --ingress all \
  --allow-unauthenticated \
  --execution-environment gen2 \
  --cpu "${API_CPU}" \
  --memory "${API_MEMORY}" \
  --cpu-boost \
  --startup-probe=initialDelaySeconds=0,timeoutSeconds=5,periodSeconds=5,failureThreshold=12,httpGet.port=8080,httpGet.path=/health/ready \
  --liveness-probe=initialDelaySeconds=30,timeoutSeconds=5,periodSeconds=30,failureThreshold=3,httpGet.port=8080,httpGet.path=/health/live \
  --min 0 \
  --max 20 \
  --concurrency 40 \
  --timeout 300
run gcloud run services update-traffic "${API_SERVICE}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}" \
  --to-latest

run gcloud run deploy "${WEB_SERVICE}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}" \
  --image "${WEB_IMAGE_URI}" \
  --service-account "${WEB_SERVICE_ACCOUNT_EMAIL}" \
  --ingress all \
  --allow-unauthenticated \
  --execution-environment gen2 \
  --cpu "${WEB_CPU}" \
  --memory "${WEB_MEMORY}" \
  --cpu-boost \
  --startup-probe=initialDelaySeconds=0,timeoutSeconds=5,periodSeconds=5,failureThreshold=12,httpGet.port=8080,httpGet.path=/ \
  --liveness-probe=initialDelaySeconds=30,timeoutSeconds=5,periodSeconds=30,failureThreshold=3,httpGet.port=8080,httpGet.path=/ \
  --min 0 \
  --max 10 \
  --concurrency 80 \
  --timeout 60
run gcloud run services update-traffic "${WEB_SERVICE}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}" \
  --to-latest

HOSTING_CONFIG="$(mktemp .firebase-hosting.XXXXXX.json)"
jq \
  --arg service "${WEB_SERVICE}" \
  --arg region "${GOOGLE_CLOUD_REGION}" \
  '.hosting.rewrites[0].run.serviceId = $service | .hosting.rewrites[0].run.region = $region' \
  firebase.json >"${HOSTING_CONFIG}"
run npx --yes "firebase-tools@${FIREBASE_CLI_VERSION}" deploy \
  --only hosting \
  --config "${HOSTING_CONFIG}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --non-interactive

if [[ -n "${SCHEDULE_PROJECT_ID}" ]]; then
  SCHEDULE_BODY="{\"project_id\":\"${SCHEDULE_PROJECT_ID}\",\"timezone\":\"${SCHEDULE_TIMEZONE}\"}"
  if exists gcloud scheduler jobs describe "${SCHEDULE_JOB}" \
    --location "${GOOGLE_CLOUD_REGION}" \
    --project "${GOOGLE_CLOUD_PROJECT}"; then
    run gcloud scheduler jobs update http "${SCHEDULE_JOB}" \
      --project "${GOOGLE_CLOUD_PROJECT}" \
      --location "${GOOGLE_CLOUD_REGION}" \
      --schedule "${SCHEDULE_CRON}" \
      --time-zone "${SCHEDULE_TIMEZONE}" \
      --uri "${WORKER_URL}/scheduler/daily-brief" \
      --http-method POST \
      --update-headers Content-Type=application/json \
      --message-body "${SCHEDULE_BODY}" \
      --oidc-service-account-email "${PUSH_SERVICE_ACCOUNT_EMAIL}" \
      --oidc-token-audience "${WORKER_URL}"
  else
    run gcloud scheduler jobs create http "${SCHEDULE_JOB}" \
      --project "${GOOGLE_CLOUD_PROJECT}" \
      --location "${GOOGLE_CLOUD_REGION}" \
      --schedule "${SCHEDULE_CRON}" \
      --time-zone "${SCHEDULE_TIMEZONE}" \
      --uri "${WORKER_URL}/scheduler/daily-brief" \
      --http-method POST \
      --headers Content-Type=application/json \
      --message-body "${SCHEDULE_BODY}" \
      --oidc-service-account-email "${PUSH_SERVICE_ACCOUNT_EMAIL}" \
      --oidc-token-audience "${WORKER_URL}"
  fi
fi

if exists gcloud logging metrics describe oga_backup_failure_count --project "${GOOGLE_CLOUD_PROJECT}"; then
  run gcloud logging metrics update oga_backup_failure_count \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --description "Oga backup verification failures" \
    --log-filter 'jsonPayload.event="backup_verification_failed"'
else
  run gcloud logging metrics create oga_backup_failure_count \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --description "Oga backup verification failures" \
    --log-filter 'jsonPayload.event="backup_verification_failed"'
fi

GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT}" \
API_SERVICE="${API_SERVICE}" \
WORKER_SUBSCRIPTION="${WORKER_SUBSCRIPTION}" \
DEAD_LETTER_SUBSCRIPTION="${DEAD_LETTER_SUBSCRIPTION}" \
MONITORING_DRY_RUN="${DEPLOY_DRY_RUN}" \
  "$(dirname "$0")/monitoring/apply.sh"

if [[ "${DEPLOY_DRY_RUN}" != "true" ]]; then
  API_URL="$(gcloud run services describe "${API_SERVICE}" \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --region "${GOOGLE_CLOUD_REGION}" \
    --format='value(status.url)')"
  WEB_URL="$(gcloud run services describe "${WEB_SERVICE}" \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --region "${GOOGLE_CLOUD_REGION}" \
    --format='value(status.url)')"
  printf 'API_URL=%s\nWORKER_URL=%s\nWEB_URL=%s\nIMAGE_URI=%s\nWEB_IMAGE_URI=%s\n' \
    "${API_URL}" "${WORKER_URL}" "${WEB_URL}" "${IMAGE_URI}" "${WEB_IMAGE_URI}"
fi
