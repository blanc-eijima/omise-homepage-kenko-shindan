import unittest
from unittest import mock

from shindan.checks import ssl_cert


class TimeoutTest(unittest.TestCase):
    def test_timeout_is_unknown_not_critical(self):
        with mock.patch.object(ssl_cert, "_read_certificate", side_effect=TimeoutError("timed out")) as read:
            result = ssl_cert.check_certificate("example.com")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(read.call_count, 2)

    def test_refused_connection_is_critical(self):
        with mock.patch.object(ssl_cert, "_read_certificate", side_effect=ConnectionRefusedError("refused")):
            result = ssl_cert.check_certificate("example.com")
        self.assertEqual(result["status"], "critical")
        self.assertFalse(result["facts"]["https_available"])


if __name__ == "__main__":
    unittest.main()
