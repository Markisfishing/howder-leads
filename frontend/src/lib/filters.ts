// 推薦清單的篩選條件 ⇄ 網址參數（F-REC-2：篩選條件反映在網址上，方便分享）

export type SortKey = "recommended" | "name" | "updated";

export interface ListFilters {
  stars: number[];
  status: string[];
  industryId: number | null;
  owner: string | null; // "me" | "none" | 使用者 id
  hasWebsite: boolean | null;
  competitor: boolean | null;
  q: string;
  sort: SortKey;
  page: number;
  pageSize: number;
}

export const DEFAULT_FILTERS: ListFilters = {
  stars: [],
  status: [],
  industryId: null,
  owner: null,
  hasWebsite: null,
  competitor: null,
  q: "",
  sort: "recommended",
  page: 1,
  pageSize: 50,
};

const SORTS: SortKey[] = ["recommended", "name", "updated"];

function toBool(v: string | null): boolean | null {
  if (v === "true") return true;
  if (v === "false") return false;
  return null;
}

function toPositiveInt(v: string | null, fallback: number): number {
  const n = Number(v);
  return Number.isInteger(n) && n > 0 ? n : fallback;
}

export function parseFilters(params: URLSearchParams): ListFilters {
  const sort = params.get("sort") as SortKey | null;
  const industry = Number(params.get("industry"));
  return {
    stars: params
      .getAll("stars")
      .map(Number)
      .filter((n) => Number.isInteger(n) && n >= 0 && n <= 5),
    status: params.getAll("status"),
    industryId: Number.isInteger(industry) && industry > 0 ? industry : null,
    owner: params.get("owner"),
    hasWebsite: toBool(params.get("website")),
    competitor: toBool(params.get("competitor")),
    q: params.get("q") ?? "",
    sort: sort && SORTS.includes(sort) ? sort : "recommended",
    page: toPositiveInt(params.get("page"), 1),
    pageSize: Math.min(toPositiveInt(params.get("size"), DEFAULT_FILTERS.pageSize), 200),
  };
}

export function toSearchParams(f: ListFilters): URLSearchParams {
  const p = new URLSearchParams();
  f.stars.forEach((s) => p.append("stars", String(s)));
  f.status.forEach((s) => p.append("status", s));
  if (f.industryId !== null) p.set("industry", String(f.industryId));
  if (f.owner) p.set("owner", f.owner);
  if (f.hasWebsite !== null) p.set("website", String(f.hasWebsite));
  if (f.competitor !== null) p.set("competitor", String(f.competitor));
  if (f.q) p.set("q", f.q);
  if (f.sort !== "recommended") p.set("sort", f.sort);
  if (f.page !== 1) p.set("page", String(f.page));
  if (f.pageSize !== DEFAULT_FILTERS.pageSize) p.set("size", String(f.pageSize));
  return p;
}

/** 改篩選條件時回到第 1 頁 */
export function updateFilters(f: ListFilters, patch: Partial<ListFilters>): ListFilters {
  const pageOnly = Object.keys(patch).every((k) => k === "page");
  return { ...f, ...patch, page: pageOnly ? (patch.page ?? f.page) : 1 };
}
