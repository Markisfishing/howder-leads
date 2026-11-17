// 推薦清單欄位自選（M3-13b、F-REC-8）：最多 10 欄，記在自己的瀏覽器。
// key 和後端 GET /companies/export 的 columns 是同一組，匯出時照畫面上選的欄位。

export const COLUMN_LABELS = {
  name: "公司名稱",
  fit_stars: "推薦度（星等）",
  tax_id: "統編",
  industry: "產業",
  product_type: "產品類型",
  tags: "命中標籤",
  reason: "推薦理由",
  likelihood: "使用可能性",
  status: "狀態",
  owner_name: "負責業務",
  website_url: "官網",
  url_status: "網址狀態",
  country: "國別",
  source: "資料來源",
  customer_type: "客戶屬性",
  score: "分數",
  updated_at: "最後更新",
} as const;

export type ColumnKey = keyof typeof COLUMN_LABELS;
export const ALL_COLUMNS = Object.keys(COLUMN_LABELS) as ColumnKey[];
export const MAX_COLUMNS = 10;
/** 公司名稱一定要顯示（點它開詳情） */
export const REQUIRED_COLUMNS: ColumnKey[] = ["name"];
export const DEFAULT_COLUMNS: ColumnKey[] = [
  "name",
  "fit_stars",
  "industry",
  "website_url",
  "reason",
  "likelihood",
  "status",
  "owner_name",
];

const STORAGE_KEY = "howder.recommendations.columns.v1";

/** 清掉不認得的 key、重複、超過上限的欄位；一定含公司名稱；順序照 ALL_COLUMNS */
export function sanitizeColumns(raw: unknown): ColumnKey[] {
  if (!Array.isArray(raw)) return DEFAULT_COLUMNS;
  const chosen = new Set<ColumnKey>([...REQUIRED_COLUMNS]);
  for (const k of raw) {
    if (typeof k === "string" && (ALL_COLUMNS as string[]).includes(k)) chosen.add(k as ColumnKey);
  }
  return ALL_COLUMNS.filter((k) => chosen.has(k)).slice(0, MAX_COLUMNS);
}

export function loadColumns(): ColumnKey[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? sanitizeColumns(JSON.parse(raw)) : DEFAULT_COLUMNS;
  } catch {
    return DEFAULT_COLUMNS; // 私密視窗或封鎖儲存空間時用預設
  }
}

export function saveColumns(cols: ColumnKey[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(cols));
  } catch {
    // 存不了就只在這次開啟有效
  }
}

/** 勾選或取消一欄；已達上限時不能再加，必要欄位不能取消 */
export function toggleColumn(cols: ColumnKey[], key: ColumnKey): ColumnKey[] {
  if (REQUIRED_COLUMNS.includes(key)) return cols;
  if (cols.includes(key)) return cols.filter((k) => k !== key);
  if (cols.length >= MAX_COLUMNS) return cols;
  return sanitizeColumns([...cols, key]);
}
