"""
Load Invoice Processing Workflow to Database

This script loads the invoice processing workflow from fixtures
into the workflows table in PostgreSQL.
"""

import os
import sys
import json

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from src.database import get_db
from src.models.workflow import Workflow

def load_workflow():
    """Load invoice workflow from JSON fixture into database"""

    # Load workflow JSON
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        '../fixtures/invoice_workflow_v3.json'
    )

    print(f"📂 Loading workflow from: {fixture_path}")

    with open(fixture_path, 'r') as f:
        workflow_data = json.load(f)

    print(f"✅ Loaded workflow: {workflow_data['name']}")
    print(f"   Description: {workflow_data.get('description', 'N/A')}")
    print(f"   Nodes: {len(workflow_data['nodes'])}")
    print(f"   Edges: {len(workflow_data['edges'])}")

    # Create workflow object
    with get_db() as db:
        # Check if workflow already exists
        existing = db.query(Workflow).filter(
            Workflow.name == workflow_data['name']
        ).first()

        if existing:
            print(f"\n⚠️  Workflow '{workflow_data['name']}' already exists (ID: {existing.id})")
            response = input("Do you want to update it? (y/n): ")

            if response.lower() == 'y':
                # Update existing workflow
                existing.description = workflow_data.get('description')
                existing.graph_definition = workflow_data
                db.commit()
                print(f"✅ Workflow updated (ID: {existing.id})")
                return existing.id
            else:
                print("❌ Cancelled")
                return existing.id

        # Create new workflow
        workflow = Workflow(
            name=workflow_data['name'],
            description=workflow_data.get('description'),
            graph_definition=workflow_data
        )

        db.add(workflow)
        db.commit()

        print(f"\n✅ Workflow created successfully!")
        print(f"   ID: {workflow.id}")
        print(f"   Name: {workflow.name}")

        return workflow.id

if __name__ == "__main__":
    print("="* 70)
    print("🚀 NOVA - Load Invoice Workflow to Database")
    print("=" * 70)
    print()

    workflow_id = load_workflow()

    print()
    print("=" * 70)
    print(f"✅ Done! Workflow ID: {workflow_id}")
    print("=" * 70)
