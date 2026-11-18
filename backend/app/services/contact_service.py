"""聯絡人：新增、修改、退訂、個資刪除（M2-01a、F-CASE-5、SPEC 9 個資）。

activity_log 只記聯絡人編號，不記姓名或 email（CLAUDE.md 第 8 節第 4 點；刪除後也不留個資）。
"""

from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.domain import company_rules as rules
from app.domain import contact_rules
from app.domain.company_rules import DomainError
from app.models import AppUser, Company, Contact
from app.services import case_service
from app.services import company_service as company_svc


def get_contact(db: Session, contact_id: int) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise DomainError("CONTACT_NOT_FOUND", "找不到這位聯絡人", 404)
    return contact


def _ensure_can_edit(company: Company, user: AppUser) -> None:
    rules.ensure_can_act(company_svc._ownership(company), user.user_id, company_svc.now(), company_svc.is_manager(user))


def _ensure_unique(db: Session, company_id: int, email: str, exclude_id: int | None = None) -> None:
    stmt = select(Contact.contact_id).where(Contact.company_id == company_id, Contact.email == email)
    if exclude_id is not None:
        stmt = stmt.where(Contact.contact_id != exclude_id)
    if db.scalar(stmt) is not None:
        raise DomainError("CONTACT_EXISTS", "這家公司已經有這個 email 的聯絡人", 409)


def create_contact(
    db: Session,
    user: AppUser,
    *,
    company_id: int,
    email: str,
    source: str,
    name: str | None,
    title: str | None,
    is_verified: bool,
) -> Contact:
    company = company_svc.get_company(db, company_id)
    _ensure_can_edit(company, user)
    normalized = contact_rules.normalize_email(email)
    contact_rules.check_source(source)
    _ensure_unique(db, company_id, normalized)
    contact = Contact(
        company_id=company_id,
        email=normalized,
        source=source,
        name=(name or "").strip() or None,
        title=(title or "").strip() or None,
        is_verified=is_verified,
    )
    db.add(contact)
    db.flush()
    company_svc.log(db, company, user, "contact_add", to_value=str(contact.contact_id), note=source)
    db.commit()
    return contact


def update_contact(
    db: Session,
    user: AppUser,
    contact: Contact,
    *,
    fields: dict[str, object],
) -> Contact:
    """fields 只會有使用者有送的欄位（name、title、email、source、is_verified）。"""
    company = company_svc.get_company(db, contact.company_id)
    _ensure_can_edit(company, user)
    if contact.unsubscribed and "email" in fields:
        raise DomainError("CONTACT_UNSUBSCRIBED", "已退訂的聯絡人不能改 email", 409)
    changed: list[str] = []
    if "email" in fields:
        email = contact_rules.normalize_email(str(fields["email"]))
        if email != contact.email:
            _ensure_unique(db, contact.company_id, email, exclude_id=contact.contact_id)
            contact.email = email
            changed.append("email")
    if "source" in fields:
        contact.source = contact_rules.check_source(str(fields["source"]))
        changed.append("source")
    for key in ("name", "title"):
        if key in fields:
            value = fields[key]
            setattr(contact, key, str(value).strip() or None if value is not None else None)
            changed.append(key)
    if "is_verified" in fields:
        contact.is_verified = bool(fields["is_verified"])
        changed.append("is_verified")
    if changed:
        company_svc.log(db, company, user, "contact_update", to_value=str(contact.contact_id), note=",".join(changed))
    db.commit()
    return contact


def reachable_left(db: Session, company_id: int) -> int:
    """公司還沒退訂的聯絡人數。"""
    stmt = select(func.count()).where(Contact.company_id == company_id, Contact.unsubscribed.is_(False))
    return int(db.scalar(stmt) or 0)


