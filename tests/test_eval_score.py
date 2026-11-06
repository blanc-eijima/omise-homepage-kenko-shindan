import unittest

from evals.review_letters import passed, score
from shindan.review import REVIEW_MODEL


class EvalScoreTest(unittest.TestCase):
    def test_all_right_passes(self):
        tally = score([(REVIEW_MODEL, True, True), (REVIEW_MODEL, False, False)])
        self.assertTrue(passed(tally))

    def test_one_miss_fails(self):
        tally = score([(REVIEW_MODEL, True, False), (REVIEW_MODEL, False, False)])
        self.assertEqual(tally[REVIEW_MODEL]["missed"], 1)
        self.assertFalse(passed(tally))

    def test_false_stop_fails(self):
        tally = score([(REVIEW_MODEL, False, True)])
        self.assertEqual(tally[REVIEW_MODEL]["false_stop"], 1)
        self.assertFalse(passed(tally))

    def test_other_model_does_not_decide(self):
        tally = score([(REVIEW_MODEL, True, True), ("other", True, False)])
        self.assertTrue(passed(tally))

    def test_no_runs_for_production_model_fails(self):
        self.assertFalse(passed(score([("other", True, True)])))


if __name__ == "__main__":
    unittest.main()
