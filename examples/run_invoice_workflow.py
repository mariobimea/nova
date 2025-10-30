"""
Test Invoice Processing Workflow

Este script ejecuta el workflow completo de procesamiento de facturas.

Prerequisitos:
1. Email con PDF en ferrermarinmario@gmail.com
2. Email debe ser de mario@bimea.es (whitelist)
3. PDF debe contener un importe

El workflow hará:
- Leer email no leído
- Extraer PDF
- OCR del PDF
- Encontrar importe total
- Si > €1000: enviar email "presupuesto alto"
- Si < €1000: guardar en BD de IDOM

Usage:
    python examples/run_invoice_workflow.py
"""

import os
import sys
import json
import asyncio
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from src.core.engine import GraphEngine

print("="* 70)
print("🧪 NOVA - Test Invoice Processing Workflow")
print("=" * 70)

async def run_workflow():
    # Load workflow definition
    workflow_path = os.path.join(
        os.path.dirname(__file__),
        '../fixtures/invoice_processing_workflow.json'
    )

    print(f"\n📂 Cargando workflow: {workflow_path}")

    with open(workflow_path, 'r') as f:
        workflow_def = json.load(f)

    print(f"✅ Workflow cargado: {workflow_def['name']}")
    print(f"   Nodos: {len(workflow_def['nodes'])}")
    print(f"   Edges: {len(workflow_def['edges'])}")

    # Initial context
    initial_context = {
        "client_slug": "idom",
        "workflow_id": 1,  # TODO: Get from DB
        "execution_id": 1  # TODO: Get from DB
    }

    print("\n" + "─" * 70)
    print("🚀 Ejecutando workflow...")
    print("─" * 70)

    # Create engine
    engine = GraphEngine()

    # Execute workflow
    start_time = datetime.now()

    try:
        result = await engine.execute_workflow(
            workflow_definition=workflow_def,
            initial_context=initial_context
        )

        execution_time = (datetime.now() - start_time).total_seconds()

        print("\n" + "=" * 70)
        if result['status'] == 'success':
            print("✅ WORKFLOW COMPLETADO EXITOSAMENTE")
        else:
            print("❌ WORKFLOW FALLÓ")
        print("=" * 70)

        print(f"\n⏱️  Tiempo de ejecución: {execution_time:.2f}s")
        print(f"📊 Nodos ejecutados: {result.get('nodes_executed', 0)}")

        # Show execution trace
        print("\n" + "─" * 70)
        print("📋 Chain of Work (Trace de Ejecución):")
        print("─" * 70)

        for i, step in enumerate(result['execution_trace'], 1):
            status_icon = "✅" if step['status'] == 'success' else "❌"
            print(f"\n{i}. {status_icon} {step['node_id']} ({step['node_type']})")
            print(f"   Tiempo: {step.get('execution_time', 0):.2f}s")

            if step['node_type'] == 'decision':
                print(f"   Decisión: {step.get('decision_result')}")
                print(f"   Path: {step.get('path_taken')}")

            if step['status'] == 'failed':
                print(f"   ❌ Error: {step.get('error_message')}")

        # Show final context
        print("\n" + "─" * 70)
        print("📄 Resultado Final:")
        print("─" * 70)

        final_ctx = result['final_context']

        print(f"\n📧 Email:")
        print(f"   From: {final_ctx.get('email_from', 'N/A')}")
        print(f"   Subject: {final_ctx.get('email_subject', 'N/A')}")
        print(f"   Has PDF: {final_ctx.get('has_pdf', False)}")

        if final_ctx.get('has_pdf'):
            print(f"\n📄 PDF:")
            print(f"   Filename: {final_ctx.get('pdf_filename')}")
            print(f"   Size: {final_ctx.get('pdf_size_bytes', 0)} bytes")
            print(f"   OCR Method: {final_ctx.get('ocr_method')}")

            print(f"\n💰 Importe:")
            print(f"   Total: €{final_ctx.get('total_amount', 0):.2f}")
            print(f"   Currency: {final_ctx.get('currency', 'N/A')}")

            if final_ctx.get('invoice_saved'):
                print(f"\n💾 Guardado en BD:")
                print(f"   Invoice ID: {final_ctx.get('invoice_id')}")
                print(f"   ✅ Factura guardada en BD de IDOM")

            elif final_ctx.get('high_budget_email_sent'):
                print(f"\n📧 Email enviado:")
                print(f"   ✅ Email de presupuesto alto enviado")

        elif final_ctx.get('rejection_sent'):
            print(f"\n❌ Email rechazado:")
            print(f"   Razón: Sin PDF adjunto")

        print("\n" + "=" * 70)

    except Exception as e:
        print(f"\n❌ ERROR EJECUTANDO WORKFLOW:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("\n💡 Prerequisitos:")
    print("   1. Email no leído en ferrermarinmario@gmail.com")
    print("   2. Email debe ser de mario@bimea.es")
    print("   3. Email debe tener PDF adjunto con importe")
    print("\n🚀 Ejecutando workflow...\n")

    asyncio.run(run_workflow())
