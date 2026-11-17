import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { RejectDialog } from "./RejectDialog";

function setup() {
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url.startsWith("/api/v1/dimensions")) {
      return Response.json({ industries: [], priorities: [], reject_reasons: ["no_demand", "other"], statuses: [], users: [] });
    }
    return Response.json({ updated: 2, status: "rejected" });
  });
  vi.stubGlobal("fetch", fetchMock);
  const onDone = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <RejectDialog open companyIds={[1, 2]} onClose={() => {}} onDone={onDone} />
    </QueryClientProvider>,
  );
  return { fetchMock, onDone };
}

describe("F-REC-3 批次排除要選原因", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("test_f_rec_3_reject_requires_reason：沒選原因不能送出，選了才送", async () => {
    const { fetchMock, onDone } = setup();
    const confirm = screen.getByRole("button", { name: "確認排除" });
    expect(confirm).toBeDisabled();

    fireEvent.click(await screen.findByLabelText("沒有端子台需求"));
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);

    await waitFor(() => expect(onDone).toHaveBeenCalledWith(2));
    const call = fetchMock.mock.calls.find(([url]) => url === "/api/v1/reviews");
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      company_ids: [1, 2],
      decision: "rejected",
      reject_reason: "no_demand",
    });
  });
});
