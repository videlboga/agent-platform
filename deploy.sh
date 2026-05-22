#!/usr/bin/env bash
# Agent Platform — Deploy Critical Alerts Stack
# Usage: ./deploy.sh [--dry-run]
# Run from repo root on control-plane (85.9.211.227)

set -euo pipefail

DRY_RUN="${1:-}"

if [ "${DRY_RUN}" = "--dry-run" ]; then
    echo "[DRY RUN] Would execute the following:"
    DRY="echo"
else
    DRY=""
fi

AGENT_PLATFORM_DIR="/opt/agent-platform"

# ── 1. Copy new files ────────────────────────────────────────────

echo "==> Installing monitoring configs..."
${DRY} mkdir -p ${AGENT_PLATFORM_DIR}/configs/monitoring/alerts
${DRY} cp -v monitoring/prometheus.yml ${AGENT_PLATFORM_DIR}/configs/monitoring/
${DRY} cp -v monitoring/alerts/*.yml ${AGENT_PLATFORM_DIR}/configs/monitoring/alerts/
${DRY} cp -v monitoring/alertmanager.yml ${AGENT_PLATFORM_DIR}/configs/monitoring/

echo "==> Installing health-check server..."
${DRY} cp -rv health-check ${AGENT_PLATFORM_DIR}/

echo "==> Installing cron dispatcher..."
${DRY} mkdir -p ${AGENT_PLATFORM_DIR}/cron-dispatcher
${DRY} cp -v cron-dispatcher/cron_dispatcher.py ${AGENT_PLATFORM_DIR}/cron-dispatcher/
${DRY} chmod +x ${AGENT_PLATFORM_DIR}/cron-dispatcher/cron_dispatcher.py

# ── 2. Update docker-compose ─────────────────────────────────────

echo "==> Updating docker-compose.yml..."
${DRY} cp -v docker-compose.yml ${AGENT_PLATFORM_DIR}/docker-compose.yml

# ── 3. Build & start services ────────────────────────────────────

echo "==> Rebuilding and starting Docker services..."
${DRY} cd ${AGENT_PLATFORM_DIR}
${DRY} docker compose up -d --build

# ── 4. Wait for health check ────────────────────────────────────

echo "==> Waiting for health-check..."
for i in $(seq 1 15); do
    if curl -sf http://127.0.0.1:9100/health > /dev/null 2>&1; then
        echo "health-check is UP"
        break
    fi
    sleep 2
done

# Check all services
echo "==> Checking Prometheus..."
if curl -sf http://127.0.0.1:9090/-/healthy > /dev/null 2>&1; then
    echo "Prometheus is UP"
else
    echo "WARNING: Prometheus not reachable"
fi

echo "==> Checking Alertmanager..."
if curl -sf http://127.0.0.1:9093/-/healthy > /dev/null 2>&1; then
    echo "Alertmanager is UP"
else
    echo "WARNING: Alertmanager not reachable"
fi

# ── 5. Set up system cron for dispatcher ─────────────────────────

echo "==> Setting up system cron for dispatcher..."
CRON_JOB="* * * * * cd /opt/agent-platform && python3 cron-dispatcher/cron_dispatcher.py >> /opt/agent-platform/logs/dispatcher.cron.log 2>&1"
if [ -z "${DRY}" ]; then
    # Add to root's crontab (preserve existing, no duplicates)
    (crontab -l 2>/dev/null | grep -v "cron_dispatcher" ; echo "${CRON_JOB}") | crontab -
    echo "Cron entry added"
else
    echo "[DRY] Would add: ${CRON_JOB}"
fi

# ── 6. Verify ────────────────────────────────────────────────────

echo ""
echo "==> Verification: docker compose ps"
${DRY} docker compose -f ${AGENT_PLATFORM_DIR}/docker-compose.yml ps

echo ""
echo "==> Verification: /health endpoint"
${DRY} curl -s http://127.0.0.1:9100/health | python3 -m json.tool

echo ""
echo "=== Deploy complete ==="
echo "Prometheus:    http://127.0.0.1:9090"
echo "Alertmanager:  http://127.0.0.1:9093"
echo "Health check:  http://127.0.0.1:9100/health"
echo ""
echo "Alert rules:  ${AGENT_PLATFORM_DIR}/configs/monitoring/alerts/critical.yml"
echo "Cron log:     /opt/agent-platform/logs/dispatcher.cron.log"
