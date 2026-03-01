#!/bin/bash
set -euo pipefail

# =============================================================================
# API Test Script - Secure Data Ingestion API
# Usage: ./test_api.sh [environment]
#   environment: dev (default) | prod
# =============================================================================

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ENVIRONMENT="${1:-dev}"

# Capitalize first letter (Bash 3.2 compatible)
ENVIRONMENT_CAP=$(echo "$ENVIRONMENT" | awk '{print toupper(substr($0,1,1)) tolower(substr($0,2))}')
STACK_NAME="DataIngestionStack-${ENVIRONMENT_CAP}"

echo "=================================================="
echo " Secure Data Ingestion API - Test Suite"
echo " Environment : $ENVIRONMENT"
echo " Stack       : $STACK_NAME"
echo "=================================================="
echo ""

# ---------------------------------------------------------------------------
# Dependency check: ensure PyJWT is available for JWT generation
# ---------------------------------------------------------------------------
echo "🔍 Checking Python dependencies..."

if ! python3 -c "import jwt" 2>/dev/null; then
    echo "   PyJWT not found. Installing..."
    pip3 install --quiet PyJWT
    echo "   ✅ PyJWT installed"
else
    echo "   ✅ PyJWT already available"
fi

if ! python3 -c "import boto3" 2>/dev/null; then
    echo "   boto3 not found. Installing..."
    pip3 install --quiet boto3
    echo "   ✅ boto3 installed"
else
    echo "   ✅ boto3 already available"
fi
echo ""

# ---------------------------------------------------------------------------
# Fetch stack outputs
# ---------------------------------------------------------------------------
echo "📥 Fetching stack outputs..."

