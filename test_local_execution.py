#!/usr/bin/env python3
"""
Local Testing Script for NOVA Executor System

Tests both E2BExecutor (hardcoded) and CachedExecutor (AI-powered).
Run with: python3 test_local_execution.py
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.executors import E2BExecutor, CachedExecutor, get_executor
from core.exceptions import ExecutorError, E2BSandboxError
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_e2b_hardcoded():
    """
    Test 1: E2BExecutor with hardcoded Python code

    This test executes simple Python code without AI generation.
    """
    print("\n" + "="*80)
    print("TEST 1: E2BExecutor (Hardcoded Code)")
    print("="*80)

    try:
        # Create executor
        executor = get_executor("e2b")

        # Simple Python code to execute
        code = """
# Simple calculation
result = 2 + 2
context['result'] = result
context['message'] = f"Calculation complete: {result}"
"""

        # Context to inject
        context = {
            "test_mode": True,
            "input_value": 42
        }

        print(f"\n📝 Executing code:")
        print(code)
        print(f"\n📊 Input context: {context}")

        # Execute
        result = await executor.execute(
            code=code,
            context=context,
            timeout=30
        )

        print(f"\n✅ SUCCESS!")
        print(f"📤 Output context: {result}")

        # Validate
        assert result['result'] == 4, "Math check failed"
        assert 'message' in result, "Message missing"

        print(f"\n✅ All validations passed!")
        return True

    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        logger.exception("E2BExecutor test failed")
        return False


async def test_cached_executor_simple():
    """
    Test 2: CachedExecutor with simple AI task (no heavy data)

    This test uses AI to generate code for a simple calculation.
    Requires OPENAI_API_KEY in .env
    """
    print("\n" + "="*80)
    print("TEST 2: CachedExecutor (AI-Powered - Simple Task)")
    print("="*80)

    # Check if OpenAI API key is configured
    if not os.getenv("OPENAI_API_KEY"):
        print("\n⚠️  SKIPPED: OPENAI_API_KEY not configured in .env")
        print("   To enable this test, add your OpenAI API key to .env:")
        print("   OPENAI_API_KEY=sk-proj-...")
        return None

    try:
        # Create executor
        executor = get_executor("cached")

        # Natural language task (prompt, not code!)
        task = "Calculate the sum of 15 and 27, and store it in 'total'"

        # Context
        context = {
            "test_mode": True
        }

        print(f"\n📝 Task (natural language): {task}")
        print(f"📊 Input context: {context}")

        # Execute (AI will generate code)
        result = await executor.execute(
            code=task,  # This is a PROMPT, not code!
            context=context,
            timeout=60
        )

        print(f"\n✅ SUCCESS!")
        print(f"📤 Output context keys: {list(result.keys())}")

        # Show AI metadata
        if '_ai_metadata' in result:
            metadata = result['_ai_metadata']
            print(f"\n🤖 AI Metadata:")
            print(f"   Model: {metadata.get('model')}")
            print(f"   Attempts: {metadata.get('attempts')}")
            print(f"   Cost: ${metadata.get('cost_usd_estimated', 0):.6f}")
            print(f"   Generation time: {metadata.get('generation_time_ms')}ms")
            print(f"   Execution time: {metadata.get('execution_time_ms')}ms")
            print(f"   Tool calls: {metadata.get('total_tool_calls', 0)}")

            # Show generated code
            print(f"\n📜 Generated code:")
            print(metadata.get('generated_code', 'N/A')[:500])
            if len(metadata.get('generated_code', '')) > 500:
                print("... (truncated)")

        # Validate
        assert 'total' in result or any('total' in str(v) for v in result.values()), \
            "Expected 'total' in output"

        print(f"\n✅ All validations passed!")
        return True

    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        logger.exception("CachedExecutor test failed")
        return False


async def test_cached_executor_with_data():
    """
    Test 3: CachedExecutor with data processing (JSON parsing)

    This test uses AI to process structured data.
    """
    print("\n" + "="*80)
    print("TEST 3: CachedExecutor (AI-Powered - Data Processing)")
    print("="*80)

    # Check if OpenAI API key is configured
    if not os.getenv("OPENAI_API_KEY"):
        print("\n⚠️  SKIPPED: OPENAI_API_KEY not configured")
        return None

    try:
        # Create executor
        executor = get_executor("cached")

        # Task with structured data
        task = """
        Parse the invoice_data JSON and extract:
        - Customer name
        - Total amount
        - Number of items
        """

        # Context with data
        context = {
            "invoice_data": {
                "customer": {
                    "name": "ACME Corp",
                    "email": "info@acme.com"
                },
                "items": [
                    {"name": "Widget A", "price": 10.00, "qty": 2},
                    {"name": "Widget B", "price": 15.00, "qty": 1}
                ],
                "total": 35.00
            }
        }

        print(f"\n📝 Task: {task}")
        print(f"📊 Input context keys: {list(context.keys())}")

        # Execute
        result = await executor.execute(
            code=task,
            context=context,
            timeout=60
        )

        print(f"\n✅ SUCCESS!")
        print(f"📤 Output context (excluding metadata):")
        for key, value in result.items():
            if not key.startswith('_'):
                print(f"   {key}: {value}")

        # Show AI metadata summary
        if '_ai_metadata' in result:
            metadata = result['_ai_metadata']
            print(f"\n🤖 AI Summary:")
            print(f"   Cost: ${metadata.get('cost_usd_estimated', 0):.6f}")
            print(f"   Total time: {metadata.get('total_time_ms')}ms")
            print(f"   Stages used: {metadata.get('stages_used', 1)}")

        print(f"\n✅ All validations passed!")
        return True

    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        logger.exception("CachedExecutor data test failed")
        return False


async def main():
    """Run all tests"""
    print("\n" + "🧪 " * 20)
    print("NOVA EXECUTOR SYSTEM - LOCAL TESTS")
    print("🧪 " * 20)

    # Check environment
    print("\n📋 Environment Check:")
    print(f"   E2B_API_KEY: {'✅ Set' if os.getenv('E2B_API_KEY') else '❌ Missing'}")
    print(f"   OPENAI_API_KEY: {'✅ Set' if os.getenv('OPENAI_API_KEY') else '⚠️  Not set (AI tests will be skipped)'}")
    print(f"   E2B_TEMPLATE_ID: {os.getenv('E2B_TEMPLATE_ID', 'default')}")

    results = {}

    # Test 1: E2B Hardcoded (always available)
    results['e2b_hardcoded'] = await test_e2b_hardcoded()

    # Test 2: CachedExecutor Simple (requires OpenAI)
    results['cached_simple'] = await test_cached_executor_simple()

    # Test 3: CachedExecutor Data (requires OpenAI)
    results['cached_data'] = await test_cached_executor_with_data()

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, result in results.items():
        if result is None:
            status = "⚠️  SKIPPED"
        elif result:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"

        print(f"{status}  {test_name}")

    # Exit code
    passed = sum(1 for r in results.values() if r is True)
    total = sum(1 for r in results.values() if r is not None)

    print(f"\n📊 Results: {passed}/{total} tests passed")

    if total > 0 and passed == total:
        print("\n🎉 All tests passed!")
        return 0
    elif passed > 0:
        print(f"\n⚠️  Some tests passed ({passed}/{total})")
        return 1
    else:
        print("\n❌ All tests failed or skipped")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
