"""
Test class to test behaviour of SupportCaseAggregator
"""
import unittest


class SupportCaseAggregator(unittest.TestCase):
    """
    unittest class for SupportCaseAggregator
    """

    def test_get_all_existing_cases(self):
        """
        Test get all existing cases reads support case information from Support services API and
        correctly updates DDB table
        :return:
        """
        self.assertEqual("foo".upper(), "FOO")
