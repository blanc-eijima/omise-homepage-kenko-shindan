"""サイトの電話番号と、Googleマップの登録を比べる（Places API の公式の検索）。"""
import json
import re
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from shindan.checks.domain import registrable_domain
from shindan.page import Fetched, read_head

TIMEOUT = 15
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.displayName,places.nationalPhoneNumber,places.websiteUri"
# 日本の電話番号。全角・ハイフン違いは NFKC と数字化で吸収する。
_PHONE = re.compile(r"(?<![\d-])(0\d{0,4}[-‐ー()（） ]{0,2}\d{1,4}[-‐ー()（） ]{0,2}\d{3,4})(?![\d-])")
_TEL_LINK = re.compile(r'href=["\']tel:([^"\']+)', re.IGNORECASE)
_TAG = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.IGNORECASE | re.DOTALL)
PHONE_DIGITS = (10, 11)


def normalize_phone(text: str) -> str:
    digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", text))
    return "0" + digits[2:] if digits.startswith("81") else digits


def find_phones(html: str) -> list[str]:
    """サイトの電話番号（FAX等も含みうる）。数字だけの形で返す。"""
    normalized = unicodedata.normalize("NFKC", _TAG.sub(" ", html))
    found = _TEL_LINK.findall(html) + _PHONE.findall(normalized)
    phones = {normalize_phone(p) for p in found}
    return sorted(p for p in phones if len(p) in PHONE_DIGITS and p.startswith("0"))


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


def judge_listing(site_phones: list[str], listing: dict | None) -> dict:
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
        },
    }


def check_map_listing(page: Fetched | None, host: str, key: str, name: str | None = None) -> dict:
    if page is None:
        return {"id": "map_listing", "status": "unknown", "facts": {"page_read": False}}
    query = name or read_head(page.body)[1] or host
    try:
        listing = pick_own_listing(_search(query, key), host)
    except (OSError, ValueError) as exc:
        reason = f"HTTP {exc.code}" if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
        return {"id": "map_listing", "status": "unknown", "facts": {"error": reason}}
    return judge_listing(find_phones(page.body), listing)
