from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_deploy_script_contains_release_critical_resources() -> None:
    source = (ROOT / "infra" / "deploy.sh").read_text(encoding="utf-8")

    assert ': "${FIRESTORE_LOCATION:?Set FIRESTORE_LOCATION}"' in source
    assert "FIRESTORE_LOCATION:=nam5" not in source
    assert 'gcloud run deploy "${API_SERVICE}"' in source
    assert 'gcloud run deploy "${WORKER_SERVICE}"' in source
    assert "--push-auth-service-account" in source
    assert "--dead-letter-topic" in source
    assert "--max-delivery-attempts 5" in source
    assert "backups schedules create" in source
    assert "gcloud builds get-default-service-account" in source
    assert "roles/artifactregistry.writer" in source
    assert "roles/storage.objectViewer" in source
    assert (
        "projects/${GOOGLE_CLOUD_PROJECT}/serviceAccounts/${BUILD_SERVICE_ACCOUNT_EMAIL}" in source
    )
    assert "--config cloudbuild.yaml" in source
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
    assert "firebaserules.googleapis.com" in source
    assert "gcloud firestore databases update" in source
    assert "else\n  run gcloud firestore databases update" in source
    assert "--delete-protection" in source
    assert "firebase-tools@${FIREBASE_CLI_VERSION}" in source
    assert "--only firestore" in source
    assert '--project "${GOOGLE_CLOUD_PROJECT}"' in source
    assert "--startup-probe" in source
    assert "--liveness-probe" in source
    assert "Refusing cloud deployment from a dirty worktree" in source
    assert 'load_deploy_env "${DEPLOY_ENV_FILE}"' in source
    assert 'export GOOGLE_CLOUD_QUOTA_PROJECT="${GOOGLE_CLOUD_PROJECT}"' in source
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
                "GEMINI_MODEL_ID=gemini-3.1-pro-preview",
                "GEMINI_LOCATION=global",
                "AUTH_ISSUER=https://securetoken.google.com/dotenv-project",
                "AUTH_AUDIENCE=dotenv-project",
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
        "AUTH_ISSUER",
        "AUTH_AUDIENCE",
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

    assert manifest["firestore"] == [
        {
            "database": "(default)",
            "rules": "firebase/firestore.rules",
            "indexes": "firebase/firestore.indexes.json",
        }
    ]
    assert "allow read, write: if false;" in rules


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
    assert config["steps"][0]["args"] == ["build", "-t", "${_IMAGE_URI}", "."]
