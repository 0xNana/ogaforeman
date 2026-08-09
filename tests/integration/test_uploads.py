from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import BytesIO
from typing import Any, cast

import pytest
from fastapi import FastAPI

from app.api.uploads import create_upload_router
from app.config.settings import RuntimeEnvironment, Settings
from app.domain.authorization import (
    AuthenticatedUser,
    ProjectAccessContext,
    ProjectForbiddenError,
    RoleRequiredError,
)
from app.domain.enums import AttachmentUploadStatus, MemberRole
from app.domain.models import ActivityEvent, Attachment
from app.infrastructure.storage import (
    GoogleCloudStorageAdapter,
    SignedUpload,
    StorageObjectNotFoundError,
    StorageObjectValidationError,
    StoredObject,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.services.attachments import (
    AttachmentConflictError,
    AttachmentError,
    AttachmentInput,
    AttachmentService,
)


NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
JPEG_SHA256 = "a" * 64


@dataclass
class FakeStorage:
    objects: dict[str, StoredObject | Exception] = field(default_factory=dict)
    signed_paths: list[str] = field(default_factory=list)

    def sign_upload(
        self,
        *,
        object_path: str,
        content_type: str,
        byte_size: int,
        expires_in_seconds: int,
    ) -> SignedUpload:
        self.signed_paths.append(object_path)
        return SignedUpload(
            url=f"https://storage.test/{object_path}?signed=upload",
            expires_at=NOW + timedelta(seconds=expires_in_seconds),
            required_headers={
                "Content-Type": content_type,
                "Content-Length": str(byte_size),
                "x-goog-if-generation-match": "0",
            },
        )

    def inspect(self, *, object_path: str, expected_sha256: str, max_bytes: int) -> StoredObject:
        result = self.objects.get(object_path)
        if result is None:
            raise StorageObjectNotFoundError(object_path)
        if isinstance(result, Exception):
            raise result
        if result.byte_size > max_bytes:
            raise StorageObjectValidationError("uploaded object exceeds the configured size limit")
        if result.sha256 != expected_sha256:
            raise StorageObjectValidationError("uploaded object checksum does not match")
        return result

    def sign_read(self, *, object_path: str, expires_in_seconds: int) -> SignedUpload:
        return SignedUpload(
            url=f"https://storage.test/{object_path}?signed=read",
            expires_at=NOW + timedelta(seconds=expires_in_seconds),
            required_headers={},
        )


def make_access(
    *, project_id: str = "prj_ridge", role: MemberRole = MemberRole.FOREMAN
) -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_foreman", subject="firebase-foreman"),
        project_id=project_id,
        role=role,
    )


def make_service(
    *, max_upload_bytes: int = 1_024
) -> tuple[AttachmentService, InMemoryRepositoryStore, FakeStorage]:
    store = InMemoryRepositoryStore()
    storage = FakeStorage()
    settings = Settings(
        _env_file=None,
        oga_env=RuntimeEnvironment.TEST,
        max_upload_bytes=max_upload_bytes,
        signed_upload_ttl_seconds=60,
    )
    return AttachmentService(store, storage, settings), store, storage


def upload_input(**changes: object) -> AttachmentInput:
    values: dict[str, object] = {
        "attachment_id": "att_photo001",
        "content_type": "image/jpeg",
        "byte_size": 512,
        "sha256": JPEG_SHA256,
    }
    values.update(changes)
    return AttachmentInput.model_validate(values)


def test_valid_upload_is_project_scoped_short_lived_verified_and_audited() -> None:
    service, store, storage = make_service()
    access = make_access()

    grant = service.sign_upload(access, upload_input())
    storage.objects[grant.attachment.object_path] = StoredObject(
        name=grant.attachment.object_path,
        content_type="image/jpeg",
        byte_size=512,
        sha256=JPEG_SHA256,
        generation="7",
    )
    verified = service.verify_upload(access, grant.attachment.id, include_read_url=True)

    assert grant.attachment.object_path == "projects/prj_ridge/attachments/att_photo001"
    assert grant.signed_upload.expires_at == NOW + timedelta(seconds=60)
    assert grant.signed_upload.required_headers["Content-Length"] == "512"
    assert grant.signed_upload.required_headers["x-goog-if-generation-match"] == "0"
    assert verified.attachment.upload_status is AttachmentUploadStatus.VERIFIED
    assert verified.signed_read is not None
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 2


