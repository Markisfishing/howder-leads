"""共用測試信箱的 SMTP 連線檢查（ADR 0008）：由信箱擁有人自己手動執行，不進 pytest。

讀 backend/.env 的 SMTP_* 設定，做 STARTTLS＋登入，確認這個信箱還能用密碼登入 SMTP。
加 --send 會寄一封測試信到 MAIL_ALLOWED_RECIPIENTS 的第一個完整 email（白名單是空的就不寄）。
不會印出密碼；錯誤只印代碼與伺服器回的簡短原因。

用法：
    cd backend
    uv run python -m scripts.smtp_check          # 只檢查能不能登入
    uv run python -m scripts.smtp_check --send   # 登入後寄一封測試信給白名單裡的自己
"""

import argparse
import smtplib
import ssl
import sys

from app.config import get_settings
from app.services.mailer import MailSendError, OutgoingMail, SmtpMailer, mask_email

AUTH_HINT = (
    "登入被拒（535）。如果帳號密碼確定正確，通常是 Microsoft 已經停用這個信箱的「密碼登入 SMTP」，"
    "這條路就不能用了，請改走 Graph 授權（ADR 0007）；另外也確認帳號有沒有開兩步驟驗證、"
    "或 Outlook.com 設定裡有沒有關掉 POP/IMAP/SMTP。"
)
# 伺服器回的原因（不含密碼）→ 白話說明。Outlook.com 個人信箱 2024-09-16 起停用密碼登入
REASON_HINTS = [
    ("basic authentication is disabled", "Microsoft 已停用這個信箱的密碼登入（含應用程式密碼），使用者無法自己打開。"),
    ("smtpclientauthentication is disabled", "這個信箱關閉 SMTP 登入，連 OAuth 的 SMTP 也不行；只能走 Graph。"),
    ("5.7.3", "帳號或密碼不正確，或帳號被要求驗證／鎖定，請先用瀏覽器登入 outlook.com 確認。"),
]


def _reason(e: smtplib.SMTPAuthenticationError) -> str:
    raw = e.smtp_error.decode("utf-8", "replace") if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
    return " ".join(raw.split())[:300]


def main() -> int:
    parser = argparse.ArgumentParser(description="檢查共用測試信箱能不能用 SMTP 寄信")
    parser.add_argument("--send", action="store_true", help="登入後寄一封測試信給白名單裡的第一個 email")
    args = parser.parse_args()

    s = get_settings()
    if not (s.smtp_username and s.smtp_password):
        print("請先在 backend/.env 填 SMTP_USERNAME 與 SMTP_PASSWORD")
        return 2
    print(f"連線 {s.smtp_host}:{s.smtp_port}，帳號 {mask_email(s.smtp_username)}")

    try:
        server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds)
        server.starttls(context=ssl.create_default_context())
        server.login(s.smtp_username, s.smtp_password)
        server.quit()
    except smtplib.SMTPAuthenticationError as e:
        reason = _reason(e)
        print(f"失敗：SMTP_AUTH_FAILED（{e.smtp_code}）")
        print(f"伺服器回覆：{reason}")
        hint = next((h for key, h in REASON_HINTS if key in reason.lower()), AUTH_HINT)
        print(f"說明：{hint}")
        return 1
    except (OSError, smtplib.SMTPException) as e:
        print(f"失敗：連不上 SMTP 伺服器（{type(e).__name__}）")
        return 1
    print("登入成功：這個信箱目前可以用 SMTP 寄信")

    if not args.send:
        return 0
    to = next((a for a in s.allowlist if not a.startswith("@")), None)
    if to is None:
        print("MAIL_ALLOWED_RECIPIENTS 沒有完整的 email，不寄測試信")
        return 2
    mailer = SmtpMailer(
        host=s.smtp_host,
        port=s.smtp_port,
        username=s.smtp_username,
        password=s.smtp_password,
        from_name=s.smtp_from_name,
        timeout=s.smtp_timeout_seconds,
    )
    mail = OutgoingMail(
        draft_id=0,
        sender_user_id=0,
        to_email=to,
        subject="厚達電子系統：SMTP 測試信",
        body_html="<p>這是系統的 SMTP 測試信（ADR 0008），收到代表共用測試信箱可以寄信。</p>",
    )
    try:
        mailer.send(mail)
    except MailSendError as e:
        print(f"寄送失敗：{e.code}")
        return 1
    print(f"已寄出測試信到 {mask_email(to)}，請到收件匣與寄件帳號的寄件備份確認")
    return 0


if __name__ == "__main__":
    sys.exit(main())
