import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.enums import UserRole
from app.db.models import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(func.lower(User.email) == email.lower()))

    def list_all(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.created_at)))

    def list_page(self, offset: int, limit: int) -> tuple[list[User], int]:
        total = int(self.db.scalar(select(func.count()).select_from(User)) or 0)
        rows = self.db.scalars(
            select(User).order_by(User.created_at, User.id).offset(offset).limit(limit)
        )
        return list(rows), total

    def count_active_admins(self) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == UserRole.admin, User.is_active.is_(True))
            )
            or 0
        )

    def create(
        self,
        email: str,
        full_name: str,
        password: str,
        role: UserRole = UserRole.officer,
        must_change_password: bool = False,
    ) -> User:
        user = User(
            email=email.strip().lower(),
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            role=role,
            must_change_password=must_change_password,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def set_password(self, user: User, password: str, must_change: bool = False) -> None:
        user.password_hash = hash_password(password)
        user.must_change_password = must_change
        self.db.flush()
