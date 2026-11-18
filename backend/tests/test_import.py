"""名單匯入（F-IMP-1 ~ F-IMP-4、SPEC 8.3）。"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Classification, Company
from tests.factories import FAKE_ROWS, csv_bytes, two_sheet_xlsx

Headers = Callable[[str], dict[str, str]]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def admin(as_user: Headers) -> dict[str, str]:
    return as_user("admin@example.com")


def _upload(client: TestClient, headers: dict[str, str], content: bytes, name: str = "list.csv") -> dict:
    mime = XLSX if name.endswith(".xlsx") else "text/csv"
    res = client.post("/api/v1/imports", files={"file": (name, content, mime)}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Company)) or 0


@pytest.mark.parametrize("encoding", ["utf-8-sig", "cp950"])
def test_f_imp_1_csv_utf8_and_big5(client: TestClient, admin: dict[str, str], encoding: str) -> None:
    body = _upload(client, admin, csv_bytes(encoding=encoding))
    assert body["rows_created"] == 4
    assert body["rows_error"] == 0


def test_f_imp_1_rejects_large_and_unknown_files(client: TestClient, admin: dict[str, str]) -> None:
    res = client.post("/api/v1/imports", files={"file": ("a.txt", b"x", "text/plain")}, headers=admin)
    assert res.json()["error"]["code"] == "IMPORT_UNSUPPORTED_TYPE"
    big = b"a" * (10 * 1024 * 1024 + 1)
    res = client.post("/api/v1/imports", files={"file": ("a.csv", big, "text/csv")}, headers=admin)
    assert res.status_code == 413


def test_f_imp_2_preview_does_not_write_until_commit(client: TestClient, admin: dict[str, str], db: Session) -> None:
    body = _upload(client, admin, csv_bytes())
    assert body["status"] == "previewed"
    assert {r["action"] for r in body["rows"]} == {"create"}
    assert _count(db) == 0

    res = client.post(f"/api/v1/imports/{body['batch_id']}/commit", headers=admin)
    assert res.json()["status"] == "committed"
    assert _count(db) == 4
    statuses = set(db.scalars(select(Company.status)))
    assert statuses == {"pending_review"}

    again = client.post(f"/api/v1/imports/{body['batch_id']}/commit", headers=admin)
    assert again.json()["error"]["code"] == "IMPORT_NOT_PREVIEWED"


def test_f_imp_2_cancel(client: TestClient, admin: dict[str, str], db: Session) -> None:
    body = _upload(client, admin, csv_bytes())
    assert client.post(f"/api/v1/imports/{body['batch_id']}/cancel", headers=admin).json()["status"] == "cancelled"
    assert _count(db) == 0


def test_f_imp_3_reimport_same_file_does_not_add_companies(
    client: TestClient, admin: dict[str, str], db: Session
) -> None:
    first = _upload(client, admin, csv_bytes())
    client.post(f"/api/v1/imports/{first['batch_id']}/commit", headers=admin)
    second = _upload(client, admin, csv_bytes())
    assert second["rows_unchanged"] == 4 and second["rows_created"] == 0
    client.post(f"/api/v1/imports/{second['batch_id']}/commit", headers=admin)
    assert _count(db) == 4
    assert db.scalar(select(func.count()).select_from(Classification)) == 4


def test_f_imp_3_changed_row_creates_new_classification_version(
    client: TestClient, admin: dict[str, str], db: Session
) -> None:
    first = _upload(client, admin, csv_bytes())
    client.post(f"/api/v1/imports/{first['batch_id']}/commit", headers=admin)
    rows = [dict(r) for r in FAKE_ROWS]
    rows[1]["優先級"] = "A"
    second = _upload(client, admin, csv_bytes(rows))
    assert second["rows_updated"] == 1
    client.post(f"/api/v1/imports/{second['batch_id']}/commit", headers=admin)

    company = db.scalar(select(Company).where(Company.tax_id == "10000002"))
    assert company is not None
    versions = list(db.scalars(select(Classification).where(Classification.company_id == company.company_id)))
    assert len(versions) == 2
    current = [v for v in versions if v.is_current]
    assert len(current) == 1 and current[0].priority == "A"


def test_f_imp_4_validation_errors(client: TestClient, admin: dict[str, str]) -> None:
    rows = [dict(r) for r in FAKE_ROWS]
    rows[0]["統編"] = "12AB"
    rows[1]["產業"] = "不存在的產業"
    rows[2]["優先級"] = "Z"
    rows[3]["統編"] = rows[1]["統編"]  # 和第 3 列同統編，但第 3 列本身有錯被略過，所以第 5 列有效
    rows.append(dict(FAKE_ROWS[3], 統編="10000002", 公司名稱="重複統編公司"))  # 第 6 列：和第 5 列重複
    body = _upload(client, admin, csv_bytes(rows))
    fields = {(e["row"], e["field"]) for e in body["errors"]}
    assert (2, "tax_id") in fields
    assert (3, "industry") in fields
    assert (4, "priority") in fields
    assert body["rows_created"] == 1  # 只有第 5 列有效
    assert any(e["row"] == 6 and "重複" in e["message"] for e in body["errors"])


def test_m1_20_two_sheet_excel_merges_tax_id_and_cleans_columns(
    client: TestClient, admin: dict[str, str], db: Session
) -> None:
    body = _upload(client, admin, two_sheet_xlsx(), name="客戶.xlsx")
    assert body["rows_error"] == 0, body["errors"]
    by_tax = {r["tax_id"]: r for r in body["rows"]}
    assert set(by_tax) == {"10000001", "10000002", "10000003", "10000004"}
    assert by_tax["10000001"]["registered_products"] == "293通用機械設備"
    competitor = by_tax["10000003"]
    assert competitor["likelihood"] == "高" and competitor["is_competitor"] is True
    assert by_tax["10000002"]["website_url"] is None  # 「無官網」轉成空值
    assert "家數" not in by_tax["10000001"] and "分類" not in by_tax["10000001"]


def test_sales_cannot_upload(client: TestClient, as_user: Headers) -> None:
    res = client.post(
        "/api/v1/imports", files={"file": ("a.csv", csv_bytes(), "text/csv")}, headers=as_user("sales1@example.com")
    )
    assert res.status_code == 403
