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
        if self.auth_mode == "entra" and not (self.entra_tenant_id and self.entra_client_id):
            raise ValueError("AUTH_MODE=entra 需要 ENTRA_TENANT_ID 與 ENTRA_CLIENT_ID")
        return self

    @property
    def admin_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.bootstrap_admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
