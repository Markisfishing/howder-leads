"""官網摘要的規則（M4-08b、M4-08d、SPEC 7.4、SPEC 9 個資）。

純 Python（CLAUDE.md 第 4 節第 2 點）：網頁抓回來的內容一律視為不可信資料——
只轉成純文字、不執行、不跟隨裡面的指示；進資料庫前再過濾一次人名、email、電話。
"""

import ipaddress
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from app.domain.company_rules import DomainError

MAX_TEXT_CHARS = 6000  # 給 LLM 摘要的網頁文字上限
SUMMARY_MIN = 20
SUMMARY_MAX = 600

# 只抓首頁與這類頁面（產品、關於我們）
_LINK_KEYWORDS = (
    "product",
    "products",
    "about",
    "company",
    "profile",
    "產品",
    "商品",
    "關於",
    "公司簡介",
    "簡介",
    "公司介紹",
)
_SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "head"})


# ---------- 網址與位址 ----------
def normalize_url(raw: str) -> str:
    """補上 https://、只接受 http／https、一定要有網域；否則 SITE_BAD_URL。"""
    url = raw.strip()
    if not url:
        raise DomainError("SITE_BAD_URL", "沒有官網網址", 422)
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or "." not in parsed.hostname:
        raise DomainError("SITE_BAD_URL", "官網網址格式不正確", 422)
    return url


def is_public_address(ip: str) -> bool:
    """只允許公開網路位址：擋掉本機、內網、連結本地、保留位址（避免用官網欄位掃公司內網）。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


# ---------- HTML → 純文字、連結 ----------
class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str, limit: int = MAX_TEXT_CHARS) -> str:
    """去掉 script／style 等標籤，只留可見文字，空白收斂成單一空格。"""
    parser = _TextParser()
    parser.feed(html)
    parser.close()
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()[:limit]


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []  # (href, 連結文字)
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip()))
            self._href = None


def candidate_links(html: str, base_url: str, limit: int = 2) -> list[str]:
    """首頁裡指向「產品／關於我們」的同網域連結（依出現順序、去重、最多 limit 個）。"""
    parser = _LinkParser()
    parser.feed(html)
    parser.close()
    host = urlparse(base_url).hostname
    seen: list[str] = []
    for href, label in parser.links:
        absolute = urljoin(base_url, href.split("#")[0])
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or parsed.hostname != host:
            continue
        haystack = f"{parsed.path} {label}".lower()
        if absolute.rstrip("/") == base_url.rstrip("/") or not any(k in haystack for k in _LINK_KEYWORDS):
            continue
        if absolute not in seen:
            seen.append(absolute)
        if len(seen) >= limit:
            break
    return seen


# ---------- 個資過濾 ----------
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+?886[-\s]?)?\(?0?\d{1,2}\)?[-\s]?\d{3,4}[-\s]?\d{3,4}(?:\s?#\s?\d{1,5})?"  # 市話、手機
)
_LINE_RE = re.compile(r"(?i)(?:line|賴|微信|wechat)\s*(?:id)?\s*[:：@]?\s*[A-Za-z0-9._\-@]{3,}")
_TITLE_NAME_RE = re.compile(
    r"(?:董事長|總經理|副總經理|經理|協理|負責人|聯絡人|窗口|業務|採購|先生|小姐)\s*[:：]?\s*[一-鿿]{2,3}"
)
_REDACTED = "（已移除）"


def redact_personal(text: str) -> str:
    """移除 email、電話、LINE／微信帳號、「職稱＋姓名」。只存公司層級的產品與產業描述（SPEC 9）。"""
    out = _EMAIL_RE.sub(_REDACTED, text)
    out = _LINE_RE.sub(_REDACTED, out)
    out = _PHONE_RE.sub(lambda m: _REDACTED if sum(c.isdigit() for c in m.group(0)) >= 7 else m.group(0), out)
    out = _TITLE_NAME_RE.sub(_REDACTED, out)
    return out
