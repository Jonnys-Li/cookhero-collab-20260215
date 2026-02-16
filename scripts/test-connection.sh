#!/usr/bin/env bash

# CookHero 前后端连接测试脚本
# 用于验证前端和后端的 API 连接是否正常

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 默认后端 URL（可以被命令行参数覆盖）
BACKEND_URL="${1:-https://cookhero-collab-20260215.onrender.com}"
FRONTEND_URL="${2:-https://frontend-one-gray-39.vercel.app}"
API_BASE="${BACKEND_URL}/api/v1"
TOKEN=""

echo "========================================="
echo "CookHero 连接测试"
echo "========================================="
echo ""
echo "测试目标: ${API_BASE}"
echo ""

# 测试函数（API_BASE 前缀）
test_endpoint() {
    local name=$1
    local endpoint=$2
    local expected_code=${3:-200}

    echo -n "测试 ${name}... "

    local status_code=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}${endpoint}")

    if [ "$status_code" = "$expected_code" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP ${status_code})"
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (HTTP ${status_code}, expected ${expected_code})"
        return 1
    fi
}

# 测试函数（完整 URL）
test_full_url() {
    local name=$1
    local full_url=$2
    local expected_code=${3:-200}

    echo -n "测试 ${name}... "

    local status_code
    status_code=$(curl -s -o /dev/null -w "%{http_code}" "${full_url}")

    if [ "$status_code" = "$expected_code" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP ${status_code})"
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (HTTP ${status_code}, expected ${expected_code})"
        return 1
    fi
}

# 1. 测试基础连通性
echo "--- 基础连接测试 ---"
test_full_url "后端根路径" "${BACKEND_URL}/" "200"
test_endpoint "API 鉴权闸门" "/health" "401"
echo ""

# 2. 测试 API 文档可访问性
echo "--- API 文档测试 ---"
test_full_url "Swagger 文档" "${BACKEND_URL}/docs" "200"
echo ""

# 3. 测试 API 端点
echo "--- API 端点测试 ---"
test_endpoint "登录端点 (POST)" "/auth/login" "405"  # Method not allowed for GET
test_endpoint "对话列表 (未授权)" "/conversation" "401"
test_endpoint "用户信息 (未授权)" "/user/profile" "401"
echo ""

# 4. 测试登录功能
echo "--- 登录功能测试 ---"
echo -n "测试用户注册/登录... "
response=$(curl -s -X POST "${API_BASE}/auth/register" \
    -H "Content-Type: application/json" \
    -d '{"username":"test_user_'$(date +%s)'","password":"testpass123"}')

if echo "$response" | grep -q "access_token"; then
    echo -e "${GREEN}✓ PASS${NC}"
    TOKEN=$(echo "$response" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
else
    echo -e "${YELLOW}⚠ SKIP${NC} (可能用户已存在)"
fi
echo ""

# 5. 带认证的请求测试
if [ -n "$TOKEN" ]; then
    echo "--- 认证请求测试 ---"
    echo -n "测试获取用户信息... "
    user_response=$(curl -s -X GET "${API_BASE}/user/profile" \
        -H "Authorization: Bearer ${TOKEN}")

    if echo "$user_response" | grep -q "username"; then
        echo -e "${GREEN}✓ PASS${NC}"
    else
        echo -e "${RED}✗ FAIL${NC}"
    fi
    echo ""
fi

# 6. CORS 测试
echo "--- CORS 配置测试 ---"
echo -n "检查 CORS 响应头... "
cors_headers=$(curl -s -I -X OPTIONS "${API_BASE}/auth/login" \
    -H "Origin: ${FRONTEND_URL}" \
    -H "Access-Control-Request-Method: POST" \
    2>&1 | grep -i "access-control-allow-origin" || true)

if [ -n "$cors_headers" ]; then
    echo -e "${GREEN}✓ PASS${NC}"
    echo "  ${cors_headers}"
else
    echo -e "${YELLOW}⚠ WARNING${NC} (CORS headers not found in preflight response)"
fi
echo ""

# 总结
echo "========================================="
echo "测试完成"
echo "========================================="
echo ""
echo "如果所有测试都通过，说明后端 API 工作正常。"
echo ""
echo "下一步："
echo "1. Vercel 生产环境推荐保留:"
echo "   VITE_API_BASE=/api/v1"
echo ""
echo "2. 确认 frontend/vercel.json 已将 /api/v1/* 转发到 Render 后端。"
echo ""
echo "3. 在前端检查 API 配置:"
echo "   打开浏览器控制台，执行: console.log(import.meta.env.VITE_API_BASE)"
echo "   生产环境应显示: /api/v1"
echo ""
echo "4. 如果遇到 CORS 错误，检查后端环境变量:"
echo "   CORS_ALLOW_ORIGINS=${FRONTEND_URL},http://localhost:5173"
echo "   CORS_ALLOW_ORIGIN_REGEX=^https://.*\\.vercel\\.app$"
echo ""
