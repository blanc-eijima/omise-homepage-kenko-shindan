import unittest
from datetime import datetime

from shindan.limits import (
    DAILY_LIMIT, DAILY_MESSAGE, JST, PER_IP_LIMIT, PER_IP_MESSAGE, REVIEW_DAILY_LIMIT, UsageLimits,
)

NOON = datetime(2026, 11, 3, 12, tzinfo=JST).timestamp()


class UsageLimitsTest(unittest.TestCase):
    def setUp(self):
        self.now = NOON
        self.limits = UsageLimits(clock=lambda: self.now)

    def test_one_visitor_is_stopped_then_allowed_after_an_hour(self):
        for _ in range(PER_IP_LIMIT):
            self.assertIsNone(self.limits.take("a"))
        self.assertEqual(self.limits.take("a"), PER_IP_MESSAGE)
        self.assertIsNone(self.limits.take("b"))
        self.now += 3601
        self.assertIsNone(self.limits.take("a"))

    def test_daily_limit_applies_across_visitors_and_resets_in_jst(self):
        for i in range(DAILY_LIMIT):
            self.assertIsNone(self.limits.take(f"ip{i}"))
        self.assertEqual(self.limits.take("new"), DAILY_MESSAGE)
        self.now = datetime(2026, 11, 3, 23, 59, tzinfo=JST).timestamp()
        self.assertEqual(self.limits.take("new"), DAILY_MESSAGE)
        self.now = datetime(2026, 11, 4, 0, 1, tzinfo=JST).timestamp()
        self.assertIsNone(self.limits.take("new"))
        self.assertEqual(self.limits.used_today(), 1)

    def test_review_period_raises_daily_limit_then_returns(self):
        for day, limit in ((7, DAILY_LIMIT), (8, REVIEW_DAILY_LIMIT), (10, REVIEW_DAILY_LIMIT), (11, DAILY_LIMIT)):
            self.now = datetime(2026, 11, day, 12, tzinfo=JST).timestamp()
            limits = UsageLimits(clock=lambda: self.now)
            for i in range(limit):
                self.assertIsNone(limits.take(f"ip{i}"))
            self.assertEqual(limits.take("new"), DAILY_MESSAGE, day)
            self.assertEqual(limits.limit_today(), limit)

    def test_give_back_restores_both_counts(self):
        self.limits.take("a")
        self.limits.give_back("a")
        self.assertEqual(self.limits.used_today(), 0)
        self.limits.give_back("never-seen")
        self.assertEqual(self.limits.used_today(), 0)


if __name__ == "__main__":
    unittest.main()
