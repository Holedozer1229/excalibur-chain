import unittest

from chainstate import _candidate_has_more_work


class ChainworkForkChoiceTests(unittest.TestCase):
    def test_higher_cumulative_work_wins(self):
        # The candidate may be shorter or deeper; height/depth is not an
        # input to fork choice. Only cumulative proof-of-work is compared.
        self.assertTrue(_candidate_has_more_work(10_000, 9_999))

    def test_equal_work_does_not_trigger_reorganization(self):
        self.assertFalse(_candidate_has_more_work(10_000, 10_000))

    def test_lower_work_does_not_trigger_reorganization(self):
        self.assertFalse(_candidate_has_more_work(9_999, 10_000))


if __name__ == "__main__":
    unittest.main()
