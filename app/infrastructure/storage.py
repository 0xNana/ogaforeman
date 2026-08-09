from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from google.api_core.exceptions import NotFound
from google.cloud.storage import Client

from app.config.settings import Settings, get_settings


ALLOWED_UPLOAD_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "audio/m4a",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "image/jpeg",
        "image/png",
        "image/webp",
        "text/plain",
    }
)


class StorageObjectNotFoundError(LookupError):
    """Raised when an attachment object is missing from the private bucket."""


class StorageObjectValidationError(ValueError):
    """Raised when the object does not match its signed upload contract."""


@dataclass(frozen=True)
class StoredObject:
    name: str
    content_type: str
    byte_size: int
    sha256: str
    generation: str | None = None


@dataclass(frozen=True)
class SignedUpload:
    url: str
    expires_at: datetime
    required_headers: dict[str, str]


class StorageAdapter(Protocol):
    def sign_upload(
        self,
        *,
        object_path: str,
        content_type: str,
        byte_size: int,
        expires_in_seconds: int,
    ) -> SignedUpload:
        """Return a short-lived, create-only upload URL for one exact object."""

    def inspect(self, *, object_path: str, expected_sha256: str, max_bytes: int) -> StoredObject:
        """Read and hash one private object, enforcing its upload contract."""

    def sign_read(self, *, object_path: str, expires_in_seconds: int) -> SignedUpload:
        """Return a short-lived read URL for an already authorized object."""

    def read_bytes(
        self,
        *,
        object_path: str,
        expected_sha256: str,
        max_bytes: int,
    ) -> bytes:
        """Read verified private media bytes with size and checksum enforcement."""


class GoogleCloudStorageAdapter(StorageAdapter):
    """Cloud Storage adapter using V4 signed URLs and generation preconditions.

    The client-library methods follow Google's Blob reference and signed URL sample:
    https://cloud.google.com/python/docs/reference/storage/latest/google.cloud.storage.blob.Blob#google_cloud_storage_blob_Blob_generate_signed_url
    https://cloud.google.com/storage/docs/samples/storage-generate-upload-signed-url-v4
    https://cloud.google.com/storage/docs/request-preconditions#the_0_value_in_a_generation-match_precondition
    """

    def __init__(self, bucket_name: str, *, client: Client | None = None) -> None:
        self._client = client or Client()
        self._bucket = self._client.bucket(bucket_name)

    def sign_upload(
        self,
        *,
        object_path: str,
        content_type: str,
        byte_size: int,
        expires_in_seconds: int,
    ) -> SignedUpload:
        blob = self._bucket.blob(object_path)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(byte_size),
            "x-goog-if-generation-match": "0",
        }
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expires_in_seconds),
            method="PUT",
            content_type=content_type,
            headers={
                "Content-Length": str(byte_size),
                "x-goog-if-generation-match": "0",
            },
        )
        return SignedUpload(url=url, expires_at=expires_at, required_headers=headers)

    def inspect(self, *, object_path: str, expected_sha256: str, max_bytes: int) -> StoredObject:
        blob = self._bucket.blob(object_path)
        try:
            blob.reload()
        except NotFound as exc:
            raise StorageObjectNotFoundError(object_path) from exc

        size = blob.size
        content_type = blob.content_type
        if not isinstance(size, int) or size <= 0:
            raise StorageObjectValidationError("uploaded object has no valid byte size")
        if size > max_bytes:
            raise StorageObjectValidationError("uploaded object exceeds the configured size limit")
        if not isinstance(content_type, str) or content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
            raise StorageObjectValidationError("uploaded object has an unallowlisted content type")

        digest = hashlib.sha256()
        downloaded = 0
        prefix = bytearray()
        with blob.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                downloaded += len(chunk)
                if downloaded > max_bytes:
                    raise StorageObjectValidationError(
                        "uploaded object exceeds the configured size limit"
                    )
                if len(prefix) < 32:
                    prefix.extend(chunk[: 32 - len(prefix)])
                digest.update(chunk)
        if downloaded != size:
            raise StorageObjectValidationError("uploaded object size changed during verification")
        if not _content_matches(content_type, bytes(prefix)):
            raise StorageObjectValidationError(
                "uploaded bytes do not match the declared content type"
            )
        actual_sha256 = digest.hexdigest()
        if actual_sha256.lower() != expected_sha256.lower():
            raise StorageObjectValidationError(
                "uploaded object checksum does not match the signed contract"
            )

        return StoredObject(
            name=blob.name,
            content_type=content_type,
            byte_size=size,
            sha256=actual_sha256,
            generation=str(blob.generation) if blob.generation is not None else None,
        )

    def sign_read(self, *, object_path: str, expires_in_seconds: int) -> SignedUpload:
        blob = self._bucket.blob(object_path)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expires_in_seconds),
            method="GET",
        )
        return SignedUpload(url=url, expires_at=expires_at, required_headers={})

    def read_bytes(
        self,
        *,
        object_path: str,
        expected_sha256: str,
        max_bytes: int,
    ) -> bytes:
        blob = self._bucket.blob(object_path)
        digest = hashlib.sha256()
        content = bytearray()
        try:
            with blob.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise StorageObjectValidationError(
                            "stored media exceeds the model input limit"
                        )
                    digest.update(chunk)
        except NotFound as exc:
            raise StorageObjectNotFoundError(object_path) from exc
        if not content:
            raise StorageObjectValidationError("stored media is empty")
        if digest.hexdigest().lower() != expected_sha256.lower():
            raise StorageObjectValidationError("stored media checksum changed after verification")
        return bytes(content)


def create_storage_adapter(settings: Settings | None = None) -> GoogleCloudStorageAdapter:
    runtime = settings or get_settings()
    if not runtime.media_bucket:
        raise RuntimeError("media_bucket is required for Storage access")
    return GoogleCloudStorageAdapter(runtime.media_bucket)


def decode_gcs_checksum(value: str) -> str:
    """Decode a base64 GCS checksum when an adapter needs to compare it."""

    return base64.b64decode(value).hex()


def _content_matches(content_type: str, prefix: bytes) -> bool:
    signatures = {
        "application/pdf": lambda value: value.startswith(b"%PDF-"),
        "audio/m4a": lambda value: len(value) >= 12 and value[4:8] == b"ftyp",
        "audio/mpeg": lambda value: (
            value.startswith(b"ID3")
            or (len(value) >= 2 and value[0] == 0xFF and value[1] & 0xE0 == 0xE0)
        ),
        "audio/ogg": lambda value: value.startswith(b"OggS"),
        "audio/wav": lambda value: (
            len(value) >= 12 and value.startswith(b"RIFF") and value[8:12] == b"WAVE"
        ),
        "audio/webm": lambda value: value.startswith(b"\x1aE\xdf\xa3"),
        "image/jpeg": lambda value: value.startswith(b"\xff\xd8\xff"),
        "image/png": lambda value: value.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": lambda value: (
            len(value) >= 12 and value.startswith(b"RIFF") and value[8:12] == b"WEBP"
        ),
        "text/plain": _is_plain_text,
    }
    return signatures[content_type](prefix)


def _is_plain_text(prefix: bytes) -> bool:
    if b"\x00" in prefix:
        return False
    try:
        prefix.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
