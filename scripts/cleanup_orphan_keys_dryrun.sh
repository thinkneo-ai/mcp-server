#!/bin/bash
# ThinkNEO Cleanup — DRYRUN mode
# Counts orphan auto-registered API keys that WOULD be deleted.
# Must run in DRYRUN for 7 days before activating real cleanup.
set -euo pipefail

LOG="/opt/backups/postgres/cleanup_dryrun.log"
log() { echo "[$(date -Iseconds)] $1" | tee -a "$LOG"; }

COUNT=$(sudo -u postgres psql -d thinkneo_mcp -t -c "
SELECT count(*) FROM api_keys
WHERE auto_registered = true
  AND created_at < NOW() - INTERVAL '30 days'
  AND last_used_at IS NULL;
" 2>/dev/null | tr -d ' ')

TOTAL=$(sudo -u postgres psql -d thinkneo_mcp -t -c "SELECT count(*) FROM api_keys;" 2>/dev/null | tr -d ' ')

log "DRYRUN: would delete ${COUNT:-0} orphan auto-registered keys (total keys: ${TOTAL:-?})"
