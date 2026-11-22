#!/usr/bin/env bash
# Compare delivery of a normal message and the spam example from the lab guide.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh" || exit 1

send_message() {
    local container=$1 message=$2

    printf '\nEmail headers and body:\n%s\n' "$message"

    printf '%s\n' "$message" |
        run_in --with-stdin "$container" curl --silent --show-error --max-time 10 \
            --mail-from demo@lab.test --mail-rcpt project-alerts@mail-container.incus \
            --crlf --upload-file - smtp://10.255.255.119
}

normal_message() {
    local message
    message=$(run_in demo-legit cat -- /root/normal.eml) || return
    send_message demo-legit "$message"
}

spam_message() {
    local message
    message=$(cat <<'EOF'
From: demo@lab.test
To: project-alerts@mail-container.incus
Subject: BUY CHEAP VIAGRA NOW FREE PILLS AND CIALIS
MIME-Version: 1.0
Content-Type: text/plain; charset=us-ascii

buy viagra cheap free shipping now cialis generic pills
EOF
    )
    send_message demo-attacker "$message"
}

junk_subjects() {
    mailbox_subjects Junk 2 |
        sed -E 's/^(Subject: (\*+SPAM\*+[[:blank:]]+)?)(SSLE|\[SSLE\])[[:blank:]]+/\1/'
}

menu "Email filtering and quarantine" \
    "1|Send a normal email (expect it in Inbox)|normal_message" \
    "2|Send the Viagra spam example from the lab guide (expect it in Junk, Wazuh 100220)|spam_message" \
    "3|Check Inbox|inbox_subjects" \
    "4|Check Junk Inbox|junk_subjects"
