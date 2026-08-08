#!/bin/bash

BASE_URL="http://localhost:30021/api"
USERNAME="jinqisen"
PASSWORD="Hello!2025"

echo "=== Trigger Reflexion in Docker ==="

# 1. Register (Ignore error if exists)
echo "1. Registering..."
REGISTER_RES=$(curl -s -X POST "$BASE_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"$USERNAME\", \"password\": \"$PASSWORD\"}")
echo "   Register Response: $REGISTER_RES"

# 2. Login to get token
echo "2. Logging in..."
TOKEN_RES=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$USERNAME&password=$PASSWORD")

TOKEN=$(echo $TOKEN_RES | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
  echo "Failed to get token. Response: $TOKEN_RES"
  exit 1
fi

echo "   Got Token: ${TOKEN:0:10}..."

# 3. Chat
echo "3. Sending Chat Message..."
curl -X POST "$BASE_URL/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "我们见一面吧",
    "session_id": "test_reflexion_shell"
  }'

echo -e "\n4. Done. Check docker logs."
