"""
Test Invoice Processing Workflow V2

Versión simplificada: inyecta credenciales en context
"""

import os
import sys
import json
import asyncio
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from src.core.engine import GraphEngine
from src.models.credentials import get_email_credentials, get_database_credentials

print("="* 70)
print("🧪 NOVA - Test Invoice Processing Workflow V2")
print("=" * 70)

async def run_workflow():
    # Load workflow
    workflow_path = os.path.join(os.path.dirname(__file__), '../fixtures/invoice_workflow_v3.json')

    print(f"\n📂 Cargando workflow...")

    with open(workflow_path, 'r') as f:
        workflow_def = json.load(f)

    print(f"✅ Workflow: {workflow_def['name']}")

    # Get credentials and inject in context
    print("\n🔐 Obteniendo credenciales...")
    email_creds = get_email_credentials("idom")
    db_creds = get_database_credentials("idom")

    print(f"✅ Email: {email_creds.email_user}")
    print(f"✅ Database: {db_creds.db_host}")

    # Initial context with ALL credentials
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
    print("🚀 Ejecutando workflow...")
    print("─" * 70)

    engine = GraphEngine()
    start_time = datetime.now()

    try:
        result = await engine.execute_workflow(
            workflow_definition=workflow_def,
            initial_context=initial_context
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

        # Show OCR text length for debugging
        ocr_text = final.get('ocr_text', '')
        if ocr_text:
            print(f"\n📝 Texto OCR: {len(ocr_text)} caracteres")
            print(f"Primeros 200 caracteres:")
            print(ocr_text[:200])

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_workflow())
