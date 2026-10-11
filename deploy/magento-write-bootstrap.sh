#!/usr/bin/env bash
# Existing operator-approved Magento Brain WRITE bootstrap wrapper.
# Only for a specific authorized recovery; routine deploy is via Brain Run Core.
# Usage: bash magento-write-bootstrap.sh MCP_APPS_SHA40 BRAIN_SHA40
set -Eeuo pipefail
if [[ $# -ne 2 || ! "${1:-}" =~ ^[a-f0-9]{40}$ || ! "${2:-}" =~ ^[a-f0-9]{40}$ ]]; then
  echo 'Usage: bash magento-write-bootstrap.sh MCP_APPS_SHA40 BRAIN_SHA40' >&2
  exit 2
fi
MCP_SHA="$1"; BRAIN_SHA="$2"
if [[ "$MCP_SHA" == "$BRAIN_SHA" ]]; then
  echo 'FAIL_CLOSED: APPLICATION_AND_BRAIN_SHA_MUST_BE_DISTINCT' >&2
  exit 2
fi
# The existing bootstrap was previously used for the protected initial
# source cutover. This wrapper does not invent a new target, runner or plan.
CANDIDATE="${PB_EXISTING_OPERATOR_BOOTSTRAP:-$PWD/deploy_mcp_apps_sha_magento.sh}"
if [[ ! -f "$CANDIDATE" || -L "$CANDIDATE" ]]; then
  echo 'FAIL_CLOSED: EXISTING_OPERATOR_BOOTSTRAP_NOT_PRESENT'
  echo 'Use the canonical Brain brain_execute(repository, commit_sha) release path.'
  exit 2
fi
if ! grep -q 'RUNNING_REGISTERED_RELAY_REFRESH' "$CANDIDATE" || \
   ! grep -q 'MCP_APPS_FULL_SOURCE_PASS' "$CANDIDATE"; then
  echo 'FAIL_CLOSED: EXISTING_BOOTSTRAP_IDENTITY_UNVERIFIED' >&2
  exit 2
fi
echo "REQUESTED_EXACT_SHA: mcp_apps=$MCP_SHA brain=$BRAIN_SHA"
echo 'EXCEPTION_ONLY: pre-existing operator bootstrap; no independent deployment route authorized'
export PYTHONDONTWRITEBYTECODE=1
exec bash "$CANDIDATE" "$MCP_SHA" "$BRAIN_SHA"
