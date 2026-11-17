"""郵件模板（M2-02a）。讀取所有登入者都可以（建立批次要選模板），修改只有 admin。"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_admin
from app.db import get_db
from app.domain import template_rules
from app.models import AppUser, EmailTemplate
from app.services import template_service as svc

router = APIRouter()


class TemplateOut(BaseModel):
    template_id: int
    family_id: int
    name: str
    version: int
    is_active: bool
    subject: str
    body_text: str
    created_at: datetime

    @classmethod
    def of(cls, t: EmailTemplate) -> "TemplateOut":
        return cls(
            template_id=t.template_id,
            family_id=t.family_id or t.template_id,
            name=t.name,
            version=t.version,
            is_active=t.is_active,
            subject=t.subject,
            body_text=t.body_text,
            created_at=t.created_at,
        )


class TemplateBody(BaseModel):
    name: str = Field(max_length=100)
    subject: str = Field(max_length=template_rules.SUBJECT_MAX)
    body_text: str = Field(max_length=template_rules.BODY_MAX)


class PreviewBody(BaseModel):
    subject: str = Field(max_length=template_rules.SUBJECT_MAX)
    body_text: str = Field(max_length=template_rules.BODY_MAX)


class PreviewOut(BaseModel):
    subject: str
    body_text: str
    body_html: str


class Variable(BaseModel):
    name: str
    label: str
    required: bool


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(_: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> list[TemplateOut]:
    return [TemplateOut.of(t) for t in svc.list_active(db)]


@router.get("/templates/variables", response_model=list[Variable])
def list_variables(_: AppUser = Depends(current_user)) -> list[Variable]:
    return [Variable(name=k, label=v, required=k == "unsubscribe") for k, v in template_rules.VARIABLES.items()]


@router.post("/templates/preview", response_model=PreviewOut)
def preview_template(body: PreviewBody, user: AppUser = Depends(require_admin)) -> PreviewOut:
    subject, text, html_body = svc.preview(user, body.subject, body.body_text)
    return PreviewOut(subject=subject, body_text=text, body_html=html_body)


@router.get("/templates/{template_id}", response_model=TemplateOut)
def get_template(template_id: int, _: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> TemplateOut:
    return TemplateOut.of(svc.get_template(db, template_id))


@router.get("/templates/{template_id}/versions", response_model=list[TemplateOut])
def template_versions(
    template_id: int, _: AppUser = Depends(require_admin), db: Session = Depends(get_db)
) -> list[TemplateOut]:
    return [TemplateOut.of(t) for t in svc.list_versions(db, svc.get_template(db, template_id))]


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(
    body: TemplateBody, user: AppUser = Depends(require_admin), db: Session = Depends(get_db)
) -> TemplateOut:
    return TemplateOut.of(svc.create(db, user, name=body.name, subject=body.subject, body_text=body.body_text))


@router.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int, body: TemplateBody, user: AppUser = Depends(require_admin), db: Session = Depends(get_db)
) -> TemplateOut:
    current = svc.get_template(db, template_id)
    return TemplateOut.of(
        svc.new_version(db, user, current, name=body.name, subject=body.subject, body_text=body.body_text)
    )


@router.post("/templates/{template_id}/archive", response_model=TemplateOut)
def archive_template(
    template_id: int, user: AppUser = Depends(require_admin), db: Session = Depends(get_db)
) -> TemplateOut:
    return TemplateOut.of(svc.archive(db, user, svc.get_template(db, template_id)))
