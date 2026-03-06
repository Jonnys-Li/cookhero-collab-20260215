#!/usr/bin/env bash

set -euo pipefail

RENDER_API_BASE="${RENDER_API_BASE:-https://api.render.com/v1}"
RENDER_API_KEY="${RENDER_API_KEY:-}"
RENDER_SERVICE_ID="${RENDER_SERVICE_ID:-}"
RENDER_SERVICE_NAME="${RENDER_SERVICE_NAME:-cookhero-backend}"
BACKEND_URL="${BACKEND_URL:-https://cookhero-collab-20260215.onrender.com}"
MCP_DIET_SERVICE_KEY="${MCP_DIET_SERVICE_KEY:-}"

TRIGGER_DEPLOY=false
VERIFY_ENDPOINT=true
WAIT_SECONDS="${WAIT_SECONDS:-240}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-8}"

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [options]

Options:
  --service-id <id>               Render service id (optional)
  --service-name <name>           Render service name (default: ${RENDER_SERVICE_NAME})
  --backend-url <url>             Backend base url (default: ${BACKEND_URL})
  --wait-seconds <n>              Wait seconds for verify polling (default: ${WAIT_SECONDS})
  --poll-interval-seconds <n>     Polling interval seconds (default: ${POLL_INTERVAL_SECONDS})
  --trigger-deploy                Trigger Render deploy after env update
  --no-verify                     Skip MCP endpoint verification
  -h, --help                      Show this help message

Required environment variables:
  RENDER_API_KEY
  MCP_DIET_SERVICE_KEY

One of these must be provided:
  RENDER_SERVICE_ID
  RENDER_SERVICE_NAME
EOF
}

log_info() {
  echo "[INFO] $1"
}

log_error() {
  echo "[ERROR] $1" >&2
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    log_error "Missing required command: ${command_name}"
    exit 1
  fi
}

urlencode() {
  jq -nr --arg value "$1" '$value|@uri'
}

render_request() {
  local method="$1"
  local url="$2"
  local data="${3:-}"
  local tmp_body

  tmp_body="$(mktemp)"
  if [[ -n "${data}" ]]; then
    RENDER_STATUS_CODE="$(
      curl -sS \
        -o "${tmp_body}" \
        -w "%{http_code}" \
        -X "${method}" \
        "${url}" \
        -H "Authorization: Bearer ${RENDER_API_KEY}" \
        -H "Content-Type: application/json" \
        --data "${data}"
    )"
  else
    RENDER_STATUS_CODE="$(
      curl -sS \
        -o "${tmp_body}" \
        -w "%{http_code}" \
        -X "${method}" \
        "${url}" \
        -H "Authorization: Bearer ${RENDER_API_KEY}"
    )"
  fi
  RENDER_RESPONSE_BODY="$(cat "${tmp_body}")"
  rm -f "${tmp_body}"
}

resolve_service_id_by_name() {
  local encoded_name
  encoded_name="$(urlencode "${RENDER_SERVICE_NAME}")"
  render_request "GET" "${RENDER_API_BASE}/services?name=${encoded_name}"

  if [[ "${RENDER_STATUS_CODE}" != "200" ]]; then
    log_error "Failed to list Render services by name, status=${RENDER_STATUS_CODE}"
    echo "${RENDER_RESPONSE_BODY}" >&2
    exit 1
  fi

  RENDER_SERVICE_ID="$(
    echo "${RENDER_RESPONSE_BODY}" | jq -r --arg service_name "${RENDER_SERVICE_NAME}" '
      [
        .[]? |
        (
          .service? // .
        ) |
        select(.name == $service_name) |
        .id
      ][0] // empty
    '
  )"

  if [[ -z "${RENDER_SERVICE_ID}" ]]; then
    log_error "Cannot find Render service id for name: ${RENDER_SERVICE_NAME}"
    exit 1
  fi
}

upsert_mcp_service_key() {
  local payload
  payload="$(jq -nc --arg value "${MCP_DIET_SERVICE_KEY}" '{value:$value}')"

  render_request \
    "PUT" \
    "${RENDER_API_BASE}/services/${RENDER_SERVICE_ID}/env-vars/MCP_DIET_SERVICE_KEY" \
    "${payload}"

  if [[ "${RENDER_STATUS_CODE}" != "200" ]]; then
    log_error "Failed to update MCP_DIET_SERVICE_KEY on Render, status=${RENDER_STATUS_CODE}"
    echo "${RENDER_RESPONSE_BODY}" >&2
    exit 1
  fi
}

