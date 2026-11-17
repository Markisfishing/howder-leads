"""SQLAlchemy ORM。

資料表由 migrations 建立（手寫 SQL），這裡只做對應，不用來建表。
欄位要和 migrations/sql/*.sql 一致，由 tests/test_models.py 檢查。
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
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
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

USER_ROLES = ("sales", "manager", "admin")
COMPANY_STATUSES = (
    "imported", "pending_review", "approved", "rejected",
    "drafted", "draft_approved", "sent", "replied",
    "meeting", "won", "lost", "do_not_contact",
)

user_role_enum = ENUM(*USER_ROLES, name="user_role", create_type=False)
company_status_enum = ENUM(*COMPANY_STATUSES, name="company_status", create_type=False)


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


# ---------- 指標層 view（唯讀）----------
v_recommendation = Table(
    "v_recommendation", Base.metadata,
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
    info={"is_view": True},
)

v_kpi_summary = Table(
    "v_kpi_summary", Base.metadata,
    Column("pending_review", BigInteger),
    Column("total_companies", BigInteger),
    Column("five_star", BigInteger),
    Column("sent_7d", BigInteger),
    Column("sent_total", BigInteger),
    Column("replied_total", BigInteger),
    info={"is_view": True},
)

v_reject_reasons = Table(
    "v_reject_reasons", Base.metadata,
    Column("reject_reason", Text),
    Column("run_id", BigInteger),
    Column("n", BigInteger),
    info={"is_view": True},
)
