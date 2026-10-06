from __future__ import annotations

import asyncio
import os
from typing import Any

import jwt
from jwt import InvalidTokenError, PyJWKClient
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl


def _optional(name: str) -> str:
    value = os.environ.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _csv(name: str, default: str) -> list[str]:
    raw = _optional(name) or default
    return [item.strip() for item in raw.split(",") if item.strip()]


AUTH_MODE = (_optional("MCP_AUTH_MODE") or "bootstrap_bearer").lower()
if AUTH_MODE not in {"bootstrap_bearer", "oauth"}:
    raise RuntimeError("MCP_AUTH_MODE_INVALID")

OAUTH_SCOPES = _csv("MCP_OAUTH_SCOPES", "infra.read") if AUTH_MODE == "oauth" else []
OAUTH_ALGORITHMS = _csv("MCP_OAUTH_ALGORITHMS", "RS256") if AUTH_MODE == "oauth" else []


class JwtTokenVerifier:
    def __init__(
        self,
        issuer: str,
        resource: str,
        jwks_url: str,
        algorithms: list[str],
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.resource = resource.rstrip("/")
        self.algorithms = algorithms
        self.jwks = PyJWKClient(jwks_url, cache_keys=True)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            key = await asyncio.to_thread(self.jwks.get_signing_key_from_jwt, token)
            claims: dict[str, Any] = await asyncio.to_thread(
                jwt.decode,
                token,
                key.key,
                algorithms=self.algorithms,
                issuer=self.issuer,
                audience=self.resource,
                options={"require": ["exp", "iss", "aud"]},
            )
        except (InvalidTokenError, Exception):
            return None

        raw_scopes = claims.get("scope", claims.get("scp", []))
        if isinstance(raw_scopes, str):
            scopes = [s for s in raw_scopes.split() if s]
        elif isinstance(raw_scopes, list):
            scopes = [str(s) for s in raw_scopes if str(s)]
        else:
            scopes = []

        client_id = str(
            claims.get("azp")
            or claims.get("client_id")
            or claims.get("sub")
            or "oauth-client"
        )
        expires_at = int(claims["exp"]) if claims.get("exp") is not None else None

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=expires_at,
            resource=self.resource,
        )


AUTH_SETTINGS = None
TOKEN_VERIFIER = None

if AUTH_MODE == "oauth":
    issuer = _optional("MCP_OAUTH_ISSUER_URL")
    resource = _optional("MCP_OAUTH_RESOURCE_URL")
    jwks_url = _optional("MCP_OAUTH_JWKS_URL")
    if not issuer or not resource or not jwks_url:
        raise RuntimeError("MCP_OAUTH_CONFIGURATION_INCOMPLETE")

    AUTH_SETTINGS = AuthSettings(
        issuer_url=AnyHttpUrl(issuer),
        resource_server_url=AnyHttpUrl(resource),
        required_scopes=OAUTH_SCOPES,
    )
    TOKEN_VERIFIER = JwtTokenVerifier(
        issuer=issuer,
        resource=resource,
        jwks_url=jwks_url,
        algorithms=OAUTH_ALGORITHMS,
    )
