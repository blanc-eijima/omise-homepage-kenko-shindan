"""画面。調査と読み解きを分け、調査結果を先に見せる。"""
import json
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from shindan.cli import scan
from shindan.explain import ExplainError, explain
from shindan.guard import UnsafeTarget

HOST = "127.0.0.1"
PORT = 8765
MAX_BODY = 4096
INDEX_HTML = Path(__file__).parent / "static" / "index.html"

# 読み解きには、サーバーが自分で調べた結果だけを渡す（画面から事実を差し込ませない）。
# ponytail: メモリに置くだけで消さない。ローカル動作専用。一般公開するなら期限と上限、
# 利用回数の制限、DNSリバインディング対策（guard.py のコメント参照）が要る。
_scans: dict[str, dict] = {}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

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

    def _scan(self, payload: dict) -> None:
        url = str(payload.get("url") or "").strip()
        name = str(payload.get("name") or "").strip() or None
        if not url:
            self._send_json(400, {"error": "ホームページのアドレスを入れてください"})
            return
        try:
            report = scan(url, name)
        except UnsafeTarget:
            self._send_json(400, {"error": "このアドレスは調べられません。入力をご確認ください"})
            return
        scan_id = secrets.token_urlsafe(16)
        _scans[scan_id] = report
        self._send_json(200, {"id": scan_id, "report": report})

    def _explain(self, payload: dict) -> None:
        report = _scans.get(str(payload.get("id")))
        if report is None:
            self._send_json(404, {"error": "調査結果が見つかりません。もう一度診断してください"})
            return
        try:
            self._send_json(200, {"explanation": explain(report)})
        except ExplainError as exc:
            print(f"読み解きの失敗: {exc}", file=sys.stderr)
            self._send_json(502, {"error": "説明文を作れませんでした。調査結果だけ表示しています"})

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
