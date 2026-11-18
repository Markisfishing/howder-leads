import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { ImportBatch, ImportBatchDetail } from "../api/types";
import { AdminImportsPage } from "./AdminImportsPage";

const batch: ImportBatch = {
  batch_id: 7,
  file_name: "sample.csv",
  source: "file",
  status: "previewed",
  model_name: null,
  run_id: null,
  rows_total: 3,
  rows_created: 2,
  rows_updated: 0,
  rows_unchanged: 0,
  rows_error: 1,
  created_at: "2026-11-18T02:00:00Z",
};

const detail: ImportBatchDetail = {
  ...batch,
  rows_skipped: 0,
  rows: [
    {
      row: 2,
      tax_id: "90000101",
      name: "範例自動化",
      priority: "A",
      industry_id: 1,
      likelihood: "高",
      is_competitor: false,
      website_url: null,
      fit_stars: 4.5,
      source: "expo",
      action: "create",
    },
  ],
  errors: [{ row: 4, field: "tax_id", message: "統編格式不正確" }],
  warnings: [{ row: 0, field: "備註", message: "看不懂的欄位會被忽略" }],
};

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;

function setup(handler: Handler) {
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => handler(url, init));
  vi.stubGlobal("fetch", fn);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AdminImportsPage />
    </QueryClientProvider>,
  );
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("名單管理頁（F-IMP-1～4）", () => {
  it("test_f_imp_1_upload_button_needs_a_file：沒選檔案時不能上傳", () => {
    setup(() => Response.json([]));
    expect(screen.getByRole("button", { name: "上傳並預覽" })).toBeDisabled();
  });

  it("test_f_imp_2_upload_shows_preview_with_counts_and_errors：上傳後顯示預覽、略過說明與錯誤列", async () => {
    const fn = setup((url, init) =>
      url === "/api/v1/imports" && init.method === "POST" ? Response.json(detail, { status: 201 }) : Response.json([]),
    );
    const file = new File(["tax_id,name"], "sample.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/檔案/), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "上傳並預覽" }));

    expect(await screen.findByRole("region", { name: "匯入預覽" })).toBeInTheDocument();
    expect(screen.getByText("範例自動化")).toBeInTheDocument();
    expect(screen.getByText("統編格式不正確")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("確認匯入時會略過這些列");
    expect(screen.getByText(/看不懂的欄位會被忽略/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "略過錯誤列，匯入 2 筆" })).toBeEnabled();
    const upload = fn.mock.calls.find(([u, init]) => u === "/api/v1/imports" && init?.method === "POST");
    expect(upload).toBeDefined();
  });

  it("test_f_imp_3_commit_posts_and_shows_notice：確認匯入會呼叫 commit，並顯示匯入批次編號", async () => {
    const fn = setup((url, init) => {
      if (url === "/api/v1/imports" && init.method === "POST") return Response.json(detail, { status: 201 });
      if (url === "/api/v1/imports/7/commit")
        return Response.json({ ...detail, status: "committed", run_id: 12, rows_created: 2, rows_updated: 0 });
      return Response.json([]);
    });
    fireEvent.change(screen.getByLabelText(/檔案/), {
      target: { files: [new File(["x"], "sample.csv", { type: "text/csv" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "上傳並預覽" }));
    fireEvent.click(await screen.findByRole("button", { name: /略過錯誤列/ }));

    await waitFor(() => expect(screen.getByText(/匯入批次 #12/)).toBeInTheDocument());
    expect(fn.mock.calls.some(([u, init]) => u === "/api/v1/imports/7/commit" && init?.method === "POST")).toBe(true);
    expect(screen.queryByRole("region", { name: "匯入預覽" })).not.toBeInTheDocument();
  });

  it("test_f_imp_3_all_rows_invalid_cannot_commit：全部列都有錯時不能確認匯入", async () => {
    setup((url, init) =>
      url === "/api/v1/imports" && init.method === "POST"
        ? Response.json({ ...detail, rows_created: 0, rows: [] }, { status: 201 })
        : Response.json([]),
    );
    fireEvent.change(screen.getByLabelText(/檔案/), {
      target: { files: [new File(["x"], "bad.csv", { type: "text/csv" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "上傳並預覽" }));
    expect(await screen.findByRole("button", { name: /匯入 0 筆/ })).toBeDisabled();
  });

  it("test_f_imp_4_cancel_posts：取消這次匯入會呼叫 cancel", async () => {
    const fn = setup((url, init) => {
      if (url === "/api/v1/imports" && init.method === "POST") return Response.json(detail, { status: 201 });
      if (url === "/api/v1/imports/7/cancel") return Response.json({ ...detail, status: "cancelled" });
      return Response.json([]);
    });
    fireEvent.change(screen.getByLabelText(/檔案/), {
      target: { files: [new File(["x"], "sample.csv", { type: "text/csv" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "上傳並預覽" }));
    fireEvent.click(await screen.findByRole("button", { name: "取消這次匯入" }));
    expect(await screen.findByText("已取消這次匯入")).toBeInTheDocument();
    expect(fn.mock.calls.some(([u]) => u === "/api/v1/imports/7/cancel")).toBe(true);
  });

  it("test_f_imp_6_history_states：匯入紀錄的空資料、錯誤與正常三種狀態", async () => {
    setup(() => Response.json([]));
    fireEvent.click(screen.getByRole("button", { name: "匯入紀錄" }));
    expect(await screen.findByText("還沒有匯入紀錄")).toBeInTheDocument();
    vi.unstubAllGlobals();
    document.body.innerHTML = "";

    setup(() => Response.json({ error: { code: "INTERNAL", message: "壞了" } }, { status: 500 }));
    fireEvent.click(screen.getByRole("button", { name: "匯入紀錄" }));
    expect(await screen.findByRole("button", { name: /重試|重新/ })).toBeInTheDocument();
    vi.unstubAllGlobals();
    document.body.innerHTML = "";

    setup(() => Response.json([{ ...batch, status: "committed", run_id: 12 }]));
    fireEvent.click(screen.getByRole("button", { name: "匯入紀錄" }));
    expect(await screen.findByText("sample.csv")).toBeInTheDocument();
    expect(screen.getByText("已匯入")).toBeInTheDocument();
    expect(screen.getByText("#12")).toBeInTheDocument();
  });
});
