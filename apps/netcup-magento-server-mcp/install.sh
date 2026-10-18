#!/usr/bin/env bash
# Bootstrap ONLY: fresh Ubuntu 24.04 Netcup Magento Server MCP from pinned mcp-apps GitHub SHA.
# Run: sudo bash install.sh <40-hex-GitHub-SHA>
set -Eeuo pipefail
umask 077
[ "$#" -eq 1 ] || { echo 'Usage: sudo bash install.sh <40-character SHA>' >&2; exit 2; }
SHA="$1"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'FAIL_CLOSED: require exact Git SHA' >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo 'FAIL_CLOSED: sudo required' >&2; exit 1; }
. /etc/os-release
[ "$ID" = ubuntu ] && [ "$VERSION_ID" = 24.04 ] && [ "$(uname -m)" = x86_64 ] || { echo 'FAIL_CLOSED: expected Ubuntu 24.04 amd64' >&2; exit 1; }
command -v ip >/dev/null || { echo 'FAIL_CLOSED: ip not installed; verify host identity' >&2; exit 1; }
ip -4 -o address show scope global | grep -Fq '62.83.43.3/' || { echo 'FAIL_CLOSED: this is not the new Magento server (62.83.43.3)' >&2; exit 1; }
ROOT=/opt/netcup-magento-mcp
USER_ID=projectbrain-mcp-magento
UNIT=netcup-magento-mcp.service
ENV_FILE=/etc/project-brain/mcp/netcup-magento.env
PW_FILE=/etc/project-brain/mcp/netcup-magento-login-password
SUDOERS=/etc/sudoers.d/netcup-magento-mcp
DOMAIN=magento-mcp.larimarcode.com
for p in "$ROOT/server.py" "$ENV_FILE" "$SUDOERS" "/etc/systemd/system/$UNIT"; do
    [ ! -e "$p" ] || { echo "FAIL_CLOSED: prior installation exists: $p" >&2; exit 1; }
done

echo '==> Installing dependencies; SSH, firewall, DNS and Tailscale unchanged'
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y --no-install-recommends ca-certificates git curl sudo python3 python3-venv python3-pip

echo "==> Fetching exact mcp-apps GitHub commit $SHA"
install -d -m 0755 -o root -g root "$ROOT"
git clone --quiet --no-checkout https://github.com/lifeenergy-eu/mcp-apps.git "$ROOT/source"
git -C "$ROOT/source" checkout --quiet --detach "$SHA"
[ "$(git -C "$ROOT/source" rev-parse HEAD)" = "$SHA" ] || { echo 'FAIL_CLOSED: SHA mismatch' >&2; exit 1; }
APP="$ROOT/source/apps/netcup-magento-server-mcp"
for f in server.py root_helper.py admin_executor.py README.md; do
    [ -f "$APP/$f" ] || { echo "FAIL_CLOSED: missing source $f" >&2; exit 1; }
done
[ -f "$ROOT/source/packages/mcp_auth/private_oauth.py" ] || { echo 'FAIL_CLOSED: canonical OAuth missing' >&2; exit 1; }

echo '==> Creating dedicated account, immutable source files and independent OAuth state'
id "$USER_ID" >/dev/null 2>&1 || useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$USER_ID"
install -d -o root -g root -m 0755 /etc/project-brain
install -d -o root -g "$USER_ID" -m 0750 /etc/project-brain/mcp
install -d -o "$USER_ID" -g "$USER_ID" -m 0700 /var/lib/netcup-magento-mcp
for f in server.py root_helper.py admin_executor.py; do
    install -o root -g root -m 0644 "$APP/$f" "$ROOT/$f"
done
python3 -m venv "$ROOT/venv"
"$ROOT/venv/bin/python" -m pip --disable-pip-version-check install --no-cache-dir \
  'mcp==1.26.0' 'uvicorn==0.54.0' 'python-multipart==0.0.32'
# Bootstrap uses umask 077 for secrets. Source and virtualenv are public-code only;
# ensure the dedicated non-root service user can traverse and import them.
chmod -R a+rX "$ROOT/source" "$ROOT/venv"
runuser -u "$USER_ID" -- test -r "$ROOT/source/packages/mcp_auth/private_oauth.py"
runuser -u "$USER_ID" -- test -x "$ROOT/venv/bin/python"

if [ ! -e "$PW_FILE" ]; then
    python3 - "$PW_FILE" <<'PY'
