# Simulate temperatures and send readings to ingestion over HTTPS using a key from a file.

import os
import random
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

DEVICE_ID = os.environ.get("DEVICE_ID", "sensor-001")
INGESTION_URL = os.environ.get("INGESTION_URL", "https://localhost:5001/ingest")
KEY_FILE = Path(os.environ.get("SENSOR_API_KEY_FILE", "/run/secrets/ingestion-api-key"))
CA_FILE = os.environ.get("INGESTION_CA_FILE")

SEND_INTERVAL = 5
REQUEST_TIMEOUT = 5


def send_temp():
    destination = urlsplit(INGESTION_URL)
    if destination.scheme != "https" or not destination.hostname or destination.username is not None:
        raise SystemExit("INGESTION_URL must be an HTTPS URL without embedded credentials")
    # Read the key once at startup. Restart the sensor after replacing the key file.
    try:
        api_key = KEY_FILE.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        raise SystemExit(f"Cannot read the sensor API key from {KEY_FILE}")
    if not api_key:
        raise SystemExit(f"Missing sensor API key in {KEY_FILE}")

    with requests.Session() as session:
        session.trust_env = False
        # Check that this is the expected ingestion server before sending it the key.
        session.verify = CA_FILE or True
        session.headers["Authorization"] = f"Bearer {api_key}"
        send_readings(session)


def send_readings(session):
    while True:
        # Generate a simulated reading rather than reading a physical sensor
        temperature = round(random.uniform(20.0, 30.0), 2)

        payload = {
            "device_id": DEVICE_ID,
            "temperature": temperature,
        }

        try:
            response = session.post(
                INGESTION_URL,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
            )

            if 200 <= response.status_code < 300:
                print("Reading accepted:", payload)
            else:
                print("Ingestion returned HTTP status:", response.status_code)

        except requests.Timeout:
            print("Request timed out; storage outcome is unknown")

        except requests.RequestException:
            print("Could not complete the HTTPS request")

        # The five-second pause starts after each request finishes
        # Failed readings are discarded rather than retried
        time.sleep(SEND_INTERVAL)


if __name__ == "__main__":
    send_temp()
