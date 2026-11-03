"""SSL証明書の期限と、http から https への転送を調べる。"""
import ssl
from datetime import datetime, timezone
from urllib.parse import urlsplit

from cryptography import x509

from shindan.guard import PublicHTTPConnection, connect_public

TIMEOUT = 10
# Let's Encrypt などは期限の約30日前に自動更新する＝残り30日は正常の範囲。
# 残り14日を切ったら自動更新の失敗を疑う。
WARN_DAYS = 14
CRITICAL_DAYS = 7


def _read_certificate(host: str) -> bytes:
    """期限切れでも読めるよう、検証なしで証明書の本体だけを受け取る。"""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with connect_public((host, 443), TIMEOUT) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            return tls.getpeercert(binary_form=True)


def _verify_error(host: str) -> str | None:
    """通常のブラウザと同じ検証をかけ、失敗の理由を返す。"""
    ctx = ssl.create_default_context()
    try:
        with connect_public((host, 443), TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=host):
                return None
    except ssl.SSLCertVerificationError as exc:
        return exc.verify_message


def _with_retry(func, host: str):
    """時間切れは一時的な不調のことがあるので、もう1回だけ試す。"""
    try:
        return func(host)
    except TimeoutError:
        return func(host)


def judge_certificate(days_left: int, verify_error: str | None) -> str:
    if verify_error or days_left <= CRITICAL_DAYS:
        return "critical"
    return "warn" if days_left <= WARN_DAYS else "ok"


def check_certificate(host: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    try:
        cert = x509.load_der_x509_certificate(_with_retry(_read_certificate, host))
        verify_error = _with_retry(_verify_error, host)
    except TimeoutError as exc:
        # 通信の一時的な不調を「サイトの異常」と店主に伝えない。
        return {
            "id": "ssl_certificate",
            "status": "unknown",
            "facts": {"error": str(exc)},
        }
    except (OSError, ValueError) as exc:
        return {
            "id": "ssl_certificate",
            "status": "critical",
            "facts": {"https_available": False, "error": str(exc)},
        }
    expires = cert.not_valid_after_utc
    days_left = (expires - now).days
    return {
        "id": "ssl_certificate",
        "status": judge_certificate(days_left, verify_error),
        "facts": {
            "https_available": True,
            "expires_at": expires.date().isoformat(),
            "days_left": days_left,
            "verify_error": verify_error,
        },
    }


def _read_http_response(host: str) -> tuple[int, str]:
    conn = PublicHTTPConnection(host, 80, timeout=TIMEOUT)
    try:
        conn.request("GET", "/", headers={"User-Agent": "omise-kenko-shindan/0.1"})
        response = conn.getresponse()
        return response.status, response.getheader("Location", "")
    finally:
        conn.close()


def check_http_redirect(host: str) -> dict:
    """http で開いたとき https へ転送されるかを見る。転送先は読みに行かない。"""
    try:
        status_code, location = _with_retry(_read_http_response, host)
    except OSError as exc:
        return {
            "id": "http_redirect",
            "status": "unknown",
            "facts": {"error": str(exc)},
        }
    redirected = 300 <= status_code < 400 and urlsplit(location).scheme == "https"
    return {
        "id": "http_redirect",
        "status": "ok" if redirected else "warn",
        "facts": {
            "http_status": status_code,
            "location": location,
            "redirects_to_https": redirected,
        },
    }

