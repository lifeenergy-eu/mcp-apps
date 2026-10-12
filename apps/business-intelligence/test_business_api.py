import unittest
from unittest.mock import patch
from io import BytesIO
from business_api import BusinessApiClient, BusinessApiError

class ApiAdapterTests(unittest.TestCase):
    def test_https_and_token_required(self):
        with self.assertRaises(BusinessApiError):
            BusinessApiClient("http://example.org", "token")
    def test_oib_validation_blocks_external_call(self):
        client = BusinessApiClient("https://example.org", "token")
        with patch("business_api.urlopen") as call:
            with self.assertRaises(BusinessApiError):
                client.company_by_oib("../secret")
            call.assert_not_called()
    def test_authorization_and_result(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b'{"data":{"oib":"12345678901"}}'
        client=BusinessApiClient("https://example.org", "token")
        with patch("business_api.urlopen", return_value=Response()) as call:
            value=client.company_by_oib("12345678901")
        self.assertEqual(value["data"]["oib"],"12345678901")
        self.assertEqual(call.call_args.args[0].get_header("Authorization"),"Bearer token")

if __name__ == "__main__": unittest.main()
