"""Outlook 連結與 Graph 寄信（M2-07b、M2-07c、ADR 0005）。全部用假的 OBO 與假的 HTTP，不連 Microsoft。"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.mail_connection import get_cipher, get_obo_client
from app.config import Settings, get_settings
from app.models import AppUser, UserMailCredential
from app.services import mail_token
from app.services.mailer import GraphMailer, MailAuthError, MailSendError, OutgoingMail

Headers = Callable[[str], dict[str, str]]
SECRET_REFRESH = "refresh-token-super-secret"


@dataclass
class FakeObo:
    """假的 On-Behalf-Of：快取內容含一個假的 refresh token，access token 依使用者區分。"""

    expired: set[str] = field(default_factory=set)

    def exchange(self, user_assertion: str) -> mail_token.OboResult:
        return mail_token.OboResult(
            cache=json.dumps({"user": user_assertion, "refresh": SECRET_REFRESH}),
            scopes=["Mail.Send", "User.Read"],
        )

    def acquire_silent(self, cache: str) -> tuple[str, str]:
        data = json.loads(cache)
        if data["user"] in self.expired:
            raise mail_token.TokenExpired()
        return f"access-for-{data['user']}", cache


@pytest.fixture
def cipher() -> mail_token.TokenCipher:
    return mail_token.TokenCipher(Fernet.generate_key().decode())


@pytest.fixture
def live(client: TestClient, cipher: mail_token.TokenCipher) -> Iterator[FakeObo]:
    """把 API 切成 live 模式（model_construct 跳過「只有正式環境能 live」的檢查，僅限測試）。"""
    base = get_settings()
    settings = Settings.model_construct(**{**base.model_dump(), "mail_mode": "live", "mail_token_key": "x"})
    obo = FakeObo()
    app: FastAPI = client.app  # type: ignore[assignment]
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_obo_client] = lambda: obo
    app.dependency_overrides[get_cipher] = lambda: cipher
    yield obo
    app.dependency_overrides.clear()


def _bearer(headers: dict[str, str], token: str) -> dict[str, str]:
    return {**headers, "Authorization": f"Bearer {token}"}


# ---------- 設定 ----------
def test_m2_07c_live_requires_secret_and_key() -> None:
    with pytest.raises(ValueError, match="ENTRA_CLIENT_SECRET"):
        Settings(env="production", auth_mode="entra", entra_tenant_id="t", entra_client_id="c", mail_mode="live")


LIVE_READY = {
    "auth_mode": "entra",
    "entra_tenant_id": "t",
    "entra_client_id": "c",
    "entra_client_secret": "s",
    "mail_token_key": "k",
    "mail_mode": "live",
}


def test_m2_22_live_in_development_requires_allowlist() -> None:
    with pytest.raises(ValueError, match="MAIL_ALLOWED_RECIPIENTS"):
        Settings(env="development", **LIVE_READY)


def test_m2_22_live_in_development_allowed_with_allowlist() -> None:
    settings = Settings(env="development", mail_allowed_recipients="tester@example.com", **LIVE_READY)
    assert settings.mail_mode == "live"
    assert settings.allowlist == ("tester@example.com",)


def test_m2_22_live_never_in_test_env() -> None:
    with pytest.raises(ValueError, match="測試環境"):
        Settings(env="test", mail_allowed_recipients="tester@example.com", **LIVE_READY)


def test_m2_22_live_in_development_still_needs_secret_and_entra() -> None:
    with pytest.raises(ValueError, match="AUTH_MODE=entra"):
        Settings(
            env="development",
            mail_mode="live",
            mail_allowed_recipients="tester@example.com",
            entra_client_secret="s",
            mail_token_key="k",
        )


def test_m2_22_production_live_without_allowlist_still_allowed() -> None:
    """正式上線時白名單清空，不受這條限制。"""
    assert Settings(env="production", **LIVE_READY).mail_mode == "live"


# ---------- API ----------
def test_m2_07c_sandbox_needs_no_connection(client: TestClient, as_user: Headers) -> None:
    sales = as_user("sales1@example.com")
    assert client.get("/api/v1/me/mail-connection", headers=sales).json() == {
        "mail_mode": "sandbox",
        "status": "not_required",
        "connected_at": None,
        "scopes": [],
        "resumed": 0,
    }
    res = client.post("/api/v1/me/mail-connection", headers=sales)
    assert res.json()["error"]["code"] == "MAIL_SANDBOX"


def test_m2_07c_connect_stores_encrypted_and_hides_token(
    client: TestClient, db: Session, as_user: Headers, live: FakeObo, cipher: mail_token.TokenCipher
) -> None:
    sales = as_user("sales1@example.com")
    assert client.get("/api/v1/me/mail-connection", headers=sales).json()["status"] == "not_connected"
    res = client.post("/api/v1/me/mail-connection", headers=_bearer(sales, "user-a-assertion"))
    assert res.status_code == 200, res.text
    body = res.text
    assert res.json()["status"] == "connected"
    assert SECRET_REFRESH not in body and "access-for" not in body and "assertion" not in body

    cred = db.query(UserMailCredential).one()
    assert SECRET_REFRESH.encode() not in cred.token_cache  # 資料庫裡是加密的
    assert SECRET_REFRESH in cipher.decrypt(cred.token_cache)
    assert "token_cache" not in repr(cred)


def test_m2_07c_disconnect_deletes_row(client: TestClient, db: Session, as_user: Headers, live: FakeObo) -> None:
    sales = as_user("sales1@example.com")
    client.post("/api/v1/me/mail-connection", headers=_bearer(sales, "a"))
    assert client.delete("/api/v1/me/mail-connection", headers=sales).status_code == 204
    assert db.query(UserMailCredential).count() == 0


def test_m2_07c_send_requires_connection_in_live(
    client: TestClient, db: Session, as_user: Headers, live: FakeObo
) -> None:
    from app.domain.company_rules import DomainError
    from app.services import send_service

    sales = as_user("sales1@example.com")
    client.get("/api/v1/me", headers=sales)  # 第一次登入才會建立使用者
    user = db.query(AppUser).filter_by(email="sales1@example.com").one()
    live_settings = get_settings().model_copy(update={"mail_mode": "live"})
    with pytest.raises(DomainError) as e:
        send_service.ensure_mail_ready(db, user, live_settings)
    assert e.value.code == "MAIL_NOT_CONNECTED"
    client.post("/api/v1/me/mail-connection", headers=_bearer(sales, "a"))
    send_service.ensure_mail_ready(db, user, live_settings)  # 連結後就可以
    db.query(UserMailCredential).update({"status": "needs_reconnect"})
    db.commit()
    with pytest.raises(DomainError) as e:
        send_service.ensure_mail_ready(db, user, live_settings)
    assert e.value.code == "MAIL_AUTH_REQUIRED"
    assert client.get("/api/v1/me/mail-connection", headers=sales).json()["status"] == "needs_reconnect"


# ---------- 權杖 ----------
def _user(db: Session, email: str) -> AppUser:
    u = AppUser(email=email, display_name=email.split("@")[0], role="sales")
    db.add(u)
    db.commit()
    return u


def test_m2_07c_only_own_token_is_used(db: Session, cipher: mail_token.TokenCipher) -> None:
    obo = FakeObo()
    a, b = _user(db, "a@example.com"), _user(db, "b@example.com")
    mail_token.connect(db, a, "user-a", obo, cipher)
    mail_token.connect(db, b, "user-b", obo, cipher)
    assert mail_token.access_token_for(db, a.user_id, obo, cipher) == "access-for-user-a"
    assert mail_token.access_token_for(db, b.user_id, obo, cipher) == "access-for-user-b"
    c = _user(db, "c@example.com")
    with pytest.raises(MailAuthError):  # 沒連結的人不能借用別人的權杖
        mail_token.access_token_for(db, c.user_id, obo, cipher)


def test_m2_07c_expired_token_marks_needs_reconnect(db: Session, cipher: mail_token.TokenCipher) -> None:
    obo = FakeObo(expired={"user-a"})
    a = _user(db, "a@example.com")
    mail_token.connect(db, a, "user-a", obo, cipher)
    with pytest.raises(MailAuthError):
        mail_token.access_token_for(db, a.user_id, obo, cipher)
    cred = db.get(UserMailCredential, a.user_id)
    assert cred is not None and cred.status == "needs_reconnect"


def test_m2_07c_key_rotation(db: Session) -> None:
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    token = mail_token.TokenCipher(old).encrypt("cache")
    assert mail_token.TokenCipher(f"{new},{old}").decrypt(token) == "cache"


# ---------- GraphMailer（M2-07b）----------
MAIL = OutgoingMail(draft_id=7, sender_user_id=1, to_email="buyer@example.com", subject="主旨", body_html="<p>內文</p>")


def _graph(handler: Callable[[httpx.Request], httpx.Response]) -> tuple[GraphMailer, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    mailer = GraphMailer(lambda uid: f"token-{uid}", httpx.Client(transport=httpx.MockTransport(wrapped)))
    return mailer, seen


def test_m2_07b_graph_creates_then_sends(caplog: pytest.LogCaptureFixture) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/me/messages"):
            return httpx.Response(201, json={"id": "AAMk", "conversationId": "conv1"})
        return httpx.Response(202)

    mailer, seen = _graph(handler)
    result = mailer.send(MAIL)
    assert (result.graph_message_id, result.conversation_id) == ("AAMk", "conv1")
    assert [r.url.path for r in seen] == ["/v1.0/me/messages", "/v1.0/me/messages/AAMk/send"]
    assert seen[0].headers["Authorization"] == "Bearer token-1"  # 寄件人本人的權杖
    payload = json.loads(seen[0].content)
    assert payload["toRecipients"][0]["emailAddress"]["address"] == "buyer@example.com"
    assert "內文" not in caplog.text and "token-1" not in caplog.text


@pytest.mark.parametrize(
    ("status", "error", "retryable"),
    [(401, MailAuthError, False), (429, MailSendError, True), (503, MailSendError, True), (400, MailSendError, False)],
)
def test_m2_07b_graph_errors(status: int, error: type[Exception], retryable: bool) -> None:
    mailer, _ = _graph(lambda req: httpx.Response(status))
    with pytest.raises(error) as e:
        mailer.send(MAIL)
    assert isinstance(e.value, MailSendError) and e.value.retryable is retryable
