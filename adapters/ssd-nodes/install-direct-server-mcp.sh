#!/usr/bin/env bash
# SSD Nodes / brain-ssd-fra01: direct Server MCP bootstrap from pinned GitHub source.
# Requires current root SSH session. Does not modify SSH authorization or firewall.
set -Eeuo pipefail
umask 077
export DEBIAN_FRONTEND=noninteractive
SOURCE_SHA="672339c1940639996620fb65af43092de6538cfb"
IP="209.182.239.112"
DOMAIN="209-182-239-112.sslip.io"
PUBLIC_URL="https://$DOMAIN"
BASE="/opt/ssd-server-mcp"
PORT="18795"
SERVICE="ssd-server-mcp.service"
LOG="/var/log/ssd-server-mcp-install.log"
msg(){ printf '\n== %s ==\n' "$*"; }
die(){ echo "INSTALL_FAILED: $*" >&2; exit 1; }
trap 'echo "ERROR near line $LINENO; check $LOG and journalctl -u ssd-server-mcp" >&2' ERR
[[ "$(id -u)" = 0 ]] || die "Root login required"
grep -q 'ID=ubuntu' /etc/os-release || die "Expected Ubuntu"
grep -q 'VERSION_ID="24.04"' /etc/os-release || die "Expected Ubuntu 24.04"
[[ "$(hostname -s)" == "brain-ssd-fra01" ]] || die "Wrong hostname"
ip -4 -o addr show | grep -Fq "$IP/" || die "Expected IPv4 not assigned"
getent ahostsv4 "$DOMAIN" | awk '{print $1}' | grep -Fxq "$IP" || die "Public DNS mismatch"
[[ ! -e "$BASE/app/server.py" ]] || die "MCP already installed: do not overwrite"
[[ -z "$(ss -lnt '( sport = :80 or sport = :443 or sport = :18795 )' | sed -n '2,$p')" ]] || die "Port 80/443/18795 already in use"
touch "$LOG"; chmod 600 "$LOG"
msg "Install prerequisites and Caddy"
apt-get update -qq >>"$LOG" 2>&1
apt-get install -y -qq --no-install-recommends git caddy python3-venv python3-pip sudo curl ca-certificates openssl sqlite3 >>"$LOG" 2>&1
msg "Download and verify exact mcp-apps source $SOURCE_SHA"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone --quiet https://github.com/lifeenergy-eu/mcp-apps.git "$TMP/repo" 2>>"$LOG"
git -C "$TMP/repo" checkout --quiet --detach "$SOURCE_SHA" 2>>"$LOG"
[[ "$(git -C "$TMP/repo" rev-parse HEAD)" == "$SOURCE_SHA" ]] || die "Source SHA mismatch"
SRC="$TMP/repo"
for f in apps/p620-diagnostics/server.py apps/p620-diagnostics/server_admin/root_helper.py apps/p620-diagnostics/server_admin/admin_executor.py apps/p620-diagnostics/requirements.txt packages/mcp_auth/private_oauth.py packages/mcp_auth/__init__.py; do
  [[ -f "$SRC/$f" ]] || die "Source missing: $f"
done
msg "Create dedicated MCP user, application and fresh local OAuth credentials"
id ssd-mcp >/dev/null 2>&1 || useradd --system --user-group --home-dir /var/lib/ssd-server-mcp --shell /usr/sbin/nologin ssd-mcp
install -d -o root -g root -m 0755 "$BASE" "$BASE/app" "$BASE/packages"
install -d -o ssd-mcp -g ssd-mcp -m 0700 /var/lib/ssd-server-mcp /var/lib/ssd-server-mcp/secrets
install -d -o root -g root -m 0700 /etc/ssd-server-mcp
if [[ ! -e /var/lib/ssd-server-mcp/secrets/operator-password ]]; then
  python3 -c "import secrets,pathlib;p=pathlib.Path('/var/lib/ssd-server-mcp/secrets/operator-password');p.write_text(secrets.token_urlsafe(32)+'\n')"
  chown ssd-mcp:ssd-mcp /var/lib/ssd-server-mcp/secrets/operator-password
  chmod 0400 /var/lib/ssd-server-mcp/secrets/operator-password
