import { DEFAULT_FILTERS, parseFilters, toSearchParams, updateFilters } from "./filters";

describe("F-REC-2 篩選條件反映在網址上", () => {
  it("test_f_rec_2_round_trip：篩選條件轉成網址再讀回來不變", () => {
    const f = {
      ...DEFAULT_FILTERS,
      stars: [5, 4],
      status: ["pending_review"],
      industryId: 3,
      owner: "me",
      hasWebsite: false,
      competitor: true,
      q: "電子",
      sort: "name" as const,
      page: 2,
    };
    expect(parseFilters(toSearchParams(f))).toEqual(f);
  });

  it("test_f_rec_2_defaults_empty_url：預設條件不寫進網址", () => {
    expect(toSearchParams(DEFAULT_FILTERS).toString()).toBe("");
  });

  it("test_f_rec_2_ignores_invalid：網址被亂改時退回預設值", () => {
    const f = parseFilters(new URLSearchParams("stars=9&stars=x&industry=-1&sort=hack&page=0&size=9999&website=maybe"));
    expect(f.stars).toEqual([]);
    expect(f.industryId).toBeNull();
    expect(f.sort).toBe("recommended");
    expect(f.page).toBe(1);
    expect(f.pageSize).toBe(200);
    expect(f.hasWebsite).toBeNull();
  });

  it("test_f_rec_2_filter_change_resets_page：改條件回到第 1 頁，只換頁時保留頁碼", () => {
    const onPage3 = { ...DEFAULT_FILTERS, page: 3 };
    expect(updateFilters(onPage3, { q: "abc" }).page).toBe(1);
    expect(updateFilters(onPage3, { page: 4 }).page).toBe(4);
  });
});
