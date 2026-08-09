# Deployment and Environment Guide

## Environments

| Environment | Purpose | Data policy |
| --- | --- | --- |
| Local | Fast development, fake model, optional emulators | Disposable data only |
| Preview | Pull-request/browser integration | Isolated project and identities |
| Staging | Cloud integration, smoke, eval, restore, rollback, demo | Non-production data |
| Production/Beta | Public beta after every release gate passes | Approved retention and access policy |

## Configuration

`app.config.Settings` owns runtime configuration. Deployed environments require
the Google Cloud project/region, Firestore database, Storage bucket, Pub/Sub
resources, Gemini model/location, and authentication issuer/audience. Production
rejects demo and fake-model modes.

Credentials belong in workload identity or Secret Manager. Never commit service
account keys, bearer tokens, or Firebase admin credentials.

The backend container runs as a non-root user. Cloud Run uses `/readyz` for its
startup probe and `/healthz` for liveness; startup therefore verifies deployed
configuration and required Firestore/Storage access before the revision receives
traffic.

The complete human and workload identity boundary is documented in
[AUTH.md](AUTH.md).

### Firebase Authentication

For the Firebase/Identity Platform project matching the deployed environment:

1. add the Google Cloud project to Firebase if it is not already linked;
2. enable the Email/Password provider;
3. add only the approved preview, staging, and production domains;
4. set `AUTH_AUDIENCE` to the Firebase project ID;
5. set `AUTH_ISSUER` to
   `https://securetoken.google.com/<firebase-project-id>`;
6. keep demo mode disabled in every deployed environment.

The backend verifier and frontend session flow use these values. A deploy must
not be treated as an authenticated product launch until the browser and staging
evidence listed in `AUTH.md` passes.

The frontend also requires `NEXT_PUBLIC_FIREBASE_API_KEY`,
`NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`, `NEXT_PUBLIC_FIREBASE_PROJECT_ID`,
`NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET`,
`NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID`, and
`NEXT_PUBLIC_FIREBASE_APP_ID`.

## Local setup

```bash
UV_CACHE_DIR=/tmp/oga-uv-cache uv sync --all-extras --locked
cp .env.example .env
cd frontend && npm ci
```

For Firestore integration:

```bash
npx --yes firebase-tools@15.26.0 emulators:start --only firestore --project oga-foreman-test
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8085
.venv/bin/python -m pytest -q tests/integration/test_firestore_repositories.py
```

Deployed environments must never set `FIRESTORE_EMULATOR_HOST`.

Verify the production image before any cloud mutation:

```bash
docker build --tag oga-foreman:cloud-ready .
bash infra/smoke-container.sh oga-foreman:cloud-ready
```

## Reproducible Google Cloud deployment

The V1 choice is reviewed `gcloud` scripts; see
[ADR-006](decisions/ADR-006-reviewed-gcloud-infrastructure.md) and
[`infra/README.md`](../infra/README.md).

Review the plan without cloud mutation:

```bash
GOOGLE_CLOUD_PROJECT=oga-staging \
GOOGLE_CLOUD_REGION=europe-west1 \
FIRESTORE_LOCATION=your-approved-firestore-location \
MEDIA_BUCKET=oga-staging-media \
GEMINI_MODEL_ID=your-approved-model \
GEMINI_LOCATION=global \
AUTH_ISSUER=https://securetoken.google.com/oga-staging \
AUTH_AUDIENCE=oga-staging \
DEPLOY_DRY_RUN=true \
./infra/deploy.sh
```

The script manages:

- Firestore Native, deletion protection, deny-by-default client rules, indexes,
  and a daily 30-day backup schedule;
- a private/versioned/soft-delete-protected Storage bucket;
- Artifact Registry and a locked container build;
- separate `oga-api-*` and `oga-worker-*` Cloud Run services with explicit CPU,
  memory, startup, and liveness settings;
- API, worker, and push-invoker service accounts and IAM;
- site-event, dead-letter, worker, and dead-letter-inspection Pub/Sub resources;
- an optional per-project Daily Brief Scheduler job;
- a backup-failure logs metric and five alert policies.

The worker is private. Pub/Sub and Scheduler use an OIDC service account with
`roles/run.invoker`. The API may be Cloud Run-public, but protected project routes
still require application authentication and membership.

The pinned Firebase CLI deploy uses Application Default Credentials and an
explicit `--project`; it never relies on `.firebaserc` for environment selection.
The root `firebase.json` points to the checked-in rules and index definitions in
`firebase/firestore.rules` and `firebase/firestore.indexes.json`.
The V1 script supports the `(default)` Firestore database only and fails before
cloud mutation for a named database. Real deploys also require a clean Git
worktree so the image tag corresponds to reviewed source.

## Staging verification

After a real deploy:

```bash
.venv/bin/python scripts/smoke_observability.py \
  --base-url "$OGA_STAGING_API_URL" \
  --output artifacts/operations/staging-observability.json

.venv/bin/python scripts/verify_backups.py \
  --project-id "$GOOGLE_CLOUD_PROJECT" \
  --bucket "$MEDIA_BUCKET" \
  --live \
  --output artifacts/operations/staging-backups.json
```

Also execute the authenticated site-update/approval/duplicate/delivery-delay
smoke, the emulator or staging demo rehearsal, an isolated Firestore restore,
projection rebuild timing, and each alert smoke. Preserve commit SHA, Cloud Run
revisions, trace links, incident links, and command output.

## Rollback

Rollback shifts traffic to explicit previously verified revisions:

```bash
GOOGLE_CLOUD_PROJECT=oga-staging \
GOOGLE_CLOUD_REGION=europe-west1 \
API_SERVICE=oga-api-staging \
WORKER_SERVICE=oga-worker-staging \
API_REVISION=oga-api-staging-00012-abc \
WORKER_REVISION=oga-worker-staging-00009-def \
./infra/rollback.sh
```

The rollback script does not delete or rewrite Firestore, Storage, Pub/Sub,
events, runs, or activities. Run readiness, event delivery, and approval-resume
smokes immediately after traffic moves.

## Current evidence state

Infrastructure syntax, manifests, and dry-run output are locally verified. No
staging deployment, rollback rehearsal, backup visibility check, or restore has
been executed in this workspace. Those are release blockers, not assumed passes.

Official implementation references: [Firebase CLI](https://firebase.google.com/docs/cli),
[Firestore database protection](https://cloud.google.com/firestore/docs/manage-databases),
[authenticated Pub/Sub push](https://cloud.google.com/pubsub/docs/authenticate-push-subscriptions),
and [Cloud Run health checks](https://cloud.google.com/run/docs/configuring/healthchecks).