trigger_render_deploy() {
  local payload
  payload='{"clearCache":"do_not_clear"}'
  render_request \
    "POST" \
    "${RENDER_API_BASE}/services/${RENDER_SERVICE_ID}/deploys" \
    "${payload}"

  if [[ "${RENDER_STATUS_CODE}" != "201" && "${RENDER_STATUS_CODE}" != "202" ]]; then
    log_error "Failed to trigger Render deploy, status=${RENDER_STATUS_CODE}"
    echo "${RENDER_RESPONSE_BODY}" >&2
    exit 1
  fi
}

verify_mcp_endpoint() {
  local endpoint
  local deadline
  local tmp_body
  local attempt
  local current_time
  local verify_code
  local verify_body
  local tool_count
  local payload

  endpoint="${BACKEND_URL%/}/api/v1/mcp/diet-adjust"
  payload='{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
  deadline=$((SECONDS + WAIT_SECONDS))
  attempt=0

  while true; do
    current_time=${SECONDS}
    if (( current_time > deadline )); then
      log_error "Timed out waiting for MCP endpoint readiness: ${endpoint}"
      exit 1
    fi

    attempt=$((attempt + 1))
    tmp_body="$(mktemp)"
    verify_code="$(
      curl -sS \
        -o "${tmp_body}" \
        -w "%{http_code}" \
        -X POST \
        "${endpoint}" \
        -H "Content-Type: application/json" \
        -H "X-MCP-Service-Key: ${MCP_DIET_SERVICE_KEY}" \
        --data "${payload}"
    )"
    verify_body="$(cat "${tmp_body}")"
    rm -f "${tmp_body}"

    if [[ "${verify_code}" == "200" ]]; then
      tool_count="$(echo "${verify_body}" | jq -r '.result.tools | length // 0' 2>/dev/null || echo "0")"
      if [[ "${tool_count}" =~ ^[0-9]+$ ]] && (( tool_count > 0 )); then
        log_info "MCP endpoint ready on attempt ${attempt}: tools=${tool_count}"
        return 0
      fi
      log_info "MCP endpoint reachable but tools empty on attempt ${attempt}, retrying..."
    else
      log_info "MCP endpoint not ready on attempt ${attempt}, status=${verify_code}, retrying..."
    fi

    sleep "${POLL_INTERVAL_SECONDS}"
  done
}

while (($# > 0)); do
  case "$1" in
    --service-id)
      RENDER_SERVICE_ID="$2"
      shift 2
      ;;
    --service-name)
      RENDER_SERVICE_NAME="$2"
      shift 2
      ;;
    --backend-url)
      BACKEND_URL="$2"
      shift 2
      ;;
    --wait-seconds)
      WAIT_SECONDS="$2"
      shift 2
      ;;
    --poll-interval-seconds)
      POLL_INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --trigger-deploy)
      TRIGGER_DEPLOY=true
      shift
      ;;
    --no-verify)
      VERIFY_ENDPOINT=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log_error "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

require_command "curl"
require_command "jq"

if [[ -z "${RENDER_API_KEY}" ]]; then
  log_error "RENDER_API_KEY is required."
  exit 1
fi

if [[ -z "${MCP_DIET_SERVICE_KEY}" ]]; then
  log_error "MCP_DIET_SERVICE_KEY is required."
  exit 1
fi

if [[ -z "${RENDER_SERVICE_ID}" && -z "${RENDER_SERVICE_NAME}" ]]; then
  log_error "Provide RENDER_SERVICE_ID or RENDER_SERVICE_NAME."
  exit 1
fi

if [[ -z "${RENDER_SERVICE_ID}" ]]; then
  log_info "Resolving Render service id by name: ${RENDER_SERVICE_NAME}"
  resolve_service_id_by_name
fi

log_info "Syncing MCP_DIET_SERVICE_KEY to Render service: ${RENDER_SERVICE_ID}"
upsert_mcp_service_key
log_info "Render env var sync completed."

if [[ "${TRIGGER_DEPLOY}" == "true" ]]; then
  log_info "Triggering Render deploy..."
  trigger_render_deploy
fi

if [[ "${VERIFY_ENDPOINT}" == "true" ]]; then
  log_info "Verifying MCP endpoint after sync..."
  verify_mcp_endpoint
fi

log_info "All done."
