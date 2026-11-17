"""聯絡人（M2-01a、F-CASE-5、SPEC 9 個資）。商業規則在 services/contact_service.py。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import AppUser, Contact
from app.services import contact_service as svc

router = APIRouter()


class ContactOut(BaseModel):
    contact_id: int
    company_id: int
    name: str | None
    title: str | None
    email: str
    source: str
    is_verified: bool
    unsubscribed: bool
    created_at: datetime

    @classmethod
    def of(cls, c: Contact) -> "ContactOut":
        return cls(
            contact_id=c.contact_id,
            company_id=c.company_id,
            name=c.name,
            title=c.title,
            email=c.email,
            source=c.source,
            is_verified=c.is_verified,
            unsubscribed=c.unsubscribed,
            created_at=c.created_at,
        )


class ContactCreate(BaseModel):
    company_id: int
    email: str = Field(max_length=320)
    source: str  # 白名單在 domain/contact_rules.py 檢查，錯誤代碼是 INVALID_SOURCE
    name: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=100)
    is_verified: bool = False


class ContactPatch(BaseModel):
    """只更新有送的欄位；退訂請用 /unsubscribe，不能用 PATCH 取消退訂。"""

    email: str | None = Field(default=None, max_length=320)
    source: str | None = None
    name: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=100)
    is_verified: bool | None = None


class UnsubscribeBody(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class DeleteBody(BaseModel):
    reason: str = Field(max_length=500)


@router.post("/contacts", response_model=ContactOut, status_code=201)
def create_contact(
    body: ContactCreate, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> ContactOut:
    contact = svc.create_contact(
        db,
        user,
        company_id=body.company_id,
        email=body.email,
        source=body.source,
        name=body.name,
        title=body.title,
        is_verified=body.is_verified,
    )
    return ContactOut.of(contact)


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def patch_contact(
    contact_id: int, body: ContactPatch, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> ContactOut:
    contact = svc.get_contact(db, contact_id)
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    # email、source、is_verified 不能清成 null
    for key in ("email", "source", "is_verified"):
        if key in fields and fields[key] is None:
            del fields[key]
    return ContactOut.of(svc.update_contact(db, user, contact, fields=fields))


@router.post("/contacts/{contact_id}/unsubscribe", response_model=ContactOut)
def unsubscribe_contact(
    contact_id: int,
    body: UnsubscribeBody | None = None,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ContactOut:
    contact = svc.get_contact(db, contact_id)
    return ContactOut.of(svc.unsubscribe(db, user, contact, body.note if body else None))


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(
    contact_id: int, body: DeleteBody, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    contact = svc.get_contact(db, contact_id)
    svc.delete_contact(db, user, contact, body.reason)
    return Response(status_code=204)
