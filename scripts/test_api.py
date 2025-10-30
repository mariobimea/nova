"""
Test NOVA API endpoints
"""

import requests
import json

BASE_URL = "http://localhost:8002"

def test_api():
    print("="*70)
    print("🧪 NOVA API - Test Suite")
    print("="*70)

    # 1. Test root
    print("\n1️⃣  GET / (root)")
    r = requests.get(f"{BASE_URL}/")
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.json()}")

    # 2. Test health
    print("\n2️⃣  GET /health")
    r = requests.get(f"{BASE_URL}/health")
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.json()}")

    # 3. List workflows
    print("\n3️⃣  GET /workflows")
    r = requests.get(f"{BASE_URL}/workflows")
    print(f"   Status: {r.status_code}")
    data = r.json()
    print(f"   Total workflows: {data['total']}")
    if data['workflows']:
        print(f"   First workflow: {data['workflows'][0]['name']} (ID: {data['workflows'][0]['id']})")

    # 4. Get workflow 1
    print("\n4️⃣  GET /workflows/1")
    r = requests.get(f"{BASE_URL}/workflows/1")
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        wf = r.json()
        print(f"   Name: {wf['name']}")
        print(f"   Nodes: {len(wf['graph_definition']['nodes'])}")
        print(f"   Edges: {len(wf['graph_definition']['edges'])}")

    # 5. List executions
    print("\n5️⃣  GET /executions")
    r = requests.get(f"{BASE_URL}/executions")
    print(f"   Status: {r.status_code}")
    data = r.json()
    print(f"   Total executions: {data['total']}")
    if data['executions']:
        latest = data['executions'][0]
        print(f"   Latest execution: ID {latest['id']} - {latest['status']}")

    # 6. Get execution 2
    print("\n6️⃣  GET /executions/2")
    r = requests.get(f"{BASE_URL}/executions/2")
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        ex = r.json()
        print(f"   Workflow ID: {ex['workflow_id']}")
        print(f"   Status: {ex['status']}")
        print(f"   Started: {ex['started_at']}")

    # 7. Get chain of work for execution 2
    print("\n7️⃣  GET /executions/2/chain")
    r = requests.get(f"{BASE_URL}/executions/2/chain")
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        chain = r.json()
        print(f"   Total entries: {chain['total']}")
        print(f"   Nodes executed:")
        for entry in chain['entries'][:5]:  # Show first 5
            print(f"      - {entry['node_id']} ({entry['node_type']}) - {entry['status']} ({entry['execution_time']:.2f}s)")

    print("\n" + "="*70)
    print("✅ API tests completed")
    print("="*70)

if __name__ == "__main__":
    try:
        test_api()
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API. Make sure it's running:")
        print("   python3 -m uvicorn src.api.main:app --reload")
    except Exception as e:
        print(f"❌ Error: {e}")
