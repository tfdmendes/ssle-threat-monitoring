#!/usr/bin/env bash
# Shared functions for the Kali lab demonstration.

set -o pipefail

INGESTION_URL=https://ssle-ingestion:30502/ingest

print_shell_argument() {
    local argument=$1
    local escaped_quote="'\\''"
    local double_quote_special='["\\$`!]'

    case "$argument" in
        ''|*[!a-zA-Z0-9_./:@%+=,-]*)
            if [[ $argument == *"'"* && ! $argument =~ $double_quote_special ]]; then
                printf '"%s"' "$argument"
            else
                printf "'%s'" "${argument//\'/$escaped_quote}"
            fi
            ;;
        *)
            printf '%s' "$argument"
            ;;
    esac
}

print_command() {
    local executable=$1 argument
    local separator=' '
    shift

    printf ' '
    print_shell_argument "$executable"
    for argument in "$@"; do
        case "$executable:$argument" in
            curl:--write-out|curl:--header|curl:--json|curl:--mail-from|curl:--mail-rcpt|curl:--upload-file|curl:http://*|curl:https://*|curl:smtp://*)
                separator=$' \\\n  '
                ;;
        esac

        printf '%s' "$separator"
        print_shell_argument "$argument"
        separator=' '
        if [[ $argument == *$'\n'* ]]; then
            separator=$' \\\n  '
        fi
    done
}

run_in() {
    local -a exec_options=(--disable-stdin)
    if [[ $1 == --with-stdin ]]; then
        exec_options=(--mode=non-interactive)
        shift
    fi

    local container=$1
    shift

    {
        printf '\n[%s]$' "$container"
        print_command "$@"
        printf '\n\n'
    } >&2
    incus exec "${exec_options[@]}" "$container" -- "$@"
}

kube() {
    run_in k3s-master k3s kubectl --namespace ssle "$@"
}

ingest() {
    local payload=$1
    shift

    run_in demo-attacker curl --silent --show-error --max-time 5 \
        --write-out '\nHTTP %{http_code}\n' "$@" --json "$payload" "$INGESTION_URL"
}

storage_query() {
    kube exec deploy/ssle-storage -- python -c '
import sqlite3
import sys
from contextlib import closing

with closing(sqlite3.connect("file:readings.db?mode=ro", uri=True)) as database:
    for row in database.execute(sys.argv[1]):
        print(row)
' "$1"
}

recent_sensor_counts() {
    storage_query "SELECT device_id, COUNT(*) FROM temperatures
                  WHERE timestamp > datetime('now', '-30 seconds') GROUP BY device_id"
}

ingestion_firewall() {
    run_in k3s-node1 iptables --list-rules INPUT
}

show_wazuh_rules() {
    local rules=$1
    local matches

    matches=$(run_in wazuh-container tail --lines=1000 /var/ossec/logs/alerts/alerts.log |
        awk -v rules="$rules" '$0 ~ ("^Rule: (" rules ") ")' |
        tail --lines=10) || return

    if [[ -n $matches ]]; then
        printf '%s\n' "$matches"
    else
        printf 'No matching alerts in the last 1,000 lines of the Wazuh log.\n'
    fi
}

mailbox_subjects() {
    local mailbox=$1 limit=$2 subjects

    subjects=$(run_in mail-container doveadm -f pager fetch -u project-alerts \
        hdr.subject mailbox "$mailbox" all |
        sed -n 's/^hdr\.subject: /Subject: /p' |
        tail --lines="$limit") || return

    if [[ -n $subjects ]]; then
        printf '%s\n' "$subjects"
    else
        printf 'No messages in %s.\n' "$mailbox"
    fi
}

inbox_subjects() {
    mailbox_subjects INBOX 3
}

# Each entry contains a key, a label and the function that runs on selection.
menu() {
    local title=$1
    shift
    local entry key label action choice
    local prompt='Choose an option > '
    local header line home erase rows columns prompt_row page_size
    local fixed_screen=false result='' capture status
    local page=0 page_count=1 first_line last_line index footer
    local -a output_lines

    header=$(
        printf '== %s ==\n' "$title"
        if [[ -n ${menu_note:-} ]]; then
            printf '%s\n' "$menu_note"
        fi
        for entry in "$@"; do
            IFS='|' read -r key label action <<< "$entry"
            printf '  %s) %s\n' "$key" "$label"
        done
        printf '  q) Quit\n'
    )

    if [[ -t 0 && -t 1 ]] &&
        home=$(tput home 2>/dev/null) && erase=$(tput ed 2>/dev/null) &&
        tput cup 0 0 >/dev/null 2>&1; then
        fixed_screen=true
    fi

    while true; do
        page_size=0
        if [[ $fixed_screen == true ]] &&
            read -r rows columns < <(stty size 2>/dev/null) &&
            (( columns > ${#prompt} )); then
            line=$(printf '%s\n' "$header" | fold -s -w "$columns")
            prompt_row=$(printf '%s\n\n' "$line" | wc -l)
            # Leave room for the prompt, separation, page controls and shell cursor.
            page_size=$((rows - prompt_row - 4))
        fi

        if (( page_size > 0 )); then
            printf '%s%s%s\n\n%s\n\n' "$home" "$erase" "$line" "$prompt"
            output_lines=()
            while IFS= read -r line; do
                output_lines+=("$line")
            done < <(printf '%s\n' "$result" |
                tr -d '\000-\010\013-\037\177' | expand | fold -s -w "$columns")

            page_count=$(( (${#output_lines[@]} + page_size - 1) / page_size ))
            if (( page >= page_count )); then
                page=$((page_count - 1))
            fi
            first_line=$((page * page_size))
            last_line=$((first_line + page_size))
            for ((index = first_line; index < last_line && index < ${#output_lines[@]}; index++)); do
                printf '%s\n' "${output_lines[index]}"
            done
            if (( page_count > 1 )); then
                tput cup "$((rows - 2))" 0
                footer="Page $((page + 1))/$page_count [p/n]"
                printf '%.*s' "$columns" "$footer"
            fi
            tput cup "$((prompt_row))" "${#prompt}"
        else
            if [[ -n $result ]]; then
                printf '\n%s\n' "$result"
                result=''
            fi
            printf '\n%s\n\n%s' "$header" "$prompt"
        fi

        if ! read -r choice || [[ $choice == q ]]; then
            if (( page_size > 0 )); then
                tput cup "$((rows - 1))" 0
            fi
            return 0
        fi

        if (( page_size > 0 && page_count > 1 )); then
            case "$choice" in
                p) (( page > 0 )) && page=$((page - 1)); continue ;;
                n) (( page < page_count - 1 )) && page=$((page + 1)); continue ;;
            esac
        fi

        for entry in "$@"; do
            IFS='|' read -r key label action <<< "$entry"
            if [[ $choice == "$key" ]]; then
                if (( page_size > 0 )) && capture=$(mktemp); then
                    tput cup "$((prompt_row + 2))" 0
                    printf '%sRunning...\n' "$erase"
                    # Keep action state in this shell and unlink the capture before running it.
                    {
                        rm -f -- "$capture"
                        printf '%s\n' "$label" >&4
                        status=0
                        "$action" >&4 2>&1 || status=$?
                        if (( status != 0 )); then
                            printf '\nAction exited with status %s.\n' "$status" >&4
                        fi
                        result=$(cat <&3)
                    } 3<"$capture" 4>"$capture"
                    page=0
                else
                    printf '\n%s\n' "$label"
                    "$action"
                fi
                continue 2
            fi
        done
        result='Enter one of the numbers above, or q to quit.'
        page=0
    done
}
