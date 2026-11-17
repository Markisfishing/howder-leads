"""業務自己的 Outlook 寄信連結（M2-07c、ADR 0005）。

回應只有狀態、連結時間、權限範圍，不回傳任何權杖內容。
sandbox 模式不需要連結（信不會真的寄出）。
"""

from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.domain.company_rules import DomainError
from app.models import AppUser
from app.services import mail_token, send_service

router = APIRouter()


class MailConnectionOut(BaseModel):
    mail_mode: Literal["sandbox", "live"]
    status: Literal["not_required", "not_connected", "connected", "needs_reconnect"]
    connected_at: datetime | None = None
    scopes: list[str] = []
    resumed: int = 0  # 重新連結後自動恢復排程的封數


@lru_cache
def _cipher(key: str) -> mail_token.TokenCipher:
    return mail_token.TokenCipher(key)


def get_obo_client(settings: Settings = Depends(get_settings)) -> mail_token.OboClient:
    """測試用 app.dependency_overrides 換成假的 OBO（CLAUDE.md 第 6 節第 4 點）。"""
    return mail_token.MsalOboClient(settings)


def get_cipher(settings: Settings = Depends(get_settings)) -> mail_token.TokenCipher | None:
    """沒設定金鑰時回傳 None（sandbox 不需要）；live 時在 connect 裡報錯。"""
    return _cipher(settings.mail_token_key) if settings.mail_token_key else None


def _out(db: Session, user: AppUser, settings: Settings, resumed: int = 0) -> MailConnectionOut:
    if settings.mail_mode != "live":
        return MailConnectionOut(mail_mode=settings.mail_mode, status="not_required")
    cred = mail_token.status(db, user)
    if cred is None:
        return MailConnectionOut(mail_mode="live", status="not_connected")
    return MailConnectionOut(
        mail_mode="live",
        status="connected" if cred.status == "connected" else "needs_reconnect",
        connected_at=cred.connected_at,
        scopes=list(cred.scopes),
        resumed=resumed,
    )


@router.get("/me/mail-connection", response_model=MailConnectionOut)
def get_connection(
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MailConnectionOut:
    return _out(db, user, settings)


@router.post("/me/mail-connection", response_model=MailConnectionOut)
def connect(
    authorization: str | None = Header(default=None),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    obo: mail_token.OboClient = Depends(get_obo_client),
    cipher: mail_token.TokenCipher | None = Depends(get_cipher),
) -> MailConnectionOut:
    if settings.mail_mode != "live":
        raise DomainError("MAIL_SANDBOX", "目前是測試模式，信不會真的寄出，不需要連結 Outlook", 409)
    if cipher is None:
        raise DomainError("MAIL_NOT_CONFIGURED", "系統尚未設定寄信金鑰，請聯絡管理員", 503)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise DomainError("UNAUTHORIZED", "請先登入", 401)
    mail_token.connect(db, user, authorization[7:], obo, cipher)
    resumed = send_service.resume_paused(db, user, datetime.now(UTC), settings)
    return _out(db, user, settings, resumed)


@router.delete("/me/mail-connection", status_code=204)
def disconnect(user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    mail_token.disconnect(db, user)
    return Response(status_code=204)
