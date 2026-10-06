# ChatGPT / plugin readiness

## Intended connection

Private Infrastructure Access is a remote MCP application.

For the P620 bootstrap host the intended product path is:

`ChatGPT plugin -> HTTPS /mcp -> P620`

Cloudways is not in this path.

## Current transport

- MCP transport: Streamable HTTP
- MCP path: `/mcp`
- tools: read-only
- custom UI: not required
- arbitrary shell: forbidden
- mutation tools: none

## Authentication stages

### Bootstrap runtime

The current P620 runtime uses a host-local static bearer secret. This is suitable for the verified private bootstrap service but is not the final public/plugin authentication model.

### Plugin/public distribution gate

Move the product authentication boundary to an OAuth-compatible remote MCP model supported by the target client. Credentials, authorization-server configuration and private host identity remain runtime configuration and must never be committed to this repository.

## OpenAI integration target

The app is designed so a supported ChatGPT surface can create a plugin directly from the remote MCP server URL, configure authentication, inspect the MCP tools and install the resulting plugin.

Plan availability is a client/product concern and does not change this repository's direct MCP network architecture.

## Compatibility path

The source directory remains `apps/p620-diagnostics` during the bootstrap compatibility series because the P620 wrapper currently pins that path. Product identity is now **Private Infrastructure Access**. A later source migration may rename the directory only together with an exact-SHA host-wrapper update.
