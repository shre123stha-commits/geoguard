"""FastAPI dependencies: DB session, current user, role guards (techspec §8)."""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import TokenError, decode_access_token
from app.db.enums import UserRole
from app.db.models import User
from app.db.session import get_db
from app.repositories import UserRepository

_bearer = HTTPBearer(auto_error=False)


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


DbDep = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_current_user(
    db: DbDep,
    settings: SettingsDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        claims = decode_access_token(creds.credentials, settings.jwt_secret.get_secret_value())
    except TokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None
    user = UserRepository(db).get(uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account not found or deactivated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_active_user(user: CurrentUser) -> User:
    """Like CurrentUser, but a user who must change their password can only do that."""
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Password change required before continuing")
    return user


ActiveUser = Annotated[User, Depends(get_active_user)]


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    def _guard(user: ActiveUser) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return _guard


AdminUser = Annotated[User, Depends(require_roles(UserRole.admin))]
ReviewerUser = Annotated[User, Depends(require_roles(UserRole.admin, UserRole.officer))]
