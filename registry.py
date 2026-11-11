"""
Keep the latest advertised URL and registration time for each service name

Registering the same name again replaces its previous entry
"""

from datetime import datetime, timezone
from flask import Flask, jsonify, request

app = Flask(__name__)


# Registrations are kept in memory and lost on restart
registry = {}

@app.route("/register", methods=["POST"])
def register():
    # Invalid JSON becomes None and is handled by the validation below
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object"}), 400

    name = data.get("name")
    url = data.get("url")

    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "Missing or invalid name"}), 400

    if not isinstance(url, str) or not url.strip():
        return jsonify({"error": "Missing or invalid URL"}), 400

    # Register a new service or update an existing entry
    registry[name] = {
        "url": url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return jsonify({"message": f"{name} registered"}), 200


@app.route("/unregister", methods=["DELETE"])
def unregister():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object"}), 400

    name = data.get("name")

    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "Missing or invalid name"}), 400

    if name not in registry:
        return jsonify({"error": "Service not found"}), 404

    del registry[name]

    return jsonify({"message": f"{name} unregistered"}), 200


@app.route("/services", methods=["GET"])
def list_services():
    return jsonify(registry), 200


@app.route("/services/<name>", methods=["GET"])
def get_service(name):
    service = registry.get(name)

    if service is None:
        return jsonify({"error": "Service not found"}), 404

    return jsonify(service), 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050)