def test_retrying_the_same_signed_contract_does_not_duplicate_attachment_or_activity() -> None:
    service, store, _ = make_service()
    access = make_access()

    first = service.sign_upload(access, upload_input())
    second = service.sign_upload(access, upload_input())

    assert first.attachment == second.attachment
    assert len(store.repository(Attachment).list("prj_ridge")) == 1
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 1


def test_verified_attachment_cannot_be_reopened_with_a_new_upload_url() -> None:
    service, _, storage = make_service()
    access = make_access()
    grant = service.sign_upload(access, upload_input())
    storage.objects[grant.attachment.object_path] = StoredObject(
        name=grant.attachment.object_path,
        content_type="image/jpeg",
        byte_size=512,
        sha256=JPEG_SHA256,
    )
    service.verify_upload(access, grant.attachment.id)

    with pytest.raises(AttachmentConflictError, match="no longer uploadable"):
        service.sign_upload(access, upload_input())


@pytest.mark.parametrize(
    "changes",
    [
        {"byte_size": 1_025},
        {"content_type": "text/html"},
        {"attachment_id": "att_good/../../prj_other"},
    ],
)
def test_signing_rejects_oversized_unallowlisted_and_forged_path_inputs(
    changes: dict[str, object],
) -> None:
    service, store, storage = make_service()

    with pytest.raises(AttachmentError):
        service.sign_upload(make_access(), upload_input(**changes))

    assert storage.signed_paths == []
    assert store.repository(Attachment).list("prj_ridge") == ()


@pytest.mark.parametrize(
    "stored",
    [
        StoredObject(
            name="projects/prj_other/attachments/att_photo001",
            content_type="image/jpeg",
            byte_size=512,
            sha256=JPEG_SHA256,
        ),
        StoredObject(
            name="projects/prj_ridge/attachments/att_photo001",
            content_type="text/html",
            byte_size=512,
            sha256=JPEG_SHA256,
        ),
        StoredObject(
            name="projects/prj_ridge/attachments/att_photo001",
            content_type="image/jpeg",
            byte_size=513,
            sha256=JPEG_SHA256,
        ),
        StorageObjectValidationError("uploaded object checksum does not match"),
    ],
)
def test_verification_rejects_forged_path_invalid_type_size_and_checksum(
    stored: StoredObject | Exception,
) -> None:
    service, store, storage = make_service()
    access = make_access()
    grant = service.sign_upload(access, upload_input())
    storage.objects[grant.attachment.object_path] = stored

    with pytest.raises(AttachmentError):
        service.verify_upload(access, grant.attachment.id)

    rejected = store.repository(Attachment).require("prj_ridge", grant.attachment.id)
    assert rejected.upload_status is AttachmentUploadStatus.REJECTED
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 2


def test_viewer_cannot_sign_or_verify_uploads() -> None:
    service, _, _ = make_service()

    with pytest.raises(RoleRequiredError):
        service.sign_upload(make_access(role=MemberRole.VIEWER), upload_input())


def test_service_rejects_a_route_project_that_differs_from_authorized_context() -> None:
    service, _, storage = make_service()

    with pytest.raises(ProjectForbiddenError):
        service.sign_upload(
            make_access(project_id="prj_ridge"),
            upload_input(),
            project_id="prj_other",
        )

    assert storage.signed_paths == []


def test_authorized_viewer_can_receive_private_read_url_only_after_verification() -> None:
    service, _, storage = make_service()
    foreman = make_access()
    grant = service.sign_upload(foreman, upload_input())

    with pytest.raises(AttachmentConflictError):
        service.get_read_url(make_access(role=MemberRole.VIEWER), grant.attachment.id)

    storage.objects[grant.attachment.object_path] = StoredObject(
        name=grant.attachment.object_path,
        content_type="image/jpeg",
        byte_size=512,
        sha256=JPEG_SHA256,
    )
    service.verify_upload(foreman, grant.attachment.id)
    result = service.get_read_url(make_access(role=MemberRole.VIEWER), grant.attachment.id)

    assert result.signed_read is not None
    assert result.signed_read.url.endswith("?signed=read")


