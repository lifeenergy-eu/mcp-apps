"""Fail-closed product-mode regression tests, no host credentials or network."""
import unittest
from product_access import ProductAccessError, require_private_operator_mode


class ProductAccessTests(unittest.TestCase):
    def private_env(self):
        return {"MCP_AUTH_MODE": "oauth_private",
                "MCP_OAUTH_SCOPES": "business.read",
                "BUSINESS_MCP_CLIENT_MODE": "private_operator",
                "BUSINESS_MCP_PUBLIC_CLIENTS_ENABLED": "false"}

    def test_private_operator_permitted(self):
        require_private_operator_mode(self.private_env())

    def test_tenant_activation_denied(self):
        for mode in ("public", "tenant", "multi_tenant", ""):
            with self.subTest(mode=mode):
                env = self.private_env()
                env["BUSINESS_MCP_CLIENT_MODE"] = mode
                with self.assertRaisesRegex(ProductAccessError, "TENANT_AUTH_NOT_IMPLEMENTED"):
                    require_private_operator_mode(env)

    def test_public_flag_denied(self):
        for flag in ("true", "1", "yes", "TRUE"):
            with self.subTest(flag=flag):
                env = self.private_env()
                env["BUSINESS_MCP_PUBLIC_CLIENTS_ENABLED"] = flag
                with self.assertRaisesRegex(ProductAccessError, "PUBLIC_CLIENTS_NOT_AUTHORIZED"):
                    require_private_operator_mode(env)

    def test_wrong_auth_or_missing_scope_denied(self):
        for key, value in (("MCP_AUTH_MODE", "bootstrap_bearer"),
                           ("MCP_OAUTH_SCOPES", "infra.read"),
                           ("MCP_AUTH_MODE", "")):
            with self.subTest(key=key, value=value):
                env = self.private_env()
                env[key] = value
                with self.assertRaises(ProductAccessError):
                    require_private_operator_mode(env)

    def test_missing_auth_defaults_deny(self):
        with self.assertRaises(ProductAccessError):
            require_private_operator_mode({})


if __name__ == "__main__":
    unittest.main()
