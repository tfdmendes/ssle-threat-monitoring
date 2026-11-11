"""
Read temperature statistics from storage over HTTP and calculate their average
"""

import math
import os

import requests
from flask import Flask, jsonify

app = Flask(__name__)

STORAGE_URL = os.environ.get("STORAGE_URL", "http://127.0.0.1:5002") # Cant acess the sql directly anymore
REQUEST_TIMEOUT = 5


@app.route("/average", methods=["GET"])
def average_temp():
    try:
        response = requests.get(f"{STORAGE_URL}/stats", timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.Timeout:
        return jsonify({"error": "Storage request timed out"}), 504
    except requests.RequestException:
        return jsonify({"error": "Could not retrieve storage statistics"}), 502

    try:
        stats = response.json()
        count = stats["count"]
        total = stats["sum"]
        if (
            type(count) is not int
            or count < 0
            or isinstance(total, bool)
            or not isinstance(total, (int, float))
            or not math.isfinite(total)
        ):
            raise ValueError("Invalid storage statistics")
    except (KeyError, TypeError, ValueError, OverflowError):
        return jsonify({"error": "Invalid storage statistics"}), 502

    average = round(total / count, 2) if count else None
    return jsonify({"average_temperature": average})


if __name__ == "__main__":
    app.run(port=5003)
