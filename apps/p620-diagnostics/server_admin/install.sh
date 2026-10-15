#!/usr/bin/env bash
set -euo pipefail
# Run in the root of an extracted/checked-out lifeenergy-eu/mcp-apps repository.
ROOT="$(pwd)"
test -f "$ROOT/apps/p620-diagnostics/server.py"
test -f "$ROOT/apps/p620-diagnostics/auth.py"
test -f "$ROOT/apps/p620-diagnostics/server_admin/admin_executor.py"
test -f "$ROOT/apps/p620-diagnostics/server_admin/root_helper.py"
SERVICE=project-brain-p620-mcp.service
CURRENT_DIR="$(systemctl show "$SERVICE" -p WorkingDirectory --value)"
test -d "$CURRENT_DIR"
test -d "$(dirname "$CURRENT_DIR")/packages"
test -x /srv/project-brain/mcp-apps/venv/bin/python
test -f /usr/local/libexec/p620-debug-read
/usr/bin/python3 -m py_compile "$ROOT/apps/p620-diagnostics/server.py" "$ROOT/apps/p620-diagnostics/server_admin/admin_executor.py" "$ROOT/apps/p620-diagnostics/server_admin/root_helper.py"
install -d -m 0755 /opt/p620-server-mcp/app /etc/systemd/system/"$SERVICE".d
if [ ! -e /opt/p620-server-mcp/packages ]; then
  ln -s "$(dirname "$CURRENT_DIR")/packages" /opt/p620-server-mcp/packages
fi
test -d /opt/p620-server-mcp/packages
install -m 0644 "$ROOT/apps/p620-diagnostics/server.py" /opt/p620-server-mcp/app/server.py
install -m 0644 "$ROOT/apps/p620-diagnostics/auth.py" /opt/p620-server-mcp/app/auth.py
install -m 0644 "$ROOT/apps/p620-diagnostics/server_admin/admin_executor.py" /opt/p620-server-mcp/admin_executor.py
install -m 0644 "$ROOT/apps/p620-diagnostics/server_admin/root_helper.py" /opt/p620-server-mcp/root_helper.py
install -d -m 0700 /var/backups/p620-server-mcp
DATE="$(date +%Y%m%d%H%M%S)"
DROP="/etc/systemd/system/$SERVICE.d/90-p620-server-mcp.conf"
SUDOERS=/etc/sudoers.d/90-p620-server-mcp
if [ -f "$DROP" ]; then cp -p "$DROP" "/var/backups/p620-server-mcp/$DATE.conf"; fi
if [ -f "$SUDOERS" ]; then cp -p "$SUDOERS" "/var/backups/p620-server-mcp/$DATE.sudoers"; fi
cat > "$SUDOERS" <<'RULE'
p620 ALL=(root) NOPASSWD: /usr/bin/python3 -I /opt/p620-server-mcp/root_helper.py
RULE
chmod 0440 "$SUDOERS"
/usr/sbin/visudo -cf "$SUDOERS"
cat > "$DROP" <<'UNIT'
[Service]
WorkingDirectory=/opt/p620-server-mcp/app
ExecStart=
ExecStart=/srv/project-brain/mcp-apps/venv/bin/python /opt/p620-server-mcp/app/server.py
Environment=MCP_OAUTH_SCOPES=infra.read,control.execute
Restart=always
RestartSec=3
UNIT
chmod 0644 "$DROP"
systemctl daemon-reload
systemctl restart "$SERVICE"
sleep 3
if ! systemctl is-active --quiet "$SERVICE"; then
  echo "SERVICE_FAILED: inspect journalctl -u $SERVICE -n 35"
  exit 1
fi
echo "P620_SERVER_MCP_ACTIVE"
systemctl show "$SERVICE" -p ActiveState -p UnitFileState -p WorkingDirectory
echo "Previous OAuth endpoint retained. Refresh existing ChatGPT plugin and reauthorize control.execute."
echo "Existing Brain execution MCP NOT MODIFIED."
