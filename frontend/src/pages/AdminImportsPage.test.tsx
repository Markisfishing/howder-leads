import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { ImportBatchDetail } from "../api/types";
import { AdminImportsPage } from "./AdminImportsPage";

// 假資料：公司名、統編都是虛構的
const preview: ImportBatchDetail = {
  batch_id: 7,
  file_name: "list.csv",
  source: "csv",
  status: "previewed",
  model_name: null,
  run_id: null,
  rows_total: 4,
  rows_created: 1,
  rows_updated: 1,
  rows_unchanged: 0,
  rows_error: 1,
  rows_skipped: 1,
  created_at: "2026-11-18T00:00:00Z",
  funnel: null,
  rows: [
    { row: 2, tax_id: "90000101", name: "範例自動化", priority: "A", industry_id: 1, likelihood: null, is_competitor: false, website_url: null, fit_stars: 4.5, source: "expo", action: "create" },
    { row: 3, tax_id: "90000102", name: "範例配電", priority: "B", industry_id: 2, likelihood: null, is_competitor: false, website_url: null, action: "update", changed_fields: ["產業", "優先級"] },
  ],
  errors: [{ row: 5, field: "統編", message: "統編必須是 8 碼數字" }],
  warnings: [{ row: 0, field: "備註欄", message: "看不懂的欄位「備註欄」會被忽略" }],
};

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

function setup(handler: Handler) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => handler(url, init));
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AdminImportsPage />
    </QueryClientProvider>,
  );
  return fetchMock;
}

function chooseFile() {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("找不到檔案欄位");
  fireEvent.change(input, { target: { files: [new File(["統編\n"], "list.csv", { type: "text/csv" })] } });
  fireEvent.click(screen.getByRole("button", { name: "上傳並預覽" }));
}

const base: Handler = (url, init) => {
  if (url === "/api/v1/imports" && init?.method === "POST") return Response.json(preview, { status: 201 });
  if (url === "/api/v1/imports") return Response.json([]);
  if (url === "/api/v1/imports/7/commit")
    return Response.json({ ...preview, status: "committed", run_id: 3, rows_created: 1, rows_updated: 1 });
  if (url === "/api/v1/imports/7/cancel") return Response.json({ ...preview, status: "cancelled" });
  return Response.json({});
};

describe("名單匯入頁（F-IMP）", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("test_f_imp_2_upload_shows_preview_diff：上傳後顯示新增／更新／錯誤與提示，錯誤列另外列出", async () => {
    const fetchMock = setup(base);
    expect(screen.getByRole("button", { name: "上傳並預覽" })).toBeDisabled(); // 沒選檔案不能上傳
    chooseFile();

    const card = await screen.findByRole("region", { name: "匯入預覽" });
    expect(within(card).getByText("預覽：list.csv")).toBeInTheDocument();
    expect(within(card).getByText("範例自動化")).toBeInTheDocument();
    expect(within(card).getByText("產業、優先級")).toBeInTheDocument();
    expect(within(card).getByText("統編必須是 8 碼數字")).toBeInTheDocument();
    expect(within(card).getByText(/看不懂的欄位/)).toBeInTheDocument();
    expect(within(card).getByText(/有 1 列網址狀態是 invalid/)).toBeInTheDocument();
    expect(within(card).getByRole("alert")).toHaveTextContent("有 1 列有錯誤");

    const post = fetchMock.mock.calls.find(([u, init]) => u === "/api/v1/imports" && init?.method === "POST");
    expect(post?.[1]?.body).toBeInstanceOf(FormData);
  });

  it("test_f_imp_2_commit_skips_error_rows：有錯誤列時按鈕寫出只匯入幾筆，確認後顯示結果並收起預覽", async () => {
    const fetchMock = setup(base);
    chooseFile();
    fireEvent.click(await screen.findByRole("button", { name: "略過錯誤列，匯入 2 筆" }));

    expect(await screen.findByText("已匯入：新增 1、更新 1（匯入批次 #3）")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "匯入預覽" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => u === "/api/v1/imports/7/commit")).toBe(true);
  });

  it("test_f_imp_2_all_rows_invalid_cannot_commit：每一列都有錯時不能確認匯入", async () => {
    setup((url, init) => {
      if (url === "/api/v1/imports" && init?.method === "POST")
        return Response.json({ ...preview, rows_created: 0, rows_updated: 0, rows: [] }, { status: 201 });
      return base(url, init);
    });
    chooseFile();
    expect(await screen.findByRole("button", { name: "略過錯誤列，匯入 0 筆" })).toBeDisabled();
  });

  it("test_f_imp_2_cancel_preview：取消這次匯入後預覽消失並顯示提示", async () => {
    setup(base);
    chooseFile();
    fireEvent.click(await screen.findByRole("button", { name: "取消這次匯入" }));
    expect(await screen.findByText("已取消這次匯入")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "匯入預覽" })).not.toBeInTheDocument();
  });

  it("test_f_imp_1_upload_error_shows_chinese_message：檔案格式錯誤時顯示中文錯誤，不出現預覽", async () => {
    setup((url, init) => {
      if (url === "/api/v1/imports" && init?.method === "POST")
        return Response.json(
          { error: { code: "IMPORT_UNSUPPORTED_TYPE", message: "unsupported" } },
          { status: 400 },
        );
      return base(url, init);
    });
    chooseFile();
    expect(await screen.findByText("只支援 .csv 或 .xlsx 檔")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "匯入預覽" })).not.toBeInTheDocument();
  });

  it("test_m1_22_history_empty：沒有匯入紀錄時顯示空狀態", async () => {
    setup(base);
    fireEvent.click(screen.getByRole("button", { name: "匯入紀錄" }));
    expect(await screen.findByText("還沒有匯入紀錄")).toBeInTheDocument();
  });

  it("test_m1_22_history_error_then_retry：載入失敗顯示錯誤，按重試後出現列表", async () => {
    let fail = true;
    setup((url, init) => {
      if (url === "/api/v1/imports" && init?.method !== "POST") {
        if (fail) return Response.json({ error: { code: "INTERNAL_ERROR", message: "x" } }, { status: 500 });
        return Response.json([{ ...preview, status: "committed", run_id: 3 }]);
      }
      return base(url, init);
    });
    fireEvent.click(screen.getByRole("button", { name: "匯入紀錄" }));
    expect(await screen.findByText("無法載入資料")).toBeInTheDocument();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "重試" }));
    expect(await screen.findByText("已匯入")).toBeInTheDocument();
    expect(screen.getByText("#3")).toBeInTheDocument();
  });
});
