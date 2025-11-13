"""
Test AI Self-Determination approach for two-stage code generation.

This test demonstrates how AI decides whether to analyze data first
or go directly to solving the task, without using hardcoded heuristics.

The AI marks its code with stage identifiers:
- # STAGE: ANALYSIS → AI decided to analyze data first
- # STAGE: TASK → AI decided to solve directly (or this is stage 2)
"""

import asyncio
import base64
from dotenv import load_dotenv

load_dotenv()

from src.core.executors import CachedExecutor


async def test_ai_self_determination_with_pdf():
    """Test AI self-determination with complex data (PDF)."""

    # Create a dummy PDF for testing
    dummy_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n0\n%%EOF"
    pdf_b64 = base64.b64encode(dummy_pdf).decode('utf-8')

    print("=" * 80)
    print("TEST 1: AI Self-Determination with Complex Data (PDF)")
    print("=" * 80)
    print(f"\nContext:")
    print(f"  - pdf_data_b64: {len(pdf_b64)} chars (base64)")
    print(f"  - email_subject: 'Invoice #12345'")

    context = {
        "pdf_data_b64": pdf_b64,
        "email_subject": "Invoice #12345"
    }

    task = "Extract any text content from the PDF"

    print(f"\nTask: {task}")
    print("\n" + "=" * 80)
    print("EXECUTING WITH AI SELF-DETERMINATION...")
    print("=" * 80 + "\n")

    # Execute with new method
    executor = CachedExecutor(db_session=None)

    try:
        # Call the new AI self-determination method
        result = await executor._execute_with_ai_self_determination(
            task=task,
            context=context,
            timeout=60
        )

        print("\n" + "=" * 80)
        print("SUCCESS!")
        print("=" * 80)

        # Print metadata
        if "_ai_metadata" in result:
            metadata = result["_ai_metadata"]

            print(f"\n📊 AI Self-Determination Metadata:")
            print(f"  AI determined: {metadata.get('ai_self_determined')}")
            print(f"  Stages used: {metadata.get('stages_used')}")

            # Analysis stage (if used)
            if metadata.get('analysis_metadata'):
                analysis = metadata['analysis_metadata']
                print(f"\n  Stage 1 (Analysis) - AI DECIDED TO ANALYZE:")
                print(f"    - Generation time: {analysis.get('generation_time_ms')}ms")
                print(f"    - Execution time: {analysis.get('execution_time_ms')}ms")
                print(f"    - Tool calls: {len(analysis.get('tool_calls', []))}")

            # Task stage
            if metadata.get('task_metadata'):
                task_meta = metadata['task_metadata']
                print(f"\n  Stage {metadata.get('stages_used')} (Task):")
                print(f"    - Generation time: {task_meta.get('generation_time_ms')}ms")
                print(f"    - Execution time: {task_meta.get('execution_time_ms')}ms")
                print(f"    - Tool calls: {len(task_meta.get('tool_calls', []))}")

        # Print results
        print(f"\n📝 Result keys: {list(result.keys())}")
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


async def test_ai_self_determination_simple():
    """Test AI self-determination with simple data (should skip analysis)."""

    print("\n\n" + "=" * 80)
    print("TEST 2: AI Self-Determination with Simple Data")
    print("=" * 80)

    # Simple context
    context = {
        "email_subject": "Hello World",
        "amount": 250,
        "currency": "EUR"
    }

    task = "Extract the amount and currency from context"

    print(f"\nContext: {context}")
    print(f"Task: {task}")
    print("\n" + "=" * 80)
    print("EXECUTING WITH AI SELF-DETERMINATION...")
    print("=" * 80 + "\n")

    executor = CachedExecutor(db_session=None)

    try:
        result = await executor._execute_with_ai_self_determination(
            task=task,
            context=context,
            timeout=30
        )

        print("\n" + "=" * 80)
        print("SUCCESS!")
        print("=" * 80)

        metadata = result.get("_ai_metadata", {})
        print(f"\n📊 AI Self-Determination Metadata:")
        print(f"  AI determined: {metadata.get('ai_self_determined')}")
        print(f"  Stages used: {metadata.get('stages_used')}")
        print(f"  (Should be 1 - AI decided no analysis needed)")

        if metadata.get('analysis_metadata'):
            print(f"\n  ⚠️ Unexpected: AI decided to analyze simple data")
        else:
            print(f"\n  ✅ Correct: AI skipped analysis, went straight to task")

        return result

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("\n🧪 NOVA AI Self-Determination Tests\n")

    # Test 1: Complex data (PDF) - AI should decide to analyze
    result1 = asyncio.run(test_ai_self_determination_with_pdf())

    # Test 2: Simple data - AI should skip analysis
    result2 = asyncio.run(test_ai_self_determination_simple())

    print("\n\n" + "=" * 80)
    print("TESTS COMPLETE")
    print("=" * 80)

    if result1 and result2:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
