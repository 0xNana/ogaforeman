"""Tests for deployed source/revision/image provenance evidence."""

from __future__ import annotations

import json
from subprocess import CompletedProcess

import httpx
import pytest

from scripts.verify_deployment_provenance import (
    DeploymentProvenanceError,
    collect_deployment_provenance,
    repo_git_sha,
)


GIT_SHA = "b134039daa3bc1528f9e869678dd6d59a4f9d1f9"
BUILD_TIME = "2026-08-23T14:05:06Z"


def _version_transport(
    *,
    revision: str = "oga-api-staging-00042-abc",
    git_sha: str = GIT_SHA,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/version"
        return httpx.Response(
            200,
            json={
                "app_version": "0.1.0",
                "git_sha": git_sha,
                "build_timestamp": BUILD_TIME,
                "source_tree_dirty": False,
                "environment": "staging",
                "service": "oga-api-staging",
                "revision": revision,
            },
            request=request,
        )

    return httpx.MockTransport(handler)


def _gcloud_runner(command: list[str], **_: object) -> CompletedProcess[str]:
    resource_kind = command[2]
    name = command[4]
    if resource_kind == "services":
        payload = {
            "status": {
                "latestReadyRevisionName": f"{name}-00042-abc",
                "url": f"https://{name}.example.test",
            }
        }
    elif resource_kind == "revisions":
        service = name.rsplit("-00042-abc", 1)[0]
        image_name = "oga-web" if service == "oga-web" else "oga-foreman"
        payload = {
            "metadata": {"creationTimestamp": "2026-08-23T14:06:07Z"},
            "spec": {
                "containers": [
                    {
                        "env": [
                            {"name": "APP_GIT_SHA", "value": GIT_SHA},
                            {"name": "APP_BUILD_TIME", "value": BUILD_TIME},
                            {"name": "APP_VERSION", "value": "0.1.0"},
                            {"name": "APP_SOURCE_TREE_DIRTY", "value": "false"},
                            {"name": "SECRET_VALUE", "value": "must-not-be-recorded"},
                        ]
                    }
                ]
            },
            "status": {
                "imageDigest": (
                    f"europe-west1-docker.pkg.dev/project/repository/{image_name}@sha256:{'a' * 64}"
                )
            },
        }
    else:  # pragma: no cover - makes an unexpected command immediately diagnostic
        raise AssertionError(command)
    return CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")


def test_collector_proves_endpoint_revision_digest_and_stamped_source() -> None:
    with httpx.Client(transport=_version_transport()) as client:
        evidence = collect_deployment_provenance(
            base_url="https://oga-api-staging.example.test",
            project_id="ogaforeman-cloud-2026",
            region="europe-west1",
            environment="staging",
            expected_git_sha=GIT_SHA,
            expected_build_time=BUILD_TIME,
            expected_app_version="0.1.0",
            services={
                "api": "oga-api-staging",
                "worker": "oga-worker-staging",
                "web": "oga-web",
            },
            client=client,
            command_runner=_gcloud_runner,
        )

    assert evidence["passed"] is True
    assert evidence["repo_git_sha"] == GIT_SHA
    assert evidence["build_timestamp"] == BUILD_TIME
    assert evidence["deployment_timestamp"] == "2026-08-23T14:06:07Z"
    assert evidence["version_endpoint"] == ("https://oga-api-staging.example.test/api/v1/version")
    assert evidence["services"]["api"] == {
        "service": "oga-api-staging",
        "revision": "oga-api-staging-00042-abc",
        "image_digest": f"sha256:{'a' * 64}",
        "deployment_timestamp": "2026-08-23T14:06:07Z",
        "url": "https://oga-api-staging.example.test",
    }
    assert "SECRET_VALUE" not in json.dumps(evidence)


def test_collector_rejects_endpoint_that_reports_an_older_revision() -> None:
    with httpx.Client(transport=_version_transport(revision="oga-api-staging-00041-old")) as client:
        with pytest.raises(DeploymentProvenanceError, match="revision"):
            collect_deployment_provenance(
                base_url="https://oga-api-staging.example.test",
                project_id="ogaforeman-cloud-2026",
                region="europe-west1",
                environment="staging",
                expected_git_sha=GIT_SHA,
                expected_build_time=BUILD_TIME,
                expected_app_version="0.1.0",
                services={"api": "oga-api-staging"},
                client=client,
                command_runner=_gcloud_runner,
            )


def test_collector_rejects_deployed_sha_that_differs_from_repository_head() -> None:
    deployed_sha = "a" * 40
    with httpx.Client(transport=_version_transport(git_sha=deployed_sha)) as client:
        with pytest.raises(DeploymentProvenanceError, match="git SHA mismatch"):
            collect_deployment_provenance(
                base_url="https://oga-api-staging.example.test",
                project_id="ogaforeman-cloud-2026",
                region="europe-west1",
                environment="staging",
                expected_git_sha=GIT_SHA,
                expected_build_time=BUILD_TIME,
                expected_app_version="0.1.0",
                services={"api": "oga-api-staging"},
                client=client,
                command_runner=_gcloud_runner,
            )


def test_repo_sha_is_derived_from_git_head() -> None:
    def runner(command: list[str], **_: object) -> CompletedProcess[str]:
        assert command == ["git", "rev-parse", "HEAD"]
        return CompletedProcess(command, 0, stdout=f"{GIT_SHA}\n", stderr="")

    assert repo_git_sha(runner) == GIT_SHA
