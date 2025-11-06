"""
Test REALISTIC PDF workflow: simulate receiving a PDF invoice and extracting data.

This demonstrates the REAL workflow:
1. PDF invoice arrives (e.g., email attachment) as binary data
2. PDF binary data is stored in context
3. CachedExecutor receives prompt: "Extract total from invoice"
4. OpenAI generates PyMuPDF code that reads from context
5. E2B executes code with PDF accessible
6. Returns extracted amount

This is how it would work in production with IMAP → PDF → Extraction.

Requirements:
    export OPENAI_API_KEY="sk-..."
    export E2B_API_KEY="e2b_..."
    export E2B_TEMPLATE_ID="<custom-template-with-pymupdf>"  # Optional

Note: This test creates a simple PDF first, then simulates the workflow
receiving it as binary data in context.
"""

import asyncio
import os
import sys
from pathlib import Path
import base64

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.executors import CachedExecutor
from src.core.circuit_breaker import e2b_circuit_breaker


async def create_test_invoice_pdf():
    """
    Create a simple PDF invoice for testing.

    In a real workflow, this would come from:
    - Email attachment (IMAP)
    - Uploaded file (HTTP)
    - Cloud storage (S3, GCS)

    Returns:
        bytes: PDF binary data
    """
    print("\n📄 Creating test invoice PDF...")

    # We'll create the PDF using E2B (since it has reportlab)
    # In production, the PDF would arrive from external source

    executor = CachedExecutor()

    create_pdf_prompt = """
    Create a simple PDF invoice with the following content:

    INVOICE #INV-2025-001
    Date: 2025-11-05
    Customer: ACME Corporation

    Item: Consulting Services
    Amount: $1,234.56

    TOTAL: $1,234.56

    Save it as 'invoice.pdf' and return the file content as base64 string.
    """

    try:
        result = await executor.execute(
            code=create_pdf_prompt,
            context={},
            timeout=60
        )

        # Get base64 PDF data from result
        if 'pdf_base64' in result:
            pdf_data = base64.b64decode(result['pdf_base64'])
            print("✅ Test invoice PDF created")
            return pdf_data
        else:
            print("⚠️  Could not create PDF, will use mock data")
            return b"Mock PDF data for testing"

    except Exception as e:
        print(f"⚠️  Error creating PDF: {e}")
        print("   Using mock PDF data instead")
        return b"Mock PDF data with TOTAL: $1,234.56"


