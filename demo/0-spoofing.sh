#!/usr/bin/env bash
# Sensor identity and authentication checks.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh" || exit 1

valid_reading() {
    ingest '{"device_id":"sensor-demo","temperature":21.5}' --header @/root/auth.hdr
}

mismatched_identity() {
    ingest '{"device_id":"sensor-A","temperature":99}' --header @/root/auth.hdr
}

missing_key() {
    ingest '{"device_id":"sensor-A","temperature":99}'
}

invalid_key() {
    ingest '{"device_id":"sensor-A","temperature":99}' --header 'Authorization: Bearer invalid-demo-key'
}

revoked_key() {
    ingest '{"temperature":99}' --header @/root/revoked.hdr
}

latest_demo_reading() {
    local reading

    reading=$(storage_query "SELECT device_id, temperature, timestamp
FROM temperatures
WHERE device_id = 'sensor-demo'
ORDER BY id DESC
LIMIT 1") || return
    if [[ -n $reading ]]; then
        printf '%s\n' "$reading"
    else
        printf 'Storage has no readings from sensor-demo yet. Send one with option 1.\n'
    fi
}

menu "Sensor spoofing and authentication" \
    "1|Send a reading as sensor-demo with its own key (HTTP 200)|valid_reading" \
    "2|Send a reading as sensor-A with sensor-demo's key (HTTP 403, Wazuh 100203)|mismatched_identity" \
    "3|Send a reading without a key (HTTP 401, Wazuh 100203)|missing_key" \
    "4|Send a reading with an invalid key (HTTP 401, Wazuh 100203)|invalid_key" \
    "5|Send a reading with a revoked key (HTTP 401, Wazuh 100203)|revoked_key" \
    "6|Show the last reading stored for sensor-demo|latest_demo_reading" \
    "7|Count each sensor's readings from the last 30 seconds|recent_sensor_counts"
