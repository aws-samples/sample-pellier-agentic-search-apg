#!/bin/bash
# Pellier - Write human-readable test credentials file.
#
# Pulls the seeded Cognito test users out of Secrets Manager and writes
# them to /home/<user>/test-credentials.txt for workshop participants.
#
# Requires env vars:
#   COGNITO_TEST_CREDENTIALS_SECRET_ARN
#   COGNITO_HOSTED_UI_URL
#   AWS_REGION
#   CODE_EDITOR_USER                 (default: workshop)
#   HOME_FOLDER                      (default: /home/<user>)

set -uo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
CODE_EDITOR_USER="${CODE_EDITOR_USER:-workshop}"
HOME_FOLDER="${HOME_FOLDER:-/home/$CODE_EDITOR_USER}"
OUT_FILE="${OUT_FILE:-$HOME_FOLDER/test-credentials.txt}"

log() { echo "[write-test-credentials] $*"; }
warn() { echo "[write-test-credentials][WARN] $*" >&2; }

if [ -z "${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}" ]; then
    warn "COGNITO_TEST_CREDENTIALS_SECRET_ARN not set - skipping"
    exit 0
fi

CREDS_JSON=$(aws secretsmanager get-secret-value \
    --secret-id "$COGNITO_TEST_CREDENTIALS_SECRET_ARN" \
    --region "$AWS_REGION" \
    --query SecretString --output text 2>/dev/null || echo "")

if [ -z "$CREDS_JSON" ]; then
    warn "Could not retrieve test credentials secret"
    exit 1
fi

# Illustrative personalization preferences seeded onto each sign-in account
# (users 1/2/3 = Marco/Anna/Theo) - kept in sync with seed-sample-preferences.sh.
# These are a demo signal for signed-in personalization and are deliberately
# INDEPENDENT of the persona's editorial profile: the persona (picked by the
# in-app switch) answers "whose data"; this account preference answers "how to
# rank for this login". They need not match, by design.
declare -A PREF_LABEL
PREF_LABEL[1]="minimal, serene, neutral, linen, slow"
PREF_LABEL[2]="bold, creative, warm, evening, dresses"
PREF_LABEL[3]="adventurous, earth, outdoor, outerwear, travel"

HOSTED_UI="${COGNITO_HOSTED_UI_URL:-<hosted-ui-url>}"

{
    echo "============================================================="
    echo "Pellier Workshop Test Credentials"
    echo "============================================================="
    echo "These are throwaway credentials for workshop use only."
    echo "DO NOT use for any production system."
    echo ""
    echo "Sign-in URL: $HOSTED_UI"
    echo ""

    num_users=$(echo "$CREDS_JSON" | jq -r '.users | length')
    for i in $(seq 0 $((num_users - 1))); do
        n=$((i + 1))
        username=$(echo "$CREDS_JSON" | jq -r ".users[$i].username")
        password=$(echo "$CREDS_JSON" | jq -r ".users[$i].password")
        echo "Username: $username"
        echo "Password: $password"
        if [ -n "${PREF_LABEL[$n]:-}" ]; then
            echo "Seeded personalization signal (illustrative): ${PREF_LABEL[$n]}"
        fi
        echo ""
    done

    echo "============================================================="
} > "$OUT_FILE"

chmod 0600 "$OUT_FILE"
if id "$CODE_EDITOR_USER" &>/dev/null; then
    chown "$CODE_EDITOR_USER:$CODE_EDITOR_USER" "$OUT_FILE" 2>/dev/null || true
fi

log "Wrote $OUT_FILE (0600)"
exit 0
