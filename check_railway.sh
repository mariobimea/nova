#!/bin/bash

# Railway Service Diagnostics Script
# Run this to check if all services are configured correctly

echo "======================================"
echo "NOVA Railway Service Diagnostics"
echo "======================================"
echo ""

# Replace this with your actual nova-app URL
NOVA_URL="https://nova-app-production-xxxx.up.railway.app"

echo "1. Checking if API is alive..."
curl -s "$NOVA_URL/health" | python3 -m json.tool
echo ""

echo "2. Testing workflow execution..."
TASK_RESPONSE=$(curl -s -X POST "$NOVA_URL/workflows/1/execute" \
  -H "Content-Type: application/json" \
  -d '{"initial_context":{"invoice_url":"https://example.com/invoice.pdf","client_name":"IDOM"},"client_slug":"idom"}')

echo "$TASK_RESPONSE" | python3 -m json.tool
echo ""

# Extract task_id from response
TASK_ID=$(echo "$TASK_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('task_id', ''))" 2>/dev/null)

if [ -n "$TASK_ID" ]; then
  echo "3. Task queued successfully! Task ID: $TASK_ID"
  echo "   Waiting 5 seconds for execution..."
  sleep 5

  echo ""
  echo "4. Checking task status..."
  curl -s "$NOVA_URL/tasks/$TASK_ID" | python3 -m json.tool
else
  echo "3. ERROR: Failed to queue task"
fi

echo ""
echo "======================================"
echo "Diagnostics complete"
echo "======================================"
