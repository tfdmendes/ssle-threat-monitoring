import os
import random
import time

import requests

DEVICE_ID = os.environ.get("DEVICE_ID", "sensor-001")
INGESTION_URL = os.environ.get("INGESTION_URL", "http://127.0.0.1:5001/ingest")

SEND_INTERVAL = 5
REQUEST_TIMEOUT = 5


def send_temp():
    while True:
        # Generate a simulated reading rather than reading a physical sensor
        temperature = round(random.uniform(20.0, 30.0), 2)

        payload = {
            "device_id": DEVICE_ID,
            "temperature": temperature,
        }

        try:
            response = requests.post(
                INGESTION_URL,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            # Convert HTTP 4xx and 5xx responses into the HTTPError handled below
            response.raise_for_status()

            print("Reading accepted:", payload)

        except requests.Timeout:
            print("Request timed out; storage outcome is unknown")

        except requests.HTTPError as error:
            print("Ingestion returned an HTTP error:", error)

        except requests.RequestException as error:
            print("Could not complete the request:", error)

        # The five-second pause starts after each request finishes
        # Failed readings are discarded rather than retried
        time.sleep(SEND_INTERVAL)


if __name__ == "__main__":
    send_temp()
