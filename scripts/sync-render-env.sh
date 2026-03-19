#!/usr/bin/env bash

set -euo pipefail

RENDER_API_BASE="${RENDER_API_BASE:-https://api.render.com/v1}"
RENDER_API_KEY="${RENDER_API_KEY:-}"
RENDER_SERVICE_ID="${RENDER_SERVICE_ID:-}"
RENDER_SERVICE_NAME="${RENDER_SERVICE_NAME:-}"
BACKEND_URL="${BACKEND_URL:-https://cookhero-collab-20260215.onrender.com}"
MCP_DIET_SERVICE_KEY="${MCP_DIET_SERVICE_KEY:-}"
VERIFY_OPENAPI_PATHS="${VERIFY_OPENAPI_PATHS:-}"

TRIGGER_DEPLOY=false
VERIFY_ENDPOINT=true
WAIT_SECONDS="${WAIT_SECONDS:-240}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-8}"
VERIFY_CONNECT_TIMEOUT_SECONDS="${VERIFY_CONNECT_TIMEOUT_SECONDS:-10}"
VERIFY_MAX_TIME_SECONDS="${VERIFY_MAX_TIME_SECONDS:-20}"
RENDER_DEPLOY_ID=""
RENDER_SERVICE_DETAILS=""

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [options]

Options:
  --service-id <id>               Render service id (optional)
  --service-name <name>           Render service name (optional)
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
  BACKEND_URL
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

normalize_url() {
  jq -nr --arg value "$1" '$value | ascii_downcase | sub("/+$"; "")'
}

extract_service_object() {
  echo "$1" | jq -c '(.service // .)'
}

service_name_from_json() {
  echo "$1" | jq -r '.name // empty'
}

service_type_from_json() {
  echo "$1" | jq -r '.type // .serviceType // empty'
}

service_url_from_json() {
  echo "$1" | jq -r '.serviceDetails.url // .url // empty'
}

service_slug_from_json() {
  echo "$1" | jq -r '.slug // empty'
}

service_branch_from_json() {
  echo "$1" | jq -r '
    .branch //
    .repoDetails.branch //
    .serviceDetails.branch //
    .gitRepoSettings.branch //
    empty
  '
}

