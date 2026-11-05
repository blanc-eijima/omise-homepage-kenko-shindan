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
        with patch("shindan.checks.vendor_hints._query", lambda _, kind: answers.get(kind, [])):
            hints = collect_hints("shop.example.jp", page("<footer>制作：かもめ工房</footer>"))
        self.assertEqual(hints, {"server": [], "dns": ["エックスサーバー"], "mail": [], "credit": "かもめ工房", "platform": False, "hosting": None})

    def test_aws_name_servers_become_one_plain_name(self):
        answers = {
            "NS": ["ns-1.awsdns-15.org.", "ns-2.awsdns-17.net.", "ns-3.awsdns-63.com.", "ns-4.awsdns-01.co.uk."],
            "MX": ["1 aspmx.l.google.com."],
        }
        with patch("shindan.checks.vendor_hints._query", lambda _, kind: answers.get(kind, [])):
            hints = collect_hints("shop.example.jp", None)
        self.assertEqual(hints, {"server": [], "dns": ["Amazon（AWS）"], "mail": ["Google"], "credit": None, "platform": True, "hosting": None})

    def test_reverse_lookup_finds_the_server_company_behind_aws_name_servers(self):
        def answer(name, kind):
            if kind == "A":
                return ["192.0.2.10"]
            if kind == "PTR":
                self.assertEqual(name, "10.2.0.192.in-addr.arpa")
                return ["bird-blue-1.znlc.jp."]
            return {"NS": ["ns-1.awsdns-15.org."]}.get(kind, [])

        with patch("shindan.checks.vendor_hints._query", answer):
            hints = collect_hints("shop.example.jp", None)
        self.assertEqual(hints["server"], ["Zenlogic"])
        self.assertEqual(hints["dns"], [])
        self.assertFalse(hints["platform"])

    def test_server_header_names_the_host_instead_of_the_platform_behind_it(self):
        answers = {"A": ["192.0.2.10"], "PTR": ["ec2-1.compute.amazonaws.com."], "NS": ["dns1.p01.nsone.net."]}
        netlify = Fetched("https://shop.example.jp/", 200, {"server": "Netlify"}, "")
        with patch("shindan.checks.vendor_hints._query", lambda _, kind: answers.get(kind, [])):
            hints = collect_hints("shop.example.jp", netlify)
        self.assertEqual(hints["server"], ["Netlify"])
        self.assertEqual(hints["dns"], [])
        self.assertEqual(hints["hosting"], "Netlify")

    def test_unknown_names_stay_as_the_domain(self):
        answers = {"NS": ["ns1.unknown-host.co.uk."], "MX": []}
        with patch("shindan.checks.vendor_hints._query", lambda _, kind: answers.get(kind, [])):
            hints = collect_hints("shop.example.jp", None)
        self.assertEqual(hints["dns"], ["unknown-host.co.uk"])
        self.assertFalse(hints["platform"])

    def test_dns_failure_leaves_hints_empty(self):
        def fail(*_):
            raise OSError("down")

        with patch("shindan.checks.vendor_hints._query", fail):
            hints = collect_hints("shop.example.jp", None)
        self.assertEqual(hints, {"server": [], "dns": [], "mail": [], "credit": None, "platform": False, "hosting": None})


if __name__ == "__main__":
    unittest.main()
