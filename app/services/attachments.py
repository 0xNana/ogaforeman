from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from secrets import token_hex
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

from app.config.settings import Settings
from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.enums import ActorType, AttachmentUploadStatus
from app.domain.models import ActivityEvent, Attachment, CanonicalId
from app.infrastructure.storage import (
    ALLOWED_UPLOAD_CONTENT_TYPES,
    SignedUpload,
    StorageAdapter,
    StorageObjectValidationError,
)
from app.repositories.interfaces import (
    EntityAlreadyExistsError,
    RepositoryStore,
    VersionConflictError,
)


Sha256 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[a-fA-F0-9]{64}$"),
]


class AttachmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    attachment_id: str | None = Field(default=None, min_length=3, max_length=128)
    content_type: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(gt=0)
    sha256: Sha256


class AttachmentError(ValueError):
    code = "ATTACHMENT_INVALID"


class AttachmentConflictError(AttachmentError):
    code = "ATTACHMENT_CONFLICT"


class AttachmentNotFoundError(AttachmentError):
    code = "ATTACHMENT_NOT_FOUND"


@dataclass(frozen=True)
class UploadGrant:
    attachment: Attachment
    signed_upload: SignedUpload
    max_bytes: int


@dataclass(frozen=True)
class VerifiedAttachment:
    attachment: Attachment
    signed_read: SignedUpload | None = None


