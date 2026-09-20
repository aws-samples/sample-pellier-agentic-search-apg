#!/usr/bin/env bash
# Start an isolated Pellier HMR stack: FastAPI on 8003 and Vite on 5173.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/pellier/backend"
FRONTEND_DIR="${REPO_ROOT}/pellier/frontend"
BACKEND_HOST="${PELLIER_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${PELLIER_BACKEND_PORT:-8003}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
BACKEND_PYTHON="${BACKEND_DIR}/.venv/bin/python"
BACKEND_PID=""
TUNNEL_PID=""

dotenv_value() {
  awk -F= -v key="$1" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' \
    "${BACKEND_DIR}/.env"
}

DB_CLUSTER_ARN="$(dotenv_value DB_CLUSTER_ARN)"
DB_SECRET_ARN="$(dotenv_value DB_SECRET_ARN)"
CONFIGURED_AWS_REGION="$(dotenv_value AWS_REGION)"
CLUSTER_AWS_REGION="$(awk -F: '/^arn:/{ print $4; exit }' <<<"${DB_CLUSTER_ARN}")"
# A shell-wide AWS_REGION can belong to another local workshop. The configured
# cluster ARN is authoritative for this isolated Pellier stack.
AWS_REGION="${PELLIER_SSM_TUNNEL_REGION:-${CLUSTER_AWS_REGION:-${CONFIGURED_AWS_REGION:-${AWS_REGION:-us-east-1}}}}"
REMOTE_DB_HOST="${PELLIER_SSM_TUNNEL_REMOTE_HOST:-$(dotenv_value DB_HOST)}"
REMOTE_DB_PORT="${PELLIER_SSM_TUNNEL_REMOTE_PORT:-$(dotenv_value DB_PORT)}"
REMOTE_DB_PORT="${REMOTE_DB_PORT:-5432}"
TUNNEL_LOCAL_PORT="${PELLIER_SSM_TUNNEL_LOCAL_PORT:-15432}"

discover_tunnel_target() {
  [[ -n "${DB_CLUSTER_ARN}" ]] || return 0

  local cluster_id security_group descriptions
  cluster_id="${DB_CLUSTER_ARN##*:cluster:}"
  security_group="$(
    aws rds describe-db-clusters \
      --region "${AWS_REGION}" \
      --db-cluster-identifier "${cluster_id}" \
      --query 'DBClusters[0].VpcSecurityGroups[0].VpcSecurityGroupId' \
      --output text 2>/dev/null || true
  )"
  [[ -n "${security_group}" && "${security_group}" != "None" ]] || return 0

  descriptions="$(
    aws ec2 describe-security-groups \
      --region "${AWS_REGION}" \
      --group-ids "${security_group}" \
      --query "SecurityGroups[0].IpPermissions[].UserIdGroupPairs[?starts_with(Description, 'Pellier via SSM tunnel')].Description[]" \
      --output text 2>/dev/null || true
  )"
  awk 'NF { print $NF; exit }' <<<"${descriptions}"
}

# Session Manager can close an idle or interrupted session while the API and
# Vite remain alive. Keep their existing database endpoint available by opening
# a replacement session; the database pool reconnects through the same port.
maintain_tunnel() (
  local session_pid="" retry_delay=5 tunnel_started tunnel_status
  stop_session() {
    if [[ -n "${session_pid}" ]]; then
      # The CLI owns a session-manager-plugin child. Stop that child before its
      # parent so closing this launcher cannot leave its local port occupied.
      pkill -TERM -P "${session_pid}" 2>/dev/null || true
      kill "${session_pid}" 2>/dev/null || true
      wait "${session_pid}" 2>/dev/null || true
    fi
  }
  trap stop_session EXIT
  trap 'exit 0' INT TERM

  while true; do
    tunnel_started="${SECONDS}"
    aws ssm start-session \
      --region "${AWS_REGION}" \
      --target "${TUNNEL_TARGET}" \
      --document-name AWS-StartPortForwardingSessionToRemoteHost \
      --parameters "${tunnel_parameters}" &
    session_pid="$!"
    if wait "${session_pid}"; then tunnel_status=0; else tunnel_status=$?; fi
    session_pid=""
    if (( SECONDS - tunnel_started >= 60 )); then retry_delay=5; fi
    echo "Pellier Aurora tunnel ended (exit ${tunnel_status}); reconnecting in ${retry_delay}s." >&2
    sleep "${retry_delay}"
    if (( retry_delay < 60 )); then retry_delay=$((retry_delay * 2)); fi
    if (( retry_delay > 60 )); then retry_delay=60; fi
  done
)

