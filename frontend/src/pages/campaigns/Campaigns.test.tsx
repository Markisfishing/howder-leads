import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { Campaign, Candidate, Draft } from "../../api/types";
import { draftErrorText } from "../../lib/labels";
import { CampaignNewPage } from "./CampaignNewPage";
import { CampaignReviewPage, nextToReview } from "./CampaignReviewPage";
import { needsAction, progressText } from "./CampaignsPage";

const me = { user_id: 1, display_name: "業務甲", role: "sales" as const, email: "sales1@example.com" };
vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => ({ user: me, isAdmin: false }) }));

const progress = {
  total: 2,
  generating: 0,
  pending_review: 2,
  approved: 0,
  scheduled: 0,
  sent: 0,
  failed: 0,
  discarded: 0,
};
const campaign: Campaign = {
  campaign_id: 5,
  name: "測試批次",
  status: "reviewing",
  gen_mode: "template_only",
  template_id: 1,
  template_name: "邀請信",
  template_version: 1,
  owner_id: 1,
  owner_name: "業務甲",
  scheduled_at: null,
  created_at: "2026-11-18T00:00:00Z",
  progress,
};
const draft = (id: number, status: Draft["status"] = "pending_review"): Draft => ({
  draft_id: id,
  campaign_id: 5,
  company_id: id,
  company_name: `公司${id}`,
  contact_id: id,
  contact_name: null,
  contact_email: `buyer${id}@example.com`,
  subject: `主旨${id}`,
  body_text: `內文${id}`,
  status,
  edit_ratio: null,
  scheduled_at: null,
  send_attempts: 0,
  last_error: null,
  approved_at: null,
});

type Handler = (url: string, init: RequestInit) => unknown;
function mockFetch(handler: Handler) {
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    const out = handler(url, init);
    return out instanceof Response ? out : Response.json(out ?? {});
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
const calls = (fn: ReturnType<typeof mockFetch>, method: string, url: string) =>
  fn.mock.calls.filter(([u, init]) => u === url && init?.method === method);

function renderAt(path: string, element: React.ReactNode, route: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
          <Route path="/campaigns/:id" element={<p>到了批次頁</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const sandbox = { mail_mode: "sandbox", status: "not_required", connected_at: null, scopes: [], resumed: 0 };
const reasons = { UNSUBSCRIBED: "聯絡人已退訂", LOCKED_BY_OTHER: "由其他業務負責" };

afterEach(() => vi.unstubAllGlobals());

describe("M2 邀請信純函式", () => {
  it("test_m2_03e_progress_text：只顯示不是 0 的項目", () => {
    expect(progressText({ ...progress, total: 3, pending_review: 1, sent: 2 })).toBe("共 3 封：待審核 1、已寄出 2");
  });

  it("test_m2_16_ready_is_todo：待寄出的批次也算我的待辦，已排程的不算", () => {
    const done = { ...progress, pending_review: 0, failed: 0, approved: 2 };
    expect(needsAction({ ...campaign, status: "ready", progress: done })).toBe(true);
    expect(needsAction({ ...campaign, status: "scheduled", progress: done })).toBe(false);
    expect(needsAction({ ...campaign, status: "reviewing", progress: { ...done, pending_review: 1 } })).toBe(true);
  });

  it("test_m2_05b_next_to_review：跳到下一封待審核或失敗的，最後回頭找", () => {
    const list = [draft(1, "approved"), draft(2), draft(3, "sent"), draft(4, "failed")];
    expect(nextToReview(list, 2)).toBe(4);
    expect(nextToReview(list, 4)).toBe(2);
    expect(nextToReview([draft(1, "approved")], 1)).toBeNull();
  });

  it("test_m2_07e_draft_error_text：防呆代碼翻成中文", () => {
    expect(draftErrorText("GUARD:UNSUBSCRIBED,LOCKED_BY_OTHER", reasons)).toBe(
      "寄出前檢查沒過：聯絡人已退訂、由其他業務負責",
    );
    expect(draftErrorText("MAIL_AUTH_REQUIRED")).toBe("Outlook 連結已失效，請重新連結");
    expect(draftErrorText(null)).toBeNull();
  });
});

describe("M2-03d 建立批次", () => {
  const ok: Candidate = {
    company_id: 10,
    name: "可寄公司",
    stars: 5,
    priority: "A",
    industry: "電子",
    owner_name: "業務甲",
    contacts: [{ contact_id: 100, name: null, email: "a@example.com", unsubscribed: false }],
    default_contact_id: 100,
    reasons: [],
  };
  const blocked: Candidate = { ...ok, company_id: 11, name: "退訂公司", reasons: ["UNSUBSCRIBED"] };

  it("test_f_mail_1_create_campaign_with_selected_targets：勾選對象後建立，被排除的顯示原因", async () => {
    const fn = mockFetch((url, init) => {
      if (url === "/api/v1/campaigns/candidates") return [ok, blocked];
      if (url === "/api/v1/templates") return [{ template_id: 1, name: "邀請信", version: 2 }];
      if (url === "/api/v1/campaigns/exclusion-reasons") return reasons;
      if (url === "/api/v1/campaigns" && init.method === "POST")
        return Response.json({ campaign, job_id: 1, excluded: [] }, { status: 201 });
      return {};
    });
    renderAt("/campaigns/new", <CampaignNewPage />, "/campaigns/new");

    expect(await screen.findByText("原因：聯絡人已退訂")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "退訂公司（不能選）" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /整封 AI 撰寫/ })).toBeDisabled(); // M4 才開放

    const submit = screen.getByRole("button", { name: "產生 0 封草稿" });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /可寄公司/ }));
    await screen.findByRole("option", { name: /邀請信（第 2 版）/ });
    fireEvent.click(screen.getByRole("button", { name: "產生 1 封草稿" }));

    expect(await screen.findByText("到了批次頁")).toBeInTheDocument();
    const body = JSON.parse(String(calls(fn, "POST", "/api/v1/campaigns")[0]?.[1]?.body));
    expect(body).toMatchObject({ template_id: 1, gen_mode: "template_only", targets: [{ company_id: 10, contact_id: 100 }] });
  });
});

