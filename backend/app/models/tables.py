"""SQLAlchemy ORM。

資料表由 migrations 建立（手寫 SQL），這裡只做對應，不用來建表。
欄位要和 migrations/sql/*.sql 一致，由 tests/test_models.py 檢查。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, ENUM, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

USER_ROLES = ("sales", "manager", "admin")
COMPANY_STATUSES = (
    "imported",
    "pending_review",
    "approved",
    "rejected",
    "drafted",
    "draft_approved",
    "sent",
    "replied",
    "meeting",
    "won",
    "lost",
    "do_not_contact",
)

user_role_enum = ENUM(*USER_ROLES, name="user_role", create_type=False)
company_status_enum = ENUM(*COMPANY_STATUSES, name="company_status", create_type=False)
GEN_MODES = ("template_only", "template_ai", "full_ai")
DRAFT_STATUSES = ("generating", "pending_review", "approved", "discarded", "sent", "failed")
gen_mode_enum = ENUM(*GEN_MODES, name="gen_mode", create_type=False)
draft_status_enum = ENUM(*DRAFT_STATUSES, name="draft_status", create_type=False)


class Base(DeclarativeBase):
    metadata = MetaData()


class AppUser(Base):
    __tablename__ = "app_user"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(user_role_enum, default="sales")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DimIndustry(Base):
    __tablename__ = "dim_industry"
    industry_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    is_prospect: Mapped[bool] = mapped_column(Boolean, default=True)


class DimPriority(Base):
    __tablename__ = "dim_priority"
    priority: Mapped[str] = mapped_column(String(1), primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    definition: Mapped[str] = mapped_column(Text)
    suggested_action: Mapped[str] = mapped_column(Text)
    stars: Mapped[int] = mapped_column(SmallInteger)


class ModelRun(Base):
    __tablename__ = "model_run"
    run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    model_name: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cost_tokens: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportBatch(Base):
    __tablename__ = "import_batch"
    batch_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    file_name: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="csv")
    run_id: Mapped[int | None] = mapped_column(ForeignKey("model_run.run_id"))
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_created: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_error: Mapped[int] = mapped_column(Integer, default=0)
    rows_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    model_name: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[Any] = mapped_column(JSONB)
    error_report: Mapped[Any] = mapped_column(JSONB)
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    status: Mapped[str] = mapped_column(Text, default="previewed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    funnel: Mapped[Any] = mapped_column(JSONB)


class Company(Base):
    __tablename__ = "company"
    company_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tax_id: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(Text)
    registered_products: Mapped[str | None] = mapped_column(Text)
    website_url: Mapped[str | None] = mapped_column(Text)
    website_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    industry_override_id: Mapped[int | None] = mapped_column(ForeignKey("dim_industry.industry_id"))
    status: Mapped[str] = mapped_column(company_status_enum, default="pending_review")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    owner_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    added_manually: Mapped[bool] = mapped_column(Boolean, default=False)
    first_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batch.batch_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    country: Mapped[str] = mapped_column(String(2), default="TW")
    url_status: Mapped[str] = mapped_column(Text, default="unchecked")
    source: Mapped[str | None] = mapped_column(Text)


class Classification(Base):
    __tablename__ = "classification"
    classification_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.company_id"))
    run_id: Mapped[int] = mapped_column(ForeignKey("model_run.run_id"))
    industry_id: Mapped[int | None] = mapped_column(ForeignKey("dim_industry.industry_id"))
    customer_type: Mapped[str | None] = mapped_column(Text)
    likelihood: Mapped[str | None] = mapped_column(Text)
    is_competitor: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[str | None] = mapped_column(ForeignKey("dim_priority.priority"))
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    reason: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fit_stars: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    product_type: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)


class Review(Base):
    __tablename__ = "review"
    review_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.company_id"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    decision: Mapped[str] = mapped_column(Text)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    corrected_industry_id: Mapped[int | None] = mapped_column(ForeignKey("dim_industry.industry_id"))
    corrected_url: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Contact(Base):
    __tablename__ = "contact"
    contact_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.company_id"))
    name: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActivityLog(Base):
    __tablename__ = "activity_log"
    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.company_id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    action: Mapped[str] = mapped_column(Text)
    from_value: Mapped[str | None] = mapped_column(Text)
    to_value: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserMailCredential(Base):
    """業務的 Outlook 寄信權杖（ADR 0005）。token_cache 是加密後的位元組，任何地方都不可以印出來。"""

    __tablename__ = "user_mail_credential"
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"), primary_key=True)
    token_cache: Mapped[bytes] = mapped_column(BYTEA)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text))
    status: Mapped[str] = mapped_column(Text, default="connected")
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # 避免 debug 時把權杖印出來
        return f"UserMailCredential(user_id={self.user_id}, status={self.status!r})"


class Job(Base):
    """背景工作（ADR 0003）。worker 用 SELECT … FOR UPDATE SKIP LOCKED 領取。"""

    __tablename__ = "job"
    job_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(Text, default="queued")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------- 郵件（M2）----------
class EmailTemplate(Base):
    """郵件模板。修改時新增一列（version + 1），同一個 family_id 只有一個啟用中的版本（migration 0005）。"""

    __tablename__ = "email_template"
    template_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    family_id: Mapped[int | None] = mapped_column(ForeignKey("email_template.template_id"))
    name: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, default="zh-TW")
    subject: Mapped[str] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Campaign(Base):
    __tablename__ = "campaign"
    campaign_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("email_template.template_id"))
    gen_mode: Mapped[str] = mapped_column(gen_mode_enum, default="template_only")
    owner_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    status: Mapped[str] = mapped_column(Text, default="draft")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailDraft(Base):
    """草稿。業務編輯 body_text，系統轉成 body_html；ai_original 是一開始產生的原稿（算 edit_ratio 用）。"""

    __tablename__ = "email_draft"
    draft_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaign.campaign_id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("company.company_id"))
    contact_id: Mapped[int] = mapped_column(ForeignKey("contact.contact_id"))
    subject: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    body_html: Mapped[str] = mapped_column(Text, default="")
    ai_original: Mapped[str | None] = mapped_column(Text)
    edit_ratio: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    status: Mapped[str] = mapped_column(draft_status_enum, default="generating")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    send_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # 不印內文（CLAUDE.md 第 8 節第 4 點）
        return f"EmailDraft(draft_id={self.draft_id}, status={self.status!r})"


class EmailMessage(Base):
    """實際寄出的信。只有核准的草稿才會變成這個（CLAUDE.md 第 6 節）。"""

    __tablename__ = "email_message"
    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("email_draft.draft_id"))
    sender_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    graph_message_id: Mapped[str | None] = mapped_column(Text)
    conversation_id: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------- 案件（M3、ADR 0004）----------
CASE_STATUSES = ("sent", "tracking", "replied", "negotiating", "no_response", "won", "lost")
CASE_CHANNELS = ("email", "line", "wechat", "phone", "visit", "other", "system")
CASE_RESULTS = ("sent", "replied", "negotiating", "won", "lost", "no_response")


class SalesCase(Base):
    """案件：每封開發信（或「加入追蹤」）一件。同一家公司同時只有一件未結案（migration 0006）。"""

    __tablename__ = "sales_case"
    case_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_no: Mapped[str] = mapped_column(Text, Computed("'C-' || lpad(case_id::text, 4, '0')", persisted=True))
    company_id: Mapped[int] = mapped_column(ForeignKey("company.company_id"))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contact.contact_id"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    origin: Mapped[str] = mapped_column(Text)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("email_message.message_id"))
    status: Mapped[str] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_up: Mapped[date | None] = mapped_column(Date)
    amount_twd: Mapped[Decimal | None] = mapped_column(Numeric(14, 0))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CaseUpdate(Base):
    """回填紀錄（時間軸的一筆）。業務人工輸入；系統自動事件 channel = 'system'。"""

    __tablename__ = "case_update"
    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("sales_case.case_id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    channel: Mapped[str] = mapped_column(Text)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contact.contact_id"))
    result: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    next_follow_up: Mapped[date | None] = mapped_column(Date)
    amount_twd: Mapped[Decimal | None] = mapped_column(Numeric(14, 0))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------- 指標層 view（唯讀）----------
v_recommendation = Table(
    "v_recommendation",
    Base.metadata,
    Column("company_id", BigInteger, primary_key=True),
    Column("tax_id", String(8)),
    Column("name", Text),
    Column("website_url", Text),
    Column("website_verified", Boolean),
    Column("status", company_status_enum),
    Column("owner_id", BigInteger),
    Column("owner_name", Text),
    Column("owner_locked_until", DateTime(timezone=True)),
    Column("added_manually", Boolean),
    Column("updated_at", DateTime(timezone=True)),
    Column("run_id", BigInteger),
    Column("priority", String(1)),
    Column("stars", SmallInteger),
    Column("score", Numeric(5, 2)),
    Column("likelihood", Text),
    Column("is_competitor", Boolean),
    Column("industry_id", SmallInteger),
    Column("industry", Text),
    Column("customer_type", Text),
    Column("reason", Text),
    Column("country", String(2)),
    Column("url_status", Text),
    Column("source", Text),
    Column("fit_stars", Numeric(2, 1)),
    Column("product_type", Text),
    Column("tags", ARRAY(Text)),
    info={"is_view": True},
)

v_kpi_summary = Table(
    "v_kpi_summary",
    Base.metadata,
    Column("pending_review", BigInteger),
    Column("total_companies", BigInteger),
    Column("five_star", BigInteger),
    Column("sent_7d", BigInteger),
    Column("sent_total", BigInteger),
    Column("replied_total", BigInteger),
    Column("reply_rate", Numeric(6, 4)),
    Column("won_total", BigInteger),
    Column("won_amount_twd", Numeric(14, 0)),
    info={"is_view": True},
)

# 0010：總覽頁（M3-12a）；寄出、回覆、成交的定義只在這兩個 view
v_case_fact = Table(
    "v_case_fact",
    Base.metadata,
    Column("case_id", BigInteger, primary_key=True),
    Column("case_no", Text),
    Column("company_id", BigInteger),
    Column("owner_id", BigInteger),
    Column("origin", Text),
    Column("status", Text),
    Column("opened_at", DateTime(timezone=True)),
    Column("closed_at", DateTime(timezone=True)),
    Column("sent_at", DateTime(timezone=True)),
    Column("is_sent", Boolean),
    Column("is_replied", Boolean),
    Column("is_won", Boolean),
    Column("won_amount", Numeric(14, 0)),
    Column("industry_id", SmallInteger),
    Column("industry", Text),
    Column("source", Text),
    Column("product_type", Text),
    Column("priority", String(1)),
    Column("fit_stars", Numeric(2, 1)),
    info={"is_view": True},
)

v_company_fact = Table(
    "v_company_fact",
    Base.metadata,
    Column("company_id", BigInteger, primary_key=True),
    Column("status", company_status_enum),
    Column("owner_id", BigInteger),
    Column("industry_id", SmallInteger),
    Column("source", Text),
    Column("product_type", Text),
    Column("priority", String(1)),
    Column("stars", SmallInteger),
    Column("fit_stars", Numeric(2, 1)),
    Column("created_at", DateTime(timezone=True)),
    Column("is_approved", Boolean),
    Column("is_sent", Boolean),
    Column("is_replied", Boolean),
    Column("is_won", Boolean),
    Column("first_sent_at", DateTime(timezone=True)),
    info={"is_view": True},
)

v_case_reminder = Table(
    "v_case_reminder",
    Base.metadata,
    Column("case_id", BigInteger),
    Column("owner_id", BigInteger),
    Column("company_id", BigInteger),
    Column("kind", Text),
    Column("since", DateTime(timezone=True)),
    info={"is_view": True},
)

v_reject_reasons = Table(
    "v_reject_reasons",
    Base.metadata,
    Column("reject_reason", Text),
    Column("run_id", BigInteger),
    Column("n", BigInteger),
    info={"is_view": True},
)
