#!/bin/bash
# ThinkNEO Cleanup — REAL mode
# Deletes orphan auto-registered API keys older than 30 days with no usage.
# Only activate after 7 days of successful DRYRUN.
set -euo pipefail

LOG="/opt/backups/postgres/cleanup.log"
log() { echo "[$(date -Iseconds)] $1" | tee -a "$LOG"; }

DELETED=$(sudo -u postgres psql -d thinkneo_mcp -t -c "
DELETE FROM api_keys
WHERE auto_registered = true
  AND created_at < NOW() - INTERVAL '30 days'
  AND last_used_at IS NULL
RETURNING key_hash;
" 2>/dev/null | grep -c "." || echo 0)

TOTAL=$(sudo -u postgres psql -d thinkneo_mcp -t -c "SELECT count(*) FROM api_keys;" 2>/dev/null | tr -d ' ')

log "CLEANUP: deleted ${DELETED} orphan keys (remaining: ${TOTAL})"
