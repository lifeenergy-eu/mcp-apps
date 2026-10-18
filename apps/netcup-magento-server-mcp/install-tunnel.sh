#!/usr/bin/env bash
# Direct Netcup Magento tunnel bootstrap. Mirrors existing Netcup WordPress cloudflared.service.
# Execute ONLY on new Netcup Magento Ubuntu 24.04 host.
set -Eeuo pipefail
umask 077
[ "$(id -u)" -eq 0 ] || { echo 'FAIL_CLOSED: sudo required' >&2; exit 1; }
. /etc/os-release
[ "$ID" = ubuntu ] && [ "$VERSION_ID" = 24.04 ] || { echo 'FAIL_CLOSED: Ubuntu 24.04 required' >&2; exit 1; }
ip -4 -o address show scope global | grep -Fq '62.83.43.3/' || { echo 'FAIL_CLOSED: expected Magento host 62.83.43.3' >&2; exit 1; }
systemctl is-active --quiet netcup-magento-mcp.service || { echo 'FAIL_CLOSED: install Magento MCP first' >&2; exit 1; }
[ "$(curl -s --max-time 6 -o /dev/null -w '%{http_code}' http://127.0.0.1:18793/mcp)" = 401 ] || { echo 'FAIL_CLOSED: local MCP does not return OAuth HTTP 401' >&2; exit 1; }
[ ! -e /etc/cloudflared/token ] && [ ! -e /etc/systemd/system/cloudflared.service ] || { echo 'FAIL_CLOSED: cloudflared already configured; do not overwrite' >&2; exit 1; }

echo 'Installing cloudflared from the official signed Cloudflare APT repository'
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl
install -d -m 0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' > /etc/apt/sources.list.d/cloudflared.list
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends cloudflared
[ -x /usr/bin/cloudflared ] || { echo 'FAIL_CLOSED: cloudflared installation not complete' >&2; exit 1; }

echo
echo 'In Cloudflare Zero Trust > Networks > Tunnels > netcup-magento-server-mcp:'
echo 'Open Install connector and copy ONLY the tunnel TOKEN (not the entire command).'
echo 'Enter the token below. It is hidden; never send this token to ChatGPT.'
[ -r /dev/tty ] || { echo 'FAIL_CLOSED: interactive SSH terminal required' >&2; exit 1; }
read -r -s -p 'Tunnel token (hidden): ' TOKEN < /dev/tty
echo
[ "$(printf '%s' "$TOKEN" | wc -c)" -ge 70 ] || { echo 'FAIL_CLOSED: token too short or not provided' >&2; exit 1; }
install -d -o root -g root -m 0700 /etc/cloudflared
(umask 077; printf '%s' "$TOKEN" > /etc/cloudflared/token)
unset TOKEN
chmod 0600 /etc/cloudflared/token
chown root:root /etc/cloudflared/token

cat > /etc/systemd/system/cloudflared.service <<'EOF'
[Unit]
Description=Cloudflare Tunnel client
After=network-online.target
Wants=network-online.target

[Service]
TimeoutStartSec=15
Type=notify
ExecStart=/usr/bin/cloudflared --no-autoupdate tunnel run --token-file /etc/cloudflared/token
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF
chown root:root /etc/systemd/system/cloudflared.service
chmod 0644 /etc/systemd/system/cloudflared.service
systemctl daemon-reload
systemctl enable --now cloudflared.service

for i in $(seq 1 15); do
    systemctl is-active --quiet cloudflared.service && break
    sleep 2
done
systemctl is-active --quiet cloudflared.service || { systemctl status cloudflared.service --no-pager | head -20 || true; echo 'FAIL_CLOSED: cloudflared did not start' >&2; exit 1; }

echo 'TUNNEL_SERVICE_ACTIVE - await public metadata and OAuth verification'
echo 'No SSH/Tailscale/firewall settings changed.'
echo 'Report only these non-secret results:'
systemctl is-active cloudflared.service netcup-magento-mcp.service
for p in '/.well-known/oauth-authorization-server' '/.well-known/oauth-protected-resource/mcp' '/mcp'; do
    printf '%s -> ' "$p"
    curl -sS --connect-timeout 3 --max-time 8 -o /dev/null -w '%{http_code}\n' "https://magento-mcp.larimarcode.com$p" || true
done
