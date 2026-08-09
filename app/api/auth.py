from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from google.auth import exceptions as google_auth_exceptions
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from app.config.settings import Settings
from app.domain.authorization import AuthenticatedUser, AuthenticationRequiredError
from app.domain.enums import UserStatus
from app.domain.models import User
from app.repositories.membership import IdentityRepository


@dataclass(frozen=True)
class VerifiedIdentity:
    subject: str
    email: str | None


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedIdentity:
        """Verify one bearer token and return safe identity claims."""


class FirebaseTokenVerifier:
    """Verify Firebase Authentication tokens with Google's official helper.

    Source: https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.id_token.html#google.oauth2.id_token.verify_firebase_token
    """

    def __init__(self, settings: Settings, *, request: Request | None = None) -> None:
        if not settings.auth_audience:
            raise ValueError("auth_audience is required for Firebase token verification")
        self._audience = settings.auth_audience
        self._issuer = settings.auth_issuer
        self._request = request or Request()

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            claims = id_token.verify_firebase_token(
                token,
                self._request,
                audience=self._audience,
            )
        except (ValueError, google_auth_exceptions.GoogleAuthError) as exc:
            raise AuthenticationRequiredError("identity token verification failed") from exc

        if self._issuer and claims.get("iss") != self._issuer:
            raise AuthenticationRequiredError("identity token issuer is not allowed")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationRequiredError("identity token subject is missing")
        email_claim = claims.get("email")
        email = email_claim if isinstance(email_claim, str) else None
        return VerifiedIdentity(subject=subject, email=email)


def authenticate_bearer(
    authorization_header: str | None,
    verifier: TokenVerifier,
    identities: IdentityRepository,
) -> AuthenticatedUser:
    token = _extract_bearer_token(authorization_header)
    identity = verifier.verify(token)
    user = identities.get_by_subject(identity.subject)
    if user is None:
        raise AuthenticationRequiredError("verified identity is not a registered user")
    if user.status is not UserStatus.ACTIVE:
        raise AuthenticationRequiredError("registered user is disabled")
    return AuthenticatedUser(
        user_id=user.id,
        subject=identity.subject,
        email=identity.email or user.email,
    )


def authenticate_or_provision_bearer(
    authorization_header: str | None,
    verifier: TokenVerifier,
    identities: IdentityRepository,
    *,
    display_name: str | None = None,
) -> AuthenticatedUser:
    """Verify a token and create one canonical user when the subject is new.

    The subject-derived opaque ID makes repeated bootstrap calls converge on the
    same user. It is never used as a display name or role source.
    """

    token = _extract_bearer_token(authorization_header)
    identity = verifier.verify(token)
    user = identities.get_by_subject(identity.subject)
    if user is None:
        if not identity.email:
            raise AuthenticationRequiredError("verified identity has no usable email")
        user = identities.provision(
            User(
                id=canonical_user_id(identity.subject),
                identity_subject=identity.subject,
                display_name=display_name or "Oga user",
                email=identity.email,
            )
        )
    if user.status is not UserStatus.ACTIVE:
        raise AuthenticationRequiredError("registered user is disabled")
    return AuthenticatedUser(user_id=user.id, subject=identity.subject, email=user.email)


def canonical_user_id(subject: str) -> str:
    return f"usr_{sha256(subject.encode('utf-8')).hexdigest()[:32]}"


def _extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header:
        raise AuthenticationRequiredError("Authorization Bearer token is required")
    scheme, separator, token = authorization_header.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationRequiredError("Authorization header must use Bearer authentication")
    return token.strip()
