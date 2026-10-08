#!/usr/bin/env bash
# OTB WRITE MCP: deploy exact mcp-apps ingress and route via OTB PHP front controller.
# Does not change DEBUG MCP or grant new write execution authority.
set -Eeuo pipefail
umask 077
SHA=fc254e6f9bf1d9737e4961d5c76808e9ff7e5887
SRC="$HOME/.project-brain/staging/mcp-apps/$SHA"
BASE="$HOME/.project-brain/controlled-execution-mcp-wordpress"
WEBROOT="/home/200070.cloudwaysapps.com/pfdpqmzggy/public_html"
INGRESS="$WEBROOT/pb-control-mcp"
test "$(git -C "$SRC" rev-parse HEAD)" = "$SHA"
test -f "$SRC/adapters/cloudways-shared/ingress/pb-control-mcp/index.php"
test -f "$WEBROOT/index.php"
test -d "$WEBROOT"
test -f "$BASE/runtime.env"
test -f "$BASE/adapter/helper.py"
test -x "$SRC/.venv/bin/python"
echo "SOURCE: PINNED $SHA"
# Ensure separate backend is active. Existing READ MCP is untouched.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if test -S "$XDG_RUNTIME_DIR/bus"; then
  export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi
systemctl --user start pb-otb-write-mcp.service
for i in $(seq 1 20); do
  local_code="$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8793/mcp 2>/dev/null || true)"
  if test "$local_code" = 401; then break; fi
  sleep 1
done
test "$local_code" = 401 || { echo "BACKEND: FAIL HTTP ${local_code:-000}"; exit 1; }
echo "BACKEND: PASS HTTP 401"
# Refresh public ingress from exact repository file, with its host restriction changed to OTB.
install -d -m 755 "$INGRESS"
if test -f "$INGRESS/index.php" && ! test -f "$INGRESS/.pb-write-owned"; then
  echo "BLOCKED: non-owned WRITE ingress"; exit 1
fi
sed 's/ai-runtime\.larimarcode\.com/otbplatform.com/g' \
  "$SRC/adapters/cloudways-shared/ingress/pb-control-mcp/index.php" > "$INGRESS/index.php.new"
php -l "$INGRESS/index.php.new" >/dev/null
chmod 644 "$INGRESS/index.php.new"
mv "$INGRESS/index.php.new" "$INGRESS/index.php"
touch "$INGRESS/.pb-write-owned"
cat > "$INGRESS/.htaccess" <<'HTACCESS'
Options -Indexes
DirectoryIndex index.php
RewriteEngine On
RewriteCond %{HTTP:Authorization} ^(.+)$
RewriteRule .* - [E=HTTP_AUTHORIZATION:%1]
RewriteRule ^$ index.php [L,QSA]
RewriteRule ^(mcp|authorize|token|register|revoke|oauth/login|\.well-known/oauth-authorization-server)/?$ index.php [L,QSA]
HTACCESS
chmod 644 "$INGRESS/.htaccess"
# OTB's index.php outputs index.html; intercept only WRITE paths before the homepage.
python3 - "$WEBROOT/index.php" "$WEBROOT/.htaccess" <<'PY'
from pathlib import Path
import shutil, sys
root, access = map(Path, sys.argv[1:])
guard = "PB_OTB_WRITE_MCP_DISPATCH_V1"
original = root.read_text(encoding="utf-8")
if guard not in original:
    if not original.lstrip().startswith("<?php"):
        raise SystemExit("BLOCKED: unrecognized OTB index.php format")
    shutil.copy2(root, str(root) + ".before-write-mcp.bak")
    dispatch = r'''
// PB_OTB_WRITE_MCP_DISPATCH_V1 — separate route; preserve OTB homepage.
$pbWritePath = parse_url((string)($_SERVER['REQUEST_URI'] ?? '/'), PHP_URL_PATH);
if (is_string($pbWritePath) && (
    preg_match('#^/pb-control-mcp(?:/|$)#', $pbWritePath) === 1 ||
    preg_match('#^/\.well-known/oauth-authorization-server/pb-control-mcp/?$#', $pbWritePath) === 1 ||
    preg_match('#^/\.well-known/oauth-protected-resource/pb-control-mcp/mcp/?$#', $pbWritePath) === 1
)) {
    require __DIR__ . '/pb-control-mcp/index.php';
    exit;
}
'''
    mark = original.find("<?php")
    root.write_text(original[:mark + 5] + "\n" + dispatch + original[mark + 5:], encoding="utf-8")
    print("ROOT PHP DISPATCH: INSTALLED")
else:
    print("ROOT PHP DISPATCH: PRESENT")
ht = access.read_text(encoding="utf-8") if access.exists() else ""
b, e = "# BEGIN PB OTB WRITE FRONT", "# END PB OTB WRITE FRONT"
block = """# BEGIN PB OTB WRITE FRONT
<IfModule mod_rewrite.c>
RewriteEngine On
RewriteRule ^pb-control-mcp(?:/.*)?$ index.php [L,QSA]
RewriteRule ^\\.well-known/oauth-authorization-server/pb-control-mcp/?$ index.php [L,QSA]
RewriteRule ^\\.well-known/oauth-protected-resource/pb-control-mcp/mcp/?$ index.php [L,QSA]
</IfModule>
# END PB OTB WRITE FRONT
"""
if b not in ht:
    if access.exists():
        shutil.copy2(access, str(access) + ".before-write-front.bak")
    access.write_text(block + "\n" + ht.replace("DirectoryIndex index.html index.php", "DirectoryIndex index.php index.html"), encoding="utf-8")
    print("ROOT REWRITE: INSTALLED")
else:
    print("ROOT REWRITE: PRESENT")
PY
php -l "$WEBROOT/index.php"
php -l "$INGRESS/index.php"
# Cloudways cache purge is best-effort and never changes application data.
curl -s -o /dev/null --max-time 4 -X PURGE -H 'Host: otbplatform.com' 'http://127.0.0.1/pb-control-mcp/mcp' || true
echo "=== PUBLIC ACCEPTANCE ==="
T="$(date +%s)"
BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT
for url in \
  "https://otbplatform.com/pb-control-mcp/mcp?pb_probe=$T" \
  "https://otbplatform.com/.well-known/oauth-authorization-server/pb-control-mcp?pb_probe=$T"; do
  code="$(curl -sS --max-time 20 -H 'Cache-Control: no-cache' -H 'Accept: application/json, text/event-stream' -o "$BODY" -w '%{http_code}' "$url")"
  echo "HTTP $code $url"
  if [[ "$url" == *"/mcp?pb_probe="* ]]; then
    test "$code" = 401 || { echo "MCP_ROUTING_FAILED: $(head -c 110 "$BODY")"; exit 1; }
  else
    test "$code" = 200 && grep -q '"issuer"' "$BODY" || { echo "OAUTH_ROUTING_FAILED: $(head -c 110 "$BODY")"; exit 1; }
  fi
done
echo "OTB WRITE MCP PUBLIC ONLINE: PASS"
echo "https://otbplatform.com/pb-control-mcp/mcp"
echo "EXECUTION: FAIL_CLOSED until canonical adapter registration"
