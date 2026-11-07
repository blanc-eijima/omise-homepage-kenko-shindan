"""業者が分からない店主のために、外から分かる名前を「手がかり」として集める。

判定ではないので status を持たず、読み解きにも渡さない。外れることがある。
ドメインの登録事業者は出さない: .jp では取れず、取れても実際の管理会社と違うことが多い。
"""
import re
from html import unescape

from shindan.checks.domain import registrable_domain
from shindan.checks.mail_settings import _query
from shindan.html_text import strip_tags
from shindan.page import Fetched

# 「制作：」のように区切りがあるか、英語の by があるものだけ。「ホームページ制作」のような案内を拾わない。
_CREDIT = re.compile(
    r"(?:制作(?:会社)?\s*[:：]|(?:Web ?[Dd]esign|Designed|Produced|Created)(?: by|\s*:))"
    r"\s*([^\s|｜<>]{2,30}(?: [^\s|｜<>]{2,20})?)"
)
_NOT_A_NAME = re.compile(r"wordpress", re.I)
TAIL_CHARS = 1500


# 店主には「awsdns-15.org」では何の会社か分からないので、知っている相手は会社の名前で出す。
# ponytail: よく見る相手だけ。無いものはドメインのまま出す。増やすのは実際に見かけたときでよい。
_SERVICES = {
    "xserver.jp": "エックスサーバー",
    "znlc.jp": "Zenlogic",
    "gmoserver.jp": "GMOのサーバー",
    "sakura.ne.jp": "さくらインターネット",
    "lolipop.jp": "ロリポップ",
    "heteml.jp": "ヘテムル",
    "dnsv.jp": "お名前.com",
    "muumuu-domain.com": "ムームードメイン",
    "muumuu-mail.com": "ムームーメール",
    "value-domain.com": "バリュードメイン",
    "mixh.jp": "mixhost",
}
# サーバー会社や制作会社が裏側で使う基盤。ここが見えても契約先とは限らない。
_PLATFORMS = {
    "awsdns": "Amazon（AWS）",
    "amazonaws.com": "Amazon（AWS）",
    "google.com": "Google",
    "googlemail.com": "Google",
    "azure-dns": "Microsoft",
    "outlook.com": "Microsoft",
    "cloudflare.com": "Cloudflare",
    "nsone.net": "NS1",
}


# 応答ヘッダの Server に自分の名前を出すホスティング。IPの逆引きより確かで、逆引きだと裏側の基盤が出てしまう。
_SERVER_HEADERS = {"netlify": "Netlify", "vercel": "Vercel"}


def _service_name(name: str, table: dict[str, str]) -> str | None:
    labels = name.split(".")
    for key, service in table.items():
        if name == key or name.endswith("." + key) or any(label.startswith(key) for label in labels):
            return service
    return None


def _other_names(records: list[str], own: str) -> tuple[list[str], bool]:
    """DNSの値から相手先の名前を取り出す。自社ドメインで動かしていれば手がかりにならない。

    2つ目の値は、裏側の基盤の名前が混ざっているか。
    """
    names, platform = set(), False
    for record in records:
        if not record.strip():
            continue
        host = record.split()[-1].rstrip(".").lower()
        domain = registrable_domain(host)
        if domain == own:
            continue
        behind = _service_name(host, _PLATFORMS)
        platform = platform or behind is not None
        names.add(behind or _service_name(host, _SERVICES) or domain)
    return sorted(names), platform


def _server_names(host: str, own: str) -> tuple[list[str], bool]:
    """IPアドレスの逆引きでサーバーの持ち主を見る。ネームサーバーがAWSでも、実際のサーバー会社が分かることがある。"""
    records = []
    for address in _query(host, "A"):
        reverse = ".".join(reversed(address.split("."))) + ".in-addr.arpa"
        records += _query(reverse, "PTR")
    return _other_names(records, own)


def find_credit(html: str) -> str | None:
    """ページの末尾（フッター）にある制作の表示だけを読む。本文の「ホームページ制作」を拾わない。"""
    text = unescape(strip_tags(html))
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
    dns_names, _ = _other_names(dns, own)
    mail_names, _ = _other_names(mail, own)
    hosting = _SERVER_HEADERS.get(page.headers.get("server", "").strip().lower()) if page else None
    try:
        server_names = [hosting] if hosting else _server_names(host, own)[0]
    except (OSError, ValueError):
        server_names = []
    # サーバーの会社が分かったら、裏側の基盤の名前はかえって迷わせるので出さない。
    behind = set(_PLATFORMS.values())
    if any(name not in behind for name in server_names):
        dns_names = [name for name in dns_names if name not in behind]
    return {
        "server": server_names,
        "dns": dns_names,
        "mail": mail_names,
        "credit": find_credit(page.body) if page else None,
        "platform": bool(behind & set(server_names + dns_names + mail_names)),
        "hosting": hosting,
    }
