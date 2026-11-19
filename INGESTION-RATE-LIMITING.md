# Denial of service at ingestion

## Problem

A high rate of requests to `POST /ingest` can consume the processing capacity that ingestion needs to serve legitimate sensors. Even well-formed requests create work. After checking the sensor credentials and validating the reading, [ingestion](ingestion.py#L81) sends it to Storage, which writes it to SQLite. Excess traffic can delay or prevent legitimate readings from being stored.

The existing Wazuh response to repeated invalid readings addresses requests that fail payload validation. Well-formed requests can create load without producing that signal. [Ingestion rules](deploy/wazuh/ingestion-rules.xml) · SSLE Guide 5, pp. 1–3

## Implemented mitigation

1. NGINX and the Python ingestion application run in separate containers in the same Kubernetes Pod. NGINX receives sensor requests over HTTPS and applies its rate limit to `POST /ingest`. It forwards admitted requests over HTTP to the Flask application on the Pod's loopback address, `127.0.0.1:5001`. The application then [authenticates the sensor](SENSOR-AUTHENTICATION.md) and validates the reading before calling Storage.
2. The proxy applies a shared rate of 20 requests per second per Pod, with a burst allowance of five requests. It forwards requests within the burst allowance immediately. It rejects excess requests with HTTP `429 Too Many Requests` and `Retry-After: 1` before they reach Flask. [NGINX configuration](deploy/k8s/ingestion.yaml#L24)
3. NGINX records rejections in its access log. Wazuh rule `100211` matches a `POST /ingest` that NGINX rejected with `429`. Rule `100212` correlates 20 such rejections within 30 seconds on the same Wazuh agent and is configured to alert by email. NGINX enforces the limit on each request. Wazuh reports sustained rejections. [Wazuh rules](deploy/wazuh/nginx-rules.xml#L8)

## Why we enforce the limit at NGINX

We could check the request rate at the start of the Flask request lifecycle. That would allow Flask to return `429` before authenticating the sensor, validating the temperature or contacting Storage. Each incoming request would still have to reach the Python process and use some of its capacity to check the limit and return a response.

We chose to enforce the limit in NGINX so that the Python service handles only requests admitted by the proxy. NGINX already receives and terminates HTTPS, and its built-in rate limiter lets us configure this policy at the same entry point. Keeping the Flask listener on loopback makes NGINX the entry point from outside the Pod. The design adds a container and a proxy hop to the ingestion path. [Flask listener](ingestion.py#L155) · [Ingestion Deployment](deploy/k8s/ingestion.yaml#L84)

We use a shared budget because the load on ingestion and Storage depends on the combined traffic from all clients. A per-client limit would give each client its own allowance, so the total admitted rate could still grow with the number of clients. With the shared budget, heavy traffic can also cause legitimate requests to receive `429`. Each additional Pod would have its own budget. The 20 requests per second setting is the configured lab policy. Establishing the safe operating capacity would require a separate measurement.

## Validation

| Check | Observed result |
| --- | --- |
| Initial K3s deployment, 2026-11-15, before HTTPS and sensor authentication | Of 40 valid requests, 8 returned HTTP 200 and 32 returned HTTP 429. A subsequent request succeeded after the burst ended. |
| Current HTTPS path on Kali, 2026-11-19 | In two short trials at 2 and 8 requests per second, all 60 requests returned HTTP 200 and produced 60 SQLite rows. |
| Wazuh rule check, 2026-11-19 | A log test with 20 synthetic NGINX rejection events produced 19 single-rejection matches and one correlated match. |

The November 19 results are recorded in `ssle-kali-validation-2026-11-19.json`. The short HTTPS trials measured successful ingestion below the configured limit. Availability for legitimate sensors while the current limiter is saturated remains unmeasured.
