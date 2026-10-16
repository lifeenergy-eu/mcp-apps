#!/usr/bin/env bash
# Non-mutating initial acceptance / diagnostics for a newly provisioned SSD Nodes server.
set -uo pipefail
export LC_ALL=C
IP="209.182.239.112"
HOST="${SSD_MCP_HOST:-209-182-239-112.sslip.io}"
say(){ printf '\n== %s ==\n' "$*"; }
check(){ if "$@" >/dev/null 2>&1; then echo "PASS $*"; else echo "WARN $*"; fi; }
say "SSD NODES BRain / read-only preflight"; date -u '+UTC %FT%TZ'
printf 'host='; hostname
printf 'user='; id -un
printf 'uid='; id -u
say "OS / CPU / RAM / storage"
sed -n '/^PRETTY_NAME=/p' /etc/os-release 2>/dev/null
uname -rm
command -v nproc >/dev/null && nproc
command -v free >/dev/null && free -h
df -hT / || :
command -v lsblk >/dev/null && lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS || :
say "Network / DNS"
ip -brief address 2>/dev/null | head -15 || :
ip route get 1.1.1.1 2>/dev/null | head -1 || :
printf 'expected_ipv4=%s\nexternal_dns_host=%s\n' "$IP" "$HOST"
getent ahostsv4 "$HOST" 2>/dev/null | head -3 || :
if getent ahostsv4 "$HOST" 2>/dev/null | awk '{print $1}' | grep -Fxq "$IP"; then echo "PASS DNS resolves to configured IP"; else echo "WARN DNS does not resolve to configured IP"; fi
say "Connectivity"
for u in https://raw.githubusercontent.com/ https://github.com/ https://pypi.org/simple/mcp/ https://acme-v02.api.letsencrypt.org/directory; do
   printf '%s => ' "$u"
   curl -ILsS -o /dev/null --max-time 8 -w '%{http_code}\n' "$u" 2>/dev/null || echo TIMEOUT_OR_BLOCKED
done
say "Listening TCP ports and firewall status"
ss -lnt 2>/dev/null | head -25 || :
if command -v ufw >/dev/null; then ufw status 2>/dev/null | head -12 || :; else echo 'UFW not installed'; fi
command -v nft >/dev/null && nft list tables 2>/dev/null | head -15 || :
say "System services / prerequisites"
for x in python3 git curl sudo caddy systemctl tailscale; do
 if command -v "$x" >/dev/null; then printf 'PRESENT %s %s\n' "$x" "$(command -v "$x")"; else echo "MISSING $x"; fi
done
check systemctl is-system-running --wait
if [ -f /root/.ssh/authorized_keys ]; then echo 'PASS /root/.ssh/authorized_keys exists (contents not printed)'; else echo 'WARN root authorized_keys missing (login may use provider access)'; fi
say "Existing MCP / web service guard"
for s in ssd-server-mcp.service caddy.service nginx.service apache2.service; do
  a=$(systemctl is-active "$s" 2>/dev/null || :); echo "$s = ${a:-absent}"
done
if [ -d /opt/ssd-server-mcp ]; then echo 'WARN /opt/ssd-server-mcp already present; installer should preserve/reconcile state'; else echo 'PASS No previous SSD MCP installation'; fi
say "RESULT"
echo 'Preflight complete. No writes performed. Copy this result to ChatGPT; do not share private keys or passwords.'
