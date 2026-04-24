#!/usr/bin/env bash
#
# Boot test for self-hosted Docker Compose deployment.
# Validates: containers start, health checks pass, MCP responds.
#
# Usage: ./tests/deploy/test_docker_compose_boot.sh
# Exit: 0 = success, 1 = failure

set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")/../../deploy" && pwd)"
PASS=0
FAIL=0

check() {
    if [ "$2" = "OK" ]; then
        echo "  ✅ $1"
        PASS=$((PASS+1))
    else
        echo "  ❌ $1 — $2"
        FAIL=$((FAIL+1))
    fi
}

echo "=== Self-Hosted Boot Test ==="
echo "Deploy dir: $DEPLOY_DIR"
echo ""

# Clean up any existing containers
cd "$DEPLOY_DIR"
docker compose down -v 2>/dev/null || true

# Start
echo "Starting containers..."
docker compose up -d --build 2>&1 | tail -5

# Wait for health
echo "Waiting for health (max 60s)..."
for i in $(seq 1 60); do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' thinkneo-gateway 2>/dev/null || echo "starting")
    if [ "$STATUS" = "healthy" ]; then
        echo "  Gateway healthy after ${i}s"
        break
    fi
    sleep 1
done

# Tests
echo ""
echo "Running checks..."

# Container running
GATEWAY=$(docker inspect --format='{{.State.Status}}' thinkneo-gateway 2>/dev/null || echo "not found")
[ "$GATEWAY" = "running" ] && check "Gateway container" "OK" || check "Gateway container" "$GATEWAY"

POSTGRES=$(docker inspect --format='{{.State.Status}}' thinkneo-postgres 2>/dev/null || echo "not found")
[ "$POSTGRES" = "running" ] && check "Postgres container" "OK" || check "Postgres container" "$POSTGRES"

# Health
HEALTH=$(docker inspect --format='{{.State.Health.Status}}' thinkneo-gateway 2>/dev/null || echo "unknown")
[ "$HEALTH" = "healthy" ] && check "Health check" "OK" || check "Health check" "$HEALTH"

# MCP endpoint
MCP=$(curl -sf --max-time 5 -o /dev/null -w "%{http_code}" http://localhost:8081/mcp/docs 2>/dev/null || echo "000")
[ "$MCP" = "200" ] && check "MCP docs" "OK" || check "MCP docs" "HTTP $MCP"

# Tool call
TOOL=$(curl -sf --max-time 10 \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    "http://localhost:8081/mcp" \
    -d '{"jsonrpc":"2.0","method":"tools/call","id":1,"params":{"name":"thinkneo_provider_status","arguments":{}}}' 2>/dev/null)
echo "$TOOL" | grep -q "content" && check "Tool call (provider_status)" "OK" || check "Tool call" "no response"

# Clean up
echo ""
echo "Cleaning up..."
docker compose down -v 2>/dev/null

echo ""
echo "=== Result: $PASS passed, $FAIL failed ==="
exit $FAIL
