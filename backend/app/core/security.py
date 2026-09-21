"""Password hashing (argon2id) and JWT access tokens (techspec §8)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

MIN_PASSWORD_LENGTH = 10
JWT_ALGORITHM = "HS256"
_ph = PasswordHasher()


def hash_password(plain: str) -> str:
    if len(plain) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return str(_ph.hash(plain))


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bool(_ph.verify(hashed, plain))
    except VerifyMismatchError:
        return False


class TokenError(Exception):
    """Token missing, expired, malformed or signed with another key."""


def create_access_token(
    user_id: uuid.UUID,
    role: str,
    secret: str,
    expires_minutes: int,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return str(jwt.encode(payload, secret, algorithm=JWT_ALGORITHM))


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    """Return the claims or raise TokenError. Never trust `role` alone: routes re-load the
    user so deactivation and role changes take effect immediately."""
    try:
        claims: dict[str, Any] = jwt.decode(
            token, secret, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "exp"]}
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    try:
        uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise TokenError("invalid subject") from exc
    return claims
