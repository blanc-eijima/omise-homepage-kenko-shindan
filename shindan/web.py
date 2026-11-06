"""画面。調査と読み解きを分け、調査結果を先に見せる。"""
import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from shindan.cli import scan
from shindan.explain import ExplainError, explain
from shindan.guard import UnsafeTarget
from shindan.limits import UsageLimits

# 既定はこのPCの中だけ。公開先では Dockerfile が環境変数で指定する。
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))
MAX_BODY = 4096
SCAN_TTL = 3600
HEARTBEAT = 20  # 秒。前段のプロキシは無通信が続く接続を切る
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
}
INDEX_HTML = Path(__file__).parent / "static" / "index.html"

# 読み解きには、サーバーが自分で調べた結果だけを渡す（画面から事実を差し込ませない）。
# 調査結果1件につき読み解きは1回だけ。同じ番号で何度も呼ばれてClaudeの費用が増えるのを防ぐ。
FAILED = (500, {"error": "うまく調べられませんでした。もう一度お試しください"})
_scans: dict[str, tuple[float, dict]] = {}
_scans_lock = threading.Lock()
_limits = UsageLimits()


def _keep_scan(report: dict) -> str:
    scan_id = secrets.token_urlsafe(16)
    now = time.time()
    with _scans_lock:
        for old_id in [i for i, (kept_at, _) in _scans.items() if now - kept_at > SCAN_TTL]:
            del _scans[old_id]
        _scans[scan_id] = (now, report)
    return scan_id


def _take_scan(scan_id: str) -> dict | None:
    with _scans_lock:
        kept = _scans.pop(scan_id, None)
    return kept[1] if kept else None


class Handler(BaseHTTPRequestHandler):
    timeout = 60  # 途中で黙る接続に居座られない

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _send_slow(self, work) -> None:
        """すぐ終われば普通に返す。長引くなら先に200を返し、終わるまで空白を送り続ける。
        JSONの前の空白は無視されるので、画面は本文の error で失敗を判断する。"""
        box: dict = {}
        thread = threading.Thread(target=lambda: box.update(result=work()), daemon=True)
        thread.start()
        thread.join(HEARTBEAT)
        if not thread.is_alive():
            self._send_json(*box.get("result", FAILED))
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        try:
            while thread.is_alive():
                self.wfile.write(b" ")
                thread.join(HEARTBEAT)
            _, payload = box.get("result", FAILED)
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        except OSError:
            pass  # 相手が先に閉じた

    def _read_json(self) -> dict | None:
        """他のサイトから勝手に呼ばれないよう、JSON以外は受けない。"""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if not 0 < length <= MAX_BODY:
            return None
        # 本文を読み切ってから断る。読まずに返すと接続が切れ、応答が届かないことがある。
        body = self.rfile.read(length)
        if self.headers.get_content_type() != "application/json":
            return None
        try:
            payload = json.loads(body)
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    def do_GET(self):
        if self.path == "/":
            self._send(200, INDEX_HTML.read_bytes(), "text/html; charset=utf-8")
        else:
            self._send_json(404, {"error": "ページがありません"})

    def do_POST(self):
        payload = self._read_json()
        if payload is None:
            self._send_json(400, {"error": "入力の形が正しくありません"})
        elif self.path == "/api/scan":
            self._scan(payload)
        elif self.path == "/api/explain":
            self._explain(payload)
        else:
            self._send_json(404, {"error": "ページがありません"})

    def _client_ip(self) -> str:
        """Fly.io上では、前段が付ける接続元だけを信じる（他の環境では偽装できるので見ない）。"""
        if os.environ.get("FLY_APP_NAME"):
            return self.headers.get("Fly-Client-IP") or self.client_address[0]
        return self.client_address[0]

    def _scan(self, payload: dict) -> None:
        url = str(payload.get("url") or "").strip()
        name = str(payload.get("name") or "").strip() or None
        if not url:
            self._send_json(400, {"error": "ホームページのアドレスを入れてください"})
            return
        ip = self._client_ip()
        if refusal := _limits.take(ip):
            self._send_json(429, {"error": refusal})
            return

        def work() -> tuple[int, dict]:
            try:
                report = scan(url, name)
            except UnsafeTarget:
                _limits.give_back(ip)
                return 400, {"error": "このアドレスは調べられません。入力をご確認ください"}
            print(f"診断 本日{_limits.used_today()}/{_limits.limit_today()}件", file=sys.stderr)
            return 200, {"id": _keep_scan(report), "report": report}

        self._send_slow(work)

    def _explain(self, payload: dict) -> None:
        report = _take_scan(str(payload.get("id")))
        if report is None:
            self._send_json(404, {"error": "調査結果が見つかりません。もう一度診断してください"})
            return

        def work() -> tuple[int, dict]:
            try:
                return 200, {"explanation": explain(report)}
            except ExplainError as exc:
                print(f"読み解きの失敗: {exc}", file=sys.stderr)
                return 502, {"error": "説明文を作れませんでした。調査結果だけ表示しています"}

        self._send_slow(work)

    def log_message(self, format, *args):
        pass


def make_server(port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, port), Handler)


def main() -> None:
    sys.stderr.reconfigure(encoding="utf-8")
    print(f"http://{HOST}:{PORT}/ を開いてください", flush=True)
    make_server().serve_forever()


if __name__ == "__main__":
    main()
