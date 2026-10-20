"""
The Ingestion Service receives data from different sources and forwards it to the appropriate services
In this system, it receives temperature readings from sensors and forwards them to the Storage Service

Temperature Sensor
       |
       | POST /ingest
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


import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

SERVICE_NAME = "ingestion-service"
SERVICE_URL = "http://127.0.0.1:5001"

REGISTRY_URL = "http://127.0.0.1:5050"
STORAGE_URL = "http://127.0.0.1:5002"

REQUEST_TIMEOUT = 5


def register():
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
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object"}), 400

    device_id = data.get("device_id")
    temperature = data.get("temperature")

    if not isinstance(device_id, str) or not device_id.strip():
        return jsonify({"error": "Missing or invalid device_id"}), 400

    # Python treats booleans as integers, so reject them explicitly
    if isinstance(temperature, bool) or not isinstance(
        temperature, (int, float)
    ):
        return jsonify({"error": "Missing or invalid temperature"}), 400

    payload = {
        "device_id": device_id,
        "temperature": temperature,
    }

    try:
        response = requests.post(
            f"{STORAGE_URL}/store",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        return jsonify({"error": "Storage request timed out"}), 504
    except requests.RequestException:
        return jsonify({"error": "Could not contact storage"}), 502

    if not 200 <= response.status_code < 300:
        return jsonify({"error": "Storage rejected the request"}), 502

    return jsonify({"stored": True}), 200


if __name__ == "__main__":
    # Require a successful registration before starting the server
    try:
        register()
    except requests.RequestException as error:
        raise SystemExit(f"Could not register ingestion service: {error}")

    app.run(host="127.0.0.1", port=5001)