#!/usr/bin/env bash
# Demonstrate the Ingestion API's rate limiting with a bounded request burst.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh" || exit 1

send_requests() {
    run_in demo-attacker bash -c '
        for request in $(seq 1 120); do
            curl --silent --show-error --max-time 5 \
                --output /dev/null \
                --write-out "Request $request: HTTP %{http_code}\n" \
                --header @/root/auth.hdr --json "{\"temperature\":21.5}" \
                https://ssle-ingestion:30502/ingest &
            sleep 0.03
        done
        wait
    '
}

rate_limit_burst() {
    local responses summary

    printf 'Sending 120 authenticated demo readings, 30 ms apart.\n'
    if [[ -t 0 ]]; then
        printf 'Each response will appear below as it arrives.\n' > /dev/tty
        responses=$(send_requests | tee /dev/tty) || return
    else
        responses=$(send_requests) || return
    fi

    summary=$(printf '%s\n' "$responses" | awk '
        /^Request [0-9]+: HTTP [0-9][0-9][0-9]$/ {
            status = $4
            count[status]++
            total++
            next
        }
        { unexpected++ }
        END {
            printf "HTTP 200 (stored): %d\n", count["200"]
            printf "HTTP 429 (rate limited): %d\n", count["429"]
            for (status in count)
                if (status != "200" && status != "429")
                    printf "HTTP %s: %d\n", status, count[status]
            if (unexpected) printf "Unexpected output lines: %d\n", unexpected
            printf "Responses: %d of 120\n", total
            if (total != 120 || unexpected) exit 1
        }
    ') || return

    printf '%s\n' "$summary"
    if [[ -t 0 ]]; then
        printf '\n%s\n\nPress Enter to return to the menu. ' "$summary" > /dev/tty
        IFS= read -r _ </dev/tty
    fi
}

rate_limit_alerts() {
    printf 'Correlated alerts (100212):\n'
    show_wazuh_rules 100212 || return
    printf '\nIndividual rejections (100211):\n'
    show_wazuh_rules 100211
}

nginx_logs() {
    kube logs deploy/ssle-ingestion --container nginx --since=5m |
        awk '/"status":429/ && /"limit_status":"REJECTED"/ { latest = $0 }
             END { if (latest != "") print latest;
                   else print "No HTTP 429 / REJECTED entry in the last five minutes." }'
}

menu "NGINX rate limiting" \
    "1|Send paced requests to Ingestion and show each response|rate_limit_burst" \
    "2|Show the latest HTTP 429 / REJECTED NGINX log|nginx_logs" \
    "3|Show rate-limit alerts (Wazuh 100211 and 100212)|rate_limit_alerts" \
    "4|Show the latest Inbox subjects|inbox_subjects"
