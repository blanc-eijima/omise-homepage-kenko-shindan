"""トップページから読める項目。ページの文字列そのものはClaudeへ渡さず、判定結果だけ渡す。"""
import re
from urllib.robotparser import RobotFileParser

from shindan.page import Fetched, fetch, read_head, robots_url

# PHPのエラーが画面にそのまま出ている形。サーバーのPHP更新の直後によく見る。
_PHP_ERROR = re.compile(
    r"(Fatal error|Parse error|Warning|Notice|Deprecated)(</b>)?\s*:.{0,300}?\son line\s+(<b>)?\d+",
    re.IGNORECASE | re.DOTALL,
)


def _unknown(check_id: str) -> dict:
    return {"id": check_id, "status": "unknown", "facts": {"page_read": False}}


def check_page_response(page: Fetched | None) -> dict:
    if page is None:
        return _unknown("page_response")
    error_visible = bool(_PHP_ERROR.search(page.body))
    return {
        "id": "page_response",
        "status": "critical" if page.status >= 400 or error_visible else "ok",
        "facts": {"http_status": page.status, "error_text_visible": error_visible},
    }


def _has_noindex(page: Fetched, metas: dict[str, list[str]]) -> bool:
    values = metas.get("robots", []) + metas.get("googlebot", [])
    values.append(page.headers.get("x-robots-tag", ""))
    return any("noindex" in value.lower() or "none" in value.lower().split() for value in values)


def blocks_top(robots_text: str, page_url: str) -> bool:
    parser = RobotFileParser()
    parser.parse(robots_text.splitlines())
    return not parser.can_fetch("Googlebot", page_url)


def _robots_blocks(page: Fetched) -> bool | None:
    """読めなければ None。robots.txt が無いのは正常（止められていない）。"""
    robots = fetch(robots_url(page.url))
    if robots is None:
        return None
    if robots.status != 200:
        return False
    return blocks_top(robots.body, page.url)


def check_search_settings(page: Fetched | None) -> dict:
    if page is None:
        return _unknown("search_settings")
    metas, title = read_head(page.body)
    noindex = _has_noindex(page, metas)
    blocked = _robots_blocks(page)
    if noindex or blocked:
        status = "critical"
    else:
        status = "ok" if title else "warn"
    return {
        "id": "search_settings",
        "status": status,
        "facts": {"noindex": noindex, "robots_blocks_top": blocked, "title_present": bool(title)},
    }


def check_mobile_view(page: Fetched | None) -> dict:
    if page is None:
        return _unknown("mobile_view")
    metas, _ = read_head(page.body)
    present = "viewport" in metas
    return {
        "id": "mobile_view",
        "status": "ok" if present else "warn",
        "facts": {"viewport_present": present},
    }
