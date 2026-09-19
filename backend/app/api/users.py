"""/users (admin): list, create, patch (role, active, reset password). Task 3.4.

Last-admin protection: the last active admin can neither be deactivated nor demoted.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import AdminUser, DbDep
from app.db.enums import UserRole
from app.repositories import UserRepository
from app.schemas.common import Page, PageParams, page_params
from app.schemas.users import UserCreate, UserOut, UserPatch

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger(__name__)


@router.get("", response_model=Page[UserOut])
def list_users(
    _: AdminUser, db: DbDep, paging: Annotated[PageParams, Depends(page_params)]
) -> Page[UserOut]:
    rows, total = UserRepository(db).list_page(paging.offset, paging.page_size)
    return Page(
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, admin: AdminUser, db: DbDep) -> UserOut:
    repo = UserRepository(db)
    if repo.get_by_email(body.email) is not None:
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    user = repo.create(
        body.email, body.full_name, body.password, body.role, body.must_change_password
    )
    db.commit()
    logger.info("user created", extra={"user_id": str(user.id), "by": str(admin.id)})
    return UserOut.model_validate(user)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, _: AdminUser, db: DbDep) -> UserOut:
    user = UserRepository(db).get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
def patch_user(user_id: uuid.UUID, body: UserPatch, admin: AdminUser, db: DbDep) -> UserOut:
    repo = UserRepository(db)
    user = repo.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    losing_admin = user.role == UserRole.admin and user.is_active
    becomes_non_admin = body.role is not None and body.role != UserRole.admin
    becomes_inactive = body.is_active is False
    if losing_admin and (becomes_non_admin or becomes_inactive) and repo.count_active_admins() <= 1:
        raise HTTPException(
            status_code=409, detail="Cannot demote or deactivate the last active administrator"
        )
    if user.id == admin.id and becomes_inactive:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account")

    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.new_password is not None:
        repo.set_password(user, body.new_password, must_change=True)
    db.flush()
    db.commit()
    logger.info("user updated", extra={"user_id": str(user.id), "by": str(admin.id)})
    return UserOut.model_validate(user)
