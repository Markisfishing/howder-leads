"""共用測試信箱 SMTP 寄信（M2-24、ADR 0008）。一律用假的 SMTP，不連真實伺服器（CLAUDE.md 第 6 節第 4 點）。"""

import logging
import smtplib
import ssl
from collections.abc import Callable, Iterator
from email.message import EmailMessage as MimeMessage

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import AppUser
from app.services import send_service
from app.services.mailer import MailSendError, OutgoingMail, SandboxMailer, SmtpMailer
from app.workers.runner import build_mailer

Headers = Callable[[str], dict[str, str]]
PASSWORD = "fake-password-do-not-log"
MAIL = OutgoingMail(
    draft_id=7, sender_user_id=1, to_email="buyer@example.com", subject="合作邀請", body_html="<p>您好</p>"
)
SMTP_READY = {
    "mail_mode": "live",
    "mail_transport": "smtp",
    "smtp_username": "shared@example.com",
    "smtp_password": PASSWORD,
    "mail_allowed_recipients": "buyer@example.com",
}


class FakeSmtp:
    def __init__(self, fail_at: str | None = None, error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.sent: list[MimeMessage] = []
        self.login_args: tuple[str, str] | None = None
        self._fail_at, self._error = fail_at, error

    def _step(self, name: str) -> None:
        self.calls.append(name)
        if self._fail_at == name and self._error is not None:
            raise self._error

    def starttls(self, *, context: ssl.SSLContext) -> object:
        self._step("starttls")
        return None

    def login(self, user: str, password: str) -> object:
        self.login_args = (user, password)
        self._step("login")
        return None

    def send_message(self, msg: MimeMessage) -> object:
        self._step("send_message")
        self.sent.append(msg)
        return None

    def quit(self) -> object:
        self.calls.append("quit")
        return None


def _mailer(fake: FakeSmtp) -> SmtpMailer:
    return SmtpMailer(
        host="smtp.example.com",
        port=587,
        username="shared@example.com",
        password=PASSWORD,
        from_name="厚達電子",
        connect=lambda: fake,
    )


# ---------- SmtpMailer ----------
def test_m2_24_smtp_sends_html_with_starttls_and_login(caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeSmtp()
    with caplog.at_level(logging.INFO):
        result = _mailer(fake).send(MAIL)
    assert fake.calls == ["starttls", "login", "send_message", "quit"]
    assert fake.login_args == ("shared@example.com", PASSWORD)
    msg = fake.sent[0]
    assert msg["To"] == "buyer@example.com"
    assert msg["Subject"] == "合作邀請"
    assert "shared@example.com" in msg["From"]
    html = msg.get_body(preferencelist=("html",))
    assert html is not None and "<p>您好</p>" in html.get_content()
    assert result.graph_message_id == msg["Message-ID"] and result.graph_message_id.endswith("@example.com>")
    # log 只有遮罩後的收件人，沒有密碼、主旨或內文（CLAUDE.md 第 8 節第 4 點）
    assert PASSWORD not in caplog.text and "合作邀請" not in caplog.text and "buyer@" not in caplog.text


@pytest.mark.parametrize(
    "fail_at,error,code,retryable",
    [
        (
            "login",
            smtplib.SMTPAuthenticationError(535, b"5.7.139 basic authentication is disabled"),
            "SMTP_AUTH_FAILED",
            False,
        ),
        (
            "send_message",
            smtplib.SMTPRecipientsRefused({"buyer@example.com": (550, b"no")}),
            "SMTP_RECIPIENT_REFUSED",
            False,
        ),
        ("send_message", smtplib.SMTPDataError(451, b"try later"), "SMTP_451", True),
        ("send_message", smtplib.SMTPDataError(554, b"spam"), "SMTP_554", False),
        ("starttls", OSError("timeout"), "SMTP_NETWORK_ERROR", True),
    ],
)
def test_m2_24_smtp_errors_map_to_codes(fail_at: str, error: Exception, code: str, retryable: bool) -> None:
    fake = FakeSmtp(fail_at=fail_at, error=error)
    with pytest.raises(MailSendError) as e:
        _mailer(fake).send(MAIL)
    assert (e.value.code, e.value.retryable) == (code, retryable)
    assert PASSWORD not in str(e.value)
    assert fake.calls[-1] == "quit"  # 失敗也會關閉連線


def test_m2_24_smtp_connect_failure_is_retryable() -> None:
    def boom() -> FakeSmtp:
        raise OSError("connection refused")

    mailer = SmtpMailer(
        host="h", port=587, username="shared@example.com", password=PASSWORD, from_name="x", connect=boom
    )
    with pytest.raises(MailSendError) as e:
        mailer.send(MAIL)
    assert (e.value.code, e.value.retryable) == ("SMTP_NETWORK_ERROR", True)


# ---------- 設定 ----------
def test_m2_24_smtp_live_in_development_needs_no_entra() -> None:
    s = Settings(env="development", **SMTP_READY)  # type: ignore[arg-type]
    assert (s.mail_mode, s.mail_transport, s.auth_mode) == ("live", "smtp", "dev")


def test_m2_24_smtp_live_requires_username_and_password() -> None:
    with pytest.raises(ValueError, match="SMTP_PASSWORD"):
        Settings(env="development", **{**SMTP_READY, "smtp_password": ""})  # type: ignore[arg-type]


def test_m2_24_smtp_live_still_requires_allowlist_in_development() -> None:
    with pytest.raises(ValueError, match="MAIL_ALLOWED_RECIPIENTS"):
        Settings(env="development", **{**SMTP_READY, "mail_allowed_recipients": ""})  # type: ignore[arg-type]


def test_m2_24_smtp_never_in_production_or_test() -> None:
    with pytest.raises(ValueError, match="開發環境"):
        Settings(env="production", auth_mode="entra", entra_tenant_id="t", entra_client_id="c", mail_transport="smtp")
    with pytest.raises(ValueError, match="測試環境"):
        Settings(env="test", **SMTP_READY)  # type: ignore[arg-type]


def test_m2_24_worker_builds_smtp_mailer_only_when_live() -> None:
    live = Settings(env="development", **SMTP_READY)  # type: ignore[arg-type]
    assert isinstance(build_mailer(live, lambda: None), SmtpMailer)  # type: ignore[arg-type, return-value]
    sandbox = Settings(env="development", mail_transport="smtp")
    assert isinstance(build_mailer(sandbox, lambda: None), SandboxMailer)  # type: ignore[arg-type, return-value]


# ---------- API 與寄送前檢查 ----------
@pytest.fixture
def smtp_live(client: TestClient) -> Iterator[Settings]:
    """把 API 切成 live＋共用 SMTP（model_construct 跳過啟動檢查，僅限測試；不會真的寄出）。"""
    settings = Settings.model_construct(**{**get_settings().model_dump(), **SMTP_READY})
    app: FastAPI = client.app  # type: ignore[assignment]
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.clear()


def test_m2_24_shared_mailbox_needs_no_outlook_connection(
    client: TestClient, db: Session, as_user: Headers, smtp_live: Settings
) -> None:
    sales = as_user("sales1@example.com")
    body = client.get("/api/v1/me/mail-connection", headers=sales).json()
    assert (body["mail_mode"], body["status"]) == ("live", "not_required")
    res = client.post("/api/v1/me/mail-connection", headers=sales)
    assert res.status_code == 409 and res.json()["error"]["code"] == "MAIL_SHARED_MAILBOX"
    user = db.query(AppUser).filter_by(email="sales1@example.com").one()
    send_service.ensure_mail_ready(db, user, smtp_live)  # 沒有連結 Outlook 也可以寄
