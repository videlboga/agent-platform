#!/usr/bin/env python3
"""
Agent Platform — Cron Dispatcher
Lightweight scheduler for periodic platform tasks.
Replaces Celery-beat for resource-constrained 1-core VPS.

Tasks defined here run on schedule. Each task is a function:
  - name: human-readable
  - interval_seconds: how often to run
  - run(): do the work, return (success_bool, message_string)
  - timeout_seconds: max runtime per tick (default 30)

Usage:
  python3 cron_dispatcher.py           # run once (for cron)
  python3 cron_dispatcher.py --daemon  # run persistently (not recommended on 1-core)

Designed to be invoked by system cron every minute with --one-shot.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone


# ── Configuration ────────────────────────────────────────────────

HERMES_HOME = os.environ.get("HERMES_HOME", "/root/.hermes")
HEALTH_CHECK_URL = os.environ.get("HEALTH_CHECK_URL", "http://127.0.0.1:9100")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090")
DISPATCH_LOG = os.environ.get("DISPATCH_LOG", "/opt/agent-platform/logs/dispatcher.log")

os.makedirs(os.path.dirname(DISPATCH_LOG), exist_ok=True)


# ── Task: Kanban Dispatch ────────────────────────────────────────

def kanban_dispatch():
    """Run `hermes kanban dispatch` to process ready tasks."""
    try:
        result = subprocess.run(
            ["hermes", "kanban", "dispatch"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output.strip()[:500]
    except Exception as e:
        return False, str(e)


# ── Task: Health Check Verification ──────────────────────────────

def verify_health():
    """Ping health check server and report status."""
    try:
        resp = urllib.request.urlopen(f"{HEALTH_CHECK_URL}/health", timeout=10)
        data = json.loads(resp.read().decode())
        ok = data.get("status") == "ok"
        checks = data.get("checks", {})
        detail = "; ".join(f"{k}:{v}" for k, v in checks.items())
        return ok, detail
    except Exception as e:
        return False, str(e)


# ── Task: Prometheus Alert Check ──────────────────────────────────

def check_firing_alerts():
    """Check Prometheus for currently firing alerts."""
    try:
        resp = urllib.request.urlopen(f"{PROMETHEUS_URL}/api/v1/alerts", timeout=10)
        data = json.loads(resp.read().decode())
        alerts = data.get("data", {}).get("alerts", [])
        firing = [a for a in alerts if a.get("state") == "firing"]
        if firing:
            names = [a["labels"].get("alertname", "?") for a in firing]
            return False, f"Firing alerts: {', '.join(names)}"
        return True, "No firing alerts"
    except urllib.error.HTTPError as e:
        return False, f"Prometheus HTTP {e.code}"
    except Exception as e:
        return False, str(e)


# ── Task: Docker Service Health ──────────────────────────────────

def docker_service_check():
    """Verify all platform containers are running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}} {{.Status}}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return False, f"docker ps failed: {result.stderr.strip()}"
        lines = result.stdout.strip().split("\n")
        expected = ["postgres", "redis", "health-check", "prometheus", "alertmanager"]
        running = {line.split()[0] for line in lines if "Up" in line}
        missing = [s for s in expected if s not in running]
        if missing:
            return False, f"Missing containers: {', '.join(missing)}"
        return True, f"All {len(expected)} containers running"
    except Exception as e:
        return False, str(e)


# ── Task: Disk Cleanup ──────────────────────────────────────────

def disk_cleanup():
    """Prune unused Docker resources if disk >80%."""
    try:
        result = subprocess.run(
            ["df", "--output=pcent", "/"],
            capture_output=True, text=True, timeout=10,
        )
        pct_str = result.stdout.strip().split("\n")[-1].replace("%", "").strip()
        pct = int(pct_str)
        if pct > 80:
            prune = subprocess.run(
                ["docker", "system", "prune", "-af", "--filter", "until=24h"],
                capture_output=True, text=True, timeout=120,
            )
            msg = prune.stdout.strip()[:200] if prune.stdout else "pruned"
            return True, f"Disk at {pct}%; {msg}"
        return True, f"Disk at {pct}% — below threshold"
    except Exception as e:
        return False, str(e)


# ── Registry ──────────────────────────────────────────────────────

TASKS = [
    {
        "name": "kanban-dispatch",
        "interval_seconds": 60,
        "timeout_seconds": 60,
        "run": kanban_dispatch,
        "description": "Dispatch ready kanban tasks",
    },
    {
        "name": "verify-health",
        "interval_seconds": 60,
        "timeout_seconds": 15,
        "run": verify_health,
        "description": "Ping /health endpoint",
    },
    {
        "name": "check-alerts",
        "interval_seconds": 120,
        "timeout_seconds": 15,
        "run": check_firing_alerts,
        "description": "Check Prometheus firing alerts",
    },
    {
        "name": "docker-check",
        "interval_seconds": 300,
        "timeout_seconds": 20,
        "run": docker_service_check,
        "description": "Verify all containers are up",
    },
    {
        "name": "disk-cleanup",
        "interval_seconds": 3600,
        "timeout_seconds": 120,
        "run": disk_cleanup,
        "description": "Auto-clean Docker if disk >80%",
    },
]


# ── State tracking ──────────────────────────────────────────────

STATE_FILE = "/opt/agent-platform/configs/cron_state.json"


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Main ──────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    with open(DISPATCH_LOG, "a") as f:
        f.write(line + "\n")
    print(line)


def run_once(state):
    now = time.time()
    triggered = []

    for task_def in TASKS:
        name = task_def["name"]
        interval = task_def["interval_seconds"]
        last_run = state.get(name, 0)

        if now - last_run >= interval:
            state[name] = now
            log(f"Running: {name} ({task_def['description']})")
            try:
                ok, msg = task_def["run"]()
                status = "OK" if ok else "FAIL"
                log(f"  → {status}: {msg}")
                triggered.append((name, status, msg))
            except Exception as e:
                log(f"  → EXCEPTION: {e}")
                triggered.append((name, "EXCEPTION", str(e)))

    save_state(state)
    return triggered


def main():
    state = load_state()

    # Parse arguments
    if "--daemon" in sys.argv:
        log("Starting cron-dispatcher in daemon mode (sleep 60s between ticks)")
        while True:
            run_once(state)
            time.sleep(60)
    else:
        # One-shot mode for system cron
        run_once(state)
        log("One-shot complete")


if __name__ == "__main__":
    main()
