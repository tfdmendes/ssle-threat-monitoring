#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 || ! $2 =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]]; then
    printf 'Usage: bash %s NEW_DIRECTORY EXTERNAL_DNS_NAME\n' "$0" >&2
    exit 2
fi

output=$1
external_dns=$2
umask 077
mkdir -- "$output"
cd -- "$output"

openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -keyout ca.key -out ca.crt -days 365 -sha256 -subj '/CN=SSLE Lab Ingestion CA' \
    -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' \
    -addext 'keyUsage=critical,keyCertSign,cRLSign' \
    -addext 'subjectKeyIdentifier=hash'

openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -keyout tls.key -out tls.csr -sha256 -subj "/CN=$external_dns"

cat > server.ext <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=serverAuth
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always
subjectAltName=DNS:localhost,DNS:ingestion,DNS:ingestion.threat-monitoring.svc,DNS:$external_dns
EOF

openssl x509 -req -in tls.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out tls.crt -days 90 -sha256 -extfile server.ext
printf 'Keep ca.key offline. Use ca.crt for client trust and tls.crt/tls.key on the HTTPS listener.\n'
