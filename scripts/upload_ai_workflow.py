"""
Upload AI-powered workflow to Railway database

This script uploads the invoice_ai_workflow.json to the database
so it can be executed via the API.
"""

import sys
import json
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models.workflow import Workflow

def upload_workflow():
    """Upload invoice AI workflow to database"""

    # Get DATABASE_URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ Error: DATABASE_URL not found in environment")
        print("Set it with: export DATABASE_URL='postgresql://...'")
        return False

    # Load workflow JSON
    workflow_path = Path(__file__).parent.parent / 'fixtures' / 'invoice_ai_workflow.json'

    if not workflow_path.exists():
        print(f"❌ Error: Workflow file not found at {workflow_path}")
        return False

    with open(workflow_path, 'r') as f:
        workflow_data = json.load(f)

    print(f"📁 Loaded workflow: {workflow_data['name']}")
    print(f"   Description: {workflow_data['description']}")
    print(f"   Nodes: {len(workflow_data['nodes'])}")
    print(f"   Edges: {len(workflow_data['edges'])}")

    # Create database session
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Check if workflow already exists
        existing = session.query(Workflow).filter_by(name=workflow_data['name']).first()

        if existing:
            print(f"\n⚠️  Workflow '{workflow_data['name']}' already exists (ID: {existing.id})")
            print("   Updating workflow definition...")

            existing.description = workflow_data['description']
            existing.graph_definition = workflow_data

            session.commit()

            print(f"✅ Workflow updated successfully!")
            print(f"   ID: {existing.id}")
            print(f"   Name: {existing.name}")

            workflow_id = existing.id
        else:
            # Create new workflow
            workflow = Workflow(
                name=workflow_data['name'],
                description=workflow_data['description'],
                graph_definition=workflow_data
            )

            session.add(workflow)
            session.commit()

            print(f"\n✅ Workflow created successfully!")
            print(f"   ID: {workflow.id}")
            print(f"   Name: {workflow.name}")

            workflow_id = workflow.id

        print(f"\n📋 Next steps:")
        print(f"   1. Execute workflow via API:")
        print(f"      curl -X POST https://web-production-a1c4f.up.railway.app/api/workflows/{workflow_id}/execute \\")
        print(f"           -H 'Content-Type: application/json' \\")
        print(f"           -d '{{\"context\": {{")
        print(f"             \"imap_host\": \"imap.gmail.com\",")
        print(f"             \"imap_port\": 993,")
        print(f"             \"email_user\": \"your-email@gmail.com\",")
        print(f"             \"email_password\": \"your-app-password\",")
        print(f"             \"smtp_host\": \"smtp.gmail.com\",")
        print(f"             \"smtp_port\": 587,")
        print(f"             \"db_host\": \"trolley.proxy.rlwy.net\",")
        print(f"             \"db_port\": 23108,")
        print(f"             \"db_name\": \"railway\",")
        print(f"             \"db_user\": \"postgres\",")
        print(f"             \"db_password\": \"KEeNOLKQWzndcAzbXAMAXzxJJrhGmPbM\"")
        print(f"           }}}}'")

        print(f"\n   2. Check execution logs in Railway dashboard")

        return True

    except Exception as e:
        print(f"\n❌ Error uploading workflow: {e}")
        session.rollback()
        return False
    finally:
        session.close()

if __name__ == "__main__":
    print("="*80)
    print("UPLOAD AI WORKFLOW TO RAILWAY")
    print("="*80)
    print()

    success = upload_workflow()

    sys.exit(0 if success else 1)
