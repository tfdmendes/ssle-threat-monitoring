#!/usr/bin/env bash
# Demonstrate Analytics availability in the Kali lab.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh" || exit 1

deployment=deployment/ssle-analytics
health_query='service_health{job="ssle-health",service="analytics"}'
paused_here=false

show_status() {
    kube get "$deployment" --request-timeout=10s || return

    curl --fail --silent --show-error --max-time 5 --get \
        --data-urlencode "query=$health_query" http://10.255.255.42:9090/api/v1/query |
        python3 -c '
import json
import sys

samples = json.load(sys.stdin)["data"]["result"]
if not samples:
    raise SystemExit("Prometheus has no health data for Analytics.")

states = {"0": "DOWN", "1": "UP"}
for sample in samples:
    value = sample["value"][1]
    print(f"Analytics in Prometheus: {states.get(value, value)}")
'
}

pause_analytics() {
    kube scale "$deployment" --current-replicas=1 --replicas=0 --request-timeout=10s || return
    paused_here=true
    printf '\nAnalytics is stopping. Watch the Service health panel in Grafana.\n'
}

restore_analytics() {
    local replicas

    replicas=$(kube get "$deployment" --output=jsonpath='{.spec.replicas}' --request-timeout=10s) || return
    if [[ $replicas != 1 ]]; then
        kube scale "$deployment" --current-replicas=0 --replicas=1 --request-timeout=10s || return
    fi
    paused_here=false
    printf '\nAnalytics is back to one replica. Use option 1 to see whether it is ready.\n'
}

cleanup() {
    if [[ $paused_here == true ]]; then
        printf '\nStarting Analytics again before quitting.\n'
        if ! restore_analytics; then
            printf 'Could not restore Analytics. Reopen this menu and use option 3.\n' >&2
            exit 1
        fi
    fi
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

menu_note='Grafana: SSLE Overview > Service health and Service health history.' \
    menu "Analytics availability" \
        "1|Check Analytics in Kubernetes and Prometheus|show_status" \
        "2|Stop Analytics (scale to zero replicas)|pause_analytics" \
        "3|Start Analytics again (scale to one replica)|restore_analytics"
