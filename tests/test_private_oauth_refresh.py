from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from packages.mcp_auth.private_oauth import PrivateOAuthProvider, REFRESH_TTL


class PrivateOAuthRefreshTests(unittest.TestCase):
    def _provider_and_client(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        password = root / "password"
        password.write_text("x" * 32, encoding="utf-8")
        provider = PrivateOAuthProvider(
            issuer="https://brain.example.test",
            resource="https://brain.example.test/mcp",
            db_path=str(root / "oauth.sqlite3"),
            password_file=str(password),
            scopes=["control.execute"],
        )
        client = OAuthClientInformationFull(
            client_id="chatgpt-test-client-0001",
            client_secret="s" * 32,
            client_id_issued_at=1,
            client_secret_expires_at=None,
            redirect_uris=[AnyUrl("https://chatgpt.com/connector/oauth/callback")],
            token_endpoint_auth_method="client_secret_post",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope="control.execute",
            client_name="test",
        )
        asyncio.run(provider.register_client(client))
        return temp, provider, client

    def test_refresh_token_is_reusable_and_not_rotated_on_refresh(self):
        temp, provider, client = self._provider_and_client()
        self.addCleanup(temp.cleanup)
        original = provider._issue_pair(str(client.client_id), ["control.execute"], provider.resource)
        first_loaded = asyncio.run(provider.load_refresh_token(client, original.refresh_token))
        self.assertIsNotNone(first_loaded)
        first = asyncio.run(provider.exchange_refresh_token(client, first_loaded, ["control.execute"]))
        self.assertEqual(first.refresh_token, original.refresh_token)

        second_loaded = asyncio.run(provider.load_refresh_token(client, original.refresh_token))
        self.assertIsNotNone(second_loaded)
        second = asyncio.run(provider.exchange_refresh_token(client, second_loaded, ["control.execute"]))
        self.assertEqual(second.refresh_token, original.refresh_token)
        self.assertNotEqual(first.access_token, second.access_token)

    def test_refresh_ttl_is_ninety_days(self):
        self.assertEqual(REFRESH_TTL, 90 * 24 * 3600)


if __name__ == "__main__":
    unittest.main()
