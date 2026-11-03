import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from shindan import web
from shindan.explain import ExplainError
from shindan.guard import UnsafeTarget

REPORT = {"host": "shop.example.jp", "checks": []}


class WebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = web.make_server(0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def post(self, path, payload, content_type="application/json"):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def test_page_is_served(self):
        with urllib.request.urlopen(self.base + "/") as response:
            self.assertIn("健康診断", response.read().decode("utf-8"))

    def test_form_post_from_other_site_is_rejected(self):
        status, _ = self.post("/api/scan", {"url": "https://a.example"}, "text/plain")
        self.assertEqual(status, 400)

    def test_unsafe_address_does_not_expose_details(self):
        with mock.patch.object(web, "scan", side_effect=UnsafeTarget("127.0.0.1 secret")):
            status, data = self.post("/api/scan", {"url": "http://127.0.0.1/"})
        self.assertEqual(status, 400)
        self.assertNotIn("secret", data["error"])

    def test_explain_uses_only_the_servers_own_scan(self):
        with mock.patch.object(web, "scan", return_value=REPORT):
            _, scanned = self.post("/api/scan", {"url": "https://shop.example.jp"})
        with mock.patch.object(web, "explain", return_value={"summary": "ok"}) as explain:
            status, data = self.post("/api/explain", {"id": scanned["id"], "report": {"host": "evil"}})
        self.assertEqual(status, 200)
        explain.assert_called_once_with(REPORT)
        self.assertEqual(data["explanation"]["summary"], "ok")

    def test_unknown_scan_id_is_404(self):
        self.assertEqual(self.post("/api/explain", {"id": "none"})[0], 404)

    def test_explain_failure_keeps_details_on_server(self):
        with mock.patch.object(web, "scan", return_value=REPORT):
            _, scanned = self.post("/api/scan", {"url": "https://shop.example.jp"})
        with mock.patch.object(web, "explain", side_effect=ExplainError("internal detail")):
            with mock.patch("sys.stderr"):
                status, data = self.post("/api/explain", {"id": scanned["id"]})
        self.assertEqual(status, 502)
        self.assertNotIn("internal", data["error"])


if __name__ == "__main__":
    unittest.main()
