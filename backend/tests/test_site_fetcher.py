"""官網抓取與個資過濾（M4-08b、M4-08d、SPEC 7.4）。一律用假的 HTTP 回應與假的 DNS，不連真實網站。"""

import httpx
import pytest

from app.domain import site_rules
from app.domain.company_rules import DomainError
from app.services.site_fetcher import SiteFetcher, SiteFetchError

HOME = """<html><head><title>x</title><script>var secret = 1;</script></head><body>
<h1>範例工業股份有限公司</h1><p>我們製造控制盤與配電設備。</p>
<a href="/products">產品介紹</a> <a href="/about.html">關於我們</a> <a href="/news">最新消息</a>
<a href="https://other.example.net/products">外部連結</a></body></html>"""
PRODUCTS = "<html><body><p>主要產品：端子台用控制箱、PLC 盤體。</p></body></html>"
ABOUT = "<html><body><p>成立於 2000 年，專注工業自動化。</p></body></html>"
PUBLIC_IP = "93.184.216.34"


def _fetcher(routes: dict[str, httpx.Response | Exception], **kw: object) -> tuple[SiteFetcher, list[str]]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        out = routes.get(str(request.url), httpx.Response(404))
        if isinstance(out, Exception):
            raise out
        return out

    sleeps: list[float] = []
    params: dict[str, object] = {
        "transport": httpx.MockTransport(handler),
        "resolver": lambda host: [PUBLIC_IP],
        "sleep": sleeps.append,
        "clock": lambda: 0.0,
    }
    params.update(kw)
    fetcher = SiteFetcher(**params)  # type: ignore[arg-type]
    fetcher.sleeps = sleeps  # type: ignore[attr-defined]
    return fetcher, seen


def _html(body: str) -> httpx.Response:
    return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})


# ---------- domain 規則 ----------
def test_m4_08b_html_to_text_drops_scripts_and_collapses_space() -> None:
    text = site_rules.html_to_text(HOME)
    assert "範例工業股份有限公司" in text and "控制盤與配電設備" in text
    assert "secret" not in text and "var" not in text


def test_m4_08b_candidate_links_same_domain_product_and_about_only() -> None:
    links = site_rules.candidate_links(HOME, "https://www.example.com/")
    assert links == ["https://www.example.com/products", "https://www.example.com/about.html"]
    assert site_rules.candidate_links(HOME, "https://www.example.com/", limit=1) == ["https://www.example.com/products"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("example.com", "https://example.com"), (" http://a.example.com/x ", "http://a.example.com/x")],
)
def test_m4_08b_normalize_url(raw: str, expected: str) -> None:
    assert site_rules.normalize_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "ftp://example.com", "javascript:alert(1)", "http://localhost", "https://"])
def test_m4_08b_normalize_url_rejects(raw: str) -> None:
    with pytest.raises(DomainError) as e:
        site_rules.normalize_url(raw)
    assert e.value.code == "SITE_BAD_URL"


@pytest.mark.parametrize(
    ("ip", "ok"),
    [
        ("93.184.216.34", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("192.168.1.10", False),
        ("172.16.0.1", False),
        ("169.254.169.254", False),
        ("::1", False),
        ("0.0.0.0", False),
        ("not-an-ip", False),
    ],
)
def test_m4_08b_only_public_addresses_allowed(ip: str, ok: bool) -> None:
    assert site_rules.is_public_address(ip) is ok


def test_m4_08d_redact_personal_removes_email_phone_line_and_titled_names() -> None:
    raw = (
        "我們是範例公司，產品為控制盤。聯絡人：王小明，電話 (02) 2345-6789，手機 0912-345-678，"
        "email contact@example.com，LINE ID: example_id，成立於 2000 年。"
    )
    out = site_rules.redact_personal(raw)
    for leaked in ("王小明", "2345-6789", "0912-345-678", "contact@example.com", "example_id"):
        assert leaked not in out
    assert "控制盤" in out and "成立於 2000 年" in out  # 產品描述與年份不受影響


def test_m4_08d_redact_keeps_short_numbers_and_product_text() -> None:
    assert (
        site_rules.redact_personal("提供 M4 規格 5.08 mm 端子台，電流 32A") == "提供 M4 規格 5.08 mm 端子台，電流 32A"
    )


# ---------- 抓取 ----------
def test_m4_08b_fetch_home_product_and_about_pages() -> None:
    fetcher, seen = _fetcher(
        {
            "https://www.example.com/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /admin"),
            "https://www.example.com": _html(HOME),
            "https://www.example.com/products": _html(PRODUCTS),
            "https://www.example.com/about.html": _html(ABOUT),
        }
    )
    site = fetcher.fetch("www.example.com")
    assert site.pages == 3 and site.source_url == "https://www.example.com"
    assert "控制盤" in site.text and "PLC 盤體" in site.text and "專注工業自動化" in site.text
    assert not any("other.example.net" in u or "/news" in u for u in seen)  # 不抓外部網域與不相關頁面


