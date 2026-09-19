from pydantic import BaseModel, Field

from app.db.enums import UserRole
from app.schemas.auth import Email, PasswordField, UserOut

__all__ = ["UserCreate", "UserOut", "UserPatch"]


class UserCreate(BaseModel):
    email: Email
    full_name: str = Field(min_length=1, max_length=200)
    password: str = PasswordField
    role: UserRole = UserRole.officer
    # New accounts start with a temporary password handed over by the admin.
    must_change_password: bool = True


class UserPatch(BaseModel):
    """Admin edits: any subset. `new_password` resets the password (user must change it)."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None
    new_password: str | None = Field(default=None, min_length=10, max_length=256)
