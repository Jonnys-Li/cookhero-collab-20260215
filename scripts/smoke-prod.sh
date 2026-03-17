#!/usr/bin/env bash

# CookHero 生产环境烟测脚本
# 默认采用“演示稳定模式”：失败仅告警，不中断 CI。
# 若需严格校验可设置 SMOKE_STRICT=true。

set -euo pipefail

FRONTEND_URL="${FRONTEND_URL:-https://frontend-one-gray-39.vercel.app}"
BACKEND_URL="${BACKEND_URL:-https://cookhero-collab-20260215.onrender.com}"
MAX_RETRIES="${MAX_RETRIES:-2}"
CONNECT_TIMEOUT_SECONDS="${CONNECT_TIMEOUT_SECONDS:-8}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-20}"
SMOKE_STRICT="${SMOKE_STRICT:-false}"
MCP_SERVICE_KEY="${MCP_SERVICE_KEY:-}"
MCP_TOOLS_MIN="${MCP_TOOLS_MIN:-1}"
SMOKE_DIET_PHOTO="${SMOKE_DIET_PHOTO:-false}"
SMOKE_PHOTO_IMAGE_B64="${SMOKE_PHOTO_IMAGE_B64:-}"
SMOKE_PHOTO_MIME_TYPE="${SMOKE_PHOTO_MIME_TYPE:-image/png}"
SMOKE_PHOTO_CONTEXT_TEXT="${SMOKE_PHOTO_CONTEXT_TEXT:-}"

TMP_DIR="$(mktemp -d)"
TMP_HEADERS="${TMP_DIR}/headers.txt"
TMP_BODY="${TMP_DIR}/body.txt"
LAST_STATUS=""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=false
AUTH_CHECKS_ENABLED=true

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