service_owner_id_from_json() {
  echo "$1" | jq -r '
    .ownerId //
    .owner.id //
    .serviceDetails.ownerId //
    empty
  '
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

fetch_service_details_by_id() {
  render_request "GET" "${RENDER_API_BASE}/services/${RENDER_SERVICE_ID}"

  if [[ "${RENDER_STATUS_CODE}" != "200" ]]; then
    log_error "Failed to retrieve Render service ${RENDER_SERVICE_ID}, status=${RENDER_STATUS_CODE}"
    echo "${RENDER_RESPONSE_BODY}" >&2
    return 1
  fi

  RENDER_SERVICE_DETAILS="$(extract_service_object "${RENDER_RESPONSE_BODY}")"
  return 0
}

resolve_service_id_by_name() {
  local encoded_name
  encoded_name="$(urlencode "${RENDER_SERVICE_NAME}")"
  render_request "GET" "${RENDER_API_BASE}/services?name=${encoded_name}"

  if [[ "${RENDER_STATUS_CODE}" != "200" ]]; then
    log_error "Failed to list Render services by name, status=${RENDER_STATUS_CODE}"
    echo "${RENDER_RESPONSE_BODY}" >&2
    return 1
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
    return 1
  fi

  return 0
}

resolve_service_id_by_backend_url() {
  local normalized_backend_url
  normalized_backend_url="$(normalize_url "${BACKEND_URL}")"

  render_request "GET" "${RENDER_API_BASE}/services?limit=100"

  if [[ "${RENDER_STATUS_CODE}" != "200" ]]; then
    log_error "Failed to list Render services for backend url lookup, status=${RENDER_STATUS_CODE}"
    echo "${RENDER_RESPONSE_BODY}" >&2
    return 1
  fi

  RENDER_SERVICE_ID="$(
    echo "${RENDER_RESPONSE_BODY}" | jq -r --arg target "${normalized_backend_url}" '
      [
        .[]? |
        (.service? // .) |
        {
          id,
          direct_url: (.serviceDetails.url // .url // empty),
          slug: (.slug // empty)
        } |
        .candidate_urls = (
          [
            .direct_url,
            (
              if (.slug | length) > 0 then
                ("https://" + .slug + ".onrender.com")
              else
                empty
              end
            )
          ]
          | map(select(length > 0) | ascii_downcase | sub("/+$"; ""))
        ) |
        select(.candidate_urls | index($target))
      ][0].id // empty
    '
  )"

  if [[ -z "${RENDER_SERVICE_ID}" ]]; then
    log_error "Cannot find Render service id for backend url: ${BACKEND_URL}"
    return 1
  fi

  return 0
}

assert_service_matches_backend_url() {
  if [[ -z "${BACKEND_URL}" || -z "${RENDER_SERVICE_DETAILS}" ]]; then
    return 0
  fi

  local normalized_backend_url
  local normalized_service_url
  local slug
  local normalized_slug_url=""

  normalized_backend_url="$(normalize_url "${BACKEND_URL}")"
  normalized_service_url="$(normalize_url "$(service_url_from_json "${RENDER_SERVICE_DETAILS}")")"
  slug="$(service_slug_from_json "${RENDER_SERVICE_DETAILS}")"
  if [[ -n "${slug}" ]]; then
    normalized_slug_url="$(normalize_url "https://${slug}.onrender.com")"
  fi

  if [[ "${normalized_backend_url}" == "${normalized_service_url}" || "${normalized_backend_url}" == "${normalized_slug_url}" ]]; then
    return 0
  fi

  log_error "Resolved Render service does not match BACKEND_URL."
  log_error "BACKEND_URL=${BACKEND_URL}"
  log_error "service.url=$(service_url_from_json "${RENDER_SERVICE_DETAILS}")"
  if [[ -n "${slug}" ]]; then
    log_error "service.slug_url=https://${slug}.onrender.com"
  fi
  return 1
}

log_service_summary() {
  if [[ -z "${RENDER_SERVICE_DETAILS}" ]]; then
    return 0
  fi

  log_info "Render service resolved:"
  log_info "  id=${RENDER_SERVICE_ID}"
  log_info "  name=$(service_name_from_json "${RENDER_SERVICE_DETAILS}")"
  log_info "  type=$(service_type_from_json "${RENDER_SERVICE_DETAILS}")"
  log_info "  url=$(service_url_from_json "${RENDER_SERVICE_DETAILS}")"
  if [[ -n "$(service_branch_from_json "${RENDER_SERVICE_DETAILS}")" ]]; then
    log_info "  branch=$(service_branch_from_json "${RENDER_SERVICE_DETAILS}")"
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

  RENDER_DEPLOY_ID="$(
    echo "${RENDER_RESPONSE_BODY}" | jq -r '.id // .deploy.id // empty'
  )"
}

wait_for_render_deploy() {
  local deadline
  local status
  local normalized_status
  local commit_id

  if [[ -z "${RENDER_DEPLOY_ID}" ]]; then
    log_error "Triggered deploy response did not include deploy id."
    echo "${RENDER_RESPONSE_BODY}" >&2
    exit 1
  fi

  deadline=$((SECONDS + WAIT_SECONDS))

  while true; do
    if (( SECONDS > deadline )); then
      log_error "Timed out waiting for deploy ${RENDER_DEPLOY_ID} to finish."
      exit 1
    fi

    render_request "GET" "${RENDER_API_BASE}/services/${RENDER_SERVICE_ID}/deploys/${RENDER_DEPLOY_ID}"
    if [[ "${RENDER_STATUS_CODE}" != "200" ]]; then
      log_info "Deploy status fetch returned ${RENDER_STATUS_CODE}, retrying..."
      sleep "${POLL_INTERVAL_SECONDS}"
      continue
    fi

    status="$(
      echo "${RENDER_RESPONSE_BODY}" | jq -r '.status // .deploy.status // .state // .deploy.state // empty'
    )"
    commit_id="$(
      echo "${RENDER_RESPONSE_BODY}" | jq -r '.commit.id // .commit.commit.id // .commitId // empty'
    )"
    normalized_status="$(printf '%s' "${status}" | tr '[:upper:]' '[:lower:]')"

    case "${normalized_status}" in
      live|deployed|active|deploy_live|completed|success)
        log_info "Deploy ${RENDER_DEPLOY_ID} is live. status=${status} commit=${commit_id:-unknown}"
        return 0
        ;;
      failed|build_failed|update_failed|errored|error|canceled|cancelled)
        log_error "Deploy ${RENDER_DEPLOY_ID} failed. status=${status} commit=${commit_id:-unknown}"
        dump_recent_service_events
        dump_recent_build_logs
        echo "${RENDER_RESPONSE_BODY}" >&2
        exit 1
        ;;
      *)
        log_info "Deploy ${RENDER_DEPLOY_ID} still in progress. status=${status:-unknown} commit=${commit_id:-unknown}"
        sleep "${POLL_INTERVAL_SECONDS}"
        ;;
    esac
  done
}

