# Business Intelligence MCP — source-only prototype

Remote MCP over HTTPS Streamable HTTP, using the shared `packages/mcp_auth` OAuth implementation.

## Boundary
This app is **not yet approved for production or public multi-tenant access**. The shared OAuth component currently exposes a private/single-operator authorization mode; a tenant-scoped OAuth-to-Business-API identity exchange, granular entitlements and quota enforcement must be validated before public usage. Do **not** deploy with a global service credential to public consumers.

- `BUSINESS_API_BASE_URL`: HTTPS Laravel Business API base URL
- `BUSINESS_API_SERVICE_TOKEN`: private bootstrap integration token, **not** a public user identity
- `BUSINESS_MCP_PUBLIC_HOST`: exact public hostname after registered activation
- `BUSINESS_MCP_BIND_HOST`, `BUSINESS_MCP_BIND_PORT`: loopback binding

The central Laravel API endpoint `GET /api/business/v1/companies/{oib}` is a *pending* dependency; no runtime availability is claimed. No Fabric database is directly accessed by the MCP product.

## Development acceptance
`python -m unittest discover -s apps/business-intelligence -p 'test_*.py'`

Next: implement Laravel contract and authenticated read adapter, then guarded local MCP protocol tests, and only then exact SHA governed release plus ChatGPT Plus / Claude real-client acceptance. Free user support must be tested on the actual plan and distribution surface.

<!-- Source-only API/MCP development tracking: 2026-10-12. -->

## Upstream URL acceptance

The private adapter requires a parsed HTTPS hostname and rejects URL user information, query strings and fragments. It refuses redirects. These source-side checks do not grant external client access.

## Internal operator business tools (source-only)

- `company_profile_by_oib(oib)`: exact OIB lookup via the existing central Business API.
- `company_source_provenance_by_oib(oib)`: source identifiers, retrieval times and data `as_of`; no company profile fields in the projection.
- Both tools use the same private authenticated read contract and deny results that lack explicit redistribution clearance or valid provenance.
- This is **not** a new CI/CRM UX, an independent company master, a direct P620 datastore connection or an external customer product.
- No runtime installation or external-client activation is implied by GitHub source acceptance.

## Product activation guard (2026-10-16)

The server enforces `product_access.require_private_operator_mode()` **before**
initializing OAuth. Current accepted settings are `MCP_AUTH_MODE=oauth_private`,
`MCP_OAUTH_SCOPES` containing `business.read`,
`BUSINESS_MCP_CLIENT_MODE=private_operator` (default), and
`BUSINESS_MCP_PUBLIC_CLIENTS_ENABLED=false` (default).

Any public/multi-tenant client mode fails closed. This guard is **not** tenant
authorization, nor does it make a globally shared service token safe for
external users. Tenant-scoped identity exchange and source-specific entitlements
must be implemented and verified end-to-end before external product activation.
The P620 source materializer must package `product_access.py`; source commits,
CI success, and HMAC attestation do not constitute production activation.
