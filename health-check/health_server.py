#!/usr/bin/env python3
"""
Health check server for Agent Platform control-plane.
Endpoints:
  /health          — overall status
  /health/db       — PostgreSQL connectivity
  /health/redis    — Redis connectivity
  /health/system   — system metrics (disk, memory, CPU)
"""

import json
import os
import socket
import time
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PG_HOST = os.environ.get("PG_HOST", "postgres")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_USER = os.environ.get("PG_USER", "agent")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")
PG_DB = os.environ.get("PG_DB", "agent_platform")

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

START_TIME = time.time()


def tcp_check(host, port, timeout=3):
    """Simple TCP connect check."""
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True, ""
    except Exception as e:
        return False, str(e)


def pg_check():
    """Check PostgreSQL via pg_isready."""
    cmd = [
        "pg_isready",
        "-h", PG_HOST,
        "-p", str(PG_PORT),
        "-U", PG_USER,
        "-d", PG_DB,
        "-t", "3",
    ]
    env = os.environ.copy()
    if PG_PASSWORD:
        env["PGPASSWORD"] = PG_PASSWORD
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, env=env)
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def redis_check():
    """Check Redis via redis-cli PING."""
    cmd = ["redis-cli", "-h", REDIS_HOST, "-p", str(REDIS_PORT), "PING"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        return result.returncode == 0 and "PONG" in result.stdout, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def system_metrics():
    """Collect system metrics."""
    metrics: dict = {"uptime_seconds": int(time.time() - START_TIME)}

    # Disk
    try:
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=3)
        parts = r.stdout.strip().split("\n")[-1].split()
        metrics["disk_used_pct"] = parts[4].replace("%", "")
        metrics["disk_total"] = parts[1]
        metrics["disk_used"] = parts[2]
        metrics["disk_avail"] = parts[3]
    except Exception:
        metrics["disk_error"] = "df failed"

    # Memory
    try:
        with open("/proc/meminfo") as f:
            data = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    data[parts[0].strip()] = parts[1].strip()
            total_kb = int(data.get("MemTotal", "0").split()[0])
            avail_kb = int(data.get("MemAvailable", "0").split()[0])
            used_kb = total_kb - avail_kb
            metrics["mem_total_mb"] = round(total_kb / 1024, 1)
            metrics["mem_used_mb"] = round(used_kb / 1024, 1)
            metrics["mem_avail_mb"] = round(avail_kb / 1024, 1)
            metrics["mem_used_pct"] = round(used_kb / total_kb * 100, 1) if total_kb else 0
    except Exception:
        metrics["mem_error"] = "meminfo read failed"

    # CPU
    try:
        r = subprocess.run(["cat", "/proc/loadavg"], capture_output=True, text=True, timeout=3)
        parts = r.stdout.strip().split()
        metrics["load_1min"] = parts[0]
        metrics["load_5min"] = parts[1]
        metrics["load_15min"] = parts[2]
    except Exception:
        metrics["load_error"] = "loadavg read failed"

    # Swap
    try:
        r = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=3)
        for line in r.stdout.split("\n"):
            if line.startswith("Swap:"):
                parts = line.split()
                metrics["swap_total_mb"] = int(parts[1])
                metrics["swap_used_mb"] = int(parts[2])
                break
    except Exception:
        pass

    # Uptime
    try:
        r = subprocess.run(["cat", "/proc/uptime"], capture_output=True, text=True, timeout=3)
        metrics["system_uptime_seconds"] = int(float(r.stdout.strip().split()[0]))
    except Exception:
        pass

    return metrics


class HealthHandler(BaseHTTPRequestHandler):
    def _respond(self, status_code, body):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/health" or path == "":
            db_ok, db_msg = pg_check()
            redis_ok, redis_msg = redis_check()
            all_ok = db_ok and redis_ok
            self._respond(
                200 if all_ok else 503,
                {
                    "status": "ok" if all_ok else "degraded",
                    "uptime_seconds": int(time.time() - START_TIME),
                    "checks": {
                        "db": "ok" if db_ok else f"fail: {db_msg}",
                        "redis": "ok" if redis_ok else f"fail: {redis_msg}",
                    },
                },
            )

        elif path == "/health/db":
            ok, msg = pg_check()
            self._respond(200 if ok else 503, {"status": "ok" if ok else "fail", "detail": msg})

        elif path == "/health/redis":
            ok, msg = redis_check()
            self._respond(200 if ok else 503, {"status": "ok" if ok else "fail", "detail": msg})

        elif path == "/health/system":
            metrics = system_metrics()
            self._respond(200, {"status": "ok", "metrics": metrics})

        elif path == "/metrics":
            # Basic Prometheus metrics
            metrics = system_metrics()
            lines = [
                "# HELP health_server_info Health check server info",
                "# TYPE health_server_info gauge",
                f'health_server_info{{version="1.0.0"}} 1',
                "# HELP health_up Service health status (1=up, 0=down)",
                "# TYPE health_up gauge",
            ]
            for svc in ["db", "redis"]:
                ok, _ = pg_check() if svc == "db" else redis_check()
                lines.append(f"health_up{{service=\"{svc}\"}} {'1' if ok else '0'}")

            lines.append("# HELP system_disk_used_pct Disk usage percentage")
            lines.append("# TYPE system_disk_used_pct gauge")
            lines.append(f"system_disk_used_pct {metrics.get('disk_used_pct', 0)}")
            lines.append("# HELP system_mem_used_pct Memory usage percentage")
            lines.append("# TYPE system_mem_used_pct gauge")
            lines.append(f"system_mem_used_pct {metrics.get('mem_used_pct', 0)}")
            lines.append("# HELP system_load_1min CPU load average 1min")
            lines.append("# TYPE system_load_1min gauge")
            lines.append(f"system_load_1min {metrics.get('load_1min', 0)}")
            lines.append("# HELP system_swap_used_mb Swap used in MB")
            lines.append("# TYPE system_swap_used_mb gauge")
            lines.append(f"system_swap_used_mb {metrics.get('swap_used_mb', 0)}")

            self._respond(200, "\n".join(lines) + "\n")

        else:
            self._respond(404, {"error": "not_found", "path": path})


def main():
    port = int(os.environ.get("HEALTH_PORT", "9100"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health check server listening on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
