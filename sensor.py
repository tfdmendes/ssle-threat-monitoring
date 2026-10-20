import random
import time

import requests

DEVICE_ID = "sensor-001"
INGESTION_URL = "http://127.0.0.1:5001/ingest"

SEND_INTERVAL = 5
REQUEST_TIMEOUT = 5


def send_temp():
    while True:
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

            # HTTP error responses do not raise exceptions automatically
            response.raise_for_status()

            print("Reading accepted:", payload)

        except requests.Timeout:
            print("Request timed out; storage outcome is unknown")

        except requests.HTTPError as error:
            print("Ingestion returned an HTTP error:", error)

        except requests.RequestException as error:
            print("Could not complete the request:", error)

        time.sleep(SEND_INTERVAL)


if __name__ == "__main__":
    send_temp()