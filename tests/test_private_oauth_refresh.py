from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages/mcp_auth/private_oauth.py"


class PrivateOAuthRefreshSourceTests(unittest.TestCase):
    def test_refresh_ttl_is_ninety_days(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("REFRESH_TTL = 90 * 24 * 3600", source)

    def test_refresh_exchange_preserves_refresh_token(self):
        source = SOURCE.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("refresh_token=refresh_token.token", source)
        self.assertNotIn('con.execute("DELETE FROM tokens WHERE token_hash=?", (token_hash,))', source)

    def test_expired_tokens_are_pruned(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            'DELETE FROM tokens WHERE expires_at IS NOT NULL AND expires_at < ?',
            source,
        )


if __name__ == "__main__":
    unittest.main()
