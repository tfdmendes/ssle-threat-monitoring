#!/usr/bin/env bash
# Follow new Wazuh alerts in a second Kali terminal.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh" || exit 1

printf 'Watching for new Wazuh alerts. Press Ctrl+C to stop.\n' >&2
run_in wazuh-container tail --lines=0 --follow=name --retry /var/ossec/logs/alerts/alerts.log |
    grep --line-buffered '^Rule:'
