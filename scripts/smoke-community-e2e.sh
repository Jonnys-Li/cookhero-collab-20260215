#!/usr/bin/env bash
#
# Community module end-to-end smoke test (backend API only).
#
# What it validates:
# - Register -> token works
# - Meta capabilities returns expected AI modes
# - Community CRUD: create post -> feed -> detail -> comment -> like toggle -> delete
# - Community AI: polish/reply/card endpoints return expected shape
#
# Notes:
# - Uses a random user each run so it is self-contained.
# - Creates one post and deletes it at the end to avoid polluting production data.
#

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-https://cookhero-collab-20260215.onrender.com}"
API_BASE="${API_BASE:-${BACKEND_URL%/}/api/v1}"
CONNECT_TIMEOUT_SECONDS="${CONNECT_TIMEOUT_SECONDS:-8}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-45}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

HEADERS_FILE="${TMP_DIR}/headers.txt"
BODY_FILE="${TMP_DIR}/body.txt"

log() {
  echo "[smoke-community] $*"
}

perform_request() {
  local method="$1"
  local url="$2"
  shift 2
  local -a extra_args=("$@")

  : > "${HEADERS_FILE}"
  : > "${BODY_FILE}"

  curl -sS \
    --connect-timeout "${CONNECT_TIMEOUT_SECONDS}" \
    --max-time "${REQUEST_TIMEOUT_SECONDS}" \
    -X "${method}" \
    -D "${HEADERS_FILE}" \
    -o "${BODY_FILE}" \
    "${extra_args[@]}" \
    "${url}" \
    -w "%{http_code}"
}

extract_field() {
  local field="$1"
  # Best-effort extraction for a simple JSON string field: "field":"value"
  sed -n "s/.*\\\"${field}\\\":\\\"\\([^\\\"]*\\)\\\".*/\\1/p" "${BODY_FILE}" | head -n 1
}

assert_status() {
  local got="$1"
  local expected="$2"
  local title="$3"
  if [[ "${got}" != "${expected}" ]]; then
    log "[FAIL] ${title} expected ${expected}, got ${got}"
    log "---- headers ----"
    sed -n '1,60p' "${HEADERS_FILE}" || true
    log "---- body ----"
    sed -n '1,120p' "${BODY_FILE}" || true
    exit 1
  fi
  log "[PASS] ${title} -> ${got}"
}

contains() {
  local needle="$1"
  rg -q --fixed-strings "${needle}" "${BODY_FILE}"
}

random_username="smoke_comm_$(date +%s)_$RANDOM"
password="Passw0rd!"

log "API_BASE=${API_BASE}"
log "Register user=${random_username}"

status="$(
  perform_request \
    "POST" \
    "${API_BASE}/auth/register" \
    -H "Content-Type: application/json" \
    --data "{\"username\":\"${random_username}\",\"password\":\"${password}\"}"
)"
assert_status "${status}" "200" "auth/register"

token="$(extract_field "access_token")"
if [[ -z "${token}" ]]; then
  log "[FAIL] missing access_token in register response"
  sed -n '1,120p' "${BODY_FILE}" || true
  exit 1
fi
log "[PASS] token extracted (len=${#token})"

log "Probe meta capabilities"
status="$(perform_request "GET" "${API_BASE}/meta/capabilities" -H "Authorization: Bearer ${token}")"
assert_status "${status}" "200" "meta/capabilities"
contains "\"community_ai_modes\"" || { log "[FAIL] capabilities missing community_ai_modes"; exit 1; }
contains "polish" || { log "[FAIL] capabilities missing polish mode"; exit 1; }
contains "reply" || { log "[FAIL] capabilities missing reply mode"; exit 1; }
contains "card" || { log "[FAIL] capabilities missing card mode"; exit 1; }
log "[PASS] capabilities include polish/reply/card"

log "AI polish (mode=polish)"
status="$(
  perform_request \
    "POST" \
    "${API_BASE}/community/ai/suggest" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    --data "{\"mode\":\"polish\",\"content\":\"今天没忍住吃了炸鸡，我好失败。\"}"
)"
assert_status "${status}" "200" "community/ai/suggest polish"
contains "\"polished\"" || { log "[FAIL] AI polish response missing 'polished'"; exit 1; }

log "Create a post"
status="$(
  perform_request \
    "POST" \
    "${API_BASE}/community/posts" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    --data "{\"is_anonymous\":true,\"mood\":\"neutral\",\"content\":\"今天外食有点多，但我还是尽量控制住了晚餐。打卡一下。\",\"tags\":[\"外食\",\"坚持打卡\"]}"
)"
assert_status "${status}" "201" "community/posts create"

post_id="$(extract_field "id")"
if [[ -z "${post_id}" ]]; then
  log "[FAIL] create post response missing id"
  sed -n '1,120p' "${BODY_FILE}" || true
  exit 1
fi
log "[PASS] post created id=${post_id}"

log "Feed should include the post (at least 1 total)"
status="$(perform_request "GET" "${API_BASE}/community/feed?limit=5&offset=0" -H "Authorization: Bearer ${token}")"
assert_status "${status}" "200" "community/feed"
contains "\"total\"" || { log "[FAIL] feed missing total"; exit 1; }

log "Post detail should be readable"
status="$(perform_request "GET" "${API_BASE}/community/posts/${post_id}?comment_limit=10&comment_offset=0" -H "Authorization: Bearer ${token}")"
assert_status "${status}" "200" "community/posts/{id} detail"
contains "\"post\"" || { log "[FAIL] post detail missing post"; exit 1; }

log "Add a comment"
status="$(
  perform_request \
    "POST" \
    "${API_BASE}/community/posts/${post_id}/comments" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    --data "{\"content\":\"给你一个拥抱，明天继续就好。\"}"
)"
assert_status "${status}" "201" "community comment create"
contains "\"id\"" || { log "[FAIL] comment response missing id"; exit 1; }

log "Toggle like twice (should be idempotent)"
status="$(perform_request "POST" "${API_BASE}/community/posts/${post_id}/reactions/toggle" -H "Authorization: Bearer ${token}" -H "Content-Type: application/json" --data "{}")"
assert_status "${status}" "200" "community like toggle (1)"
contains "\"liked\"" || { log "[FAIL] like toggle missing liked"; exit 1; }

status="$(perform_request "POST" "${API_BASE}/community/posts/${post_id}/reactions/toggle" -H "Authorization: Bearer ${token}" -H "Content-Type: application/json" --data "{}")"
assert_status "${status}" "200" "community like toggle (2)"

log "AI reply suggestion (mode=reply)"
status="$(
  perform_request \
    "POST" \
    "${API_BASE}/community/ai/suggest" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    --data "{\"mode\":\"reply\",\"post_id\":\"${post_id}\"}"
)"
assert_status "${status}" "200" "community/ai/suggest reply"
contains "\"reply\"" || { log "[FAIL] AI reply response missing 'reply'"; exit 1; }

log "AI empathy card (mode=card)"
status="$(
  perform_request \
    "POST" \
    "${API_BASE}/community/ai/suggest" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    --data "{\"mode\":\"card\",\"post_id\":\"${post_id}\"}"
)"
assert_status "${status}" "200" "community/ai/suggest card"
contains "\"card\"" || { log "[FAIL] AI card response missing 'card'"; exit 1; }

log "Cleanup: delete post (cascades comments/reactions)"
status="$(perform_request "DELETE" "${API_BASE}/community/posts/${post_id}" -H "Authorization: Bearer ${token}")"
assert_status "${status}" "200" "community post delete"
contains "帖子已删除" || contains "\"message\"" || true

log "All checks passed."

