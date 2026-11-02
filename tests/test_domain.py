import unittest
from datetime import date

from shindan.checks.domain import (
    judge_domain,
    parse_jprs_whois,
    parse_rdap,
    registrable_domain,
)
from shindan.checks.ssl_cert import judge_certificate

# JPRS WHOIS の実際の応答から、期限の判定に関わる行だけを抜いたもの。
ATTRIBUTE_TYPE = """
a. [Domain Name]                JPRS.CO.JP
[State]                         Connected (2027/01/31)
[Registered Date]               2001/01/22
[Last Update]                   2026/02/01 01:02:04 (JST)
"""
GENERAL_TYPE = """
[Domain Name]                   JPRS.JP
[Created on]                    2001/02/02
[Expires on]                    2027/02/28
[Status]                        Active
"""
NOT_FOUND = "No match!!\n"


class DomainTest(unittest.TestCase):
    def test_registrable_domain(self):
        self.assertEqual(registrable_domain("www.example.co.jp"), "example.co.jp")
        self.assertEqual(registrable_domain("example.co.jp"), "example.co.jp")
        self.assertEqual(registrable_domain("www.example.jp"), "example.jp")
        self.assertEqual(registrable_domain("shop.example.com"), "example.com")

    def test_jprs_both_formats(self):
        self.assertEqual(parse_jprs_whois(ATTRIBUTE_TYPE)["expires_at"], date(2027, 1, 31))
        self.assertEqual(parse_jprs_whois(GENERAL_TYPE)["expires_at"], date(2027, 2, 28))
        self.assertEqual(parse_jprs_whois(NOT_FOUND), {"found": False, "expires_at": None})

    def test_rdap_date_is_converted_to_jst(self):
        payload = {"events": [{"eventAction": "expiration", "eventDate": "2027-08-13T20:00:00Z"}]}
        self.assertEqual(parse_rdap(payload)["expires_at"], date(2027, 8, 14))

    def test_domain_thresholds(self):
        today = date(2026, 11, 2)
        for days, expected in [(-1, "critical"), (7, "critical"), (8, "warn"), (30, "warn"), (31, "ok")]:
            expires = date.fromordinal(today.toordinal() + days)
            self.assertEqual(judge_domain({"expires_at": expires}, today)[0], expected)
        self.assertEqual(judge_domain({"expires_at": None}, today), ("unknown", None))

    def test_certificate_thresholds(self):
        self.assertEqual(judge_certificate(100, "certificate has expired"), "critical")
        self.assertEqual(judge_certificate(7, None), "critical")
        self.assertEqual(judge_certificate(14, None), "warn")
        self.assertEqual(judge_certificate(30, None), "ok")


if __name__ == "__main__":
    unittest.main()
