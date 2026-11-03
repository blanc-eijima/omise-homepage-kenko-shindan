import unittest
from types import SimpleNamespace

import anthropic

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


class FileNameTest(unittest.TestCase):
    def test_file_names_are_not_domains(self):
        fine = good()
        fine["summary"] = "robots.txt と wp-config.php を確認します。"
        self.assertFalse([p for p in find_problems(fine, SCAN) if "ドメイン名" in p])
        bad = good()
        bad["summary"] = "other-shop.com を確認します。"
        self.assertIn("調査結果に無いドメイン名: other-shop.com", find_problems(bad, SCAN))


class PhoneNumberTest(unittest.TestCase):
    SCAN = {
        **SCAN,
        "checks": SCAN["checks"]
        + [{"id": "map_listing", "status": "ok", "facts": {"listing_phone": "0300005678"}}],
    }

    def test_same_digits_with_hyphens_pass_but_other_numbers_do_not(self):
        fine = good()
        fine["summary"] = "登録の番号は 03-0000-5678 です。"
        self.assertEqual(find_problems(fine, self.SCAN), [])
        bad = good()
        bad["summary"] = "登録の番号は 03-0000-9999 です。"
        self.assertIn("調査結果に無い数字: 300009999", find_problems(bad, self.SCAN))


class CountWordsTest(unittest.TestCase):
    def test_counting_words_pass_but_days_and_money_do_not(self):
        fine = good()
        fine["summary"] = "気になる点が２つ、確認が3件あります。"
        self.assertEqual(find_problems(fine, SCAN), [])
        for text, number in [("あと3日です。", 3), ("費用は3000円です。", 3000)]:
            bad = good()
            bad["summary"] = text
            self.assertIn(f"調査結果に無い数字: {number}", find_problems(bad, SCAN))


class JargonInDomainTest(unittest.TestCase):
    def test_domain_containing_jargon_letters_passes(self):
        scan = {**SCAN, "host": "expired.badssl.com"}
        fine = good()
        fine["summary"] = "expired.badssl.com の更新が近づいています。"
        self.assertEqual(find_problems(fine, scan), [])

    def test_fullwidth_and_lowercase_jargon_fail(self):
        for text in ["ＳＳＬの問題です。", "sslの問題です。", "httpsの設定です。"]:
            bad = good()
            bad["summary"] = text
            self.assertTrue(any("専門用語" in p for p in find_problems(bad, SCAN)), text)


class DateFormTest(unittest.TestCase):
    def test_iso_date_in_owner_field_fails(self):
        bad = good()
        bad["cards"][0]["what_is_happening"] = "期限は2026-11-08です。"
        self.assertIn("店主向けの欄の日付の形: 2026-11-08", find_problems(bad, SCAN))


NO_ISSUES = {"issues": []}


class _ApiDown(anthropic.APIError):
    def __init__(self):
        pass


class FakeClient:
    """用意した出力を順に返す。"""

    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        text = __import__("json").dumps(next(self.outputs), ensure_ascii=False)
        return SimpleNamespace(
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            content=[SimpleNamespace(type="text", text=text)],
        )


class ExplainTest(unittest.TestCase):
    def test_retries_with_problems_then_succeeds(self):
        bad = good()
        bad["summary"] = "あと99日です。"
        client = FakeClient([bad, good()])
        result = explain(SCAN, client=client)
        self.assertEqual(len(client.calls), 2)  # 残り回数が無いのでレビューは呼ばない
        self.assertEqual(result["cards"][0]["status"], "critical")
        self.assertIn("調査結果に無い数字: 99", client.calls[1]["messages"][0]["content"])

    def test_gives_up_rather_than_returning_invented_facts(self):
        bad = good()
        bad["summary"] = "あと99日です。"
        with self.assertRaises(ExplainError):
            explain(SCAN, client=FakeClient([bad, bad]))


class ReviewFlowTest(unittest.TestCase):
    def test_clean_review_needs_no_rewrite(self):
        client = FakeClient([good(), NO_ISSUES])
        self.assertEqual(explain(SCAN, client=client)["summary"], good()["summary"])
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[1]["model"], "claude-haiku-5-5")

    def test_review_issue_goes_back_to_the_writer(self):
        better = good()
        better["summary"] = "直した文面です。"
        issues = {"issues": [{"to": "ドメイン会社", "issue": "対象のドメインが書かれていません"}]}
        client = FakeClient([good(), issues, better])
        self.assertEqual(explain(SCAN, client=client)["summary"], "直した文面です。")
        self.assertIn("対象のドメインが書かれていません", client.calls[2]["messages"][0]["content"])

    def test_failed_rewrite_keeps_the_version_that_passed(self):
        bad = good()
        bad["summary"] = "あと99日です。"
        issues = {"issues": [{"to": "ドメイン会社", "issue": "値がありません"}]}
        client = FakeClient([good(), issues, bad])
        self.assertEqual(explain(SCAN, client=client)["summary"], good()["summary"])

    def test_review_api_failure_still_returns_the_letter(self):
        client = FakeClient([good()])
        real = client._create

        def create(**kwargs):
            if kwargs.get("model") == "claude-haiku-5-5":
                raise _ApiDown()
            return real(**kwargs)

        client.beta.messages.create = create
        self.assertEqual(explain(SCAN, client=client)["summary"], good()["summary"])

    def test_no_letters_means_no_review(self):
        scan = {"host": "shop.example.co.jp", "checks": [SCAN["checks"][0]]}
        client = FakeClient([{"summary": "今回調べた範囲では問題ありません。", "cards": [], "requests": []}])
        explain(scan, client=client)
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
