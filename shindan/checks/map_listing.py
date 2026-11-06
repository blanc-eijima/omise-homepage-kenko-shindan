"""サイトの電話番号と、Googleマップの登録を比べる（Places API の公式の検索）。"""
import json
import re
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit

from shindan.checks.domain import registrable_domain
from shindan.page import Fetched, fetch, read_head

TIMEOUT = 15
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.displayName,places.nationalPhoneNumber,places.websiteUri"
# 日本の電話番号。全角・ハイフン違いは NFKC と数字化で吸収する。
_PHONE = re.compile(r"(?<![\d-])(0\d{0,4}[-‐ー()（） ]{0,2}\d{1,4}[-‐ー()（） ]{0,2}\d{3,4})(?![\d-])")
_TEL_LINK = re.compile(r'href=["\']tel:([^"\']+)', re.IGNORECASE)
_TAG = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.IGNORECASE | re.DOTALL)
PHONE_DIGITS = (10, 11)
# トップに地図の番号が無いときだけ、番号が載っていそうなページを読む。読む数は上限を決める。
_LINK = re.compile(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_INFO_PAGE = re.compile(
    r"会社概要|会社案内|会社情報|企業情報|店舗情報|店舗案内|お店の情報|アクセス|所在地|特定商取引"
    r"|company|about|access|profile|shop-?info|tokusho",
    re.IGNORECASE,
)
MAX_INFO_PAGES = 3
# 架空のお店はGoogleマップに載らない。デモの照合だけ、この登録と比べて画面に架空と明記する。
DEMO_LISTINGS = {
    "hidamari-shotengai-demo.netlify.app": {"nationalPhoneNumber": "03-0000-5678"},
    "hidamari-shotengai-demo-fixed.netlify.app": {"nationalPhoneNumber": "03-0000-5678"},
}


def normalize_phone(text: str) -> str:
    digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", text))
    return "0" + digits[2:] if digits.startswith("81") else digits


def find_phones(html: str) -> list[str]:
    """サイトの電話番号（FAX等も含みうる）。数字だけの形で返す。"""
    normalized = unicodedata.normalize("NFKC", _TAG.sub(" ", html))
    found = _TEL_LINK.findall(html) + _PHONE.findall(normalized)
    phones = {normalize_phone(p) for p in found}
    return sorted(p for p in phones if len(p) in PHONE_DIGITS and p.startswith("0"))


def info_page_urls(page: Fetched) -> list[str]:
    """トップから同じサイトの会社概要・アクセス等へのリンクを、出てきた順に返す。"""
    host = urlsplit(page.url).hostname or ""
    urls: list[str] = []
    for href, text in _LINK.findall(page.body):
        url = urljoin(page.url, href.strip())
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or parts.hostname != host:
            continue
        if url.rstrip("/") == page.url.rstrip("/") or url in urls:
            continue
        if _INFO_PAGE.search(_TAG.sub(" ", text)) or _INFO_PAGE.search(parts.path):
            urls.append(url)
    return urls[:MAX_INFO_PAGES]


def site_phones_and_pages(page: Fetched, listing: dict | None) -> tuple[list[str], list[str]]:
    """トップの番号に地図の番号が無ければ、会社概要などのページの番号も足す。"""
    phones = set(find_phones(page.body))
    raw = (listing or {}).get("nationalPhoneNumber", "")
    if not raw or normalize_phone(raw) in phones:
        return sorted(phones), []
    pages = []
    for url in info_page_urls(page):
        found = fetch(url)
        if found is None or found.status != 200:
            continue
        pages.append(urlsplit(found.url).path or "/")
        phones |= set(find_phones(found.body))
        if normalize_phone(raw) in phones:
            break
    return sorted(phones), pages


def _search(query: str, key: str) -> list[dict]:
    body = {"textQuery": query, "languageCode": "ja", "regionCode": "JP", "maxResultCount": 5}
    request = urllib.request.Request(
        SEARCH_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response).get("places", [])


def pick_own_listing(places: list[dict], host: str) -> dict | None:
    """同じ名前の別のお店と比べないよう、登録のサイトが同じドメインのものだけを採る。"""
    own = registrable_domain(host)
    for place in places:
        website = urlsplit(place.get("websiteUri", "")).hostname or ""
        if website and registrable_domain(website) == own:
            return place
    return None


def judge_listing(site_phones: list[str], listing: dict | None, pages: list[str] | None = None) -> dict:
    if listing is None:
        # 見つからない＝未登録とは限らない。問題としては扱わない。
        facts = {"listing_found": False, "site_phones": site_phones}
        return {"id": "map_listing", "status": "ok", "facts": facts}
    raw_phone = listing.get("nationalPhoneNumber", "")
    listing_phone = normalize_phone(raw_phone) if raw_phone else None
    # サイトに電話番号が見当たらない・地図に電話が無いときは、食い違いと言わない。
    mismatch = bool(site_phones and listing_phone and listing_phone not in site_phones)
    return {
        "id": "map_listing",
        "status": "warn" if mismatch else "ok",
        "facts": {
            "listing_found": True,
            "site_phones": site_phones,
            "listing_phone": listing_phone,
            "phones_differ": mismatch,
            # トップ以外に読んだページ。空ならトップだけで比べた。
            "other_pages_read": pages or [],
        },
    }


def check_map_listing(page: Fetched | None, host: str, key: str, name: str | None = None) -> dict:
    if page is None:
        return {"id": "map_listing", "status": "unknown", "facts": {"page_read": False}}
    if host in DEMO_LISTINGS:
        result = judge_listing(find_phones(page.body), DEMO_LISTINGS[host])
        return {**result, "facts": {**result["facts"], "demo_data": True}}
    query = name or read_head(page.body)[1] or host
    try:
        listing = pick_own_listing(_search(query, key), host)
    except (OSError, ValueError) as exc:
        reason = f"HTTP {exc.code}" if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
        return {"id": "map_listing", "status": "unknown", "facts": {"error": reason}}
    phones, pages = site_phones_and_pages(page, listing)
    return judge_listing(phones, listing, pages)
