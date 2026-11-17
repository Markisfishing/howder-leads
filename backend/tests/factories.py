"""測試用假資料。公司名稱、統編、網址全部是虛構的（CLAUDE.md 第 8 節）。"""

import io
from typing import Any

import pandas as pd

FAKE_ROWS: list[dict[str, Any]] = [
    {
        "統編": "10000001",
        "公司名稱": "測試自動化股份有限公司",
        "官網": "https://auto.example.com",
        "產業": "工業自動化與機械設備",
        "客戶屬性": "自動化/包裝機械",
        "端子台使用可能性": "高",
        "優先級": "A",
        "判斷理由": "整機含控制箱與 PLC",
        "工廠主要產品(登記)": "293通用機械設備",
    },
    {
        "統編": "10000002",
        "公司名稱": "測試電機股份有限公司",
        "官網": "無官網",
        "產業": "馬達、變壓器與電力設備",
        "客戶屬性": "電機",
        "端子台使用可能性": "中",
        "優先級": "B",
        "判斷理由": "部分機型有電控",
        "工廠主要產品(登記)": "281發電輸電配電機械",
    },
    {
        "統編": "10000003",
        "公司名稱": "測試連接器股份有限公司",
        "官網": "https://conn.example.com",
        "產業": "電子連接器、線材與EMS",
        "客戶屬性": "連接器",
        "端子台使用可能性": "明確但競合",
        "優先級": "C",
        "判斷理由": "本身生產端子台",
        "工廠主要產品(登記)": "262被動電子元件",
    },
    {
        "統編": "10000004",
        "公司名稱": "測試塑膠股份有限公司",
        "官網": "",
        "產業": "金屬、模具與塑膠零件製造",
        "客戶屬性": "塑膠零件",
        "端子台使用可能性": "低",
        "優先級": "D",
        "判斷理由": "純零件加工",
        "工廠主要產品(登記)": "220塑膠製品",
    },
]


def csv_bytes(rows: list[dict[str, Any]] | None = None, encoding: str = "utf-8-sig") -> bytes:
    return pd.DataFrame(rows or FAKE_ROWS).to_csv(index=False).encode(encoding)


def two_sheet_xlsx(rows: list[dict[str, Any]] | None = None) -> bytes:
    """模擬現有 Excel 的格式：模型結果那張表沒有統編，統編在另一張「原檔」表，還混了圖例欄。"""
    rows = rows or FAKE_ROWS
    raw = pd.DataFrame(
        [
            {
                "統編": r["統編"],
                "公司名稱": r["公司名稱"],
                "官網(工具找到的)": r["官網"],
                "工廠主要產品(登記)": r["工廠主要產品(登記)"],
                "標準化產業": "",
                "是否真的潛在客戶(Y/N)": "",
            }
            for r in rows
        ]
    )
    result = pd.DataFrame(
        [
            {
                "序號": i + 1,
                "公司名稱": r["公司名稱"],
                "官網": r["官網"],
                "產業": r["產業"],
                "客戶屬性": r["客戶屬性"],
                "端子台使用可能性": r["端子台使用可能性"],
                "優先級": r["優先級"],
                "判斷理由": r["判斷理由"],
                "建議動作": "可開發",
                "Unnamed: 9": "",
                "分類": "A 第一優先/優先" if i == 0 else "",
                "家數": 12 if i == 0 else "",
            }
            for i, r in enumerate(rows)
        ]
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        raw.to_excel(writer, sheet_name="請標(原檔)", index=False)
        result.to_excel(writer, sheet_name="端子台潛客整理(完成)", index=False)
    return buf.getvalue()
