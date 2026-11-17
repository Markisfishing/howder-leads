"""登入：驗證 Microsoft Entra ID 的 access token，並取得或建立 app_user。

- AUTH_MODE=entra：前端用 MSAL 取得 access token，放在 Authorization: Bearer。
  這裡用 Entra 公開的 JWKS 驗證簽章、audience（本系統的 client id）、issuer（公司租用戶）。
- AUTH_MODE=dev：前端送 X-Dev-User: <email>，只能在非正式環境使用（config 會擋）。
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError
from app.models import AppUser


@dataclass(frozen=True)
class Identity:
    email: str
    display_name: str


@lru_cache
def _jwks_client(tenant_id: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys")


def verify_entra_token(token: str, settings: Settings, signing_key: Any = None) -> Identity:
    """驗證 Entra access token。signing_key 只給測試注入用，正式環境從 JWKS 取得。"""
    try:
        key = signing_key or _jwks_client(settings.entra_tenant_id).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=[settings.entra_client_id, f"api://{settings.entra_client_id}"],
            issuer=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
        )
    except jwt.PyJWTError as exc:
        raise AppError("INVALID_TOKEN", "登入已失效，請重新登入", 401) from exc
    email = claims.get("preferred_username") or claims.get("email") or claims.get("upn")
    if not email:
        raise AppError("INVALID_TOKEN", "登入資訊缺少 email", 401)
    return Identity(email=str(email).lower(), display_name=str(claims.get("name") or email))


def get_or_create_user(db: Session, identity: Identity, settings: Settings) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.email == identity.email))
    if user is None:
        role = "admin" if identity.email in settings.admin_emails else "sales"
        user = AppUser(email=identity.email, display_name=identity.display_name, role=role)
        db.add(user)
        db.commit()
    if not user.is_active:
        raise AppError("USER_DISABLED", "這個帳號已停用，請聯絡管理員", 403)
    return user
