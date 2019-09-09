"""
Test class to test common utils
"""
import unittest
import string
import random
from src.aws_common_utils_layer import handle_session_name_length


class AWSCommonUtils(unittest.TestCase):
    """
    unittest class for SupportCaseAggregator
    """

    def test_handle_session_name_length(self):
        """
        Test session longer than 64 characters is truncated
        :return:
        """
        random_long_string = "".join(
            [random.choice(string.ascii_letters) for _ in range(100)]
        )
        self.assertEqual(len(handle_session_name_length(random_long_string)), 64)

        random_long_string = "".join(
            [random.choice(string.ascii_letters) for _ in range(63)]
        )
        self.assertEqual(len(handle_session_name_length(random_long_string)), 63)
