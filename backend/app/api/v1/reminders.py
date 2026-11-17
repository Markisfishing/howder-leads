"""待辦提醒（M3-10b、F-CASE-3、F-DASH-4）。條件在 view v_case_reminder。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import AppUser
from app.services import reminder_service

router = APIRouter()


class ReminderItem(BaseModel):
    kind: str
    label: str
    count: int


@router.get("/reminders", response_model=list[ReminderItem])
def reminders(user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> list[ReminderItem]:
    """業務看自己的案件；主管看全部。另附「新名單待審核」件數。"""
    counts = reminder_service.summary(db, user)
    labels = {**reminder_service.REMINDER_LABELS, "pending_review": "新名單待審核"}
    return [ReminderItem(kind=k, label=labels[k], count=counts[k]) for k in labels]
