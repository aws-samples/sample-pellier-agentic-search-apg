#!/bin/bash
# Pellier - Seed sample preferences for test users 1, 2, 3.
#
# Participants who sign in as one of these users immediately see a personalized
# storefront (reinforces the agentic AI story before they touch the preferences
# modal). Critical for the Builders Session C9 demo.
#
# Requires env vars:
#   COGNITO_USER_POOL_ID
#   COGNITO_CLIENT_ID
#   COGNITO_CLIENT_SECRET_ARN        (optional; falls back to no-secret auth)
#   COGNITO_TEST_CREDENTIALS_SECRET_ARN
#   AWS_REGION
#   BACKEND_URL                      (default: http://localhost:8000)

set -uo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"

log() { echo "[seed-sample-preferences] $*"; }
warn() { echo "[seed-sample-preferences][WARN] $*" >&2; }

# --- Guard rails -----------------------------------------------------------
for var in COGNITO_USER_POOL_ID COGNITO_CLIENT_ID COGNITO_TEST_CREDENTIALS_SECRET_ARN; do
    if [ -z "${!var:-}" ]; then
        warn "$var not set - skipping preference seeding"
        exit 0
    fi
done

# Wait for backend to be up (max 60s)
for _ in {1..30}; do
    if curl -fsS "$BACKEND_URL/api/health" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

if ! curl -fsS "$BACKEND_URL/api/health" >/dev/null 2>&1; then
    warn "Backend $BACKEND_URL/api/health not reachable - skipping preference seeding"
    exit 0
fi

# --- Load test user credentials --------------------------------------------
CREDS_JSON=$(aws secretsmanager get-secret-value \
    --secret-id "$COGNITO_TEST_CREDENTIALS_SECRET_ARN" \
    --region "$AWS_REGION" \
    --query SecretString --output text 2>/dev/null || echo "")

if [ -z "$CREDS_JSON" ]; then
    warn "Could not retrieve test credentials secret"
    exit 0
fi

CLIENT_SECRET=""
if [ -n "${COGNITO_CLIENT_SECRET_ARN:-}" ]; then
    CLIENT_SECRET=$(aws secretsmanager get-secret-value \
        --secret-id "$COGNITO_CLIENT_SECRET_ARN" \
        --region "$AWS_REGION" \
        --query SecretString --output text 2>/dev/null | jq -r '.client_secret // empty' || echo "")
fi

# --- Preference sets -------------------------------------------------------
# Keep order aligned with storefront.md: overall vibe, colors, where worn,
# categories. Backend stores them as a single tag list for personalization.
declare -A PREFS
PREFS[1]='["minimal","serene","neutral","linen","slow"]'
PREFS[2]='["bold","creative","warm","evening","dresses"]'
PREFS[3]='["adventurous","earth","outdoor","outerwear","travel"]'

# --- Auth helper -----------------------------------------------------------
compute_secret_hash() {
    local username="$1"
    if [ -z "$CLIENT_SECRET" ]; then return 0; fi
    printf '%s' "${username}${COGNITO_CLIENT_ID}" \
        | openssl dgst -sha256 -hmac "$CLIENT_SECRET" -binary \
        | base64
}

auth_user() {
    local username="$1" password="$2"
    local auth_params secret_hash
    if [ -n "$CLIENT_SECRET" ]; then
        secret_hash=$(compute_secret_hash "$username")
        auth_params=$(jq -n \
            --arg u "$username" --arg p "$password" --arg s "$secret_hash" \
            '{USERNAME:$u, PASSWORD:$p, SECRET_HASH:$s}')
    else
        auth_params=$(jq -n \
            --arg u "$username" --arg p "$password" \
            '{USERNAME:$u, PASSWORD:$p}')
    fi
    aws cognito-idp admin-initiate-auth \
        --user-pool-id "$COGNITO_USER_POOL_ID" \
        --client-id "$COGNITO_CLIENT_ID" \
        --auth-flow ADMIN_USER_PASSWORD_AUTH \
        --auth-parameters "$auth_params" \
        --region "$AWS_REGION" \
        --query 'AuthenticationResult.IdToken' --output text 2>/dev/null
}

# --- Seed ------------------------------------------------------------------
for n in 1 2 3; do
    username=$(echo "$CREDS_JSON" | jq -r ".users[$((n-1))].username // empty")
    password=$(echo "$CREDS_JSON" | jq -r ".users[$((n-1))].password // empty")

    if [ -z "$username" ] || [ -z "$password" ]; then
        warn "User $n not found in credentials secret - skipping"
        continue
    fi

    id_token=$(auth_user "$username" "$password")
    if [ -z "$id_token" ] || [ "$id_token" = "None" ]; then
        warn "Auth failed for $username - skipping"
        continue
    fi

    body=$(jq -n --argjson prefs "${PREFS[$n]}" '{preferences: $prefs}')
    http_code=$(curl -sS -o /tmp/seed-pref-resp.json -w "%{http_code}" \
        -X POST "$BACKEND_URL/api/user/preferences" \
        -H "Authorization: Bearer $id_token" \
        -H "Content-Type: application/json" \
        -d "$body")

    if [ "$http_code" = "200" ] || [ "$http_code" = "204" ]; then
        log "user-$n preferences seeded: ${PREFS[$n]}"
    else
        warn "user-$n preferences POST returned HTTP $http_code"
        cat /tmp/seed-pref-resp.json >&2 || true
    fi
done

log "Sample preference seeding complete"
exit 0
