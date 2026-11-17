"""推薦清單：小數星等排序與 CSV v1 篩選（M3-06c、F-REC-1、F-REC-7）。"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

Headers = Callable[[str], dict[str, str]]


def _row(tax_id: str, name: str, priority: str, **v1: object) -> dict[str, object]:
    return {"tax_id": tax_id, "name": name, "priority": priority, "industry": "配電盤與電機控制", **v1}


@pytest.fixture
def sales1(client: TestClient, as_user: Headers) -> dict[str, str]:
    rows = [
        _row("90000301", "甲", "A", fit_stars=4.2, source="expo", tags=["電箱", "PLC"], product_type="控制盤"),
        _row("90000302", "乙", "A", fit_stars=4.8, source="b2b", country="VN", tags=["電箱"]),
        _row("90000303", "丙", "B", fit_stars=2.5, source="b2b", url_status="valid"),
        _row("90000304", "丁", "A", source="expo"),  # 沒給 fit_stars → 用優先級星等
        _row("90000305", "戊", "C", fit_stars=3.0),  # 沒有來源
    ]
    # 「戊」沒有來源但同批有來源欄，API 匯入要求每列都填；分兩批送
    for batch in (rows[:4], rows[4:]):
        res = client.post(
            "/api/v1/imports/api?commit=true",
            json={"model_name": "t", "rows": batch},
            headers={"X-API-Key": "test-key"},
        )
        assert res.status_code == 201, res.text
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
