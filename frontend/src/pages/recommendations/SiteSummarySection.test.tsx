import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { CompanyDetail } from "../../api/types";
import { SiteSummarySection } from "./SiteSummarySection";

// 只用到 company_id、website_url、site_summary；其餘欄位對這個元件沒有影響
const company = (over: Partial<CompanyDetail>): CompanyDetail =>
  ({ company_id: 3, website_url: "https://www.example.com", site_summary: null, ...over }) as CompanyDetail;

function mount(c: CompanyDetail, canAct = true) {
  const fn = vi.fn(async () => Response.json(c, { status: 202 }));
  vi.stubGlobal("fetch", fn);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <SiteSummarySection company={c} canAct={canAct} />
    </QueryClientProvider>,
  );
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("M4-08e 官網摘要區塊", () => {
  it("test_m4_08e_shows_summary_with_fetched_time：顯示摘要、抓取時間與個資說明", () => {
    mount(
      company({
        site_summary: {
          status: "ok",
          summary: "製造包裝機械與控制盤。",
          error_code: null,
          source_url: "https://www.example.com",
          fetched_at: "2026-11-18T02:00:00Z",
        },
      }),
    );
    expect(screen.getByText("製造包裝機械與控制盤。")).toBeInTheDocument();
    expect(screen.getByText(/抓取時間/)).toBeInTheDocument();
    expect(screen.getByText(/不含人名、email、電話/)).toBeInTheDocument();
  });

  it("test_m4_08e_failed_state_explains_fallback：抓取失敗顯示中文原因，並說明改用推薦理由", () => {
    mount(
      company({
        site_summary: {
          status: "failed",
          summary: null,
          error_code: "SITE_ROBOTS_DISALLOWED",
          source_url: null,
          fetched_at: "2026-11-18T02:00:00Z",
        },
      }),
    );
    expect(screen.getByRole("status")).toHaveTextContent("robots.txt 不允許自動讀取");
    expect(screen.getByRole("status")).toHaveTextContent("改用推薦理由");
  });

  it("test_m4_08e_empty_and_no_website_states：還沒抓過、沒有官網各有說明；沒官網不能重新抓取", () => {
    mount(company({}));
    expect(screen.getByText(/還沒有摘要/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新抓取" })).toBeEnabled();
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
    mount(company({ website_url: null }));
    expect(screen.getByText(/沒有官網/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新抓取" })).toBeDisabled();
  });

  it("test_m4_08e_refresh_posts：按重新抓取會呼叫 refresh API；被鎖定時不能按", async () => {
    const fn = mount(company({}));
    fireEvent.click(screen.getByRole("button", { name: "重新抓取" }));
    await waitFor(() => expect(fn).toHaveBeenCalled());
    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/companies/3/site-summary/refresh");
    expect(init.method).toBe("POST");
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
    mount(company({}), false);
    expect(screen.getByRole("button", { name: "重新抓取" })).toBeDisabled();
  });
});
