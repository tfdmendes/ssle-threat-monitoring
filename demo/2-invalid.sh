#!/usr/bin/env bash
# Inspect reading validation and the corresponding Wazuh alerts.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh" || exit 1

invalid_reading() {
    ingest '{"temperature":"invalid"}' --header @/root/auth.hdr
}

repeated_readings_email() {
    local uid

    uid=$(run_in mail-container doveadm search -u project-alerts mailbox INBOX BODY 'Rule: 100202' |
        awk '$2 > latest { latest = $2 } END { if (latest) print latest }') || return

    if [[ -z $uid ]]; then
        printf '\nNo email for Wazuh rule 100202 is in the Inbox yet. Select option 3 again to refresh.\n'
        return
    fi

    printf '\nLatest Inbox email for Wazuh rule 100202:\n'
    run_in mail-container doveadm -f pager fetch -u project-alerts \
        'date.received hdr.subject' mailbox INBOX uid "$uid"
}

menu "Reading validation and Active Response" \
    "1|Send text instead of a temperature, using a valid key (HTTP 400, Wazuh 100201)|invalid_reading" \
    "2|Count each sensor's readings from the last 30 seconds|recent_sensor_counts" \
    "3|Check Inbox|repeated_readings_email"
