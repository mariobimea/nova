"""
Test API endpoint with automatic credential loading from database
"""

import requests
import json

BASE_URL = "http://localhost:8002"

print("=" * 70)
print("🧪 Testing API with Automatic Credential Loading")
print("=" * 70)

# Test 1: Execute workflow with client_slug (credentials from DB)
print("\n1️⃣  POST /workflows/1/execute (with client_slug)")
print("   This should automatically load credentials from database")

payload = {
    "client_slug": "idom"
}

try:
    print(f"\n   Sending request...")
    print(f"   Payload: {json.dumps(payload, indent=2)}")

    r = requests.post(
        f"{BASE_URL}/workflows/1/execute",
        json=payload,
        timeout=120  # 2 minutes for email processing
    )

    print(f"\n   Status: {r.status_code}")

    if r.status_code == 202:
        result = r.json()
        print(f"   ✅ Execution created!")
        print(f"   Execution ID: {result['id']}")
        print(f"   Workflow ID: {result['workflow_id']}")
        print(f"   Status: {result['status']}")
        print(f"   Started at: {result['started_at']}")

        if result.get('completed_at'):
            print(f"   Completed at: {result['completed_at']}")

        if result.get('result'):
            print(f"\n   📋 Result:")
            res = result['result']
            print(f"      Email: {res.get('email_from', 'N/A')}")
            print(f"      PDF: {res.get('has_pdf', False)}")
            amount = res.get('total_amount')
            if amount is not None:
                print(f"      Amount: €{amount:.2f}")
            else:
                print(f"      Amount: Not detected")

        if result.get('error'):
            print(f"\n   ❌ Error: {result['error']}")

        # Now get chain of work
        print(f"\n2️⃣  GET /executions/{result['id']}/chain")
        chain_r = requests.get(f"{BASE_URL}/executions/{result['id']}/chain")

        if chain_r.status_code == 200:
            chain = chain_r.json()
            print(f"   Total entries: {chain['total']}")
            print(f"\n   📋 Nodes executed:")
            for entry in chain['entries']:
                icon = "✅" if entry['status'] == 'success' else "❌"
                print(f"      {icon} {entry['node_id']} ({entry['node_type']}) - {entry['execution_time']:.2f}s")
                if entry.get('error_message'):
                    print(f"         Error: {entry['error_message']}")
    else:
        print(f"   ❌ Error response:")
        print(f"   {json.dumps(r.json(), indent=2)}")

except requests.exceptions.Timeout:
    print("   ⏱️  Request timed out (workflow still processing)")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 70)
print("✅ Test completed")
print("=" * 70)