describe("M2-05 預覽佇列", () => {
  function setupReview(overrides: Partial<Campaign> = {}) {
    let drafts = [draft(1), draft(2)];
    const cp = { ...campaign, ...overrides };
    const fn = mockFetch((url, init) => {
      if (url === "/api/v1/campaigns/5") return cp;
      if (url.startsWith("/api/v1/campaigns/5/drafts?")) return { items: drafts, total: drafts.length, page: 1, page_size: 25, status_counts: { pending_review: drafts.filter((item) => item.status === "pending_review").length, approved: drafts.filter((item) => item.status === "approved").length } };
      if (url === "/api/v1/campaigns/exclusion-reasons") return reasons;
      if (url === "/api/v1/me/mail-connection") return sandbox;
      const m = /\/api\/v1\/drafts\/(\d+)\/approve$/.exec(url);
      if (m && init.method === "POST") {
        drafts = drafts.map((d) => (d.draft_id === Number(m[1]) ? { ...d, status: "approved" } : d));
        return drafts.find((d) => d.draft_id === Number(m[1]));
      }
      if (url === "/api/v1/campaigns/5/approve-all") return cp;
      if (url === "/api/v1/campaigns/5/send") return { scheduled: 2, blocked: [], campaign: cp };
      return {};
    });
    renderAt("/campaigns/5", <CampaignReviewPage />, "/campaigns/:id");
    return fn;
  }

  it("test_m2_14_keyboard_approve_and_next：Ctrl+Enter 核准並跳到下一封", async () => {
    const fn = setupReview();
    fireEvent.click(await screen.findByRole("row", { name: /公司1/ }));
    const subject = await screen.findByDisplayValue("主旨1");
    fireEvent.keyDown(subject, { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(calls(fn, "POST", "/api/v1/drafts/1/approve")).toHaveLength(1));
    expect(await screen.findByDisplayValue("主旨2")).toHaveFocus(); // 焦點自動放到下一封
    expect(calls(fn, "PATCH", "/api/v1/drafts/1")).toHaveLength(0); // 沒改就不存
  });

  it("test_f_mail_4_approve_all_needs_second_click：全部核准要按兩次", async () => {
    const fn = setupReview();
    fireEvent.click(await screen.findByRole("button", { name: "全部核准…" }));
    expect(calls(fn, "POST", "/api/v1/campaigns/5/approve-all")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "確定全部核准 2 封" }));
    await waitFor(() => expect(calls(fn, "POST", "/api/v1/campaigns/5/approve-all")).toHaveLength(1));
    expect(JSON.parse(String(calls(fn, "POST", "/api/v1/campaigns/5/approve-all")[0]?.[1]?.body))).toEqual({
      confirm: true,
    });
  });

  it("test_f_mail_6_send_confirm_dialog：寄出要在對話框再確認，沒填時間就立即寄", async () => {
    const fn = setupReview({ progress: { ...progress, pending_review: 0, approved: 2 } });
    const sendButton = await screen.findByRole("button", { name: "寄出已核准的 2 封…" });
    await waitFor(() => expect(sendButton).toBeEnabled());
    fireEvent.click(sendButton);
    const dialog = await screen.findByRole("dialog");
    expect(calls(fn, "POST", "/api/v1/campaigns/5/send")).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "確定立即寄出" }));
    await waitFor(() => expect(calls(fn, "POST", "/api/v1/campaigns/5/send")).toHaveLength(1));
    expect(await screen.findByText(/已排入寄送 2 封/)).toBeInTheDocument();
  });

  it("test_m2_07d_only_owner_sees_send：不是負責業務就沒有寄出按鈕", async () => {
    setupReview({ owner_id: 99, owner_name: "業務乙", progress: { ...progress, approved: 2 } });
    expect(await screen.findByText(/只有 業務乙 可以寄/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /寄出已核准/ })).not.toBeInTheDocument();
  });
});
