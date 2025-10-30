"""
Test Invoice Processing Workflow WITH DATABASE PERSISTENCE

This version:
1. Loads workflow from database (workflows table)
2. Creates Execution record
3. Saves Chain of Work after each node
4. Updates Execution when complete
"""

import os
import sys
import asyncio
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from src.core.engine import GraphEngine
from src.database import get_db_session
from src.models.workflow import Workflow
from src.models.credentials import get_email_credentials, get_database_credentials

print("="* 70)
print("🧪 NOVA - Test Invoice Workflow WITH PERSISTENCE")
print("=" * 70)

async def run_workflow():
    # Get database session
    db = get_db_session()

    try:
        # Load workflow from database
        print(f"\n📂 Loading workflow from database...")
        workflow = db.query(Workflow).filter(Workflow.id == 1).first()

        if not workflow:
            print("❌ Workflow ID 1 not found in database")
            print("   Run: python3 scripts/load_invoice_workflow.py")
            return

        print(f"✅ Workflow: {workflow.name} (ID: {workflow.id})")

        # Get credentials
        print("\n🔐 Obteniendo credenciales...")
        email_creds = get_email_credentials("idom")
        db_creds = get_database_credentials("idom")

        print(f"✅ Email: {email_creds.email_user}")
        print(f"✅ Database: {db_creds.db_host}")

        # Initial context with credentials
        initial_context = {
            "client_slug": "idom",
            # Email credentials
            "email_user": email_creds.email_user,
            "email_password": email_creds.email_password,
            "imap_host": email_creds.imap_host,
            "imap_port": email_creds.imap_port,
            "smtp_host": email_creds.smtp_host,
            "smtp_port": email_creds.smtp_port,
            "sender_whitelist": email_creds.sender_whitelist,
            # Database credentials
            "db_host": db_creds.db_host,
            "db_port": db_creds.db_port,
            "db_name": db_creds.db_name,
            "db_user": db_creds.db_user,
            "db_password": db_creds.db_password,
        }

        print("\n" + "─" * 70)
        print("🚀 Ejecutando workflow CON PERSISTENCIA...")
        print("─" * 70)

        # Create engine with database session
        engine = GraphEngine(db_session=db)

        start_time = datetime.now()

        # Execute workflow (will create Execution and ChainOfWork records)
        result = await engine.execute_workflow(
            workflow_definition=workflow.graph_definition,
            initial_context=initial_context,
            workflow_id=workflow.id
        )

        execution_time = (datetime.now() - start_time).total_seconds()

        print("\n" + "=" * 70)
        if result['status'] == 'success':
            print("✅ WORKFLOW COMPLETADO")
        else:
            print("❌ WORKFLOW FALLÓ")
        print("=" * 70)

        print(f"\n⏱️  Tiempo: {execution_time:.2f}s")
        print(f"📊 Nodos: {result.get('nodes_executed', 0)}")
        print(f"💾 Execution ID: {result.get('execution_id', 'N/A')}")

        # Show trace
        print("\n📋 Trace:")
        for i, step in enumerate(result['execution_trace'], 1):
            icon = "✅" if step['status'] == 'success' else "❌"
            print(f"{i}. {icon} {step['node_id']} ({step.get('execution_time', 0):.1f}s)")
            if step.get('error_message'):
                print(f"   Error: {step['error_message']}")

        # Final context
        final = result['final_context']
        print("\n📄 Resultado:")
        print(f"Email: {final.get('email_from', 'N/A')}")
        print(f"PDF: {final.get('has_pdf', False)}")

        # Show amount (even if 0 or None)
        amount = final.get('total_amount')
        if amount is not None:
            print(f"Importe: €{amount:.2f}")
        else:
            print(f"Importe: No detectado")

        # Show which path was taken
        if final.get('high_budget_sent'):
            print(f"📧 Email enviado: Presupuesto alto")
        if final.get('invoice_saved'):
            print(f"✅ Guardado en BD - ID: {final['invoice_id']}")

        # Show database info
        if result.get('execution_id'):
            print(f"\n💾 Persistencia:")
            print(f"   Execution ID: {result['execution_id']}")
            print(f"   Chain of Work: {len(result['execution_trace'])} entradas")
            print(f"\n   Ver en BD:")
            print(f"   SELECT * FROM executions WHERE id = {result['execution_id']};")
            print(f"   SELECT * FROM chain_of_work WHERE execution_id = {result['execution_id']};")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_workflow())
