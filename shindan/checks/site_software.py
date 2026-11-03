"""WordPressとPHPの古さ。外に出ている版番号を、公開されているサポート期限と照らす。"""
import json
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone

from shindan.page import Fetched, read_head

JST = timezone(timedelta(hours=9))
TIMEOUT = 10
EOL_API = "https://endoflife.date/api/{}.json"
_WP_GENERATOR = re.compile(r"WordPress\s+(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)
_PHP_HEADER = re.compile(r"PHP/(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)


def _load_cycles(product: str) -> list[dict]:
    request = urllib.request.Request(
        EOL_API.format(product), headers={"User-Agent": "omise-kenko-shindan/0.1"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def read_versions(page: Fetched) -> dict:
    metas, _ = read_head(page.body)
    wp = next(filter(None, map(_WP_GENERATOR.search, metas.get("generator", []))), None)
    php = _PHP_HEADER.search(page.headers.get("x-powered-by", ""))
    return {
        "wordpress_in_use": bool(wp) or "/wp-content/" in page.body,
        "wordpress_version": wp.group(1) if wp else None,
        "php_version": php.group(1) if php else None,
    }


def _cycle_of(version: str, cycles: list[dict]) -> dict | None:
    line = ".".join(version.split(".")[:2])
    return next((c for c in cycles if c["cycle"] == line), None)


def _ended(cycle: dict, today: date) -> tuple[bool, str | None]:
    """サポート終了済みか、と終了日。eol は日付か真偽値で返ってくる。"""
    eol = cycle.get("eol")
    if isinstance(eol, str):
        return date.fromisoformat(eol) <= today, eol
    return bool(eol), None


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def judge_wordpress(version: str, cycles: list[dict], today: date) -> dict | None:
    cycle = _cycle_of(version, cycles)
    if cycle is None:
        return None
    ended, ended_on = _ended(cycle, today)
    latest = cycle.get("latest")
    return {
        "wordpress_support_ended": ended,
        "wordpress_support_ended_on": ended_on,
        "wordpress_latest_in_line": latest,
        "wordpress_behind_in_line": bool(latest) and _version_key(version) < _version_key(latest),
    }


def judge_php(version: str, cycles: list[dict], today: date) -> dict | None:
    cycle = _cycle_of(version, cycles)
    if cycle is None:
        return None
    ended, ended_on = _ended(cycle, today)
    return {"php_support_ended": ended, "php_support_ended_on": ended_on}


def _status(facts: dict) -> str:
    outdated = (
        facts.get("wordpress_support_ended")
        or facts.get("wordpress_behind_in_line")
        or facts.get("php_support_ended")
    )
    return "warn" if outdated else "ok"


def check_site_software(page: Fetched | None, today: date | None = None) -> dict:
    if page is None:
        return {"id": "site_software", "status": "unknown", "facts": {"page_read": False}}
    today = today or datetime.now(JST).date()
    facts = read_versions(page)
    try:
        for name, judge, product in (
            ("wordpress_version", judge_wordpress, "wordpress"),
            ("php_version", judge_php, "php"),
        ):
            if facts[name]:
                judged = judge(facts[name], _load_cycles(product), today)
                if judged is None:
                    return {"id": "site_software", "status": "unknown", "facts": facts}
                facts.update(judged)
    except (OSError, ValueError):
        # 版番号は見えたが期限一覧を読めなかった＝古いと断定しない。
        return {"id": "site_software", "status": "unknown", "facts": facts}
    return {"id": "site_software", "status": _status(facts), "facts": facts}