def test_m4_08b_robots_disallow_blocks_everything() -> None:
    fetcher, seen = _fetcher(
        {
            "https://www.example.com/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /"),
            "https://www.example.com": _html(HOME),
        }
    )
    with pytest.raises(SiteFetchError) as e:
        fetcher.fetch("https://www.example.com")
    assert e.value.code == "SITE_ROBOTS_DISALLOWED"
    assert seen == ["https://www.example.com/robots.txt"]  # 不會去抓被禁止的首頁


def test_m4_08b_robots_disallows_only_product_page() -> None:
    fetcher, seen = _fetcher(
        {
            "https://www.example.com/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /products"),
            "https://www.example.com": _html(HOME),
            "https://www.example.com/products": _html(PRODUCTS),
            "https://www.example.com/about.html": _html(ABOUT),
        }
    )
    site = fetcher.fetch("https://www.example.com")
    assert "PLC 盤體" not in site.text and "專注工業自動化" in site.text
    assert "https://www.example.com/products" not in seen


def test_m4_08b_missing_robots_means_allowed_and_secondary_failure_is_ignored() -> None:
    fetcher, _ = _fetcher({"https://www.example.com": _html(HOME)})  # robots、產品頁都是 404
    site = fetcher.fetch("https://www.example.com")
    assert site.pages == 1 and "控制盤" in site.text


@pytest.mark.parametrize(
    ("home", "code"),
    [
        (httpx.ConnectError("refused"), "SITE_UNREACHABLE"),
        (httpx.ReadTimeout("slow"), "SITE_TIMEOUT"),
        (httpx.Response(500), "SITE_HTTP_ERROR"),
        (httpx.Response(200, text="{}", headers={"content-type": "application/json"}), "SITE_NOT_HTML"),
        (_html("<html><body><script>x()</script></body></html>"), "SITE_EMPTY"),
    ],
)
def test_m4_08b_failures_map_to_error_codes(home: httpx.Response | Exception, code: str) -> None:
    fetcher, _ = _fetcher({"https://www.example.com": home})
    with pytest.raises(SiteFetchError) as e:
        fetcher.fetch("https://www.example.com")
    assert e.value.code == code


def test_m4_08b_private_addresses_are_blocked_without_any_request() -> None:
    fetcher, seen = _fetcher({}, resolver=lambda host: ["192.168.1.10"])
    with pytest.raises(SiteFetchError) as e:
        fetcher.fetch("https://intranet.example.com")
    assert e.value.code == "SITE_BLOCKED_ADDRESS"
    assert seen == []


def test_m4_08b_redirect_to_private_address_is_blocked() -> None:
    def resolver(host: str) -> list[str]:
        return ["10.0.0.1"] if host == "internal.example.com" else [PUBLIC_IP]

    fetcher, seen = _fetcher(
        {"https://www.example.com": httpx.Response(302, headers={"location": "https://internal.example.com/"})},
        resolver=resolver,
    )
    with pytest.raises(SiteFetchError) as e:
        fetcher.fetch("https://www.example.com")
    assert e.value.code == "SITE_BLOCKED_ADDRESS"
    assert not any("internal.example.com" in u for u in seen)


def test_m4_08b_follows_a_public_redirect_and_reports_final_url() -> None:
    fetcher, _ = _fetcher(
        {
            "https://example.com": httpx.Response(301, headers={"location": "https://www.example.com/"}),
            "https://www.example.com/": _html(HOME),
        }
    )
    assert fetcher.fetch("https://example.com").source_url == "https://www.example.com/"


def test_m4_08b_redirect_loop_gives_up() -> None:
    fetcher, _ = _fetcher({"https://a.example.com": httpx.Response(302, headers={"location": "https://a.example.com"})})
    with pytest.raises(SiteFetchError) as e:
        fetcher.fetch("https://a.example.com")
    assert e.value.code == "SITE_TOO_MANY_REDIRECTS"


def test_m4_08b_oversized_page_is_truncated_not_failed() -> None:
    big = "<html><body><p>" + ("端子台。" * 200_000) + "</p></body></html>"
    fetcher, _ = _fetcher({"https://www.example.com": _html(big)}, max_bytes=2000)
    site = fetcher.fetch("https://www.example.com")
    assert 0 < len(site.text) <= site_rules.MAX_TEXT_CHARS


def test_m4_08b_same_host_requests_are_rate_limited() -> None:
    now = [0.0]
    fetcher, _ = _fetcher(
        {
            "https://www.example.com": _html(HOME),
            "https://www.example.com/products": _html(PRODUCTS),
            "https://www.example.com/about.html": _html(ABOUT),
        },
        per_host_delay=1.0,
        clock=lambda: now[0],
    )
    fetcher.fetch("https://www.example.com")
    assert len(fetcher.sleeps) >= 3  # type: ignore[attr-defined]  # robots、首頁、產品頁、關於頁之間都要間隔
    assert all(s > 0 for s in fetcher.sleeps)  # type: ignore[attr-defined]


def test_m4_08b_bad_url_is_reported_as_fetch_error() -> None:
    fetcher, _ = _fetcher({})
    with pytest.raises(SiteFetchError) as e:
        fetcher.fetch("ftp://example.com")
    assert e.value.code == "SITE_BAD_URL"
