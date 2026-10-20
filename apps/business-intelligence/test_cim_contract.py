"""Offline CIM MCP contract tests; no network, secrets or live authorization."""
import unittest
from cim_contract import (TOOLS, CIM_CANDIDATES, CimAccessDenied,
                          require_verified_customer_context, public_customer_tools_enabled)


class CimContractTests(unittest.TestCase):
    def test_existing_tool_names_stable_and_unique(self):
        self.assertEqual([t.name for t in TOOLS], [
            "company_profile_by_oib", "company_source_provenance_by_oib",
            "business_profile_by_identifier", "business_profile_by_subject_id"])
        self.assertEqual(len({t.name for t in TOOLS + CIM_CANDIDATES}),
                         len(TOOLS + CIM_CANDIDATES))

    def test_customer_tools_not_activated(self):
        self.assertFalse(public_customer_tools_enabled())
        self.assertTrue(all(not t.customer_enabled for t in TOOLS + CIM_CANDIDATES))
        self.assertTrue(all(t.route.startswith("/ci-api/business/v1/") for t in
                            TOOLS + CIM_CANDIDATES))

    def test_missing_or_spoofed_verification_denied(self):
        for ctx in (None, {}, {"principal_kind": "human"},
                    {"verification_source": "mcp_client", "principal_kind": "human"},
                    {"verification_source": "jwt_decoded_unverified", "principal_kind": "human"}):
            with self.subTest(ctx=ctx):
                with self.assertRaises(CimAccessDenied):
                    require_verified_customer_context(ctx)

    def test_machine_tenant_terms_and_revoke_negative(self):
        valid = dict(verification_source="laravel_cim_authority",
                     principal_kind="human", subject="user-test",
                     tenant_id="tenant-test", membership_active=True,
                     terms_accepted=True, revoked=False)
        mutations = [
            {"principal_kind": "service"},
            {"subject": ""},
            {"tenant_id": ""},
            {"membership_active": False},
            {"terms_accepted": False},
            {"revoked": True},
            {"revoked": None},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(CimAccessDenied):
                    require_verified_customer_context({**valid, **mutation})

    def test_verified_authority_interface_fixture_only(self):
        # This tests the shape of an integration assertion, NOT token verification.
        require_verified_customer_context(dict(
            verification_source="laravel_cim_authority",
            principal_kind="human", subject="user-test",
            tenant_id="tenant-test", membership_active=True,
            terms_accepted=True, revoked=False))


if __name__ == "__main__":
    unittest.main()
