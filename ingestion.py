"""
Checks each sensor's API key and sends valid temperature readings to Storage.

Temperature Sensor
       |
       | POST /ingest over HTTPS (through NGINX in K3s)
       | Authorization: Bearer <sensor key>
       | JSON: {"device_id": "sensor-001", "temperature": 25.5}
       v
 Ingestion Service
   (Port 5001)
       |
       | POST /store
       v
  Storage Service
   (Port 5002)
       |
       v
   SQLite DB

"""

import os
import sqlite3

import requests
from flask import Flask, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from devices import authenticate, init_db
from instrumentation import configure_metrics
from security_logging import log_ingestion_rejection

app = Flask(__name__)
TRUST_LOCAL_PROXY = os.environ.get("TRUST_LOCAL_PROXY") == "1"
# The container binds to loopback and NGINX replaces the forwarded address
if TRUST_LOCAL_PROXY:
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=0, x_host=0, x_port=0, x_prefix=0
    )
# Attach /metrics and request hooks to this same Flask app
configure_metrics(app)

SERVICE_NAME = "ingestion-service"
SERVICE_URL = os.environ.get("SERVICE_URL", "http://127.0.0.1:5001")

# Kubernetes overrides the local defaults with stable Service addresses
REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://127.0.0.1:5050")
STORAGE_URL = os.environ.get("STORAGE_URL", "http://127.0.0.1:5002")

REQUEST_TIMEOUT = 5


def reject_reading(reason, message):
    log_ingestion_rejection(request, reason)
    return jsonify({"error": message}), 400


def reject_sensor(reason, status):
    log_ingestion_rejection(request, reason, status)
    if status == 401:
        return jsonify({"error": "Invalid sensor credential"}), 401, {"WWW-Authenticate": "Bearer"}
    return jsonify({"error": "Credential is not authorized for this device ID"}), 403


def register():
    # Registration advertises ingestion while STORAGE_URL determines how to reach storage
    response = requests.post(
        f"{REGISTRY_URL}/register",
        json={
            "name": SERVICE_NAME,
            "url": SERVICE_URL,
        },
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()


@app.route("/ingest", methods=["POST"])
def ingest():
    # Use the key to find the sensor before reading the JSON.
    try:
        device_id = authenticate(request.headers.get("Authorization", ""))
    except sqlite3.Error:
        app.logger.error("Device credentials are unavailable")
        return jsonify({"error": "Device credentials are unavailable"}), 503

    if device_id is None:
        return reject_sensor("invalid_sensor_credential", 401)

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return reject_reading("invalid_json_object", "Expected a JSON object")

    temperature = data.get("temperature")

    # If the JSON includes an ID, check that it names the sensor found by its key.
    if "device_id" in data:
        declared_id = data["device_id"]
        if not isinstance(declared_id, str) or not declared_id.strip():
            return reject_reading("invalid_device_id", "Invalid device_id")
        if declared_id != device_id:
            return reject_sensor("sensor_identity_mismatch", 403)

    # Python treats booleans as integers, so reject them explicitly
    if isinstance(temperature, bool) or not isinstance(
        temperature, (int, float)
    ):
        return reject_reading("invalid_temperature", "Missing or invalid temperature")

    # Save the temperature under the ID found in devices.db.
    payload = {
        "device_id": device_id,
        "temperature": temperature,
    }

    try:
        # Acknowledge the reading only after storage accepts it
        response = requests.post(
            f"{STORAGE_URL}/store",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        # A timeout does not prove that storage failed to save the reading
        return jsonify({"error": "Storage request timed out"}), 504
    except requests.RequestException:
        return jsonify({"error": "Could not contact storage"}), 502

    if not 200 <= response.status_code < 300:
        return jsonify({"error": "Storage rejected the request"}), 502

    return jsonify({"stored": True}), 200


if __name__ == "__main__":
    tls = None
    if not TRUST_LOCAL_PROXY:
        certificate = os.environ.get("INGESTION_TLS_CERT")
        private_key = os.environ.get("INGESTION_TLS_KEY")
        if not certificate or not private_key:
            raise SystemExit("Set INGESTION_TLS_CERT and INGESTION_TLS_KEY for local HTTPS")
        tls = (certificate, private_key)

    try:
        init_db()
        register()
    except sqlite3.Error:
        raise SystemExit("Could not initialize the device database")
    except requests.RequestException as error:
        raise SystemExit(f"Could not register ingestion service: {error}")

    app.run(host="127.0.0.1", port=5001, ssl_context=tls)
