import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { EmailTemplate } from "../api/types";
import { AdminTemplatesPage } from "./AdminTemplatesPage";

const tpl: EmailTemplate = {
  template_id: 1,
  family_id: 1,
  name: "邀請信",
  version: 1,
  is_active: true,
  subject: "{{company_name}} 合作邀請",
  body_text: "{{contact_name}} 您好\n\n{{unsubscribe}}",
  created_at: "2026-11-17T00:00:00Z",
};

function setup() {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/v1/templates" && init?.method === "GET") return Response.json([tpl]);
    if (url === "/api/v1/templates/variables")
      return Response.json([{ name: "company_name", label: "公司名稱", required: false }]);
    if (url.endsWith("/versions")) return Response.json([tpl]);
    if (url === "/api/v1/templates/preview")
      return Response.json({ subject: "範例 合作邀請", body_text: "王經理 您好", body_html: "<p>王經理 您好</p>" });
    return Response.json({ ...tpl, template_id: 2, version: 2 });
  });
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AdminTemplatesPage />
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("M2-02b 郵件模板頁", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("test_m2_02b_edit_saves_new_version：編輯後存成新版本，並能插入變數", async () => {
    const fetchMock = setup();
    fireEvent.click(await screen.findByRole("button", { name: "編輯" }));
    expect(screen.getByText(/存檔會建立第 2 版/)).toBeInTheDocument();
    const previewToggle = screen.getByRole("button", { name: "顯示預覽" });
    expect(previewToggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(previewToggle);
    expect(screen.getByRole("button", { name: "隱藏預覽" })).toHaveAttribute("aria-expanded", "true");

    const body = screen.getByLabelText(/內文/) as HTMLTextAreaElement;
    body.setSelectionRange(0, 0);
    fireEvent.click(await screen.findByRole("button", { name: "公司名稱" }));
    expect(body.value.startsWith("{{company_name}}")).toBe(true);

    expect(await screen.findByText("範例 合作邀請")).toBeInTheDocument(); // 假資料預覽
    fireEvent.click(screen.getByRole("button", { name: "存成新版本" }));
    await waitFor(() => expect(screen.getByText("已儲存「邀請信」第 2 版")).toBeInTheDocument());

    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(put?.[0]).toBe("/api/v1/templates/1");
    expect(JSON.parse(String(put?.[1]?.body)).body_text.startsWith("{{company_name}}")).toBe(true);
  });
});