dump_recent_service_events() {
  local tmp_body
  local status_code
  local start_time
  local end_time

  start_time="$(date -u -d '30 minutes ago' '+%Y-%m-%dT%H:%M:%SZ')"
  end_time="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  tmp_body="$(mktemp)"

  status_code="$(
    curl -sS -G \
      -o "${tmp_body}" \
      -w "%{http_code}" \
      "${RENDER_API_BASE}/services/${RENDER_SERVICE_ID}/events" \
      -H "Authorization: Bearer ${RENDER_API_KEY}" \
      --data-urlencode "startTime=${start_time}" \
      --data-urlencode "endTime=${end_time}" \
      --data-urlencode "limit=20" || true
  )"

  if [[ "${status_code}" != "200" ]]; then
    log_error "Render service event query failed, status=${status_code}"
    cat "${tmp_body}" >&2 || true
    rm -f "${tmp_body}"
    return 0
  fi

  log_info "Recent Render service events:"
  jq -c '.[]?.event | {timestamp, type, details}' "${tmp_body}" || true
  rm -f "${tmp_body}"
}

dump_recent_build_logs() {
  local owner_id
  local start_time
  local end_time
  local tmp_body
  local status_code

  owner_id="$(service_owner_id_from_json "${RENDER_SERVICE_DETAILS}")"
  if [[ -z "${owner_id}" ]]; then
    log_error "Cannot fetch Render build logs because ownerId is missing from service details."
    return 0
  fi

  start_time="$(date -u -d '30 minutes ago' '+%Y-%m-%dT%H:%M:%SZ')"
  end_time="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  tmp_body="$(mktemp)"

  status_code="$(
    curl -sS -G \
      -o "${tmp_body}" \
      -w "%{http_code}" \
      "${RENDER_API_BASE}/logs" \
      -H "Authorization: Bearer ${RENDER_API_KEY}" \
      --data-urlencode "ownerId=${owner_id}" \
      --data-urlencode "resource=${RENDER_SERVICE_ID}" \
      --data-urlencode "type=build" \
      --data-urlencode "startTime=${start_time}" \
      --data-urlencode "endTime=${end_time}" \
      --data-urlencode "direction=backward" \
      --data-urlencode "limit=100" || true
  )"

  if [[ "${status_code}" != "200" ]]; then
    log_error "Render build log query failed, status=${status_code}"
    cat "${tmp_body}" >&2 || true
    rm -f "${tmp_body}"
    return 0
  fi

  log_info "Recent Render build logs:"
  jq -r '.logs[]? | "[\(.timestamp)] \(.message)"' "${tmp_body}" || true
  rm -f "${tmp_body}"
}

openapi_missing_paths() {
  local openapi_json="$1"
  local required_csv="$2"

  python3 - "$openapi_json" "$required_csv" <<'PY'
import json
import sys

openapi_path = sys.argv[1]
required = [item for item in sys.argv[2].split("|") if item]
try:
    with open(openapi_path, "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    print("OPENAPI_PARSE_ERROR")
    raise SystemExit(0)

paths = data.get("paths") or {}
missing = [item for item in required if item not in paths]
print("|".join(missing))
PY
}

verify_backend_openapi_routes() {
  local endpoint
  local deadline
  local attempt
  local tmp_body
  local verify_code
  local missing

  if [[ -z "${VERIFY_OPENAPI_PATHS}" ]]; then
    return 0
  fi

  endpoint="${BACKEND_URL%/}/openapi.json"
  deadline=$((SECONDS + WAIT_SECONDS))
  attempt=0

  while true; do
    if (( SECONDS > deadline )); then
      log_error "Timed out waiting for backend OpenAPI route set: ${endpoint}"
      exit 1
    fi

    attempt=$((attempt + 1))
    tmp_body="$(mktemp)"
    verify_code="$(
      curl -sS \
        --connect-timeout "${VERIFY_CONNECT_TIMEOUT_SECONDS}" \
        --max-time "${VERIFY_MAX_TIME_SECONDS}" \
        -o "${tmp_body}" \
        -w "%{http_code}" \
        "${endpoint}" || true
    )"
    if [[ -z "${verify_code}" ]]; then
      verify_code="000"
    fi

    if [[ "${verify_code}" == "200" ]]; then
      missing="$(openapi_missing_paths "${tmp_body}" "${VERIFY_OPENAPI_PATHS}")"
      rm -f "${tmp_body}"

      if [[ -z "${missing}" ]]; then
        log_info "OpenAPI route guard passed on attempt ${attempt}."
        return 0
      fi

      if [[ "${missing}" == "OPENAPI_PARSE_ERROR" ]]; then
        log_info "OpenAPI parse failed on attempt ${attempt}, retrying..."
      else
        log_info "OpenAPI route guard missing: ${missing}; retrying..."
      fi
    else
      rm -f "${tmp_body}"
      log_info "OpenAPI returned ${verify_code} on attempt ${attempt}, retrying..."
    fi

    sleep "${POLL_INTERVAL_SECONDS}"
  done
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
  local error_message

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
        --connect-timeout "${VERIFY_CONNECT_TIMEOUT_SECONDS}" \
        --max-time "${VERIFY_MAX_TIME_SECONDS}" \
        -o "${tmp_body}" \
        -w "%{http_code}" \
        -X POST \
        "${endpoint}" \
        -H "Content-Type: application/json" \
        -H "X-MCP-Service-Key: ${MCP_DIET_SERVICE_KEY}" \
        --data "${payload}" || true
    )"
    if [[ -z "${verify_code}" ]]; then
      verify_code="000"
    fi
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
      error_message="$(echo "${verify_body}" | jq -r '.error.message // empty' 2>/dev/null || true)"
      if [[ -n "${error_message}" ]]; then
        log_info "MCP endpoint not ready on attempt ${attempt}, status=${verify_code}, message=${error_message}, retrying..."
      else
        log_info "MCP endpoint not ready on attempt ${attempt}, status=${verify_code}, retrying..."
      fi
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
if [[ -n "${VERIFY_OPENAPI_PATHS}" ]]; then
  require_command "python3"
