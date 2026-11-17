import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { Overview } from "../../api/types";
import { formatRate, OverviewPage, readOverviewQuery, REMINDER_LINKS } from "./OverviewPage";

vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => ({ isManager: true, isAdmin: false }) }));

const data: Overview = {
  scope_owner_id: null,
  kpis: {
    companies: 120,
    high_priority: 30,
    sent: 16,
    replied: 4,
    reply_rate: "0.2500",
    won: 1,
    won_amount_twd: "50000",
  },
  funnel: [
    { key: "list", label: "名單", count: 120, rate: null },
    { key: "approved", label: "審核通過", count: 60, rate: "0.5000" },
    { key: "sent", label: "已寄信", count: 16, rate: "0.2667" },
    { key: "replied", label: "回覆", count: 4, rate: "0.2500" },
    { key: "won", label: "成交", count: 1, rate: "0.2500" },
  ],
  mle_funnel: { 產品命中: 900, 資料庫總數: 39000 }, // JSONB 回來的順序不固定
  by_source: [
    { source: "expo", sent: 12, replied: 4, reply_rate: "0.3333", insufficient: false },
    { source: "b2b", sent: 3, replied: 0, reply_rate: null, insufficient: true },
  ],
  reminders: [
    { kind: "overdue_report", label: "逾期未回報", count: 2 },
    { kind: "pending_review", label: "新名單待審核", count: 5 },
  ],
};

function setup(path = "/overview") {
  const fn = vi.fn(async (url: string) => {
    if (url.startsWith("/api/v1/metrics/overview")) return Response.json(data);
    if (url === "/api/v1/dimensions") return Response.json({ industries: [], users: [] });
    return Response.json({});
  });
  vi.stubGlobal("fetch", fn);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <OverviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("M3-12b 總覽純函式", () => {
  it("test_f_dash_1_query_from_url：網址參數轉成篩選，不合法的值忽略", () => {
    expect(readOverviewQuery(new URLSearchParams("from=2026-11-01&industry=3&owner=x&product=盤"))).toEqual({
      from: "2026-11-01",
      to: null,
      industry: 3,
      product_type: "盤",
      owner: null,
    });
    expect(readOverviewQuery(new URLSearchParams("from=11/01")).from).toBeNull();
  });

  it("test_f_dash_3_rate_format：比例轉百分比，樣本不足顯示 —", () => {
    expect(formatRate("0.2667")).toBe("26.7%");
    expect(formatRate(null)).toBe("—");
  });
});

describe("M3-12b 總覽頁", () => {
  it("test_f_dash_1_kpis_and_funnel：顯示 KPI 與漏斗留存率（不在前端重算）", async () => {
    const fn = setup("/overview?from=2026-11-01");
    expect(await screen.findByText("名單公司數")).toBeInTheDocument();
    expect(screen.getByText("25.0%")).toBeInTheDocument();
    expect(screen.getByText("（留存 50.0%）")).toBeInTheDocument();
    expect(screen.getByText(/資料庫總數 39,000 → 產品命中 900/)).toBeInTheDocument();
    expect(String(fn.mock.calls[0]?.[0])).toContain("from=2026-11-01");
  });

  it("test_f_dash_3_insufficient_sample_tag：寄出少於 10 封標「樣本不足」", async () => {
    setup();
    const row = (await screen.findByText("b2b")).closest("tr") as HTMLElement;
    expect(within(row).getByText("樣本不足")).toBeInTheDocument();
  });

  it("test_f_dash_4_reminders_link_to_lists：待辦件數可以點進對應清單", async () => {
    setup();
    const link = await screen.findByRole("link", { name: /新名單待審核/ });
    expect(link).toHaveAttribute("href", REMINDER_LINKS.pending_review);
    expect(screen.getByRole("link", { name: /逾期未回報/ })).toHaveAttribute("href", REMINDER_LINKS.overdue_report);
  });
});
