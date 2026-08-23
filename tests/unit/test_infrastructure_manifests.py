from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_deploy_script_contains_release_critical_resources() -> None:
    source = (ROOT / "infra" / "deploy.sh").read_text(encoding="utf-8")

    assert ': "${FIRESTORE_LOCATION:?Set FIRESTORE_LOCATION}"' in source
    assert ': "${CORS_ALLOWED_ORIGINS:?Set CORS_ALLOWED_ORIGINS as a JSON origin list}"' in source
    assert "FIRESTORE_LOCATION:=nam5" not in source
    assert 'gcloud run deploy "${API_SERVICE}"' in source
    assert 'gcloud run deploy "${WORKER_SERVICE}"' in source
    assert 'gcloud run deploy "${WEB_SERVICE}"' in source
    assert source.count("gcloud run services update-traffic") == 3
    assert source.count("--to-latest") == 3
    assert "--push-auth-service-account" in source
    assert "--dead-letter-topic" in source
    assert "--max-delivery-attempts 5" in source
    assert "backups schedules create" in source
    assert "gcloud builds get-default-service-account" in source
    assert "roles/artifactregistry.writer" in source
    assert "roles/storage.objectViewer" in source
    assert "STORAGE_SIGNING_SERVICE_ACCOUNT: '${API_SERVICE_ACCOUNT_EMAIL}'" in source
    assert "roles/iam.serviceAccountTokenCreator" in source
    assert (
        "projects/${GOOGLE_CLOUD_PROJECT}/serviceAccounts/${BUILD_SERVICE_ACCOUNT_EMAIL}" in source
    )
    assert "--config cloudbuild.yaml" in source
    assert "--config frontend/cloudbuild.yaml" in source
    assert "--versioning" in source
    assert "--soft-delete-duration 30d" in source
    assert 'BACKUP_BUCKET="${BACKUP_BUCKET:-${GOOGLE_CLOUD_PROJECT}-oga-backups}"' in source
    assert "gcp-sa-firestore.iam.gserviceaccount.com" in source
    assert "roles/storage.admin" in source
    assert "scheduler jobs create http" in source
    assert "scheduler jobs update http" in source
    assert "--update-headers Content-Type=application/json" in source
    assert "monitoring/apply.sh" in source
    assert "identitytoolkit.googleapis.com" in source
    assert "secretmanager.googleapis.com" in source
    assert source.count("roles/secretmanager.secretAccessor") == 1
    assert source.count("GOOGLE_CHAT_WEBHOOK_URL=${GOOGLE_CHAT_WEBHOOK_SECRET}:latest") == 2
    assert "NOTIFICATION_PROVIDER: '${NOTIFICATION_PROVIDER}'" in source
    assert ': "${NOTIFICATION_PROVIDER:?Set NOTIFICATION_PROVIDER=google_chat}"' in source
    assert "Staging and production require NOTIFICATION_PROVIDER=google_chat" in source
    assert "CONVERSATION_PROPOSAL_SIGNING_KEY:" not in source
    assert "firebaserules.googleapis.com" in source
    assert "gcloud firestore databases update" in source
    assert "else\n  run gcloud firestore databases update" in source
    assert "--delete-protection" in source
    assert "firebase-tools@${FIREBASE_CLI_VERSION}" in source
    assert "--only firestore" in source
    assert "--only hosting" in source
    assert '--project "${GOOGLE_CLOUD_PROJECT}"' in source
    assert "--startup-probe" in source
    assert "--liveness-probe" in source
    assert "Refusing cloud deployment from a dirty worktree" in source
    assert 'load_deploy_env "${DEPLOY_ENV_FILE}"' in source
    assert 'export GOOGLE_CLOUD_QUOTA_PROJECT="${GOOGLE_CLOUD_PROJECT}"' in source
    assert ': "${ADK_AGENT_ENGINE_ID:?Set ADK_AGENT_ENGINE_ID}"' in source
    assert "ADK_AGENT_ENGINE_ID: '${ADK_AGENT_ENGINE_ID}'" in source
    assert 'APP_GIT_SHA="$(git rev-parse HEAD)"' in source
    assert "APP_BUILD_TIME:" in source
    assert "APP_VERSION:" in source
    assert "APP_SOURCE_TREE_DIRTY:" in source
    assert "scripts/verify_deployment_provenance.py" in source
    assert "--expected-git-sha" not in source
    assert "--expected-build-time" in source
    assert "--expected-app-version" in source
    assert "deployment-current.json" in source


