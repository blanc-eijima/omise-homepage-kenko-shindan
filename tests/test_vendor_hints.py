import unittest
from unittest.mock import patch

from shindan.checks.vendor_hints import collect_hints, find_credit
from shindan.page import Fetched


def page(html: str) -> Fetched:
    return Fetched("https://shop.example.jp/", 200, {}, html)


class FindCreditTest(unittest.TestCase):
    def test_reads_credit_in_the_footer(self):
        self.assertEqual(find_credit("<footer>制作：かもめ工房</footer>"), "かもめ工房")
        self.assertEqual(find_credit("<p>Web design by Kamome Studio</p>"), "Kamome Studio")

    def test_ignores_service_words_and_wordpress(self):
        self.assertIsNone(find_credit("<footer>ホームページ制作について</footer>"))
        self.assertIsNone(find_credit("<footer>Designed by WordPress</footer>"))

    def test_ignores_credit_like_words_far_from_the_end(self):
        self.assertIsNone(find_credit("<p>制作：かもめ工房</p>" + "あ" * 2000))

    def test_ignores_script_contents(self):
        self.assertIsNone(find_credit('<script>var a="制作：偽の会社";</script>'))


class CollectHintsTest(unittest.TestCase):
    def test_lists_other_domains_only(self):
        answers = {"NS": ["ns1.xserver.jp.", "ns2.xserver.jp."], "MX": ["10 mail.example.jp."]}
        with patch("shindan.checks.vendor_hints._query", lambda _, kind: answers[kind]):
            hints = collect_hints("shop.example.jp", page("<footer>制作：かもめ工房</footer>"))
        self.assertEqual(hints, {"dns": ["xserver.jp"], "mail": [], "credit": "かもめ工房"})

    def test_dns_failure_leaves_hints_empty(self):
        def fail(*_):
            raise OSError("down")

        with patch("shindan.checks.vendor_hints._query", fail):
            hints = collect_hints("shop.example.jp", None)
        self.assertEqual(hints, {"dns": [], "mail": [], "credit": None})


if __name__ == "__main__":
    unittest.main()
