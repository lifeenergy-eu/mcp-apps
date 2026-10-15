#!/usr/bin/env bash
set -Eeuo pipefail
# Full offline and encrypted Wazuh snapshot, independent of legacy P620 backups.
BASE=/opt/p620-wazuh
RUN="$BASE/runtime"
OVERLAY="$BASE/docker-compose.private.yml"
REPO="$BASE/portable-restic-repository"
KEY="$BASE/secrets/restic-portable-password"
LABEL=p620-wazuh
LOCK="$BASE/.backup.lock"
[[ $EUID -eq 0 ]] || { echo ROOT_REQUIRED; exit 2; }
exec 9>"$LOCK"
flock -n 9 || { echo BACKUP_ALREADY_RUNNING; exit 2; }
for file in "$RUN/docker-compose.yml" "$OVERLAY" "$BASE/secrets/credentials.json"; do
 [[ -f "$file" ]] || { echo "MISSING_CONFIG $file"; exit 2; }
done
[[ -d /var/lib/docker/volumes/runtime_wazuh_queue/_data ]] || { echo VOLUME_MISSING; exit 2; }
install -d -m 0700 "$BASE/secrets" "$REPO"
if [[ ! -s $KEY ]]; then
    umask 077
    /usr/bin/openssl rand -base64 48 > "$KEY"
fi
chmod 600 "$KEY"
export RESTIC_REPOSITORY="$REPO" RESTIC_PASSWORD_FILE="$KEY"
if [[ ! -f "$REPO/config" ]]; then restic init >/dev/null; fi
function compose() {
   /usr/bin/docker compose -f "$RUN/docker-compose.yml" -f "$OVERLAY" "$@"
}
RESTART_NEEDED=0
function ensure_started() {
   if [[ $RESTART_NEEDED == 1 ]]; then
      echo WAZUH_RESTARTING
      if compose up -d --quiet-pull; then echo WAZUH_RESTARTED; else echo WAZUH_RESTART_FAILED >&2; fi
   fi
}
trap ensure_started EXIT
echo WAZUH_STOPPING_FOR_CONSISTENT_SNAPSHOT
RESTART_NEEDED=1
compose stop --timeout 35
echo WAZUH_RESTIC_SNAPSHOT_START
# Include precise compose runtime, certs, local-only secrets and named Docker volumes.
# Containers are stopped to ensure indexer DB snapshot consistency.
RESTIC_PATHS=(
 "$RUN"
 "$OVERLAY"
 "$BASE/secrets"
)
for vol in /var/lib/docker/volumes/runtime_*; do
  [[ -d "$vol/_data" ]] && RESTIC_PATHS+=("$vol/_data")
done
restic backup --tag "$LABEL" --compression auto --exclude='**/__pycache__/**' "${RESTIC_PATHS[@]}"
echo WAZUH_RESTIC_SNAPSHOT_FINISHED
restic snapshots --tag "$LABEL" --json | /usr/bin/python3 -c 'import json,sys;x=json.load(sys.stdin); print("SNAPSHOT_COUNT",len(x)); print("LATEST_SNAPSHOT_ID",x[-1]["short_id"] if x else "NONE")'
# Do not prune automatically, protect historic snapshots.