fi
cp -a "$SRC/packages/mcp_auth" "$BASE/packages/"
python3 -m venv "$BASE/venv"
"$BASE/venv/bin/pip" -q install --disable-pip-version-check -r "$SRC/apps/p620-diagnostics/requirements.txt" >>"$LOG" 2>&1
install -m 0644 "$SRC/apps/p620-diagnostics/server.py" "$BASE/app/server.py"
install -m 0644 "$SRC/apps/p620-diagnostics/server_admin/root_helper.py" "$BASE/root_helper.py"
install -m 0644 "$SRC/apps/p620-diagnostics/server_admin/admin_executor.py" "$BASE/admin_executor.py"
msg "Generate SSD-specific adapter from verified P620 interface without copying target identity"
SSD_BASE="$BASE" SSD_PORT="$PORT" python3 - <<'PY'
import os
from pathlib import Path
root=Path(os.environ["SSD_BASE"]); port=os.environ["SSD_PORT"]
p=root/"app/server.py"; s=p.read_text()
changes=[
("P620_MCP_AUTH_PACKAGES","SSD_MCP_AUTH_PACKAGES"),
("assert PORT == 8792","assert PORT == "+port),
("os.environ.get('MCP_BIND_PORT','8792')","os.environ.get('MCP_BIND_PORT','"+port+"')"),
("/opt/p620-server-mcp/root_helper.py",str(root/"root_helper.py")),
("return {'target_id':'SERVER-NETCUP-WORDPRESS'","return {'target_id':'SERVER-SSD-NODES-BRAIN'"),
]
for a,b in changes:
    if a not in s: raise SystemExit("SOURCE_TEMPLATE_MISMATCH: "+a)
    s=s.replace(a,b)
s=s.replace("P620","SSD Nodes")
if "SERVER-NETCUP-WORDPRESS" in s or "assert PORT == 8792" in s:
    raise SystemExit("TARGET_IDENTITY_NOT_REPLACED")
p.write_text(s)
p=root/"root_helper.py"; t=p.read_text()
if "/opt/p620-server-mcp" not in t: raise SystemExit("ROOT_HELPER_TEMPLATE_MISMATCH")
p.write_text(t.replace("/opt/p620-server-mcp",str(root)).replace("p620-migration-mcp","ssd-server-mcp"))
p=root/"admin_executor.py";p.write_text(p.read_text().replace(".p620-write-",".ssd-write-"))
PY
chown -R root:root "$BASE/app" "$BASE/packages" "$BASE/root_helper.py" "$BASE/admin_executor.py"
chmod 0644 "$BASE/app/server.py" "$BASE/root_helper.py" "$BASE/admin_executor.py"
"$BASE/venv/bin/python" -m py_compile "$BASE/app/server.py" "$BASE/root_helper.py" "$BASE/admin_executor.py" "$BASE/packages/mcp_auth/private_oauth.py"
msg "Configure private OAuth and target-bound privileged helper"
cat > /etc/ssd-server-mcp/config.env <<ENV
MCP_BIND_PORT=$PORT
MCP_PUBLIC_HOST=$DOMAIN
SSD_MCP_AUTH_PACKAGES=$BASE/packages
MCP_AUTH_MODE=oauth_private
MCP_OAUTH_SCOPES=control.execute
MCP_OAUTH_REQUIRED_SCOPES=control.execute
MCP_OAUTH_ISSUER_URL=$PUBLIC_URL
MCP_OAUTH_RESOURCE_URL=$PUBLIC_URL/mcp
MCP_OAUTH_DB_PATH=/var/lib/ssd-server-mcp/oauth.sqlite3
MCP_OAUTH_PASSWORD_FILE=/var/lib/ssd-server-mcp/secrets/operator-password
MCP_OAUTH_PRODUCT_NAME=SSD Nodes Server MCP
MCP_OAUTH_LOGIN_DESCRIPTION=Authorize private administration of brain-ssd-fra01.
ENV
chmod 0600 /etc/ssd-server-mcp/config.env
cat > /etc/sudoers.d/90-ssd-server-mcp <<'SUDO'
ssd-mcp ALL=(root) NOPASSWD: /usr/bin/python3 -I /opt/ssd-server-mcp/root_helper.py
SUDO
chmod 0440 /etc/sudoers.d/90-ssd-server-mcp
visudo -cf /etc/sudoers.d/90-ssd-server-mcp >/dev/null
cat > /etc/systemd/system/ssd-server-mcp.service <<UNIT
[Unit]
Description=SSD Nodes Direct Server MCP (private OAuth)
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=ssd-mcp
Group=ssd-mcp
WorkingDirectory=$BASE/app
EnvironmentFile=/etc/ssd-server-mcp/config.env
ExecStart=$BASE/venv/bin/python $BASE/app/server.py
UMask=0077
Restart=always
RestartSec=3
TimeoutStartSec=90
[Install]
WantedBy=multi-user.target
UNIT
if [[ -f /etc/caddy/Caddyfile ]] && grep -Eq 'reverse_proxy|tls |import |^[[:space:]]*[a-zA-Z0-9.-]+\.[a-zA-Z]+' /etc/caddy/Caddyfile; then
 die "Existing custom Caddy configuration detected; review before replacing"
