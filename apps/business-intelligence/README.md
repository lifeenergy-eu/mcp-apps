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