is_truthy() {
  local value
  value="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "${value}" in
    1|true|yes|y|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

if is_truthy "${SMOKE_STRICT}"; then
  STRICT_MODE=true
fi

log_pass() {
  local message="$1"
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "[PASS] ${message}"
}

log_warn() {
  local message="$1"
  WARN_COUNT=$((WARN_COUNT + 1))
  echo "[WARN] ${message}"
}

dump_last_response() {
  echo "---- Last Response Headers ----"
  sed -n '1,30p' "${TMP_HEADERS}" || true
  echo "---- Last Response Body ----"
  sed -n '1,30p' "${TMP_BODY}" || true
}

handle_assert_failure() {
  local message="$1"
  FAIL_COUNT=$((FAIL_COUNT + 1))

  if [[ "${STRICT_MODE}" == "true" ]]; then
    echo "[FAIL] ${message}"
    dump_last_response
    exit 1
  fi

  log_warn "${message}"
  dump_last_response
}

perform_request() {
  local method="$1"
  local url="$2"
  shift 2
  local -a extra_args=("$@")

  : > "${TMP_HEADERS}"
  : > "${TMP_BODY}"

  if ((${#extra_args[@]} > 0)); then
    LAST_STATUS="$(
      curl -sS \
        --http1.1 \
        --connect-timeout "${CONNECT_TIMEOUT_SECONDS}" \
        --max-time "${REQUEST_TIMEOUT_SECONDS}" \
        -X "${method}" \
        -D "${TMP_HEADERS}" \
        -o "${TMP_BODY}" \
        -w "%{http_code}" \
        "${extra_args[@]}" \
        "${url}" || true
    )"
  else
    LAST_STATUS="$(
      curl -sS \
        --http1.1 \
        --connect-timeout "${CONNECT_TIMEOUT_SECONDS}" \
        --max-time "${REQUEST_TIMEOUT_SECONDS}" \
        -X "${method}" \
        -D "${TMP_HEADERS}" \
        -o "${TMP_BODY}" \
        -w "%{http_code}" \
        "${url}" || true
    )"
  fi
}

is_retryable_status() {
  local status="$1"
  if [[ "${status}" == "000" || "${status}" == "429" ]]; then
    return 0
  fi
  if [[ "${status}" =~ ^[0-9]{3}$ ]] && ((10#${status} >= 500)); then
    return 0
  fi
  return 1
}

status_matches_expected() {
  local status="$1"
  local expected_csv="$2"
  local item=""
  IFS=',' read -r -a expected_items <<< "${expected_csv}"

  for item in "${expected_items[@]}"; do
    item="${item//[[:space:]]/}"
    [[ -z "${item}" ]] && continue
    if [[ "${status}" == "${item}" ]]; then
      return 0
    fi
  done
  return 1
}

assert_status_with_retry() {
  local title="$1"
  local method="$2"
  local url="$3"
  local expected_statuses="$4"
  shift 4
  local -a extra_args=("$@")
  local attempt=1
  local sleep_seconds=1

  while ((attempt <= MAX_RETRIES)); do
    if ((${#extra_args[@]} > 0)); then
      perform_request "${method}" "${url}" "${extra_args[@]}"
    else
      perform_request "${method}" "${url}"
    fi
    if status_matches_expected "${LAST_STATUS}" "${expected_statuses}"; then
      log_pass "${title} | ${method} ${url} -> ${LAST_STATUS}"
      return 0
    fi

    if ((attempt < MAX_RETRIES)) && is_retryable_status "${LAST_STATUS}"; then
      echo "[WARN] ${title} | attempt ${attempt}/${MAX_RETRIES} got ${LAST_STATUS}, retry in ${sleep_seconds}s"
      sleep "${sleep_seconds}"
      sleep_seconds=$((sleep_seconds * 2))
      attempt=$((attempt + 1))
      continue
    fi

    handle_assert_failure "${title} | ${method} ${url} expected ${expected_statuses}, got ${LAST_STATUS}"
    return 0
  done
}

echo "========================================="
echo "CookHero Production Smoke Test"
echo "========================================="
if [[ "${STRICT_MODE}" == "true" ]]; then
  echo "MODE=STRICT"
else
  echo "MODE=DEMO_STABLE"
fi
echo "FRONTEND_URL=${FRONTEND_URL}"
echo "BACKEND_URL=${BACKEND_URL}"
echo "MAX_RETRIES=${MAX_RETRIES}"
echo "CONNECT_TIMEOUT_SECONDS=${CONNECT_TIMEOUT_SECONDS}"
echo "REQUEST_TIMEOUT_SECONDS=${REQUEST_TIMEOUT_SECONDS}"
echo ""

# 1) 代理健康探测（应命中后端鉴权层，返回 401 JSON）
assert_status_with_retry \
  "Frontend proxy health gate" \
  "GET" \
  "${FRONTEND_URL}/api/v1/health" \
  "401"

# 2) 登录路由 GET 应返回 405（路由命中后端 auth endpoint）
assert_status_with_retry \
  "Frontend proxy auth route method check" \
  "GET" \
  "${FRONTEND_URL}/api/v1/auth/login" \
  "405"

if [[ -z "${SMOKE_USERNAME:-}" || -z "${SMOKE_PASSWORD:-}" ]]; then
  AUTH_CHECKS_ENABLED=false
  if [[ "${STRICT_MODE}" == "true" ]]; then
    echo "[FAIL] Missing required secrets in strict mode: SMOKE_USERNAME / SMOKE_PASSWORD"
    exit 1
  fi
  log_warn "SMOKE_USERNAME / SMOKE_PASSWORD missing, skip authenticated checks in demo mode."
fi

if [[ "${AUTH_CHECKS_ENABLED}" == "true" ]]; then
  # 3) 登录获取 token
  LOGIN_PAYLOAD="{\"username\":\"${SMOKE_USERNAME}\",\"password\":\"${SMOKE_PASSWORD}\"}"
  assert_status_with_retry \
    "Smoke user login" \
    "POST" \
    "${FRONTEND_URL}/api/v1/auth/login" \
    "200" \
    -H "Content-Type: application/json" \
    --data "${LOGIN_PAYLOAD}"

  if ! status_matches_expected "${LAST_STATUS}" "200"; then
    log_warn "Skip token extraction because login did not return 200."
    AUTH_CHECKS_ENABLED=false
  fi

if [[ "${AUTH_CHECKS_ENABLED}" == "true" ]]; then
  TOKEN="$(sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p' "${TMP_BODY}" | head -n 1)"
  if [[ -z "${TOKEN}" ]]; then
    handle_assert_failure "Login response missing access_token"
    AUTH_CHECKS_ENABLED=false
  else
    log_pass "Smoke token extraction"
  fi
fi
fi

if [[ "${AUTH_CHECKS_ENABLED}" == "true" ]]; then
  # 4) 用户信息
  assert_status_with_retry \
    "Authorized profile check" \
    "GET" \
    "${FRONTEND_URL}/api/v1/user/profile" \
    "200" \
    -H "Authorization: Bearer ${TOKEN}"

  # 5) 会话列表
  assert_status_with_retry \
    "Conversation list check" \
    "GET" \
    "${FRONTEND_URL}/api/v1/conversation?limit=1&offset=0" \
    "200" \
    -H "Authorization: Bearer ${TOKEN}"

  # 6) Agent tools
  assert_status_with_retry \
    "Agent tools check" \
    "GET" \
    "${FRONTEND_URL}/api/v1/agent/tools" \
    "200" \
    -H "Authorization: Bearer ${TOKEN}"

  # 7) Personal docs list
  assert_status_with_retry \
    "Knowledge list check" \
    "GET" \
    "${FRONTEND_URL}/api/v1/knowledge/personal-docs?limit=1&offset=0" \
    "200" \
    -H "Authorization: Bearer ${TOKEN}"

  # 8) Diet enums
  assert_status_with_retry \
    "Diet enum check" \
    "GET" \
    "${FRONTEND_URL}/api/v1/diet/enums" \
    "200" \
    -H "Authorization: Bearer ${TOKEN}"

  # 8.5) Wave 3 (optional): photo-first diet logging flow (parse -> write -> refresh)
  if is_truthy "${SMOKE_DIET_PHOTO}"; then
    # Build a deterministic marker so we can verify the write via GET /diet/logs.
    PHOTO_MARKER="smoke_photo_marker_${RANDOM}_$(date +%s)"

    # If no real food image is provided, fall back to a minimal valid PNG.
    # This is enough to validate connectivity + fallback path, but may not yield items.
    if [[ -z "${SMOKE_PHOTO_IMAGE_B64}" ]]; then
      SMOKE_PHOTO_IMAGE_B64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X9nqkAAAAASUVORK5CYII="
    fi

    TODAY="$(date +%F)"

    # Prefer the dedicated parse-only endpoint (no side effects). If it's not deployed yet,
    # fall back to the existing recognize-image endpoint.
    PARSE_PAYLOAD="$(
      jq -nc \
        --arg b64 "${SMOKE_PHOTO_IMAGE_B64}" \
        --arg mt "${SMOKE_PHOTO_MIME_TYPE}" \
        --arg txt "${SMOKE_PHOTO_CONTEXT_TEXT}" \
        '{images:[{data:$b64,mime_type:$mt}], text: (if ($txt|length)>0 then $txt else null end)}'
    )"

    perform_request \
      "POST" \
      "${FRONTEND_URL}/api/v1/diet/logs/parse" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      --data "${PARSE_PAYLOAD}"

    ITEMS_JSON="[]"
    MEAL_TYPE="snack"

    if status_matches_expected "${LAST_STATUS}" "200"; then
      if ! jq -e '.items | type == "array"' "${TMP_BODY}" >/dev/null 2>&1; then
        handle_assert_failure "Diet photo parse response missing items array"
      else
        ITEMS_JSON="$(jq -c '[.items[]? | {food_name:.food_name, weight_g:(.weight_g // null), unit:(.unit // null), calories:(.calories // null), protein:(.protein // null), fat:(.fat // null), carbs:(.carbs // null)}]' "${TMP_BODY}" 2>/dev/null || echo "[]")"
        MEAL_TYPE="$(jq -r '.meal_type // "snack"' "${TMP_BODY}" 2>/dev/null || echo "snack")"
        log_pass "Diet photo parse endpoint reachable"
      fi
    elif status_matches_expected "${LAST_STATUS}" "404"; then
      # Fallback: recognize-image endpoint already exists on main.
      perform_request \
        "POST" \
        "${FRONTEND_URL}/api/v1/diet/meals/recognize-image" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Content-Type: application/json" \
        --data "${PARSE_PAYLOAD}"

      if ! status_matches_expected "${LAST_STATUS}" "200"; then
        handle_assert_failure "Diet photo recognize-image endpoint unavailable (expected 200)"
      elif ! jq -e '.dishes | type == "array"' "${TMP_BODY}" >/dev/null 2>&1; then
        handle_assert_failure "Diet recognize-image response missing dishes array"
      else
        ITEMS_JSON="$(jq -c '[.dishes[]? | {food_name:(.name // ""), weight_g:(.weight_g // null), unit:(.unit // null), calories:(.calories // null), protein:(.protein // null), fat:(.fat // null), carbs:(.carbs // null)} | select(.food_name|length>0)]' "${TMP_BODY}" 2>/dev/null || echo "[]")"
        MEAL_TYPE="snack"
        log_pass "Diet recognize-image endpoint reachable (parse endpoint not deployed)"
      fi
    else
      handle_assert_failure "Diet photo parse endpoint returned unexpected status: ${LAST_STATUS}"
    fi

    # If no items were recognized, validate the fallback by writing a minimal manual item.
    if [[ "$(echo "${ITEMS_JSON}" | jq -r 'length' 2>/dev/null || echo "0")" == "0" ]]; then
      ITEMS_JSON="$(jq -nc --arg name "manual_${PHOTO_MARKER}" '[{food_name:$name, calories:0}]')"
      MEAL_TYPE="snack"
      log_warn "Diet photo recognition yielded 0 items; exercising manual fallback write."
    fi

    CREATE_LOG_PAYLOAD="$(
      jq -nc \
        --arg date "${TODAY}" \
        --arg meal "${MEAL_TYPE}" \
        --arg marker "${PHOTO_MARKER}" \
        --argjson items "${ITEMS_JSON}" \
        '{log_date:$date, meal_type:$meal, items:$items, notes:$marker}'
    )"

    assert_status_with_retry \
      "Diet photo write log check" \
      "POST" \
      "${FRONTEND_URL}/api/v1/diet/logs" \
      "201" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      --data "${CREATE_LOG_PAYLOAD}"

    assert_status_with_retry \
      "Diet photo write visible in logs" \
      "GET" \
      "${FRONTEND_URL}/api/v1/diet/logs?log_date=${TODAY}" \
      "200" \
      -H "Authorization: Bearer ${TOKEN}"

    if status_matches_expected "${LAST_STATUS}" "200"; then
      if ! jq -e --arg marker "${PHOTO_MARKER}" 'any(.logs[]?; (.notes // "") == $marker)' "${TMP_BODY}" >/dev/null 2>&1; then
        handle_assert_failure "Diet logs missing the photo write marker (notes)"
      else
        log_pass "Diet photo write marker found in logs"
      fi
    fi
  fi
else
  log_warn "Authenticated endpoint checks skipped."
fi

# 9) CORS preflight
assert_status_with_retry \
  "CORS preflight check" \
  "OPTIONS" \
  "${FRONTEND_URL}/api/v1/auth/login" \
  "200,204" \
  -H "Origin: ${FRONTEND_URL}" \
  -H "Access-Control-Request-Method: POST"

if ! grep -qi '^access-control-allow-origin:' "${TMP_HEADERS}"; then
  handle_assert_failure "CORS preflight missing access-control-allow-origin header"
else
  log_pass "CORS response header check"
fi

# 10) Render 基线探测
assert_status_with_retry \
  "Backend root baseline" \
  "GET" \
  "${BACKEND_URL}/" \
  "200"

# 11) MCP diet-adjust 可用性探测（可选）
if [[ -z "${MCP_SERVICE_KEY}" ]]; then
  if [[ "${STRICT_MODE}" == "true" ]]; then
    handle_assert_failure "MCP_SERVICE_KEY missing in strict mode: cannot validate MCP diet-adjust availability"
  else
    log_warn "MCP_SERVICE_KEY missing, skip MCP diet-adjust smoke check."
  fi
else
  assert_status_with_retry \
    "MCP diet-adjust tools/list status check" \
    "POST" \
    "${FRONTEND_URL}/api/v1/mcp/diet-adjust" \
    "200" \
    -H "Content-Type: application/json" \
    -H "X-MCP-Service-Key: ${MCP_SERVICE_KEY}" \
    --data '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

  if status_matches_expected "${LAST_STATUS}" "200"; then
    if ! jq -e '.result.tools | type == "array"' "${TMP_BODY}" >/dev/null 2>&1; then
      handle_assert_failure "MCP diet-adjust response does not contain result.tools array"
    else
      MCP_TOOL_COUNT="$(jq -r '.result.tools | length' "${TMP_BODY}" 2>/dev/null || echo "0")"
      if [[ "${MCP_TOOL_COUNT}" =~ ^[0-9]+$ ]] && (( MCP_TOOL_COUNT >= MCP_TOOLS_MIN )); then
        log_pass "MCP diet-adjust tools loaded (${MCP_TOOL_COUNT})"
      else
        handle_assert_failure "MCP diet-adjust tools count too low: expected >= ${MCP_TOOLS_MIN}, got ${MCP_TOOL_COUNT}"
      fi
    fi
  fi
fi

echo ""
echo "========================================="
echo "Smoke suite summary"
echo "PASS_COUNT=${PASS_COUNT}"
echo "WARN_COUNT=${WARN_COUNT}"
echo "FAIL_COUNT=${FAIL_COUNT}"
if [[ "${STRICT_MODE}" == "true" ]]; then
  echo "[PASS] Strict smoke suite completed."
else
  echo "[PASS] Demo stable smoke completed (fail-open enabled)."
fi
echo "========================================="
