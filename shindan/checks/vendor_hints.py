"""業者が分からない店主のために、外から分かる名前を「手がかり」として集める。

判定ではないので status を持たず、読み解きにも渡さない。外れることがある。
ドメインの登録事業者は出さない: .jp では取れず、取れても実際の管理会社と違うことが多い。
"""
import re
from html import unescape

from shindan.checks.domain import registrable_domain
from shindan.checks.mail_settings import _query
from shindan.page import Fetched

_TAGS = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.I | re.S)
# 「制作：」のように区切りがあるか、英語の by があるものだけ。「ホームページ制作」のような案内を拾わない。
_CREDIT = re.compile(
    r"(?:制作(?:会社)?\s*[:：]|(?:Web ?[Dd]esign|Designed|Produced|Created)(?: by|\s*:))"
    r"\s*([^\s|｜<>]{2,30}(?: [^\s|｜<>]{2,20})?)"
)
_NOT_A_NAME = re.compile(r"wordpress", re.I)
TAIL_CHARS = 1500


def _other_domains(records: list[str], own: str) -> list[str]:
    """DNSの値から相手先のドメインを取り出す。自社ドメインで動かしていれば手がかりにならない。"""
    domains = {registrable_domain(r.split()[-1].rstrip(".").lower()) for r in records if r.strip()}
    return sorted(domains - {own})


def find_credit(html: str) -> str | None:
    """ページの末尾（フッター）にある制作の表示だけを読む。本文の「ホームページ制作」を拾わない。"""
    text = unescape(_TAGS.sub(" ", html))
    tail = " ".join(text.split())[-TAIL_CHARS:]
    for match in _CREDIT.finditer(tail):
        name = match.group(1).strip()
        if not _NOT_A_NAME.search(name):
            return name
    return None


def collect_hints(host: str, page: Fetched | None) -> dict:
    own = registrable_domain(host)
    try:
        dns, mail = _query(own, "NS"), _query(own, "MX")
    except (OSError, ValueError):
        dns, mail = [], []
    return {
        "dns": _other_domains(dns, own),
        "mail": _other_domains(mail, own),
        "credit": find_credit(page.body) if page else None,
    }