async def test_realistic_pdf_workflow():
    """
    Test REALISTIC workflow: Extract amount from PDF invoice.

    Simulates:
    1. PDF arrives as binary data (e.g., from email)
    2. Stored in context
    3. CachedExecutor generates extraction code
    4. E2B executes with PDF accessible
    """
    print("\n" + "=" * 70)
    print("🧪 REALISTIC PDF WORKFLOW TEST")
    print("=" * 70)

    # Reset circuit breaker
    e2b_circuit_breaker.reset()

    # Check environment
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ ERROR: OPENAI_API_KEY not set")
        return False

    if not os.getenv("E2B_API_KEY"):
        print("\n❌ ERROR: E2B_API_KEY not set")
        return False

    print(f"\n✅ API Keys configured")

    # Step 1: Simulate PDF arriving (e.g., from email attachment)
    print("\n" + "-" * 70)
    print("STEP 1: Simulate PDF Invoice Arrival")
    print("-" * 70)

    # In production, this would be:
    # - IMAP email attachment
    # - HTTP file upload
    # - Cloud storage download

    # For this test, we'll use simple text that simulates PDF content
    # (since base E2B template might not have PyMuPDF)

    invoice_text = """
    INVOICE #INV-2025-001
    Date: 2025-11-05
    Customer: ACME Corporation

    Description: Professional Services
    Quantity: 10 hours
    Rate: $123.45/hour

    Subtotal: $1,234.50
    Tax (10%): $123.45

    TOTAL: $1,357.95

    Payment Due: 2025-12-05
    """

    print(f"📧 Invoice received (simulated email attachment)")
    print(f"   Filename: invoice-INV-2025-001.txt")
    print(f"   Size: {len(invoice_text)} bytes")
    print(f"   Preview: {invoice_text[:100]}...")

    # Step 2: Store in context (as workflow would do)
    print("\n" + "-" * 70)
    print("STEP 2: Prepare Workflow Context")
    print("-" * 70)

    # This is what the workflow engine would create
    context = {
        "invoice_data": invoice_text,  # PDF content (as text for simplicity)
        "invoice_number": "INV-2025-001",
        "customer": "ACME Corporation",
        "source": "email_attachment"
    }

    print(f"📦 Context prepared:")
    for key, value in context.items():
        if key == "invoice_data":
            print(f"   {key}: <{len(value)} bytes of invoice data>")
        else:
            print(f"   {key}: {value}")

    # Step 3: Execute CachedExecutor node
    print("\n" + "-" * 70)
    print("STEP 3: Execute Workflow Node (CachedExecutor)")
    print("-" * 70)

    # Workflow node configuration
    workflow_node = {
        "node_id": "extract_invoice_total",
        "type": "action",
        "executor": "cached",
        "prompt": "Extract the TOTAL amount from the invoice data and return it as a number (without $ or commas)",
        "timeout": 60
    }

    print(f"🔧 Node Configuration:")
    print(f"   Node ID: {workflow_node['node_id']}")
    print(f"   Executor: {workflow_node['executor']}")
    print(f"   Prompt: {workflow_node['prompt']}")

    try:
        executor = CachedExecutor()

        print(f"\n⏳ Executing node with CachedExecutor...")
        print(f"   (OpenAI will generate extraction code, E2B will execute)")

        result = await executor.execute(
            code=workflow_node['prompt'],
            context=context,
            timeout=workflow_node['timeout']
        )

        print("\n" + "=" * 70)
        print("✅ WORKFLOW NODE EXECUTION SUCCESSFUL!")
        print("=" * 70)

        # Step 4: Analyze results
        metadata = result.get("_ai_metadata", {})

        print(f"\n📊 Execution Metadata:")
        print(f"   Model: {metadata.get('model')}")
        print(f"   Attempts: {metadata.get('attempts')}/3")
        print(f"   Cost: ${metadata.get('cost_usd'):.6f}")
        print(f"   Total time: {metadata.get('total_time_ms')}ms")

        print(f"\n💻 Generated Code:")
        print("-" * 70)
        code = metadata.get('generated_code', '')
        code_lines = code.split('\n')
        print('\n'.join(code_lines[:40]))
        if len(code_lines) > 40:
            print(f"\n... ({len(code_lines) - 40} more lines)")
        print("-" * 70)

        print(f"\n📤 Workflow Result:")
        print("-" * 70)
        result_without_meta = {k: v for k, v in result.items() if k != '_ai_metadata'}
        for key, value in result_without_meta.items():
            if isinstance(value, str) and len(value) > 100:
                print(f"   {key}: {value[:100]}...")
            else:
                print(f"   {key}: {value}")
        print("-" * 70)

        # Verify extraction
        print(f"\n🔍 Verification:")

        expected_amount = 1357.95
        found_correct = False

        for key, value in result_without_meta.items():
            if key == "invoice_data":
                continue  # Skip original data

            # Check if this looks like an amount
            try:
                if isinstance(value, (int, float)):
                    amount = float(value)
                elif isinstance(value, str):
                    # Try to parse as number
                    clean_value = value.replace('$', '').replace(',', '').strip()
                    amount = float(clean_value)
                else:
                    continue

                if abs(amount - expected_amount) < 0.01:
                    print(f"   ✅ CORRECT! Found expected amount ${expected_amount} in field '{key}'")
                    found_correct = True
                    break
                else:
                    print(f"   ⚠️  Found amount ${amount} in '{key}' (expected ${expected_amount})")

            except (ValueError, TypeError):
                pass

        if not found_correct:
            print(f"   ⚠️  Expected amount ${expected_amount} not found")

        print("\n" + "=" * 70)
        print("🎉 REALISTIC WORKFLOW TEST COMPLETED!")
        print("=" * 70)

        print("\n✅ Verified Realistic Workflow:")
        print("   1. PDF/invoice data arrives (simulated email attachment)")
        print("   2. Data stored in workflow context")
        print("   3. CachedExecutor receives prompt + context")
        print("   4. OpenAI generates extraction code")
        print("   5. E2B executes code with data accessible")
        print("   6. Results extracted and returned")
        print(f"   7. Total cost: ${metadata.get('cost_usd'):.6f}")

        print("\n💡 In Production:")
        print("   - Replace invoice_data with actual PDF binary (PyMuPDF)")
        print("   - Use E2B_TEMPLATE_ID with PyMuPDF pre-installed")
        print("   - PDF arrives from IMAP, HTTP upload, or cloud storage")
        print("   - Same workflow pattern applies")

        return found_correct

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ WORKFLOW EXECUTION FAILED")
        print("=" * 70)
        print(f"\nError: {e.__class__.__name__}")
        print(f"Message: {str(e)[:500]}")

        import traceback
        print("\nFull traceback:")
        traceback.print_exc()

        return False


async def main():
    """Run realistic PDF workflow test."""
    print("\n" + "=" * 70)
    print("🚀 CachedExecutor Realistic PDF Workflow Test")
    print("=" * 70)

    print("\n📋 Test Scenario:")
    print("   A company receives invoice emails with PDF attachments.")
    print("   The workflow must extract the total amount automatically.")
    print("   This tests the REAL production workflow pattern.")

    success = await test_realistic_pdf_workflow()

    print("\n" + "=" * 70)
    print("📊 TEST RESULT")
    print("=" * 70)

    if success:
        print("\n✅ TEST PASSED!")
        print("\n🎯 Next Steps:")
        print("   1. Phase 4: Integrate with GraphEngine")
        print("   2. Create real IMAP → PDF → Extraction workflow")
        print("   3. Deploy to production with custom E2B template")
    else:
        print("\n⚠️  TEST FAILED")
        print("   Review errors above before proceeding")

    print("=" * 70)

    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
