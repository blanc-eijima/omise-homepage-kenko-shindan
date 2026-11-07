"""トップページとrobots.txtをGETで読む。転送先も毎回、公開アドレスか確かめる。"""
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from shindan.guard import PublicHTTPConnection, PublicHTTPSConnection, UnsafeTarget, parse_target

TIMEOUT = 10
MAX_BYTES = 2_000_000
READ_SECONDS = 20
MAX_REDIRECTS = 5
USER_AGENT = "omise-kenko-shindan/0.1"


@dataclass(frozen=True)
class Fetched:
    url: str
    status: int
    headers: dict[str, str]
    body: str


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class _PublicHTTP(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(PublicHTTPConnection, req)


class _PublicHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(PublicHTTPSConnection, req, context=self._context)


def _read_body(response) -> bytes:
    """本文を MAX_BYTES まで読む。TIMEOUT は1回の受信ごとなので、少しずつ返し続けるサイトに
    いつまでも付き合わないよう、全体にも READ_SECONDS の上限を置く。"""
    deadline = time.monotonic() + READ_SECONDS
    chunks: list[bytes] = []
    size = 0
    while size < MAX_BYTES:
        if time.monotonic() > deadline:
            raise TimeoutError("ページの読み込みに時間がかかりすぎました")
        chunk = response.read1(min(65536, MAX_BYTES - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks)


def _open(url: str) -> Fetched:
    """転送は追わずに1回だけ読む。証明書切れのサイトも中身は読めるよう検証しない。"""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(
        _NoRedirect,
        urllib.request.ProxyHandler({}),  # プロキシ経由だと接続先の検査を素通りする
        _PublicHTTP,
        _PublicHTTPS(context=context),
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        response = opener.open(request, timeout=TIMEOUT)
    except urllib.error.HTTPError as exc:
        response = exc  # 3xx・4xx・5xx も調査結果として読む
    with response:
        body = _read_body(response).decode("utf-8", "replace")
        headers = {name.lower(): value for name, value in response.headers.items()}
        return Fetched(url, response.status, headers, body)


def fetch(url: str) -> Fetched | None:
    """転送を追って最後のページを返す。読めない・公開でない転送先なら None。"""
    try:
        for _ in range(MAX_REDIRECTS + 1):
            parse_target(url)
            page = _open(url)
            location = page.headers.get("location")
            if not (300 <= page.status < 400 and location):
                return page
            url = urljoin(url, location)
    except (OSError, UnsafeTarget, ValueError):
        return None
    return None


def fetch_top(host: str) -> Fetched | None:
    return fetch(f"https://{host}/") or fetch(f"http://{host}/")


def robots_url(page_url: str) -> str:
    parts = urlsplit(page_url)
    return f"{parts.scheme}://{parts.netloc}/robots.txt"


class _HeadReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.metas: dict[str, list[str]] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            values = dict(attrs)
            name = (values.get("name") or "").lower()
            if name:
                self.metas.setdefault(name, []).append(values.get("content") or "")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def read_head(html: str) -> tuple[dict[str, list[str]], str]:
    """metaタグ（名前→内容）と title を返す。コメント内は読まない。"""
    reader = _HeadReader()
    reader.feed(html)
    return reader.metas, reader.title.strip()
