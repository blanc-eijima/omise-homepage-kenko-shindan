"""入力URLの検証。公開されていないアドレスへは読みに行かない。"""
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeTarget(ValueError):
    """調べてはいけない、または形が正しくない入力。"""


def _is_public(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text.split("%")[0])
    mapped = getattr(ip, "ipv4_mapped", None)
    return (mapped or ip).is_global


def assert_public_host(host: str) -> None:
    """hostの解決先がすべて公開アドレスであることを確かめる。"""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as exc:
        raise UnsafeTarget(f"名前を解決できません: {host}") from exc
    addresses = {info[4][0] for info in infos}
    private = sorted(a for a in addresses if not _is_public(a))
    if private:
        raise UnsafeTarget(f"公開されていないアドレスです: {host} -> {private}")


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
    # ponytail: 検査と接続で別々に名前解決する（DNSリバインディングは防げない）。
    # 一般公開するときは、検査済みのIPへ直接つなぐ形へ変える。
    assert_public_host(host)
    return host
