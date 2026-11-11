"""
Expose ingestion request metrics through Flask hooks and a metrics endpoint
"""

from time import perf_counter

from flask import Response, g, request
from prometheus_client import Counter, Histogram, generate_latest

# Keep the text format compatible with the lab's Prometheus 2.x server
_PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

_INGEST_REQUESTS = Counter(
    "ssle_ingestion_requests_total",
    "Responses to POST /ingest by HTTP status",
    ["status"],
)
_INGEST_DURATION = Histogram(
    "ssle_ingestion_request_duration_seconds",
    "Time spent processing POST /ingest in seconds",
)


def configure_metrics(app):
    """
    app is in the Flask application itself
    
    Attach ingestion metrics once, before the Flask app handles requests
    """
    @app.before_request
    def start_ingest_timer():
        if request.endpoint == "ingest":
            g.ingest_started = perf_counter()

    @app.after_request
    def record_ingest_metrics(response):
        if request.endpoint == "ingest":
            _INGEST_REQUESTS.labels(status=str(response.status_code)).inc()
            _INGEST_DURATION.observe(perf_counter() - g.ingest_started)
        return response

    @app.route("/metrics", methods=["GET"])
    def metrics():
        return Response(generate_latest(), content_type=_PROMETHEUS_CONTENT_TYPE)