API_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey==\`ApiEndpoint\`].OutputValue" \
    --output text)

API_KEY_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey==\`ApiKeyId\`].OutputValue" \
    --output text)

JWT_SECRET_PARAM=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey==\`JWTSecretParamOutput\`].OutputValue" \
    --output text)

if [[ -z "$API_URL" || -z "$API_KEY_ID" || -z "$JWT_SECRET_PARAM" ]]; then
    echo "❌ Failed to retrieve stack outputs. Is the stack deployed and the environment correct?"
    exit 1
fi

echo "   ✅ API URL           : $API_URL"
echo "   ✅ API Key ID        : $API_KEY_ID"
echo "   ✅ JWT Secret Param  : $JWT_SECRET_PARAM"
echo ""

# ---------------------------------------------------------------------------
# Retrieve API key value
# ---------------------------------------------------------------------------
echo "🔑 Retrieving API Key value..."

API_KEY=$(aws apigateway get-api-key \
    --api-key "$API_KEY_ID" \
    --include-value \
    --query "value" \
    --output text)

if [[ -z "$API_KEY" ]]; then
    echo "❌ Failed to retrieve API Key value."
    exit 1
fi

echo "   ✅ API Key retrieved"
echo ""

# ---------------------------------------------------------------------------
# Generate JWT token using Python (PyJWT confirmed available above)
# ---------------------------------------------------------------------------
echo "🎫 Generating JWT token..."

# Note: JWT_SECRET_PARAM is passed as a shell variable into the Python script
# via a positional argument to avoid heredoc interpolation issues.
JWT_TOKEN=$(python3 - "$JWT_SECRET_PARAM" <<'PYTHON_EOF'
import sys
import jwt
import boto3
from datetime import datetime, timedelta, timezone

param_name = sys.argv[1]

# Fetch JWT secret from SSM Parameter Store
ssm = boto3.client('ssm')
response = ssm.get_parameter(Name=param_name, WithDecryption=True)
secret = response['Parameter']['Value']

# Build token payload
payload = {
    'sub': 'test-user-script',
    'email': 'test@example.com',
    'scope': 'data:write',
    'iat': datetime.now(timezone.utc),
    'exp': datetime.now(timezone.utc) + timedelta(hours=1),
}

token = jwt.encode(payload, secret, algorithm='HS256')
print(token)
PYTHON_EOF
)

if [[ -z "$JWT_TOKEN" ]]; then
    echo "❌ Failed to generate JWT token."
    exit 1
fi

echo "   ✅ JWT Token generated"
echo ""

# ---------------------------------------------------------------------------
# Test 1: Health endpoint (no auth required)
# ---------------------------------------------------------------------------
echo "──────────────────────────────────────────────────"
echo "🏥 Test 1: Health endpoint"
echo "──────────────────────────────────────────────────"

HEALTH_RESPONSE=$(curl -s -o /tmp/health_body.txt -w "%{http_code}" \
    "${API_URL}health")
HEALTH_BODY=$(cat /tmp/health_body.txt)

echo "   Status : $HEALTH_RESPONSE"
echo "   Body   : $HEALTH_BODY"

if [[ "$HEALTH_RESPONSE" == "200" ]]; then
    echo "   ✅ Health check PASSED"
else
    echo "   ⚠️  Health check returned HTTP $HEALTH_RESPONSE (non-200)"
fi
echo ""

# ---------------------------------------------------------------------------
# Test 2: Data ingestion endpoint (JWT + API key required)
# ---------------------------------------------------------------------------
echo "──────────────────────────────────────────────────"
echo "📨 Test 2: Data ingestion endpoint"
echo "──────────────────────────────────────────────────"

REQUEST_BODY=$(cat <<EOF
{
    "userId": "test-user-script",
    "eventType": "manual-test",
    "data": {
        "message": "Hello from test script",
        "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
        "source": "bash-test-script",
        "environment": "$ENVIRONMENT"
    }
}
EOF
)

HTTP_RESPONSE=$(curl -s -o /tmp/ingest_body.txt -w "%{http_code}" \
    -X POST "${API_URL}data" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "x-api-key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d "$REQUEST_BODY")

HTTP_BODY=$(cat /tmp/ingest_body.txt)

echo "   Status : $HTTP_RESPONSE"
echo "   Body   : $HTTP_BODY"

if [[ "$HTTP_RESPONSE" == "200" ]]; then
    echo "   ✅ Data ingestion PASSED"
else
    echo "   ❌ Data ingestion FAILED (HTTP $HTTP_RESPONSE)"
    exit 1
fi
echo ""

# ---------------------------------------------------------------------------
# Test 3: Reject request with missing required fields
# ---------------------------------------------------------------------------
echo "──────────────────────────────────────────────────"
echo "🚫 Test 3: Validation - missing required fields"
echo "──────────────────────────────────────────────────"

BAD_RESPONSE=$(curl -s -o /tmp/bad_body.txt -w "%{http_code}" \
    -X POST "${API_URL}data" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "x-api-key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"eventType": "incomplete-payload"}')

BAD_BODY=$(cat /tmp/bad_body.txt)

echo "   Status : $BAD_RESPONSE"
echo "   Body   : $BAD_BODY"

if [[ "$BAD_RESPONSE" == "400" ]]; then
    echo "   ✅ Validation PASSED (correctly rejected malformed request)"
else
    echo "   ⚠️  Expected HTTP 400, got $BAD_RESPONSE"
fi
echo ""

# ---------------------------------------------------------------------------
# Test 4: Reject request without auth token
# ---------------------------------------------------------------------------
echo "──────────────────────────────────────────────────"
echo "🔒 Test 4: Security - request without JWT token"
echo "──────────────────────────────────────────────────"

UNAUTH_RESPONSE=$(curl -s -o /tmp/unauth_body.txt -w "%{http_code}" \
    -X POST "${API_URL}data" \
    -H "x-api-key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"userId": "hacker", "data": {}}')

echo "   Status : $UNAUTH_RESPONSE"

if [[ "$UNAUTH_RESPONSE" == "401" || "$UNAUTH_RESPONSE" == "403" ]]; then
    echo "   ✅ Auth enforcement PASSED (correctly rejected unauthenticated request)"
else
    echo "   ⚠️  Expected HTTP 401/403, got $UNAUTH_RESPONSE"
fi
echo ""

# ---------------------------------------------------------------------------
# Cleanup temp files
# ---------------------------------------------------------------------------
rm -f /tmp/health_body.txt /tmp/ingest_body.txt /tmp/bad_body.txt /tmp/unauth_body.txt

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "=================================================="
echo " 🎉 All tests completed for environment: $ENVIRONMENT"
echo "=================================================="