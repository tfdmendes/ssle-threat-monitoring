"""
Expose ingestion request metrics through Flask hooks and a metrics endpoint
"""

from time import perf_counter

from flask import Response, g, request
from prometheus_client import Counter, Histogram, generate_latest

# Keep the text format compatible with the deployed Prometheus 2.x server
_PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

# Measurements reset when the ingestion process restarts
# The status label separates successful responses from different HTTP errors
_INGEST_REQUESTS = Counter(
    "ingestion_requests_total",
    "Responses to POST /ingest by HTTP status",
    ["status"],
)
# A histogram records duration buckets, a count and total elapsed time
_INGEST_DURATION = Histogram(
    "ingestion_request_duration_seconds",
    "Time spent processing POST /ingest in seconds",
)


def configure_metrics(app):
    """
    Attach request hooks and /metrics to the Flask app passed by ingestion

    Call once per app before it handles requests
    """
    @app.before_request
    def start_ingest_timer():
        # Exclude /metrics so scraping does not affect ingestion measurements
        if request.endpoint == "ingest":
            # g keeps concurrent request timers separate
            g.ingest_started = perf_counter()

    @app.after_request
    def record_ingest_metrics(response):
        if request.endpoint == "ingest":
            # Record the final response status and elapsed time, including storage waits
            _INGEST_REQUESTS.labels(status=str(response.status_code)).inc()
            _INGEST_DURATION.observe(perf_counter() - g.ingest_started)
        return response

    @app.route("/metrics", methods=["GET"])
    def metrics():
        # Prometheus reads the current measurements without resetting them
        return Response(generate_latest(), content_type=_PROMETHEUS_CONTENT_TYPE)
