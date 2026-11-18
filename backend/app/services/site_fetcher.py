"""抓公司官網文字（M4-08b、SPEC 7.4）。

只抓首頁和產品／關於我們頁（最多 3 頁）；遵守 robots.txt，有逾時、大小上限，同網域請求間隔限速。
只允許公開網路位址，且每次轉址都重新檢查（避免用官網欄位掃公司內網）。
網頁內容一律當不可信資料：轉成純文字後才交給後面的流程，不執行、不跟隨裡面的指示。
log 只記網域與錯誤代碼，不記網頁內容。測試用 httpx.MockTransport 與假的 resolver，不連真實網站。
"""

import logging
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.domain import site_rules
from app.domain.company_rules import DomainError

log = logging.getLogger("howder.site")

USER_AGENT = "HowderSalesBot/1.0 (internal sales tool)"
MAX_REDIRECTS = 3


class SiteFetchError(Exception):
    """抓官網失敗。code 寫進 company_site_summary.error_code，不放網頁內容。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FetchedSite:
    source_url: str  # 首頁網址（轉址後）
    text: str  # 各頁純文字合併（已限長）
    pages: int


def default_resolver(host: str) -> list[str]:
    try:
        return sorted({str(info[4][0]) for info in socket.getaddrinfo(host, None)})
    except OSError as e:
        raise SiteFetchError("SITE_UNREACHABLE") from e


class SiteFetcher:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
        max_bytes: int = 500_000,
        max_pages: int = 3,
        per_host_delay: float = 1.0,
        resolver: Callable[[str], list[str]] = default_resolver,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = httpx.Client(
            transport=transport, timeout=timeout, follow_redirects=False, headers={"User-Agent": USER_AGENT}
        )
        self._max_bytes = max_bytes
        self._max_pages = max_pages
        self._delay = per_host_delay
        self._resolve = resolver
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}

    # ---------- 低階：單一請求 ----------
    def _ensure_public(self, host: str) -> None:
        addresses = self._resolve(host)
        if not addresses or not all(site_rules.is_public_address(a) for a in addresses):
            raise SiteFetchError("SITE_BLOCKED_ADDRESS")

    def _throttle(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            wait = self._delay - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()

    def _get(self, url: str) -> tuple[httpx.Response, str]:
        """GET 一個網址（手動處理轉址並逐次檢查位址）。回傳 (回應, 最後的網址)；內容最多讀 max_bytes。"""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            host = urlparse(current).hostname or ""
            self._ensure_public(host)
            self._throttle(host)
            try:
                with self._client.stream("GET", current) as res:
                    if res.is_redirect and res.headers.get("location"):
                        current = urljoin(current, res.headers["location"])
                        site_rules.normalize_url(current)
                        continue
                    body = b""
                    for chunk in res.iter_bytes():
                        body += chunk
                        if len(body) >= self._max_bytes:
                            body = body[: self._max_bytes]  # 太大的頁面只取前面一段
                            break
                    final = httpx.Response(res.status_code, headers=res.headers, content=body, request=res.request)
                    return final, current
            except httpx.TimeoutException as e:
                raise SiteFetchError("SITE_TIMEOUT") from e
            except httpx.HTTPError as e:
                raise SiteFetchError("SITE_UNREACHABLE") from e
            except DomainError as e:  # 轉址到不合法的網址
                raise SiteFetchError("SITE_BAD_URL") from e
        raise SiteFetchError("SITE_TOO_MANY_REDIRECTS")

    # ---------- robots.txt ----------
    def _robots(self, origin: str) -> RobotFileParser:
        parser = RobotFileParser()
        try:
            res, _ = self._get(origin + "/robots.txt")
        except SiteFetchError:
            parser.parse([])  # 讀不到 robots.txt 視為沒有限制
            return parser
        if res.status_code == 200:
            parser.parse(res.text.splitlines())
        elif res.status_code in (401, 403):
            parser.parse(["User-agent: *", "Disallow: /"])  # 規範：401／403 視為全部不可抓
        else:
            parser.parse([])
        return parser

    @staticmethod
    def _html(res: httpx.Response) -> str:
        if res.status_code >= 400:
            raise SiteFetchError("SITE_HTTP_ERROR")
        if "html" not in res.headers.get("content-type", "text/html").lower():
            raise SiteFetchError("SITE_NOT_HTML")
        return res.text

    # ---------- 對外 ----------
    def fetch(self, raw_url: str) -> FetchedSite:
        try:
            url = site_rules.normalize_url(raw_url)
        except DomainError as e:
            raise SiteFetchError(e.code) from e
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robots = self._robots(origin)
        if not robots.can_fetch(USER_AGENT, url):
            raise SiteFetchError("SITE_ROBOTS_DISALLOWED")

        res, final_url = self._get(url)
        home_html = self._html(res)
        texts = [site_rules.html_to_text(home_html)]
        for link in site_rules.candidate_links(home_html, final_url, limit=self._max_pages - 1):
            if not robots.can_fetch(USER_AGENT, link):
                continue
            try:
                page, _ = self._get(link)
                texts.append(site_rules.html_to_text(self._html(page)))
            except SiteFetchError:
                continue  # 次要頁面失敗不影響首頁的內容
        merged = " ".join(t for t in texts if t)[: site_rules.MAX_TEXT_CHARS]
        if not merged:
            raise SiteFetchError("SITE_EMPTY")
        log.info("官網抓取完成 host=%s pages=%d", urlparse(final_url).hostname, len(texts))
        return FetchedSite(source_url=final_url, text=merged, pages=len(texts))
