import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { PerfTable, RejectReport } from "../../api/types";
import { AdminModelPage } from "./AdminModelPage";
import { formatRate, PerformancePage, rangeFor } from "./PerformancePage";

vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => ({ isManager: true, isAdmin: false }) }));

const table: PerfTable = {
  scope_owner_id: null,
  items: [
    {
      key: "expo",
      label: "expo",
      sent: 12,
      replied: 4,
      reply_rate: "0.3333",
      won: 1,
      win_rate: "0.0833",
      won_amount_twd: "50000",
      insufficient: false,
    },
    {
      key: "b2b",
      label: "b2b",
      sent: 3,
      replied: 0,
      reply_rate: null,
      won: 0,
      win_rate: null,
      won_amount_twd: "0",
      insufficient: true,
    },
  ],
};

function mount(ui: React.ReactElement, handler: (url: string) => unknown, path = "/") {
  const fn = vi.fn(async (url: string) => {
    const body = handler(url);
    return body instanceof Response ? body : Response.json(body);
  });
  vi.stubGlobal("fetch", fn);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
  return fn;
}

const errorResponse = (status: number, code: string, message: string) =>
  new Response(JSON.stringify({ error: { code, message } }), { status });

afterEach(() => vi.unstubAllGlobals());

describe("M4-01c 績效頁", () => {
  it("test_m4_01c_format_helpers：比例轉百分比、樣本不足顯示 —、日期區間", () => {
    expect(formatRate("0.3333")).toBe("33.3%");
    expect(formatRate(null)).toBe("—");
    expect(rangeFor("all")).toEqual({ from: null, to: null });
    expect(rangeFor("30d", new Date(2026, 10, 18))).toEqual({ from: "2026-10-20", to: "2026-11-18" });
    expect(rangeFor("this_month", new Date(2026, 10, 18))).toEqual({ from: "2026-11-01", to: "2026-11-18" });
  });

  it("test_m4_01c_table_with_counts_and_insufficient_tag：比例旁附件數，樣本不足要標示", async () => {
    const fn = mount(<PerformancePage />, () => table, "/performance?by=source");
    expect(await screen.findByText("12 件")).toBeInTheDocument();
    expect(screen.getByText("33.3%")).toBeInTheDocument();
    expect(screen.getAllByText("樣本不足")).toHaveLength(1);
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(String(fn.mock.calls[0]?.[0])).toContain("/api/v1/metrics/win-rate?by=source");
  });

  it("test_m4_01c_tabs_switch_endpoint：切到模板與業務會換成對應的 API", async () => {
    const fn = mount(<PerformancePage />, () => table);
    await screen.findByText("12 件");
    fireEvent.click(screen.getByRole("button", { name: "郵件模板" }));
    await waitFor(() =>
      expect(fn.mock.calls.some(([u]) => String(u).startsWith("/api/v1/metrics/templates"))).toBe(true),
    );
    fireEvent.click(screen.getByRole("button", { name: "業務" }));
    await waitFor(() => expect(fn.mock.calls.some(([u]) => String(u).startsWith("/api/v1/metrics/reps"))).toBe(true));
  });

  it("test_m4_01c_empty_state：沒資料顯示空狀態", async () => {
    mount(<PerformancePage />, () => ({ scope_owner_id: null, items: [] }));
    expect(await screen.findByText("這個區間還沒有寄出的案件")).toBeInTheDocument();
  });

  it("test_m4_01c_error_state：失敗顯示錯誤", async () => {
    mount(<PerformancePage />, () => errorResponse(500, "X", "壞了"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("M4-02b 名單品質頁", () => {
  const report: RejectReport = {
    run_id: 2,
    runs: [
      { run_id: 2, model_name: "model-b", created_at: "2026-11-18T02:00:00Z" },
      { run_id: 1, model_name: "model-a", created_at: "2026-11-01T02:00:00Z" },
    ],
    total: 3,
    items: [
      { reason: "wrong_industry", count: 2, share: "0.6667" },
      { reason: "competitor", count: 1, share: "0.3333" },
    ],
  };

  it("test_m4_02b_reject_report：顯示中文原因、家數、占比，切換批次會重新查詢", async () => {
    const fn = mount(<AdminModelPage />, () => report);
    expect(await screen.findByText("產業判斷錯誤")).toBeInTheDocument();
    expect(screen.getByText("66.7%")).toBeInTheDocument();
    expect(screen.getByText(/共 3 家被排除/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("匯入批次（模型版本）"), { target: { value: "1" } });
    await waitFor(() => expect(fn.mock.calls.some(([u]) => String(u).includes("run_id=1"))).toBe(true));
  });

  it("test_m4_02b_empty_state：沒有匯入過時顯示空狀態", async () => {
    mount(<AdminModelPage />, () => ({ run_id: null, runs: [], total: 0, items: [] }));
    expect(await screen.findByText("還沒有匯入過名單")).toBeInTheDocument();
  });

  it("test_m4_02b_error_state：沒有權限或失敗時顯示錯誤", async () => {
    mount(<AdminModelPage />, () => errorResponse(403, "FORBIDDEN", "沒權限"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
