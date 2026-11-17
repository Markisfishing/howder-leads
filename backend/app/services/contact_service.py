"""聯絡人：新增、修改、退訂、個資刪除（M2-01a、F-CASE-5、SPEC 9 個資）。

activity_log 只記聯絡人編號，不記姓名或 email（CLAUDE.md 第 8 節第 4 點；刪除後也不留個資）。
"""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domain import company_rules as rules
from app.domain import contact_rules
from app.domain.company_rules import DomainError
from app.models import AppUser, Company, Contact
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


def unsubscribe(db: Session, user: AppUser, contact: Contact, note: str | None = None) -> Contact:
    """F-CASE-5：聯絡人改成退訂，公司改成 do_not_contact。

    退訂一定要能生效，所以不檢查認領鎖定：任何業務收到退訂都可以標記。
    公司已經是 won（終點）時，只標記聯絡人，不改公司狀態。
    """
    company = company_svc.get_company(db, contact.company_id)
    if not contact.unsubscribed:
        contact.unsubscribed = True
        company_svc.log(db, company, user, "contact_unsubscribe", to_value=str(contact.contact_id), note=note)
    if rules.can_transition(company.status, "do_not_contact"):
        company_svc.change_status(db, company, "do_not_contact", user, "聯絡人退訂")
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
