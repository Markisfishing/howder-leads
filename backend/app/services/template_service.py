"""郵件模板管理（M2-02a）：修改就新增版本，舊版保留給已產生的草稿對照。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import template_rules
from app.domain.company_rules import DomainError
from app.models import ActivityLog, AppUser, EmailTemplate

# 預覽用的假資料（CLAUDE.md 第 8 節：不用真實聯絡人）
PREVIEW_VALUES = {
    "company_name": "範例科技股份有限公司",
    "contact_name": "王經理",
    "contact_title": "採購經理",
    "industry": "工業自動化與機械設備",
    "sender_email": "sales@example.com",
    "ai_paragraph": "",
}


def get_template(db: Session, template_id: int) -> EmailTemplate:
    t = db.get(EmailTemplate, template_id)
    if t is None:
        raise DomainError("TEMPLATE_NOT_FOUND", "找不到這份模板", 404)
    return t


def list_active(db: Session) -> list[EmailTemplate]:
    return list(db.scalars(select(EmailTemplate).where(EmailTemplate.is_active).order_by(EmailTemplate.name)))


def list_versions(db: Session, template: EmailTemplate) -> list[EmailTemplate]:
    return list(
        db.scalars(
            select(EmailTemplate)
            .where(EmailTemplate.family_id == template.family_id)
            .order_by(EmailTemplate.version.desc())
        )
    )


def _log(db: Session, user: AppUser, action: str, t: EmailTemplate) -> None:
    db.add(ActivityLog(user_id=user.user_id, action=action, to_value=f"template:{t.template_id}", note=f"v{t.version}"))


def _check(name: str, subject: str, body_text: str) -> None:
    if not name.strip():
        raise DomainError("TEMPLATE_NAME_REQUIRED", "模板名稱不能空白", 422)
    template_rules.validate_template(subject, body_text)


def create(db: Session, user: AppUser, *, name: str, subject: str, body_text: str) -> EmailTemplate:
    _check(name, subject, body_text)
    t = EmailTemplate(
        name=name.strip(),
        subject=subject.strip(),
        body_text=body_text.strip(),
        body_html=template_rules.text_to_html(body_text),
        version=1,
        is_active=True,
        created_by=user.user_id,
    )
    db.add(t)
    db.flush()
    t.family_id = t.template_id
    _log(db, user, "template_create", t)
    db.commit()
    return t


def new_version(
    db: Session, user: AppUser, current: EmailTemplate, *, name: str, subject: str, body_text: str
) -> EmailTemplate:
    """修改模板：舊版改成停用，新增一列 version + 1。只能從啟用中的版本修改。"""
    if not current.is_active:
        raise DomainError("TEMPLATE_NOT_ACTIVE", "只能修改目前使用中的版本", 409)
    _check(name, subject, body_text)
    latest = db.scalar(select(func.max(EmailTemplate.version)).where(EmailTemplate.family_id == current.family_id))
    current.is_active = False
    db.flush()  # 先停用舊版，部分唯一索引才不會衝突
    t = EmailTemplate(
        family_id=current.family_id,
        name=name.strip(),
        language=current.language,
        subject=subject.strip(),
        body_text=body_text.strip(),
        body_html=template_rules.text_to_html(body_text),
        version=(latest or 0) + 1,
        is_active=True,
        created_by=user.user_id,
    )
    db.add(t)
    db.flush()
    _log(db, user, "template_update", t)
    db.commit()
    return t


def archive(db: Session, user: AppUser, current: EmailTemplate) -> EmailTemplate:
    """停用整份模板（軟刪除）：之後建立批次時選不到，已產生的草稿不受影響。"""
    if not current.is_active:
        raise DomainError("TEMPLATE_NOT_ACTIVE", "這個版本已經停用", 409)
    current.is_active = False
    _log(db, user, "template_archive", current)
    db.commit()
    return current


def preview(user: AppUser, subject: str, body_text: str) -> tuple[str, str, str]:
    """用假資料渲染，回傳 (主旨, 純文字, HTML)。"""
    template_rules.validate_template(subject, body_text)
    values = {**PREVIEW_VALUES, "sender_name": user.display_name}
    out_subject, out_body = template_rules.render(subject, body_text, values)
    return out_subject, out_body, template_rules.text_to_html(out_body)
