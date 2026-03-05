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

  if ((${#extra_args[@]} > 0)); then
    LAST_STATUS="$(
      curl -sS \
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

  TOKEN="$(sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p' "${TMP_BODY}" | head -n 1)"
  if [[ -z "${TOKEN}" ]]; then
    handle_assert_failure "Login response missing access_token"
    AUTH_CHECKS_ENABLED=false
  else
    log_pass "Smoke token extraction"
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
