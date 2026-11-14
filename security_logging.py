"""
Write structured ingestion rejection events to the container output
"""

import json
from datetime import datetime, timezone


def log_ingestion_rejection(request, reason):
    """
    Record the observed peer without logging client payloads or headers
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "ingestion-service",
        "event": "ingestion_rejected",
        # Forwarded headers are untrusted without a verified proxy configuration
        "srcip": request.remote_addr,
        "method": request.method,
        "endpoint": "/ingest",
        "status": 400,
        "reason": reason,
    }
    print(json.dumps(event, separators=(",", ":")), flush=True)
