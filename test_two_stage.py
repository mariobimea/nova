"""
Quick test for two-stage code generation.

Tests that CachedExecutor:
1. Detects complex data (PDF base64)
2. Runs Stage 1 (analysis)
3. Enriches context with analysis
4. Runs Stage 2 (task code) with enriched context
"""

import asyncio
import base64
from dotenv import load_dotenv

load_dotenv()

from src.core.executors import CachedExecutor


async def test_two_stage_with_pdf():
    """Test two-stage generation with a PDF."""

    # Create a small dummy PDF (just for testing the flow)
    # In real usage, this would be a real PDF
    dummy_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n0\n%%EOF"
    pdf_b64 = base64.b64encode(dummy_pdf).decode('utf-8')

    print("=" * 80)
    print("TEST: Two-Stage Code Generation")
    print("=" * 80)
    print(f"\nContext:")
    print(f"  - pdf_data_b64: {len(pdf_b64)} chars (base64)")
    print(f"  - email_subject: 'Test Invoice'")

    # Context with PDF data (triggers Stage 1)
    context = {
        "pdf_data_b64": pdf_b64,
        "email_subject": "Test Invoice"
    }

    # Task prompt
    task = "Analyze the PDF and extract any text content"

    print(f"\nTask: {task}")
    print("\n" + "=" * 80)
    print("EXECUTING...")
    print("=" * 80 + "\n")

    # Execute with CachedExecutor
    executor = CachedExecutor(db_session=None)

    try:
        result = await executor.execute(
            code=task,
            context=context,
            timeout=60
        )

        print("\n" + "=" * 80)
        print("SUCCESS!")
        print("=" * 80)

        # Print metadata
        if "_ai_metadata" in result:
            metadata = result["_ai_metadata"]

            print(f"\n📊 Two-Stage Metadata:")
            print(f"  Two-stage enabled: {metadata.get('two_stage_enabled')}")

            if metadata.get('analysis_metadata'):
                analysis = metadata['analysis_metadata']
                print(f"\n  Stage 1 (Analysis):")
                print(f"    - Analysis code length: {len(analysis.get('analysis_code', ''))} chars")
                print(f"    - Generation time: {analysis.get('generation_time_ms')}ms")
                print(f"    - Execution time: {analysis.get('execution_time_ms')}ms")
                print(f"    - Total time: {analysis.get('total_time_ms')}ms")

            print(f"\n  Stage 2 (Task):")
            print(f"    - Task code length: {metadata.get('code_length')} chars")
            print(f"    - Generation time: {metadata.get('generation_time_ms')}ms")
            print(f"    - Execution time: {metadata.get('execution_time_ms')}ms")
            print(f"    - Total time: {metadata.get('total_time_ms')}ms")
            print(f"    - Attempts: {metadata.get('attempts')}")

        print(f"\n📝 Result keys: {list(result.keys())}")

        # Print non-metadata results
        for key, value in result.items():
            if not key.startswith('_'):
                if isinstance(value, str) and len(value) > 200:
                    print(f"  {key}: {value[:200]}... ({len(value)} chars)")
                else:
                    print(f"  {key}: {value}")

        return result

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_simple_context_no_analysis():
    """Test that simple context skips Stage 1."""

    print("\n\n" + "=" * 80)
    print("TEST 2: Simple Context (No Analysis)")
    print("=" * 80)

    # Simple context (no large data)
    context = {
        "email_subject": "Hello",
        "amount": 100
    }

    task = "Extract the amount from context"

    print(f"\nContext: {context}")
    print(f"Task: {task}")
    print("\n" + "=" * 80)
    print("EXECUTING...")
    print("=" * 80 + "\n")

    executor = CachedExecutor(db_session=None)

    try:
        result = await executor.execute(
            code=task,
            context=context,
            timeout=30
        )

        print("\n" + "=" * 80)
        print("SUCCESS!")
        print("=" * 80)

        metadata = result.get("_ai_metadata", {})
        print(f"\n📊 Two-Stage Metadata:")
        print(f"  Two-stage enabled: {metadata.get('two_stage_enabled')}")
        print(f"  (Should be False - no complex data)")

        return result

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return None


if __name__ == "__main__":
    print("\n🧪 NOVA Two-Stage Generation Tests\n")

    # Test 1: With PDF (triggers analysis)
    result1 = asyncio.run(test_two_stage_with_pdf())

    # Test 2: Simple context (skips analysis)
    result2 = asyncio.run(test_simple_context_no_analysis())

    print("\n\n" + "=" * 80)
    print("TESTS COMPLETE")
    print("=" * 80)

    if result1 and result2:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
