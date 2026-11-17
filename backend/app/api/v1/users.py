"""使用者：/me 與管理員的使用者管理。"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_admin
from app.db import get_db
from app.errors import AppError
from app.models import AppUser

router = APIRouter()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    email: str
    display_name: str
    role: str
    is_active: bool


class UserPatch(BaseModel):
    role: Literal["sales", "manager", "admin"] | None = None
    is_active: bool | None = None


@router.get("/me", response_model=UserOut)
def me(user: AppUser = Depends(current_user)) -> AppUser:
    return user


@router.get("/admin/users", response_model=list[UserOut])
def list_users(_: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> list[AppUser]:
    return list(db.scalars(select(AppUser).order_by(AppUser.user_id)))


@router.patch("/admin/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserPatch,
    admin: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AppUser:
    user = db.get(AppUser, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "找不到這個使用者", 404)
    if user.user_id == admin.user_id and (body.role not in (None, "admin") or body.is_active is False):
        raise AppError("CANNOT_DEMOTE_SELF", "不能移除自己的管理員權限", 409)
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    db.commit()
    return user
