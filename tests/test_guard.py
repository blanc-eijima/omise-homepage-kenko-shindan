import http.server
import socket
import threading
import unittest
from unittest import mock

from shindan import page
from shindan.checks import ssl_cert
from shindan.guard import BlockedAddress, UnsafeTarget, connect_public, parse_target


def resolves_to(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0))]


class RebindingTest(unittest.TestCase):
    """検査のときは公開アドレス、接続のときは内部アドレスを返す名前を、本物のサーバーで試す。"""

    def setUp(self):
        self.hits = []
        hits = self.hits

        class Target(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Target)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_page_read_does_not_reach_internal_address(self):
        # 80番は parse_target の許可範囲。接続の時点の答えが内部アドレスなら止まること。
        answers = [resolves_to("8.8.8.8"), resolves_to("127.0.0.1")]
        with mock.patch("socket.getaddrinfo", side_effect=answers):
            self.assertIsNone(page.fetch("http://rebind.example/"))

    def test_connection_goes_to_the_checked_address(self):
        with mock.patch("shindan.guard.public_addresses", return_value=["127.0.0.1"]):
            fetched = page._open(f"http://shop.example:{self.port}/")
        self.assertEqual((fetched.status, fetched.body), (200, "ok"))
        self.assertEqual(self.hits, ["/"])

    def test_every_direct_connection_is_blocked(self):
        with mock.patch("socket.getaddrinfo", return_value=resolves_to("127.0.0.1")):
            with self.assertRaises(BlockedAddress):
                connect_public(("rebind.example", self.port), 1)
            self.assertEqual(ssl_cert.check_http_redirect("rebind.example")["status"], "unknown")
            self.assertFalse(ssl_cert.check_certificate("rebind.example")["facts"]["https_available"])
        self.assertEqual(self.hits, [])




class GuardTest(unittest.TestCase):
    def test_rejects_non_public_and_malformed(self):
        for url in [
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://192.168.10.1/",
            "http://169.254.169.254/latest/meta-data/",
            "http://100.64.0.1/",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "file:///etc/passwd",
            "ftp://8.8.8.8/",
            "https://user:pass@8.8.8.8/",
            "https://8.8.8.8:8080/",
            "https://",
        ]:
            with self.subTest(url=url), self.assertRaises(UnsafeTarget):
                parse_target(url)

    def test_accepts_public_ip(self):
        self.assertEqual(parse_target("https://8.8.8.8/"), "8.8.8.8")
        self.assertEqual(parse_target("8.8.8.8"), "8.8.8.8")


if __name__ == "__main__":
    unittest.main()