class AttachmentService:
    """Project-scoped attachment intake and post-upload verification."""

    def __init__(
        self,
        store: RepositoryStore,
        storage: StorageAdapter,
        settings: Settings,
    ) -> None:
        self._store = store
        self._storage = storage
        self._settings = settings

    def sign_upload(
        self,
        access: ProjectAccessContext,
        request: AttachmentInput,
        *,
        project_id: str | None = None,
    ) -> UploadGrant:
        target_project_id = project_id or access.project_id
        ensure_project_scope(access, target_project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        if request.content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
            raise AttachmentError("content type is not allowlisted")
        if request.byte_size > self._settings.max_upload_bytes:
            raise AttachmentError("attachment exceeds the configured size limit")

        attachment_id = request.attachment_id or f"att_{token_hex(16)}"
        try:
            attachment_id = TypeAdapter(CanonicalId).validate_python(attachment_id)
        except ValueError as exc:
            raise AttachmentError("attachment ID is not a canonical ID") from exc
        object_path = f"projects/{target_project_id}/attachments/{attachment_id}"
        existing = self._store.repository(Attachment).get(target_project_id, attachment_id)
        if existing is not None:
            if not _matches_contract(existing, request, object_path):
                raise AttachmentConflictError("attachment ID is already bound to another upload")
            if existing.upload_status is not AttachmentUploadStatus.INITIATED:
                raise AttachmentConflictError("attachment is no longer uploadable")
            attachment = existing
        else:
            attachment = Attachment(
                id=attachment_id,
                project_id=target_project_id,
                object_path=object_path,
                content_type=request.content_type,
                byte_size=request.byte_size,
                sha256=request.sha256.lower(),
                upload_status=AttachmentUploadStatus.INITIATED,
            )
            try:
                self._store.run_transaction(
                    lambda session: self._create_with_activity(session, attachment, access)
                )
            except EntityAlreadyExistsError:
                concurrent = self._store.repository(Attachment).require(
                    target_project_id, attachment_id
                )
                if (
                    not _matches_contract(concurrent, request, object_path)
                    or concurrent.upload_status is not AttachmentUploadStatus.INITIATED
                ):
                    raise AttachmentConflictError(
                        "attachment ID was concurrently bound to another upload"
                    ) from None
                attachment = concurrent

        signed_upload = self._storage.sign_upload(
            object_path=object_path,
            content_type=request.content_type,
            byte_size=request.byte_size,
            expires_in_seconds=self._settings.signed_upload_ttl_seconds,
        )
        return UploadGrant(
            attachment=attachment,
            signed_upload=signed_upload,
            max_bytes=self._settings.max_upload_bytes,
        )

    def verify_upload(
        self,
        access: ProjectAccessContext,
        attachment_id: str,
        *,
        project_id: str | None = None,
        include_read_url: bool = False,
    ) -> VerifiedAttachment:
        target_project_id = project_id or access.project_id
        ensure_project_scope(access, target_project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        attachment_repository = self._store.repository(Attachment)
        attachment = attachment_repository.get(target_project_id, attachment_id)
        if attachment is None:
            raise AttachmentNotFoundError("attachment was not found in this project")
        if attachment.upload_status is AttachmentUploadStatus.VERIFIED:
            return VerifiedAttachment(
                attachment=attachment,
                signed_read=(
                    self._storage.sign_read(
                        object_path=attachment.object_path,
                        expires_in_seconds=self._settings.signed_upload_ttl_seconds,
                    )
                    if include_read_url
                    else None
                ),
            )
        if attachment.upload_status is not AttachmentUploadStatus.INITIATED:
            raise AttachmentConflictError("attachment is not awaiting verification")

        try:
            stored = self._storage.inspect(
                object_path=attachment.object_path,
                expected_sha256=attachment.sha256,
                max_bytes=self._settings.max_upload_bytes,
            )
            if stored.name != attachment.object_path:
                raise StorageObjectValidationError("storage returned an unexpected object path")
            if stored.content_type != attachment.content_type:
                raise StorageObjectValidationError("uploaded content type differs from signed type")
            if stored.byte_size != attachment.byte_size:
                raise StorageObjectValidationError("uploaded byte size differs from signed size")
        except (StorageObjectValidationError, LookupError) as exc:
            rejected = attachment.model_copy(
                update={"upload_status": AttachmentUploadStatus.REJECTED}
            )
            try:
                self._store.run_transaction(
                    lambda session: self._save_with_activity(
                        session, rejected, access, action="attachment.upload_rejected"
                    )
                )
            except VersionConflictError:
                pass
            raise AttachmentError(str(exc)) from exc

        verified = attachment.model_copy(
            update={
                "upload_status": AttachmentUploadStatus.VERIFIED,
                "metadata": {
                    **attachment.metadata,
                    "storage_generation": stored.generation,
                    "verified_at": datetime.now(UTC).isoformat(),
                },
            }
        )
        try:
            saved = self._store.run_transaction(
                lambda session: self._save_with_activity(
                    session, verified, access, action="attachment.upload_verified"
                )
            )
        except VersionConflictError:
            saved = self._store.repository(Attachment).require(target_project_id, attachment_id)
            if saved.upload_status is not AttachmentUploadStatus.VERIFIED:
                raise AttachmentConflictError(
                    "attachment verification resolved to another terminal state"
                ) from None
        return VerifiedAttachment(
            attachment=saved,
            signed_read=(
                self._storage.sign_read(
                    object_path=saved.object_path,
                    expires_in_seconds=self._settings.signed_upload_ttl_seconds,
                )
                if include_read_url
                else None
            ),
        )

    def get_read_url(
        self,
        access: ProjectAccessContext,
        attachment_id: str,
        *,
        project_id: str | None = None,
    ) -> VerifiedAttachment:
        target_project_id = project_id or access.project_id
        ensure_project_scope(access, target_project_id)
        ensure_permission(access, ProjectPermission.READ)
        attachment = self._store.repository(Attachment).get(target_project_id, attachment_id)
        if attachment is None:
            raise AttachmentNotFoundError("attachment was not found in this project")
        if attachment.upload_status is not AttachmentUploadStatus.VERIFIED:
            raise AttachmentConflictError("attachment is not available for reading")
        return VerifiedAttachment(
            attachment=attachment,
            signed_read=self._storage.sign_read(
                object_path=attachment.object_path,
                expires_in_seconds=self._settings.signed_upload_ttl_seconds,
            ),
        )

    @staticmethod
    def _create_with_activity(
        session, attachment: Attachment, access: ProjectAccessContext
    ) -> Attachment:
        created = session.repository(Attachment).create(attachment)
        _create_activity(
            session,
            access,
            attachment,
            action="attachment.upload_requested",
            summary="Attachment upload URL issued",
        )
        return created

    @staticmethod
    def _save_with_activity(
        session,
        updated: Attachment,
        access: ProjectAccessContext,
        *,
        action: str,
    ) -> Attachment:
        saved = session.repository(Attachment).save(updated, expected_version=0)
        _create_activity(
            session,
            access,
            saved,
            action=action,
            summary=(
                "Attachment upload verified"
                if action.endswith("verified")
                else "Attachment upload rejected"
            ),
        )
        return saved


def _create_activity(
    session: Any,
    access: ProjectAccessContext,
    attachment: Attachment,
    *,
    action: str,
    summary: str,
) -> None:
    activity_id = f"act_{sha256(f'{attachment.id}:{action}'.encode()).hexdigest()[:24]}"
    repository = session.repository(ActivityEvent)
    if repository.get(access.project_id, activity_id) is not None:
        return
    try:
        repository.create(
            ActivityEvent(
                id=activity_id,
                project_id=access.project_id,
                actor_type=ActorType.USER,
                actor_id=access.actor.user_id,
                action=action,
                entity_type="attachment",
                entity_id=attachment.id,
                summary=summary,
                metadata={"upload_status": attachment.upload_status.value},
            )
        )
    except EntityAlreadyExistsError:
        return


def _matches_contract(
    attachment: Attachment,
    request: AttachmentInput,
    object_path: str,
) -> bool:
    return (
        attachment.object_path == object_path
        and attachment.content_type == request.content_type
        and attachment.byte_size == request.byte_size
        and attachment.sha256.lower() == request.sha256.lower()
    )
