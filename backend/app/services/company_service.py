"""公司相關的寫入流程：套用 domain 規則、寫資料庫、寫 activity_log。

公司狀態只能透過 change_status() 改（CLAUDE.md 第 4 節第 3 點）。
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import company_rules as rules
from app.domain.company_rules import DomainError, Ownership
from app.models import ActivityLog, AppUser, Company, DimIndustry, Review
from app.services import site_service


def now() -> datetime:
    return datetime.now(UTC)


def is_manager(user: AppUser) -> bool:
    return user.role in ("manager", "admin")


def _ownership(company: Company) -> Ownership:
    return Ownership(company.owner_id, company.owner_locked_until)


def _apply(company: Company, owner: Ownership) -> None:
    company.owner_id = owner.owner_id
    company.owner_locked_until = owner.locked_until


def log(
    db: Session,
    company: Company,
    user: AppUser | None,
    action: str,
    from_value: str | None = None,
    to_value: str | None = None,
    note: str | None = None,
) -> None:
    db.add(
        ActivityLog(
            company_id=company.company_id,
            user_id=user.user_id if user else None,
            action=action,
            from_value=from_value,
            to_value=to_value,
            note=note,
        )
    )


def change_status(db: Session, company: Company, target: str, user: AppUser | None, note: str | None = None) -> None:
    previous = company.status
    company.status = rules.transition(previous, target)
    log(db, company, user, "status_change", previous, target, note)


def get_company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise DomainError("COMPANY_NOT_FOUND", "找不到這家公司", 404)
    return company


def _check_industry(db: Session, industry_id: int | None) -> None:
    if industry_id is not None and db.get(DimIndustry, industry_id) is None:
        raise DomainError("UNKNOWN_INDUSTRY", "產業不在清單裡", 422)


# ---------- 審核（F-REC-3）----------
def review_companies(
    db: Session,
    company_ids: list[int],
    decision: str,
    reject_reason: str | None,
    note: str | None,
    corrected_industry_id: int | None,
    user: AppUser,
) -> list[Company]:
    """批次審核：全部成功才寫入，任何一家不合規則就整批不動，並回報是哪幾家。"""
    target = rules.review_target(decision, reject_reason)
    _check_industry(db, corrected_industry_id)
    companies = list(db.scalars(select(Company).where(Company.company_id.in_(company_ids))))
    missing = set(company_ids) - {c.company_id for c in companies}
    if missing:
        raise DomainError("COMPANY_NOT_FOUND", f"找不到公司：{sorted(missing)}", 404)

    problems: list[str] = []
    current = now()
    for c in companies:
        try:
            rules.ensure_can_act(_ownership(c), user.user_id, current, is_manager(user))
            rules.transition(c.status, target)
        except DomainError as exc:
            problems.append(f"{c.name}：{exc.message}")
    if problems:
        raise DomainError("REVIEW_REJECTED", "以下公司無法審核，整批未變更：" + "；".join(problems))

    for c in companies:
        change_status(db, c, target, user, note)
        if corrected_industry_id is not None:
            c.industry_override_id = corrected_industry_id
        db.add(
            Review(
                company_id=c.company_id,
                reviewer_id=user.user_id,
                decision=decision,
                reject_reason=reject_reason,
                corrected_industry_id=corrected_industry_id,
                note=note,
            )
        )
    db.commit()
    return companies


# ---------- 認領（SPEC 3.1）----------
def claim(db: Session, company: Company, user: AppUser, lock_days: int) -> Company:
    before = company.owner_id
    _apply(company, rules.claim(_ownership(company), user.user_id, now(), lock_days))
    log(db, company, user, "claim", str(before) if before else None, str(user.user_id))
    db.commit()
    return company


def release(db: Session, company: Company, user: AppUser) -> Company:
    before = company.owner_id
    _apply(company, rules.release(_ownership(company), user.user_id, is_manager(user)))
    log(db, company, user, "release", str(before) if before else None, None)
    db.commit()
    return company


def assign(db: Session, company: Company, target_user_id: int, user: AppUser, lock_days: int) -> Company:
    target = db.get(AppUser, target_user_id)
    if target is None or not target.is_active:
        raise DomainError("USER_NOT_FOUND", "找不到這位業務", 404)
    before = company.owner_id
    _apply(company, rules.assign(target_user_id, now(), lock_days, is_manager(user)))
    log(db, company, user, "assign", str(before) if before else None, str(target_user_id))
    db.commit()
    return company


# ---------- 修正資料（F-REC-4）----------
def update_company(
    db: Session,
    company: Company,
    user: AppUser,
    *,
    website_url: str | None = None,
    clear_website: bool = False,
    industry_id: int | None = None,
    note: str | None = None,
) -> Company:
    rules.ensure_can_act(_ownership(company), user.user_id, now(), is_manager(user))
    if clear_website or website_url is not None:
        new_url = None if clear_website else website_url
        log(db, company, user, "update_website", company.website_url, new_url)
        if new_url != company.website_url:
            site_service.invalidate(db, company.company_id)  # 官網換了，舊摘要不再可信（M4-08c）
        company.website_url = new_url
        company.website_verified = True
        db.flush()
        site_service.schedule_if_needed(db, company, user.user_id)
    if industry_id is not None:
        _check_industry(db, industry_id)
        log(db, company, user, "update_industry", str(company.industry_override_id or ""), str(industry_id))
        company.industry_override_id = industry_id
    if note:
        log(db, company, user, "note", note=note)
    db.commit()
    return company


def ensure_can_act(company: Company, user: AppUser) -> None:
    """鎖定規則：被其他業務認領中的公司只有主管能動（和 update_company 同一套）。"""
    rules.ensure_can_act(_ownership(company), user.user_id, now(), is_manager(user))


# ---------- 手動加入（F-REC-6）----------
def create_manual(
    db: Session,
    user: AppUser,
    *,
    tax_id: str,
    name: str,
    website_url: str | None,
    industry_id: int | None,
    note: str | None,
) -> Company:
    if not (tax_id.isdigit() and len(tax_id) == 8):
        raise DomainError("INVALID_TAX_ID", "統編必須是 8 碼數字", 422)
    if db.scalar(select(Company).where(Company.tax_id == tax_id)) is not None:
        raise DomainError("COMPANY_EXISTS", "這個統編已經在名單裡", 409)
    _check_industry(db, industry_id)
    company = Company(
        tax_id=tax_id,
        name=name.strip(),
        website_url=website_url or None,
        website_verified=bool(website_url),
        industry_override_id=industry_id,
        status="pending_review",
        added_manually=True,
    )
    db.add(company)
    db.flush()
    log(db, company, user, "manual_add", note=note)
    db.commit()
    return company
