"""推薦清單：小數星等排序與 CSV v1 篩選（M3-06c、F-REC-1、F-REC-7）。"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from tests.factories import csv_bytes

Headers = Callable[[str], dict[str, str]]


COLUMNS = {
    "country": "國別",
    "url_status": "網址狀態",
    "product_type": "產品類型",
    "tags": "命中標籤",
    "fit_stars": "適合度星等",
    "source": "資料來源",
}


def _row(tax_id: str, name: str, priority: str, **v1: object) -> dict[str, object]:
    row: dict[str, object] = {"統編": tax_id, "公司名稱": name, "開發優先級": priority, "產業": "配電盤與電機控制"}
    for key, value in v1.items():
        row[COLUMNS[key]] = "、".join(value) if isinstance(value, list) else value
    return row


@pytest.fixture
def sales1(client: TestClient, as_user: Headers) -> dict[str, str]:
    rows = [
        _row("90000301", "甲", "A", fit_stars=4.2, source="expo", tags=["電箱", "PLC"], product_type="控制盤"),
        _row("90000302", "乙", "A", fit_stars=4.8, source="b2b", country="VN", tags=["電箱"]),
        _row("90000303", "丙", "B", fit_stars=2.5, source="b2b", url_status="valid"),
        _row("90000304", "丁", "A", source="expo"),  # 沒給 fit_stars → 用優先級星等
        _row("90000305", "戊", "C", fit_stars=3.0),  # 沒有來源
    ]
    # 「戊」沒有來源：有「資料來源」欄時每列都要填，所以分兩個檔案匯入（第二個沒有這一欄）
    admin = as_user("admin@example.com")
    for batch in (rows[:4], rows[4:]):
        res = client.post("/api/v1/imports", files={"file": ("v1.csv", csv_bytes(batch), "text/csv")}, headers=admin)
        assert res.status_code == 201, res.text
        assert res.json()["rows_error"] == 0, res.json()["errors"]
        res = client.post(f"/api/v1/imports/{res.json()['batch_id']}/commit", headers=admin)
        assert res.status_code == 200, res.text
    return as_user("sales1@example.com")


def _names(client: TestClient, headers: dict[str, str], query: str = "") -> list[str]:
    res = client.get(f"/api/v1/companies?{query}", headers=headers)
    assert res.status_code == 200, res.text
    return [r["name"] for r in res.json()["items"]]


def test_f_rec_1_sorted_by_decimal_fit_stars(client: TestClient, sales1: dict[str, str]) -> None:
    items = client.get("/api/v1/companies", headers=sales1).json()["items"]
    stars = {r["name"]: r["fit_stars"] for r in items}
    assert [r["name"] for r in items][:2] == ["丁", "乙"]  # A 的星等 5 > 4.8 > 4.2
    assert stars["乙"] == "4.8" and stars["甲"] == "4.2"


@pytest.mark.parametrize(
    "query,expected",
    [
        ("country=vn", {"乙"}),
        ("source=expo", {"甲", "丁"}),
        ("source=none", {"戊"}),
        ("source=b2b&source=none", {"乙", "丙", "戊"}),
        ("url_status=valid", {"丙"}),
        ("product_type=控制", {"甲"}),
        ("tag=PLC", {"甲"}),
        ("tag=電箱", {"甲", "乙"}),
        ("min_stars=4.5", {"乙", "丁"}),
        ("min_stars=3&source=b2b", {"乙"}),
    ],
)
def test_f_rec_7_v1_filters(client: TestClient, sales1: dict[str, str], query: str, expected: set[str]) -> None:
    assert set(_names(client, sales1, query)) == expected


def test_f_rec_7_dimensions_list_facets(client: TestClient, sales1: dict[str, str]) -> None:
    dims = client.get("/api/v1/dimensions", headers=sales1).json()
    assert dims["countries"] == ["TW", "VN"]
    assert dims["sources"] == ["b2b", "expo"]
    assert dims["tags"] == ["PLC", "電箱"]


# ---------- 匯出（M3-13a、F-REC-8）----------
def _csv(client: TestClient, headers: dict[str, str], query: str = "") -> list[list[str]]:
    import csv
    import io

    res = client.get(f"/api/v1/companies/export?{query}", headers=headers)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/csv")
    assert res.content.startswith("\ufeff".encode())  # BOM：Excel 開得了
    return list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))


def test_f_rec_8_export_follows_filters_and_default_columns(client: TestClient, sales1: dict[str, str]) -> None:
    rows = _csv(client, sales1, "source=expo")
    assert rows[0] == ["統編", "公司名稱", "適合度星等", "開發優先級", "產業", "推薦理由", "狀態", "負責業務"]
    assert {r[1] for r in rows[1:]} == {"甲", "丁"}


def test_f_rec_8_export_chosen_columns_in_order(client: TestClient, sales1: dict[str, str]) -> None:
    rows = _csv(client, sales1, "columns=name&columns=tags&columns=source&tag=電箱")
    assert rows[0] == ["公司名稱", "命中標籤", "資料來源"]
    assert sorted(rows[1:]) == [["乙", "電箱", "b2b"], ["甲", "PLC、電箱", "expo"]]


def test_f_rec_8_export_rejects_unknown_column(client: TestClient, sales1: dict[str, str]) -> None:
    res = client.get("/api/v1/companies/export?columns=email", headers=sales1)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_EXPORT_COLUMN"
