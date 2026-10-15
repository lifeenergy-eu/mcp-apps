import unittest
from unittest.mock import patch
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
            def read(self, n): return b'{"data":{"oib":"12345678901"},"meta":{"as_of":"2026-10-12T00:00:00Z","provenance":[{"source_key":"FIXTURE","retrieved_at":"2026-10-12T00:00:00Z"}],"redistribution_allowed":true}}'
        client=BusinessApiClient("https://example.org", "token")
        with patch("business_api.urlopen", return_value=Response()) as call:
            value=client.company_by_oib("12345678901")
        self.assertEqual(value["data"]["oib"],"12345678901")
        self.assertEqual(call.call_args.args[0].get_header("Authorization"),"Bearer token")

    def test_disallowed_redistribution_rejected(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n):
                return b'{"data":{"oib":"12345678901"},"meta":{"as_of":"2026-10-12T00:00:00Z","provenance":[{"source_key":"FIXTURE","retrieved_at":"2026-10-12T00:00:00Z"}],"redistribution_allowed":false}}'
        client = BusinessApiClient("https://example.org", "token")
        with patch("business_api.urlopen", return_value=Response()):
            with self.assertRaisesRegex(BusinessApiError, "RIGHTS_NOT_GRANTED"):
                client.company_by_oib("12345678901")

    def test_incomplete_source_entry_rejected(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n):
                return b'{"data":{"oib":"12345678901"},"meta":{"as_of":"2026-10-12T00:00:00Z","provenance":[{"source_key":"FIXTURE"}],"redistribution_allowed":true}}'
        client = BusinessApiClient("https://example.org", "token")
        with patch("business_api.urlopen", return_value=Response()):
            with self.assertRaisesRegex(BusinessApiError, "SOURCE_TRAIL_REQUIRED"):
                client.company_by_oib("12345678901")

    def test_missing_provenance_rejected(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b'{"data":{"oib":"12345678901"}}'
        client=BusinessApiClient("https://example.org", "token")
        with patch("business_api.urlopen", return_value=Response()):
            with self.assertRaisesRegex(BusinessApiError, "PROVENANCE_ENVELOPE_REQUIRED"):
                client.company_by_oib("12345678901")

if __name__ == "__main__": unittest.main()
