"""Offline protocol-boundary tests for Business API client."""
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO
from business_api import BusinessApiClient, BusinessApiError

class TransportTests(unittest.TestCase):
    def test_https_only(self):
        with self.assertRaises(BusinessApiError):
            BusinessApiClient("http://invalid.example", "token")

    def test_oib_validation(self):
        client = BusinessApiClient("https://example.org", "token")
        with patch("business_api._safe_urlopen") as send:
            with self.assertRaises(BusinessApiError):
                client.company_by_oib("not-an-oib")
            send.assert_not_called()

    def test_api_denied_remains_error(self):
        client = BusinessApiClient("https://example.org", "token")
        error = HTTPError("https://example.org", 403, "Forbidden", {}, BytesIO())
        with patch("business_api._safe_urlopen", side_effect=error):
            with self.assertRaisesRegex(BusinessApiError, "BUSINESS_API_HTTP_403"):
                client.company_by_oib("12345678901")

if __name__ == "__main__":
    unittest.main()
