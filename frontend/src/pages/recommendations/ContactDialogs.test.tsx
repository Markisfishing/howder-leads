import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import type { Contact } from "../../api/types";
import { ContactConfirmDialog } from "./ContactConfirmDialog";
import { ContactDialog } from "./ContactDialog";

const contact: Contact = {
  contact_id: 7,
  name: "王小明",
  title: "採購",
  email: "buyer@example.com",
  source: "website",
  is_verified: false,
  unsubscribed: false,
};

function wrap(ui: ReactNode) {
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
    init?.method === "DELETE" ? new Response(null, { status: 204 }) : Response.json(contact),
  );
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
  return fetchMock;
}

const bodyOf = (call: unknown[] | undefined) => JSON.parse(String((call?.[1] as RequestInit | undefined)?.body));

describe("M2-01b 聯絡人對話框", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("test_m2_01b_create_requires_email_and_source：沒填 email 或來源不能儲存", async () => {
    const onClose = vi.fn();
    const fetchMock = wrap(<ContactDialog companyId={3} contact={null} onClose={onClose} />);
    const save = screen.getByRole("button", { name: "儲存" });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText("email（必填）"), { target: { value: " new@example.com " } });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("來源（必填）"), { target: { value: "business_card" } });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([url]) => url === "/api/v1/contacts");
    expect(call?.[1]?.method).toBe("POST");
    expect(bodyOf(call)).toEqual({
      company_id: 3,
      email: "new@example.com",
      source: "business_card",
      is_verified: false,
    });
  });

  it("test_m2_01b_edit_sends_only_changed_fields：編輯只送有改的欄位", async () => {
    const onClose = vi.fn();
    const fetchMock = wrap(<ContactDialog companyId={3} contact={contact} onClose={onClose} />);
    fireEvent.change(screen.getByLabelText("職稱（選填）"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([url]) => url === "/api/v1/contacts/7");
    expect(call?.[1]?.method).toBe("PATCH");
    expect(bodyOf(call)).toEqual({ title: null });
  });

  it("test_m2_01b_delete_requires_reason_and_confirmation：刪除要填原因並勾選了解", async () => {
    const onClose = vi.fn();
    const fetchMock = wrap(<ContactConfirmDialog kind="delete" contact={contact} onClose={onClose} />);
    const confirm = screen.getByRole("button", { name: "永久刪除" });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText("刪除原因（必填）"), { target: { value: "客戶來信要求" } });
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByLabelText("我了解刪除後無法復原"));
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([url]) => url === "/api/v1/contacts/7");
    expect(call?.[1]?.method).toBe("DELETE");
    expect(bodyOf(call)).toEqual({ reason: "客戶來信要求" });
  });

  it("test_m3_17_unsubscribe_confirm：預設只退訂這位聯絡人，備註選填", async () => {
    const onClose = vi.fn();
    const fetchMock = wrap(<ContactConfirmDialog kind="unsubscribe" contact={contact} onClose={onClose} />);
    expect(screen.getByText(/改成已退訂，之後不會再寄信給他/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "確認退訂" }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([url]) => url === "/api/v1/contacts/7/unsubscribe");
    expect(call?.[1]?.method).toBe("POST");
    expect(bodyOf(call)).toMatchObject({ whole_company: false });
  });

  it("test_m3_17_unsubscribe_whole_company：勾選整家公司不再聯絡會送 whole_company", async () => {
    const onClose = vi.fn();
    const fetchMock = wrap(<ContactConfirmDialog kind="unsubscribe" contact={contact} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText(/整家公司都不要再聯絡/));
    fireEvent.click(screen.getByRole("button", { name: "確認退訂" }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([url]) => url === "/api/v1/contacts/7/unsubscribe");
    expect(bodyOf(call)).toMatchObject({ whole_company: true });
  });
});
