#!/bin/bash
# ThinkNEO Weekly Backup Restoration Test
# Validates backup integrity by restoring to isolated temp container.
# Schedule: Sunday 04:00 UTC (after daily backup at 03:00)
set -euo pipefail

BACKUP_DIR="/opt/backups/postgres"
LOG_FILE="${BACKUP_DIR}/restore_test.log"
TEMP_CONTAINER="pg-restore-test"
TEMP_PORT=15432
RESEND_API_KEY=$(grep RESEND_API_KEY /opt/thinkneo-mcp-server/.env 2>/dev/null | cut -d= -f2 || echo "")

log() { echo "[$(date -Iseconds)] $1" | tee -a "$LOG_FILE"; }
alert() {
    log "ALERT: $1"
    if [ -n "$RESEND_API_KEY" ]; then
        curl -sS -X POST "https://api.resend.com/emails" \
            -H "Authorization: Bearer $RESEND_API_KEY" \
            -H "Content-Type: application/json" \
            -d "{\"from\":\"ThinkNEO Backup <no-reply@thinkneo.ai>\",\"to\":[\"security@thinkneo.ai\"],\"subject\":\"BACKUP RESTORE TEST FAILED\",\"text\":\"$1\"}" \
            >/dev/null 2>&1 || true
    fi
}

cleanup() {
    log "Cleanup: removing temp container"
    docker rm -f "$TEMP_CONTAINER" 2>/dev/null || true
}
trap cleanup EXIT

log "=========================================="
log "Starting backup restoration test"
START_TIME=$(date +%s)

# 1. Find latest host backup
LATEST_HOST=$(ls -t "${BACKUP_DIR}"/host_pg_*.sql.gz 2>/dev/null | head -1)
if [ -z "$LATEST_HOST" ]; then
    alert "No host backup found in ${BACKUP_DIR}!"
    exit 1
fi
BACKUP_DATE=$(basename "$LATEST_HOST" | sed 's/host_pg_//;s/.sql.gz//')
log "Using backup: ${LATEST_HOST} (date: ${BACKUP_DATE})"

# 2. Verify backup integrity
if ! gzip -t "$LATEST_HOST" 2>/dev/null; then
    alert "Backup file corrupted: ${LATEST_HOST}"
    exit 1
fi
log "Integrity check: PASS"

# 3. Start temp PostgreSQL container
log "Starting temp PostgreSQL container on port ${TEMP_PORT}..."
docker run -d --name "$TEMP_CONTAINER" \
    -e POSTGRES_PASSWORD=restore_test_pw \
    -e POSTGRES_HOST_AUTH_METHOD=trust \
    -p "127.0.0.1:${TEMP_PORT}:5432" \
    --memory=512m --cpus=1 \
    postgres:16-alpine \
    >/dev/null 2>&1

# Wait for postgres to be ready
for i in $(seq 1 30); do
    if docker exec "$TEMP_CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! docker exec "$TEMP_CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
    alert "Temp PostgreSQL failed to start"
    exit 1
fi
log "Temp PostgreSQL ready"

# 4. Restore backup
log "Restoring backup (this may take a minute)..."
RESTORE_START=$(date +%s)
if gunzip -c "$LATEST_HOST" | docker exec -i "$TEMP_CONTAINER" psql -U postgres >/dev/null 2>&1; then
    RESTORE_END=$(date +%s)
    RESTORE_TIME=$((RESTORE_END - RESTORE_START))
    log "Restore complete in ${RESTORE_TIME}s"
else
    alert "Backup restore FAILED for ${LATEST_HOST}"
    log "Preserving temp container for debug"
    trap - EXIT
    exit 1
fi

# 5. Validate restored data
log "Validating restored data..."
ERRORS=0

# 5a. Check thinkneo_mcp database exists
if ! docker exec "$TEMP_CONTAINER" psql -U postgres -d thinkneo_mcp -c "SELECT 1" >/dev/null 2>&1; then
    log "  FAIL: thinkneo_mcp database not found"
    ERRORS=$((ERRORS + 1))
else
    log "  thinkneo_mcp database: EXISTS"
fi

# 5b. Check critical tables
for tbl in api_keys usage_log rate_limit_events revoked_keys oauth_clients a2a_interactions policies mcp_registry outcome_claims; do
    COUNT=$(docker exec "$TEMP_CONTAINER" psql -U postgres -d thinkneo_mcp -t -c "SELECT count(*) FROM ${tbl};" 2>/dev/null | tr -d ' ')
    if [ -z "$COUNT" ] || [ "$COUNT" = "" ]; then
        log "  FAIL: table ${tbl} not found"
        ERRORS=$((ERRORS + 1))
    else
        log "  OK: ${tbl} = ${COUNT} rows"
    fi
done

# 5c. Compare key counts with live DB
LIVE_KEYS=$(sudo -u postgres psql -d thinkneo_mcp -t -c "SELECT count(*) FROM api_keys;" 2>/dev/null | tr -d ' ')
RESTORED_KEYS=$(docker exec "$TEMP_CONTAINER" psql -U postgres -d thinkneo_mcp -t -c "SELECT count(*) FROM api_keys;" 2>/dev/null | tr -d ' ')
log "  api_keys: live=${LIVE_KEYS} restored=${RESTORED_KEYS}"

LIVE_USAGE=$(sudo -u postgres psql -d thinkneo_mcp -t -c "SELECT count(*) FROM usage_log;" 2>/dev/null | tr -d ' ')
RESTORED_USAGE=$(docker exec "$TEMP_CONTAINER" psql -U postgres -d thinkneo_mcp -t -c "SELECT count(*) FROM usage_log;" 2>/dev/null | tr -d ' ')
log "  usage_log: live=${LIVE_USAGE} restored=${RESTORED_USAGE}"

# 5d. FK integrity
FK_ERRORS=$(docker exec "$TEMP_CONTAINER" psql -U postgres -d thinkneo_mcp -t -c "
SELECT count(*) FROM usage_log u
LEFT JOIN api_keys a ON u.key_hash = a.key_hash
WHERE a.key_hash IS NULL AND u.key_hash != 'anonymous';
" 2>/dev/null | tr -d ' ')
if [ "${FK_ERRORS:-0}" -gt 0 ]; then
    log "  WARN: ${FK_ERRORS} orphaned usage_log entries"
else
    log "  FK integrity: PASS"
fi

# 6. Results
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

log ""
log "=========================================="
if [ $ERRORS -eq 0 ]; then
    log "RESULT: PASS"
else
    log "RESULT: FAIL (${ERRORS} errors)"
fi
log "  RTO (restore time): ${RESTORE_TIME}s"
log "  RPO (backup age): ${BACKUP_DATE}"
log "  Total test time: ${TOTAL_TIME}s"
log "=========================================="

if [ $ERRORS -gt 0 ]; then
    alert "Backup restore test had ${ERRORS} errors. Check ${LOG_FILE}"
    trap - EXIT
    exit 1
fi

log "Test PASSED — cleaning up"
