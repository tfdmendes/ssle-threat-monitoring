"""
Probe HTTP services and expose their latest health check results to Prometheus
"""

import argparse
import json
import math
from pathlib import Path
import time
from urllib.parse import urlsplit

from prometheus_client import CollectorRegistry, Gauge, start_http_server
import requests


def load_targets(path):
    """
    Load a non-empty mapping of service names to HTTP URLs
    """
    targets = json.loads(Path(path).read_text())
    if not isinstance(targets, dict) or not targets:
        raise ValueError("Targets must be a non-empty JSON object")
    for service, url in targets.items():
        if not isinstance(service, str) or not service.strip():
            raise ValueError("Each service must have a non-empty name")
        if not isinstance(url, str):
            raise ValueError(f"The URL for {service} must be a string")
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(f"The URL for {service} must use HTTP or HTTPS")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError(f"The URL for {service} has an invalid port")
    return targets


def check_service_health(targets, health_metric, timeout):
    """
    Set each service's gauge to one for HTTP 2xx or zero for a failed check
    """
    for service, url in targets.items():
        try:
            with requests.get(
                url, timeout=timeout, allow_redirects=False, stream=True,
            ) as response:
                healthy = int(200 <= response.status_code < 300)
        except requests.RequestException:
            healthy = 0
        health_metric.labels(service=service).set(healthy)


def main():
    """
    Run an exporter until interrupted, checking targets between sleep intervals
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("health_targets.example.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--timeout", type=float, default=2)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    if not math.isfinite(args.interval) or args.interval <= 0:
        parser.error("Interval must be a positive finite number")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("Timeout must be a positive finite number")
    try:
        targets = load_targets(args.config)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    registry = CollectorRegistry()
    health_metric = Gauge(
        "service_health", "Latest HTTP health check result: 1 for success, 0 for failure",
        ["service"], registry=registry,
    )
    server = None
    try:
        # Probe before serving metrics so untested targets are not reported as down
        check_service_health(targets, health_metric, args.timeout)
        server, thread = start_http_server(args.port, addr=args.host, registry=registry)
        print(f"Health exporter listening on {args.host}:{args.port}", flush=True)
        while True:
            time.sleep(args.interval)
            check_service_health(targets, health_metric, args.timeout)
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    main()
