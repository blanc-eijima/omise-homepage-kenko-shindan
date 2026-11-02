import unittest

from shindan.guard import UnsafeTarget, parse_target


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
