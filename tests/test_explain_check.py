import unittest
from types import SimpleNamespace

from shindan.explain import ExplainError, explain
from shindan.explain_check import find_problems

SCAN = {
    "host": "shop.example.co.jp",
    "checks": [
        {"id": "ssl_certificate", "status": "ok", "facts": {"days_left": 200}},
        {
            "id": "domain_expiry",
            "status": "critical",
            "facts": {"domain": "example.co.jp", "expires_at": "2026-11-08", "days_left": 5},
        },
    ],
}


def good() -> dict:
    return {
        "summary": "ドメインの更新が近づいています。",
        "cards": [
            {
                "check_id": "domain_expiry",
                "what_is_happening": "example.co.jp の期限は2026年11月8日、あと5日です。",
                "trouble_if_left": "ホームページとメールが止まります。",
                "who_to_ask": "ドメイン会社",
                "what_to_do": "依頼文を送ってください。",
            }
        ],
        "requests": [{"to": "ドメイン会社", "subject": "更新のお願い", "body": "ご確認をお願いします。"}],
    }


class FindProblemsTest(unittest.TestCase):
    def test_grounded_output_passes(self):
        self.assertEqual(find_problems(good(), SCAN), [])

    def test_invented_number_and_domain_fail(self):
        bad = good()
        bad["cards"][0]["what_to_do"] = "費用は30000円です。other-example.jp へ連絡を。"
        problems = find_problems(bad, SCAN)
        self.assertIn("調査結果に無い数字: 30000", problems)
        self.assertIn("調査結果に無いドメイン名: other-example.jp", problems)

    def test_fullwidth_number_is_also_checked(self):
        bad = good()
        bad["summary"] = "あと３０日です。"
        self.assertIn("調査結果に無い数字: 30", find_problems(bad, SCAN))

    def test_finding_about_unscanned_topic_fails(self):
        bad = good()
        bad["summary"] = "WordPressが古くなっています。"
        self.assertIn("調べていない項目への言及: WordPress", find_problems(bad, SCAN))

    def test_missing_card_and_card_for_ok_item_fail(self):
        bad = good()
        bad["cards"][0]["check_id"] = "ssl_certificate"
        problems = find_problems(bad, SCAN)
        self.assertIn("カードの無い項目: domain_expiry", problems)
        self.assertIn("問題の無い項目のカード: ssl_certificate", problems)

    def test_requests_must_match_cards(self):
        bad = good()
        bad["requests"][0]["to"] = "制作会社"
        problems = find_problems(bad, SCAN)
        self.assertIn("依頼文の無い依頼先: ドメイン会社", problems)
        self.assertIn("カードに無い依頼先: 制作会社", problems)

    def test_jargon_only_checked_in_owner_fields(self):
        bad = good()
        bad["cards"][0]["what_is_happening"] = "SSLの問題です。"
        self.assertIn("店主向けの欄の専門用語: SSL", find_problems(bad, SCAN))
        fine = good()
        fine["requests"][0]["body"] = "SSLをご確認ください。"
        self.assertEqual(find_problems(fine, SCAN), [])


class DateFormTest(unittest.TestCase):
    def test_iso_date_in_owner_field_fails(self):
        bad = good()
        bad["cards"][0]["what_is_happening"] = "期限は2026-11-08です。"
        self.assertIn("店主向けの欄の日付の形: 2026-11-08", find_problems(bad, SCAN))


class FakeClient:
    """用意した出力を順に返す。"""

    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        text = __import__("json").dumps(next(self.outputs), ensure_ascii=False)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])


class ExplainTest(unittest.TestCase):
    def test_retries_with_problems_then_succeeds(self):
        bad = good()
        bad["summary"] = "あと99日です。"
        client = FakeClient([bad, good()])
        result = explain(SCAN, client=client)
        self.assertEqual(result["cards"][0]["status"], "critical")
        self.assertIn("調査結果に無い数字: 99", client.calls[1]["messages"][0]["content"])

    def test_gives_up_rather_than_returning_invented_facts(self):
        bad = good()
        bad["summary"] = "あと99日です。"
        with self.assertRaises(ExplainError):
            explain(SCAN, client=FakeClient([bad, bad]))


if __name__ == "__main__":
    unittest.main()
