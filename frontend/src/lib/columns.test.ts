import { downloadCompanies, exportColumns } from "../api/endpoints";
import {
  DEFAULT_COLUMNS,
  loadColumns,
  MAX_COLUMNS,
  sanitizeColumns,
  saveColumns,
  toggleColumn,
} from "./columns";
import { DEFAULT_FILTERS } from "./filters";

describe("M3-13b 欄位自選", () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("test_f_rec_8_max_10_columns：最多 10 欄，已滿不能再加，公司名稱不能取消", () => {
    let cols = sanitizeColumns(["name"]);
    for (const k of [
      "tax_id",
      "industry",
      "product_type",
      "tags",
      "reason",
      "likelihood",
      "status",
      "owner_name",
      "source",
      "country",
      "score",
    ] as const) {
      cols = toggleColumn(cols, k);
    }
    expect(cols).toHaveLength(MAX_COLUMNS);
    expect(cols).not.toContain("score");
    expect(toggleColumn(cols, "name")).toEqual(cols);
    expect(toggleColumn(cols, "tags")).toHaveLength(MAX_COLUMNS - 1);
  });

  it("test_f_rec_8_saved_in_browser：存在瀏覽器，壞資料就用預設", () => {
    saveColumns(["name", "source"]);
    expect(loadColumns()).toEqual(["name", "source"]);
    window.localStorage.setItem("howder.recommendations.columns.v1", "{壞掉");
    expect(loadColumns()).toEqual(DEFAULT_COLUMNS);
    expect(sanitizeColumns(["bogus", "source", "source"])).toEqual([
      "name",
      "source",
    ]);
  });

  it("test_f_rec_8_export_uses_chosen_columns：匯出照畫面上的欄位與篩選", async () => {
    expect(exportColumns(["name", "fit_stars"])).toEqual([
      "name",
      "fit_stars",
      "priority",
    ]);
    const fn = vi.fn(
      async () =>
        new Response("\ufeff公司名稱\n", {
          headers: { "content-type": "text/csv" },
        }),
    );
    vi.stubGlobal("fetch", fn);
    await downloadCompanies({ ...DEFAULT_FILTERS, source: "expo" }, [
      "name",
      "tags",
    ]);
    const url = String((fn.mock.calls[0] as unknown[])[0]);
    expect(url).toContain("/api/v1/companies/export?");
    expect(url).toContain("source=expo");
    expect(url).toContain("columns=name&columns=tags");
  });
});
