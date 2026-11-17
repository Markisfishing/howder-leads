import { ApiError, api, buildUrl, configureAuth } from "./client";

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    configureAuth(async () => ({}), () => {});
  });

  it("test_build_url_skips_empty_and_repeats_arrays：空值不帶、陣列重複帶", () => {
    expect(buildUrl("/companies", { stars: [5, 4], q: "", owner: null, page: 2, competitor: false })).toBe(
      "/api/v1/companies?stars=5&stars=4&page=2&competitor=false",
    );
  });

  it("test_error_code_maps_to_chinese：錯誤碼對應到中文訊息", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({ error: { code: "COMPANY_EXISTS", message: "exists" } }, { status: 409 }),
      ),
    );
    const err = await api("/companies").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("COMPANY_EXISTS");
    expect((err as ApiError).message).toBe("這個統編已經在名單裡了");
  });

  it("test_unauthorized_triggers_sign_out：401 時通知登出", async () => {
    const onUnauthorized = vi.fn();
    configureAuth(async () => ({ "X-Dev-User": "sales1@example.com" }), onUnauthorized);
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
      Response.json({ error: { code: "UNAUTHORIZED", message: "" } }, { status: 401 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await expect(api("/me")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[1]?.headers).toMatchObject({ "X-Dev-User": "sales1@example.com" });
  });

  it("test_m2_01b_no_content_response：刪除成功（204）不解析 JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
    await expect(api("/contacts/1", { method: "DELETE", json: { reason: "客戶要求" } })).resolves.toBeUndefined();
  });

  it("test_network_error：連不到伺服器時給中文訊息", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("failed"))));
    await expect(api("/me")).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
});
