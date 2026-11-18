import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { CompanyPage, CompanyRow } from "../../api/types";
import { RecommendationsPage } from "../RecommendationsPage";

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ isManager: false, isAdmin: false }),
}));

const row: CompanyRow = {
  company_id: 3,
  tax_id: "90000101",
  name: "範例自動化",
  website_url: null,
  website_verified: false,
  status: "approved",
  owner_id: null,
  owner_name: null,
  owner_locked_until: null,
  added_manually: false,
  priority: "A",
  stars: 5,
  score: null,
  likelihood: "高",
  is_competitor: false,
  industry_id: 1,
  industry: "工業自動化與機械設備",
  customer_type: null,
  reason: "整機含控制箱",
  updated_at: "2026-11-18T02:00:00Z",
  country: "TW",
  url_status: "valid",
  source: "expo",
  fit_stars: "4.5",
  product_type: null,
  tags: [],
};
const page: CompanyPage = { items: [row], total: 1, page: 1, page_size: 50 };

function setup(data: CompanyPage = page, failList = false) {
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    if (url.startsWith("/api/v1/companies"))
      return failList ? Response.json({ error: { code: "INTERNAL", message: "壞了" } }, { status: 500 }) : Response.json(data);
    if (url === "/api/v1/cases" && init.method === "POST")
      return Response.json([{ case_id: 1 }], { status: 201 });
    if (url === "/api/v1/dimensions")
      return Response.json({
        industries: [],
        users: [],
        countries: [],
        sources: [],
        tags: [],
      });
    return Response.json({});
  });
  vi.stubGlobal("fetch", fn);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <RecommendationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("M3-13c 推薦清單批次加入追蹤", () => {
  it("test_f_rec_9_batch_add_tracking：勾選後按「加入追蹤」呼叫 POST /cases", async () => {
    const fn = setup();
    fireEvent.click(await screen.findByLabelText("選取 範例自動化"));
    fireEvent.click(screen.getByRole("button", { name: "加入追蹤" }));
    await waitFor(() =>
      expect(
        fn.mock.calls.some(
          ([u, init]) => u === "/api/v1/cases" && init?.method === "POST",
        ),
      ).toBe(true),
    );
    const call = fn.mock.calls.find(
      ([u, init]) => u === "/api/v1/cases" && init?.method === "POST",
    );
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ company_ids: [3] });
    expect(await screen.findByText(/已加入追蹤 1 家/)).toBeInTheDocument();
  });

  it("test_f_rec_1_decimal_stars_in_list：清單顯示小數星等", async () => {
    setup();
    expect(await screen.findByText("4.5")).toBeInTheDocument();
  });

  it("test_f_rec_2_empty_state：沒有符合的公司時顯示空資料說明", async () => {
    setup({ items: [], total: 0, page: 1, page_size: 50 });
    expect(await screen.findByText("沒有符合條件的公司")).toBeInTheDocument();
    expect(screen.getByText(/還沒有匯入名單/)).toBeInTheDocument();
  });

  it("test_f_rec_2_error_state_has_retry：載入失敗顯示錯誤並可重試", async () => {
    setup(undefined, true);
    expect(await screen.findByRole("button", { name: /重試|重新/ })).toBeInTheDocument();
  });
});
