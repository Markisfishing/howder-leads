"""CSV 欄位規格 v1 匯入（M3-06b、SPEC 8.4、F-REC-7）。"""

import codecs
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Classification, Company
from tests.factories import FAKE_ROWS, csv_bytes

Headers = Callable[[str], dict[str, str]]
SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "import_v1_sample.csv"


@pytest.fixture
def admin(as_user: Headers) -> dict[str, str]:
    return as_user("admin@example.com")


def _upload(client: TestClient, headers: dict[str, str], content: bytes) -> dict:
    res = client.post("/api/v1/imports", files={"file": ("v1.csv", content, "text/csv")}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _commit(client: TestClient, headers: dict[str, str], batch_id: int) -> dict:
    res = client.post(f"/api/v1/imports/{batch_id}/commit", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_m3_06b_sample_csv_imports_new_columns(client: TestClient, admin: dict[str, str], db: Session) -> None:
    """範例 CSV 給 MLE 參考：要能直接匯入，新欄位寫進公司與分類。"""
    body = _upload(client, admin, SAMPLE.read_bytes())
    assert body["rows_error"] == 0, body["errors"]
    assert body["warnings"] == []
    _commit(client, admin, body["batch_id"])

    company = db.scalars(select(Company).where(Company.tax_id == "90000101")).one()
    cl = db.scalars(select(Classification).where(Classification.company_id == company.company_id)).one()
    assert (company.country, company.url_status, company.source) == ("TW", "valid", "expo")
    assert (cl.fit_stars, cl.product_type, sorted(cl.tags)) == (
        Decimal("4.5"),
        "包裝機械、PLC 控制盤",
        ["自動化", "電箱"],
    )


def test_m3_06b_invalid_url_rows_are_skipped(client: TestClient, admin: dict[str, str], db: Session) -> None:
    body = _upload(client, admin, SAMPLE.read_bytes())
    assert body["rows_skipped"] == 1
    assert {r["tax_id"]: r["action"] for r in body["rows"]}["90000104"] == "skip"
    committed = _commit(client, admin, body["batch_id"])
    assert committed["rows_created"] == 3
    assert db.scalars(select(Company).where(Company.tax_id == "90000104")).first() is None


def test_m3_06b_unknown_columns_warned_not_blocking(client: TestClient, admin: dict[str, str]) -> None:
    rows = [{**r, "資料來源": "expo", "神秘欄位": "x"} for r in FAKE_ROWS]
    body = _upload(client, admin, csv_bytes(rows))
    assert body["rows_error"] == 0
    assert [w["field"] for w in body["warnings"]] == ["神秘欄位"]
    assert body["rows_created"] == len(FAKE_ROWS)


def test_m3_06b_legacy_file_without_source_warns(client: TestClient, admin: dict[str, str]) -> None:
    """舊版 Excel 沒有資料來源欄：照樣匯入，提示來源會算在「未標示」。"""
    body = _upload(client, admin, csv_bytes())
    assert body["rows_error"] == 0
    assert [w["field"] for w in body["warnings"]] == ["source"]


@pytest.mark.parametrize(
    "field,value",
    [("國別", "Taiwan"), ("網址狀態", "broken"), ("適合度星等", "6"), ("適合度星等", "abc"), ("資料來源", "")],
)
def test_m3_06b_v1_field_validation(client: TestClient, admin: dict[str, str], field: str, value: str) -> None:
    row = {**FAKE_ROWS[0], "資料來源": "expo", field: value}
    body = _upload(client, admin, csv_bytes([row]))
    assert body["rows_error"] == 1
    assert body["errors"][0]["row"] == 2


def test_m3_06b_reimport_without_source_keeps_known_source(
    client: TestClient, admin: dict[str, str], db: Session
) -> None:
    first = [{**r, "資料來源": "expo"} for r in FAKE_ROWS]
    _commit(client, admin, _upload(client, admin, csv_bytes(first))["batch_id"])
    again = _upload(client, admin, csv_bytes())
    assert again["rows_unchanged"] == len(FAKE_ROWS)
    assert {c.source for c in db.scalars(select(Company))} == {"expo"}


def test_m3_06b_api_import_tags_list_and_funnel(client: TestClient, db: Session) -> None:
    body = {
        "model_name": "mle-v3",
        "funnel": {"資料庫總數": 12000, "產業篩選後": 800, "網址有效": 600, "產品命中": 120},
        "rows": [
            {
                "tax_id": "90000201",
                "name": "範例 API 公司",
                "priority": "B",
                "country": "vn",
                "tags": ["電箱", "自動化"],
                "fit_stars": 3.26,
                "source": "b2b",
            }
        ],
    }
    res = client.post("/api/v1/imports/api?commit=true", json=body, headers={"X-API-Key": "test-key"})
    assert res.status_code == 201, res.text
    assert res.json()["funnel"]["產品命中"] == 120
    company = db.scalars(select(Company).where(Company.tax_id == "90000201")).one()
    cl = db.scalars(select(Classification).where(Classification.company_id == company.company_id)).one()
    assert company.country == "VN"
    assert (cl.fit_stars, sorted(cl.tags)) == (Decimal("3.3"), ["自動化", "電箱"])


def test_m3_06b_sample_csv_has_utf8_bom() -> None:
    """範例檔要帶 UTF-8 BOM：Excel 雙擊開啟時才不會把中文顯示成亂碼。"""
    raw = SAMPLE.read_bytes()
    assert raw.startswith(codecs.BOM_UTF8)
    assert "統編" in raw.decode("utf-8-sig").splitlines()[0]
