# CIM-MCP source-only handoff — 2026-10-20

Branch: dev/cim-lane-mcp-20261020. Owner: CIM-MCP only.

Existing apps/business-intelligence/server.py remains the ONLY Business Intelligence HTTPS Streamable HTTP MCP server. Existing packages/mcp_auth/private_oauth.py provides password-based private-operator OAuth, NOT verified CIM user Keycloak PKCE. Existing business_api.py uses only the central Laravel /ci-api/business/v1 endpoint. Existing product_access.py denies public and tenant modes; do not disable this guard without full integration.

Added cim_contract.py containing four existing stable tool names and three disabled typed CIM candidates. Added test_cim_contract.py with fail-closed negative fixtures for invalid verification source, machine identity, missing human, inactive membership, missing tenant, unaccepted Terms and revocation. These are offline shape tests, not cryptographic token verification or actual user authorization.

Required coordinator integrations:
1. IAM: real human Keycloak authorization code S256 PKCE, state, issuer, audience, redirect, verifier, nonce, expiration, replay and refresh tests.
2. Laravel: verified user subject, scope, active tenant membership, current approved Terms receipt and revocation validated SERVER-SIDE on EVERY call. Never trust caller-supplied tenant_id or an MCP client ID as user identity.
3. MCP bridge: keep existing HTTPS FastMCP endpoint, preserve four existing tool names and schema; wire user-bound token exchange or verified principal against Laravel. Never expose global BUSINESS_API_SERVICE_TOKEN as a public user credential.
4. Source policy: reject restricted or unknown data redistribution and provenance, even for active members.
5. Negative end-to-end: wrong issuer/audience, missing/mismatched PKCE, reused code, expired or replayed refresh, wrong scopes, machine token, inactive tenant, cross-tenant access, missing/old Terms, revoke and restricted sources must fail with no protected data.
6. Client acceptance: individually connect real ChatGPT Free and Plus clients and verify OAuth callback, refresh, tools/list, tools/call and denied cases. Local protocol simulations cannot prove plan eligibility.
7. Release: no customer enrollment, new service, new API, new IAM, scheduler or production deploy from this lane. Coordinator alone owns integration and registered exact-SHA release.

Offline test command: python -m unittest discover -s apps/business-intelligence -p 'test_*.py'

This source handoff does NOT assert working live PKCE, public customer compatibility or production PASS.
