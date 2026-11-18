"""批次審核與排除原因匯出（F-REC-3、M1-38）。"""

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_admin
from app.db import get_db
from app.models import AppUser, Classification, Company, DimIndustry, Review
from app.services import company_service as svc

router = APIRouter()


class ReviewBody(BaseModel):
    company_ids: list[int] = Field(min_length=1, max_length=500)
    decision: Literal["approved", "rejected"]
    reject_reason: str | None = None
    note: str | None = Field(default=None, max_length=2000)
    corrected_industry_id: int | None = None


class ReviewResult(BaseModel):
    updated: int
    status: str


@router.post("/reviews", response_model=ReviewResult)
def create_reviews(
    body: ReviewBody, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> ReviewResult:
    companies = svc.review_companies(
        db,
        sorted(set(body.company_ids)),
        body.decision,
        body.reject_reason,
        body.note,
        body.corrected_industry_id,
        user,
    )
    return ReviewResult(updated=len(companies), status=body.decision)


@router.get("/admin/reviews/export", response_class=Response)
def export_reviews(_: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> Response:
    """所有審核紀錄，附上當時模型的判斷，內部備查用（CSV，Excel 可直接開）。"""
    industries = dict(db.execute(select(DimIndustry.industry_id, DimIndustry.name)).all())
    names = dict(db.execute(select(AppUser.user_id, AppUser.display_name)).all())
    stmt = (
        select(Review, Company, Classification)
        .join(Company, Company.company_id == Review.company_id)
        .outerjoin(Classification, (Classification.company_id == Review.company_id) & Classification.is_current)
        .order_by(Review.created_at)
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["統編", "公司名稱", "模型版本", "模型優先級", "模型產業", "審核結果", "排除原因",
         "修正後產業", "備註", "審核人", "審核時間"]
    )  # fmt: skip
    for r, c, cl in db.execute(stmt):
        writer.writerow([
            c.tax_id,
            c.name,
            cl.run_id if cl else "",
            cl.priority if cl else "",
            industries.get(cl.industry_id, "") if cl and cl.industry_id else "",
            r.decision,
            r.reject_reason or "",
            industries.get(r.corrected_industry_id, "") if r.corrected_industry_id else "",
            r.note or "",
            names.get(r.reviewer_id, ""),
            r.created_at.isoformat(),
        ])  # fmt: skip
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="reviews.csv"'},
    )