def test_api_and_worker_can_invoke_vertex_ai() -> None:
    source = (ROOT / "infra" / "deploy.sh").read_text(encoding="utf-8")

    def granted_roles(service_account_variable: str) -> set[str]:
        match = re.search(
            rf"for role in ([^;]+); do\n\s+grant_project_role "
            rf'"serviceAccount:\$\{{{service_account_variable}\}}"',
            source,
        )
        assert match is not None
        return set(match.group(1).split())

    assert "roles/aiplatform.user" in granted_roles("API_SERVICE_ACCOUNT_EMAIL")
    assert "roles/aiplatform.user" in granted_roles("WORKER_SERVICE_ACCOUNT_EMAIL")
    assert "firebase_project_exists" in source
    assert "projects:addfirebase" in source
    assert "run_with_transient_retry" in source
    assert "Transient IAM conflict" in source
    assert source.count("run_with_transient_retry gcloud") == 7
    assert "ALLOW_DIRTY_DEPLOY" not in source.split("DEPLOY_ENV_KEYS=", 1)[1].split("$'", 1)[0]


def test_deploy_script_safely_loads_dotenv_with_shell_overrides(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "\n".join(
            (
                "GOOGLE_CLOUD_PROJECT=dotenv-project",
                "GOOGLE_CLOUD_REGION=dotenv-region",
                "FIRESTORE_DATABASE='(default)'",
                "FIRESTORE_LOCATION=europe-west1",
                "MEDIA_BUCKET=dotenv-media",
                "GEMINI_MODEL_ID=gemini-3.6-flash",
                "GEMINI_LOCATION=global",
                "ADK_AGENT_ENGINE_ID=agent-engine-dotenv",
                "NOTIFICATION_PROVIDER=google_chat",
                "PUBLIC_APP_BASE_URL=https://dotenv.example",
                "AUTH_ISSUER=https://securetoken.google.com/dotenv-project",
                "AUTH_AUDIENCE=dotenv-project",
                'CORS_ALLOWED_ORIGINS=["https://dotenv.example"]',
                "NEXT_PUBLIC_API_BASE_URL=https://api.dotenv.example",
                "NEXT_PUBLIC_FIREBASE_API_KEY=public-web-key",
                "NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=dotenv.firebaseapp.com",
                "NEXT_PUBLIC_FIREBASE_PROJECT_ID=dotenv-project",
                "NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=dotenv.firebasestorage.app",
                "NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=123456789",
                "NEXT_PUBLIC_FIREBASE_APP_ID=1:123456789:web:dotenv",
                'SCHEDULE_CRON="15 6 * * *"',
                f"PATH=$(touch {marker})",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    for key in (
        "GOOGLE_CLOUD_PROJECT",
        "FIRESTORE_DATABASE",
        "FIRESTORE_LOCATION",
        "MEDIA_BUCKET",
        "GEMINI_MODEL_ID",
        "GEMINI_LOCATION",
        "ADK_AGENT_ENGINE_ID",
        "NOTIFICATION_PROVIDER",
        "PUBLIC_APP_BASE_URL",
        "AUTH_ISSUER",
        "AUTH_AUDIENCE",
        "CORS_ALLOWED_ORIGINS",
        "NEXT_PUBLIC_API_BASE_URL",
        "NEXT_PUBLIC_FIREBASE_API_KEY",
        "NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN",
        "NEXT_PUBLIC_FIREBASE_PROJECT_ID",
        "NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET",
        "NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID",
        "NEXT_PUBLIC_FIREBASE_APP_ID",
    ):
        environment.pop(key, None)
    environment.update(
        {
            "DEPLOY_ENV_FILE": str(env_file),
            "DEPLOY_DRY_RUN": "true",
            "GOOGLE_CLOUD_REGION": "override-region",
        }
    )

    completed = subprocess.run(
        ["bash", "infra/deploy.sh"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert "override-region-docker.pkg.dev/dotenv-project" in completed.stdout
    assert "dotenv-region-docker.pkg.dev" not in completed.stdout
    assert not marker.exists()


def test_firebase_manifest_deploys_deny_by_default_firestore_rules_and_indexes() -> None:
    manifest = json.loads((ROOT / "firebase.json").read_text(encoding="utf-8"))
    rules = (ROOT / "firebase" / "firestore.rules").read_text(encoding="utf-8")
    indexes = json.loads((ROOT / "firebase" / "firestore.indexes.json").read_text(encoding="utf-8"))

    assert manifest["firestore"] == [
        {
            "database": "(default)",
            "rules": "firebase/firestore.rules",
            "indexes": "firebase/firestore.indexes.json",
        }
    ]
    assert "allow read, write: if false;" in rules
    assert indexes["indexes"] == [
        {
            "collectionGroup": "members",
            "queryScope": "COLLECTION_GROUP",
            "fields": [
                {"fieldPath": "status", "order": "ASCENDING"},
                {"fieldPath": "user_id", "order": "ASCENDING"},
            ],
            "density": "SPARSE_ALL",
        }
    ]
    assert manifest["hosting"]["rewrites"] == [
        {
            "source": "**",
            "run": {"serviceId": "oga-web", "region": "europe-west1"},
        }
    ]


def test_deploy_applies_exact_origin_cors_to_media_bucket() -> None:
    source = (ROOT / "infra" / "deploy.sh").read_text(encoding="utf-8")

    assert "infra/render_storage_cors.py" in source
    assert '--origins-json "${CORS_ALLOWED_ORIGINS}"' in source
    assert '--cors-file="${STORAGE_CORS_FILE}"' in source


def test_ci_runs_backend_suite_with_durable_backing_service_emulators() -> None:
    manifest = json.loads((ROOT / "firebase.json").read_text(encoding="utf-8"))
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    storage_rules = (ROOT / "firebase" / "storage.rules").read_text(encoding="utf-8")

    assert manifest["storage"]["rules"] == "firebase/storage.rules"
    assert manifest["emulators"]["storage"] == {"host": "127.0.0.1", "port": 9199}
    assert "allow read, write: if false;" in storage_rules
    assert "actions/setup-java@v4" in workflow
    assert "actions/setup-node@v4" in workflow
    assert "firebase emulators:exec" in workflow
    assert "--only firestore,storage" in workflow
    assert "--project demo-oga-foreman-ci" in workflow
    assert 'pytest -q -m "not backing_services"' in workflow
    assert "pytest -q -m backing_services" in workflow


def test_frontend_container_is_standalone_and_non_root() -> None:
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    config = (ROOT / "frontend" / "next.config.mjs").read_text(encoding="utf-8")

    assert "'standalone'" in config
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "USER nextjs" in dockerfile
    assert 'CMD ["node", "server.js"]' in dockerfile


def test_cloud_build_includes_frontend_source_without_local_state() -> None:
    ignore = (ROOT / ".gcloudignore").read_text(encoding="utf-8")

    assert "!frontend/**" in ignore
    assert "frontend/.env*" in ignore
    assert "frontend/node_modules/" in ignore
    assert "frontend/.next*/" in ignore


def test_abandoned_firebase_scaffolds_are_removed() -> None:
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))

    assert not (ROOT / ".firebaserc").exists()
    assert not (ROOT / "functions").exists()
    assert not (ROOT / "dataconnect").exists()
    assert not (ROOT / "frontend" / "src" / "dataconnect-generated").exists()
    assert not (ROOT / "setup_ui.sh").exists()
    assert not (ROOT / "docs" / "auth.md").exists()
    assert "@dataconnect/generated" not in package["dependencies"]


def test_scoped_ignore_files_cover_generated_firebase_and_frontend_state() -> None:
    firebase_ignore = (ROOT / "firebase" / ".gitignore").read_text(encoding="utf-8")
    frontend_ignore = (ROOT / "frontend" / ".gitignore").read_text(encoding="utf-8")

    assert ".firebase/" in firebase_ignore
    assert "*-debug.log" in firebase_ignore
    assert "node_modules/" in frontend_ignore
    assert ".next/" in frontend_ignore
    assert "!.env.example" in frontend_ignore


def test_rollback_requires_explicit_verified_revisions_and_only_shifts_traffic() -> None:
    source = (ROOT / "infra" / "rollback.sh").read_text(encoding="utf-8")

    assert "API_REVISION:?" in source
    assert "WORKER_REVISION:?" in source
    assert source.count("services update-traffic") == 2
    assert "firestore delete" not in source
    assert "storage rm" not in source
    assert "pubsub topics delete" not in source


def test_authenticated_staging_smoke_covers_project_import_and_rollback_preservation() -> None:
    source = (ROOT / "scripts" / "smoke_authenticated_staging.py").read_text(encoding="utf-8")

    assert "create_import" in source
    assert "replay_import_creation" in source
    assert "recover_import" in source
    assert "confirm_import" in source
    assert "read_initialized_snapshot" in source
    assert "--verify-evidence" in source
    assert "read_preserved_import" in source
    assert "read_preserved_activity" in source


def test_ci_runs_locked_backend_frontend_and_container_gates() -> None:
    source = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "uv sync --all-extras --locked" in source
    assert "python -m pytest -q" in source
    assert "scripts/run_evals.py --adapter fixture" in source
    assert "npm ci" in source
    assert "npm run build" in source
    assert "playwright install --with-deps chromium" in source
    assert "npm run test:e2e" in source
    assert "docker build" in source
    assert "infra/smoke-container.sh" in source


def test_frontend_ci_installs_java_before_starting_firestore_e2e() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["frontend"]["steps"]
    e2e_index = next(
        index for index, step in enumerate(steps) if step.get("run") == "npm run test:e2e"
    )
    java_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses") == "actions/setup-java@v4"
        and step.get("with", {}).get("java-version") == "21"
    )

    assert java_index < e2e_index


def test_runtime_container_drops_root_and_has_reusable_smoke_check() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    smoke = (ROOT / "infra" / "smoke-container.sh").read_text(encoding="utf-8")

    assert "USER oga" in dockerfile
    assert "/health/live" in smoke
    assert "app.worker_http:app" in smoke

    deploy = (ROOT / "infra" / "deploy.sh").read_text(encoding="utf-8")
    assert deploy.count("httpGet.path=/health/live") == 2
    assert deploy.count("httpGet.path=/health/ready") == 2


def test_cloud_build_upload_contains_only_container_sources() -> None:
    ignore = (ROOT / ".gcloudignore").read_text(encoding="utf-8").splitlines()

    assert ignore[0] == "*"
    assert {
        "!Dockerfile",
        "!cloudbuild.yaml",
        "!.dockerignore",
        "!pyproject.toml",
        "!uv.lock",
        "!README.md",
        "!main.py",
        "!app/",
        "!app/**",
        "!scripts/",
        "!scripts/**",
        "**/__pycache__/",
        "**/*.py[cod]",
    }.issubset(ignore)


def test_cloud_build_uses_cloud_logging_without_bucket_write_access() -> None:
    config = yaml.safe_load((ROOT / "cloudbuild.yaml").read_text(encoding="utf-8"))

    assert config["options"]["logging"] == "CLOUD_LOGGING_ONLY"
    assert config["images"] == ["${_IMAGE_URI}"]
    assert config["steps"][0]["args"] == [
        "build",
        "--build-arg",
        "APP_GIT_SHA=${_APP_GIT_SHA}",
        "--build-arg",
        "APP_BUILD_TIME=${_APP_BUILD_TIME}",
        "--build-arg",
        "APP_VERSION=${_APP_VERSION}",
        "-t",
        "${_IMAGE_URI}",
        ".",
    ]


def test_backend_and_frontend_images_are_labeled_with_source_identity() -> None:
    backend = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    frontend_build = yaml.safe_load(
        (ROOT / "frontend" / "cloudbuild.yaml").read_text(encoding="utf-8")
    )

    for dockerfile in (backend, frontend):
        assert "org.opencontainers.image.revision=${APP_GIT_SHA}" in dockerfile
        assert "org.opencontainers.image.created=${APP_BUILD_TIME}" in dockerfile
        assert "org.opencontainers.image.version=${APP_VERSION}" in dockerfile
    assert "APP_GIT_SHA=${_APP_GIT_SHA}" in frontend_build["steps"][0]["args"]
    assert "APP_BUILD_TIME=${_APP_BUILD_TIME}" in frontend_build["steps"][0]["args"]
    assert "APP_VERSION=${_APP_VERSION}" in frontend_build["steps"][0]["args"]
