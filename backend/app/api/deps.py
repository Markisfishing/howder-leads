"""API 共用相依：資料庫 session、目前使用者、角色檢查。"""

from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.errors import AppError
from app.models import AppUser
from app.services.auth import Identity, get_or_create_user, verify_entra_token


def current_user(
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AppUser:
    if settings.auth_mode == "dev":
        if not x_dev_user:
            raise AppError("UNAUTHORIZED", "請先登入", 401)
        email = x_dev_user.strip().lower()
        identity = Identity(email=email, display_name=email.split("@")[0])
    else:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise AppError("UNAUTHORIZED", "請先登入", 401)
        identity = verify_entra_token(authorization[7:], settings)
    return get_or_create_user(db, identity, settings)


def require_roles(*roles: str) -> Callable[[AppUser], AppUser]:
    def _check(user: AppUser = Depends(current_user)) -> AppUser:
        if user.role not in roles:
            raise AppError("FORBIDDEN", "沒有權限使用這個功能", 403)
        return user

    return _check


require_admin = require_roles("admin")