fi
cp -p /etc/caddy/Caddyfile /etc/caddy/Caddyfile.before-ssd-mcp 2>/dev/null || :
cat > /etc/caddy/Caddyfile <<CADDY
# PROJECT-BRAIN-SSD-SERVER-MCP
$DOMAIN {
  encode gzip
  reverse_proxy 127.0.0.1:$PORT
}
CADDY
chmod 0644 /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile >>"$LOG" 2>&1 || die "Caddy config invalid"
msg "Start authenticated MCP service and HTTPS"
systemctl daemon-reload
systemctl enable --now ssd-server-mcp.service >>"$LOG" 2>&1
sleep 3
systemctl is-active --quiet ssd-server-mcp.service || { journalctl -u ssd-server-mcp -n 25 --no-pager; die "MCP service not active"; }
systemctl enable caddy >>"$LOG" 2>&1
systemctl restart caddy >>"$LOG" 2>&1
systemctl is-active --quiet caddy || die "HTTPS proxy not active"
msg "Verify OAuth discovery and refusal of unauthenticated administration"
local_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:$PORT/mcp)"
[[ "$local_code" == "401" ]] || die "Local unauthenticated MCP must return 401, got $local_code"
http_code=000
for attempt in $(seq 1 12); do
 http_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$PUBLIC_URL/.well-known/oauth-authorization-server" || :)"
 [[ "$http_code" == "200" ]] && break
 sleep 5
done
[[ "$http_code" == "200" ]] || { journalctl -u caddy -n 22 --no-pager; die "External HTTPS OAuth metadata not ready ($http_code): verify provider permits TCP 80/443"; }
remote_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$PUBLIC_URL/mcp")"
[[ "$remote_code" == "401" ]] || die "Public unauthenticated MCP must return 401, got $remote_code"
msg "SSD_SERVER_MCP_BOOTSTRAP_PASS"
echo "target_id=SERVER-SSD-NODES-BRAIN"
echo "source_sha=$SOURCE_SHA"
echo "service=ssd-server-mcp.service"
echo "mcp_url=$PUBLIC_URL/mcp"
echo "Operator password is stored locally at /var/lib/ssd-server-mcp/secrets/operator-password; do NOT paste into chat."
echo "Next: connect this MCP URL to ChatGPT Plugins and authorize privately; after connection perform full connector_health and read/write checks."
echo "No production Brain migration, SSH or firewall mutation was performed."