fi

if [[ -z "${RENDER_API_KEY}" ]]; then
  log_error "RENDER_API_KEY is required."
  exit 1
fi

if [[ -z "${MCP_DIET_SERVICE_KEY}" ]]; then
  log_error "MCP_DIET_SERVICE_KEY is required."
  exit 1
fi

if [[ -z "${RENDER_SERVICE_ID}" && -z "${RENDER_SERVICE_NAME}" && -z "${BACKEND_URL}" ]]; then
  log_error "Provide RENDER_SERVICE_ID, RENDER_SERVICE_NAME, or BACKEND_URL."
  exit 1
fi

original_service_id="${RENDER_SERVICE_ID}"
name_resolved_service_id=""
url_resolved_service_id=""

# Prefer resolving by service name (ids can drift when services are recreated).
# If resolving by name fails, fall back to the explicitly provided id.
if [[ -n "${RENDER_SERVICE_NAME}" ]]; then
  log_info "Resolving Render service id by name: ${RENDER_SERVICE_NAME}"
  if resolve_service_id_by_name; then
    name_resolved_service_id="${RENDER_SERVICE_ID}"
    if [[ -n "${original_service_id}" && "${original_service_id}" != "${RENDER_SERVICE_ID}" ]]; then
      log_info "Provided RENDER_SERVICE_ID differs from resolved id; using resolved id=${RENDER_SERVICE_ID}."
    fi
  else
    if [[ -n "${original_service_id}" ]]; then
      RENDER_SERVICE_ID="${original_service_id}"
      log_error "Failed to resolve service id by name; falling back to provided RENDER_SERVICE_ID=${RENDER_SERVICE_ID}."
    else
      exit 1
    fi
  fi
fi

if [[ -n "${BACKEND_URL}" ]]; then
  log_info "Resolving Render service id by backend URL: ${BACKEND_URL}"
  if resolve_service_id_by_backend_url; then
    url_resolved_service_id="${RENDER_SERVICE_ID}"
    if [[ -n "${name_resolved_service_id}" && "${name_resolved_service_id}" != "${url_resolved_service_id}" ]]; then
      log_info "Service name and backend URL resolved to different ids; preferring backend URL match=${url_resolved_service_id}."
    fi
  else
    if [[ -z "${original_service_id}" && -z "${name_resolved_service_id}" ]]; then
      exit 1
    fi
    log_info "Backend URL lookup failed; falling back to previously resolved Render service id."
  fi
fi

if [[ -n "${url_resolved_service_id}" ]]; then
  RENDER_SERVICE_ID="${url_resolved_service_id}"
elif [[ -n "${name_resolved_service_id}" ]]; then
  RENDER_SERVICE_ID="${name_resolved_service_id}"
else
  RENDER_SERVICE_ID="${original_service_id}"
fi

if [[ -z "${RENDER_SERVICE_ID}" ]]; then
  log_error "Render service id is empty after resolution."
  exit 1
fi

fetch_service_details_by_id
assert_service_matches_backend_url
log_service_summary

log_info "Syncing MCP_DIET_SERVICE_KEY to Render service: ${RENDER_SERVICE_ID}"
upsert_mcp_service_key
log_info "Render env var sync completed."

if [[ "${TRIGGER_DEPLOY}" == "true" ]]; then
  log_info "Triggering Render deploy..."
  trigger_render_deploy
  wait_for_render_deploy
fi

verify_backend_openapi_routes

if [[ "${VERIFY_ENDPOINT}" == "true" ]]; then
  log_info "Verifying MCP endpoint after sync..."
  verify_mcp_endpoint
fi

log_info "All done."