import os, secrets, sys
fd=os.open(sys.argv[1], os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o640)
with os.fdopen(fd,'w') as f: f.write(secrets.token_urlsafe(48)+'\n')
PY
fi
chown root:"$USER_ID" "$PW_FILE"
chmod 0640 "$PW_FILE"
cat > "$ENV_FILE" <<EOF
MCP_AUTH_MODE=oauth_private
MCP_BIND_HOST=127.0.0.1
MCP_BIND_PORT=18793
MCP_OAUTH_DB_PATH=/var/lib/netcup-magento-mcp/oauth.sqlite3
MCP_OAUTH_ISSUER_URL=https://$DOMAIN
MCP_OAUTH_RESOURCE_URL=https://$DOMAIN/mcp
MCP_OAUTH_PASSWORD_FILE=$PW_FILE
MCP_OAUTH_SCOPES=control.execute
MCP_OAUTH_REQUIRED_SCOPES=control.execute
MCP_OAUTH_PRODUCT_NAME=Netcup Magento Server MCP
MCP_PUBLIC_HOST=$DOMAIN
MCP_TARGET_ID=SERVER-NETCUP-MAGENTO
MCP_PROFILE_ID=server-netcup-magento
MCP_TARGET_CLASS=netcup-business-production
MAGENTO_MCP_AUTH_PACKAGES=$ROOT/source/packages
EOF
chown root:"$USER_ID" "$ENV_FILE"
chmod 0640 "$ENV_FILE"
runuser -u "$USER_ID" -- test -r "$PW_FILE"
runuser -u "$USER_ID" -- test -r "$ENV_FILE"
runuser -u "$USER_ID" -- test -w /var/lib/netcup-magento-mcp

echo '==> Installing exact sudo helper rule (no unrestricted passwordless sudo)'
printf '%s\n' "$USER_ID ALL=(root) NOPASSWD: /usr/bin/python3 -I $ROOT/root_helper.py" > "$SUDOERS"
chown root:root "$SUDOERS"
chmod 0440 "$SUDOERS"
visudo -cf "$SUDOERS" >/dev/null

echo '==> Static check and actual root-helper smoke test'
"$ROOT/venv/bin/python" -m py_compile "$ROOT/server.py" "$ROOT/root_helper.py" "$ROOT/admin_executor.py" "$ROOT/source/packages/mcp_auth/private_oauth.py"
python3 - "$ROOT/server.py" <<'PY'
import ast, pathlib, sys
s=pathlib.Path(sys.argv[1]).read_text()
n=sum(isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and any(
 isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr=='tool'
 for d in x.decorator_list) for x in ast.walk(ast.parse(s)))
assert n==19, f'expected 19 tools, found {n}'
assert 'SERVER-NETCUP-MAGENTO' in s and 'SERVER-NETCUP-WORDPRESS' not in s
assert 'MAGENTO_MCP_AUTH_PACKAGES' in s and "'control.execute'" in s
print('STATIC_PASS: 19 tools, unique target, canonical OAuth')
PY
SMOKE="$(sudo -u "$USER_ID" sudo -n /usr/bin/python3 -I "$ROOT/root_helper.py" <<<'{"operation":"run","request_id":"MAGENTO-INSTALL-01234567890123456789","argv":["/usr/bin/id","-u"],"cwd":"/","timeout_seconds":15}')"
printf '%s' "$SMOKE" | python3 -c 'import json,sys; r=json.load(sys.stdin); assert r.get("status")=="PASS" and r.get("stdout","").strip()=="0", "no verified root"; print("HELPER_PASS: root uid=0")'

echo '==> Creating Netcup Magento MCP systemd service'
cat > "/etc/systemd/system/$UNIT" <<EOF
[Unit]
Description=Netcup Magento Server MCP - direct authorized admin, not Brain deploy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_ID
Group=$USER_ID
WorkingDirectory=$ROOT
EnvironmentFile=$ENV_FILE
ExecStart=$ROOT/venv/bin/python $ROOT/server.py
Restart=always
RestartSec=3
RuntimeMaxSec=infinity
ProtectHome=no
PrivateTmp=yes
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 "/etc/systemd/system/$UNIT"
systemctl daemon-reload
systemctl enable --now "$UNIT"
RESULT=''
for i in $(seq 1 30); do
    RESULT="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 -H 'Accept: text/event-stream, application/json' http://127.0.0.1:18793/mcp || true)"
    [ "$RESULT" = 401 ] && break
    sleep 1
done
[ "$RESULT" = 401 ] || { systemctl status "$UNIT" --no-pager | head -25 || true; echo "FAIL_CLOSED: expected HTTP 401, got $RESULT" >&2; exit 1; }
systemctl is-active --quiet "$UNIT"
echo "LOCAL_INSTALL_PASS: SERVER-NETCUP-MAGENTO"
echo "Pinned source SHA: $SHA"
echo "Service: $UNIT"
echo 'Root helper: PASS; 19 tools: PASS; anonymous local MCP: 401 PASS'
echo 'Bind: 127.0.0.1:18793 only'
echo "Future HTTPS endpoint: https://$DOMAIN/mcp (not connected yet)"
echo "Private login password file: $PW_FILE (never share in chat)"
echo 'NO SSH/FIREWALL/TAILSCALE/DNS changes. Next: independent Cloudflare Tunnel + OAuth plugin acceptance.'