cleanup() {
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi
  if [[ -n "${TUNNEL_PID}" ]] && kill -0 "${TUNNEL_PID}" 2>/dev/null; then
    kill "${TUNNEL_PID}" 2>/dev/null || true
    wait "${TUNNEL_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [[ ! -x "${BACKEND_PYTHON}" ]]; then
  echo "Pellier backend virtual environment is missing: ${BACKEND_PYTHON}" >&2
  echo "Create it with: cd pellier/backend && python3 -m venv .venv" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to verify the local Pellier API." >&2
  exit 1
fi

TUNNEL_TARGET="${PELLIER_SSM_TUNNEL_TARGET:-$(discover_tunnel_target)}"
if [[ -n "${TUNNEL_TARGET}" ]]; then
  if ! command -v aws >/dev/null 2>&1 \
    || ! command -v session-manager-plugin >/dev/null 2>&1 \
    || ! command -v jq >/dev/null 2>&1; then
    echo "AWS CLI, session-manager-plugin, and jq are required for the Pellier SSM tunnel." >&2
    exit 1
  fi
  if [[ -z "${REMOTE_DB_HOST}" || -z "${DB_SECRET_ARN}" ]]; then
    echo "DB_HOST and DB_SECRET_ARN are required for the Pellier SSM tunnel." >&2
    exit 1
  fi
  if command -v lsof >/dev/null 2>&1 \
    && lsof -nP -iTCP:"${TUNNEL_LOCAL_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Pellier SSM tunnel port ${TUNNEL_LOCAL_PORT} is already in use." >&2
    echo "Set PELLIER_SSM_TUNNEL_LOCAL_PORT to an unused port and rerun npm run dev." >&2
    exit 1
  fi

  tunnel_parameters="$(
    printf '{"host":["%s"],"portNumber":["%s"],"localPortNumber":["%s"]}' \
      "${REMOTE_DB_HOST}" "${REMOTE_DB_PORT}" "${TUNNEL_LOCAL_PORT}"
  )"
  maintain_tunnel &
  TUNNEL_PID="$!"

  for _ in {1..15}; do
    if command -v lsof >/dev/null 2>&1 \
      && lsof -nP -iTCP:"${TUNNEL_LOCAL_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "${TUNNEL_PID}" 2>/dev/null; then
      echo "Pellier SSM tunnel exited before opening local port ${TUNNEL_LOCAL_PORT}." >&2
      exit 1
    fi
    sleep 1
  done

  if ! lsof -nP -iTCP:"${TUNNEL_LOCAL_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Pellier SSM tunnel did not open local port ${TUNNEL_LOCAL_PORT}." >&2
    exit 1
  fi

  secret_json="$(
    aws secretsmanager get-secret-value \
      --region "${AWS_REGION}" \
      --secret-id "${DB_SECRET_ARN}" \
      --query SecretString \
      --output text
  )"
  export DB_HOST="127.0.0.1"
  export DB_TUNNEL_REMOTE_HOST="${REMOTE_DB_HOST}"
  export DB_PORT="${TUNNEL_LOCAL_PORT}"
  DB_USER="$(jq -er '.username | select(type == "string" and length > 0)' <<<"${secret_json}")"
  DB_PASSWORD="$(jq -er '.password | select(type == "string" and length > 0)' <<<"${secret_json}")"
  export DB_USER DB_PASSWORD
  export DATABASE_URL=""
  # The SSM leg is encrypted, and PostgreSQL must verify the Aurora endpoint
  # on the remaining leg too. Cache only the public AWS CA bundle, no secrets.
  "${BACKEND_PYTHON}" - <<'PY'
from pathlib import Path
import os
import urllib.request

certificate = Path(os.environ["DB_SSLROOTCERT"]).expanduser() if os.environ.get("DB_SSLROOTCERT") else (
    Path.home() / ".cache" / "pellier" / "rds-global-bundle.pem"
)
if not certificate.is_file():
    certificate.parent.mkdir(parents=True, exist_ok=True)
    data = urllib.request.urlopen(
        "https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem", timeout=20
    ).read()
    if b"-----BEGIN CERTIFICATE-----" not in data:
        raise SystemExit("The AWS RDS CA download did not contain a certificate bundle.")
    temporary = certificate.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.chmod(0o600)
    temporary.replace(certificate)
PY
fi

if command -v lsof >/dev/null 2>&1 \
  && lsof -nP -iTCP:"${BACKEND_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Pellier local backend port ${BACKEND_PORT} is already in use." >&2
  echo "Set PELLIER_BACKEND_PORT to an unused port and rerun npm run dev." >&2
  exit 1
fi

(
  cd "${BACKEND_DIR}"
  exec "${BACKEND_PYTHON}" -m uvicorn app:app \
    --reload \
    --host "${BACKEND_HOST}" \
    --port "${BACKEND_PORT}"
) &
BACKEND_PID="$!"

for _ in {1..45}; do
  if curl -fsS --max-time 2 "${BACKEND_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    echo "Pellier API exited before it became healthy." >&2
    echo "Check pellier/backend/.env, especially whether DB_HOST resolves." >&2
    exit 1
  fi
  sleep 1
done

if ! curl -fsS --max-time 2 "${BACKEND_URL}/api/health" >/dev/null 2>&1; then
  echo "Pellier API did not become healthy within 45 seconds." >&2
  echo "Check pellier/backend/.env, especially whether DB_HOST resolves." >&2
  exit 1
fi

cd "${FRONTEND_DIR}"
if [[ "$#" -eq 0 ]]; then
  set -- --host 127.0.0.1
fi

# HMR must stay same-origin so every client uses the Vite proxy below.
VITE_API_URL="" \
VITE_API_BASE_URL="" \
VITE_BASE_PATH="/" \
VITE_BACKEND_TARGET="${BACKEND_URL}" \
  npm run dev:vite -- "$@"