def unsubscribe(
    db: Session, user: AppUser, contact: Contact, note: str | None = None, *, whole_company: bool = False
) -> Contact:
    """F-CASE-5：只有這位聯絡人改成退訂。

    整家公司不要聯絡（whole_company），或公司已沒有其他沒退訂的聯絡人時，公司才改成 do_not_contact，
    進行中的案件一起結案（規則在 domain/contact_rules.company_stops_contact）。
    退訂一定要能生效，所以不檢查認領鎖定：任何業務收到退訂都可以標記。
    公司已經是 won（終點）時，只標記聯絡人，不改公司狀態。
    """
    company = company_svc.get_company(db, contact.company_id)
    if not contact.unsubscribed:
        contact.unsubscribed = True
        why = note
        if whole_company:
            why = f"{note}（整家公司不再聯絡）" if note else "整家公司不再聯絡"
        company_svc.log(db, company, user, "contact_unsubscribe", to_value=str(contact.contact_id), note=why)
        db.flush()
    stop = contact_rules.company_stops_contact(
        whole_company=whole_company, reachable_left=reachable_left(db, company.company_id)
    )
    if stop and rules.can_transition(company.status, "do_not_contact"):
        reason = "客戶要求整家公司不再聯絡" if whole_company else "所有聯絡人都已退訂"
        company_svc.change_status(db, company, "do_not_contact", user, reason)
        # 不再聯絡 → 進行中的案件一起結案（M3-04a），之後也不會再出現催辦
        case = case_service.open_case(db, company.company_id, lock=True)
        if case is not None:
            case_service.close_for_unsubscribe(db, user, case, datetime.now(UTC))
    db.commit()
    return contact


def resubscribe(db: Session, user: AppUser, contact: Contact, reason: str | None) -> Contact:
    """M3-18：取消退訂，只限主管／管理員，原因必填。

    公司若因退訂變成 do_not_contact，會依 domain 規則退回「已通過」（status_after_resubscribe）。
    """
    if not company_svc.is_manager(user):
        raise DomainError("FORBIDDEN", "只有主管或管理員可以取消退訂", 403)
    why = contact_rules.check_resubscribe_reason(reason)
    if not contact.unsubscribed:
        raise DomainError("CONTACT_NOT_UNSUBSCRIBED", "這位聯絡人沒有退訂", 409)
    company = company_svc.get_company(db, contact.company_id)
    contact.unsubscribed = False
    company_svc.log(db, company, user, "contact_resubscribe", to_value=str(contact.contact_id), note=why)
    target = rules.status_after_resubscribe(company.status)
    if target is not None:
        previous = company.status
        company.status = target
        company_svc.log(db, company, user, "status_change", previous, target, f"取消退訂：{why}")
    db.commit()
    return contact


def delete_contact(db: Session, user: AppUser, contact: Contact, reason: str | None) -> None:
    """個資刪除請求：真的刪除聯絡人，連帶刪除寄給他的草稿與信件（事件跟著信件刪）。

    只有主管或管理員可以做；activity_log 記原因與刪了幾封，不記個資。
    """
    if not company_svc.is_manager(user):
        raise DomainError("FORBIDDEN", "只有主管或管理員可以刪除個資", 403)
    why = contact_rules.check_delete_reason(reason)
    company = company_svc.get_company(db, contact.company_id)
    # 郵件表還沒有 ORM（M2-02 才加），這裡直接用 SQL；email_event 會跟著 email_message 一起刪（ON DELETE CASCADE）
    params = {"c": contact.contact_id}
    messages = db.execute(
        text(
            "DELETE FROM email_message WHERE draft_id IN "
            "(SELECT draft_id FROM email_draft WHERE contact_id = :c) RETURNING message_id"
        ),
        params,
    ).all()
    drafts = db.execute(text("DELETE FROM email_draft WHERE contact_id = :c RETURNING draft_id"), params).all()
    contact_id = contact.contact_id
    db.delete(contact)
    company_svc.log(
        db,
        company,
        user,
        "contact_delete",
        from_value=str(contact_id),
        note=f"{why}（刪除草稿 {len(drafts)} 封、寄出信件 {len(messages)} 封）",
    )
    db.commit()
