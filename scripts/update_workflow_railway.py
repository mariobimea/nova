"""
Update Invoice Processing Workflow in Railway Database

This script updates the workflow in the Railway production database
by calling the API endpoint directly.
"""

import json
import requests

# Railway API URL
API_URL = "https://web-production-a1c4f.up.railway.app"

def update_workflow():
    """Update workflow via API"""

    # Load updated workflow JSON
    fixture_path = '../fixtures/invoice_workflow_v3.json'

    print(f"📂 Loading workflow from: {fixture_path}")

    with open(fixture_path, 'r') as f:
        workflow_data = json.load(f)

    print(f"✅ Loaded workflow: {workflow_data['name']}")
    print(f"   Description: {workflow_data.get('description', 'N/A')}")
    print(f"   Nodes: {len(workflow_data['nodes'])}")
    print(f"   Edges: {len(workflow_data['edges'])}")

    # Get existing workflow
    print(f"\n📡 Fetching existing workflow from Railway...")
    response = requests.get(f"{API_URL}/workflows/1")

    if response.status_code != 200:
        print(f"❌ Failed to fetch workflow: {response.status_code}")
        print(response.text)
        return

    existing = response.json()
    print(f"✅ Found workflow: {existing['name']} (ID: {existing['id']})")

    # Update workflow
    print(f"\n🔄 Updating workflow...")
    update_response = requests.put(
        f"{API_URL}/workflows/1",
        json={
            "name": workflow_data['name'],
            "description": workflow_data.get('description'),
            "graph_definition": workflow_data
        }
    )

    if update_response.status_code == 200:
        print(f"✅ Workflow updated successfully!")
        updated = update_response.json()
        print(f"   ID: {updated['id']}")
        print(f"   Name: {updated['name']}")

        # Show optimized nodes
        print(f"\n📊 Optimized nodes:")
        print(f"   - extract_text: Removed pip install PyMuPDF")
        print(f"   - save_db: Removed pip install psycopg2-binary")
        print(f"\n   Expected performance improvement:")
        print(f"   - extract_text: 6.25s → ~1.5s (76% faster)")
        print(f"   - save_db: May also see improvement")

        return updated['id']
    else:
        print(f"❌ Failed to update workflow: {update_response.status_code}")
        print(update_response.text)
        return None

if __name__ == "__main__":
    print("=" * 70)
    print("🚀 NOVA - Update Workflow in Railway Database")
    print("=" * 70)
    print()

    workflow_id = update_workflow()

    print()
    print("=" * 70)
    if workflow_id:
        print(f"✅ Done! Workflow ID: {workflow_id}")
    else:
        print("❌ Update failed")
    print("=" * 70)
