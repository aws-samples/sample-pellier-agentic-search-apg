#!/usr/bin/env bash
# Run as root on the private workshop host. Publish the public certificate only.
set -euo pipefail
umask 077

: "${PELLIER_ORIGIN_SERVER_NAME:?TLS server name is required}"
: "${PELLIER_ORIGIN_CERT_SECRET_ARN:?Public certificate secret is required}"
: "${AWS_REGION:?AWS Region is required}"
[[ "$PELLIER_ORIGIN_SERVER_NAME" =~ ^[a-z0-9.-]+$ ]] || exit 1
TLS_DIR="${PELLIER_TLS_DIR:-/etc/pellier/tls}"
install -d -m 0700 "$TLS_DIR"

# Reboots reuse the same key and trust anchor. Rotation replaces the host and
# browser workspace together through InfrastructureRevision; never silently
# replace the certificate underneath a running proxy's trust store.
if [[ ! -e "$TLS_DIR/origin.crt" && ! -e "$TLS_DIR/origin.key" ]]; then
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
        -sha256 -days 90 -subj "/CN=$PELLIER_ORIGIN_SERVER_NAME" \
        -addext "subjectAltName=DNS:$PELLIER_ORIGIN_SERVER_NAME" \
        -addext 'basicConstraints=critical,CA:FALSE' \
        -addext 'keyUsage=critical,digitalSignature' \
        -addext 'extendedKeyUsage=serverAuth' \
        -keyout "$TLS_DIR/origin.key" -out "$TLS_DIR/origin.crt"
fi
test -s "$TLS_DIR/origin.key"
test -s "$TLS_DIR/origin.crt"
chmod 0600 "$TLS_DIR/origin.key" "$TLS_DIR/origin.crt"
openssl x509 -in "$TLS_DIR/origin.crt" -noout -checkend 86400
openssl verify -CAfile "$TLS_DIR/origin.crt" \
    -verify_hostname "$PELLIER_ORIGIN_SERVER_NAME" -purpose sslserver "$TLS_DIR/origin.crt"
test "$(openssl pkey -in "$TLS_DIR/origin.key" -pubout 2>/dev/null)" = \
    "$(openssl x509 -in "$TLS_DIR/origin.crt" -pubkey -noout)"
aws secretsmanager put-secret-value --region "$AWS_REGION" \
    --secret-id "$PELLIER_ORIGIN_CERT_SECRET_ARN" \
    --secret-string "file://$TLS_DIR/origin.crt" --output json > /dev/null
