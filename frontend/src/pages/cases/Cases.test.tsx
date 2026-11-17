import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CaseDetail, CaseList } from "../../api/types";
import { allowedResults } from "./CasePanel";
import { CasesPage, readCaseQuery } from "./CasesPage";

vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => ({ isManager: false, isAdmin: false }) }));

const base: CaseDetail = {
  case_id: 7,
  case_no: "C-0007",
  company_id: 3,
  company_name: "測試公司",
  company_status: "sent",
  contact_id: 9,
  contact_name: "測試窗口",
  contact_email: "buyer@example.com",
  owner_id: 1,
  owner_name: "業務甲",
  origin: "email",
  status: "sent",
  opened_at: "2026-11-01T02:00:00Z",
  last_update_at: null,
  next_follow_up: null,
  amount_twd: null,
  closed_at: null,
  reminders: ["overdue_report"],
  timeline: [
    {
      update_id: 1,
      user_name: "業務甲",
      channel: "system",
      contact_name: "測試窗口",
      result: "sent",
      note: "寄出開發信（草稿 #1）",
      next_follow_up: null,
      amount_twd: null,
      created_at: "2026-11-01T02:00:00Z",
    },
  ],
  contacts: [{ contact_id: 9, name: "測試窗口", email: "buyer@example.com", unsubscribed: false }],
};
const list: CaseList = {
  items: [base],
  counts: { sent: 1, tracking: 0, replied: 0, negotiating: 0, no_response: 0, won: 0, lost: 0 },
};

function setup(path = "/cases/7") {
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    if (url.startsWith("/api/v1/cases?") || url === "/api/v1/cases") return Response.json(list);
    if (url === "/api/v1/cases/7" && init.method === "GET") return Response.json(base);
    if (url === "/api/v1/cases/7/updates") return Response.json({ ...base, status: "negotiating" }, { status: 201 });
    if (url === "/api/v1/cases/7/unsubscribe") return Response.json({ ...base, status: "lost" });
    if (url === "/api/v1/dimensions") return Response.json({ users: [] });
    return Response.json({});
  });
  vi.stubGlobal("fetch", fn);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/cases" element={<CasesPage />} />
          <Route path="/cases/:id" element={<CasesPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fn;
}
const posted = (fn: ReturnType<typeof setup>, url: string) =>
  fn.mock.calls.filter(([u, init]) => u === url && init?.method === "POST");

afterEach(() => vi.unstubAllGlobals());

describe("M3-11 案件純函式", () => {
  it("test_f_case_4_query_from_url：網址參數轉成篩選，不合法的值忽略", () => {
    expect(readCaseQuery(new URLSearchParams("status=replied&owner=2&from=2026-11-01&overdue=1"))).toMatchObject({
      status: "replied",
      owner: 2,
      sent_from: "2026-11-01",
      sent_to: null,
      overdue: true,
    });
    expect(readCaseQuery(new URLSearchParams("status=bogus&owner=x")).status).toBeNull();
  });

  it("test_f_case_2_allowed_results：不能往回走，結案後不能回填", () => {
    expect(allowedResults("negotiating")).toEqual(["negotiating", "won", "lost"]);
    expect(allowedResults("won")).toEqual([]);
    expect(allowedResults("sent")).toContain("no_response");
  });
});

describe("M3-11 案件頁", () => {
  it("test_f_case_4_list_counts_and_reminders：顯示各狀態件數與待辦提醒", async () => {
    setup("/cases");
    expect(await screen.findByText("逾期，請回報")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /我的待辦/ })).toHaveTextContent("1");
    expect(screen.getByText("集中處理今天需要跟進的案件。")).toBeInTheDocument();
  });

  it("test_f_case_2_backfill_form_posts_update：回填送出管道、結果、備註、下次追蹤日", async () => {
    const fn = setup();
    expect(await screen.findByText("寄出開發信（草稿 #1）")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "記錄聯絡結果" }));
    fireEvent.change(screen.getByLabelText("管道"), { target: { value: "visit" } });
    fireEvent.change(screen.getByLabelText("結果"), { target: { value: "negotiating" } });
    fireEvent.change(screen.getByLabelText(/客戶說了什麼/), { target: { value: "  客戶要報價  " } });
    fireEvent.change(screen.getByLabelText(/下一次追蹤/), { target: { value: "2099-01-02" } });
    expect(screen.queryByLabelText(/成交金額/)).not.toBeInTheDocument(); // 只有成交才填金額
    fireEvent.click(screen.getByRole("button", { name: "儲存紀錄" }));
    await waitFor(() => expect(posted(fn, "/api/v1/cases/7/updates")).toHaveLength(1));
    expect(JSON.parse(String(posted(fn, "/api/v1/cases/7/updates")[0]?.[1]?.body))).toEqual({
      channel: "visit",
      result: "negotiating",
      contact_id: 9,
      note: "客戶要報價",
      next_follow_up: "2099-01-02",
      amount_twd: null,
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("test_f_case_2_won_shows_amount：選成交時顯示金額、隱藏下次追蹤日", async () => {
    setup();
    fireEvent.click(await screen.findByRole("button", { name: "記錄聯絡結果" }));
    fireEvent.change(await screen.findByLabelText("結果"), { target: { value: "won" } });
    expect(screen.getByLabelText(/成交金額/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/下次追蹤日/)).not.toBeInTheDocument();
  });

  it("test_m3_04a_unsubscribe_needs_confirm：客戶要求退訂要再按一次確認", async () => {
    const fn = setup();
    fireEvent.click(await screen.findByRole("button", { name: "更多操作 ⋯" }));
    fireEvent.click(screen.getByRole("button", { name: "客戶要求停止聯絡" }));
    expect(posted(fn, "/api/v1/cases/7/unsubscribe")).toHaveLength(0);
    expect(screen.getByRole("alert")).toHaveTextContent("不再聯絡");
    fireEvent.click(screen.getByRole("button", { name: "確定標記退訂" }));
    await waitFor(() => expect(posted(fn, "/api/v1/cases/7/unsubscribe")).toHaveLength(1));
  });
});
