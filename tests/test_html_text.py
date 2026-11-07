import random
import re
import time
import unittest

from shindan.checks.map_listing import find_phones, info_page_urls
from shindan.checks.vendor_hints import find_credit
from shindan.html_text import iter_links, strip_tags
from shindan.page import Fetched

# 置き換える前の正規表現。結果が同じかをこれと比べる。
OLD_TAG = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.I | re.S)
OLD_LINK = re.compile(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.I | re.S)
PARTS = ["<", ">", "a", " ", "script", "style", "</script>", "</style>", "<a ", 'href="x"',
         "href='y'", "#", "</a>", "b", "<>", "SCRIPT", "é", '"', "abbr", "_", "1", "\n"]


class SameResultTest(unittest.TestCase):
    def test_strip_tags_matches_the_old_regex(self):
        rng = random.Random(1)
        for _ in range(20_000):
            text = "".join(rng.choice(PARTS) for _ in range(rng.randint(0, 12)))
            self.assertEqual(strip_tags(text), OLD_TAG.sub(" ", text), text)

    def test_links_match_the_old_regex(self):
        # href の値に「>」が入る壊れた書き方だけは読まなくなった（PARTS に入れていない）。
        rng = random.Random(2)
        for _ in range(20_000):
            text = "".join(rng.choice(PARTS) for _ in range(rng.randint(0, 12)))
            self.assertEqual(list(iter_links(text)), OLD_LINK.findall(text), text)

    def test_usual_page(self):
        html = '<p>電話<b>03-1234-5678</b></p><script>var x="<a>";</script><a href="/company/">会社概要</a>'
        self.assertEqual(" ".join(strip_tags(html).split()), "電話 03-1234-5678 会社概要")
        self.assertEqual(list(iter_links(html)), [("/company/", "会社概要")])


class CraftedPageTest(unittest.TestCase):
    """閉じないタグを並べた2MBのページでも、すぐに終わる（前は1件で1時間近く止まった）。"""

    PAGES = ["<" * 2_000_000, "<script" * 285_000, "<style" * 330_000,
             '<a href="x">' * 160_000, '<a href="/about/">' * 110_000]

    def test_each_page_is_quick(self):
        for body in self.PAGES:
            started = time.monotonic()
            find_credit(body)
            find_phones(body)
            info_page_urls(Fetched("https://shop.example.jp/", 200, {}, body))
            self.assertLess(time.monotonic() - started, 3, body[:20])

    def test_info_pages_stop_at_three(self):
        body = "".join(f'<a href="/about/{n}/">会社概要</a>' for n in range(50_000))
        urls = info_page_urls(Fetched("https://shop.example.jp/", 200, {}, body))
        self.assertEqual(urls, [f"https://shop.example.jp/about/{n}/" for n in range(3)])


if __name__ == "__main__":
    unittest.main()
