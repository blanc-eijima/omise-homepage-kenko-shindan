import unittest
from datetime import date
from unittest import mock

from shindan import page as page_module
from shindan.checks import page_checks, site_software
from shindan.page import Fetched, fetch, read_head

TODAY = date(2026, 11, 3)
PHP_CYCLES = [{"cycle": "8.3", "eol": "2027-12-31"}, {"cycle": "7.4", "eol": "2022-11-28"}]
WP_CYCLES = [
    {"cycle": "7.1", "eol": False, "latest": "7.1.4"},
    {"cycle": "6.2", "eol": "2024-01-01", "latest": "6.2.9"},
]


def make_page(body="<title>店</title>", status=200, headers=None) -> Fetched:
    return Fetched("https://shop.example.com/", status, headers or {}, body)


class FetchTest(unittest.TestCase):
    def test_redirect_to_private_address_is_not_followed(self):
        hop = make_page(status=302, headers={"location": "http://127.0.0.1/admin"})
        with mock.patch.object(page_module, "_open", return_value=hop) as opened:
            self.assertIsNone(fetch("https://8.8.8.8/"))
        self.assertEqual(opened.call_count, 1)

    def test_redirect_loop_gives_up(self):
        hop = make_page(status=302, headers={"location": "https://8.8.8.8/"})
        with mock.patch.object(page_module, "_open", return_value=hop):
            self.assertIsNone(fetch("https://8.8.8.8/"))

    def test_meta_in_comment_is_ignored(self):
        metas, title = read_head('<!-- <meta name="robots" content="noindex"> --><title> 店 </title>')
        self.assertEqual(metas, {})
        self.assertEqual(title, "店")


class PageResponseTest(unittest.TestCase):
    def test_server_error_is_critical(self):
        self.assertEqual(page_checks.check_page_response(make_page(status=500))["status"], "critical")

    def test_php_error_on_screen_is_critical(self):
        body = "<b>Fatal error</b>: Uncaught Error in /home/a/x.php on line <b>12</b>"
        result = page_checks.check_page_response(make_page(body))
        self.assertEqual(result["status"], "critical")
        self.assertTrue(result["facts"]["error_text_visible"])

    def test_word_warning_in_normal_text_is_not_error(self):
        result = page_checks.check_page_response(make_page("Warning: 本日は定休日です"))
        self.assertEqual(result["status"], "ok")

    def test_unreadable_page_is_unknown(self):
        self.assertEqual(page_checks.check_page_response(None)["status"], "unknown")


class SearchSettingsTest(unittest.TestCase):
    def run_check(self, page, robots=None):
        with mock.patch.object(page_checks, "fetch", return_value=robots):
            return page_checks.check_search_settings(page)

    def test_noindex_in_meta_and_header(self):
        meta = make_page('<meta name="robots" content="NOINDEX,follow"><title>店</title>')
        self.assertEqual(self.run_check(meta)["status"], "critical")
        header = make_page(headers={"x-robots-tag": "noindex"})
        self.assertEqual(self.run_check(header)["status"], "critical")

    def test_robots_txt_blocking_everything(self):
        robots = make_page("User-agent: *\nDisallow: /\n")
        self.assertEqual(self.run_check(make_page(), robots)["status"], "critical")

    def test_missing_robots_txt_is_fine(self):
        result = self.run_check(make_page(), make_page(status=404))
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["facts"]["robots_blocks_top"])

    def test_missing_title_is_warn(self):
        self.assertEqual(self.run_check(make_page("<p>店</p>"))["status"], "warn")


class MobileViewTest(unittest.TestCase):
    def test_viewport(self):
        with_tag = make_page('<meta name="viewport" content="width=device-width">')
        self.assertEqual(page_checks.check_mobile_view(with_tag)["status"], "ok")
        self.assertEqual(page_checks.check_mobile_view(make_page())["status"], "warn")


class SiteSoftwareTest(unittest.TestCase):
    def run_check(self, page):
        cycles = {"wordpress": WP_CYCLES, "php": PHP_CYCLES}
        with mock.patch.object(site_software, "_load_cycles", side_effect=cycles.get):
            return site_software.check_site_software(page, TODAY)

    def test_old_wordpress_and_php_are_warn(self):
        page = make_page(
            '<meta name="generator" content="WordPress 6.2.1">',
            headers={"x-powered-by": "PHP/7.4.33"},
        )
        result = self.run_check(page)
        self.assertEqual(result["status"], "warn")
        self.assertTrue(result["facts"]["wordpress_support_ended"])
        self.assertTrue(result["facts"]["php_support_ended"])
        self.assertEqual(result["facts"]["php_support_ended_on"], "2022-11-28")

    def test_behind_in_supported_line_is_warn(self):
        result = self.run_check(make_page('<meta name="generator" content="WordPress 7.1.3">'))
        self.assertEqual(result["status"], "warn")
        self.assertTrue(result["facts"]["wordpress_behind_in_line"])

    def test_current_versions_are_ok(self):
        page = make_page(
            '<meta name="generator" content="WordPress 7.1.4">',
            headers={"x-powered-by": "PHP/8.3.1"},
        )
        self.assertEqual(self.run_check(page)["status"], "ok")

    def test_version_newer_than_list_is_ok(self):
        result = self.run_check(make_page('<meta name="generator" content="WordPress 7.2">'))
        self.assertEqual(result["status"], "ok")

    def test_version_missing_from_list_but_old_is_unknown(self):
        result = self.run_check(make_page('<meta name="generator" content="WordPress 5.0">'))
        self.assertEqual(result["status"], "unknown")

    def test_hidden_version_is_ok_not_a_finding(self):
        result = self.run_check(make_page('<link href="/wp-content/x.css">'))
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["facts"]["wordpress_in_use"])
        self.assertIsNone(result["facts"]["wordpress_version"])

    def test_unavailable_support_list_is_unknown(self):
        page = make_page(headers={"x-powered-by": "PHP/7.4.33"})
        with mock.patch.object(site_software, "_load_cycles", side_effect=OSError("down")):
            self.assertEqual(site_software.check_site_software(page, TODAY)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
