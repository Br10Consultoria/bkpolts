import unittest

from vendors.datacom.backup import tftp_failure_reason


class DatacomErrorTests(unittest.TestCase):
    def test_upload_failure_is_detected_immediately(self):
        response = "POPSAOFELIX# copy file backup.txt tftp://10.0.0.1\nErrors: Upload transfer failed.\nPOPSAOFELIX#"
        self.assertEqual(tftp_failure_reason(response), "Errors: Upload transfer failed.")

    def test_normal_response_is_not_failure(self):
        self.assertIsNone(tftp_failure_reason("Copy completed successfully"))


if __name__ == "__main__":
    unittest.main()
