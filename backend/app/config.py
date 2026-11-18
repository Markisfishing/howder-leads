"""系統設定：全部從環境變數或 backend/.env 讀取，欄位說明見 .env.example。"""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://postgres@127.0.0.1:5432/howder"

    # 登入：dev 模式用 X-Dev-User header 模擬登入，只能在非正式環境使用
    auth_mode: Literal["dev", "entra"] = "dev"
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    bootstrap_admin_emails: str = ""  # 逗號分隔；第一次登入就給 admin 角色

    # 寄信：sandbox 不會真的寄出（CLAUDE.md 第 6 節）
    mail_mode: Literal["sandbox", "live"] = "sandbox"
    # live 寄信用（ADR 0005）：機密用戶端密碼、權杖快取加密金鑰（Fernet，逗號分隔可放多把以便換金鑰）
    entra_client_secret: str = ""
    mail_token_key: str = ""
    # 寄送限制（F-MAIL-6、F-MAIL-7）；「一天」以台灣時間計算
    daily_send_limit: int = 50
    send_per_minute: int = 10
    send_day_start_hour: int = 9
    recent_send_days: int = 14
    # 背景工作：沒收到 NOTIFY 時多久輪詢一次
    worker_poll_seconds: float = 5.0

    # AI 寫信（ADR 0006）：預設用本機 Ollama（OpenAI 相容 API）；公司 GPU 主機確認後只改網址與模型名稱
    llm_provider: Literal["local", "claude"] = "local"
    local_llm_base_url: str = "http://127.0.0.1:11434/v1"
    local_llm_model: str = "qwen3:8b"
    llm_timeout_seconds: float = 120.0
    llm_concurrency: int = 2

    # MLE function 直接呼叫匯入 API 用的金鑰
    import_api_key: str = ""

    lock_days: int = 30
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @model_validator(mode="after")
    def _guard_production(self) -> "Settings":
        if self.env == "production" and self.auth_mode == "dev":
            raise ValueError("正式環境不可以使用 AUTH_MODE=dev")
        if self.env != "production" and self.mail_mode == "live":
            raise ValueError("只有正式環境可以設定 MAIL_MODE=live")
        if self.mail_mode == "live" and not (self.entra_client_secret and self.mail_token_key):
            raise ValueError("MAIL_MODE=live 需要 ENTRA_CLIENT_SECRET 與 MAIL_TOKEN_KEY（ADR 0005）")
        if self.mail_mode == "live" and self.auth_mode != "entra":
            raise ValueError("MAIL_MODE=live 需要 AUTH_MODE=entra")
        if self.llm_concurrency < 1 or self.llm_timeout_seconds <= 0:
            raise ValueError("LLM_CONCURRENCY 必須大於 0，LLM_TIMEOUT_SECONDS 必須大於 0")
        if self.daily_send_limit < 1 or self.send_per_minute < 1:
            raise ValueError("DAILY_SEND_LIMIT 與 SEND_PER_MINUTE 必須大於 0")
        if self.auth_mode == "entra" and not (self.entra_tenant_id and self.entra_client_id):
            raise ValueError("AUTH_MODE=entra 需要 ENTRA_TENANT_ID 與 ENTRA_CLIENT_ID")
        return self

    @property
    def admin_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.bootstrap_admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
