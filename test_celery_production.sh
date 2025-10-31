#!/bin/bash
#
# Test script for Celery in production
# Usage: ./test_celery_production.sh
#

set -e

API_URL="https://web-production-a1c4f.up.railway.app"
WORKFLOW_ID=1
CLIENT_SLUG="idom"

echo "🧪 NOVA Celery Production Testing"
echo "=================================="
echo ""
echo "API URL: $API_URL"
echo "Workflow ID: $WORKFLOW_ID"
echo "Client: $CLIENT_SLUG"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Health Check
echo "Test 1: Health Check"
echo "--------------------"
HEALTH=$(curl -s "$API_URL/health")
echo "$HEALTH" | python3 -m json.tool

DB_STATUS=$(echo "$HEALTH" | python3 -c "import sys, json; print(json.load(sys.stdin)['database'])")
if [ "$DB_STATUS" = "connected" ]; then
    echo -e "${GREEN}✅ Database connected${NC}"
else
    echo -e "${RED}❌ Database not connected${NC}"
    exit 1
fi
echo ""

# Test 2: List workflows
echo "Test 2: List Workflows"
echo "----------------------"
WORKFLOWS=$(curl -s "$API_URL/workflows")
WORKFLOW_COUNT=$(echo "$WORKFLOWS" | python3 -c "import sys, json; print(json.load(sys.stdin)['total'])")
echo "Total workflows: $WORKFLOW_COUNT"

if [ "$WORKFLOW_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ Workflows found${NC}"
else
    echo -e "${RED}❌ No workflows found${NC}"
    exit 1
fi
echo ""

# Test 3: Execute workflow (async with Celery)
echo "Test 3: Execute Workflow (Async)"
echo "---------------------------------"
echo "Sending POST /workflows/$WORKFLOW_ID/execute..."

EXECUTE_RESPONSE=$(curl -s -X POST "$API_URL/workflows/$WORKFLOW_ID/execute" \
  -H 'Content-Type: application/json' \
  -d "{\"client_slug\":\"$CLIENT_SLUG\"}")

echo "$EXECUTE_RESPONSE" | python3 -m json.tool

# Check if we got a task_id (Celery) or execution_id (old sync)
TASK_ID=$(echo "$EXECUTE_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('task_id', ''))" 2>/dev/null || echo "")

if [ -z "$TASK_ID" ]; then
    echo -e "${YELLOW}⚠️  No task_id received - Worker might not be running${NC}"
    echo -e "${YELLOW}   This is expected if worker service is not deployed yet${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Create worker service in Railway dashboard"
    echo "2. Deploy worker with command: celery -A src.workers.celery_app worker --loglevel=info --concurrency=2"
    echo "3. Run this script again"
    exit 0
fi

echo -e "${GREEN}✅ Task queued successfully${NC}"
echo "Task ID: $TASK_ID"
echo ""

# Test 4: Check task status
echo "Test 4: Check Task Status"
echo "-------------------------"
echo "Polling task status every 2 seconds..."
echo ""

MAX_ATTEMPTS=60  # 2 minutes max
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))

    TASK_STATUS=$(curl -s "$API_URL/tasks/$TASK_ID")
    STATE=$(echo "$TASK_STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "UNKNOWN")

    echo -n "[$ATTEMPT/$MAX_ATTEMPTS] Status: $STATE"

    if [ "$STATE" = "SUCCESS" ]; then
        echo -e " ${GREEN}✅${NC}"
        echo ""
        echo "Task completed successfully!"
        echo ""
        echo "Full response:"
        echo "$TASK_STATUS" | python3 -m json.tool

        # Extract execution_id
        EXECUTION_ID=$(echo "$TASK_STATUS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('execution_id', data.get('result', {}).get('execution_id', '')))" 2>/dev/null || echo "")

        if [ -n "$EXECUTION_ID" ]; then
            echo ""
            echo -e "${GREEN}✅ Execution ID: $EXECUTION_ID${NC}"

            # Test 5: Get execution details
            echo ""
            echo "Test 5: Get Execution Details"
            echo "------------------------------"
            curl -s "$API_URL/executions/$EXECUTION_ID" | python3 -m json.tool

            # Test 6: Get Chain of Work
            echo ""
            echo "Test 6: Get Chain of Work"
            echo "-------------------------"
            CHAIN=$(curl -s "$API_URL/executions/$EXECUTION_ID/chain")
            ENTRY_COUNT=$(echo "$CHAIN" | python3 -c "import sys, json; print(json.load(sys.stdin)['total'])")
            echo "Chain of Work entries: $ENTRY_COUNT"
            echo ""
            echo -e "${GREEN}✅ All tests passed!${NC}"
        fi

        exit 0

    elif [ "$STATE" = "FAILURE" ]; then
        echo -e " ${RED}❌${NC}"
        echo ""
        echo "Task failed!"
        echo ""
        echo "Error details:"
        echo "$TASK_STATUS" | python3 -m json.tool
        exit 1

    elif [ "$STATE" = "PENDING" ]; then
        echo -e " ${YELLOW}⏳${NC} (queued, waiting for worker)"

    elif [ "$STATE" = "STARTED" ] || [ "$STATE" = "RUNNING" ]; then
        echo -e " ${YELLOW}🔄${NC} (executing)"

    else
        echo " (unknown state)"
    fi

    sleep 2
done

echo ""
echo -e "${RED}❌ Timeout: Task did not complete within 2 minutes${NC}"
echo ""
echo "Last known status:"
echo "$TASK_STATUS" | python3 -m json.tool
exit 1
