"""お問い合わせフォームの送り先をHTMLから読む。送信はしない。"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from shindan.checks.domain import registrable_domain
from shindan.page import Fetched, fetch

_CONTACT_HREF = re.compile(r"contact|inquiry|enquiry|toiawase|otoiawase|mailform", re.IGNORECASE)


class _FormReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.actions: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text = ""

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form" and (values.get("method") or "").lower() == "post":
            self.actions.append(values.get("action") or "")
        elif tag == "a":
            self._href, self._text = values.get("href"), ""

    def handle_data(self, data):
        if self._href is not None:
            self._text += data

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, self._text))
            self._href = None


def _read(html: str) -> _FormReader:
    reader = _FormReader()
    reader.feed(html)
    return reader


def find_contact_link(page: Fetched, links: list[tuple[str, str]]) -> str | None:
    """同じドメインのお問い合わせページを1つ探す。"""
    own = registrable_domain(urlsplit(page.url).hostname or "")
    for href, text in links:
        url = urljoin(page.url, href)
        parts = urlsplit(url)
        same_site = parts.scheme in ("http", "https") and registrable_domain(parts.hostname or "") == own
        if same_site and ("問い合わせ" in text or "問合せ" in text or _CONTACT_HREF.search(parts.path)):
            return url
    return None


def judge_form(page: Fetched, actions: list[str]) -> dict:
    targets = [urlsplit(urljoin(page.url, action)) for action in actions]
    own = registrable_domain(urlsplit(page.url).hostname or "")
    insecure = [t for t in targets if t.scheme == "http"]
    external = sorted(
        {t.hostname for t in targets if t.hostname and registrable_domain(t.hostname) != own}
    )
    return {
        "id": "contact_form",
        "status": "critical" if insecure else "ok",
        "facts": {
            "form_found": bool(targets),
            "sent_without_encryption": bool(insecure),
            "external_services": external,
        },
    }


def check_contact_form(page: Fetched | None) -> dict:
    if page is None:
        return {"id": "contact_form", "status": "unknown", "facts": {"page_read": False}}
    top = _read(page.body)
    if top.actions:
        return judge_form(page, top.actions)
    link = find_contact_link(page, top.links)
    contact_page = fetch(link) if link else None
    if contact_page is None:
        # トップから辿れないフォームまでは探しに行かない＝「無い」とは断定しない。
        return {"id": "contact_form", "status": "ok", "facts": {"form_found": None}}
    return judge_form(contact_page, _read(contact_page.body).actions)
