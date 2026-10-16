import unittest
from unittest.mock import patch
from business_api import BusinessApiClient, BusinessApiError

class ApiAdapterTests(unittest.TestCase):
    def test_redirect_handler_rejects_redirect(self):
        from business_api import _NoRedirect
        from urllib.request import Request
        self.assertIsNone(_NoRedirect().redirect_request(
            Request("https://example.org"), None, 302, "Found", {},
            "https://untrusted.example"))

    def test_https_and_token_required(self):
        with self.assertRaises(BusinessApiError):
            BusinessApiClient("http://example.org", "token")
    def test_url_query_fragment_and_userinfo_are_rejected(self):
        for url in (
            "https://user:secret@example.org",
            "https://example.org?token=unsafe",
            "https://example.org#fragment",
            "https:///missing-host",
        ):
            with self.subTest(url=url):
                with self.assertRaises(BusinessApiError):
                    BusinessApiClient(url, "test-token")

    def test_oib_validation_blocks_external_call(self):
        client = BusinessApiClient("https://example.org", "token")
        with patch("business_api._safe_urlopen") as call:
            with self.assertRaises(BusinessApiError):
                client.company_by_oib("../secret")
            call.assert_not_called()
    def test_authorization_and_result(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b'{"data":{"oib":"12345678901"},"meta":{"as_of":"2026-10-12T00:00:00Z","provenance":[{"source_key":"FIXTURE","retrieved_at":"2026-10-12T00:00:00Z"}],"redistribution_allowed":true}}'
        client=BusinessApiClient("https://example.org", "token")
        with patch("business_api._safe_urlopen", return_value=Response()) as call:
            value=client.company_by_oib("12345678901")
        self.assertEqual(value["data"]["oib"],"12345678901")
        self.assertEqual(call.call_args.args[0].get_header("Authorization"),"Bearer token")

    def test_source_provenance_projection_excludes_company_data(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n):
                return b'{"data":{"oib":"12345678901","name":"PRIVATE_FIXTURE"},"meta":{"as_of":"2026-10-12T00:00:00Z","provenance":[{"source_key":"FIXTURE","retrieved_at":"2026-10-12T00:00:00Z"}],"redistribution_allowed":true}}'
        client = BusinessApiClient("https://example.org", "token")
        with patch("business_api._safe_urlopen", return_value=Response()):
            result = client.company_source_provenance_by_oib("12345678901")
        self.assertEqual(result["oib"], "12345678901")
        self.assertEqual(result["provenance"][0]["source_key"], "FIXTURE")
        self.assertNotIn("data", result)
        self.assertNotIn("name", result)

    def test_source_provenance_does_not_bypass_rights(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n):
                return b'{"data":{"oib":"12345678901"},"meta":{"as_of":"2026-10-12T00:00:00Z","provenance":[{"source_key":"FIXTURE","retrieved_at":"2026-10-12T00:00:00Z"}],"redistribution_allowed":false}}'
        client = BusinessApiClient("https://example.org", "token")
        with patch("business_api._safe_urlopen", return_value=Response()):
            with self.assertRaisesRegex(BusinessApiError, "RIGHTS_NOT_GRANTED"):
                client.company_source_provenance_by_oib("12345678901")

    def test_disallowed_redistribution_rejected(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n):
                return b'{"data":{"oib":"12345678901"},"meta":{"as_of":"2026-10-12T00:00:00Z","provenance":[{"source_key":"FIXTURE","retrieved_at":"2026-10-12T00:00:00Z"}],"redistribution_allowed":false}}'
        client = BusinessApiClient("https://example.org", "token")
        with patch("business_api._safe_urlopen", return_value=Response()):
            with self.assertRaisesRegex(BusinessApiError, "RIGHTS_NOT_GRANTED"):
                client.company_by_oib("12345678901")

    def test_incomplete_source_entry_rejected(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n):
                return b'{"data":{"oib":"12345678901"},"meta":{"as_of":"2026-10-12T00:00:00Z","provenance":[{"source_key":"FIXTURE"}],"redistribution_allowed":true}}'
        client = BusinessApiClient("https://example.org", "token")
        with patch("business_api._safe_urlopen", return_value=Response()):
            with self.assertRaisesRegex(BusinessApiError, "SOURCE_TRAIL_REQUIRED"):
                client.company_by_oib("12345678901")

    def test_per_source_restriction_overrides_aggregate_permission(self):
        import json
        class Response:
            def __init__(self, source): self.source = source
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n):
                return json.dumps({
                    "data": {"oib": "12345678901"},
                    "meta": {"as_of": "2026-10-16T00:00:00Z",
                             "redistribution_allowed": True,
                             "provenance": [self.source]}
                }).encode("utf-8")
        base = {"source_key": "FIXTURE", "retrieved_at": "2026-10-16T00:00:00Z"}
        client = BusinessApiClient("https://example.org", "token")
        for restricted in ({"redistribution_allowed": False},
                           {"rights_status": "DENIED"},
                           {"rights_status": "RESTRICTED"},
                           {"rights_status": "UNKNOWN"}):
            with self.subTest(restricted=restricted):
                with patch("business_api._safe_urlopen", return_value=Response({**base, **restricted})):
                    with self.assertRaisesRegex(BusinessApiError, "SOURCE_RIGHTS_NOT_GRANTED"):
                        client.company_by_oib("12345678901")

    def test_typed_profile_selectors_reject_invalid_before_network(self):
        client = BusinessApiClient("https://example.org", "token")
        cases = [
            {"oib": "invalid"},
            {"oib": "12345678901", "subject_id": "s1"},
            {"identifier_type": "MBS"},
            {"identifier_type": "REGISTRY_ID", "identifier_value": "ABC-123"},
            {"identifier_type": "MBS", "identifier_value": "110021933", "limit": 51},
            {"subject_id": "../unsafe"},
        ]
        with patch("business_api._safe_urlopen") as call:
            for kwargs in cases:
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(BusinessApiError):
                        client.profile_by_identifier(**kwargs)
            call.assert_not_called()

    def test_typed_profile_selectors_encode_query_and_check_identity(self):
        import json
        from urllib.parse import parse_qs, urlsplit
        payload = {
            "data": {"identity": {
                "subject_id": "fabric-sub-01",
                "oib": "42358685803",
                "identifiers": [
                    {"identifier_type": "MBS", "identifier_value": "110021933", "source_id": "SUDREG"},
                    {"identifier_type": "REGISTRY_ID", "identifier_value": "ABC-123", "source_id": "SUDREG"}
                ]
            }},
            "meta": {"as_of": "2026-10-16T12:00:00Z", "redistribution_allowed": True,
                     "provenance": [{"source_key": "SUDREG", "retrieved_at": "2026-10-16T11:00:00Z"}]}
        }
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return json.dumps(payload).encode()
        client = BusinessApiClient("https://example.org", "token")
        for kwargs in [
            {"oib": "42358685803"},
            {"subject_id": "fabric-sub-01"},
            {"identifier_type": "MBS", "identifier_value": "110021933"},
            {"identifier_type": "REGISTRY_ID", "identifier_value": "ABC-123", "source_id": "SUDREG"},
        ]:
            with self.subTest(kwargs=kwargs):
                with patch("business_api._safe_urlopen", return_value=Response()) as call:
                    output = client.profile_by_identifier(**kwargs)
                    query = parse_qs(urlsplit(call.call_args.args[0].full_url).query)
                    self.assertEqual(query["limit"], ["20"])
                    self.assertIn("identity", output["data"])

    def test_profile_typed_identity_mismatch_is_rejected(self):
        import json
        payload = {
            "data": {"identity": {
                "subject_id": "fabric-sub-01",
                "identifiers": [{"identifier_type": "MBS", "identifier_value": "110021933"}]
            }},
            "meta": {"as_of": "2026-10-16T12:00:00Z", "redistribution_allowed": True,
                     "provenance": [{"source_key": "SUDREG", "retrieved_at": "2026-10-16T11:00:00Z"}]}
        }
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return json.dumps(payload).encode()
        client = BusinessApiClient("https://example.org", "token")
        with patch("business_api._safe_urlopen", return_value=Response()):
            with self.assertRaisesRegex(BusinessApiError, "PROFILE_IDENTITY_MISMATCH"):
                client.profile_by_identifier(identifier_type="MBS", identifier_value="111111111")
            with self.assertRaisesRegex(BusinessApiError, "PROFILE_IDENTITY_MISMATCH"):
                client.profile_by_identifier(subject_id="fabric-sub-02")

    def test_missing_provenance_rejected(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b'{"data":{"oib":"12345678901"}}'
        client=BusinessApiClient("https://example.org", "token")
        with patch("business_api._safe_urlopen", return_value=Response()):
            with self.assertRaisesRegex(BusinessApiError, "PROVENANCE_ENVELOPE_REQUIRED"):
                client.company_by_oib("12345678901")

if __name__ == "__main__": unittest.main()
