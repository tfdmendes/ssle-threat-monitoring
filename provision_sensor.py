# Run this command on the ingestion side to give a sensor a key, replace it, or turn it off.
# It updates the same devices.db that ingestion.py checks when a reading arrives.

import argparse
import secrets
import sqlite3

from devices import DEVICE_ID, database, init_db, token_hash


def main():
    parser = argparse.ArgumentParser(description="Manage a sensor's ingestion API key")
    parser.add_argument("device_id")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--rotate", action="store_true", help="Replace an active key")
    action.add_argument("--revoke", action="store_true", help="Deactivate the sensor")
    args = parser.parse_args()

    if not DEVICE_ID.fullmatch(args.device_id):
        parser.error("invalid device ID")

    try:
        # Create the sensor table if it is missing. Existing sensor records stay as they are.
        init_db()
        # Keep the sensor's record but mark it inactive so its key stops working.
        if args.revoke:
            with database() as connection:
                result = connection.execute(
                    "UPDATE devices SET active = 0 WHERE device_id = ?", (args.device_id,)
                )
                if result.rowcount == 0:
                    parser.exit(1, "Sensor is not registered.\n")
            return

        # Generate a secret key. Save only its hash so ingestion can check the key later.
        token = secrets.token_urlsafe(32)
        digest = token_hash(token)
        with database() as connection:
            if args.rotate:
                result = connection.execute(
                    "UPDATE devices SET token_hash = ? WHERE device_id = ? AND active = 1",
                    (digest, args.device_id),
                )
                if result.rowcount == 0:
                    parser.exit(1, "Sensor is not registered or has been revoked.\n")
            else:
                result = connection.execute(
                    """
                    INSERT INTO devices (device_id, token_hash, active)
                    VALUES (?, ?, 1) ON CONFLICT (device_id) DO NOTHING
                    """,
                    (args.device_id, digest),
                )
                if result.rowcount == 0:
                    parser.exit(1, "Sensor is already registered. Use --rotate to replace its key.\n")
    except sqlite3.Error:
        parser.exit(1, "Could not update the device database.\n")

    # Print the new key after saving its hash so the administrator can give it to the sensor.
    print(token)


if __name__ == "__main__":
    main()
