#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
: "${GOOGLE_CLOUD_REGION:?Set GOOGLE_CLOUD_REGION}"
: "${FIRESTORE_DATABASE:=(default)}"
: "${FIRESTORE_LOCATION:?Set FIRESTORE_LOCATION}"
: "${MEDIA_BUCKET:?Set MEDIA_BUCKET}"
: "${GEMINI_MODEL_ID:?Set GEMINI_MODEL_ID}"
: "${GEMINI_LOCATION:?Set GEMINI_LOCATION}"
: "${AUTH_ISSUER:?Set AUTH_ISSUER}"
: "${AUTH_AUDIENCE:?Set AUTH_AUDIENCE}"

DEPLOY_ENVIRONMENT="${DEPLOY_ENVIRONMENT:-staging}"
DEPLOY_DRY_RUN="${DEPLOY_DRY_RUN:-false}"
ALLOW_DIRTY_DEPLOY="${ALLOW_DIRTY_DEPLOY:-false}"
FIREBASE_CLI_VERSION="${FIREBASE_CLI_VERSION:-15.26.0}"
API_SERVICE="${API_SERVICE:-oga-api-${DEPLOY_ENVIRONMENT}}"
WORKER_SERVICE="${WORKER_SERVICE:-oga-worker-${DEPLOY_ENVIRONMENT}}"
API_CPU="${API_CPU:-1}"
API_MEMORY="${API_MEMORY:-1Gi}"
WORKER_CPU="${WORKER_CPU:-1}"
WORKER_MEMORY="${WORKER_MEMORY:-1Gi}"
ARTIFACT_REPOSITORY="${ARTIFACT_REPOSITORY:-oga-foreman}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short=12 HEAD)}"
SITE_EVENTS_TOPIC="${PUBSUB_SITE_EVENTS_TOPIC:-oga-site-events-${DEPLOY_ENVIRONMENT}}"
DEAD_LETTER_TOPIC="${PUBSUB_DEAD_LETTER_TOPIC:-oga-dead-letter-${DEPLOY_ENVIRONMENT}}"
WORKER_SUBSCRIPTION="${PUBSUB_WORKER_SUBSCRIPTION:-oga-worker-${DEPLOY_ENVIRONMENT}}"
DEAD_LETTER_SUBSCRIPTION="${DEAD_LETTER_SUBSCRIPTION:-oga-dead-letter-inspection-${DEPLOY_ENVIRONMENT}}"
API_SERVICE_ACCOUNT="${API_SERVICE_ACCOUNT:-oga-api-${DEPLOY_ENVIRONMENT}}"
WORKER_SERVICE_ACCOUNT="${WORKER_SERVICE_ACCOUNT:-oga-worker-${DEPLOY_ENVIRONMENT}}"
PUSH_SERVICE_ACCOUNT="${PUSH_SERVICE_ACCOUNT:-oga-push-${DEPLOY_ENVIRONMENT}}"
SCHEDULE_PROJECT_ID="${SCHEDULE_PROJECT_ID:-}"
SCHEDULE_TIMEZONE="${SCHEDULE_TIMEZONE:-Africa/Accra}"
SCHEDULE_CRON="${SCHEDULE_CRON:-0 6 * * *}"
SCHEDULE_JOB="${SCHEDULE_JOB:-oga-daily-brief-${DEPLOY_ENVIRONMENT}}"

API_SERVICE_ACCOUNT_EMAIL="${API_SERVICE_ACCOUNT}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
WORKER_SERVICE_ACCOUNT_EMAIL="${WORKER_SERVICE_ACCOUNT}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
PUSH_SERVICE_ACCOUNT_EMAIL="${PUSH_SERVICE_ACCOUNT}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
IMAGE_URI="${GOOGLE_CLOUD_REGION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/${ARTIFACT_REPOSITORY}/oga-foreman:${IMAGE_TAG}"

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
  run gcloud projects add-iam-policy-binding "${GOOGLE_CLOUD_PROJECT}" \
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
create_service_account "${PUSH_SERVICE_ACCOUNT}" "Oga Foreman push invoker ${DEPLOY_ENVIRONMENT}"

