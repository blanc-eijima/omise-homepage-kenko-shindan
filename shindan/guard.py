"""入力URLの検証。公開されていないアドレスへは読みに行かない。"""
import http.client
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeTarget(ValueError):
    """調べてはいけない、または形が正しくない入力。"""


def _is_public(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text.split("%")[0])
    mapped = getattr(ip, "ipv4_mapped", None)
    return (mapped or ip).is_global


def public_addresses(host: str) -> list[str]:
    """hostの解決先を返す。1つでも公開アドレスでなければ断る。"""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as exc:
        raise UnsafeTarget(f"名前を解決できません: {host}") from exc
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    private = sorted(a for a in addresses if not _is_public(a))
    if private:
        raise UnsafeTarget(f"公開されていないアドレスです: {host} -> {private}")
    return addresses


class BlockedAddress(OSError):
    """接続の直前に、公開されていないアドレスへ変わっていた。通信の失敗として扱う。"""


def connect_public(address, timeout=None, source_address=None):
    """確かめたそのIPへ直接つなぐ。検査の後に名前の解決先を変える手口（DNSリバインディング）を防ぐ。"""
    host, port = address
    try:
        addresses = public_addresses(host)
    except UnsafeTarget as exc:
        raise BlockedAddress(str(exc)) from exc
    failure: OSError | None = None
    for ip in addresses:
        try:
            return socket.create_connection((ip, port), timeout, source_address)
        except OSError as exc:
            failure = exc
    raise failure


class _PublicOnly:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # http.client の接続の入口。名前解決と検査を1回にまとめるために差し替える。
        self._create_connection = connect_public


class PublicHTTPConnection(_PublicOnly, http.client.HTTPConnection):
    pass


class PublicHTTPSConnection(_PublicOnly, http.client.HTTPSConnection):
    pass


def parse_target(raw: str) -> str:
    """入力を検証してホスト名を返す。"""
    text = raw.strip()
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https"):
        raise UnsafeTarget(f"http と https だけ調べられます: {parts.scheme}")
    if parts.username or parts.password:
        raise UnsafeTarget("URLにログイン情報を含められません")
    if parts.port not in (None, 80, 443):
        raise UnsafeTarget(f"80番と443番以外のポートは調べません: {parts.port}")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeTarget("URLからホスト名を読み取れません")
    public_addresses(host)
    return host
