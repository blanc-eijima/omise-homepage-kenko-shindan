"""ドメインの期限を調べる。.jp は JPRS の WHOIS、それ以外は RDAP。"""
import json
import re
import socket
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
TIMEOUT = 10
WARN_DAYS = 30
CRITICAL_DAYS = 7
JP_SECOND_LEVEL = {"ac", "ad", "co", "ed", "go", "gr", "lg", "ne", "or"}
FOREIGN_SECOND_LEVEL = {"co.uk", "org.uk", "com.au", "co.nz", "co.kr", "com.cn"}

_STATE = re.compile(r"\[State\]\s+Connected \((\d{4}/\d{2}/\d{2})\)")
_EXPIRES = re.compile(r"\[Expires on\]\s+(\d{4}/\d{2}/\d{2})")


def registrable_domain(host: str) -> str:
    """www.example.co.jp -> example.co.jp"""
    labels = host.split(".")
    # ponytail: 地域型 .jp と、下の一覧に無い海外の属性型は未対応（期限は unknown になる）。
    # 必要になったら Public Suffix List へ切り替える。
    second_level = labels[-1] == "jp" and labels[-2:-1] and labels[-2] in JP_SECOND_LEVEL
    keep = 3 if second_level or ".".join(labels[-2:]) in FOREIGN_SECOND_LEVEL else 2
    return ".".join(labels[-keep:])


def parse_jprs_whois(text: str) -> dict:
    """JPRS の英語表示を読む。属性型は [State]、汎用は [Expires on] に期限がある。"""
    if "No match!!" in text:
        return {"found": False, "expires_at": None}
    match = _STATE.search(text) or _EXPIRES.search(text)
    expires = date.fromisoformat(match.group(1).replace("/", "-")) if match else None
    return {"found": True, "expires_at": expires}


def parse_rdap(payload: dict) -> dict:
    for event in payload.get("events", []):
        if event.get("eventAction") == "expiration":
            moment = datetime.fromisoformat(event["eventDate"].replace("Z", "+00:00"))
            return {"found": True, "expires_at": moment.astimezone(JST).date()}
    return {"found": True, "expires_at": None}


def _query_jprs(domain: str) -> str:
    with socket.create_connection(("whois.jprs.jp", 43), timeout=TIMEOUT) as sock:
        sock.sendall(f"{domain}/e\r\n".encode("ascii"))
        chunks = []
        while chunk := sock.recv(4096):
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", "replace")


def _query_rdap(domain: str) -> dict:
    request = urllib.request.Request(
        f"https://rdap.org/domain/{domain}",
        headers={"User-Agent": "omise-kenko-shindan/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return parse_rdap(json.load(response))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"found": False, "expires_at": None}
        raise


def judge_domain(result: dict, today: date) -> tuple[str, int | None]:
    expires = result["expires_at"]
    if expires is None:
        return "unknown", None
    days_left = (expires - today).days
    if days_left <= CRITICAL_DAYS:
        return "critical", days_left
    return ("warn" if days_left <= WARN_DAYS else "ok"), days_left


def check_domain(host: str, today: date | None = None) -> dict:
    today = today or datetime.now(JST).date()
    domain = registrable_domain(host)
    source = "jprs_whois" if domain.endswith(".jp") else "rdap"
    try:
        if source == "jprs_whois":
            result = parse_jprs_whois(_query_jprs(domain))
        else:
            result = _query_rdap(domain)
    except (OSError, ValueError) as exc:
        return {
            "id": "domain_expiry",
            "status": "unknown",
            "facts": {"domain": domain, "source": source, "error": str(exc)},
        }
    status, days_left = judge_domain(result, today)
    expires = result["expires_at"]
    return {
        "id": "domain_expiry",
        "status": status,
        "facts": {
            "domain": domain,
            "source": source,
            "found": result["found"],
            "expires_at": expires.isoformat() if expires else None,
            "days_left": days_left,
        },
    }
