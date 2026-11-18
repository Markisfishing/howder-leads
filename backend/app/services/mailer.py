"""寄信（M2-07a、M2-07b）。

- SandboxMailer：開發與測試用，不會寄出任何信，只寫 log（CLAUDE.md 第 6 節第 3 點）。
- GraphMailer：MAIL_MODE=live 時用業務本人的委派權杖呼叫 Microsoft Graph。
  先建立草稿再送出，才拿得到 message id 與 conversation id。
- SmtpMailer：MAIL_TRANSPORT=smtp 時用共用測試信箱的 SMTP＋密碼寄出（ADR 0008，只限開發環境）。
log 只記草稿編號與遮罩後的收件人，不記主旨或內文（CLAUDE.md 第 8 節第 4 點）。
"""

import contextlib
import logging
import smtplib
import ssl
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

import httpx

log = logging.getLogger("howder.mailer")
GRAPH = "https://graph.microsoft.com/v1.0"


@dataclass(frozen=True)
class OutgoingMail:
    draft_id: int
    sender_user_id: int
    to_email: str
    subject: str
    body_html: str

    def __repr__(self) -> str:  # 不把內文印進 log
        return f"OutgoingMail(draft_id={self.draft_id}, to={mask_email(self.to_email)})"


@dataclass(frozen=True)
class SendResult:
    graph_message_id: str | None
    conversation_id: str | None


class MailSendError(Exception):
    """寄送失敗。retryable=True 代表暫時性錯誤（逾時、429、5xx），可以重試。"""

    def __init__(self, code: str, retryable: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class MailAuthError(MailSendError):
    """寄件人的權杖失效，要請業務重新連結 Outlook（ADR 0005）。"""

    def __init__(self, code: str = "MAIL_AUTH_REQUIRED") -> None:
        super().__init__(code, retryable=False)


class Mailer(Protocol):
    def send(self, mail: OutgoingMail) -> SendResult: ...


def mask_email(email: str) -> str:
    """buyer@example.com → b***@example.com"""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


class SandboxMailer:
    """不會真的寄出。email_message 照樣由呼叫端寫進資料庫，方便走完整個流程。"""

    def send(self, mail: OutgoingMail) -> SendResult:
        log.info("[sandbox] 不寄出 draft=%s to=%s", mail.draft_id, mask_email(mail.to_email))
        return SendResult(graph_message_id=f"sandbox-{uuid.uuid4()}", conversation_id=f"sandbox-{uuid.uuid4()}")


class GraphMailer:
    """Microsoft Graph：POST /me/messages 建立草稿 → POST /me/messages/{id}/send。

    token_for(user_id) 回傳寄件人本人的 access token；權杖失效時它會丟 MailAuthError。
    """

    def __init__(self, token_for: Callable[[int], str], client: httpx.Client | None = None) -> None:
        self._token_for = token_for
        self._client = client or httpx.Client(timeout=30)

    def send(self, mail: OutgoingMail) -> SendResult:
        headers = {"Authorization": f"Bearer {self._token_for(mail.sender_user_id)}"}
        message = {
            "subject": mail.subject,
            "body": {"contentType": "HTML", "content": mail.body_html},
            "toRecipients": [{"emailAddress": {"address": mail.to_email}}],
        }
        created = self._call("POST", f"{GRAPH}/me/messages", headers, message)
        data = created.json()
        message_id, conversation_id = data.get("id"), data.get("conversationId")
        if not message_id:
            raise MailSendError("GRAPH_NO_MESSAGE_ID")
        self._call("POST", f"{GRAPH}/me/messages/{message_id}/send", headers, None)
        log.info("graph 已寄出 draft=%s to=%s", mail.draft_id, mask_email(mail.to_email))
        return SendResult(graph_message_id=message_id, conversation_id=conversation_id)

    def _call(self, method: str, url: str, headers: dict[str, str], body: object | None) -> httpx.Response:
        try:
            res = self._client.request(method, url, headers=headers, json=body)
        except httpx.HTTPError as e:
            raise MailSendError("GRAPH_NETWORK_ERROR") from e
        if res.status_code in (401, 403):
            raise MailAuthError()
        if res.status_code == 429 or res.status_code >= 500:
            raise MailSendError(f"GRAPH_HTTP_{res.status_code}")
        if res.status_code >= 400:
            raise MailSendError(f"GRAPH_HTTP_{res.status_code}", retryable=False)
        return res


class SmtpLike(Protocol):
    """smtplib.SMTP 用到的部分；測試換成假的，不連真實伺服器（CLAUDE.md 第 6 節第 4 點）。"""

    def starttls(self, *, context: ssl.SSLContext) -> object: ...
    def login(self, user: str, password: str) -> object: ...
    def send_message(self, msg: MimeMessage) -> object: ...
    def quit(self) -> object: ...


class SmtpMailer:
    """共用測試信箱（Outlook.com）：STARTTLS → 帳號密碼登入 → 寄出（ADR 0008）。

    所有業務都從同一個信箱寄出，信會留在那個信箱的寄件備份；客戶回信也會回到那個信箱。
    密碼只從設定讀，不寫進 log 或錯誤訊息。
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_name: str,
        timeout: float = 30.0,
        connect: Callable[[], SmtpLike] | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._from = formataddr((from_name, username))
        self._domain = username.partition("@")[2] or None
        self._connect = connect or (lambda: smtplib.SMTP(host, port, timeout=timeout))

    def build(self, mail: OutgoingMail) -> MimeMessage:
        msg = MimeMessage()
        msg["From"] = self._from
        msg["To"] = mail.to_email
        msg["Subject"] = mail.subject
        msg["Message-ID"] = make_msgid(domain=self._domain)
        msg.set_content("這封信是 HTML 格式，請用支援 HTML 的郵件程式開啟。")
        msg.add_alternative(mail.body_html, subtype="html")
        return msg

    def send(self, mail: OutgoingMail) -> SendResult:
        msg = self.build(mail)
        try:
            server = self._connect()
        except (OSError, smtplib.SMTPException) as e:
            raise MailSendError("SMTP_NETWORK_ERROR") from e
        try:
            server.starttls(context=ssl.create_default_context())
            server.login(self._username, self._password)
            server.send_message(msg)
        except smtplib.SMTPAuthenticationError as e:
            # Microsoft 停用密碼登入時也會回這個錯；重試沒有用（ADR 0008）
            raise MailSendError("SMTP_AUTH_FAILED", retryable=False) from e
        except smtplib.SMTPRecipientsRefused as e:
            raise MailSendError("SMTP_RECIPIENT_REFUSED", retryable=False) from e
        except smtplib.SMTPResponseException as e:
            raise MailSendError(f"SMTP_{e.smtp_code}", retryable=400 <= e.smtp_code < 500) from e
        except (OSError, smtplib.SMTPException) as e:
            raise MailSendError("SMTP_NETWORK_ERROR") from e
        finally:
            with contextlib.suppress(OSError, smtplib.SMTPException):
                server.quit()
        log.info("smtp 已寄出 draft=%s to=%s", mail.draft_id, mask_email(mail.to_email))
        return SendResult(graph_message_id=str(msg["Message-ID"]), conversation_id=None)