def test_upload_api_publishes_versioned_sign_verify_and_private_read_contracts() -> None:
    service, _, _ = make_service()
    app = FastAPI()
    app.include_router(
        create_upload_router(
            service_provider=lambda _request: service,
            access_provider=lambda _request, project_id: make_access(project_id=project_id),
        )
    )
    schema = app.openapi()

    assert "/api/v1/projects/{project_id}/uploads/sign" in schema["paths"]
    assert "/api/v1/projects/{project_id}/uploads/{attachment_id}/verify" in schema["paths"]
    assert "/api/v1/projects/{project_id}/uploads/{attachment_id}/read-url" in schema["paths"]
    sign_operation = schema["paths"]["/api/v1/projects/{project_id}/uploads/sign"]["post"]
    assert sign_operation["requestBody"]["required"] is True
    assert "201" in sign_operation["responses"]


class FakeBlob:
    def __init__(self, name: str, payload: bytes) -> None:
        self.name = name
        self.payload = payload
        self.size = len(payload)
        self.content_type = "image/jpeg"
        self.generation = 3
        self.sign_calls: list[dict[str, Any]] = []

    def generate_signed_url(self, **kwargs: Any) -> str:
        self.sign_calls.append(kwargs)
        return f"https://storage.test/{self.name}?signed=v4"

    def reload(self) -> None:
        return None

    def open(self, mode: str) -> BytesIO:
        assert mode == "rb"
        return BytesIO(self.payload)


class FakeBucket:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, name: str) -> FakeBlob:
        return self.blobs.setdefault(name, FakeBlob(name, self.payload))


class FakeStorageClient:
    def __init__(self, payload: bytes) -> None:
        self.bucket_instance = FakeBucket(payload)

    def bucket(self, _name: str) -> FakeBucket:
        return self.bucket_instance


def test_gcs_adapter_signs_exact_headers_and_hashes_private_object_bytes() -> None:
    payload = b"\xff\xd8\xff" + b"site-photo"
    client = FakeStorageClient(payload)
    adapter = GoogleCloudStorageAdapter("private-media", client=cast(Any, client))

    signed = adapter.sign_upload(
        object_path="projects/prj_ridge/attachments/att_photo001",
        content_type="image/jpeg",
        byte_size=len(payload),
        expires_in_seconds=60,
    )
    inspected = adapter.inspect(
        object_path="projects/prj_ridge/attachments/att_photo001",
        expected_sha256=sha256(payload).hexdigest(),
        max_bytes=1_024,
    )

    blob = client.bucket_instance.blobs["projects/prj_ridge/attachments/att_photo001"]
    sign_call = blob.sign_calls[0]
    assert sign_call["version"] == "v4"
    assert sign_call["expiration"] == timedelta(seconds=60)
    assert sign_call["method"] == "PUT"
    assert sign_call["content_type"] == "image/jpeg"
    assert sign_call["headers"] == {
        "Content-Length": str(len(payload)),
        "x-goog-if-generation-match": "0",
    }
    assert signed.required_headers["Content-Length"] == str(len(payload))
    assert inspected.sha256 == sha256(payload).hexdigest()


def test_gcs_adapter_rejects_bytes_that_do_not_match_declared_mime_type() -> None:
    payload = b"<script>alert('not a jpeg')</script>"
    client = FakeStorageClient(payload)
    adapter = GoogleCloudStorageAdapter("private-media", client=cast(Any, client))

    with pytest.raises(StorageObjectValidationError, match="declared content type"):
        adapter.inspect(
            object_path="projects/prj_ridge/attachments/att_photo001",
            expected_sha256=sha256(payload).hexdigest(),
            max_bytes=1_024,
        )
