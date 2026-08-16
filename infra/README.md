# Google Cloud infrastructure

Oga Foreman uses reviewed `gcloud` scripts for the V1 public-beta deployment.
The choice and the authenticated Pub/Sub push boundary are recorded in
[`ADR-006`](../docs/decisions/ADR-006-reviewed-gcloud-infrastructure.md).

## Resources managed

- Firestore Native database and a daily 30-day backup schedule;
- Firestore deletion protection plus checked-in deny-by-default rules and indexes;
- private Cloud Storage bucket with uniform access, versioning, 30-day soft
  delete, and exact-origin CORS for signed browser uploads;
- Artifact Registry and Cloud Build image publication;
- separate Cloud Run API and worker services with startup/liveness probes;
- API, worker, and push-invoker service accounts with scoped IAM roles;
- site-event and dead-letter Pub/Sub topics, authenticated worker subscription,
  and a retained dead-letter inspection subscription;
- optional per-project Cloud Scheduler daily-brief job;
- logs-based backup-failure metric and the alert policies in `monitoring/`.

The scripts enable the Firebase Authentication and Rules APIs, but do not create
application secrets or sign-in providers. Before deployment, add the Google
Cloud project to Firebase, enable the approved Email/Password provider and
domains, and authenticate `gcloud` plus the Firebase CLI through Application
Default Credentials. The deploy uses pinned `firebase-tools@15.26.0` through
`npx` and always passes the explicit project ID.

V1 deployment manages the Firebase `(default)` Firestore database. A named
database requires an explicit additional entry in `firebase.json` and a reviewed
deployment change; the script fails closed instead of applying rules to the
wrong database.

Keep `firebase.json` at the repository root for Firebase CLI discovery. Its
deployable Firestore definitions live in `firebase/firestore.rules` and
`firebase/firestore.indexes.json`.

## Required environment

```bash
export GOOGLE_CLOUD_PROJECT=oga-staging
export GOOGLE_CLOUD_REGION=europe-west1
export FIRESTORE_DATABASE='(default)'
export FIRESTORE_LOCATION=your-approved-firestore-location
export MEDIA_BUCKET=oga-staging-media
export GEMINI_MODEL_ID=gemini-3.6-flash
export GEMINI_LOCATION=global
export CONVERSATION_PROPOSAL_SIGNING_SECRET=oga-conversation-proposal-signing-key-staging
export AUTH_ISSUER=https://securetoken.google.com/oga-staging
export AUTH_AUDIENCE=oga-staging
export CORS_ALLOWED_ORIGINS='["https://oga-staging.web.app","https://oga-staging.firebaseapp.com"]'
```

Create the named Secret Manager secret before deployment and add a current
version containing at least 32 cryptographically random bytes. The deployment
grants only the API and worker service accounts access and mounts it as
`CONVERSATION_PROPOSAL_SIGNING_KEY`; the secret value must never be placed in
the deploy `.env` file.

`FIRESTORE_LOCATION` is mandatory because the database location cannot be
changed after creation. Choose it explicitly before the first real deployment;
the script never supplies a geographic default.

Optional resource names have safe environment-specific defaults. Set
`SCHEDULE_PROJECT_ID=prj_ridge` to create the deterministic demo daily-brief
job.

## Verify the production container

```bash
docker build --tag oga-foreman:cloud-ready .
bash infra/smoke-container.sh oga-foreman:cloud-ready
```

The smoke boots both the API and worker entrypoints from the same non-root image
and requires each `/health/live` endpoint to respond successfully.

## Review without changing cloud state

```bash
DEPLOY_DRY_RUN=true ./infra/deploy.sh
```

Dry-run validates required configuration and prints the intended commands. It
does not prove IAM, API availability, deployment, alerts, backups, or rollback.

## Deploy staging

```bash
DEPLOY_ENVIRONMENT=staging ./infra/deploy.sh
```

A real deployment refuses a dirty Git worktree so the image tag identifies the
reviewed source revision. `ALLOW_DIRTY_DEPLOY=true` exists only for controlled
incident recovery and must not be used for a normal release.

After deployment, run `scripts/smoke_observability.py`, the authenticated
workflow smoke, backup verification, and the demo rehearsal. Preserve their JSON
artifacts with the commit SHA and Cloud Run revision names.

## Roll back

Select previously verified immutable revisions, then run:

```bash
API_SERVICE=oga-api-staging \
WORKER_SERVICE=oga-worker-staging \
API_REVISION=oga-api-staging-00012-abc \
WORKER_REVISION=oga-worker-staging-00009-def \
./infra/rollback.sh
```

The script changes Cloud Run traffic only. It never deletes Firestore, Storage,
Pub/Sub, source events, or activity records.

## Evidence status

The scripts and local syntax/manifest tests are checked in. No staging deploy,
rollback rehearsal, alert smoke, backup visibility check, or isolated restore has
been executed from this workspace; those remain release gates.

## Official references

- [Firebase CLI deployment and ADC authentication](https://firebase.google.com/docs/cli)
- [Firestore database deletion protection](https://cloud.google.com/firestore/docs/manage-databases)
- [Authenticated Pub/Sub push](https://cloud.google.com/pubsub/docs/authenticate-push-subscriptions)
- [Cloud Run container health checks](https://cloud.google.com/run/docs/configuring/healthchecks)
