from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl, AnyUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

DEFAULT_DB = "/srv/project-brain/mcp-oauth/oauth.sqlite3"
DEFAULT_PASSWORD_FILE = "/srv/project-brain/secrets/p620-mcp-oauth-password"
DEFAULT_CLIENT_ID_FILE = "/srv/project-brain/secrets/p620-mcp-oauth-client-id"
DEFAULT_CLIENT_SECRET_FILE = "/srv/project-brain/secrets/p620-mcp-oauth-client-secret"
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 24 * 3600
AUTH_CODE_TTL = 300
PENDING_TTL = 600
MAX_LOGIN_FAILURES = 5


def _optional(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else default


def _csv(name: str, default: str) -> list[str]:
    return [v.strip() for v in _optional(name, default).split(",") if v.strip()]


AUTH_MODE = _optional("MCP_AUTH_MODE", "bootstrap_bearer").lower()
if AUTH_MODE not in {"bootstrap_bearer", "oauth_private"}:
    raise RuntimeError("MCP_AUTH_MODE_INVALID")

OAUTH_SCOPES = _csv("MCP_OAUTH_SCOPES", "infra.read") if AUTH_MODE == "oauth_private" else []


class StoredAuthorizationCode(AuthorizationCode):
    pass


class PrivateOAuthProvider(OAuthAuthorizationServerProvider[StoredAuthorizationCode, RefreshToken, AccessToken]):
    def __init__(self, issuer: str, resource: str, db_path: str, password_file: str, scopes: list[str], static_client_id_file: str = "", static_client_secret_file: str = "", static_redirect_uri: str = "") -> None:
        self.issuer = issuer.rstrip("/")
        self.resource = resource.rstrip("/")
        self.db_path = Path(db_path)
        self.password_file = Path(password_file)
        self.scopes = scopes
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.db_path.parent, 0o700)
        except PermissionError:
            pass
        self._init_db()
        if static_client_id_file and static_client_secret_file and static_redirect_uri:
            self._seed_static_client(static_client_id_file, static_client_secret_file, static_redirect_uri)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=5)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS clients(
                    client_id TEXT PRIMARY KEY,
                    body_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pending(
                    tx TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    body_json TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    failures INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS codes(
                    code TEXT PRIMARY KEY,
                    body_json TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tokens(
                    token_hash TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    expires_at INTEGER,
                    resource TEXT
                );
                """
            )
        try:
            os.chmod(self.db_path, 0o600)
        except PermissionError:
            pass

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _seed_static_client(self, client_id_file: str, client_secret_file: str, redirect_uri: str) -> None:
        client_id = Path(client_id_file).read_text(encoding="utf-8").strip()
        client_secret = Path(client_secret_file).read_text(encoding="utf-8").strip()
        if len(client_id) < 16 or len(client_secret) < 32:
            raise RuntimeError("MCP_OAUTH_STATIC_CLIENT_INVALID")
        if not self._allowed_redirect(redirect_uri):
            raise RuntimeError("MCP_OAUTH_STATIC_REDIRECT_INVALID")
        info = OAuthClientInformationFull(
            client_id=client_id,
            client_secret=client_secret,
            client_id_issued_at=int(time.time()),
            client_secret_expires_at=None,
            redirect_uris=[AnyUrl(redirect_uri)],
            token_endpoint_auth_method="client_secret_post",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=" ".join(self.scopes),
            client_name="ChatGPT Private Infrastructure Access",
        )
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO clients(client_id,body_json,created_at) VALUES(?,?,?)",
                (client_id, info.model_dump_json(), int(time.time())),
            )

    @staticmethod
    def _allowed_redirect(uri: str) -> bool:
        p = urlparse(uri)
        host = (p.hostname or "").lower()
        return p.scheme == "https" and (
            host == "chatgpt.com" or host.endswith(".chatgpt.com")
            or host == "openai.com" or host.endswith(".openai.com")
        )

    def _read_password(self) -> str:
        try:
            value = self.password_file.read_text(encoding="utf-8").strip()
        except Exception as exc:
            raise RuntimeError("MCP_OAUTH_PASSWORD_UNAVAILABLE") from exc
        if len(value) < 24:
            raise RuntimeError("MCP_OAUTH_PASSWORD_INVALID")
        return value

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self._connect() as con:
            row = con.execute("SELECT body_json FROM clients WHERE client_id=?", (client_id,)).fetchone()
        if not row:
            return None
        return OAuthClientInformationFull.model_validate(json.loads(row["body_json"]))

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise RegistrationError("invalid_client_metadata", "client_id missing")
        redirects = [str(v) for v in (client_info.redirect_uris or [])]
        if not redirects or not all(self._allowed_redirect(v) for v in redirects):
            raise RegistrationError("invalid_redirect_uri", "Only ChatGPT/OpenAI HTTPS callback URIs are permitted.")
        allowed = set(self.scopes)
        requested = set((client_info.scope or "").split())
        if requested and not requested.issubset(allowed):
            raise RegistrationError("invalid_client_metadata", "Unsupported OAuth scope.")
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO clients(client_id,body_json,created_at) VALUES(?,?,?)",
                (client_info.client_id, client_info.model_dump_json(), int(time.time())),
            )

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if params.resource != self.resource:
            raise TokenError("invalid_request", "resource must match the MCP resource identifier")
        client_id = str(client.client_id or "")
        if not client_id:
            raise TokenError("invalid_request", "client_id missing")
        tx = secrets.token_urlsafe(32)
        body = {
            "state": params.state,
            "scopes": params.scopes or self.scopes,
            "code_challenge": params.code_challenge,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "resource": params.resource,
        }
        with self._connect() as con:
            con.execute(
                "INSERT INTO pending(tx,client_id,body_json,expires_at,failures) VALUES(?,?,?,?,0)",
                (tx, client_id, json.dumps(body, separators=(",", ":")), int(time.time()) + PENDING_TTL),
            )
        return f"{self.issuer}/oauth/login?{urlencode({'tx': tx})}"

    def _complete_login(self, tx: str, password: str) -> str | None:
        now = int(time.time())
        with self._connect() as con:
            row = con.execute(
                "SELECT client_id,body_json,expires_at,failures FROM pending WHERE tx=?", (tx,)
            ).fetchone()
            if not row or int(row["expires_at"]) < now:
                con.execute("DELETE FROM pending WHERE tx=?", (tx,))
                return None
            if not hmac.compare_digest(password, self._read_password()):
                failures = int(row["failures"]) + 1
                if failures >= MAX_LOGIN_FAILURES:
                    con.execute("DELETE FROM pending WHERE tx=?", (tx,))
                else:
                    con.execute("UPDATE pending SET failures=? WHERE tx=?", (failures, tx))
                return ""
            body = json.loads(row["body_json"])
            code = secrets.token_urlsafe(32)
            code_body = {
                "code": code,
                "scopes": body["scopes"],
                "expires_at": now + AUTH_CODE_TTL,
                "client_id": row["client_id"],
                "code_challenge": body["code_challenge"],
                "redirect_uri": body["redirect_uri"],
                "redirect_uri_provided_explicitly": body["redirect_uri_provided_explicitly"],
                "resource": body["resource"],
            }
            con.execute(
                "INSERT INTO codes(code,body_json,expires_at) VALUES(?,?,?)",
                (code, json.dumps(code_body, separators=(",", ":")), now + AUTH_CODE_TTL),
            )
            con.execute("DELETE FROM pending WHERE tx=?", (tx,))
        return construct_redirect_uri(body["redirect_uri"], code=code, state=body.get("state"))

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> StoredAuthorizationCode | None:
        with self._connect() as con:
            row = con.execute("SELECT body_json,expires_at FROM codes WHERE code=?", (authorization_code,)).fetchone()
        if not row or int(row["expires_at"]) < int(time.time()):
            return None
        body = json.loads(row["body_json"])
        if body.get("client_id") != client.client_id:
            return None
        return StoredAuthorizationCode.model_validate(body)

    def _issue_pair(self, client_id: str, scopes: list[str], resource: str) -> OAuthToken:
        now = int(time.time())
        access = secrets.token_urlsafe(48)
        refresh = secrets.token_urlsafe(48)
        with self._connect() as con:
            con.execute(
                "INSERT INTO tokens(token_hash,kind,client_id,scopes_json,expires_at,resource) VALUES(?,?,?,?,?,?)",
                (self._hash_token(access), "access", client_id, json.dumps(scopes), now + ACCESS_TTL, resource),
            )
            con.execute(
                "INSERT INTO tokens(token_hash,kind,client_id,scopes_json,expires_at,resource) VALUES(?,?,?,?,?,?)",
                (self._hash_token(refresh), "refresh", client_id, json.dumps(scopes), now + REFRESH_TTL, resource),
            )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TTL,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: StoredAuthorizationCode
    ) -> OAuthToken:
        with self._connect() as con:
            con.execute("DELETE FROM codes WHERE code=?", (authorization_code.code,))
        return self._issue_pair(
            str(client.client_id),
            authorization_code.scopes,
            str(authorization_code.resource or self.resource),
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        h = self._hash_token(refresh_token)
        with self._connect() as con:
            row = con.execute(
                "SELECT client_id,scopes_json,expires_at FROM tokens WHERE token_hash=? AND kind='refresh'", (h,)
            ).fetchone()
        if not row or row["client_id"] != client.client_id:
            return None
        if row["expires_at"] and int(row["expires_at"]) < int(time.time()):
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=row["client_id"],
            scopes=json.loads(row["scopes_json"]),
            expires_at=row["expires_at"],
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        with self._connect() as con:
            row = con.execute(
                "SELECT resource FROM tokens WHERE token_hash=? AND kind='refresh'",
                (self._hash_token(refresh_token.token),),
            ).fetchone()
            con.execute("DELETE FROM tokens WHERE token_hash=?", (self._hash_token(refresh_token.token),))
        if not row:
            raise TokenError("invalid_grant", "refresh token missing")
        return self._issue_pair(str(client.client_id), scopes, str(row["resource"] or self.resource))

    async def load_access_token(self, token: str) -> AccessToken | None:
        h = self._hash_token(token)
        with self._connect() as con:
            row = con.execute(
                "SELECT client_id,scopes_json,expires_at,resource FROM tokens WHERE token_hash=? AND kind='access'", (h,)
            ).fetchone()
        if not row:
            return None
        if row["expires_at"] and int(row["expires_at"]) < int(time.time()):
            return None
        if str(row["resource"] or "") != self.resource:
            return None
        return AccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=json.loads(row["scopes_json"]),
            expires_at=row["expires_at"],
            resource=row["resource"],
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM tokens WHERE token_hash=?", (self._hash_token(token.token),))


AUTH_SETTINGS = None
AUTH_PROVIDER = None

if AUTH_MODE == "oauth_private":
    issuer = _optional("MCP_OAUTH_ISSUER_URL")
    resource = _optional("MCP_OAUTH_RESOURCE_URL")
    db_path = _optional("MCP_OAUTH_DB_PATH", DEFAULT_DB)
    password_file = _optional("MCP_OAUTH_PASSWORD_FILE", DEFAULT_PASSWORD_FILE)
    static_client_id_file = _optional("MCP_OAUTH_STATIC_CLIENT_ID_FILE", DEFAULT_CLIENT_ID_FILE)
    static_client_secret_file = _optional("MCP_OAUTH_STATIC_CLIENT_SECRET_FILE", DEFAULT_CLIENT_SECRET_FILE)
    static_redirect_uri = _optional("MCP_OAUTH_STATIC_REDIRECT_URI")
    if not issuer or not resource:
        raise RuntimeError("MCP_OAUTH_CONFIGURATION_INCOMPLETE")
    AUTH_SETTINGS = AuthSettings(
        issuer_url=AnyHttpUrl(issuer),
        resource_server_url=AnyHttpUrl(resource),
        required_scopes=OAUTH_SCOPES,
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            client_secret_expiry_seconds=None,
            valid_scopes=OAUTH_SCOPES,
            default_scopes=OAUTH_SCOPES,
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
    AUTH_PROVIDER = PrivateOAuthProvider(issuer, resource, db_path, password_file, OAUTH_SCOPES, static_client_id_file, static_client_secret_file, static_redirect_uri)


async def oauth_login_handler(request: Request) -> Response:
    if AUTH_PROVIDER is None:
        return Response(status_code=404)
    if request.method == "GET":
        tx = request.query_params.get("tx", "")
        safe_tx = html.escape(tx, quote=True)
        page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Private Infrastructure Access</title></head><body style="font-family:system-ui;max-width:420px;margin:12vh auto;padding:24px">
<h2>Private Infrastructure Access</h2><p>Authorize ChatGPT read-only access to P620 diagnostics.</p>
<form method="post"><input type="hidden" name="tx" value="{safe_tx}">
<label>Operator password</label><br><input name="password" type="password" autocomplete="current-password" required style="width:100%;padding:10px;margin:8px 0 16px">
<button type="submit" style="padding:10px 18px">Authorize</button></form></body></html>"""
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})
    form = await request.form()
    tx = str(form.get("tx") or "")
    password = str(form.get("password") or "")
    target = AUTH_PROVIDER._complete_login(tx, password)
    if target is None:
        return HTMLResponse("Authorization request expired or invalid.", status_code=400, headers={"Cache-Control": "no-store"})
    if target == "":
        return HTMLResponse("Invalid password.", status_code=401, headers={"Cache-Control": "no-store"})
    return RedirectResponse(target, status_code=302, headers={"Cache-Control": "no-store"})
