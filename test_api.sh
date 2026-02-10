#!/bin/bash
set -e

# Configuration
ENVIRONMENT=${1:-dev}

# Capitalize first letter (Bash 3.2 compatible)
ENVIRONMENT_CAP=$(echo "${ENVIRONMENT}" | awk '{print toupper(substr($0,1,1)) tolower(substr($0,2))}')
STACK_NAME="DataIngestionStack-${ENVIRONMENT_CAP}"

echo "Testing API for environment: $ENVIRONMENT"
echo "Stack: $STACK_NAME"
echo ""

# Get stack outputs
echo "📥 Fetching stack outputs..."
API_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text)

API_KEY_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiKeyId`].OutputValue' \
  --output text)

JWT_SECRET_PARAM=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`JWTSecretParamOutput`].OutputValue' \
  --output text)

echo "✅ API URL: $API_URL"
echo "✅ API Key ID: $API_KEY_ID"
echo "✅ JWT Secret Param: $JWT_SECRET_PARAM"
echo ""

# Get API Key value
echo "🔑 Retrieving API Key..."
API_KEY=$(aws apigateway get-api-key \
  --api-key "$API_KEY_ID" \
  --include-value \
  --query 'value' \
  --output text)

echo "✅ API Key retrieved"
echo ""

# Generate JWT token directly with Python (no external script needed)
echo "🎫 Generating JWT token..."
JWT_TOKEN=$(python3 << PYTHON_EOF
import jwt
import sys
from datetime import datetime, timedelta, timezone
import boto3

# Get JWT secret from SSM
ssm = boto3.client('ssm')
response = ssm.get_parameter(Name='$JWT_SECRET_PARAM', WithDecryption=True)
secret = response['Parameter']['Value']

# Generate token
payload = {
    'sub': 'test-user-${RANDOM}',
    'email': 'test@example.com',
    'iat': datetime.now(timezone.utc),
    'exp': datetime.now(timezone.utc) + timedelta(hours=1)
}
token = jwt.encode(payload, secret, algorithm='HS256')
print(token)
PYTHON_EOF
)

echo "✅ JWT Token generated"
echo ""

# Test health endpoint
echo "🏥 Testing health endpoint..."
HEALTH_RESPONSE=$(curl -s "${API_URL}health")
echo "Response: $HEALTH_RESPONSE"
echo ""

# Test data ingestion
echo "📨 Testing data ingestion endpoint..."
echo "URL: ${API_URL}data"
echo ""

# Make request and capture both body and status code
HTTP_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_URL}data" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "test-user",
    "eventType": "manual-test",
    "data": {
      "message": "Hello from local test - FREE TIER!",
      "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
      "source": "bash-script",
      "cost": "$0.00"
    }
  }')

# Extract status code (last line) and body (everything else)
HTTP_STATUS=$(echo "$HTTP_RESPONSE" | tail -n 1)
HTTP_BODY=$(echo "$HTTP_RESPONSE" | sed '$d')

echo "Status Code: $HTTP_STATUS"
echo "Response Body: $HTTP_BODY"
echo ""

if [ "$HTTP_STATUS" -eq 200 ]; then
  echo "✅ Test PASSED"
  
  # Pretty print the response if jq is available
  if command -v jq &> /dev/null; then
    echo ""
    echo "Response Details:"
    echo "$HTTP_BODY" | jq '.'
  fi
else
  echo "❌ Test FAILED"
  exit 1
fi

echo ""
echo "🎉 All tests completed successfully!"
echo ""
