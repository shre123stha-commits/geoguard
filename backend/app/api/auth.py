"""/auth: login, me, change-password (techspec §6, §8). Task 3.1."""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.core.security import create_access_token, verify_password
from app.repositories import UserRepository
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse, UserOut
from app.services.throttle import LoginThrottle

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _throttle(request: Request) -> LoginThrottle:
    t: LoginThrottle = request.app.state.login_throttle
    return t


def _too_many(wait: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=f"Too many failed attempts. Try again in {wait} seconds.",
        headers={"Retry-After": str(wait)},
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: DbDep, settings: SettingsDep) -> TokenResponse:
    throttle = _throttle(request)
    key = f"{body.email}|{_client_ip(request)}"
    wait = throttle.retry_after(key)
    if wait:
        raise _too_many(wait)
    repo = UserRepository(db)
    user = repo.get_by_email(body.email)
    ok = user is not None and user.is_active and verify_password(body.password, user.password_hash)
    if not ok or user is None:
        cooldown = throttle.record_failure(key)
        logger.info("login failed", extra={"email": body.email, "cooldown_s": cooldown})
        if cooldown:
            raise _too_many(cooldown)
        # Same message for unknown email, wrong password and deactivated account.
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    throttle.reset(key)
    token = create_access_token(
        user.id,
        user.role.value,
        settings.jwt_secret.get_secret_value(),
        settings.jwt_expire_minutes,
    )
    logger.info("login ok", extra={"user_id": str(user.id)})
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/change-password", response_model=UserOut)
def change_password(body: ChangePasswordRequest, user: CurrentUser, db: DbDep) -> UserOut:
    """Allowed even when `must_change_password` is set (it is the only thing allowed then)."""
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="New password must differ from the current one")
    UserRepository(db).set_password(user, body.new_password, must_change=False)
    db.commit()
    logger.info("password changed", extra={"user_id": str(user.id)})
    return UserOut.model_validate(user)
