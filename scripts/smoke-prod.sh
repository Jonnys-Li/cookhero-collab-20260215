#!/usr/bin/env bash

# CookHero 生产环境烟测脚本
# 用于验证 Vercel 前端代理与 Render 后端关键链路是否可用。

set -euo pipefail

FRONTEND_URL="${FRONTEND_URL:-https://frontend-one-gray-39.vercel.app}"
BACKEND_URL="${BACKEND_URL:-https://cookhero-collab-20260215.onrender.com}"
MAX_RETRIES="${MAX_RETRIES:-3}"

if [[ -z "${SMOKE_USERNAME:-}" || -z "${SMOKE_PASSWORD:-}" ]]; then
  echo "[FAIL] Missing required secrets: SMOKE_USERNAME / SMOKE_PASSWORD"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
TMP_HEADERS="${TMP_DIR}/headers.txt"
TMP_BODY="${TMP_DIR}/body.txt"
LAST_STATUS=""
PASS_COUNT=0

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

log_pass() {
  local message="$1"
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "[PASS] ${message}"
}

log_fail_and_exit() {
  local message="$1"
  echo "[FAIL] ${message}"
  echo "---- Last Response Headers ----"
  sed -n '1,30p' "${TMP_HEADERS}" || true
  echo "---- Last Response Body ----"
  sed -n '1,30p' "${TMP_BODY}" || true
  exit 1
}

perform_request() {
  local method="$1"
  local url="$2"
  shift 2
  local -a extra_args=("$@")

  if ((${#extra_args[@]} > 0)); then
    LAST_STATUS="$(
      curl -sS \
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

assert_status_with_retry() {
  local title="$1"
  local method="$2"
  local url="$3"
  local expected_status="$4"
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
    if [[ "${LAST_STATUS}" == "${expected_status}" ]]; then
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

    log_fail_and_exit "${title} | ${method} ${url} expected ${expected_status}, got ${LAST_STATUS}"
  done
}

echo "========================================="
echo "CookHero Production Smoke Test"
echo "========================================="
echo "FRONTEND_URL=${FRONTEND_URL}"
echo "BACKEND_URL=${BACKEND_URL}"
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
  log_fail_and_exit "Login response missing access_token"
fi
log_pass "Smoke token extraction"

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

# 9) CORS preflight
assert_status_with_retry \
  "CORS preflight check" \
  "OPTIONS" \
  "${FRONTEND_URL}/api/v1/auth/login" \
  "200" \
  -H "Origin: ${FRONTEND_URL}" \
  -H "Access-Control-Request-Method: POST"

if ! grep -qi '^access-control-allow-origin:' "${TMP_HEADERS}"; then
  log_fail_and_exit "CORS preflight missing access-control-allow-origin header"
fi
log_pass "CORS response header check"

# 10) Render 基线探测
assert_status_with_retry \
  "Backend root baseline" \
  "GET" \
  "${BACKEND_URL}/" \
  "200"

echo ""
echo "========================================="
echo "[PASS] Smoke suite completed. Checks passed: ${PASS_COUNT}"
echo "========================================="
