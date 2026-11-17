"""業務的 Outlook 寄信權杖（M2-07c、ADR 0005）。

- 連結：前端送來的 access token（audience 是本系統）用 On-Behalf-Of 換成 Graph 權杖。
- MSAL 權杖快取（含 refresh token）用 Fernet 加密後存在 user_mail_credential，一位業務一筆。
- 寄信時只讀寄件人本人那一筆；換不到權杖就標成 needs_reconnect。
權杖、快取、金鑰都不可以出現在 log、錯誤訊息或 API 回應。
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.company_rules import DomainError
from app.models import ActivityLog, AppUser, UserMailCredential
from app.services.mailer import MailAuthError

SCOPES = ["https://graph.microsoft.com/Mail.Send", "https://graph.microsoft.com/User.Read"]


class TokenExpired(Exception):  # noqa: N818
    """refresh token 失效（太久沒用、改密碼、管理員撤銷）。"""


@dataclass(frozen=True)
class OboResult:
    cache: str  # MSAL 序列化後的權杖快取（明文，只在記憶體裡）
    scopes: list[str]


class OboClient(Protocol):
    def exchange(self, user_assertion: str) -> OboResult: ...

    def acquire_silent(self, cache: str) -> tuple[str, str]:
        """回傳 (access_token, 更新後的快取)；失效時丟 TokenExpired。"""
        ...


class TokenCipher:
    """MultiFernet：第一把金鑰加密，所有金鑰都能解密，方便換金鑰。"""

    def __init__(self, keys: str) -> None:
        parts = [k.strip() for k in keys.split(",") if k.strip()]
        if not parts:
            raise ValueError("MAIL_TOKEN_KEY 沒有設定")
        self._f = MultiFernet([Fernet(k.encode()) for k in parts])

    def encrypt(self, plain: str) -> bytes:
        return self._f.encrypt(plain.encode())

    def decrypt(self, token: bytes) -> str:
        try:
            return self._f.decrypt(token).decode()
        except InvalidToken as e:
            raise TokenExpired() from e


class MsalOboClient:
    """正式環境用 MSAL Python。測試一律用假的 OboClient（CLAUDE.md 第 6 節第 4 點）。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _app(self, cache: object | None = None) -> object:
        import msal

        return msal.ConfidentialClientApplication(
            self._settings.entra_client_id,
            authority=f"https://login.microsoftonline.com/{self._settings.entra_tenant_id}",
            client_credential=self._settings.entra_client_secret,
            token_cache=cache,
        )

    def exchange(self, user_assertion: str) -> OboResult:
        import msal

        cache = msal.SerializableTokenCache()
        app = self._app(cache)
        result = app.acquire_token_on_behalf_of(user_assertion, scopes=SCOPES)  # type: ignore[attr-defined]
        if "access_token" not in result:
            raise DomainError("MAIL_CONNECT_FAILED", "無法取得 Outlook 寄信權限，請確認管理員已同意 Mail.Send", 409)
        granted = str(result.get("scope", "")).split()
        return OboResult(cache=cache.serialize(), scopes=granted)

    def acquire_silent(self, cache: str) -> tuple[str, str]:
        import msal

        token_cache = msal.SerializableTokenCache()
        token_cache.deserialize(cache)
        app = self._app(token_cache)
        accounts = app.get_accounts()  # type: ignore[attr-defined]
        result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None  # type: ignore[attr-defined]
        if not result or "access_token" not in result:
            raise TokenExpired()
        return str(result["access_token"]), token_cache.serialize()


def _now() -> datetime:
    return datetime.now(UTC)


def status(db: Session, user: AppUser) -> UserMailCredential | None:
    return db.get(UserMailCredential, user.user_id)


def connect(db: Session, user: AppUser, user_assertion: str, obo: OboClient, cipher: TokenCipher) -> UserMailCredential:
    result = obo.exchange(user_assertion)
    cred = db.get(UserMailCredential, user.user_id)
    if cred is None:
        cred = UserMailCredential(user_id=user.user_id, token_cache=b"", scopes=[])
        db.add(cred)
    cred.token_cache = cipher.encrypt(result.cache)
    cred.scopes = result.scopes
    cred.status = "connected"
    cred.connected_at = _now()
    cred.last_error = None
    db.add(ActivityLog(user_id=user.user_id, action="mail_connect"))
    db.commit()
    return cred


def disconnect(db: Session, user: AppUser) -> None:
    """中斷連結：直接刪除那一筆（權杖不需要保留稽核），寫 activity_log。"""
    cred = db.get(UserMailCredential, user.user_id)
    if cred is not None:
        db.delete(cred)
        db.add(ActivityLog(user_id=user.user_id, action="mail_disconnect"))
        db.commit()


def access_token_for(db: Session, user_id: int, obo: OboClient, cipher: TokenCipher) -> str:
    """worker 寄信用：只讀寄件人本人那一筆。失效就標成 needs_reconnect 並丟 MailAuthError。"""
    cred = db.get(UserMailCredential, user_id)
    if cred is None or cred.status != "connected":
        raise MailAuthError()
    try:
        token, new_cache = obo.acquire_silent(cipher.decrypt(cred.token_cache))
    except TokenExpired:
        cred.status = "needs_reconnect"
        cred.last_error = "TOKEN_EXPIRED"
        db.commit()
        raise MailAuthError() from None
    cred.token_cache = cipher.encrypt(new_cache)
    cred.last_used_at = _now()
    db.commit()
    return token