for role in roles/datastore.user roles/storage.objectAdmin roles/pubsub.publisher roles/logging.logWriter roles/cloudtrace.agent; do
  grant_project_role "serviceAccount:${API_SERVICE_ACCOUNT_EMAIL}" "${role}"
done
for role in roles/datastore.user roles/storage.objectViewer roles/pubsub.publisher roles/aiplatform.user roles/logging.logWriter roles/cloudtrace.agent; do
  grant_project_role "serviceAccount:${WORKER_SERVICE_ACCOUNT_EMAIL}" "${role}"
done

run gcloud iam service-accounts add-iam-policy-binding "${API_SERVICE_ACCOUNT_EMAIL}" \
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

ENV_FILE="$(mktemp)"
trap 'rm -f "${ENV_FILE}"' EXIT
cat >"${ENV_FILE}" <<EOF
OGA_ENV: '${DEPLOY_ENVIRONMENT}'
DEMO_MODE: 'false'
USE_FAKE_MODEL: 'false'
DEFAULT_PROJECT_TIMEZONE: '${SCHEDULE_TIMEZONE}'
GOOGLE_CLOUD_PROJECT: '${GOOGLE_CLOUD_PROJECT}'
GOOGLE_CLOUD_REGION: '${GOOGLE_CLOUD_REGION}'
FIRESTORE_DATABASE: '${FIRESTORE_DATABASE}'
MEDIA_BUCKET: '${MEDIA_BUCKET}'
PUBSUB_SITE_EVENTS_TOPIC: '${SITE_EVENTS_TOPIC}'
PUBSUB_DEAD_LETTER_TOPIC: '${DEAD_LETTER_TOPIC}'
PUBSUB_WORKER_SUBSCRIPTION: '${WORKER_SUBSCRIPTION}'
GEMINI_MODEL_ID: '${GEMINI_MODEL_ID}'
GEMINI_LOCATION: '${GEMINI_LOCATION}'
AUTH_ISSUER: '${AUTH_ISSUER}'
AUTH_AUDIENCE: '${AUTH_AUDIENCE}'
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

if [[ "${DEPLOY_DRY_RUN}" == "true" ]]; then
  WORKER_URL="https://${WORKER_SERVICE}.invalid"
  PROJECT_NUMBER="000000000000"
else
  WORKER_URL="$(gcloud run services describe "${WORKER_SERVICE}" \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --region "${GOOGLE_CLOUD_REGION}" \
    --format='value(status.url)')"
  PROJECT_NUMBER="$(gcloud projects describe "${GOOGLE_CLOUD_PROJECT}" \
    --format='value(projectNumber)')"
fi

run gcloud run services add-iam-policy-binding "${WORKER_SERVICE}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_REGION}" \
  --member "serviceAccount:${PUSH_SERVICE_ACCOUNT_EMAIL}" \
  --role roles/run.invoker \
  --quiet

PUBSUB_SERVICE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
run gcloud iam service-accounts add-iam-policy-binding "${PUSH_SERVICE_ACCOUNT_EMAIL}" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --member "serviceAccount:${PUBSUB_SERVICE_AGENT}" \
  --role roles/iam.serviceAccountTokenCreator \
  --quiet
run gcloud pubsub topics add-iam-policy-binding "${DEAD_LETTER_TOPIC}" \
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
run gcloud pubsub subscriptions add-iam-policy-binding "${WORKER_SUBSCRIPTION}" \
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
      --headers Content-Type=application/json \
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
  printf 'API_URL=%s\nWORKER_URL=%s\nIMAGE_URI=%s\n' "${API_URL}" "${WORKER_URL}" "${IMAGE_URI}"
fi
