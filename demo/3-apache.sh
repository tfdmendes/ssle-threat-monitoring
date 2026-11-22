#!/usr/bin/env bash
# Demonstrate Apache IP reputation and Shellshock detection.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh" || exit 1

request_apache() {
    run_in "$1" curl --silent --show-error --max-time 3 --output /dev/null \
        --write-out 'HTTP %{http_code}\n' http://10.255.255.41/
}

listed_client() {
    request_apache demo-attacker
}

control_client() {
    request_apache demo-legit
}

shellshock_attempt() {
    # Apache serves the homepage and logs the header for Wazuh detection.
    run_in demo-legit curl --silent --show-error --max-time 3 --output /dev/null \
        --write-out 'HTTP %{http_code}\n' \
        --user-agent '() { :;}; echo; echo OLA; id' \
        http://10.255.255.41/
}

menu "Apache IP reputation and Shellshock" \
    "1|Request the homepage from an IP on the blocklist (Wazuh 100100, temporary block)|listed_client" \
    "2|Request the homepage from the unlisted client (HTTP 200 or timeout while blocked)|control_client" \
    "3|Send a Shellshock signature to the homepage (HTTP 200, Wazuh 100101)|shellshock_attempt"
