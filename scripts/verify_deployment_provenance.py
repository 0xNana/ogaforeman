"""Verify and record Git-to-Cloud-Run deployment provenance."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, TypeAdapter, ValidationError


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
DIGEST_PATTERN = re.compile(r"(?:.+@)?(sha256:[0-9a-f]{64})")


class DeploymentProvenanceError(RuntimeError):
    """Raised when runtime or Cloud Run identity does not match the source build."""


class DeployedVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_version: str
    git_sha: str
    build_timestamp: AwareDatetime
    source_tree_dirty: bool
    environment: str
    service: str
    revision: str


def collect_deployment_provenance(
    *,
    base_url: str,
    project_id: str,
    region: str,
    environment: str,
    expected_git_sha: str,
    expected_build_time: str,
    expected_app_version: str,
    services: Mapping[str, str],
    client: httpx.Client,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, object]:
    normalized_url = _validate_inputs(
        base_url=base_url,
        expected_git_sha=expected_git_sha,
        services=services,
    )
    try:
        expected_time = TypeAdapter(AwareDatetime).validate_python(expected_build_time)
    except ValidationError as exc:
        raise DeploymentProvenanceError("expected build time must be timezone-aware") from exc
    version_url = f"{normalized_url}/api/v1/version"
    try:
        response = client.get(version_url)
        response.raise_for_status()
        deployed_version = DeployedVersion.model_validate(response.json())
    except (httpx.HTTPError, ValueError, ValidationError) as exc:
        raise DeploymentProvenanceError(
            f"version endpoint did not return the required contract: {type(exc).__name__}"
        ) from exc

    _require_equal("git SHA", deployed_version.git_sha, expected_git_sha)
    _require_equal("app version", deployed_version.app_version, expected_app_version)
    _require_equal("build timestamp", deployed_version.build_timestamp, expected_time)
    _require_equal("environment", deployed_version.environment, environment)
    if deployed_version.source_tree_dirty:
        raise DeploymentProvenanceError("version endpoint reports a dirty source tree")

    service_evidence: dict[str, dict[str, str]] = {}
    for role, service_name in services.items():
        service_payload = _gcloud_json(
            [
                "gcloud",
                "run",
                "services",
                "describe",
                service_name,
                "--project",
                project_id,
                "--region",
                region,
                "--format=json",
            ],
            command_runner,
        )
        revision = _required_string(
            service_payload, ("status", "latestReadyRevisionName"), service_name
        )
        service_url = _required_string(service_payload, ("status", "url"), service_name)
        revision_payload = _gcloud_json(
            [
                "gcloud",
                "run",
                "revisions",
                "describe",
                revision,
                "--project",
                project_id,
                "--region",
                region,
                "--format=json",
            ],
            command_runner,
        )
        image_digest = _required_string(revision_payload, ("status", "imageDigest"), revision)
        deployment_timestamp = _required_string(
            revision_payload,
            ("metadata", "creationTimestamp"),
            revision,
        )
        try:
            TypeAdapter(AwareDatetime).validate_python(deployment_timestamp)
        except ValidationError as exc:
            raise DeploymentProvenanceError(
                f"Cloud Run revision {revision} has an invalid deployment timestamp"
            ) from exc
        digest_match = DIGEST_PATTERN.fullmatch(image_digest)
        if digest_match is None:
            raise DeploymentProvenanceError(
                f"Cloud Run revision {revision} has no resolved sha256 image digest"
            )
        resolved_digest = digest_match.group(1)
        stamped_environment = _revision_environment(revision_payload, revision)
        for key, expected in {
            "APP_GIT_SHA": expected_git_sha,
            "APP_BUILD_TIME": expected_build_time,
            "APP_VERSION": expected_app_version,
            "APP_SOURCE_TREE_DIRTY": "false",
        }.items():
            _require_equal(f"{revision} {key}", stamped_environment.get(key), expected)

        service_evidence[role] = {
            "service": service_name,
            "revision": revision,
            "image_digest": resolved_digest,
            "deployment_timestamp": deployment_timestamp,
            "url": service_url,
        }

    api = service_evidence.get("api")
    if api is None:
        raise DeploymentProvenanceError("services must include the API role")
    _require_equal("version endpoint service", deployed_version.service, api["service"])
    _require_equal("version endpoint revision", deployed_version.revision, api["revision"])
    _require_equal("version endpoint base URL", normalized_url, api["url"].rstrip("/"))

    return {
        "schema_version": 1,
        "evidence_generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "passed": True,
        "repo_git_sha": expected_git_sha,
        "app_version": expected_app_version,
        "build_timestamp": expected_build_time,
        "deployment_timestamp": api["deployment_timestamp"],
        "source_tree_dirty": False,
        "environment": environment,
        "project_id": project_id,
        "region": region,
        "version_endpoint": version_url,
        "version_response": deployed_version.model_dump(mode="json"),
        "services": service_evidence,
    }


def _validate_inputs(*, base_url: str, expected_git_sha: str, services: Mapping[str, str]) -> str:
    normalized_url = base_url.strip().rstrip("/")
    parsed = urlparse(normalized_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path:
        raise DeploymentProvenanceError("base URL must be an HTTPS origin")
    if SHA_PATTERN.fullmatch(expected_git_sha) is None:
        raise DeploymentProvenanceError("expected Git SHA must be a full lowercase object ID")
    if not services:
        raise DeploymentProvenanceError("at least one Cloud Run service is required")
    return normalized_url


def _gcloud_json(command: list[str], command_runner: CommandRunner) -> dict[str, object]:
    completed = command_runner(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if completed.returncode != 0:
        raise DeploymentProvenanceError(
            f"gcloud describe failed for {command[4]} with exit {completed.returncode}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise DeploymentProvenanceError(
            f"gcloud describe returned invalid JSON for {command[4]}"
        ) from exc
    if not isinstance(payload, dict):
        raise DeploymentProvenanceError(f"gcloud describe returned invalid data for {command[4]}")
    return payload


def _required_string(payload: Mapping[str, object], path: tuple[str, ...], resource: str) -> str:
    value: object = payload
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise DeploymentProvenanceError(f"{resource} is missing {'.'.join(path)}")
        value = value[key]
    if not isinstance(value, str) or not value:
        raise DeploymentProvenanceError(f"{resource} has invalid {'.'.join(path)}")
    return value


def _revision_environment(payload: Mapping[str, object], revision: str) -> dict[str, str]:
    spec = payload.get("spec")
    containers = spec.get("containers") if isinstance(spec, dict) else None
    if not isinstance(containers, list) or len(containers) != 1:
        raise DeploymentProvenanceError(f"Cloud Run revision {revision} has invalid containers")
    container = containers[0]
    environment = container.get("env") if isinstance(container, dict) else None
    if not isinstance(environment, list):
        raise DeploymentProvenanceError(f"Cloud Run revision {revision} has no environment")
    stamped: dict[str, str] = {}
    for item in environment:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if isinstance(name, str) and isinstance(value, str):
            stamped[name] = value
    return stamped


def _require_equal(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise DeploymentProvenanceError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def repo_git_sha(command_runner: CommandRunner = subprocess.run) -> str:
    completed = command_runner(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    git_sha = completed.stdout.strip()
    if completed.returncode != 0 or SHA_PATTERN.fullmatch(git_sha) is None:
        raise DeploymentProvenanceError("could not derive a full Git SHA from repository HEAD")
    return git_sha


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--expected-build-time", required=True)
    parser.add_argument("--expected-app-version", required=True)
    parser.add_argument("--api-service", required=True)
    parser.add_argument("--worker-service", required=True)
    parser.add_argument("--web-service", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        expected_git_sha = repo_git_sha()
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            evidence = collect_deployment_provenance(
                base_url=args.base_url,
                project_id=args.project_id,
                region=args.region,
                environment=args.environment,
                expected_git_sha=expected_git_sha,
                expected_build_time=args.expected_build_time,
                expected_app_version=args.expected_app_version,
                services={
                    "api": args.api_service,
                    "worker": args.worker_service,
                    "web": args.web_service,
                },
                client=client,
            )
    except DeploymentProvenanceError as exc:
        print(f"Deployment provenance failed: {exc}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Deployment provenance passed git={evidence['repo_git_sha']} artifact={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DeploymentProvenanceError",
    "collect_deployment_provenance",
    "repo_git_sha",
]
