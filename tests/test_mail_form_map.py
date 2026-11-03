import unittest
from unittest import mock

from shindan.checks import contact_form, map_listing
from shindan.checks.mail_settings import judge_mail
from shindan.page import Fetched


def make_page(body="", url="https://shop.example.co.jp/") -> Fetched:
    return Fetched(url, 200, {}, body)


class MailTest(unittest.TestCase):
    MX = ["10 mx.example.jp."]
    SPF = ['"v=spf1 include:a.example -all"']
    DMARC = ['"v=DMARC1; p=none"']

    def test_healthy(self):
        self.assertEqual(judge_mail(self.MX, self.SPF, self.DMARC)["status"], "ok")

    def test_missing_spf_or_dmarc(self):
        self.assertEqual(judge_mail(self.MX, [], self.DMARC)["status"], "warn")
        self.assertEqual(judge_mail(self.MX, self.SPF, [])["status"], "warn")

    def test_double_spf_is_warn(self):
        result = judge_mail(self.MX, self.SPF * 2, self.DMARC)
        self.assertEqual(result["status"], "warn")
        self.assertEqual(result["facts"]["spf_records"], 2)

    def test_split_txt_record_is_read(self):
        split = ['"v=spf1 " "-all"']
        self.assertEqual(judge_mail(self.MX, split, self.DMARC)["facts"]["spf_records"], 1)

    def test_domain_without_mail_is_not_a_finding(self):
        self.assertEqual(judge_mail([], [], [])["status"], "ok")


class FormTest(unittest.TestCase):
    def test_http_action_is_critical(self):
        page = make_page('<form method="post" action="http://shop.example.co.jp/send.cgi"></form>')
        result = contact_form.check_contact_form(page)
        self.assertEqual(result["status"], "critical")
        self.assertTrue(result["facts"]["sent_without_encryption"])

    def test_relative_action_on_https_is_ok(self):
        page = make_page('<form method="POST" action="/send.php"></form>')
        self.assertEqual(contact_form.check_contact_form(page)["status"], "ok")

    def test_form_on_http_page_is_critical(self):
        page = make_page('<form method="post"></form>', url="http://shop.example.co.jp/")
        self.assertEqual(contact_form.check_contact_form(page)["status"], "critical")

    def test_external_service_is_recorded(self):
        page = make_page('<form method="post" action="https://ssgform.example/s/abc"></form>')
        self.assertEqual(
            contact_form.check_contact_form(page)["facts"]["external_services"], ["ssgform.example"]
        )

    def test_search_form_is_ignored(self):
        page = make_page('<form method="get" action="http://shop.example.co.jp/"></form>')
        self.assertEqual(contact_form.check_contact_form(page)["status"], "ok")

    def test_follows_contact_link_on_same_site_only(self):
        form = make_page('<form method="post" action="http://shop.example.co.jp/s"></form>')
        page = make_page('<a href="https://other.example.com/contact">外</a><a href="/toiawase/">お問い合わせ</a>')
        with mock.patch.object(contact_form, "fetch", return_value=form) as fetched:
            result = contact_form.check_contact_form(page)
        fetched.assert_called_once_with("https://shop.example.co.jp/toiawase/")
        self.assertEqual(result["status"], "critical")

    def test_no_form_found_is_not_asserted(self):
        result = contact_form.check_contact_form(make_page("<p>店</p>"))
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["facts"]["form_found"])


class MapTest(unittest.TestCase):
    def test_phone_forms_are_equal(self):
        for text in ["０８３３－１２－３４５６", "0833-12-3456", "(0833)12-3456", "+81 833-12-3456"]:
            self.assertEqual(map_listing.normalize_phone(text), "0833123456")

    def test_find_phones_from_text_and_link(self):
        html = '<a href="tel:0833123456">電話</a><p>FAX ０８３３－１２－９９９９</p><script>var x="0120-000-000"</script>'
        self.assertEqual(map_listing.find_phones(html), ["0833123456", "0833129999"])

    def test_dates_and_postal_codes_are_not_phones(self):
        self.assertEqual(map_listing.find_phones("<p>〒744-0000 2026-11-03 営業</p>"), [])

    def test_other_store_with_same_name_is_not_compared(self):
        places = [
            {"websiteUri": "https://other.example.com/", "nationalPhoneNumber": "03-1111-2222"},
            {"websiteUri": "https://www.example.co.jp/", "nationalPhoneNumber": "0833-12-3456"},
        ]
        picked = map_listing.pick_own_listing(places, "shop.example.co.jp")
        self.assertEqual(picked["nationalPhoneNumber"], "0833-12-3456")
        self.assertIsNone(map_listing.pick_own_listing(places[:1], "shop.example.co.jp"))

    def test_judge(self):
        listing = {"nationalPhoneNumber": "0833-12-3456"}
        self.assertEqual(map_listing.judge_listing(["0833123456"], listing)["status"], "ok")
        self.assertEqual(map_listing.judge_listing(["0833129999"], listing)["status"], "warn")
        self.assertEqual(map_listing.judge_listing([], listing)["status"], "ok")
        self.assertEqual(map_listing.judge_listing(["0833123456"], None)["status"], "ok")

    def test_api_failure_is_unknown_and_hides_key(self):
        with mock.patch.object(map_listing, "_search", side_effect=OSError("secret-key in url")):
            result = map_listing.check_map_listing(make_page("<title>店</title>"), "shop.example.co.jp", "k")
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn("secret", str(result))


if __name__ == "__main__":
    unittest.main()
