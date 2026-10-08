#!/usr/bin/env bash
# Exact-source OTB WRITE MCP ingress deployment.
# Separate OAuth/WRITE service; never alter the existing DEBUG MCP process or files.
set -Eeuo pipefail
umask 077

MCP_SHA=fc254e6f9bf1d9737e4961d5c76808e9ff7e5887
OTB_SHA=ce6e90a737a56eab3314f56335ad554686cd6765
SRC="$HOME/.project-brain/staging/mcp-apps/$MCP_SHA"
BASE="$HOME/.project-brain/controlled-execution-mcp-wordpress"
ROOT=/home/200070.cloudwaysapps.com/pfdpqmzggy/public_html
WEB="$ROOT/pb-control-mcp"
BACKUP="$BASE/backups/otb-routes-$(date -u +%Y%m%dT%H%M%SZ)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

test "$(git -C "$SRC" rev-parse HEAD)" = "$MCP_SHA"
test -f "$SRC/adapters/cloudways-shared/ingress/pb-control-mcp/index.php"
test -f "$BASE/runtime.env"
test -f "$BASE/adapter/helper.py"
test -d "$ROOT" && test -f "$ROOT/index.html"
test -f "$WEB/.pb-write-owned" || { echo "BLOCKED: WRITE ingress not owned"; exit 1; }

# Verify already-provisioned OAuth backend before changing public files.
CODE="$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8793/mcp || true)"
test "$CODE" = 401 || { echo "BACKEND_NOT_READY: $CODE"; exit 1; }

# Download canonical OTB front controller + routing from one immutable commit.
URL="https://raw.githubusercontent.com/lifeenergy-eu/app-otbplatform/$OTB_SHA"
curl -fsSL "$URL/index.php" -o "$TMP/index.php"
curl -fsSL "$URL/.htaccess" -o "$TMP/root.htaccess"
php -l "$TMP/index.php" >/dev/null

# Materialize original pinned WRITE bridge, changing only the public host.
sed 's/ai-runtime\.larimarcode\.com/otbplatform.com/g' \
  "$SRC/adapters/cloudways-shared/ingress/pb-control-mcp/index.php" > "$TMP/ingress.php"
php -l "$TMP/ingress.php" >/dev/null
cat > "$TMP/ingress.htaccess" <<'HTACCESS'
Options -Indexes
DirectoryIndex index.php
RewriteEngine On
RewriteCond %{HTTP:Authorization} ^(.+)$
RewriteRule .* - [E=HTTP_AUTHORIZATION:%1]
RewriteRule ^$ index.php [L,QSA]
RewriteRule ^(mcp|authorize|token|register|revoke|oauth/login|\.well-known/oauth-authorization-server)/?$ index.php [L,QSA]
<IfModule mod_headers.c>
Header always set Cache-Control "private, no-store"
</IfModule>
HTACCESS

# Back up prior files privately, never under the public webroot.
install -d -m 700 "$BACKUP"
test ! -f "$ROOT/index.php" || cp -p "$ROOT/index.php" "$BACKUP/root-index.php"
test ! -f "$ROOT/.htaccess" || cp -p "$ROOT/.htaccess" "$BACKUP/root.htaccess"
test ! -f "$WEB/index.php" || cp -p "$WEB/index.php" "$BACKUP/ingress-index.php"
test ! -f "$WEB/.htaccess" || cp -p "$WEB/.htaccess" "$BACKUP/ingress.htaccess"

# Replace invalid PHP atomically; homepage remains index.html.
install -m 644 "$TMP/index.php" "$ROOT/.index.php.otb-new"
mv -f "$ROOT/.index.php.otb-new" "$ROOT/index.php"
install -m 644 "$TMP/root.htaccess" "$ROOT/.htaccess.otb-new"
mv -f "$ROOT/.htaccess.otb-new" "$ROOT/.htaccess"
install -m 644 "$TMP/ingress.php" "$WEB/.index.php.otb-new"
mv -f "$WEB/.index.php.otb-new" "$WEB/index.php"
install -m 644 "$TMP/ingress.htaccess" "$WEB/.htaccess.otb-new"
mv -f "$WEB/.htaccess.otb-new" "$WEB/.htaccess"
php -l "$ROOT/index.php"
php -l "$WEB/index.php"
echo "SOURCE: PASS OTB=$OTB_SHA MCP=$MCP_SHA"
echo "PRIVATE_BACKUP: $BACKUP"

# Best-effort cache invalidation (dashboard purge may be needed).
curl -sS -o /dev/null --max-time 3 -X PURGE -H 'Host: otbplatform.com' \
  http://127.0.0.1/pb-control-mcp/mcp || true

# HTTP 200 OTB homepage HTML must never be interpreted as OAuth metadata.
STAMP="$(date +%s)"
MCP_STATUS="$(curl -sS --max-time 20 -H 'Cache-Control: no-cache' \
  -H 'Accept: application/json, text/event-stream' \
  -o "$TMP/mcp-response" -w '%{http_code}' \
  "https://otbplatform.com/pb-control-mcp/mcp?verification=$STAMP" || true)"
OAUTH_STATUS="$(curl -sS --max-time 20 -H 'Cache-Control: no-cache' \
  -o "$TMP/oauth-response" -w '%{http_code}' \
  "https://otbplatform.com/.well-known/oauth-authorization-server/pb-control-mcp?verification=$STAMP" || true)"
echo "MCP_HTTP: $MCP_STATUS OAUTH_HTTP: $OAUTH_STATUS"
if test "$MCP_STATUS" = 401 && test "$OAUTH_STATUS" = 200 &&
   grep -q '"issuer"' "$TMP/oauth-response"; then
  echo "OTB_WRITE_MCP_PUBLIC_ONLINE: PASS"
else
  echo "OTB_WRITE_MCP_PUBLIC_ONLINE: NOT_VERIFIED"
  echo "Cloudways Nginx/Varnish may serve cached index.html before Apache .htaccess."
  exit 2
fi
echo "EXECUTION: FAIL_CLOSED until canonical WordPress-to-Run-Core adapter is registered."
